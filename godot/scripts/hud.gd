extends CanvasLayer

## Scoreboard, messages and the start / game-over panels. Built in code like
## the rest of the scene, and kept dumb: game.gd tells it what to show.

signal start_requested(seats: Array, minutes: float, score_limit: int)
signal restart_requested
signal red_requested

const RulesScript := preload("res://scripts/rules.gd")
const INK := Color(0.96, 0.94, 0.86)
const ACCENT := Color(0.95, 0.75, 0.30)
## Who plays: one bool per seat, true for the computer.
const LINEUPS := {"Solo": [false], "vs Computer": [false, true], "2 players": [false, false],
	"3 players": [false, false, false], "4 players": [false, false, false, false]}
const TIMES := [3.0, 5.0, 10.0, 15.0, 0.0]          ## 0 = no clock
const LIMITS := [0, 500, 1000, 2000, 5000]          ## 0 = none

var _board := Label.new()
var _clock := Label.new()
var _flash := Label.new()
var _help := Label.new()
var _red: Button
var _power := ProgressBar.new()
var _board_box: PanelContainer
var _menu: PanelContainer
var _over: PanelContainer
var _over_text := Label.new()
var _rules_panel: PanelContainer
var _menu_behind := false
var _lineup := "vs Computer"
var _minutes := 5.0
var _limit := 0
var _flash_left := 0.0


func _ready() -> void:
	_board_box = _panel(Vector2(16, 14))
	_board_box.visible = false
	var board_box := _board_box
	board_box.add_child(_board)
	_style(_board, 20)
	add_child(board_box)

	_style(_clock, 30)
	_clock.anchor_left = 1.0
	_clock.anchor_right = 1.0
	_clock.offset_left = -170
	_clock.offset_right = -20
	_clock.offset_top = 12
	_clock.horizontal_alignment = HORIZONTAL_ALIGNMENT_RIGHT
	add_child(_clock)

	_style(_flash, 30)
	_flash.set_anchors_preset(Control.PRESET_CENTER_TOP)
	_flash.offset_left = -400
	_flash.offset_right = 400
	_flash.offset_top = 70
	_flash.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	_flash.add_theme_color_override("font_color", ACCENT)
	add_child(_flash)

	_style(_help, 15)
	_help.set_anchors_preset(Control.PRESET_BOTTOM_WIDE)
	_help.offset_top = -34
	_help.offset_left = 16
	_help.text = ("drag back from the ball and release to shoot  ·  right-drag or "
		+ "arrows: move in the D  ·  Tab: change ball  ·  E: the red  ·  C: camera  ·  wheel: zoom  ·  R: rules")
	add_child(_help)

	_power.set_anchors_preset(Control.PRESET_CENTER_BOTTOM)
	_power.offset_left = -160
	_power.offset_right = 160
	_power.offset_top = -74
	_power.offset_bottom = -54
	_power.max_value = 1.0
	_power.show_percentage = false
	_power.mouse_filter = Control.MOUSE_FILTER_IGNORE
	_power.visible = false
	var fill := StyleBoxFlat.new()
	fill.bg_color = ACCENT
	fill.set_corner_radius_all(4)
	_power.add_theme_stylebox_override("fill", fill)
	add_child(_power)

	# Offered only when the red is in the tray (or in hand, to put back).
	_red = _button("", 18, func(): red_requested.emit())
	_red.set_anchors_preset(Control.PRESET_CENTER_BOTTOM)
	_red.offset_left = -110
	_red.offset_right = 110
	_red.offset_top = -124
	_red.offset_bottom = -86
	var red_face := StyleBoxFlat.new()
	red_face.bg_color = Color(0.70, 0.13, 0.11)
	red_face.set_corner_radius_all(6)
	red_face.set_content_margin_all(6)
	for look in ["normal", "hover", "pressed"]:
		_red.add_theme_stylebox_override(look, red_face)
	_red.visible = false
	add_child(_red)

	# Always there once the game is on: the rules, and a way out.
	var corner := HBoxContainer.new()
	corner.anchor_left = 1.0
	corner.anchor_right = 1.0
	corner.offset_left = -260
	corner.offset_right = -20
	corner.offset_top = 56
	corner.alignment = BoxContainer.ALIGNMENT_END
	corner.add_theme_constant_override("separation", 8)
	corner.add_child(_button("Rules (R)", 15, toggle_rules))
	corner.add_child(_button("New game (N)", 15, func(): restart_requested.emit()))
	add_child(corner)

	_menu = _build_menu()
	add_child(_menu)
	_rules_panel = _build_rules()
	_rules_panel.visible = false
	add_child(_rules_panel)
	_over = _build_over()
	_over.visible = false
	add_child(_over)


