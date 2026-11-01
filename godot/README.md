# The game

A Godot 4.3 version of the same table, playable in a browser and (with a
headset plugged in) in VR — and, more usefully while the design is still
moving, a physics rig for testing the ball return before anything is
printed.

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
python godot/tools/web_export.py --serve        # browser build on :8070
cd godot && docker compose --profile vnc up godot-vnc   # watch/play on :6080
```

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

**Sorted return: 5 of 9.** The five holes that drop straight into their own
lane all work. **All four holes that need a chute fail**: the ball lands on
the chute and stops on it (the left 30, the 10, the 100), or is deflected
but not far enough and ends up one lane over (the right 30). The chute is a
shallow cross-slope — about 7° — and a ball dropping onto it from above has
no reason to roll off it. That mechanism needs rethinking before the sorted
return is worth printing; the lanes themselves are fine.

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
| `scripts/game.gd` | Builds the world, racks the balls, scores the pockets. Also builds the desk and lifts the gate out — see below. |
| `scripts/cue.gd` | Drag to aim, release to play. Shared by mouse and VR trigger. |
| `scripts/xr_rig.gd` | OpenXR rig; falls back to the spectator camera when no runtime answers. |
| `scripts/smoke_test.gd` | The headless ball-return test. |
| `assets/` | Generated by `gltf.py`. Never hand-edit. |
| `Dockerfile`, `docker-compose.yml` | Godot 4.3 headless / VNC / web images. |
| `tools/` | Thin Python wrappers around the compose commands. |

The Docker setup is adapted from the Skiagraph project's Godot image, which
had already worked out the headless flags, the writable `HOME` and the
separate web-templates layer.

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
