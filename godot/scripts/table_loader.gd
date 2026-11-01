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
	var out: Array = []
	for node in _walk(root):
		if node is MeshInstance3D and node.name.begins_with("time_bar_gate"):
			out.append(node)
	return out


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
