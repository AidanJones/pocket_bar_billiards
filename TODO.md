# TODO

Where this project actually is, and what to do next. Ordered by what would
teach us the most, not by what is easiest.

## State of play

| | Status | How we know |
|---|---|---|
| Generator | Works for 3 sizes × 2 variants × 2 returns × 7 printers | `check.py --all`: 84 combinations, 108–175 rules each |
| STL output | Watertight, fits the plate, poses itself | Export asserts, plus a re-read of every written file |
| Shared ball return | 9 of 9 balls reach the tray | Godot physics, life size |
| Sorted ball return | 9 of 9 balls reach the right lane | Godot physics, life size |
| Scoreboard | Geometry and fit checked | `check.py` rules 12 |
| Game | Plays to the rules: breaks, fouls, skittles, last ball, clock, score limit, 1–4 players or the computer | `godot/tools/game_test.py`: 63 rule checks + 70 on the table; `--autoplay` soaks (40 random, 60 computer shots, no ball lost) |
| Web build | Loads, plays a shot, the computer replies, in Chromium | `godot/e2e/web_smoke.py` (headless, SwiftShader); the owner has played it once |
| VR | **Never run** | — |
| **Anything printed** | **No** | — |

The two things worth remembering: **nothing has been printed**, and the
physics results are from a simulation at life size, which is not the same
as a 1:3.75 table made of PLA.

---

## 0. Moving to another machine

1. **Push first.** As of this writing the remote has only the initial
   commit; everything since is local. `git log origin/main..HEAD` should be
   empty before you wipe anything.
2. Setup is in `README.md` §3 — a venv, `requirements.txt`, and Docker for
   the game. Nothing else is installed on the host: Godot runs in a
   container and there is no Blender step.
3. Prove the move worked:
   ```bash
   python check.py --all                  # 0 failing combinations
   python barbilliards.py && python render.py
   python godot/tools/physics_test.py --return sorted   # 9 of 9
   ```

---

## 1. Print something (the biggest unknown)

Everything below this line is speculation until a plate comes off.

- [ ] **Print the fit-test coupon.** `python barbilliards.py --coupon --out
      stl_coupon` — one plate, ~60 g, about an hour. Work through the table
      in `README.md` §3: the hole gauge decides your real hole size, the
      wall + ledge + corner tells you whether the slab lands flush, the
      rail tells you whether the cushion sits at the right height.
- [ ] **Feed the gauge result back.** If the gauge says your printer wants a
      different hole, change the `1.20 * ball` factor in `Dims.hole_open`
      rather than fudging `--ball`.
- [ ] **Add a scoreboard sample to the coupon.** `table.coupon()` covers the
      table but not the slider: the marker is a friction fit with 0.15 mm of
      play, which is a guess, and a guess is exactly what a coupon is for. A
      two-bay stub of `score_face` + `score_track` + one marker would settle
      it for pennies.
- [ ] **Print the Mini, shared return.** Then check the things the
      simulation cannot: do the skittles topple when brushed but stand when
      the table is knocked; does a ball actually roll home on a 3° PLA ramp
      (friction, layer lines and print texture are all absent from the
      sim); do the clamps grip your desk.
- [ ] **Only then try `--return sorted`.** 20 extra pieces and a plate, and
      the chutes are the part most likely to behave differently in plastic.

---

## 2. The game

- [x] **Run the web export.** Five things were wrong; `godot/README.md`
      ("What making it playable found") lists them. The worst: an imported
      `.glb` is left out of the pack, so the build shipped without its table.
- [x] **Add a browser end-to-end check.** `godot/e2e/web_smoke.py` loads the
      export in Playwright's Chromium, starts a game, drags a shot, checks
      it was scored and that the computer replies, with no page errors. It
      caught the missing `.glb`.
- [ ] **More people playing the web build.** The owner's first go asked
      for: turns passing on no score, a computer opponent, the rules in the
      game, tests for every rule, up to four players, a score limit, a
      reset, hole values on the felt, slightly easier pockets, and a rule
      for a ball off the table, and an easy way to play the red once it is
      back in the tray (E, or a button) — all done. Still for a human to judge: the
      power range, whether the pocket help is too much or too little
      (`POCKET_REACH`, `POCKET_PULL` in game.gd), and touch on a phone.
- [ ] **Side spin, and aim-then-power.** The two ideas worth taking from
      Shadowfetch Pool (MIT): a torque impulse for side, and aiming with
      the mouse while setting power separately (wheel, or a held button).
      The aim guide's 90° rule is only exact without spin, so spin needs
      the guide to say so.
