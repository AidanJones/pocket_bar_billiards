extends Node

## The rules on the real table: each scenario sets balls out on the felt,
## plays a shot through Godot's physics, and checks what the game made of
## it — the pot was seen, the turn passed, the ball went home, the red was
## re-spotted. tests/test_rules.gd checks the arithmetic; this checks that
## game.gd feeds the rules what actually happened.
##
##     python godot/tools/game_test.py
##
## Exits non-zero if any check fails.

const TICKS := 120                ## physics steps per second (project.godot)

var game: Node3D
var r := 0.0
var failures := 0
var checks := 0


func run(owner_game: Node3D) -> void:
	game = owner_game
	r = float(game.layout["ball_radius"])
	game.ai.skill_noise = 0.0
	await _all()
	print("[game-test] %d checks, %d failure(s)" % [checks, failures])
	get_tree().quit(1 if failures > 0 else 0)


func _all() -> void:
	if "--calibrate" in OS.get_cmdline_user_args():
		await calibrate()
		return
	await test_start_hands_out_a_white()
	await test_skittles_stand()
	await test_runs_straight()
	await test_pot_white()
	await test_pot_red_doubles()
	await test_pocket_edge_pulls_in()
	await test_no_score_passes_turn()
	await test_miss_is_foul()
	await test_cleared_table_respots_red()
	await test_opening_must_hit_red()
	await test_white_skittle()
	await test_black_skittle()
	await test_off_table()
	await test_left_in_baulk()
	await test_every_ball_in_play()
	await test_score_limit()
	await test_four_players()
	await test_rerack()
	await test_choose_the_red()
	await test_time_drops_bar()
	await test_last_ball_wrong_hole()
	await test_pace_model()
	await test_computer_takes_its_turn()
	await test_computer_pots()


# ---------------------------------------------------------------- helpers

func expect(ok: bool, what: String) -> void:
	checks += 1
	print("  %s %s" % ["ok  " if ok else "FAIL", what])
	if not ok:
		failures += 1


func eq(got: Variant, want: Variant, what: String) -> void:
	expect(got == want, "%s (got %s, want %s)" % [what, got, want])


## A new game, past its opening shot unless asked, ready to aim.
func setup(title: String, seats := [false, false], limit := 0, opening := false) -> void:
	print("[game-test] ", title)
	game.set_gate(false)
	game.state = game.State.WAITING
	await game.start_game(seats, 0.0, limit)
	await until(func(): return game.state == game.State.AIM, 5.0)
	game.rules.opening = opening


## Everything but the ball in hand off the felt and into the tray.
func clear_felt() -> void:
	for b in game.balls:
		if b != game.cue_ball and game.on_felt(b):
			game._to_tray(b)
	await frames(2)


## A ball from the tray (not the one in hand), put on the felt at (x, z).
func spare(at: Vector2, red := false) -> RigidBody3D:
	var b: RigidBody3D = game.red_ball
	if not red:
		for c in game.balls:
			if c != game.cue_ball and c != game.red_ball and not game.on_felt(c):
				b = c
				break
	game.put_on_felt(b, at)
	return b


## Play the ball in hand from (x, z) along `dir` at `speed`, and wait for the
## shot to be scored.
func shoot(from: Vector2, dir: Vector2, speed: float) -> Dictionary:
	game.put_on_felt(game.cue_ball, from)
	await frames(3)
	var before: int = game.shots
	var v := Vector3(dir.x, 0, dir.y).normalized() * speed
	game.strike(v)
	await until(func(): return game.shots > before, 30.0)
	return game.last_outcome


## A shot that touches nothing: along the baulk line to the side cushion
## and back, well away from every ball and skittle.
func miss() -> Dictionary:
	return await shoot(Vector2(0, -0.33), Vector2(1, 0), 0.45)


func until(done: Callable, seconds: float) -> bool:
	for i in range(int(seconds * TICKS)):
		if done.call():
			return true
		await get_tree().physics_frame
	return done.call()


func frames(n: int) -> void:
	for i in range(n):
		await get_tree().physics_frame


func message() -> String:
	return String(game.last_outcome.get("message", ""))


