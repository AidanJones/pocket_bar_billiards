extends Node3D

## Desk bar billiards, played against Godot's physics on the same model the
## printer gets.
##
## The whole scene is built in code from `assets/table.glb` and
## `assets/table_layout.json`, so there is no .tscn to keep in step with the
## generator — change the table in Python, re-run `python gltf.py`, and this
## picks it up. The table is lifted so its bed sits at standing height,
## which is what you want when you put a headset on.
##
## Nothing about a pot is faked: a ball falls through the hole because the
## hole is in the mesh, rolls down the ramp, and is played again once it has
## physically arrived in the tray. The scoring is in rules.gd; this file
## runs the shot cycle around it.
##
## Command-line (after `--`): `--smoke` runs the ball-return test,
## `--scenarios` runs the game's rule scenarios (tests/test_game.gd),
## `--autoplay [--shots N] [--minutes M] [--cpu]` plays random shots (or the
## computer's) headless and checks no ball is ever lost, `--start
## [--players N] [--cpu] [--limit S]` skips the menu, `--rules` opens the
## rules, `--screenshot PATH` saves a frame and quits.

const TableLoaderScript := preload("res://scripts/table_loader.gd")
const CueScript := preload("res://scripts/cue.gd")
const XRRigScript := preload("res://scripts/xr_rig.gd")
const RulesScript := preload("res://scripts/rules.gd")
const HudScript := preload("res://scripts/hud.gd")
const AIScript := preload("res://scripts/ai.gd")

@export var bed_height := 0.75    ## metres from the floor to the playing bed
@export var ball_mass := 0.21     ## kg, about a real bar billiards ball
@export var ball_count := 7       ## white balls; the red is extra
@export var skittle_mass := 0.12  ## kg; light enough to topple, heavy enough not to fly

## On the felt a ball needs rolling resistance, which the solver does not
## model, or it runs for a minute. Under the bed it must not have any: the
## return was tuned (and is tested) with undamped balls on a 3 degree ramp.
const FELT_DAMP := 0.45
const FELT_SPIN_DAMP := 0.9
const FELT_DRAG := 0.10           ## m/s^2 of constant rolling resistance
## Cushions are silicone cord: lively. The ramp and tray are PLA: dead.
## Godot adds the two bodies' bounce, so these are the ball's share.
const BOUNCE_FELT := 0.42
const BOUNCE_RETURN := 0.25
const CUSHION_BOUNCE := 0.35

const REST_SPEED := 0.02          ## m/s below which a ball counts as stopped
const REST_HOLD := 0.5            ## ...for this long before a shot is over
const SHOT_LIMIT := 25.0          ## seconds; a shot never takes longer
const LOST_AFTER := 3.0           ## seconds still outside the tray = stuck
const SKITTLE_DOWN := 20.0        ## degrees of lean that counts as knocked over
## The holes are the printed size (1.2 balls), which on screen, with no feel
## for pace, is unforgiving. A ball whose centre comes within this much of a
## hole's edge is drawn gently towards the middle, as if the felt sagged
## into it. This is the game's only help; the model's holes are unchanged.
const POCKET_REACH := 0.45        ## ball radii beyond the hole's edge
const POCKET_PULL := 2.5          ## m/s^2 towards the hole's centre
## The felt has its own collision layer, so a ball over a hole can stop
## touching it (see _build_felt).
const FELT_LAYER := 2

enum State { MENU, AIM, ROLLING, WAITING, OVER }

signal racked                     ## the table is seated and ready to play

var layout: Dictionary = {}
var table: Node3D
var balls: Array[RigidBody3D] = []
var cue_ball: RigidBody3D
var red_ball: RigidBody3D
var skittles: Array[Dictionary] = []      ## {body, home: Transform3D, colour}
var rules: RefCounted = RulesScript.new()
var hud: CanvasLayer
var state := State.MENU
var gate_down := false
var time_left := 0.0
var ai: Node
var last_outcome := {}            ## the most recent shot's rules result, for tests
var last_shot := {}
var shots := 0                    ## shots resolved this game

var _gate_parts: Array = []
var _on_felt := {}                ## ball -> in play on the bed
var _still := {}                  ## ball -> seconds spent at rest
var _shot := {}
var _shot_time := 0.0
var _rest_time := 0.0
var _lift := 0.0
var _cameras: Array[Camera3D] = []
var _camera := 0
var _args := PackedStringArray()
var _auto_shots := -1
var _auto_limit := 0              ## with --cpu: stop after this many shots
var _auto_wait := 0.0
var _racked := false


