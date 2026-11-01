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
| Game | Loads, racks, aims, pots, scores | Runs headless; never seen on screen |
| Web build | **Never run** | — |
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

- [ ] **Run the web export.** `python godot/tools/web_export.py --serve` is
      written but has never been executed. The first run pulls Godot's
      export templates (~1 GB) into a separate image layer. Expect to have
      to fix something: `export_presets.cfg` was written by hand, and the
      `.glb` and layout JSON are loaded at run time, so they have to be
      caught by the preset's `include_filter`.
- [ ] **Add a browser end-to-end check.** Skiagraph's
      `godot/e2e/test_web_viewer.py` loads the exported build in headless
      Chromium with Playwright and asserts the scene logged a successful
      load with no JS errors. The same shape of test would catch an export
      that silently ships without the model.
- [ ] **Try VR.** `scripts/xr_rig.gd` is written against OpenXR and falls
      back cleanly when no runtime answers — which is all that has ever been
      tested. Needs a headset. Expect the cue to be the hard part: pointing
      a controller and pulling the trigger is a placeholder, not a cue
      action.
- [ ] **A rules engine.** The game scores pots and nothing else. Missing:
      the break (your turn continues while you keep potting), the skittle
      penalties (white = lose the break's score, black = lose everything),
      fouls, and the timer that drops the bar. `game.set_gate(true)` already
      exists and nothing calls it.
- [ ] **Rack the balls properly.** They currently sit in a row near the
      player's end. A real game starts with the red on its spot, the white
      in the D, and the rest in the tray.
- [ ] **Use the rest of the model.** The game ignores `--variant full`
      colours, the scoreboard and the cue.

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
