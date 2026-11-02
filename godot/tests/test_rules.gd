extends SceneTree

## Unit tests for scripts/rules.gd: every rule, with no table and no physics.
##
##     python godot/tools/game_test.py --rules      # or, in the container:
##     godot --headless --script res://tests/test_rules.gd
##
## Exits non-zero on the first failing file; prints every failure.

const RulesScript := preload("res://scripts/rules.gd")

var failures := 0
var checks := 0


func _init() -> void:
	for name in [
		"test_pot_scores_hole_value", "test_red_doubles", "test_break_continues_while_potting",
		"test_no_score_banks_and_passes", "test_solo_keeps_the_turn",
		"test_miss_is_foul_and_loses_break", "test_white_skittle_loses_break",
		"test_black_skittle_wipes_total", "test_skittle_cancels_pots", "test_off_table_is_foul",
		"test_opening_must_hit_red", "test_opening_must_leave_a_ball",
		"test_opening_only_once", "test_opening_rearmed",
		"test_last_ball_needs_100_or_200", "test_last_ball_needs_side_cushion",
		"test_last_ball_scores", "test_last_ball_needs_no_hit",
		"test_four_players_rotate", "test_up_to_four", "test_names",
		"test_score_limit_wins_mid_break", "test_no_limit",
		"test_finish_banks_break", "test_winner",
	]:
		call(name)
	print("[rules] %d checks, %d failure(s)" % [checks, failures])
	quit(1 if failures > 0 else 0)


func expect(ok: bool, what: String) -> void:
	checks += 1
	if not ok:
		failures += 1
		print("  FAIL: ", what)


func eq(got: Variant, want: Variant, what: String) -> void:
	expect(got == want, "%s: got %s, want %s" % [what, got, want])


## A game already past its opening shot, so tests see only the rule at hand.
func game(seats := [false, false], limit := 0) -> RefCounted:
	var r := RulesScript.new()
	r.start(seats, limit)
	r.opening = false
	return r


func pot(score: int, red := false) -> Dictionary:
	return {"score": score, "red": red}


func shot(pots: Array = [], extra := {}) -> Dictionary:
	var s := {"pots": pots, "hit_any": true, "hit_red": false}
	s.merge(extra, true)
	return s


# ------------------------------------------------------------------ tests

func test_pot_scores_hole_value() -> void:
	var r := game()
	var out: Dictionary = r.resolve(shot([pot(50)]))
	eq(r.break_score, 50, "pot 50: break")
	eq(out["break_over"], false, "pot: break goes on")
	eq(r.current, 0, "pot: same player")


func test_red_doubles() -> void:
	var r := game()
	r.resolve(shot([pot(100, true), pot(10)]))
	eq(r.break_score, 210, "red in the 100 plus a white in the 10")


func test_break_continues_while_potting() -> void:
	var r := game()
	r.resolve(shot([pot(10)]))
	r.resolve(shot([pot(20)]))
	r.resolve(shot([pot(30)]))
	eq(r.break_score, 60, "three pots in a row")
	eq(r.totals[0], 0, "not banked until the break ends")


func test_no_score_banks_and_passes() -> void:
	var r := game()
	r.resolve(shot([pot(200)]))
	var out: Dictionary = r.resolve(shot())
	eq(r.totals[0], 200, "break banked")
	eq(r.break_score, 0, "break reset")
	eq(r.current, 1, "turn passes on no score")
	eq(out["break_over"], true, "no score ends the break")
	eq(out["foul"], false, "no score is not a foul")


func test_solo_keeps_the_turn() -> void:
	var r := game([false])
	r.resolve(shot([pot(50)]))
	r.resolve(shot())
	eq(r.totals[0], 50, "solo banks")
	eq(r.current, 0, "solo: nobody else to play")


func test_miss_is_foul_and_loses_break() -> void:
	var r := game()
	r.totals[0] = 300
	r.resolve(shot([pot(100)]))
	var out: Dictionary = r.resolve(shot([], {"hit_any": false}))
	eq(out["foul"], true, "hitting nothing is a foul")
	eq(r.totals[0], 300, "the break is lost, the total kept")
	eq(r.current, 1, "turn passes after a miss")


func test_white_skittle_loses_break() -> void:
	var r := game()
	r.totals[0] = 300
	r.resolve(shot([pot(100)]))
	var out: Dictionary = r.resolve(shot([], {"white_down": true}))
	eq(out["foul"], true, "white skittle is a foul")
	eq(r.totals[0], 300, "white: break lost, total kept")
	eq(r.current, 1, "white: turn passes")


func test_black_skittle_wipes_total() -> void:
	var r := game()
	r.totals[0] = 900
	r.resolve(shot([pot(100)]))
	r.resolve(shot([], {"black_down": true}))
	eq(r.totals[0], 0, "black: whole score gone")
	eq(r.current, 1, "black: turn passes")


func test_skittle_cancels_pots() -> void:
	var r := game()
	r.resolve(shot([pot(200)], {"white_down": true}))
	eq(r.totals[0], 0, "pots on a skittle foul do not count")
	eq(r.break_score, 0, "nothing carried")
	r = game()
	r.totals[0] = 50
	r.resolve(shot([pot(200)], {"white_down": true, "black_down": true}))
	eq(r.totals[0], 0, "black and white together: black wins")