func _ready() -> void:
	layout = TableLoaderScript.load_layout()
	if layout.is_empty():
		return
	_args = OS.get_cmdline_user_args()
	_lift = bed_height - float(layout["surface_y"])
	_build_world()
	_build_table()
	_rack()
	if "--smoke" in _args:
		# The return test drops its own balls through the holes; skittles
		# standing beside a hole are not what it is testing.
		for s in skittles:
			s["body"].queue_free()
		skittles.clear()
		var smoke := preload("res://scripts/smoke_test.gd").new()
		add_child(smoke)
		smoke.run(self)
		return

	hud = HudScript.new()
	add_child(hud)
	hud.start_requested.connect(start_game)
	hud.restart_requested.connect(new_game)
	hud.red_requested.connect(toggle_red)
	ai = AIScript.new()
	ai.name = "Computer"
	ai.game = self
	add_child(ai)
	if "--scenarios" in _args:
		hud.hide_menu()
		# load, not preload: tests/ is left out of the web build.
		var test: Node = load("res://tests/test_game.gd").new()
		add_child(test)
		test.run(self)
		return
	if "--start" in _args:
		hud.hide_menu()
		start_game(_seats(), float(_arg("--minutes", "5")), int(_arg("--limit", "0")))
	elif "--autoplay" in _args:
		hud.hide_menu()
		_auto_shots = int(_arg("--shots", "12"))
		_auto_limit = _auto_shots
		if "--cpu" in _args:
			start_game([true], float(_arg("--minutes", "10")), 0)
		else:
			start_game([false], float(_arg("--minutes", "10")), 0)
	elif XRRigScript.available():
		var rig := XRRigScript.new()
		rig.game = self
		add_child(rig)
	if "--rules" in _args:
		hud.toggle_rules()
	if "--screenshot" in _args:
		_screenshot.call_deferred(_arg("--screenshot", "user://shot.png"))


## `--players N`, the last of them the computer with `--cpu`.
func _seats() -> Array:
	var seats: Array = []
	for i in range(clampi(int(_arg("--players", "1")), 1, 4)):
		seats.append(false)
	if "--cpu" in _args:
		seats.append(true)
	return seats.slice(0, 4)


func _arg(flag: String, fallback: String) -> String:
	var i := _args.find(flag)
	return _args[i + 1] if i >= 0 and i + 1 < _args.size() else fallback


# ------------------------------------------------------------------ world

func _build_world() -> void:
	var sun := DirectionalLight3D.new()
	sun.rotation_degrees = Vector3(-60, -30, 0)
	sun.light_energy = 0.55
	sun.shadow_enabled = true
	add_child(sun)
	# A pub is lit from above: a lamp over the table keeps the far end lit.
	var lamp := OmniLight3D.new()
	lamp.position = Vector3(0, bed_height + 0.9, -float(layout["playing_length"]) * 0.5)
	lamp.omni_range = 3.0
	lamp.light_energy = 0.7
	lamp.light_color = Color(1.0, 0.92, 0.78)
	add_child(lamp)

	var sky := WorldEnvironment.new()
	var env := Environment.new()
	env.background_mode = Environment.BG_COLOR
	env.background_color = Color(0.12, 0.10, 0.09)
	env.ambient_light_source = Environment.AMBIENT_SOURCE_COLOR
	env.ambient_light_color = Color(0.85, 0.8, 0.72)
	env.ambient_light_energy = 0.2
	env.tonemap_mode = Environment.TONE_MAPPER_FILMIC
	sky.environment = env
	add_child(sky)

	# Somewhere for the table to stand, and for a VR player to stand on.
	var floor_body := StaticBody3D.new()
	var floor_shape := CollisionShape3D.new()
	floor_shape.shape = WorldBoundaryShape3D.new()
	floor_body.add_child(floor_shape)
	var floor_view := MeshInstance3D.new()
	var plane := PlaneMesh.new()
	plane.size = Vector2(12, 12)
	floor_view.mesh = plane
	floor_view.material_override = _matte(Color(0.25, 0.17, 0.12))
	floor_body.add_child(floor_view)
	add_child(floor_body)

	var length := float(layout["playing_length"])
	# Standing at the player's end, looking at the middle of the bed.
	var player := Camera3D.new()
	player.name = "PlayerView"
	player.fov = 55
	var eye := Vector3(0, bed_height + 0.80, length * 0.30)
	player.transform = Transform3D(Basis(), eye).looking_at(
		Vector3(0, bed_height, -length * 0.52), Vector3.UP)
	var above := Camera3D.new()
	above.name = "Overhead"
	above.position = Vector3(0, bed_height + 1.75, -length * 0.5)
	above.rotation_degrees = Vector3(-90, 0, 0)
	above.fov = 50
	for cam in [player, above]:
		add_child(cam)
		_cameras.append(cam)
	player.current = true


func _build_table() -> void:
	table = TableLoaderScript.load_table()
	if table == null:
		return
	# The model's origin is the desk top it clamps to; lift it to bed height.
	table.position.y = _lift
	add_child(table)
	# The gate is modelled dropped into its slot, which is where it sits when
	# the game is over. Start with it lifted out, so balls can come home.
	_gate_parts = TableLoaderScript.gate_parts(table)
	var colliders: int = TableLoaderScript.add_collision(table, ["time_bar_gate", "skittle"])
	print("[table] %d trimesh colliders, %d gate part(s) lifted out" % [
		colliders, _gate_parts.size()])
	set_gate(false)
	_dress_table()
	_build_skittles()
	_build_desk()
	_build_pockets()
	_build_felt.call_deferred()
	_draw_markings()


## The printed table is one filament colour; a playing table has green felt
## on the bed and a livelier cushion than bare plastic.
func _dress_table() -> void:
	var felt := _matte(Color(0.05, 0.26, 0.11))
	var cushion := PhysicsMaterial.new()
	cushion.bounce = CUSHION_BOUNCE
	cushion.friction = 0.2
	for node in TableLoaderScript.parts_named(table, "playfield"):
		node.material_override = felt
	for node in TableLoaderScript.parts_named(table, "rail_"):
		for child in node.get_children():
			if child is StaticBody3D:
				child.physics_material_override = cushion


