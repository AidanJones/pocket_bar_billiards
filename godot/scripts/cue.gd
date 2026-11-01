extends Node3D

## Aiming and striking. Drag back from the ball, let go to play — like a
## slingshot, so the cue is drawn back as you pull. The same play() is used
## by the mouse, the VR trigger and the autoplay test.
##
## While aiming, a sphere is swept along the line of the shot to find the
## first thing the ball would touch, and a ghost ball is drawn there. From
## the contact normal the guide then draws what a pool player expects: an
## object ball leaves along the line of centres and the played ball glances
## off along the tangent (the 90 degree rule, true for a ball without spin);
## off a cushion it shows the rebound. Right drag (or the arrow keys) slides
## the ball about inside the D.

const MAX_SPEED := 3.4            ## metres/second at full power
const MAX_DRAG := 0.40            ## metres of drag for full power
const GUIDE_REACH := 1.8          ## metres the aim guide looks ahead
const NUDGE := 0.004              ## metres per arrow-key press
const AFTER := 0.35               ## metres of guide drawn after the contact
const RIBBON := 0.004             ## guide line width, metres

var game: Node3D
var aiming := false
var placing := false
var aim_from := Vector3.ZERO
var aim_to := Vector3.ZERO

var _line: MeshInstance3D
var _mesh := ImmediateMesh.new()
var _stick: MeshInstance3D
var _ghost: MeshInstance3D


func setup(owner_game: Node3D) -> void:
	game = owner_game
	var r: float = float(game.layout["ball_radius"])

	_line = MeshInstance3D.new()
	_line.mesh = _mesh
	var ink := _flat(Color(1, 1, 1, 0.8))
	ink.vertex_color_use_as_albedo = true
	ink.cull_mode = BaseMaterial3D.CULL_DISABLED
	_line.material_override = ink
	add_child(_line)

	# A cue roughly a real one's proportions, tip at the -Y end of the mesh.
	_stick = MeshInstance3D.new()
	var cyl := CylinderMesh.new()
	cyl.height = 1.3
	cyl.top_radius = 0.0145
	cyl.bottom_radius = 0.0065
	cyl.radial_segments = 16
	_stick.mesh = cyl
	var wood := StandardMaterial3D.new()
	wood.albedo_color = Color(0.78, 0.6, 0.38)
	wood.roughness = 0.5
	_stick.material_override = wood
	_stick.visible = false
	add_child(_stick)

	_ghost = MeshInstance3D.new()
	var sphere := SphereMesh.new()
	sphere.radius = r
	sphere.height = r * 2.0
	_ghost.mesh = sphere
	_ghost.material_override = _flat(Color(1, 1, 1, 0.25))
	_ghost.visible = false
	add_child(_ghost)


func _unhandled_input(event: InputEvent) -> void:
	if game == null or not game.can_aim():
		aiming = false
		placing = false
		return
	if event is InputEventMouseButton:
		if event.button_index == MOUSE_BUTTON_LEFT:
			if event.pressed:
				# The pointer is the butt of the cue: the shot goes from it
				# through the ball, harder the further back it is.
				aiming = true
				aim_from = game.cue_ball.global_position
				var hit: Variant = _bed_point(event.position)
				aim_to = aim_from if hit == null else hit
			elif aiming:
				aiming = false
				_strike()
		elif event.button_index == MOUSE_BUTTON_RIGHT:
			placing = event.pressed
			if placing:
				_place_at(event.position)
	elif event is InputEventMouseMotion:
		if aiming:
			var hit: Variant = _bed_point(event.position)
			if hit != null:
				aim_to = hit
		elif placing:
			_place_at(event.position)
	elif event is InputEventKey and event.pressed:
		var nudge := Vector2.ZERO
		match event.keycode:
			KEY_LEFT: nudge.x = -NUDGE
			KEY_RIGHT: nudge.x = NUDGE
			KEY_UP: nudge.y = -NUDGE
			KEY_DOWN: nudge.y = NUDGE
		if nudge != Vector2.ZERO:
			var p: Vector3 = game.cue_ball.global_position
			game.place_in_d(Vector2(p.x, p.z) + nudge)


func _place_at(screen: Vector2) -> void:
	var hit: Variant = _bed_point(screen)
	if hit != null:
		game.place_in_d(Vector2(hit.x, hit.z))


## Where the pointer is on the plane of the bed, or null if it misses.
func _bed_point(screen: Vector2) -> Variant:
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


func _pull() -> Vector3:
	var pull := aim_from - aim_to
	pull.y = 0.0
	return pull