func hole(score: int, side := 1.0) -> Vector2:
	for h in game.layout["holes"]:
		if int(h["score"]) == score and (float(h["x"]) * side >= 0.0):
			return Vector2(h["x"], h["z"])
	return Vector2.ZERO


## A white ball short of a hole, and where to play from to send it straight in.
func lined_up(score: int, side := 1.0, red := false) -> Array:
	var h := hole(score, side)
	var target := h + Vector2(0, 0.08)
	return [spare(target, red), target + Vector2(0, 2.0 * r + 0.035)]


# ------------------------------------------------------------------ tests

## Left alone, skittles stay up: a skittle that falls by itself would be a
## foul nobody committed.
func test_start_hands_out_a_white() -> void:
	await setup("the game starts with one white in the D, the red on its spot", [false, false], 0, true)
	await frames(30)
	var on := 0
	for b in game.balls:
		if game.on_felt(b):
			on += 1
	eq(on, 2, "two balls on the table: the red and the one in hand")
	expect(game.cue_ball != null and game.cue_ball != game.red_ball, "a white in hand")
	var d: Dictionary = game.layout["d_spot"]
	var at := Vector2(game.cue_ball.global_position.x, game.cue_ball.global_position.z)
	expect(at.distance_to(Vector2(d["x"], d["z"])) <= float(game.layout["d_radius"]) + 0.001,
		"in the D (at %s)" % at)
	eq(game.cue_ball.freeze, true, "and held there")


func test_skittles_stand() -> void:
	await setup("skittles stand still when nothing touches them", [false])
	for i in range(4):
		await frames(TICKS)
	for sk in game.skittles:
		var body: RigidBody3D = sk["body"]
		var home: Transform3D = sk["home"]
		var lean := rad_to_deg(body.global_transform.basis.y.angle_to(Vector3.UP))
		var moved := body.global_position.distance_to(home.origin)
		expect(lean < 0.5 and moved < 0.001, "the %s skittle has not moved in 4 s (%.2f deg, %.1f mm)" % [
			sk["colour"], lean, moved * 1000.0])


## The aim guide draws a straight line; the ball has to follow it. (On the
## bed's trimesh it did not: see _build_felt in game.gd.)
func test_runs_straight() -> void:
	await setup("a struck ball runs straight", [false])
	await clear_felt()
	var b: RigidBody3D = game.cue_ball
	var dir := Vector3(-0.31, 0, -0.95).normalized()
	game.put_on_felt(b, Vector2(-0.054, -0.3))
	await frames(10)
	var p0 := b.global_position
	game.strike(dir * 1.3)
	var worst := 0.0
	var hop := 0.0
	for i in range(60):
		await get_tree().physics_frame
		var d := b.global_position - p0
		worst = maxf(worst, absf(d.x * dir.z - d.z * dir.x))
		hop = maxf(hop, absf(d.y))
	expect(worst < 0.001, "drifted %.1f mm off line in half a second" % (worst * 1000.0))
	expect(hop < 0.0005, "no hops (%.2f mm)" % (hop * 1000.0))
	await until(func(): return game.state == game.State.AIM, 15.0)


func test_pot_white() -> void:
	await setup("a pot scores and the break goes on")
	await clear_felt()
	var plan := lined_up(30)
	await shoot(plan[1], Vector2(0, -1), 0.9)
	eq(game.last_shot["pots"].size(), 1, "one ball potted")
	eq(game.rules.break_score, 30, "the 30 scores 30")
	eq(game.rules.current, 0, "same player again")
	expect(await until(func(): return game.state == game.State.AIM, 10.0), "ready for the next shot")
	var potted: RigidBody3D = plan[0]
	var home := func(): return potted in game._tray_balls() or potted == game.cue_ball
	expect(await until(home, 10.0), "the potted ball rolled home to the tray")


func test_pot_red_doubles() -> void:
	await setup("the red doubles")
	await clear_felt()
	var plan := lined_up(50, -1.0, true)
	await shoot(plan[1], Vector2(0, -1), 0.9)
	eq(game.rules.break_score, 100, "red in the 50 scores 100")


