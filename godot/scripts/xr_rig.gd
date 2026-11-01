extends XROrigin3D
class_name XRRig

## Optional OpenXR rig.
##
## The table is exported life size and stood at bed height, so a headset
## needs nothing special: put the player on the floor at the baulk end and
## let them lean over it. Desktop and web fall back to the spectator camera
## without complaining — `available()` is false when no runtime answers.
##
## It is a node rather than a helper object so its lifetime is the scene's:
## the trigger handler below outlives the call that set it up.

const EYE_HEIGHT := 1.65

var game: Node3D


static func available() -> bool:
	var iface := XRServer.find_interface("OpenXR")
	return iface != null and iface.is_initialized()


func _ready() -> void:
	if game == null:
		game = get_parent()
	name = "XRRig"
	# Stand at the player's end, a comfortable reach from the baulk cushion.
	position = Vector3(0, 0, float(game.layout["playing_length"]) * 0.5 + 0.35)

	var head := XRCamera3D.new()
	head.name = "Head"
	head.position = Vector3(0, EYE_HEIGHT, 0)
	add_child(head)

	for hand in ["left_hand", "right_hand"]:
		var controller := XRController3D.new()
		controller.name = hand
		controller.tracker = hand
		add_child(controller)
		if hand == "right_hand":
			controller.button_pressed.connect(_on_button.bind(controller))

	get_viewport().use_xr = true
	Engine.max_fps = 0


## Trigger plays the shot the controller is pointing along.
func _on_button(button: String, controller: XRController3D) -> void:
	if button != "trigger_click":
		return
	var cue: Node = game.get_node_or_null("Cue")
	if cue == null:
		return
	cue.play(-controller.global_transform.basis.z, 0.8)