func power() -> float:
	return clampf(_pull().length() / MAX_DRAG, 0.0, 1.0)


func _strike() -> void:
	if power() < 0.03:
		return
	play(_pull().normalized(), power())


## Hit the ball. Shared by the mouse, the VR controller and the tests.
func play(direction: Vector3, strength: float) -> void:
	direction.y = 0.0
	if direction.length_squared() < 1e-8:
		return
	game.strike(direction.normalized() * MAX_SPEED * clampf(strength, 0.0, 1.0))


func _process(_delta: float) -> void:
	_mesh.clear_surfaces()
	var showing: bool = aiming and game != null and game.can_aim() and power() > 0.0
	_stick.visible = showing
	_ghost.visible = showing
	if game != null and game.hud != null:
		game.hud.set_power(power() if showing else -1.0)
	if not showing:
		return
	var r: float = float(game.layout["ball_radius"])
	var ball: Vector3 = game.cue_ball.global_position
	var dir := _pull().normalized()

	# Sweep a ball along the shot; stop the guide where it first touches.
	var lift := Vector3(0, 0.003, 0)
	var query := PhysicsShapeQueryParameters3D.new()
	var probe := SphereShape3D.new()
	probe.radius = r * 0.98
	query.shape = probe
	query.transform = Transform3D(Basis(), ball + lift)
	query.motion = dir * GUIDE_REACH
	query.exclude = [game.cue_ball.get_rid()]
	var space := get_world_3d().direct_space_state
	var hit: PackedFloat32Array = space.cast_motion(query)
	var reach := GUIDE_REACH * (hit[0] if hit.size() > 0 else 1.0)
	var ghost := ball + dir * reach
	_ghost.global_position = ghost
	var bed: float = game.bed_height + 0.0015
	_mesh.surface_begin(Mesh.PRIMITIVE_TRIANGLES)
	_ribbon(ball, ghost, bed, Color(1, 1, 1, 0.8))
	if hit.size() > 0 and hit[0] < 1.0:
		# What it touches, and which way it is pushed: the rest info at the
		# first overlapping position of the sweep.
		query.transform = Transform3D(Basis(), ball + lift + dir * GUIDE_REACH * hit[1])
		query.motion = Vector3.ZERO
		var rest := space.get_rest_info(query)
		if not rest.is_empty():
			var n: Vector3 = rest["normal"]
			n.y = 0.0
			n = n.normalized()
			var other := instance_from_id(rest["collider_id"])
			if other is RigidBody3D and other in game.balls:
				var push := -n                          # line of centres
				var glance := dir - push * dir.dot(push)  # what is left
				var target: Vector3 = (other as Node3D).global_position
				_ribbon(target, target + push * AFTER * dir.dot(push), bed,
					Color(1.0, 0.8, 0.3, 0.9))
				if glance.length() > 0.02:
					_ribbon(ghost, ghost + glance * AFTER, bed, Color(1, 1, 1, 0.45))
			elif not (other is RigidBody3D):                 # a cushion
				_ribbon(ghost, ghost + dir.bounce(n) * AFTER, bed, Color(1, 1, 1, 0.45))
	_mesh.surface_end()

	# The cue lies behind the ball along the line of the shot, drawn back with
	# the pull, raised a little at the butt as a real one is over a cushion.
	var back := r + 0.015 + power() * 0.16
	var tilt := deg_to_rad(6.0)
	var axis := (-dir * cos(tilt) + Vector3.UP * sin(tilt)).normalized()
	var length: float = (_stick.mesh as CylinderMesh).height
	var centre := ball - dir * back + axis * (length * 0.5) + Vector3(0, r * 0.15, 0)
	var y := axis
	var x := y.cross(Vector3.UP).normalized()
	var z := x.cross(y)
	_stick.global_transform = Transform3D(Basis(x, y, z), centre)


## A flat strip lying on the bed, which reads at any resolution where a
## GL line is one pixel wide.
func _ribbon(a: Vector3, b: Vector3, y: float, colour: Color) -> void:
	a.y = y
	b.y = y
	var along := b - a
	if along.length() < 1e-4:
		return
	var side := along.cross(Vector3.UP).normalized() * RIBBON * 0.5
	for v in [a - side, a + side, b + side, a - side, b + side, b - side]:
		_mesh.surface_set_color(colour)
		_mesh.surface_add_vertex(v)


func _flat(colour: Color) -> StandardMaterial3D:
	var mat := StandardMaterial3D.new()
	mat.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
	mat.albedo_color = colour
	mat.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
	return mat
