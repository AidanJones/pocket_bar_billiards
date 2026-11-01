# AGENTS.md — Desk Bar Billiards

Instructions for a coding agent working on this project. **Read this whole
file before editing anything.** The human-facing build guide is `README.md`;
keep it in sync with what you change.

---

## 1. What this is

A parametric generator for a scale **English bar billiards** table that
clamps to the front edge of a desk and is 3D-printed in pieces.

- Nine holes in the bed: back row **30 · 20 · 10 · 20 · 30**; diamond with
  **100** (far), two **50**s (sides), **200** (nearest the player).
- Three mushroom skittles: **black** in front of the 200, **two white**
  either side of the 100 (alternative position: in front of the 50s).
- The playing surface is **level**. Potted balls drop onto a 3° ramp under
  the bed and roll to an open **tray** at the player's end.
- A removable **time-bar gate** drops into a slot in front of the tray to
  stop balls returning (the pub table's "bar drops" end-of-game).
- Shots are played from the **D** at the player's end only.
- Balls are bought, not printed. Cushions are silicone cord in a groove in
  each printed rail. Cues are an 8 mm dowel plus a printed tip and butt.

The reference table is a league one: ~800 × 1420 mm playing area, 47.6 mm
(1⅞″) ball. Everything scales from the ball you actually buy. Exact hole and
spot positions are not published by the makers, so the ones here are a
faithful *approximation* of a standard English table, not a copy of one.

---

## 2. Files

| File | Role |
|---|---|
| `profiles.py` | **Data.** Printers, filaments, table sizes. Adding a machine is a dict entry. |
| `meshlib.py` | Minimal numpy mesh kernel: `prism()`, `lathe()`, ear-clip triangulation, STL writer, manifold check. |
| `components.py` | **Reusable printable components** — panels, strips, rails, rings, pegs, clamps, the splitter — plus `Part`/`PartList`. Knows nothing about bar billiards. |
| `table.py` | **The design.** `Spec` → `Dims` → a `Design` of `Part`s, composed from `components`. No file I/O, no import side effects. |
| `barbilliards.py` | CLI: build, validate, export STLs + `parts.csv` + `print_plan.md` + `layout.json`; plate packing; `--list`, `--fit`. |
| `check.py` | Design-rule checks. Must pass, including `--all`. |
| `render.py` | Software-rasterised previews, the layout plan, and the 1:1 A4 felt template PDF. |
| `gltf.py` | The same model as a `.glb` for the game, plus the JSON it needs. Life size by default. |
| `godot/` | Godot 4.3 project: the browser/VR game and the ball-return physics test. See `godot/README.md`. |
| `README.md` | Build guide for humans (BOM, print settings, assembly, rules). |
| `stl/`, `stl_coupon/`, `previews/` | Generated. Never hand-edit. |

Dependencies: Python 3.10+, `numpy`, `matplotlib` (render only). The game
needs Docker (Godot runs in a container; there is no native install and no
Blender step — see `godot/README.md` for why).

**`table.py` is the one model.** `barbilliards.py` slices it into printable
pieces and `gltf.py` writes the assembled thing for the game. Never model
anything a second time: if the game needs a shape, it comes from
`components.py` like everything else.
**Do not add dependencies** — no trimesh, manifold3d, OpenSCAD, CadQuery —
unless the owner asks. The environment may be offline.

---

## 3. Commands (the dev loop)

One-off setup (the repo ships a `.venv`-shaped `requirements.txt`; the
system Python here has no numpy):

```bash
python -m venv .venv
.venv/Scripts/python -m pip install -r requirements.txt   # Scripts on Windows, bin elsewhere
```

Then, with that interpreter:

```bash
python barbilliards.py              # build the default table -> stl/
python check.py                     # design rules; must end "0 failure(s)"
python render.py                    # previews/ : renders, plan, felt template
```

All three share one argument parser, so any option works on any of them:

| Option | Meaning |
|---|---|
| `--size mini\|standard\|large` | table size (default `mini`) |
| `--printer p1s\|a1mini\|mk4\|…` | printer profile (default `p1s`) |
| `--material pla\|petg\|asa` | filament profile (default `pla`) |
| `--variant simple\|full` | `simple` = one filament, fewest pieces (default) |
| `--return shared\|sorted` | `shared` = one trough, as a real table (default); `sorted` = a lane per hole |
| `--coupon` | the small fit-test set instead of the table |
| `--ball`, `--cord`, `--slope`, `--felt`, `--desk`, `--colour`, `--bed`, `--out` | overrides |
| `--list`, `--fit` | show the profiles / which sizes fit this printer |

Two extras: `python check.py --all` sweeps every size × variant × printer and
is the real regression test; `python barbilliards.py --coupon` is what the
owner prints first.

**After every change: run all three, then *look at* `previews/*.png`.** A
passing check does not prove the geometry looks right.

If you touched anything under the bed — the ramp, the beams, the gate, the
return lanes — also run the simulation, which is the only thing that tests
behaviour rather than shape:

```bash
python gltf.py                              # refresh godot/assets/
python godot/tools/physics_test.py --return sorted
```

---

## 4. Coordinate system and dimensions

Assembled frame, millimetres:

- **X** across the table, 0 = centreline.
- **Y** along it, **0 = front cushion nose**, +Y towards the far end.
  The player stands at −Y.
- **Z** up, **0 = desk top**.

Every derived dimension is an attribute of `table.Dims`, computed once from a
`Spec`. Read them from there — `d.zt`, `d.xi`, `d.ramp_z(y)`, `d.hole_open` —
and **never copy a number out of `Dims` into the code.** The useful ones:

| Name | Meaning |
|---|---|
| `width`, `length` | playing area between cushion noses |
| `half_width`, `p`, `xi`, `xo` | cushion nose / playfield edge / wall inner / wall outer, in X |
| `y_pf0…y_pf1`, `y_bw0/1`, `y_fb0/1`, `y_ap0/1`, `y_lip0/1` | Y stations, front (−Y) to back |
| `zp`, `zt` | playfield underside / playing surface |
| `ramp_z(y)` | ball-return surface height at Y |
| `cush_z`, `rail_h`, `x_face` | cushion cord centre, rail height, rail face |
| `hole_open`, `hole_d`, `hole_r` | ball drop / cut in the playfield |
| `g_*` | the time-bar gate |
| `peg_cap`, `peg_base`, `peg_h`, `peg_rim` | skittles |

Layout data (holes, skittle spots, baulk line, D, red spot, felt outline) is
in `table.REAL_HOLES` and friends, **in real-table millimetres**, scaled on
the way out and written to `layout.json`. Edit the real-table numbers.

---

## 5. How geometry is built (the important constraint)

There is **no boolean/CSG engine.** Every part is one of:

- `prism(outer, holes, w0, w1, plane)` — a 2D polygon with optional holes,
  extruded along the third axis. `plane="xy"` extrudes in Z, `"xz"` in Y,
  `"yz"` in X. Holes must sit fully inside the outline and must not touch
  each other or it.
- `lathe(profile, n)` — a closed `(r, z)` polygon revolved about Z. Points
  with `r == 0` collapse onto the axis.

Consequences:

- A hole can only go **through a part along its extrusion axis.** A part
  needing holes in two directions must be split, or redesigned.
- No fillets except those drawn into a profile. Chamfers go in the profile.
- Parts are joined in real life by glue, not modelled unions. Don't try to
  merge overlapping solids into one STL.

**Build parts from `components.py`, not from fresh triangle soup.** That is
the whole point of the split: a component is exercised by every design that
uses it, and it is what makes a new size or printer work without new
geometry code. If you need a shape that isn't there, add a *general* one to
`components.py` (dimensions in, mesh out, no table knowledge) and use it.

Adding a part to the table:

```python
_add_strip(parts, "my_beam", profile, lo, hi, "yz", pr.max_strip(cross),
           role="frame", colour=spec.hue("frame"), pose=("x", 90),
           note="what the builder needs to know")
```

`_add_strip` splits the part automatically when it will not fit the bed, so
prefer it over `parts.add` for anything long. `pose` is the rotation that
puts a large flat face on the plate; the exporter applies it. Add the part to
`render.py:scene()` if it should appear in the previews.

Profiles returned by `components` are in a local **(u, z)** frame where
`u = 0` is the working face; `C.place(profile, origin_u, origin_z, u_dir)`
maps it into the world, and `u_dir = -1` makes the left-hand twin of a
right-hand part.

---

## 6. Design rules (invariants)

Enforced by `check.py` and by `barbilliards.measure()`. **Don't weaken a check
to make a change pass** — fix the geometry, or ask the owner.

1. Every part is watertight, positively oriented, and fits the chosen
   printer (straight or turned 45°), with nothing thinner than two
   perimeters or taller than the gantry.
2. Hole opening ≥ ball + 1.5 mm.
3. Clearance under the playfield (minus splice plates) ≥ ball + 3 mm above
   the ramp at every hole, and under the front and apron beams.
4. Ramp slope ≥ 2°.
5. The gate leaves gaps < ½ ball at its sides and bottom, its slot is wider
   than the gate but not by half a ball, and its grip clears the rails.
6. Holes lie inside the cushions and are at least one ball apart edge to edge.
7. Skittle cap is wider than a hole (cap ≥ hole + 3 mm); a ball rolls under
   the cap rim; skittle bases don't overlap holes, in either white position.
8. Cushion contact height 0.60–0.70 × ball diameter above the felt; rails at
   least 0.9 × ball tall; the cord fits its groove and sits inside the rail.
9. Playfield tile seams stay ≥ hole radius + 3 mm from every hole, and no
   splice plate covers a hole.
10. Nothing needs supports: every part is posed so no overhang exceeds 45°.
11. `--variant simple` really is one filament and one colour, and with felt
    it needs only one build plate.
12. The scoreboard markers are captive (foot wider than the slot neck), run
    free in their channel, pass the neck with 0-0.4 mm of play, and do not
    crowd each other at the chosen pitch.
13. With `--return sorted`: every hole has a lane at least a ball plus two
    fins wide, no lane wall passes under a hole, every chute leaves a ball's
    headroom, and a chute only ever crosses a lane whose own hole is nearer
    the player — so nothing is rolling down it at the time.

Also keep: all sizes driven by `Spec`/`Dims`, splitting automatic, and
`check.py --all` green across every printer in `profiles.py`.

---

## 7. Common tweaks — where to change things

| Want | Change |
|---|---|
| A new printer or filament | a `Printer` / `Material` entry in `profiles.py`. Nothing else. |
| A different table size | a `Size` entry in `profiles.py`, or `--ball` / `--cord` |
| A different hole layout, or a particular pub's table | `REAL_HOLES`, `REAL_BAULK_Y`, `REAL_D_RADIUS`, `REAL_RED_OFFSET` in `table.py` (real-table mm) |
| Skittles in front of the 50s by default | swap `peg_white` / `peg_white_alt` in `table._layout` (and the README) |
| Pin-style skittles instead of mushrooms | a new lathe component beside `mushroom_peg`; keep rule 7 |
| Wider/narrower holes | the `1.20 * ball` factor in `Dims.hole_open` |
| Thicker playfield | `Dims.tp` (everything above re-derives) |
| A different cushion | `--cord`, `grooved_rail_profile()`; keep rule 8 |
| Clamps for other desks | `--desk`, or the `[18, 25, 32, 40]` list in `table.design` |
| Steeper return | `--slope` |
| What goes in the fit-test coupon | `table.coupon()` |
| How the scored return assigns lanes | `return_lanes()` in `table.py` |
| Scoreboard size, rows or marker fit | the `sb_*` block in `Dims` (nozzle-driven, not ball-driven) |
| The paper scale | `render.scoreboard_scale()` |
| A new render angle | `render(..., view=(azimuth_deg, elevation_deg))` |

---

## 8. Ground rules

- Keep changes small and parametric. No magic numbers that silently assume a
  particular ball size, nozzle or bed.
- Scale things by what actually drives them: ball size for play geometry,
  nozzle and layer height for printed-wall minimums, the desk for the
  mounting hardware. Say which in a comment when it isn't obvious.
- Don't hand-edit anything in `stl/`, `stl_coupon/` or `previews/`;
  regenerate.
- When you add, remove or rename a part, update the README's print table and
  assembly steps.
- Don't give `table.py` file I/O or import side effects: `check.py`,
  `render.py` and the CLI all build a `Design` and look at it.
- If a requested change conflicts with a design rule, say which rule and
  propose an alternative instead of breaking it silently.
- Finish by reporting: what changed, the `check.py` result (ideally
  `--all`), the new part count / plate count / size printed by
  `barbilliards.py`, and anything the owner should look at in the previews.

---

## 9. Known limitations / good next tasks

- Hole and spot positions are approximate (see §1).
- The ramp wedges are solid and are the single biggest print. Low infill
  handles it, but a ribbed ramp — still prism-only — would print faster.
- The playfield relies on splice plates and ledges for flatness; there is no
  centre support under the long span.
- Seams in the side walls and rails are plain butt joints. Alignment pins
  would help, and a pin hole along the extrusion axis is possible.
- `pack_plates()` is a shelf pack with a special case for 45° strips, so its
  plate count is an upper bound, not the slicer's answer.
- The filament estimate in `parts.csv` is a shell-plus-infill approximation.
- The scoreboard markers are a friction fit, not a detent: nothing printed
  flat like that would spring. A sprung pawl would need a part with a thin
  cantilever, which `prism` can draw but which wants testing.
- `--return sorted` is built but has never been printed. Its geometry is
  checked and `godot/tools/physics_test.py` simulates it, but a simulation
  is not a plate. Real tables do not do this: they return every ball to one
  trough and the players keep score.
- The game has no rules engine yet — it scores pots and that is all. No
  break tracking, no skittle penalties, no timer, no second player.
- The sorted return costs 20 extra pieces and a plate, which is why it is
  not the default.
- No automatic timer (idea: ESP32 + micro servo dropping the gate after
  ~15 min).
