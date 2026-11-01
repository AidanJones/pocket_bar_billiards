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

const SETTLE_SECONDS := 6.0
const DROP_CLEARANCE := 0.05

var game: Node3D
var layout: Dictionary
var holes: Array = []
var lanes: Array = []
var index := -1
var elapsed := 0.0
var probe: RigidBody3D
var results: Array = []
var started := false


func run(owner_game: Node3D) -> void:
	game = owner_game
	layout = game.layout
	holes = layout.get("holes", [])
	lanes = layout.get("return_lanes", [])
	print("[smoke] %d holes, %s return" % [
		holes.size(), "sorted" if lanes.size() > 0 else "shared"])
	for ball in game.balls:
		ball.queue_free()
	game.balls.clear()
	started = true
	_next()


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


func _make_probe(at: Vector3) -> RigidBody3D:
	var body := RigidBody3D.new()
	body.mass = game.ball_mass
	body.continuous_cd = true
	var mat := PhysicsMaterial.new()
	mat.bounce = 0.55
	mat.friction = 0.25
	body.physics_material_override = mat
	var shape := CollisionShape3D.new()
	var sphere := SphereShape3D.new()
	sphere.radius = float(layout["ball_radius"])
	shape.shape = sphere
	body.add_child(shape)
	body.position = at
	game.add_child(body)
	return body


func _physics_process(delta: float) -> void:
	if not started or probe == null:
		return
	elapsed += delta
	var at_rest := probe.linear_velocity.length() < 0.03
	if elapsed > SETTLE_SECONDS or (at_rest and elapsed > 1.0):
		_record()
		_next()


func _record() -> void:
	var hole: Dictionary = holes[index]
	var pos: Vector3 = probe.global_position
	var below: bool = pos.y < game.bed_height - float(layout["ball_radius"])
	var lane := _lane_at(pos.x)
	results.append({
		"score": int(hole["score"]),
		"x": pos.x, "y": pos.y, "z": pos.z,
		"below_bed": below,
		"lane": lane,
	})


## Which return lane an X falls in, or 0 when the table has none.
func _lane_at(x: float) -> int:
	for lane in lanes:
		if float(lane["x0"]) <= x and x <= float(lane["x1"]):
			return int(lane["score"])
	return 0


func _report() -> void:
	var failures := 0
	var sorted_return := lanes.size() > 0
	print("[smoke] %-5s %-9s %-8s %s" % ["hole", "returned", "lane", "resting place (m)"])
	for r in results:
		var ok: bool = r["below_bed"]
		var lane_note := "-"
		if sorted_return:
			lane_note = str(r["lane"])
			ok = ok and r["lane"] == r["score"]
		if not ok:
			failures += 1
		print("[smoke] %-5d %-9s %-8s (%+.3f, %+.3f, %+.3f) %s" % [
			r["score"], "yes" if r["below_bed"] else "NO", lane_note,
			r["x"], r["y"], r["z"], "" if ok else "  <-- FAIL"])
	print("[smoke] %d of %d holes returned correctly" % [results.size() - failures, results.size()])
	if failures > 0:
		push_error("%d hole(s) did not return as designed" % failures)
	get_tree().quit(1 if failures > 0 else 0)