func _build_skittles() -> void:
	for node in TableLoaderScript.parts_named(table, "skittle"):
		var colour := "black" if "black" in String(node.name) else "white"
		var body: RigidBody3D = TableLoaderScript.make_skittle(node, skittle_mass)
		# Skittles stand on the bed itself: their hulls slowly sink into the
		# felt box, where on the trimesh they stay put (tests/test_game.gd).
		body.collision_mask = 1
		body.freeze = true          # until _park_whites seats it on the bed
		add_child(body)
		skittles.append({"body": body, "home": body.global_transform, "colour": colour})


## The table clamps to the front edge of a desk, and the desk top is what
## the return ramp actually rests on — the ramp's front edge is only a few
## millimetres thick, so without it a ball arriving at speed sinks through
## the tray and drops out of the world.
func _build_desk() -> void:
	var box: AABB = TableLoaderScript.bounds(table)
	if box.size == Vector3.ZERO:
		return
	var top: float = table.position.y          # the model's own z = 0
	var thickness := 0.04
	var body := StaticBody3D.new()
	body.name = "Desk"
	var shape := CollisionShape3D.new()
	var slab := BoxShape3D.new()
	slab.size = Vector3(box.size.x + 0.30, thickness, box.size.z + 0.30)
	shape.shape = slab
	body.add_child(shape)
	var view := MeshInstance3D.new()
	var mesh := BoxMesh.new()
	mesh.size = slab.size
	view.mesh = mesh
	var wood := _matte(Color(0.42, 0.28, 0.17))
	view.material_override = wood
	body.add_child(view)
	# Legs, for looks only.
	var leg_h := top - thickness
	for sx in [-1.0, 1.0]:
		for sz in [-1.0, 1.0]:
			var leg := MeshInstance3D.new()
			var post := BoxMesh.new()
			post.size = Vector3(0.06, leg_h, 0.06)
			leg.mesh = post
			leg.material_override = wood
			leg.position = Vector3(sx * (slab.size.x * 0.5 - 0.06), -leg_h * 0.5 - thickness * 0.5,
				sz * (slab.size.z * 0.5 - 0.06))
			body.add_child(leg)
	body.position = Vector3(box.get_center().x, top - thickness * 0.5,
		box.get_center().z)
	add_child(body)


## A small sensor just under each hole. It sits below the bed so a ball has
## to actually drop to reach it — one rolling past, even over the lip, never
## does. Balls rolling home along the ramp pass under other holes too, which
## is why a pot only counts for a ball that was in play on the felt.
## The felt, as one flat box a felt's thickness deep on top of the bed.
##
## A ball rolling on the bed's trimesh catches the internal edges of its
## triangles — a slab with nine holes in it is long thin triangles — and
## each catch kicks it sideways: a straight shot drifted 4 cm in half a
## metre, enough to miss every pot the aim guide promised. The felt is not
## in the mesh anyway (it is glued on), so model it as what it is: a single
## box has no internal edges. Its holes are made per ball: once a ball's
## centre is over a hole it stops touching the felt (_tune) and drops onto
## the hole's edge in the bed below, which is what tips it in on a real one.
func _build_felt() -> void:
	await get_tree().physics_frame
	var d: Dictionary = layout["d_spot"]
	var bed_top := _floor_below(d["x"], d["z"], bed_height + 0.05)
	var depth := maxf(bed_height - bed_top, 0.001)
	# Carried down into the solid slab below, so a fast ball meets something
	# thicker than a felt; nothing ever reaches the inside of the slab.
	var under := float(layout["surface_y"]) - float(layout["bed_underside_y"])
	var thick := minf(depth + under * 0.6, under)
	var body := StaticBody3D.new()
	body.name = "Felt"
	body.collision_layer = FELT_LAYER
	body.collision_mask = 0
	var shape := CollisionShape3D.new()
	var slab := BoxShape3D.new()
	slab.size = Vector3(float(layout["playing_width"]), thick, float(layout["playing_length"]))
	shape.shape = slab
	body.add_child(shape)
	body.position = Vector3(0, bed_height - thick * 0.5, -float(layout["playing_length"]) * 0.5)
	var cloth := PhysicsMaterial.new()
	cloth.friction = 0.3
	body.physics_material_override = cloth
	add_child(body)
	print("[table] felt %.1f mm on the bed" % (depth * 1000.0))


func _build_pockets() -> void:
	var r := float(layout["ball_radius"])
	for hole in TableLoaderScript.hole_markers(layout):
		var area := Area3D.new()
		area.name = "pocket_%d_%d" % [hole["score"], int(hole["position"].x * 1000)]
		var shape := CollisionShape3D.new()
		var sphere := SphereShape3D.new()
		sphere.radius = r * 0.4
		shape.shape = sphere
		area.add_child(shape)
		area.position = Vector3(hole["position"].x,
			float(layout["bed_underside_y"]) + _lift, hole["position"].z)
		area.body_entered.connect(_on_pocket.bind(int(hole["score"])))
		add_child(area)


