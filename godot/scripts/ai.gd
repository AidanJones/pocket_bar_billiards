extends Node

## The computer player. It plays the shot a pool player would look for:
## for every ball it may hit and every hole, find the "ghost ball" spot the
## played ball must reach to send that ball at the hole, check both paths
## are clear by sweeping a ball along them through the real physics space
## (skittles, cushions and other balls included), and weigh the hole's value
## against how hard the cut and the distance make it. It tries a few spots
## across the D, and never runs its own ball over a hole on the way. Then
## it misses a little, as people do (`skill_noise`).
##
## No pot on? It plays safe: a gentle touch on the nearest ball it can find
## a line to, so it at least does not foul, and never a line into a skittle. With the bar down and one ball
## left it tries a single-cushion bank into the 100 or 200, as the rules ask.
##
## Pace comes from a model of how far a struck ball runs on the felt,
## fitted to game.gd's felt physics by tests/test_game.gd's calibration
## (`-- --scenarios --calibrate` prints the measurements), which also
## checks the fit on every run.

## How far a ball struck at v0 runs: it slides first, losing to friction
## until it rolls at SLIDE_KEEP * v0, then slows as dv/dt = -DECAY*v - DRAG.
const SLIDE_KEEP := 0.74        ## a solid sphere keeps 5/7
const DECAY := 0.68
const DRAG := 0.08
const ARRIVE := 0.25              ## m/s the object ball should reach the hole at
const TRANSFER := 0.92            ## share of speed passed on in a full contact
const MAX_CUT := deg_to_rad(68.0)
const THINK := 0.7                ## seconds before it starts to aim
const SHOW := 0.9                 ## seconds it shows the cue drawn back

## 0 = perfect; 1 = a decent pub player.
@export var skill_noise := 1.0
const AIM_SPREAD := deg_to_rad(0.7)
const PACE_SPREAD := 0.06

var game: Node3D
var _busy := false
var last_plan := {}               ## for tests and the log


func _physics_process(_delta: float) -> void:
	if _busy or game == null or not game.computer_turn():
		return
	_busy = true
	_take_turn()


func _take_turn() -> void:
	await get_tree().create_timer(THINK, true, true).timeout
	if not game.computer_turn():
		_busy = false
		return
	var plan := choose()
	last_plan = plan
	game.place_in_d(plan["spot"])
	var cue: Node = game.get_node("Cue")
	var dir: Vector3 = plan["direction"].rotated(Vector3.UP, randfn(0.0, AIM_SPREAD * skill_noise))
	var strength: float = clampf(plan["strength"] * (1.0 + randfn(0.0, PACE_SPREAD * skill_noise)), 0.03, 1.0)
	# Draw the cue back so a person can see what it is about to do.
	var from: Vector3 = game.cue_ball.global_position
	cue.aim_from = from
	cue.aiming = true
	var t := 0.0
	while t < SHOW:
		t += get_physics_process_delta_time()
		cue.aim_to = from - dir * cue.MAX_DRAG * strength * minf(1.0, t / (SHOW * 0.7))
		await get_tree().physics_frame
		if not game.computer_turn():
			cue.aiming = false
			_busy = false
			return
	cue.aiming = false
	print("[ai] %s from %s, %s at %.0f%%" % [plan["why"], game.cue_ball.global_position,
		dir, strength * 100.0])
	cue.play(dir, strength)
	_busy = false


## The best shot from here: {spot: Vector2, direction: Vector3, strength,
## why, value}.
func choose() -> Dictionary:
	var r := float(game.layout["ball_radius"])
	# Where a ball really rides: the felt is not in the mesh, so that is a
	# little below bed_height + r. The ball in the D is sitting on it.
	var y: float = game.cue_ball.global_position.y
	var best := {}
	var best_score := -1.0
	var others: Array = []
	for b in game.balls:
		if b != game.cue_ball and game.on_felt(b):
			others.append(b)
	for spot in _spots(others, r):
		var from := Vector3(spot.x, y, spot.y)
		if others.is_empty():
			for plan in _banks(from, y):
				if plan["value"] > best_score:
					best_score = plan["value"]
					best = plan
			continue
		for t in others:
			if game.rules.opening and t != game.red_ball:
				continue
			var at: Vector3 = (t as Node3D).global_position
			at.y = y
			for hole in game.layout["holes"]:
				var h := Vector3(hole["x"], y, hole["z"])
				var to_hole := h - at
				var d2 := to_hole.length()
				if d2 < 1e-3:
					continue
				var u := to_hole / d2
				var ghost := at - u * 2.0 * r
				var aim := ghost - from
				var d1 := aim.length()
				if d1 < r:
					continue
				var dir := aim / d1
				var cut := acos(clampf(dir.dot(u), -1.0, 1.0))
				if cut > MAX_CUT:
					continue
				if not _clear(from, ghost, [t]) or not _clear(at, h, [t]):
					continue
				if _over_a_hole(from, ghost, Vector2.INF) or _over_a_hole(at, h, Vector2(h.x, h.z)):
					continue
				var points := float(hole["score"]) * (2.0 if t == game.red_ball else 1.0)
				var chance := pow(cos(cut), 2.0) * exp(-(d1 + d2) / 1.2)
				var arrive := launch_speed(d2, ARRIVE) / (TRANSFER * maxf(cos(cut), 0.25))
				var speed := launch_speed(d1, arrive)
				if speed > game.get_node("Cue").MAX_SPEED:
					continue
				# Points matter, but keeping the break going matters more.
				var score := chance * (40.0 + points)
				if score > best_score:
					best_score = score
					best = {"spot": spot, "direction": dir, "strength": speed / game.get_node("Cue").MAX_SPEED,
						"why": "pot %s into the %d (cut %d deg)" % [t.name, hole["score"], rad_to_deg(cut)],
						"value": score}
	if best.is_empty():
		best = _safety(others, r, y)
	return best