func _process(delta: float) -> void:
	if _flash_left > 0.0:
		_flash_left -= delta
		_flash.modulate.a = clampf(_flash_left, 0.0, 1.0)


func show_board(rules: RefCounted, seconds_left: float, in_tray: int, bar_down: bool,
		red_in_tray := false) -> void:
	_board_box.visible = true
	var lines: Array[String] = []
	for i in range(rules.players):
		var mark := ""
		if rules.players > 1:
			mark = "> " if i == rules.current else "   "
		var who: String = rules.names[i] if rules.players > 1 else "Score"
		lines.append("%s%s   %d" % [mark, who, rules.totals[i]])
	lines.append("Break   %d" % rules.break_score)
	lines.append("Balls in tray   %d%s" % [in_tray, "  (red too)" if red_in_tray else ""])
	if rules.target > 0:
		lines.append("First to %d" % rules.target)
	_board.text = "\n".join(lines)
	if seconds_left == INF and not bar_down:
		_clock.text = ""
	elif bar_down:
		_clock.text = "BAR DOWN"
		_clock.add_theme_color_override("font_color", Color(0.95, 0.35, 0.3))
	else:
		var s := maxi(0, ceili(seconds_left))
		_clock.text = "%d:%02d" % [s / 60, s % 60]
		_clock.add_theme_color_override("font_color", INK)


## "red", "white" or "" (hidden): see game.red_choice().
func show_red(choice: String) -> void:
	_red.visible = choice != ""
	_red.text = "Play the red (E)" if choice == "red" else "Play a white (E)"


func hide_menu() -> void:
	_menu.visible = false


func toggle_rules() -> void:
	# Opened from the menu, it takes the menu's place until it is closed.
	if _rules_panel.visible:
		_rules_panel.visible = false
		_menu.visible = _menu_behind
	else:
		_menu_behind = _menu.visible
		_menu.visible = false
		_rules_panel.visible = true


func _unhandled_key_input(event: InputEvent) -> void:
	# Enter starts the game from the menu (the browser test uses it too).
	if _menu.visible and event.is_pressed() and event.keycode in [KEY_ENTER, KEY_KP_ENTER, KEY_SPACE]:
		_start()
		get_viewport().set_input_as_handled()
	elif _rules_panel.visible and event.is_pressed() and event.keycode == KEY_ESCAPE:
		toggle_rules()


func flash(text: String, seconds := 2.5) -> void:
	_flash.text = text
	_flash_left = seconds
	_flash.modulate.a = 1.0


## Green for a touch, through amber, to red for a full-blooded shot.
func set_power(power: float) -> void:
	_power.visible = power >= 0.0
	_power.value = maxf(power, 0.0)
	var fill: StyleBoxFlat = _power.get_theme_stylebox("fill")
	if power <= 0.5:
		fill.bg_color = Color(0.35, 0.8, 0.35).lerp(ACCENT, power * 2.0)
	else:
		fill.bg_color = ACCENT.lerp(Color(0.9, 0.25, 0.2), (power - 0.5) * 2.0)


func show_over(rules: RefCounted) -> void:
	var lines: Array[String] = ["Game over", ""]
	if rules.players > 1:
		for i in range(rules.players):
			lines.append("%s   %d" % [rules.names[i], rules.totals[i]])
		var w: int = rules.winner()
		lines.append("")
		if w < 0:
			lines.append("A draw!")
		elif rules.names[w] == "You":
			lines.append("You win!")
		else:
			lines.append("%s wins" % rules.names[w])
	else:
		lines.append("You scored %d" % rules.totals[0])
	_over_text.text = "\n".join(lines)
	_over.visible = true