func test_pocket_edge_pulls_in() -> void:
	await setup("a ball over the hole's edge is drawn in")
	await clear_felt()
	var h := hole(50)
	# Its centre passes outside the hole, but within the pull's reach.
	var off := float(game.layout["hole_radius"]) + r * 0.3
	var b := spare(h + Vector2(off, 0.15))
	await frames(2)
	b.linear_velocity = Vector3(0, 0, -0.45)
	await until(func(): return b.global_position.y < game.bed_height - r, 3.0)
	expect(b.global_position.y < game.bed_height - r, "rolled past the edge and dropped")


func test_no_score_passes_turn() -> void:
	await setup("no score banks the break and passes the turn")
	await clear_felt()
	game.rules.break_score = 60
	spare(Vector2(0.15, -0.45))
	await shoot(Vector2(0.15, -0.31), Vector2(0, -1), 0.4)
	eq(game.last_shot["hit_any"], true, "it hit the ball")
	eq(game.last_shot["pots"].size(), 0, "nothing potted")
	eq(game.rules.totals[0], 60, "break banked")
	eq(game.rules.current, 1, "player 2's turn")


func test_miss_is_foul() -> void:
	await setup("hitting nothing is a foul and the ball comes off")
	await clear_felt()
	spare(Vector2(-0.3, -1.0))
	game.rules.break_score = 40
	await miss()
	eq(game.last_outcome["foul"], true, "foul")
	expect("missed" in message(), "says it missed")
	eq(game.rules.totals[0], 0, "break lost")
	eq(game.rules.current, 1, "turn passes")
	var played: RigidBody3D = game.last_shot["played"]
	expect(not game.on_felt(played) or played == game.cue_ball, "the ball came off the felt")


func test_cleared_table_respots_red() -> void:
	await setup("a cleared table puts the red back on its spot")
	await clear_felt()
	await miss()
	expect(await until(func(): return game.state == game.State.AIM, 10.0), "ready again")
	var spot: Dictionary = game.layout["red_spot"]
	expect(game.on_felt(game.red_ball), "the red is on the table")
	expect(Vector2(game.red_ball.global_position.x, game.red_ball.global_position.z).distance_to(
		Vector2(spot["x"], spot["z"])) < 0.005, "on its spot")
	eq(game.rules.opening, true, "the next shot must hit it")


func test_opening_must_hit_red() -> void:
	await setup("the opening shot must hit the red", [false, false], 0, true)
	var other := spare(Vector2(0.3, -0.6))
	var from := Vector2(0.03, -0.31)
	var at := Vector2(other.global_position.x, other.global_position.z)
	await shoot(from, at - from, 0.6)
	eq(game.last_shot["hit_any"], true, "hit a white")
	eq(game.last_outcome["foul"], true, "foul")
	expect("red" in message(), "says why")
	eq(game.rules.current, 1, "turn passes")


func test_white_skittle() -> void:
	await setup("a white skittle loses the break")
	await clear_felt()
	game.rules.totals[0] = 200
	game.rules.break_score = 100
	var s: Dictionary = game.layout["skittles"][2]
	spare(Vector2(-0.3, -0.5))
	await shoot(Vector2(s["x"], s["z"] + 0.14), Vector2(0, -1), 1.6)
	eq(game.last_shot["white_down"], true, "the skittle fell")
	eq(game.last_outcome["foul"], true, "foul")
	eq(game.rules.totals[0], 200, "break lost, total kept")
	eq(game.rules.current, 1, "turn passes")
	await frames(10)
	var lean := 0.0
	for sk in game.skittles:
		lean = maxf(lean, rad_to_deg(sk["body"].global_transform.basis.y.angle_to(Vector3.UP)))
	expect(lean < 2.0, "skittles stood back up")


func test_black_skittle() -> void:
	await setup("the black skittle loses everything")
	await clear_felt()
	game.rules.totals[0] = 500
	var s: Dictionary = game.layout["skittles"][0]
	spare(Vector2(-0.3, -0.5))
	await shoot(Vector2(s["x"], s["z"] + 0.12), Vector2(0, -1), 1.0)
	eq(game.last_shot["black_down"], true, "the black fell")
	eq(game.rules.totals[0], 0, "whole score gone")


