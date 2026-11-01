# Print plan - Bambu Lab P1S

- Table size: **Mini** (ball 9.525 mm, 1:5.00)
- Variant: **simple**  - one filament, no colour changes
- Filament: **PLA**, nozzle 220 C / bed 60 C
- Layer height 0.20 mm, 0.4 mm nozzle
- 25 files, 29 pieces, roughly **712 g** of filament at the walls and infill below (an estimate - the slicer is the authority)

## Before you start

- **PLA**: The default. Stiff, flat and cheap, which is what the playfield wants. Don't leave the table in a sunny window or a hot car.
- **Bambu Lab P1S**: Enclosed, so PETG/ABS/ASA are options as well as the default PLA. One nozzle, so one colour per plate unless an AMS is fitted - which is why `--variant simple` is the default. The textured PEI plate it ships with is all you need.
- Every STL is already rotated so a large flat face is on the plate. **Do not let the slicer auto-orient them.**
- `orientation: diagonal` in `parts.csv` means the part only fits when turned 45 degrees on the plate; the slicer's arrange will usually do it, but check nothing is red before you send it.

## Plates

One plate for the lot - the textured PEI it came with is fine. The playfield tiles print face down so the playing surface comes off the plate dead flat, and the felt goes over it, so the plate's texture does not matter. (With `--felt 0` you would want a smooth plate for those tiles.)

## Settings by group

### Playing surface

| file | qty | material | walls | infill | plate | size (mm) | ~g | note |
|---|---|---|---|---|---|---|---|---|
| `playfield_r1_c1.stl` | 1 | PLA | 4 | 30% | textured | 172.1 x 130.1 x 5.0 | 85 | printed TOP FACE DOWN so the playing surface is dead flat - felt covers it, so any plate will do |
| `playfield_r2_c1.stl` | 1 | PLA | 4 | 30% | textured | 172.1 x 166.1 x 5.0 | 106 | printed TOP FACE DOWN so the playing surface is dead flat - felt covers it, so any plate will do |
| `splice_cross_1.stl` | 1 | PLA | 3 | 100% | textured | 162.1 x 16.0 x 2.0 | 6 | glue under the crossways tile seam |

### Box and frame

| file | qty | material | walls | infill | plate | size (mm) | ~g | note |
|---|---|---|---|---|---|---|---|---|
| `side_wall_right_1.stl` | 1 | PLA | 3 | 15% | textured | 19.0 x 177.2 x 40.3 | 33 | stands on its own flange; piece _1 is the front |
| `side_wall_right_2.stl` | 1 | PLA | 3 | 15% | textured | 19.0 x 177.2 x 40.3 | 33 | stands on its own flange; piece _1 is the front |
| `ledge_strip_right_1.stl` | 1 | PLA | 3 | 15% | textured | 5.0 x 287.2 x 4.0 | 4 | glue inside the wall, flat top level with the slab underside |
| `side_wall_left_1.stl` | 1 | PLA | 3 | 15% | textured | 19.0 x 177.2 x 40.3 | 33 | stands on its own flange; piece _1 is the front |
| `side_wall_left_2.stl` | 1 | PLA | 3 | 15% | textured | 19.0 x 177.2 x 40.3 | 33 | stands on its own flange; piece _1 is the front |
| `ledge_strip_left_1.stl` | 1 | PLA | 3 | 15% | textured | 5.0 x 287.2 x 4.0 | 4 | glue inside the wall, flat top level with the slab underside |
| `back_wall.stl` | 1 | PLA | 3 | 15% | textured | 172.3 x 40.3 x 8.0 | 24 | ledge faces inward |
| `front_beam.stl` | 1 | PLA | 3 | 15% | textured | 172.3 x 13.0 x 8.0 | 10 | ledge faces the far end; its front face is the back of the gate slot |
| `apron_beam.stl` | 1 | PLA | 3 | 15% | textured | 172.3 x 8.0 x 13.0 | 11 | glue 3.6 mm in front of the front beam: that gap is the gate slot |
| `tray_lip.stl` | 1 | PLA | 3 | 15% | textured | 172.3 x 4.0 x 11.6 | 8 | front of the ball tray; sits at the desk edge |

### Ball-return ramp

| file | qty | material | walls | infill | plate | size (mm) | ~g | note |
|---|---|---|---|---|---|---|---|---|
| `ramp_r1_c1.stl` | 1 | PLA | 2 | 6% | textured | 171.7 x 172.9 x 10.7 | 87 | thin end to the front; nobody sees these, keep the infill low |
| `ramp_r2_c1.stl` | 1 | PLA | 2 | 6% | textured | 171.7 x 172.9 x 19.7 | 113 | thin end to the front; nobody sees these, keep the infill low |

### Rails and cushions

| file | qty | material | walls | infill | plate | size (mm) | ~g | note |
|---|---|---|---|---|---|---|---|---|
| `rail_side_right_1.stl` | 1 | PLA | 3 | 15% | textured | 10.4 x 304.8 x 9.3 | 20 | groove faces inward; stagger its seams off the wall seams |
| `rail_side_left_1.stl` | 1 | PLA | 3 | 15% | textured | 10.4 x 304.8 x 9.3 | 20 | groove faces inward; stagger its seams off the wall seams |
| `rail_far.stl` | 1 | PLA | 3 | 15% | textured | 162.1 x 10.4 x 9.3 | 11 | fits between the side rails |
| `rail_front.stl` | 1 | PLA | 3 | 15% | textured | 162.1 x 10.4 x 9.3 | 11 | fits between the side rails |

### Playing pieces

| file | qty | material | walls | infill | plate | size (mm) | ~g | note |
|---|---|---|---|---|---|---|---|---|
| `time_bar_gate.stl` | 1 | PLA | 4 | 25% | textured | 171.5 x 54.1 x 3.0 | 21 | drop it into the slot when time is up |
| `skittle.stl` | 3 | PLA | 2 | 8% | textured | 14.4 x 14.4 x 16.0 | 2 | print upright, no supports; keep them light so they topple |

### Desk mounting

| file | qty | material | walls | infill | plate | size (mm) | ~g | note |
|---|---|---|---|---|---|---|---|---|
| `desk_clamp_25mm.stl` | 2 | PLA | 4 | 40% | textured | 46.5 x 47.0 x 14.0 | 18 | for desks about 21-29 mm thick (PETG survives the flexing better, if you have a second spool) |
| `clamp_shim.stl` | 2 | PLA | 3 | 25% | textured | 50.0 x 14.0 x 12.0 | 8 | tap in between clamp jaw and desk underside |

### Cues

| file | qty | material | walls | infill | plate | size (mm) | ~g | note |
|---|---|---|---|---|---|---|---|---|
| `cue_tip_ferrule.stl` | 1 | PLA | 3 | 30% | textured | 10.4 x 10.4 x 21.0 | 1 | glue onto an 8 mm dowel; face it with a 9 mm leather disc |
| `cue_butt.stl` | 1 | PLA | 3 | 15% | textured | 18.0 x 18.0 x 80.0 | 10 |  |

## Plates (at most 6 print jobs)

`preview_plates.png` shows one workable arrangement. It is a plain shelf pack, so the slicer's own arrange will often do better - treat the count as an upper bound.

## Supports

None. Every part is posed so nothing overhangs more than 45 degrees - the skittle caps and the ledge strips are drawn that way on purpose. If your slicer wants to add supports, the part is in the wrong orientation.

