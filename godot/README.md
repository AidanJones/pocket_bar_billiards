# The game

A Godot 4.3 version of the same table, playable in a browser and (with a
headset plugged in) in VR — and, more usefully while the design is still
moving, a physics rig for testing the ball return before anything is
printed.

![lining up a shot: the ghost ball, the red's line, the glance-off line](screenshots/aim.png)

## One model, two outputs

```
          table.py  (the model: parameters -> geometry)
            /                                  \
   barbilliards.py                           gltf.py
     stl/*.stl                        godot/assets/table.glb
   the printed table                  godot/assets/table_layout.json
```

There is no second model and no Blender step. `table.py` is the source of
truth; `barbilliards.py` slices it into printable pieces, and `gltf.py`
writes the *assembled* thing as one `.glb` plus the JSON the game needs for
hole positions, spots and lane extents. Change the table in Python and both
outputs follow.

Blender is not in the loop because nothing needs it: the geometry is
generated, the parts are flat-coloured, and at ~8,700 triangles the whole
table is far below anything a browser or a headset would struggle with. If
you later want baked lighting or textured materials, that is the point at
which a Blender pass earns its place — the `.glb` imports straight into it.

**The game runs life size.** The exporter shows a real league table
(47.6 mm ball, 800 × 1420 mm bed) rather than the desk-sized print, because
Godot's solver is happiest around human scale and because in VR you want to
stand at a real table.

It is the printed table **blown up uniformly** — not the generator re-run
with a bigger ball. That distinction matters: wall thickness, clearances and
splice plates are set by the nozzle, not by the ball, so re-generating at
47.6 mm leaves a 48 mm ball rattling around inside 4 mm walls, and it goes
straight through them. Scaling the whole thing by 3.75 keeps the
proportions a real table has. `--as-printed` leaves it at 1:1 with the
STLs.

Units on the way out: millimetres and Z-up become **metres and Y-up**, the
player stands at **+Z**, and the table is lifted so its bed sits 0.75 m off
the floor.

## Running it

Everything goes through Docker, so there is no native Godot install to
manage. Start Docker Desktop first.

```bash
python gltf.py                                  # regenerate assets/
python godot/tools/physics_test.py              # drop a ball through every hole
python godot/tools/physics_test.py --return sorted
python godot/tools/game_test.py                 # every rule, unit and on the real table
python godot/tools/web_export.py --serve        # browser build on :8070
python godot/e2e/web_smoke.py                   # load that build in Chromium, play a shot
python godot/tools/screenshots.py               # refresh screenshots/
cd godot && docker compose --profile vnc up godot-vnc   # watch/play on :6080
```

The compose volumes carry `:z`, so this works on SELinux hosts (Fedora,
RHEL) as well as Docker Desktop, and the containers run as your user so
`.godot/` and `web_export/` are not left owned by root.

Headless checks on the game itself, after `--` on the Godot command line
(`docker compose run --rm godot --headless --quit-after 400000 -- ...`):

| Flag | Does |
|---|---|
| `--smoke` | the ball-return test below |
| `--scenarios [--calibrate]` | the rule scenarios in `tests/test_game.gd` (`tools/game_test.py` runs them); `--calibrate` prints how far a struck ball runs, for refitting the computer's pace model |
| `--autoplay --shots N [--minutes M] [--cpu]` | plays N random shots (or, with `--cpu`, lets the computer play N) and fails if a ball is ever lost; a short `--minutes` runs it to the bar dropping and game over |
| `--start [--players N] [--cpu] [--limit S]` | skip the menu: N people (1–4), plus the computer with `--cpu`, first to S |
| `--rules` | open the rules panel |
| `--screenshot PATH [--aim] [--camera 1]` | save a frame (needs a display: see `tools/screenshots.py`) |

Add `--fixed-fps 120` before the `--` to step the physics as fast as the
machine allows rather than in real time; the test tools do.

### Playing

The rules are in `scripts/rules.gd`, kept apart from the physics, and the
same file holds the text of the in-game **Rules** panel (R), so the two
cannot drift apart. Each shot is played with a ball from the tray, placed
in the D, and the shot is over when everything on the felt has stopped —
balls already rolling home under the bed are not waited for, so the next
shot is ready while they are still coming back.

The menu has solo, you against the computer, and two to four players; a
3–15 minute clock or none; and a score limit (first to 500 … 5000) or
none. **N** starts a new game at any time.

| | | |
|---|---|---|
| ![start screen](screenshots/menu.png) | ![the rules panel](screenshots/rules.png) | ![from above](screenshots/overhead.png) |

**Rules implemented.** Breaks (keep potting to keep playing; a shot that
pots nothing banks the break and passes the turn); the red doubling;
fouls that lose the break — hitting no ball, a ball off the table, a white
skittle, the opening shot missing the red or leaving no ball on the table;
the black skittle losing the whole score; the red re-spotted, and the
opening rule re-armed, whenever the table is cleared; with every ball on
the table and none in the tray, the one nearest the D picked up and played;
with the bar down, the last ball scoring only in the 100 or 200 off a side
cushion; the game ending when the bar is down and nothing is left to play,
or the moment someone reaches the score limit. Not done: the real break
shot's three attempts and the "split shot".

**The computer** (`scripts/ai.gd`) looks for the pot a pool player would:
for each ball it may hit and each hole, the ghost-ball spot that sends it
there, both paths swept through the physics space for skittles, balls and
holes in the way, scored on value against cut and distance, from several
spots in the D. Its pace comes from a model of how far a ball runs on this
felt, fitted to measurements (`--calibrate`) and checked by the tests. It
then misses a little (`skill_noise`). With no pot on it plays a safe touch
on a ball, by a cushion if it must, and never a line into a skittle.
Playing itself for 60 shots it potted 35 times, scored 900, never missed a
ball, and fouled four times — all its own ball running on into a white
skittle after contact, which it does not yet look for.

**The holes help a little.** A ball whose centre comes within half a ball's
radius of a hole's edge is drawn gently towards it, as if the felt sagged
there. On screen, with no feel for pace, the printed hole size (1.2 balls)
is unforgiving. It is the game's only help; the model's holes are unchanged.

The aim guide sweeps a ball-sized sphere along the shot (`cast_motion`) and
reads the contact normal where it first touches (`get_rest_info`). Off a
ball, the object ball is drawn leaving along the line of centres and yours
along the tangent — the 90° rule, exact for a ball with no spin, which is
the only kind this game plays. Off a cushion it draws the rebound.

Before writing it we looked for an open-source Godot pool game to borrow
from. The closest was [Shadowfetch Pool](https://github.com/ShadowfetchStudio/shadowfetch-pool)
(MIT, Godot 4.7, Jolt): its ball is the same damped `RigidBody3D` this one
uses, and its guide is a fixed-length straight line, so there was nothing
to lift. [BreakoutShot](https://github.com/danielKlmr/BreakoutShot) (MIT) is
2D. Its ideas worth taking later are side spin (a torque impulse at the
strike) and aiming with the mouse while setting power separately.

### The tests

```bash
python godot/tools/game_test.py           # both: ~5 minutes
python godot/tools/game_test.py --rules   # just the scoring: seconds
```

`tests/test_rules.gd` checks every rule's arithmetic with no table: 25
cases, 63 checks. `tests/test_game.gd` then plays each rule out on the real
table through the physics — a pot seen and scored, the red doubled, a miss
returned, the red re-spotted on a cleared table, both skittles, a ball off
the table, a ball left in baulk, every ball in play, the score limit, four
players rotating, the clock dropping the bar, the last-ball rule, the
computer taking its turn and potting easy balls — plus that skittles stand
still when nothing touches them, that a struck ball runs straight, and that
the computer's pace model still matches the felt: 63 checks.

### The physics test

This is the part that earns its keep. `check.py` can prove a return lane is
wide enough and that no lane wall sits under a hole; it cannot prove that a
ball dropped through the 100 ends up in the 100's lane rather than bouncing
into the 200's. So `scripts/smoke_test.gd` drops a ball through each of the
nine holes in turn, lets it run, and reports where it came to rest:

```
[smoke] hole  returned  lane     resting place (m)
[smoke] 30    yes       30       (-0.287, +0.713, +0.612)
...
```

It exits non-zero if a ball never reaches the tray, or — with
`--return sorted` — lands in the wrong lane. The table's holes, ramp and
lane walls are all real collision geometry taken from the model, so the ball
falls through and rolls home because the shape says so, not because anything
fakes it.

### What it has found so far

**Shared return: 9 of 9.** Every hole returns its ball to the tray.

**Sorted return: 9 of 9**, each into the lane that matches its score — but
only after the test failed it at 5 of 9 and the chutes were redesigned
around what it said. Three things were wrong, and none of them was visible
in the geometry:

* The cross-slope was **too shallow** — a fixed 4.4 mm of rise spread over
  up to 59 mm, so 4–8°. A ball dropped onto that simply sits on it. It now
  takes all the rise the headroom under the bed allows and spans no further
  than the ball has to move: 12–18°.
* It **finished against the lane wall**, 0.5 mm clear of it, so a ball that
  did roll down wedged between the two. It now stops at the near wall of
  the lane it is delivering to, leaving the whole lane to land in. A lane
  is only about a ball and a half wide, so whatever the chute covers is
  taken away from the ball.
* The back-row chutes **left a gap behind them**, and a ball bouncing on
  landing could end up behind a 7 mm step it could not climb. Those now
  reach the back wall.

`check.py` gained a rule for each: at least 10° of cross-slope, a
ball-and-a-half of lane left beyond the low edge, and less than half a ball
of gap underneath.

**A caveat on scale.** Those numbers are at life size. `--as-printed` at
`--size mini` hands Godot a 9.5 mm ball, which is below what its solver
handles reliably — balls stick on slopes they should roll down, including
at holes with no chute at all. The test prints a warning when it sees a
ball under 20 mm; treat the result as inconclusive rather than as a fault
in the table.

It also caught a real bug in the generator. `place()` mirrors a profile
about its origin, and the left-hand walls and rails were being mirrored but
left at the right-hand origin — so both side walls sat on the +X side and
the left of the table was open. The printed parts were unaffected (each STL
is centred on the plate, and the shape was right), which is exactly why
nothing noticed: it passed every geometry rule, fit the bed and printed. It
showed up here as balls leaving the table sideways. `check.py` now has a
rule that every `_left` part is the mirror image, in place, of its `_right`
twin.

## Layout

| Path | What |
|---|---|
| `project.godot` | Godot 4.3 project. Physics at 120 Hz; a 48 mm ball is small for the default solver. |
| `main.tscn` | One node running `scripts/game.gd`. The scene is built in code, so there is no level file to keep in step with the generator. |
| `scripts/table_loader.gd` | Reads the `.glb` at run time with `GLTFDocument` (no editor import step) and gives every mesh a trimesh collider. |
| `scripts/game.gd` | Builds the world, racks the balls, runs the shot cycle and the clock. Also builds the desk and lifts the gate out — see below. |
| `scripts/rules.gd` | The scoring, every rule, and the text of the in-game rules. No physics in it. |
| `scripts/ai.gd` | The computer player. |
| `scripts/hud.gd` | Scoreboard, messages, power bar, menu, rules and game-over panels. |
| `scripts/cue.gd` | Drag to aim, release to play, the aim guide. Shared by mouse, VR trigger, the computer and autoplay. |
| `scripts/xr_rig.gd` | OpenXR rig; falls back to the spectator camera when no runtime answers. |
| `scripts/smoke_test.gd` | The headless ball-return test. |
| `tests/` | The rules' unit tests and the table scenarios. Left out of the web build. |
| `assets/` | Generated by `gltf.py`. Never hand-edit. |
| `Dockerfile`, `docker-compose.yml` | Godot 4.3 headless / VNC / web images. |
| `tools/` | Thin Python wrappers around the compose commands: return test, game tests, web export, screenshots. |
| `e2e/web_smoke.py` | Loads the web export in headless Chromium (Playwright's image) and plays a shot. |
| `screenshots/` | Generated by `tools/screenshots.py`; `.gdignore`d so they stay out of the build. |

The Docker setup is adapted from the Skiagraph project's Godot image, which
had already worked out the headless flags, the writable `HOME` and the
separate web-templates layer.

## What making it playable found

* **Balls did not run straight.** A ball rolling on the bed's trimesh
  catches the internal edges of its triangles — a slab with nine holes cut
  in it is all long thin triangles — and each catch hops it and kicks it
  sideways: 4 cm off line in half a metre, so pots the aim guide promised
  missed. The felt is now what it is in real life, a separate sheet on the
  bed: one flat box collider, which has no internal edges. Its holes are
  made per ball — a ball whose centre is over a hole stops colliding with
  the felt and drops onto the hole's edge in the bed below. Balls now run
  dead straight (a test checks under 1 mm), and the computer went from 0
  to 3 or 4 of 4 easy pots.
* **Skittles sink into a box.** Their hulls settle slowly into the felt box
  (3 mm in 4 s, then fall), where on the bed's trimesh they stand still, so
  they stand on the bed and only the balls ride on the felt.
* **Pockets scored near misses.** The sensor was a hole-sized sphere centred
  on the felt, so a ball rolling within ~47 mm of a hole scored. It is now a
  small sphere just under the bed: a ball has to drop to reach it.
* **The felt is not in the mesh.** The bed's collision surface is a felt's
  thickness (3.7 mm at life size) below `surface_y`. Skittles are seated on
  it with a raycast.
* **Skittles want simple hulls.** `CylinderShape3D` tipped them over at rest,
  and a hull with the lathe's full detail launched them across the room.
  Three 12-sided hulls built from the mesh's own rings (foot, stem, cap) are
  stable and keep the waist a ball can roll under.
* **Rolling resistance.** The solver has none, so a ball on the felt gets
  damping and a small constant drag — but only on the felt. Under the bed
  the balls are exactly as the return test runs them, and that test still
  passes 9 of 9 for both returns.
* **The web export could not have worked.** Threads need COOP/COEP headers
  a plain static server does not send (now off); the project was Forward+,
  which the browser does not have (now Compatibility everywhere); the
  preset asked for mobile texture compression the project does not import
  (a silent "configuration error"); the output went to a path the container
  did not mount; and an imported `.glb` is dropped from the pack in favour
  of the imported scene, so the game could not find its table. The `.glb` is
  now marked `importer="keep"` — its `.import` file is committed for that
  reason — and `e2e/web_smoke.py` would catch any of these again.

## Two things the game has to add

The model is of a table that clamps to a desk and has a removable bar, so
two things that are implicit in real life have to be explicit here:

* **The desk.** The return ramp's front edge is only a few millimetres
  thick; in real life it rests on the desk top, and without one a ball
  arriving at speed sinks through the tray and drops out of the world.
  `_build_desk()` puts a slab under the table at the model's own z = 0.
* **The gate.** The time bar is modelled *in* its slot, because that is
  where it goes when the game is over. The game lifts it out at the start —
  otherwise every potted ball stops dead against it, which is precisely what
  it is for. `set_gate(true)` drops it back in.

## VR

`xr/openxr/enabled` is on in the project settings. With a runtime present
the rig puts you on the floor at the baulk end of a life-size table, and the
right trigger plays the shot the controller is pointing along. With no
runtime — desktop, or the browser without WebXR — `XRRig.available()` is
false and the spectator camera is used instead, so nothing needs switching
off.

Not yet done: hand presence, grabbing the cue rather than pointing it, and
a comfort/teleport option.
