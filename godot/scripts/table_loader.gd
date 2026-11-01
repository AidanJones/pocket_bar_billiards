extends RefCounted
class_name TableLoader

## Loads the generated table and gives it collision.
##
## The .glb is read at run time with GLTFDocument rather than imported as a
## scene, so regenerating it (python gltf.py) needs no editor round trip and
## the headless container does not need an import pass. Every mesh gets a
## trimesh collider: the table is static, so a concave shape is fine and it
## means the holes, the ramp and the return lanes are all really there —
## a potted ball falls through and rolls home because the geometry says so,
## not because anything fakes it.

const GLB_PATH := "res://assets/table.glb"
const LAYOUT_PATH := "res://assets/table_layout.json"


static func load_layout() -> Dictionary:
	var text := FileAccess.get_file_as_string(LAYOUT_PATH)
	if text.is_empty():
		push_error("missing %s — run: python gltf.py" % LAYOUT_PATH)
		return {}
	var parsed: Variant = JSON.parse_string(text)
	return parsed if parsed is Dictionary else {}


static func load_table() -> Node3D:
	var doc := GLTFDocument.new()
	var state := GLTFState.new()
	var err := doc.append_from_file(GLB_PATH, state)
	if err != OK:
		push_error("could not read %s (error %d) — run: python gltf.py" % [GLB_PATH, err])
		return null
	var scene := doc.generate_scene(state)
	if scene == null:
		push_error("glTF loaded but generated no scene")
		return null
	scene.name = "Table"
	return scene


## Walk the loaded table and give every mesh a static trimesh collider.
## Returns how many it made, so the smoke test can assert it is not zero.
static func add_collision(root: Node, skip_prefixes: Array = []) -> int:
	var made := 0
	for node in _walk(root):
		if not (node is MeshInstance3D) or node.mesh == null:
			continue
		var skipped := false
		for prefix in skip_prefixes:
			if node.name.begins_with(prefix):
				skipped = true
				break
		if skipped:
			continue
		node.create_trimesh_collision()
		_make_solid_both_ways(node)
		made += 1
	return made


## A ConcavePolygonShape3D only collides on the front of each triangle, so a
## part whose winding came out mirrored is a one-way wall — a ball inside the
## table passes straight through it. The left-hand parts are built by
## mirroring the right-hand ones, so make every trimesh solid from both
## sides rather than depending on which way a face happens to point.
static func _make_solid_both_ways(node: Node) -> void:
	for child in node.get_children():
		if not (child is StaticBody3D):
			continue
		for shape_node in child.get_children():
			if shape_node is CollisionShape3D and shape_node.shape is ConcavePolygonShape3D:
				shape_node.shape.backface_collision = true


## The time-bar gate, if the model has one. It is modelled sitting in its
## slot — which is where it goes when the game is over — so the game lifts it
## out at the start and drops it back in when time runs out.
static func gate_parts(root: Node) -> Array:
	return parts_named(root, "time_bar_gate")


static func parts_named(root: Node, prefix: String) -> Array:
	var out: Array = []
	for node in _walk(root):
		if node is MeshInstance3D and node.name.begins_with(prefix):
			out.append(node)
	return out


## Lift a skittle out of the static table and make it something a ball can
## knock over. The collision is read off the mesh rather than restated here,
## so it follows the profile in components.mushroom_peg: the mesh is a lathe,
## so its vertices sit on rings, and the rings say where the foot, the stem
## and the cap are. A ball has to be able to roll under the cap rim (design
## rule 7), so the cap is its own convex hull and the stem a slim cylinder —
## one hull round the whole thing would fill in the waist.
static func make_skittle(node: MeshInstance3D, mass: float) -> RigidBody3D:
	var xf := node.global_transform
	var box: AABB = xf * node.mesh.get_aabb()
	var base := Vector3(box.get_center().x, box.position.y, box.get_center().z)
	var height := box.size.y

	# Radius of each ring, keyed by height above the foot.
	var rings := {}
	var points: Array[Vector3] = []
	for v in node.mesh.get_faces():
		var p: Vector3 = xf * v - base
		points.append(p)
		var key := snappedf(p.y, height * 1e-4)
		rings[key] = maxf(rings.get(key, 0.0), Vector2(p.x, p.z).length())
	var cap_r := 0.0
	for r in rings.values():
		cap_r = maxf(cap_r, r)
	var rim_y := height
	for y in rings:
		if rings[y] > cap_r * 0.99:
			rim_y = minf(rim_y, y)
	var stem_r := cap_r
	for y in rings:
		if y < rim_y and rings[y] > 1e-5:
			stem_r = minf(stem_r, rings[y])
	var foot_h := rim_y
	var cone_y := 0.0
	for y in rings:
		if y < rim_y and absf(rings[y] - stem_r) < stem_r * 0.01:
			foot_h = minf(foot_h, y)
			cone_y = maxf(cone_y, y)
	var foot_r := 0.0
	for y in rings:
		if y < foot_h:
			foot_r = maxf(foot_r, rings[y])

	var body := RigidBody3D.new()
	body.name = node.name
	body.mass = mass
	# Printed with light infill and a solid cap, so it is top heavy.
	body.center_of_mass_mode = RigidBody3D.CENTER_OF_MASS_MODE_CUSTOM
	body.center_of_mass = Vector3(0, height * 0.55, 0)
	var mat := PhysicsMaterial.new()
	mat.friction = 0.5
	mat.bounce = 0.1
	body.physics_material_override = mat
	_add_cylinder(body, foot_r, 0.0, foot_h)
	_add_cylinder(body, stem_r, foot_h, cone_y)
	var cap := ConvexPolygonShape3D.new()
	var cap_points := PackedVector3Array()
	for p in points:
		if p.y >= cone_y - height * 1e-3:
			cap_points.append(p)
	cap.points = cap_points
	var cap_node := CollisionShape3D.new()
	cap_node.shape = cap
	body.add_child(cap_node)

	var view := MeshInstance3D.new()
	view.mesh = node.mesh
	view.material_override = node.material_override
	view.transform = Transform3D(xf.basis, xf.origin - base)
	body.add_child(view)
	body.position = base
	node.queue_free()
	return body


static func _add_cylinder(body: Node, radius: float, y0: float, y1: float) -> void:
	if y1 - y0 <= 1e-5 or radius <= 1e-5:
		return
	var shape := CylinderShape3D.new()
	shape.radius = radius
	shape.height = y1 - y0
	var holder := CollisionShape3D.new()
	holder.shape = shape
	holder.position = Vector3(0, (y0 + y1) * 0.5, 0)
	body.add_child(holder)


## The table's overall extent, for sizing the desk it clamps to.
static func bounds(root: Node) -> AABB:
	var box := AABB()
	var first := true
	for node in _walk(root):
		if not (node is MeshInstance3D) or node.mesh == null:
			continue
		var m: AABB = node.global_transform * node.mesh.get_aabb()
		box = m if first else box.merge(m)
		first = false
	return box


## Hole positions come from the layout file rather than the mesh, because a
## hole is an absence — there is nothing in the geometry to look for.
static func hole_markers(layout: Dictionary) -> Array:
	var out: Array = []
	for hole in layout.get("holes", []):
		out.append({
			"score": int(hole["score"]),
			"position": Vector3(hole["x"], layout["surface_y"], hole["z"]),
		})
	return out


static func _walk(node: Node) -> Array:
	var found: Array = [node]
	for child in node.get_children():
		found.append_array(_walk(child))
	return found