func _build_menu() -> PanelContainer:
	var panel := _centre_panel()
	var box := VBoxContainer.new()
	box.add_theme_constant_override("separation", 14)
	panel.add_child(box)

	var title := Label.new()
	_style(title, 34)
	title.text = "Bar Billiards"
	title.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	box.add_child(title)
	var blurb := Label.new()
	_style(blurb, 15)
	blurb.text = ("Pot balls down the holes. Keep potting to build a break.\n"
		+ "White skittle down: lose the break. Black: lose everything.\n"
		+ "When the time runs out the bar drops, and potted balls stop coming back.")
	blurb.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	box.add_child(blurb)

	var names: Array = LINEUPS.keys()
	box.add_child(_choice(names, names.find(_lineup), func(i): _lineup = names[i]))
	var labels: Array = []
	for t in TIMES:
		labels.append("%d min" % int(t) if t > 0.0 else "No clock")
	box.add_child(_choice(labels, TIMES.find(_minutes), func(i): _minutes = TIMES[i]))
	labels = []
	for limit in LIMITS:
		labels.append("First to %d" % limit if limit > 0 else "No limit")
	box.add_child(_choice(labels, LIMITS.find(_limit), func(i): _limit = LIMITS[i]))

	var row := HBoxContainer.new()
	row.alignment = BoxContainer.ALIGNMENT_CENTER
	row.add_theme_constant_override("separation", 12)
	var play := _button("Play", 24, _start)
	play.custom_minimum_size = Vector2(200, 0)
	row.add_child(play)
	row.add_child(_button("Rules", 24, toggle_rules))
	box.add_child(row)
	return panel


func _start() -> void:
	_menu.visible = false
	start_requested.emit(LINEUPS[_lineup].duplicate(), _minutes, _limit)


func _build_rules() -> PanelContainer:
	var panel := _centre_panel()
	var box := VBoxContainer.new()
	box.add_theme_constant_override("separation", 10)
	panel.add_child(box)
	var title := Label.new()
	_style(title, 28)
	title.text = "How to play"
	title.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	box.add_child(title)
	var text := RichTextLabel.new()
	text.bbcode_enabled = true
	text.text = RulesScript.RULES_TEXT
	text.custom_minimum_size = Vector2(640, 440)
	text.add_theme_font_size_override("normal_font_size", 16)
	text.add_theme_font_size_override("bold_font_size", 17)
	text.add_theme_color_override("default_color", INK)
	box.add_child(text)
	box.add_child(_button("Close (Esc)", 18, toggle_rules))
	return panel


func _button(label: String, size: int, on_press: Callable) -> Button:
	var b := Button.new()
	b.text = label
	b.focus_mode = Control.FOCUS_NONE
	b.add_theme_font_size_override("font_size", size)
	b.pressed.connect(on_press)
	return b


func _build_over() -> PanelContainer:
	var panel := _centre_panel()
	var box := VBoxContainer.new()
	box.add_theme_constant_override("separation", 14)
	panel.add_child(box)
	_style(_over_text, 26)
	_over_text.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	box.add_child(_over_text)
	box.add_child(_button("Play again", 22, func(): restart_requested.emit()))
	return panel


## A row of toggle buttons, one of which is always down.
func _choice(labels: Array, selected: int, on_pick: Callable) -> HBoxContainer:
	var row := HBoxContainer.new()
	row.alignment = BoxContainer.ALIGNMENT_CENTER
	row.add_theme_constant_override("separation", 8)
	var group := ButtonGroup.new()
	for i in range(labels.size()):
		var b := Button.new()
		b.text = labels[i]
		b.toggle_mode = true
		b.button_group = group
		b.button_pressed = i == selected
		b.custom_minimum_size = Vector2(110, 0)
		b.focus_mode = Control.FOCUS_NONE
		b.add_theme_font_size_override("font_size", 17)
		b.pressed.connect(on_pick.bind(i))
		row.add_child(b)
	return row


func _panel(at: Vector2) -> PanelContainer:
	var p := PanelContainer.new()
	p.position = at
	var bg := StyleBoxFlat.new()
	bg.bg_color = Color(0.05, 0.07, 0.06, 0.72)
	bg.set_corner_radius_all(8)
	bg.set_content_margin_all(12)
	p.add_theme_stylebox_override("panel", bg)
	return p


func _centre_panel() -> PanelContainer:
	var p := _panel(Vector2.ZERO)
	p.set_anchors_preset(Control.PRESET_CENTER)
	p.grow_horizontal = Control.GROW_DIRECTION_BOTH
	p.grow_vertical = Control.GROW_DIRECTION_BOTH
	var bg: StyleBoxFlat = p.get_theme_stylebox("panel")
	bg.bg_color = Color(0.05, 0.07, 0.06, 0.88)
	bg.set_content_margin_all(28)
	return p


func _style(label: Label, size: int) -> void:
	label.add_theme_font_size_override("font_size", size)
	label.add_theme_color_override("font_color", INK)
	label.add_theme_color_override("font_outline_color", Color(0, 0, 0, 0.8))
	label.add_theme_constant_override("outline_size", 4)
