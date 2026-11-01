extends Node3D

## Desk bar billiards, played against Godot's physics on the same model the
## printer gets.
##
## The whole scene is built in code from `assets/table.glb` and
## `assets/table_layout.json`, so there is no .tscn to keep in step with the
## generator — change the table in Python, re-run `python gltf.py`, and this
## picks it up. The table is lifted so its bed sits at standing height,
## which is what you want when you put a headset on.

const TableLoaderScript := preload("res://scripts/table_loader.gd")
const CueScript := preload("res://scripts/cue.gd")
const XRRigScript := preload("res://scripts/xr_rig.gd")

@export var bed_height := 0.75    ## metres from the floor to the playing bed
@export var ball_mass := 0.21     ## kg, about a real bar billiards ball
@export var ball_count := 7       ## white balls; the red is extra

var layout: Dictionary = {}
var table: Node3D
var balls: Array[RigidBody3D] = []
var cue_ball: RigidBody3D
var score := 0
var potted: Array = []

@onready var _hud := Label.new()


func _ready() -> void:
	layout = TableLoaderScript.load_layout()
	if layout.is_empty():
		return
	_build_world()
	_build_table()
	_rack()
	_build_ui()
	if "--smoke" in OS.get_cmdline_user_args():
		var smoke := preload("res://scripts/smoke_test.gd").new()
		add_child(smoke)
		smoke.run(self)
	elif XRRigScript.available():
		var rig := XRRigScript.new()
		rig.game = self
		add_child(rig)


func _build_world() -> void:
	var sun := DirectionalLight3D.new()
	sun.rotation_degrees = Vector3(-55, -35, 0)
	sun.light_energy = 1.1
	sun.shadow_enabled = true
	add_child(sun)

	var sky := WorldEnvironment.new()
	var env := Environment.new()
	env.background_mode = Environment.BG_SKY
	env.sky = Sky.new()
	env.sky.sky_material = ProceduralSkyMaterial.new()
	env.ambient_light_source = Environment.AMBIENT_SOURCE_SKY
	env.ambient_light_energy = 0.45
	sky.environment = env
	add_child(sky)

	# Somewhere for the table to stand, and for a VR player to stand on.
	var floor_body := StaticBody3D.new()
	var floor_shape := CollisionShape3D.new()
	var plane := WorldBoundaryShape3D.new()
	floor_shape.shape = plane
	floor_body.add_child(floor_shape)
	add_child(floor_body)

	var cam := Camera3D.new()
	cam.name = "Spectator"
	cam.position = Vector3(0, bed_height + 0.62, float(layout["playing_length"]) * 0.62)
	cam.rotation_degrees = Vector3(-34, 0, 0)
	cam.fov = 55
	add_child(cam)
	cam.current = true


func _build_table() -> void:
	table = TableLoaderScript.load_table()
	if table == null:
		return
	# The model's origin is the desk top it clamps to; lift it to bed height.
	table.position.y = bed_height - float(layout["surface_y"])
	add_child(table)
	var colliders: int = TableLoaderScript.add_collision(table)
	print("[table] %d trimesh colliders" % colliders)
	_build_pockets()


func _build_pockets() -> void:
	for hole in TableLoaderScript.hole_markers(layout):
		var area := Area3D.new()
		area.name = "pocket_%d_%d" % [hole["score"], int(hole["position"].x * 1000)]
		area.set_meta("score", hole["score"])
		var shape := CollisionShape3D.new()
		var sphere := SphereShape3D.new()
		sphere.radius = float(layout["hole_radius"])
		shape.shape = sphere
		area.add_child(shape)
		area.position = hole["position"] + Vector3(0, bed_height - float(layout["surface_y"]), 0)
		area.monitoring = true
		area.body_entered.connect(_on_potted.bind(area))
		add_child(area)


func _ball(colour: Color, at: Vector3) -> RigidBody3D:
	var body := RigidBody3D.new()
	body.mass = ball_mass
	# A 48 mm ball moving at a few metres a second crosses its own radius in
	# well under a tick, so sweep it rather than trusting discrete steps.
	body.continuous_cd = true
	body.contact_monitor = true
	body.max_contacts_reported = 4
	var mat := PhysicsMaterial.new()
	mat.bounce = 0.55
	mat.friction = 0.25
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
	surface.roughness = 0.35
	view.material_override = surface
	body.add_child(view)

	body.position = at
	add_child(body)
	balls.append(body)
	return body


func _rack() -> void:
	var lift := bed_height - float(layout["surface_y"])
	var r := float(layout["ball_radius"])
	var d_spot: Dictionary = layout["d_spot"]
	var red_spot: Dictionary = layout["red_spot"]

	cue_ball = _ball(Color(0.96, 0.95, 0.89),
		Vector3(d_spot["x"], bed_height + r, d_spot["z"]))
	cue_ball.name = "CueBall"
	_ball(Color(0.75, 0.16, 0.12),
		Vector3(red_spot["x"], bed_height + r, red_spot["z"])).name = "RedBall"

	# The rest wait in the tray at the player's end until they are played.
	for i in range(ball_count - 1):
		var x := (float(i) - 2.5) * r * 2.4
		_ball(Color(0.96, 0.95, 0.89),
			Vector3(x, bed_height + r, float(layout["playing_length"]) * 0.08 + r * 3.0))
	var cue := CueScript.new()
	cue.name = "Cue"
	add_child(cue)
	cue.setup(self)
	set_meta("lift", lift)


func _on_potted(body: Node, area: Area3D) -> void:
	if not (body is RigidBody3D) or body in potted:
		return
	potted.append(body)
	var value: int = area.get_meta("score")
	if body.name == "RedBall":
		value *= 2
	score += value
	print("[pot] %s in the %d for %d (total %d)" %
		[body.name, int(area.get_meta("score")), value, score])


func _build_ui() -> void:
	var layer := CanvasLayer.new()
	_hud.position = Vector2(18, 14)
	_hud.add_theme_font_size_override("font_size", 20)
	layer.add_child(_hud)
	add_child(layer)


func _process(_delta: float) -> void:
	if layout.is_empty():
		return
	_hud.text = "score %d    potted %d/%d\ndrag to aim, release to play" % [
		score, potted.size(), balls.size()]


## Used by the smoke test and by "reset".
func settled() -> bool:
	for b in balls:
		if b.linear_velocity.length() > 0.02:
			return false
	return true
