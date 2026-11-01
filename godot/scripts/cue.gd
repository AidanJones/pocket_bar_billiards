extends Node3D

## Aiming and striking. Drag back from the cue ball to set direction and
## power, let go to play the shot — the same gesture works with a mouse and
## with a VR controller's trigger, so the XR rig reuses it.

const MAX_SPEED := 3.2            ## metres/second at full power
const MAX_DRAG := 0.45            ## metres of drag for full power

var game: Node3D
var aiming := false
var aim_from := Vector3.ZERO
var aim_to := Vector3.ZERO

var _line: MeshInstance3D
var _mesh := ImmediateMesh.new()


func setup(owner_game: Node3D) -> void:
	game = owner_game
	_line = MeshInstance3D.new()
	_line.mesh = _mesh
	var mat := StandardMaterial3D.new()
	mat.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
	mat.albedo_color = Color(1, 1, 1, 0.8)
	mat.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
	_line.material_override = mat
	add_child(_line)


func _unhandled_input(event: InputEvent) -> void:
	if game == null or game.cue_ball == null:
		return
	if event is InputEventMouseButton and event.button_index == MOUSE_BUTTON_LEFT:
		if event.pressed:
			aiming = true
			aim_from = game.cue_ball.global_position
			aim_to = aim_from
		elif aiming:
			aiming = false
			_strike()
	elif event is InputEventMouseMotion and aiming:
		var hit := _bed_point(event.position)
		if hit != null:
			aim_to = hit


## Where the pointer is on the plane of the bed, or null if it misses.
func _bed_point(screen: Vector2):
	var cam := get_viewport().get_camera_3d()
	if cam == null:
		return null
	var origin := cam.project_ray_origin(screen)
	var dir := cam.project_ray_normal(screen)
	var bed_y: float = game.bed_height
	if absf(dir.y) < 1e-5:
		return null
	var t := (bed_y - origin.y) / dir.y
	return null if t < 0.0 else origin + dir * t


func _strike() -> void:
	var pull := aim_from - aim_to
	pull.y = 0.0
	var power := clampf(pull.length() / MAX_DRAG, 0.0, 1.0)
	if power < 0.03:
		return
	play(pull.normalized(), power)


## Hit the cue ball. Shared by the mouse, the VR controller and the tests.
func play(direction: Vector3, power: float) -> void:
	direction.y = 0.0
	if direction.length_squared() < 1e-8:
		return
	var impulse := direction.normalized() * MAX_SPEED * clampf(power, 0.0, 1.0) * game.ball_mass
	game.cue_ball.apply_central_impulse(impulse)


func _process(_delta: float) -> void:
	_mesh.clear_surfaces()
	if not aiming:
		return
	_mesh.surface_begin(Mesh.PRIMITIVE_LINES)
	_mesh.surface_add_vertex(aim_from)
	_mesh.surface_add_vertex(aim_from + (aim_from - aim_to))
	_mesh.surface_end()
