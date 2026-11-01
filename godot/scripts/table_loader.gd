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
static func add_collision(root: Node) -> int:
	var made := 0
	for node in _walk(root):
		if node is MeshInstance3D and node.mesh != null:
			node.create_trimesh_collision()
			made += 1
	return made


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