## The baulk line and the D, which the felt template draws for the real one.
func _draw_markings() -> void:
	var y := bed_height + 0.0008
	var chalk := _matte(Color(0.9, 0.92, 0.88))
	chalk.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
	var w := 0.0025
	var half := float(layout["playing_width"]) * 0.5
	var line := MeshInstance3D.new()
	var bar := BoxMesh.new()
	bar.size = Vector3(half * 2.0, 0.0005, w)
	line.mesh = bar
	line.material_override = chalk
	line.position = Vector3(0, y, float(layout["baulk_z"]))
	add_child(line)

	var arc := ImmediateMesh.new()
	var d: Dictionary = layout["d_spot"]
	var radius := float(layout["d_radius"])
	arc.surface_begin(Mesh.PRIMITIVE_TRIANGLE_STRIP)
	for i in range(33):
		var a := PI * float(i) / 32.0           # the player's side of the line
		var dir := Vector3(cos(a), 0, sin(a))
		arc.surface_add_vertex(Vector3(d["x"], y, d["z"]) + dir * (radius - w * 0.5))
		arc.surface_add_vertex(Vector3(d["x"], y, d["z"]) + dir * (radius + w * 0.5))
	arc.surface_end()
	var arc_view := MeshInstance3D.new()
	arc_view.mesh = arc
	arc_view.material_override = chalk
	add_child(arc_view)

	# What each hole is worth, painted on the felt on the player's side of
	# it — except the 200, whose near side is the black skittle's, so its
	# number goes beside it.
	for hole in TableLoaderScript.hole_markers(layout):
		var value := Label3D.new()
		value.text = str(hole["score"])
		value.font_size = 64
		value.outline_size = 12
		value.pixel_size = float(layout["ball_radius"]) * 0.02
		value.modulate = Color(0.95, 0.85, 0.45) if hole["score"] >= 100 else Color(0.92, 0.92, 0.86)
		value.double_sided = false
		# Tipped up towards the player: flat on the felt it is unreadable
		# from the player's end, and upright it vanishes from overhead.
		value.rotation_degrees = Vector3(-60, 0, 0)
		var p: Vector3 = hole["position"]
		var gap := float(layout["hole_radius"]) + float(layout["ball_radius"]) * 0.75
		if hole["score"] == 200:
			value.position = Vector3(p.x + gap * 1.5, y + 0.008, p.z)
		else:
			value.position = Vector3(p.x, y + 0.008, p.z + gap)
		add_child(value)

	var red: Dictionary = layout["red_spot"]
	var spot := MeshInstance3D.new()
	var dot := CylinderMesh.new()
	dot.top_radius = 0.006
	dot.bottom_radius = 0.006
	dot.height = 0.0005
	spot.mesh = dot
	spot.material_override = chalk
	spot.position = Vector3(red["x"], y, red["z"])
	add_child(spot)


func _ball(colour: Color, at: Vector3) -> RigidBody3D:
	var body := RigidBody3D.new()
	body.mass = ball_mass
	# A 48 mm ball moving at a few metres a second crosses its own radius in
	# well under a tick, so sweep it rather than trusting discrete steps.
	body.continuous_cd = true
	body.collision_mask = 1 | FELT_LAYER
	body.contact_monitor = true
	body.max_contacts_reported = 4
	var mat := PhysicsMaterial.new()
	# An acetal ball on a PLA ramp is fairly dead; 0.55 was lively enough to
	# ricochet a ball into the corner of the tray and squeeze it out.
	mat.bounce = BOUNCE_RETURN
	mat.friction = 0.3
	body.physics_material_override = mat

	var shape := CollisionShape3D.new()
	var sphere := SphereShape3D.new()
	sphere.radius = float(layout["ball_radius"])
	shape.shape = sphere
	body.add_child(shape)

	var view := MeshInstance3D.new()
	var mesh := SphereMesh.new()
	mesh.radius = float(layout["ball_radius"])
	mesh.height = float(layout["ball_radius"]) * 2.0
	mesh.radial_segments = 24
	mesh.rings = 12
	view.mesh = mesh
	var surface := StandardMaterial3D.new()
	surface.albedo_color = colour
	surface.roughness = 0.25
	view.material_override = surface
	body.add_child(view)

	body.position = at
	add_child(body)
	balls.append(body)
	_on_felt[body] = false
	_still[body] = 0.0
	body.body_entered.connect(_on_contact.bind(body))
	return body


## The red on its spot, and every white in the tray waiting to be played.
func _rack() -> void:
	var r := float(layout["ball_radius"])
	var red_spot: Dictionary = layout["red_spot"]
	red_ball = _ball(Color(0.78, 0.12, 0.10), Vector3(red_spot["x"], bed_height + r, red_spot["z"]))
	red_ball.name = "RedBall"
	_on_felt[red_ball] = true
	for i in range(ball_count):
		var b := _ball(Color(0.96, 0.95, 0.89), Vector3(0, -1, 0))
		b.name = "White%d" % (i + 1)
		b.freeze = true
	_park_whites.call_deferred()
	var cue := CueScript.new()
	cue.name = "Cue"
	add_child(cue)
	cue.setup(self)