## Where in the D it may stand: the middle, and across and back from it.
func _spots(others: Array, r: float) -> Array:
	var d: Dictionary = game.layout["d_spot"]
	var radius := float(game.layout["d_radius"]) * 0.9
	var out: Array = []
	for offset in [Vector2.ZERO, Vector2(-radius, 0), Vector2(radius, 0),
			Vector2(-radius * 0.6, radius * 0.6), Vector2(radius * 0.6, radius * 0.6),
			Vector2(0, radius)]:
		var p: Vector2 = Vector2(d["x"], d["z"]) + offset
		var free := true
		for b in others:
			if Vector2(b.global_position.x, b.global_position.z).distance_to(p) < r * 2.05:
				free = false
		if free:
			out.append(p)
	return out


## The last ball: off the left or right cushion into the 100 or 200.
func _banks(from: Vector3, y: float) -> Array:
	var r := float(game.layout["ball_radius"])
	var wall := float(game.layout["playing_width"]) * 0.5 - r
	var out: Array = []
	for hole in game.layout["holes"]:
		if not (int(hole["score"]) in game.rules.LAST_BALL_HOLES):
			continue
		for side in [-1.0, 1.0]:
			var h := Vector3(hole["x"], y, hole["z"])
			var mirror := Vector3(side * 2.0 * wall - h.x, y, h.z)
			var dir := (mirror - from).normalized()
			var t: float = (side * wall - from.x) / dir.x
			var bounce: Vector3 = from + dir * t
			var d: float = t + bounce.distance_to(h)
			if not _clear(from, bounce, []) or not _clear(bounce, h, []):
				continue
			var speed := launch_speed(d, ARRIVE + 0.25) * 1.15   # the cushion takes some
			out.append({"spot": Vector2(from.x, from.z), "direction": dir,
				"strength": minf(speed / game.get_node("Cue").MAX_SPEED, 1.0),
				"why": "last ball off the cushion into the %d" % hole["score"],
				"value": float(hole["score"]) / d})
	return out


## Nothing to pot: touch a ball gently, so as not to foul. From each spot
## in the D, sweep almost side to side and take the line whose first contact
## is a ball it may hit (nearest first) — never a skittle. Failing that, a
## ball off one side cushion; failing that, a cushion alone.
func _safety(others: Array, r: float, y: float) -> Dictionary:
	var space := get_viewport().world_3d.direct_space_state
	var best := {}
	var best_gap := INF
	var cushion := {}
	var allowed: Array = []
	for t in others:
		if not game.rules.opening or t == game.red_ball:
			allowed.append(t)
	for spot in _spots(others, r):
		var from := Vector3(spot.x, y, spot.y)
		for i in range(-58, 59):
			var dir := Vector3.FORWARD.rotated(Vector3.UP, deg_to_rad(i * 1.5))
			var hit := _first_contact(space, from, dir, 1.6, r)
			if hit.is_empty() or _over_a_hole(from, from + dir * hit["gap"], Vector2.INF):
				continue
			if hit["body"] in allowed and hit["gap"] < best_gap:
				best_gap = hit["gap"]
				best = _gentle(spot, dir, hit["gap"], 0.45, "safety: just touch %s" % hit["body"].name)
			elif hit["body"] is StaticBody3D and cushion.is_empty() and absi(i) > 20:
				cushion = _gentle(spot, dir, hit["gap"], 0.3, "nothing to hit: off a cushion")
	if not best.is_empty():
		return best
	var bank := _bank_to_ball(allowed, r, y)
	if not bank.is_empty():
		return bank
	if not cushion.is_empty():
		return cushion
	var d: Dictionary = game.layout["d_spot"]
	return {"spot": Vector2(d["x"], d["z"]), "direction": Vector3.LEFT, "strength": 0.15,
		"why": "nothing to hit: a nudge", "value": 0.0}


