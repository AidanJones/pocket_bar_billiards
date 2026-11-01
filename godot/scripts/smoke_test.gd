extends Node

## Headless physics check: does a ball actually come home, and does the
## sorted return actually sort?
##
## This is the thing the simulation is for. The geometry checks in
## `check.py` can prove a lane is wide enough and that no wall sits under a
## hole; they cannot prove that a ball dropped through the 100 ends up in
## the 100's lane rather than bouncing into the 200's. So: drop a ball
## through each hole in turn, let it run, and report where it finished.
##
##     python godot/tools/physics_test.py
##
## Exits non-zero if a ball never reaches the tray, or lands in the wrong
## lane when the table was generated with --return sorted.

const SETTLE_SECONDS := 10.0      ## give up on a ball after this long
const REST_SPEED := 0.015         ## m/s below which it counts as stopped
const REST_HOLD := 0.4            ## ...and for how long, so a bounce is not rest
const DROP_CLEARANCE := 0.05
const WARMUP_FRAMES := 30         ## physics steps to settle before the first drop

var game: Node3D
var layout: Dictionary
var holes: Array = []
var lanes: Array = []
var index := -1
var elapsed := 0.0
var probe: RigidBody3D
var results: Array = []
var started := false
var still_for := 0.0
var escaped_at := -1.0
var escaped_from := Vector3.ZERO
var warmup := 0


func run(owner_game: Node3D) -> void:
	game = owner_game
	layout = game.layout
	holes = layout.get("holes", [])
	lanes = layout.get("return_lanes", [])
	print("[smoke] %d holes, %s return, %.1f mm ball" % [
		holes.size(), "sorted" if lanes.size() > 0 else "shared",
		float(layout["ball_diameter"]) * 1000.0])
	# Godot's solver is tuned for roughly human-scale objects. Below about
	# 20 mm the contact tolerances are a sizeable fraction of the ball and
	# results stop meaning much either way, which is why the exporter runs
	# the game life size.
	if float(layout["ball_diameter"]) < 0.02:
		print("[smoke] NOTE: that is small for the physics engine — treat "
			+ "anything below ~20 mm as inconclusive, not as a design fault")
	for ball in game.balls:
		ball.queue_free()
	game.balls.clear()
	# Let the engine settle before dropping anything. The first frame after a
	# scene is built carries a large delta, and a ball integrated across it
	# moves further than its own radius — straight through a wall. It is why
	# only ever the first hole failed.
	started = true


func _next() -> void:
	if probe != null:
		probe.queue_free()
		probe = null
	index += 1
	if index >= holes.size():
		_report()
		return
	var hole: Dictionary = holes[index]
	probe = _make_probe(Vector3(hole["x"], game.bed_height + DROP_CLEARANCE, hole["z"]))
	elapsed = 0.0
	still_for = 0.0
	escaped_at = -1.0


func _make_probe(at: Vector3) -> RigidBody3D:
	var body := RigidBody3D.new()
	body.mass = game.ball_mass
	body.continuous_cd = true
	var mat := PhysicsMaterial.new()
	# An acetal ball on a PLA ramp is fairly dead; 0.55 was lively enough to
	# ricochet a ball into the corner of the tray and squeeze it out.
	mat.bounce = 0.25
	mat.friction = 0.3
	body.physics_material_override = mat
	# A 3 degree ramp barely moves a sleeping body, and Godot is keen to put
	# a slow one to sleep — which would read as "it stopped here" when really
	# it had not finished rolling.
	body.can_sleep = false
	var shape := CollisionShape3D.new()
	var sphere := SphereShape3D.new()
	sphere.radius = float(layout["ball_radius"])
	shape.shape = sphere
	body.add_child(shape)
	body.position = at
	game.add_child(body)
	return body


func _physics_process(delta: float) -> void:
	if not started:
		return
	if warmup < WARMUP_FRAMES:
		warmup += 1
		if warmup == WARMUP_FRAMES:
			_next()
		return
	if probe == null:
		return
	elapsed += delta
	# Note the first moment a ball leaves the footprint of the table: if one
	# ends up on the floor, this says where it got out.
	if escaped_at < 0.0 and not _inside_table(probe.global_position):
		escaped_at = elapsed
		escaped_from = probe.global_position
	if probe.linear_velocity.length() < REST_SPEED:
		still_for += delta
	else:
		still_for = 0.0
	if elapsed > SETTLE_SECONDS or (still_for > REST_HOLD and elapsed > 1.0):
		_record()
		_next()


func _record() -> void:
	var hole: Dictionary = holes[index]
	var pos: Vector3 = probe.global_position
	var tray: Dictionary = layout.get("tray", {})
	var in_tray := false
	if not tray.is_empty():
		in_tray = (pos.z >= float(tray["z0"]) and pos.z <= float(tray["z1"])
			and pos.x >= float(tray["x0"]) and pos.x <= float(tray["x1"])
			and pos.y < game.bed_height)
	results.append({
		"score": int(hole["score"]),
		"x": pos.x, "y": pos.y, "z": pos.z,
		"below_bed": pos.y < game.bed_height - float(layout["ball_radius"]),
		"in_tray": in_tray,
		"on_floor": pos.y < float(layout["ball_radius"]) * 2.0,
		"lane": _lane_at(pos.x),
		"seconds": elapsed,
		"escaped_at": escaped_at,
		"escaped_from": escaped_from,
	})
	if escaped_at >= 0.0:
		print("[smoke]   ...left the table at t=%.2fs from (%+.3f, %+.3f, %+.3f)" % [
			escaped_at, escaped_from.x, escaped_from.y, escaped_from.z])


func _inside_table(p: Vector3) -> bool:
	var half_w: float = float(layout["playing_width"]) * 0.5 + 0.06
	var length: float = float(layout["playing_length"])
	return absf(p.x) <= half_w and p.z <= 0.45 and p.z >= -length - 0.1


## Which return lane an X falls in, or 0 when the table has none.
func _lane_at(x: float) -> int:
	for lane in lanes:
		if float(lane["x0"]) <= x and x <= float(lane["x1"]):
			return int(lane["score"])
	return 0


func _report() -> void:
	var failures := 0
	var sorted_return := lanes.size() > 0
	print("[smoke] %-5s %-8s %-6s %-5s %s" % [
		"hole", "where", "lane", "secs", "resting place (m)"])
	for r in results:
		var where := "tray"
		if r["on_floor"]:
			where = "FLOOR"
		elif not r["in_tray"]:
			where = "stuck" if r["below_bed"] else "ON BED"
		var ok: bool = r["in_tray"]
		var lane_note := "-"
		if sorted_return:
			lane_note = str(r["lane"])
			ok = ok and r["lane"] == r["score"]
		if not ok:
			failures += 1
		print("[smoke] %-5d %-8s %-6s %-5.1f (%+.3f, %+.3f, %+.3f)%s" % [
			r["score"], where, lane_note, r["seconds"],
			r["x"], r["y"], r["z"], "" if ok else "   <-- FAIL"])
	print("[smoke] %d of %d balls reached the tray%s" % [
		results.size() - failures, results.size(),
		" in the right lane" if sorted_return else ""])
	if failures > 0:
		push_error("%d ball(s) did not come home" % failures)
	get_tree().quit(1 if failures > 0 else 0)