## The tray is found by a ray, and a ray only sees the table once the
## physics server has stepped with it in the world. The skittles are seated
## the same way: the felt is a sheet glued on, not part of the mesh, so the
## bed they really stand on is a felt's thickness below `surface_y`.
func _park_whites() -> void:
	await get_tree().physics_frame
	await get_tree().physics_frame          # ...and once more with the felt in
	for s in skittles:
		var home: Transform3D = s["home"]
		home.origin.y = _floor_below(home.origin.x, home.origin.z, bed_height + 0.2, 1)
		s["home"] = home
		_teleport(s["body"], home)
	var slot := 0
	for b in balls:
		if b != red_ball:
			_to_tray(b, slot)
			slot += 1
	_racked = true
	racked.emit()


# ------------------------------------------------------------- shot cycle

## `seats`: one bool per player, true for the computer. `minutes` 0 = no
## clock; `score_limit` 0 = none.
func start_game(seats: Array, minutes: float, score_limit := 0) -> void:
	if not _racked:
		await racked
	rules.start(seats, score_limit)
	time_left = minutes * 60.0 if minutes > 0.0 else INF
	set_gate(false)
	rerack()
	state = State.WAITING
	_next_ball()


## Back to the menu with a fresh table.
func new_game() -> void:
	get_tree().reload_current_scene()


## The red on its spot, every white in the tray, the skittles up.
func rerack() -> void:
	var slot := 0
	for b in balls:
		if b == red_ball:
			_spot_red()
		else:
			_to_tray(b, slot)
			slot += 1
	for s in skittles:
		_teleport(s["body"], s["home"])
	cue_ball = null


func can_aim() -> bool:
	return state == State.AIM and cue_ball != null


## A person may aim: it is their turn, not the computer's.
func human_turn() -> bool:
	return can_aim() and not rules.computer[rules.current]


func computer_turn() -> bool:
	return can_aim() and rules.computer[rules.current] and not rules.over


func on_felt(b: RigidBody3D) -> bool:
	return _on_felt.get(b, false)


## Put a ball in play on the bed at (x, z) — the tests set up shots with it.
func put_on_felt(b: RigidBody3D, at: Vector2) -> void:
	_teleport(b, Vector3(at.x, bed_height + float(layout["ball_radius"]), at.y))
	_on_felt[b] = true
	_still[b] = 0.0


func _spot_red() -> void:
	var spot: Dictionary = layout["red_spot"]
	put_on_felt(red_ball, Vector2(spot["x"], spot["z"]))


## Play the ball in the D at this velocity. The cue calls this.
func strike(velocity: Vector3) -> void:
	if not can_aim():
		return
	cue_ball.freeze = false
	cue_ball.sleeping = false
	cue_ball.angular_velocity = Vector3.ZERO
	cue_ball.linear_velocity = velocity
	var others := 0
	for b in balls:
		if b != cue_ball and (_on_felt[b] or _in_tray(b)):
			others += 1
	_shot = {"played": cue_ball, "pots": [], "hit_any": false, "hit_red": false,
		"side_cushion": false, "off_table": false, "last_ball": gate_down and others == 0}
	_shot_time = 0.0
	_rest_time = 0.0
	state = State.ROLLING


## Slide the ball waiting to be played to the nearest point inside the D.
func place_in_d(at: Vector2) -> void:
	if not can_aim():
		return
	var d: Dictionary = layout["d_spot"]
	var centre := Vector2(d["x"], d["z"])
	var offset := at - centre
	offset.y = maxf(offset.y, 0.0)                  # the player's side of baulk
	offset = offset.limit_length(float(layout["d_radius"]))
	var spot := centre + offset
	var r := float(layout["ball_radius"])
	for b in balls:                                 # never on top of another
		if b != cue_ball and _on_felt[b] and Vector2(b.position.x, b.position.z).distance_to(spot) < r * 2.05:
			return
	_teleport(cue_ball, Vector3(spot.x, bed_height + r, spot.y))
	cue_ball.freeze = true


## Put a different ball from the tray in the D (Tab).
func swap_ball() -> void:
	if not can_aim():
		return
	var choices := _tray_balls()
	if choices.is_empty():
		return
	var leaving := cue_ball
	_to_tray(leaving)
	cue_ball = null
	_play_from_tray(choices[0])


## What the red button offers the player now: "red" (it is in the tray),
## "white" (the red is in hand and a white is waiting), or "" (neither).
## Whether to bring the red into play is the player's call: it doubles a
## pot, but a red left on the table doubles the next player's pot too.
func red_choice() -> String:
	if not can_aim() or not human_turn():
		return ""
	var waiting := _tray_balls()
	if cue_ball == red_ball:
		for b in waiting:
			if b != red_ball:
				return "white"
		return ""
	return "red" if red_ball in waiting else ""


## Swap the ball in the D for the red, or back to a white (E, or the button).
func toggle_red() -> void:
	var choice := red_choice()
	if choice == "":
		return
	var want: RigidBody3D = red_ball
	if choice == "white":
		for b in _tray_balls():
			if b != red_ball:
				want = b
				break
	_to_tray(cue_ball)
	cue_ball = null
	_play_from_tray(want)