- [ ] **Try VR.** `scripts/xr_rig.gd` is written against OpenXR and falls
      back cleanly when no runtime answers — which is all that has ever been
      tested. Needs a headset. Expect the cue to be the hard part: pointing
      a controller and pulling the trigger is a placeholder, not a cue
      action.
- [x] **A rules engine.** `scripts/rules.gd`: breaks, the red doubling,
      fouls that lose the break (no ball hit, a ball off the table, a white
      skittle, an opening shot that misses the red or clears the table), the
      black skittle, the red re-spotted on a cleared table, every ball in
      play, the last-ball rule, one to four players, a clock and a score
      limit. Tested twice over: `tests/test_rules.gd` (no table) and
      `tests/test_game.gd` (on the table, through the physics). Not yet: the
      break shot's three attempts and the "split shot"; no handicap or turn
      timer.
- [x] **A computer player.** `scripts/ai.gd`: ghost-ball pots checked
      against the physics space, a pace model fitted to the felt, and a
      safe touch when there is no pot.
- [ ] **Teach the computer about its own ball after contact.** It fouls
      by running on into a white skittle (4 in 60 shots). Sweep the
      tangent line from the ghost ball, as the aim guide already draws it.
- [ ] **Let the computer choose the red.** It plays whatever ball comes
      out of the tray (whites first). It could take the red when it has a
      good pot, and leave it in the tray otherwise.
- [ ] **A skill setting in the menu.** `ai.skill_noise` is there; nothing
      sets it but the tests.
- [x] **Rack the balls properly.** Red on its spot, the rest in the tray,
      each shot played from the tray into the D.
- [ ] **Use the rest of the model.** The game ignores `--variant full`
      colours, the scoreboard and the printed cue (it draws its own). The
      felt is painted on in the game: the bed mesh is the printed slab.

---

## 3. The generator

- [ ] **Physics-test `--variant full`.** The coloured rings sit in the hole
      and change its effective diameter; no simulation has included them.
- [ ] **A ribbed or hollow ramp.** The ramp wedges are solid and are the
      single biggest print — roughly 200 g of the Mini's 740 g. Low infill
      hides it, but the slicer still traces the whole volume. A ribbed ramp
      is possible within the prism-only rule; it just needs care about the
      gaps a ball could drop into.
- [ ] **Alignment pins on the butt joints.** Side walls and rails meet end
      to end with nothing locating them, so they rely on gluing against a
      straight edge. A pin hole along the extrusion axis is buildable.
- [ ] **Support the playfield's centre.** The slab spans the full width on
      ledges and splice plates alone. Nothing has sagged yet because
      nothing has been printed.
- [ ] **A detent for the scoreboard markers.** They run on friction; a
      sprung pawl would click. `prism` can draw a thin cantilever, but
      whether PLA will spring at that size is a print-and-see.

---

## 4. Things a faster machine buys

Timings from an 8-core Windows box, for comparison:

| Command | Time | Why it is slow |
|---|---|---|
| `check.py --all` | 96 s | 84 combinations, built one after another. Embarrassingly parallel — `multiprocessing.Pool` over the combination list would be a short change. |
| `render.py` | 21 s | `render()` rasterises triangle by triangle in a Python loop. Vectorising the inner loop over all triangles at once is the obvious fix; a tile-based numpy pass would be better. |
| `physics_test.py` | 42 s | One container, one hole at a time. The matrix (3 sizes × 2 returns) is six serial runs; they could go in parallel containers. |
| `barbilliards.py` | 4 s | Fine. |

- [ ] Parallelise `check.py --all`.
- [ ] Vectorise the rasteriser in `render.py`.
- [ ] A `physics_test.py --matrix` that runs every size and return and
      prints one table.

---

## 5. Ideas, not commitments

- An automatic timer: ESP32 + a micro servo that drops the gate after
  ~15 minutes, with an optional coin slot.
- Other pub layouts. Hole positions live in `table.REAL_HOLES` in
  real-table millimetres, so a particular table is a few numbers.
- A scoreboard that counts the balls in the sorted return's lanes instead
  of being moved by hand.

---

## Known limitations that are not bugs

These are consequences of the design, recorded so nobody "fixes" them twice.
The full list with reasoning is `AGENTS.md` §9.

- Hole and spot positions are an approximation; the makers do not publish
  them.
- `pack_plates()` is a shelf pack, so its plate count is an upper bound, not
  the slicer's answer.
- The filament figures in `parts.csv` are a shell-plus-infill estimate.
- `--as-printed --size mini` hands Godot a 9.5 mm ball, below what its
  solver handles reliably. The smoke test warns; treat the result as
  inconclusive rather than as a fault in the table.
- No CSG. Every part is an extruded outline or a revolved profile, which is
  the constraint that shapes most of the design — see `AGENTS.md` §5 before
  concluding something is "obviously" easy.