func test_off_table_is_foul() -> void:
	var r := game()
	r.totals[0] = 70
	r.resolve(shot([pot(30)]))
	var out: Dictionary = r.resolve(shot([pot(100)], {"off_table": true}))
	eq(out["foul"], true, "a ball off the table is a foul")
	eq(r.totals[0], 70, "the break and that shot's pots are lost")
	eq(r.current, 1, "turn passes")
	r = game()
	r.resolve(shot([], {"off_table": true, "last_ball": true, "hit_any": false}))
	eq(r.current, 1, "even the last ball may not leave the table")


func test_opening_must_hit_red() -> void:
	var r := RulesScript.new()
	r.start([false, false])
	var out: Dictionary = r.resolve(shot([pot(10)], {"hit_red": false}))
	eq(out["foul"], true, "opening shot missing the red")
	eq(r.totals[0], 0, "its pot does not count")
	eq(r.current, 1, "turn passes")
	r.start([false, false])
	r.resolve(shot([pot(50, true)], {"hit_red": true}))
	eq(r.break_score, 100, "opening shot that hits the red and pots it")


func test_opening_must_leave_a_ball() -> void:
	var r := RulesScript.new()
	r.start([false, false])
	var out: Dictionary = r.resolve(shot([pot(50, true), pot(100)],
		{"hit_red": true, "table_empty": true}))
	eq(out["foul"], true, "opening shot clearing the table")
	eq(r.totals[0], 0, "no score for it")
	r = game()
	r.resolve(shot([pot(50)], {"table_empty": true}))
	eq(r.break_score, 50, "after the opening, clearing the table is fine")


func test_opening_only_once() -> void:
	var r := RulesScript.new()
	r.start([false])
	r.resolve(shot([pot(10)], {"hit_red": true}))
	eq(r.opening, false, "opening is over after one shot")
	r.resolve(shot([pot(10)]))
	eq(r.break_score, 20, "second shot need not hit the red")


func test_opening_rearmed() -> void:
	# The game sets opening again when it re-spots the red on a cleared table.
	var r := game([false])
	r.opening = true
	var out: Dictionary = r.resolve(shot([pot(10)]))
	eq(out["foul"], true, "re-spotted red must be hit")


func test_last_ball_needs_100_or_200() -> void:
	var r := game()
	var out: Dictionary = r.resolve(shot([pot(50)],
		{"last_ball": true, "side_cushion": true, "hit_any": false}))
	eq(r.totals[0], 0, "last ball in the 50 scores nothing")
	eq(out["foul"], false, "but it is not a foul")


func test_last_ball_needs_side_cushion() -> void:
	var r := game()
	r.resolve(shot([pot(200)], {"last_ball": true, "side_cushion": false, "hit_any": false}))
	eq(r.totals[0] + r.break_score, 0, "last ball straight in the 200 scores nothing")


func test_last_ball_scores() -> void:
	var r := game()
	r.resolve(shot([pot(30)]))
	r.resolve(shot([pot(100)], {"last_ball": true, "side_cushion": true, "hit_any": false}))
	eq(r.break_score, 130, "last ball off a side cushion into the 100")
	r = game()
	r.resolve(shot([pot(200, true)], {"last_ball": true, "side_cushion": true, "hit_any": false}))
	eq(r.break_score, 400, "the red as last ball still doubles")


func test_last_ball_needs_no_hit() -> void:
	var r := game()
	var out: Dictionary = r.resolve(shot([], {"last_ball": true, "hit_any": false}))
	eq(out["foul"], false, "the last ball has nothing to hit")


func test_four_players_rotate() -> void:
	var r := game([false, false, false, false])
	var order: Array[int] = []
	for i in range(5):
		order.append(r.current)
		r.resolve(shot())
	eq(order, [0, 1, 2, 3, 0] as Array[int], "four players take turns")


func test_up_to_four() -> void:
	var r := game([false, false, false, false, false, false])
	eq(r.players, 4, "capped at four players")
	eq(r.totals.size(), 4, "four totals")


func test_names() -> void:
	var r := game([false, true])
	eq(r.names, ["You", "Computer"] as Array[String], "you against the computer")
	eq(r.is_computer(), false, "the person goes first")
	r.resolve(shot())
	eq(r.is_computer(), true, "then the computer")
	eq(game([false, false, true]).names, ["Player 1", "Player 2", "Computer"] as Array[String],
		"two people and the computer")


func test_score_limit_wins_mid_break() -> void:
	var r := game([false, false], 500)
	r.totals[0] = 400
	var out: Dictionary = r.resolve(shot([pot(50)]))
	eq(out["won"], false, "450 is short of 500")
	out = r.resolve(shot([pot(50)]))
	eq(out["won"], true, "500 reaches the limit")
	eq(r.over, true, "the game is over")
	eq(r.totals[0], 500, "the break is banked")
	eq(r.winner(), 0, "and the player who reached it wins")


func test_no_limit() -> void:
	var r := game([false], 0)
	r.resolve(shot([pot(200, true)]))
	r.resolve(shot([pot(200, true)]))
	eq(r.over, false, "no limit: 800 is not a win")


func test_finish_banks_break() -> void:
	var r := game()
	r.resolve(shot([pot(30)]))
	r.finish()
	eq(r.totals[0], 30, "finish banks the running break")
	eq(r.over, true, "and ends the game")


func test_winner() -> void:
	var r := game([false, false, false])
	r.totals = [10, 40, 20] as Array[int]
	eq(r.winner(), 1, "highest wins")
	r.totals = [40, 40, 20] as Array[int]
	eq(r.winner(), -1, "tie at the top")
	r.totals = [40, 10, 10] as Array[int]
	eq(r.winner(), 0, "tie below the top does not matter")
	eq(game([false]).winner(), -1, "solo has no winner")