## Off a side cushion onto a ball: aim at the ball's mirror image.
func _bank_to_ball(allowed: Array, r: float, y: float) -> Dictionary:
	var wall := float(game.layout["playing_width"]) * 0.5 - r
	for spot in _spots(game.balls.filter(func(b): return b != game.cue_ball and game.on_felt(b)), r):
		var from := Vector3(spot.x, y, spot.y)
		for t in allowed:
			var at: Vector3 = t.global_position
			at.y = y
			for side in [-1.0, 1.0]:
				var mirror := Vector3(side * 2.0 * wall - at.x, y, at.z)
				var dir := (mirror - from).normalized()
				if absf(dir.x) < 1e-3:
					continue
				var bounce: Vector3 = from + dir * ((side * wall - from.x) / dir.x)
				var back := (at - bounce).normalized()
				var contact := at - back * 2.0 * r
				if not _clear(from, bounce, []) or not _clear(bounce, contact, [t]):
					continue
				if _over_a_hole(from, bounce, Vector2.INF) or _over_a_hole(bounce, contact, Vector2.INF):
					continue
				var run := from.distance_to(bounce) + bounce.distance_to(contact)
				return _gentle(spot, dir, run * 1.2, 0.45, "safety: %s off the cushion" % t.name)
	return {}


func _first_contact(space: PhysicsDirectSpaceState3D, from: Vector3, dir: Vector3, reach: float, r: float) -> Dictionary:
	var probe := SphereShape3D.new()
	probe.radius = r * 0.98
	var query := PhysicsShapeQueryParameters3D.new()
	query.shape = probe
	query.transform = Transform3D(Basis(), from + Vector3(0, 0.003, 0))
	query.motion = dir * reach
	query.exclude = [game.cue_ball.get_rid()] as Array[RID]
	var hit := space.cast_motion(query)
	if hit.size() == 0 or hit[0] >= 1.0:
		return {}
	query.transform = Transform3D(Basis(), from + Vector3(0, 0.003, 0) + dir * reach * hit[1])
	query.motion = Vector3.ZERO
	var rest := space.get_rest_info(query)
	if rest.is_empty():
		return {}
	return {"gap": reach * hit[0], "body": instance_from_id(rest["collider_id"])}


func _gentle(spot: Vector2, dir: Vector3, gap: float, arrive: float, why: String) -> Dictionary:
	return {"spot": spot, "direction": dir,
		"strength": minf(launch_speed(gap, arrive) / game.get_node("Cue").MAX_SPEED, 1.0),
		"why": why, "value": 0.0}


## Would a ball rolling from a to b pass over a hole (other than `allowed`)?
func _over_a_hole(a: Vector3, b: Vector3, allowed: Vector2) -> bool:
	var reach := float(game.layout["hole_radius"]) + float(game.layout["ball_radius"]) * 0.5
	var a2 := Vector2(a.x, a.z)
	var b2 := Vector2(b.x, b.z)
	for hole in game.layout["holes"]:
		var h := Vector2(hole["x"], hole["z"])
		if allowed != Vector2.INF and h.distance_to(allowed) < 1e-4:
			continue
		var closest := Geometry2D.get_closest_point_to_segment(h, a2, b2)
		if closest.distance_to(h) < reach:
			return true
	return false


## True if a ball can roll from a to b without touching anything but
## `ignore` (and the ball being played, wherever it is now).
func _clear(a: Vector3, b: Vector3, ignore: Array) -> bool:
	var r := float(game.layout["ball_radius"])
	var probe := SphereShape3D.new()
	probe.radius = r * 0.98
	var query := PhysicsShapeQueryParameters3D.new()
	query.shape = probe
	query.transform = Transform3D(Basis(), a + Vector3(0, 0.003, 0))
	query.motion = b - a
	var skip: Array[RID] = [game.cue_ball.get_rid()]
	for n in ignore:
		skip.append(n.get_rid())
	query.exclude = skip
	var hit: PackedFloat32Array = get_viewport().world_3d.direct_space_state.cast_motion(query)
	return hit.size() == 0 or hit[0] >= 1.0


## The speed to strike a ball at so it is still doing `arrive` m/s after
## `distance` metres (see SLIDE_KEEP, DECAY, DRAG).
static func launch_speed(distance: float, arrive: float) -> float:
	var lo := arrive
	var hi := 8.0
	for i in range(40):
		var mid := (lo + hi) * 0.5
		if run_distance(mid * SLIDE_KEEP, arrive) < distance:
			lo = mid
		else:
			hi = mid
	return maxf(hi, arrive / SLIDE_KEEP)


## Distance to slow from v1 to v2 under dv/dt = -DECAY*v - DRAG.
static func run_distance(v1: float, v2: float) -> float:
	if v1 <= v2:
		return 0.0
	return (v1 - v2) / DECAY - DRAG / (DECAY * DECAY) * log((DECAY * v1 + DRAG) / (DECAY * v2 + DRAG))
