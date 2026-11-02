extends RefCounted

## The scoring, kept apart from the physics so the rules read in one place,
## and so tests/test_rules.gd can check every one of them without a table.
##
## English bar billiards, as the pub game plays it (the All England / league
## rule sheets, as summarised on Wikipedia):
##
## * Every shot is played with a ball from the tray, placed in the D.
## * A pot scores the hole's value; the red scores double.
## * A break lasts as long as every shot pots something. A shot that pots
##   nothing ends it: the break is banked and the next player goes.
## * Fouls end the break and lose it: hitting no ball, a ball off the table,
##   knocking down a white skittle, the opening shot missing the red, or
##   the opening shot leaving no ball on the table. Knocking down the black loses your whole score.
## * Pots on a foul shot never count.
## * Once the bar is down, the last ball scores only in the 100 or 200, and
##   only if it came off a side cushion first.
## * The game ends when the bar is down and no ball is left to play, or the
##   moment someone reaches the score limit.
##
## Taking balls off and putting them back — a ball that hit nothing, one
## left in baulk, re-spotting the red — is game.gd's job.

const LAST_BALL_HOLES := [100, 200]

## What the players read in the game (the HUD's Rules panel).
const RULES_TEXT := """[b]The table[/b]
Nine holes: 10, 20, 30 along the back, 50s at the sides, 100 and 200 in the middle. Three skittles: two white beside the 100, one black in front of the 200. Every shot is played from the D at your end.

[b]Scoring[/b]
Pot a ball for the hole's points. The [color=#e05040]red ball scores double[/color].

[b]Your break[/b]
Your turn is a break. Keep potting at least one ball every shot and you keep playing. A shot that pots nothing ends the break: its points are added to your score and the next player goes.

[b]Fouls[/b] (the break ends and its points are lost)
• Your ball hits no other ball. It is taken off the table.
• A ball leaves the table. It goes back to the tray.
• You knock down a [b]white skittle[/b].
• You knock down the [b]black skittle[/b]: you lose your [b]whole score[/b].
• The opening shot does not hit the red.
• The opening shot leaves no ball on the table.

[b]The opening shot[/b]
At the start, and whenever the table is cleared, the red is put on its spot and the first shot must hit it.

[b]Balls[/b]
Seven white and one red. Potted balls roll back to the tray and are played again, the red included: it is not re-spotted. Whether to bring the red back into play is up to you. It doubles your pot, but left on the table it doubles the next player's too. A ball left behind the baulk line goes back to the tray. If every ball is on the table, the one nearest the D is picked up and played next.

[b]Time and the bar[/b]
When the clock runs out the bar drops: potted balls stay under the table and the game winds down. The last ball only scores in the 100 or 200, and only off a side cushion. The game ends when no ball is left to play.

[b]Score limit[/b]
If one is set, the first to reach it wins at once.

[b]Controls[/b]
Drag back from the ball and let go to shoot: the further, the harder. Right-drag or the arrow keys move the ball in the D. To put spin on it, click the ball face in the corner where the cue should strike, or use W A S D: top spin follows through, back spin draws the ball back, side changes the angle off a cushion. Spin is used for one shot, then goes back to the centre. Tab changes ball, E plays the red when it is in the tray (the red button does the same), C changes camera, the wheel zooms, R shows these rules."""

var players := 1
var names: Array[String] = ["Player 1"]
var computer: Array[bool] = [false]
var totals: Array[int] = [0]
var current := 0
var break_score := 0
var opening := true
var over := false
var target := 0                   ## score limit; 0 = none


## `seats` is one entry per player, true for a computer player.
func start(seats: Array, score_limit := 0) -> void:
	players = clampi(seats.size(), 1, 4)
	names.clear()
	computer.clear()
	totals.clear()
	var people := 0
	for i in range(players):
		var cpu := bool(seats[i])
		computer.append(cpu)
		if not cpu:
			people += 1
	var person := 0
	for i in range(players):
		if computer[i]:
			names.append("Computer")
		else:
			person += 1
			names.append("You" if people == 1 and players > 1 else "Player %d" % person)
		totals.append(0)
	current = 0
	break_score = 0
	opening = true
	over = false
	target = maxi(score_limit, 0)


func is_computer() -> bool:
	return computer[current]


## One shot's outcome. `shot` holds:
##   pots          Array of {score: int, red: bool}
##   white_down    a white skittle fell
##   black_down    the black skittle fell
##   hit_any       the played ball touched another ball
##   hit_red       ...and one of them was the red
##   off_table     a ball jumped off the table
##   table_empty   no ball was left on the table afterwards
##   last_ball     the bar is down and this was the only ball left in play
##   side_cushion  the played ball touched a side cushion
## Returns {message: String, break_over: bool, foul: bool, won: bool}.
func resolve(shot: Dictionary) -> Dictionary:
	var pots: Array = shot.get("pots", [])
	var value := 0
	for pot in pots:
		value += int(pot["score"]) * (2 if pot["red"] else 1)
	var was_opening := opening
	opening = false

	if shot.get("black_down", false):
		totals[current] = 0
		return _foul("Black skittle down: whole score lost!")
	if shot.get("white_down", false):
		return _foul("White skittle down: break lost")
	if shot.get("off_table", false):
		return _foul("Foul: ball off the table")
	if shot.get("last_ball", false):
		var good := 0
		if shot.get("side_cushion", false):
			for pot in pots:
				if int(pot["score"]) in LAST_BALL_HOLES:
					good += int(pot["score"]) * (2 if pot["red"] else 1)
		if good > 0:
			break_score += good
			return _scored("Last ball: +%d" % good)
		if value > 0:
			return _end("Last ball only scores in the 100 or 200, off a side cushion")
		return _end("No score")
	if was_opening and not shot.get("hit_red", false):
		return _foul("Foul: the opening shot must hit the red")
	if not shot.get("hit_any", false):
		return _foul("Foul: missed every ball")
	if was_opening and shot.get("table_empty", false):
		return _foul("Foul: the opening shot must leave a ball on the table")
	if value > 0:
		break_score += value
		return _scored("+%d   break %d" % [value, break_score])
	return _end("No score")


## The game is over: bank whatever break was running.
func finish() -> void:
	totals[current] += break_score
	break_score = 0
	over = true


## The leader, or -1 for a tie at the top (or a solo game).
func winner() -> int:
	if players < 2:
		return -1
	var best := 0
	for i in range(1, players):
		if totals[i] > totals[best]:
			best = i
	for i in range(players):
		if i != best and totals[i] == totals[best]:
			return -1
	return best


func next_up() -> String:
	return "%s to play" % names[current] if names[current] != "You" else "Your turn"


## A pot keeps the break going, unless it reaches the score limit.
func _scored(message: String) -> Dictionary:
	if target > 0 and totals[current] + break_score >= target:
		finish()
		return {"message": message + "\n%s reaches %d!" % [names[current], target],
			"break_over": true, "foul": false, "won": true}
	return {"message": message, "break_over": false, "foul": false, "won": false}


func _foul(why: String) -> Dictionary:
	if break_score > 0:
		why += "   (%d lost)" % break_score
	break_score = 0
	var out := _end(why)
	out["foul"] = true
	return out


func _end(why: String) -> Dictionary:
	var banked := break_score
	totals[current] += break_score
	break_score = 0
	var message := why
	if banked > 0:
		message += "   (banked %d)" % banked
	if players > 1:
		current = (current + 1) % players
		message += "\n" + next_up()
	return {"message": message, "break_over": true, "foul": false, "won": false}