func test_off_table() -> void:
	await setup("a ball off the table is a foul and goes back to the tray")
	await clear_felt()
	game.rules.break_score = 50
	spare(Vector2(-0.3, -1.0))
	# Fired at the side rail, hard and rising, as a mis-hit jumps.
	game.put_on_felt(game.cue_ball, Vector2(0.3, -0.5))
	await frames(3)
	var before: int = game.shots
	game.strike(Vector3(3.0, 0, 0))
	game.cue_ball.linear_velocity.y = 1.6
	await until(func(): return game.shots > before, 30.0)
	eq(game.last_shot.get("off_table", false), true, "seen leaving the table")
	eq(game.last_outcome["foul"], true, "foul")
	eq(game.rules.break_score + game.rules.totals[0], 0, "break lost")
	var played: RigidBody3D = game.last_shot["played"]
	var home := func(): return played in game._tray_balls() or played == game.cue_ball
	expect(await until(home, 5.0), "the ball is back in the tray")


func test_left_in_baulk() -> void:
	await setup("a ball left behind the baulk line goes back to the tray")
	await clear_felt()
	var b := spare(Vector2(0.2, -0.36))
	# Clip it gently back towards the player, over the line.
	await shoot(Vector2(0.2, -0.55), Vector2(0, 1), 0.7)
	expect("baulk" in message(), "says so")
	expect(not game.on_felt(b) or b == game.cue_ball, "the ball is off the felt")


func test_every_ball_in_play() -> void:
	await setup("every ball in play: the nearest the D is played next")
	var xs := [-0.3, -0.2, -0.1, 0.1, 0.2, 0.3]
	for i in range(xs.size()):
		spare(Vector2(xs[i], -0.42 - 0.03 * i))
	await frames(3)
	eq(game._tray_balls().size(), 0, "nothing left in the tray")
	await shoot(Vector2(0, -0.31), Vector2(0, -1), 0.35)
	expect(await until(func(): return game.state == game.State.AIM, 10.0), "a ball is ready")
	var d: Dictionary = game.layout["d_spot"]
	var p: Vector3 = game.cue_ball.global_position
	expect(Vector2(p.x, p.z).distance_to(Vector2(d["x"], d["z"])) <= float(game.layout["d_radius"]) + 0.001,
		"it was picked up and put in the D")


func test_score_limit() -> void:
	await setup("reaching the score limit wins", [false, false], 50)
	await clear_felt()
	var plan := lined_up(50)
	await shoot(plan[1], Vector2(0, -1), 0.9)
	eq(game.last_outcome.get("won", false), true, "won")
	eq(game.state, game.State.OVER, "game over")
	eq(game.rules.winner(), 0, "player 1 wins")


func test_four_players() -> void:
	await setup("four players take turns", [false, false, false, false])
	await clear_felt()
	spare(Vector2(-0.3, -1.0))
	for i in range(3):
		await until(func(): return game.state == game.State.AIM, 10.0)
		await miss()
	eq(game.rules.current, 3, "player 4 is up after three misses")


func test_rerack() -> void:
	await setup("re-racking puts everything back")
	spare(Vector2(0.2, -0.8))
	game.rerack()
	await frames(5)
	eq(game.on_felt(game.red_ball), true, "red on the table")
	eq(game._tray_balls().size(), game.balls.size() - 1, "every white in the tray")


func test_choose_the_red() -> void:
	await setup("the red can be chosen from the tray, and put back")
	eq(game.red_choice(), "", "red on its spot: nothing to offer")
	game._to_tray(game.red_ball)
	await until(func(): return game.red_ball in game._tray_balls(), 5.0)
	eq(game.red_choice(), "red", "red in the tray: offered")
	game.toggle_red()
	eq(game.cue_ball, game.red_ball, "the red is in hand")
	eq(game.can_aim(), true, "and ready to play from the D")
	eq(game.red_choice(), "white", "then a white is offered instead")
	game.toggle_red()
	await until(func(): return game.red_ball in game._tray_balls(), 5.0)
	expect(game.cue_ball != game.red_ball and game.cue_ball != null, "back to a white")
	game.rules.current = 1
	game.rules.computer[1] = true
	eq(game.red_choice(), "", "not offered on the computer's turn")
	game.rules.computer[1] = false


func test_time_drops_bar() -> void:
	print("[game-test] the clock drops the bar")
	game.state = game.State.WAITING
	await game.start_game([false], 0.05, 0)
	expect(await until(func(): return game.gate_down, 6.0), "the bar is down when time is up")