func _next_ball() -> void:
	if rules.over:
		_game_over()
		return
	var on_table: Array = []
	for b in balls:
		if _on_felt[b]:
			on_table.append(b)
	# A cleared table starts again like a new game: red on its spot, and the
	# next shot must hit it. Wait for the red to come home if it is on its way.
	if on_table.is_empty() and not (red_ball in _tray_balls()) and _returning():
		state = State.WAITING
		return
	if on_table.is_empty() and red_ball in _tray_balls():
		_spot_red()
		rules.opening = true
		hud.flash("Table clear: the red goes back on its spot.\nThe next shot must hit it.", 3.0)
		on_table.append(red_ball)
	var waiting := _tray_balls()
	if waiting.is_empty():
		if _returning():
			state = State.WAITING          # one is on its way back; wait for it
			return
		if on_table.is_empty():
			_game_over()                   # the bar is down and nothing is left
			return
		# Every ball is on the table, none to play with: the one nearest
		# the D is picked up and played from it.
		var d: Dictionary = layout["d_spot"]
		var spot := Vector3(d["x"], bed_height, d["z"])
		on_table.sort_custom(func(a, b): return a.global_position.distance_to(spot) < b.global_position.distance_to(spot))
		hud.flash("Every ball is in play: the one nearest the D is played", 3.0)
		_on_felt[on_table[0]] = false
		_play_from_tray(on_table[0])
		return
	# Whites first; the red is played from the D like any other once potted.
	waiting.sort_custom(func(a, b): return a != red_ball and b == red_ball)
	_play_from_tray(waiting[0])


func _play_from_tray(ball: RigidBody3D) -> void:
	cue_ball = ball
	_on_felt[ball] = true
	state = State.AIM
	var d: Dictionary = layout["d_spot"]
	place_in_d(Vector2(d["x"], d["z"]))
	if cue_ball.freeze == false:            # the spot was taken: find room
		for i in range(1, 9):
			var a := PI * float(i) / 8.0
			place_in_d(Vector2(d["x"], d["z"]) + Vector2(cos(a), sin(a)) * float(layout["d_radius"]))
			if cue_ball.freeze:
				break


func _physics_process(delta: float) -> void:
	for b in balls:
		_tune(b, delta)
	if state == State.MENU or state == State.OVER:
		return
	if not gate_down and time_left < INF:
		time_left -= delta
		if time_left <= 0.0:
			set_gate(true)
			hud.flash("Time! The bar is down")
	if state == State.WAITING and (not _tray_balls().is_empty() or not _returning()):
		_next_ball()
	elif state == State.ROLLING:
		_watch_shot(delta)
	elif state == State.AIM and _auto_shots >= 0:
		_autoplay(delta)
	var tray := _tray_balls()
	hud.show_board(rules, time_left, tray.size(), gate_down, red_ball in tray)
	hud.show_red(red_choice())


## Felt or return system: each wants different physics (see FELT_*).
func _tune(b: RigidBody3D, delta: float) -> void:
	var r := float(layout["ball_radius"])
	var on_bed := b.global_position.y > bed_height + r * 0.5 and _over_bed(b.global_position)
	var mat: PhysicsMaterial = b.physics_material_override
	mat.bounce = BOUNCE_FELT if on_bed else BOUNCE_RETURN
	b.linear_damp = FELT_DAMP if on_bed else 0.0
	b.angular_damp = FELT_SPIN_DAMP if on_bed else 0.0
	var v := b.linear_velocity
	v.y = 0.0
	b.collision_mask = 1 if _over_hole(b.global_position) else 1 | FELT_LAYER
	if on_bed and not b.freeze:
		_pocket_pull(b)
		if v.length() > FELT_DRAG * delta:
			b.apply_central_force(-v.normalized() * FELT_DRAG * b.mass)
		elif v.length() > 0.0:
			b.linear_velocity = Vector3(0, b.linear_velocity.y, 0)
			b.angular_velocity = Vector3.ZERO
	# Anything that leaves the world, or sticks in the return, goes home.
	if b.freeze and not _on_felt[b]:
		return                      # not racked yet
	if _on_felt[b] and _off_table(b.global_position):
		# Jumped a cushion: a foul, and the ball goes back to the tray.
		if state == State.ROLLING and not _shot.get("off_table", false):
			_shot["off_table"] = true
			hud.flash("Off the table!", 1.2)
		_to_tray(b)
		return
	if b.global_position.y < 0.2:
		_to_tray(b)
		_on_felt[b] = false
	if _on_felt[b] or b.freeze or _in_tray(b):
		_still[b] = 0.0
	elif b.linear_velocity.length() < REST_SPEED:
		_still[b] += delta
		if _still[b] > LOST_AFTER and not gate_down:
			_to_tray(b)
	else:
		_still[b] = 0.0


## Is a ball's centre over a hole in the felt?
func _over_hole(p: Vector3) -> bool:
	var reach := float(layout["hole_radius"])
	for hole in layout["holes"]:
		if Vector2(float(hole["x"]) - p.x, float(hole["z"]) - p.z).length() < reach:
			return true
	return false


func _pocket_pull(b: RigidBody3D) -> void:
	var r := float(layout["ball_radius"])
	var reach := float(layout["hole_radius"]) + r * POCKET_REACH
	for hole in layout["holes"]:
		var to := Vector2(float(hole["x"]) - b.global_position.x, float(hole["z"]) - b.global_position.z)
		if to.length() < reach and to.length() > 1e-4:
			var pull := to.normalized() * POCKET_PULL * b.mass
			b.apply_central_force(Vector3(pull.x, 0, pull.y))
			return


