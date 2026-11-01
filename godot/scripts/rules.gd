extends RefCounted

## The scoring, kept apart from the physics so the rules read in one place.
##
## English bar billiards, as far as a pub table plays it:
##
## * Every shot is played with a ball from the tray, placed in the D.
## * A pot scores the hole's value; the red scores double.
## * A break lasts as long as every shot pots something. The first shot
##   that pots nothing ends it, and the break is banked.
## * Knock down a white skittle and you lose the break you are on.
##   Knock down the black and you lose your whole score.
## * The opening shot of the game must hit the red.
## * A ball that hits no other ball is taken off and returned to the tray,
##   and so is any ball left in baulk — that part is game.gd's job.
##
## Pots on a shot that also drops a skittle never count.

var players := 1
var totals: Array[int] = [0]
var current := 0
var break_score := 0
var opening := true
var over := false


func start(player_count: int) -> void:
	players = clampi(player_count, 1, 2)
	totals.clear()
	for i in range(players):
		totals.append(0)
	current = 0
	break_score = 0
	opening = true
	over = false


## One shot's outcome. `shot` holds:
##   pots        Array of {score: int, red: bool}
##   white_down  a white skittle fell
##   black_down  the black skittle fell
##   hit_any     the played ball touched another ball
##   hit_red     ...and one of them was the red
## Returns {message: String, break_over: bool}.
func resolve(shot: Dictionary) -> Dictionary:
	var pots: Array = shot.get("pots", [])
	var value := 0
	for pot in pots:
		value += int(pot["score"]) * (2 if pot["red"] else 1)
	var was_opening := opening
	opening = false

	if shot.get("black_down", false):
		totals[current] = 0
		break_score = 0
		return _end("Black skittle down: score wiped!")
	if shot.get("white_down", false):
		break_score = 0
		return _end("White skittle down: break lost")
	if was_opening and not shot.get("hit_red", false):
		return _end("Opening shot must hit the red: foul")
	if value > 0:
		break_score += value
		return {"message": "+%d   break %d" % [value, break_score], "break_over": false}
	if not shot.get("hit_any", false):
		return _end("Missed: ball off the table")
	return _end("No score")


## The game is over: bank whatever break was running.
func finish() -> void:
	totals[current] += break_score
	break_score = 0
	over = true


func winner() -> int:
	if players < 2 or totals[0] == totals[1]:
		return -1
	return 0 if totals[0] > totals[1] else 1


func _end(why: String) -> Dictionary:
	var banked := break_score
	totals[current] += break_score
	break_score = 0
	var message := why
	if banked > 0:
		message += "   (banked %d)" % banked
	if players > 1:
		current = (current + 1) % players
		message += "\nPlayer %d to play" % (current + 1)
	return {"message": message, "break_over": true}