func test_last_ball_wrong_hole() -> void:
	await setup("bar down: the last ball only scores in the 100 or 200")
	game.set_gate(true)
	for b in game.balls:
		if b != game.cue_ball:            # gone: stuck behind the bar
			game._on_felt[b] = false
			b.freeze = true
			b.global_position = Vector3(3, 1, 3)
	var h := hole(50)
	await shoot(h + Vector2(0, 0.2), Vector2(0, -1), 0.8)
	eq(game.last_shot["last_ball"], true, "the game knows it is the last ball")
	eq(game.last_shot["pots"].size(), 1, "it went in the 50")
	eq(game.rules.totals[0], 0, "and scored nothing")
	expect(await until(func(): return game.state == game.State.OVER, 5.0), "nothing left: game over")


## The computer judges pace from a model of the felt; if the felt physics
## in game.gd changes, this says the model needs refitting (--calibrate).
func test_pace_model() -> void:
	for row in await calibrate([0.6, 1.0]):
		expect(absf(row[2] - row[1]) < row[1] * 0.12,
			"pace model at %.1f m/s: %.2f m against %.2f m measured" % [row[0], row[2], row[1]])


func test_computer_takes_its_turn() -> void:
	await setup("the computer plays when it is its turn", [false, true])
	await clear_felt()
	spare(Vector2(0.15, -0.45))
	await shoot(Vector2(0.15, -0.31), Vector2(0, -1), 0.4)
	eq(game.rules.current, 1, "computer's turn")
	var before: int = game.shots
	expect(await until(func(): return game.shots > before, 20.0), "the computer shot")
	expect(not game.ai.last_plan.is_empty(), "with a plan: %s" % game.ai.last_plan.get("why", ""))
	eq(game.last_outcome["foul"], false, "and did not foul")


func test_computer_pots() -> void:
	# Easy pots from the D: a fair computer gets most of them.
	var potted := 0
	var tries := 4
	var spots := [Vector2(0.12, -0.72), Vector2(-0.2, -0.75), Vector2(-0.2, -0.62), Vector2(0.18, -0.8)]
	for i in range(tries):
		await setup("the computer pots an easy ball (%d)" % (i + 1), [true])
		await clear_felt()
		var t := spare(spots[i])
		print("    target ", t.global_position)
		var before: int = game.shots
		await until(func(): return game.shots > before, 20.0)
		print("    plan: ", game.ai.last_plan.get("why", ""), " -> ", message().replace("\n", " | "),
			"; the ball ended at ", t.global_position)
		if game.last_shot["pots"].size() > 0:
			potted += 1
	expect(potted >= 3, "the computer potted %d of %d" % [potted, tries])


## Measure how far a lone ball runs, to fit ai.gd's pace model:
##     godot --headless --fixed-fps 120 -- --scenarios --calibrate
func calibrate(speeds := [0.3, 0.6, 1.0, 1.4, 1.8]) -> Array:
	await setup("calibrate: ball run-out on the felt")
	await clear_felt()
	var out: Array = []
	for speed in speeds:
		var b: RigidBody3D = game.cue_ball
		game.put_on_felt(b, Vector2(-0.36, -0.02))   # a lane clear of holes and skittles
		await frames(3)
		b.linear_velocity = Vector3(0, 0, -speed)
		var start := b.global_position
		var t := 0.0
		var samples: Array[String] = []
		while t < 6.0:
			await get_tree().physics_frame
			t += 1.0 / TICKS
			if int(round(t * TICKS)) % int(TICKS / 4) == 0:
				samples.append("t%.2f v%.3f s%.3f" % [t, b.linear_velocity.length(), start.distance_to(b.global_position)])
			if b.linear_velocity.length() < 0.005 or not game.on_felt(b):
				break
		var model: float = game.ai.run_distance(speed * game.ai.SLIDE_KEEP, 0.0)
		var ran := start.distance_to(b.global_position)
		print("  v0 %.1f  ran %.3f m in %.2f s  (model %.3f)  %s" % [speed, ran, t, model, ", ".join(samples)])
		out.append([speed, ran, model])
	return out