func _watch_shot(delta: float) -> void:
	_shot_time += delta
	var moving := false
	for b in balls:
		if _on_felt[b] and b.linear_velocity.length() > REST_SPEED:
			moving = true
	for s in skittles:
		var body: RigidBody3D = s["body"]
		if body.linear_velocity.length() > REST_SPEED or body.angular_velocity.length() > 0.3:
			moving = true
	_rest_time = 0.0 if moving else _rest_time + delta
	if (_rest_time > REST_HOLD and _shot_time > 0.4) or _shot_time > SHOT_LIMIT:
		_end_shot()


func _end_shot() -> void:
	var r := float(layout["ball_radius"])
	var played: RigidBody3D = _shot["played"]
	_shot["white_down"] = false
	_shot["black_down"] = false
	for s in skittles:
		if _knocked(s):
			_shot[s["colour"] + "_down"] = true
	var notes: Array[String] = []
	for b in balls:
		if not _on_felt[b]:
			continue
		if _off_table(b.global_position):
			_to_tray(b)                             # jumped off
		elif b.global_position.y < bed_height:
			_on_felt[b] = false                     # down a hole; it rolls home
		elif b == played and not _shot["hit_any"] and not _shot["last_ball"]:
			_to_tray(b)                             # touched nothing: taken off
		elif b.global_position.z > float(layout["baulk_z"]) + r:
			_to_tray(b)                             # left in baulk: taken off
			notes.append("ball left in baulk returned")
	_shot["table_empty"] = true
	for b in balls:
		if _on_felt[b]:
			_shot["table_empty"] = false
	var outcome: Dictionary = rules.resolve(_shot)
	last_outcome = outcome
	shots += 1
	last_shot = _shot
	var text: String = outcome["message"]
	if not notes.is_empty():
		text += "\n" + ", ".join(notes)
	outcome["message"] = text
	hud.flash(text)
	print("[shot] %s" % text.replace("\n", " | "))
	for s in skittles:
		_teleport(s["body"], s["home"])
	cue_ball = null
	if outcome["won"]:
		_game_over()
		return
	_next_ball()


func _game_over() -> void:
	if state == State.OVER:
		return
	rules.finish()
	state = State.OVER
	hud.show_over(rules)
	print("[game] over: %s" % [rules.totals])
	if _auto_shots >= 0:
		_auto_report()


func _on_pocket(body: Node, score: int) -> void:
	if not (body is RigidBody3D) or not _on_felt.get(body, false):
		return
	_on_felt[body] = false
	if state != State.ROLLING:
		return
	var red: bool = body == red_ball
	_shot["pots"].append({"score": score, "red": red})
	hud.flash("%d%s" % [score * (2 if red else 1), "  (red doubles)" if red else ""], 1.2)


func _on_contact(other: Node, ball: RigidBody3D) -> void:
	if state != State.ROLLING or ball != _shot.get("played"):
		return
	if other is StaticBody3D and String(other.get_parent().name).begins_with("rail_side"):
		_shot["side_cushion"] = true
	if not (other is RigidBody3D and other in balls):
		return
	_shot["hit_any"] = true
	if other == red_ball:
		_shot["hit_red"] = true


func _knocked(s: Dictionary) -> bool:
	var body: RigidBody3D = s["body"]
	var home: Transform3D = s["home"]
	var lean := rad_to_deg(body.global_transform.basis.y.angle_to(Vector3.UP))
	return lean > SKITTLE_DOWN or body.global_position.y < home.origin.y - 0.02


# ------------------------------------------------------------ the tray

func _over_bed(p: Vector3) -> bool:
	return (absf(p.x) <= float(layout["playing_width"]) * 0.5
		and p.z <= 0.0 and p.z >= -float(layout["playing_length"]))


## Clear of the bed, past the cushions: not in play, not down a hole.
func _off_table(p: Vector3) -> bool:
	var r := float(layout["ball_radius"])
	return (absf(p.x) > float(layout["playing_width"]) * 0.5 + r
		or p.z > r or p.z < -float(layout["playing_length"]) - r)


func _in_tray(b: RigidBody3D) -> bool:
	var tray: Dictionary = layout["tray"]
	var p := b.global_position
	return (p.z >= float(tray["z0"]) and p.z <= float(tray["z1"])
		and p.x >= float(tray["x0"]) and p.x <= float(tray["x1"])
		and p.y < bed_height)


func _tray_balls() -> Array:
	var out: Array = []
	for b in balls:
		if not _on_felt[b] and _in_tray(b) and b.linear_velocity.length() < 0.3:
			out.append(b)
	return out


## A ball that has left the felt but not yet reached the tray.
func _returning() -> bool:
	for b in balls:
		if not _on_felt[b] and not _in_tray(b) and _still[b] < LOST_AFTER:
			if gate_down and b.linear_velocity.length() < REST_SPEED:
				continue            # stopped against the bar: it is not coming
			return true
	return false


## Put a ball in the tray, in the first slot nothing else is sitting in.
func _to_tray(b: RigidBody3D, slot := -1) -> void:
	var tray: Dictionary = layout["tray"]
	var r := float(layout["ball_radius"])
	var z := (float(tray["z0"]) + float(tray["z1"])) * 0.5
	var x0 := float(tray["x0"]) + r * 1.5
	var count := int((float(tray["x1"]) - r * 1.5 - x0) / (r * 2.3)) + 1
	var x := x0
	for i in range(count):
		x = x0 + float(i if slot < 0 else slot) * r * 2.3
		var free := true
		for other in balls:
			if other != b and Vector2(other.global_position.x - x, other.global_position.z - z).length() < r * 2.1:
				free = false
		if free or slot >= 0:
			break
	_on_felt[b] = false
	_still[b] = 0.0
	_teleport(b, Vector3(x, _floor_below(x, z, bed_height + 0.1) + r + 0.002, z))


## The first solid surface below a point, ignoring anything that moves.
func _floor_below(x: float, z: float, from_y: float, mask := 0xFFFFFFFF) -> float:
	var query := PhysicsRayQueryParameters3D.create(
		Vector3(x, from_y, z), Vector3(x, 0.0, z), mask)
	var skip: Array[RID] = []
	for b in balls:
		skip.append(b.get_rid())
	for s in skittles:
		skip.append(s["body"].get_rid())
	query.exclude = skip
	var hit := get_world_3d().direct_space_state.intersect_ray(query)
	return hit["position"].y if not hit.is_empty() else _lift


func _teleport(body: RigidBody3D, where: Variant) -> void:
	body.freeze = false
	body.linear_velocity = Vector3.ZERO
	body.angular_velocity = Vector3.ZERO
	if where is Transform3D:
		body.global_transform = where
	else:
		body.global_transform = Transform3D(Basis(), where)
	body.sleeping = false


# -------------------------------------------------------------- the bar

## Drop the time bar in (or lift it out). With it down, potted balls stay
## under the table and the game winds down — the pub table's end of play.
func set_gate(down: bool) -> void:
	gate_down = down
	for part in _gate_parts:
		part.visible = down
		for child in part.get_children():
			if child is StaticBody3D:
				child.queue_free()
		if down:
			part.create_trimesh_collision()


## Used by the smoke test and by "reset".
func settled() -> bool:
	for b in balls:
		if b.linear_velocity.length() > REST_SPEED:
			return false
	return true


# ------------------------------------------------------------ the player

func _unhandled_input(event: InputEvent) -> void:
	if event is InputEventKey and event.pressed and not event.echo:
		match event.keycode:
			KEY_C:
				_camera = (_camera + 1) % _cameras.size()
				_cameras[_camera].current = true
			KEY_TAB:
				if human_turn():
					swap_ball()
			KEY_E:
				toggle_red()
			KEY_R:
				hud.toggle_rules()
			KEY_N:
				new_game()
	elif event is InputEventMouseButton and event.pressed:
		var cam: Camera3D = _cameras[_camera]
		if event.button_index == MOUSE_BUTTON_WHEEL_UP:
			cam.fov = clampf(cam.fov - 2.5, 20.0, 80.0)
		elif event.button_index == MOUSE_BUTTON_WHEEL_DOWN:
			cam.fov = clampf(cam.fov + 2.5, 20.0, 80.0)


func _matte(colour: Color) -> StandardMaterial3D:
	var mat := StandardMaterial3D.new()
	mat.albedo_color = colour
	mat.roughness = 0.9
	return mat


# ---------------------------------------------------- headless checking

## Random shots up the table, as a soak test: does every shot finish, and is
## every ball always somewhere — felt, return or tray?
func _autoplay(delta: float) -> void:
	_auto_wait += delta
	if _auto_wait < 0.3:
		return
	_auto_wait = 0.0
	if _auto_shots == 0:
		_auto_report()
		return
	if computer_turn():
		if shots >= _auto_limit:
			_auto_report()
		return                      # the computer plays its own shots
	_auto_shots -= 1
	var angle := randf_range(-0.35, 0.35)
	var cue: Node = get_node("Cue")
	cue.play(Vector3(sin(angle), 0, -cos(angle)), randf_range(0.35, 1.0))


func _auto_report() -> void:
	if "--screenshot" in _args:
		_auto_shots = -1            # stop shooting and hold still for the picture
		return
	var lost := 0
	for b in balls:
		if not is_instance_valid(b) or b.global_position.y < 0.2:
			lost += 1
	print("[autoplay] %d shots, score %s, break %d, %d ball(s) lost, %d in tray, bar %s" % [
		shots, rules.totals, rules.break_score, lost, _tray_balls().size(),
		"down" if gate_down else "up"])
	get_tree().quit(1 if lost > 0 else 0)


## Save one frame. `--camera N` picks a view; `--aim` waits for a ball in
## the D and draws a shot being lined up, for the README's pictures.
func _screenshot(path: String) -> void:
	_cameras[int(_arg("--camera", "0"))].current = true
	for i in range(int(_arg("--frames", "90"))):
		await get_tree().process_frame
	if "--aim" in _args:
		while _auto_shots > 0 or not can_aim():
			await get_tree().process_frame
		var cue: Node = get_node("Cue")
		cue.aim_from = cue_ball.global_position
		# Line up on the red (or straight up the table), slightly off full.
		var target := red_ball.global_position if _on_felt[red_ball] else cue_ball.global_position + Vector3.FORWARD
		var line := (target - cue_ball.global_position).normalized().rotated(Vector3.UP, 0.05)
		cue.aim_to = cue_ball.global_position - line * 0.24
		cue.aiming = true
		for i in range(10):
			await get_tree().process_frame
	var image := get_viewport().get_texture().get_image()
	image.save_png(path)
	print("[screenshot] %s" % path)
	get_tree().quit()
