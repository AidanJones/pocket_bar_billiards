# Print plan - Bambu Lab P1S

- Table size: **Mini** (ball 9.525 mm, 1:5.00)
- Variant: **simple**  - one filament, no colour changes
- Filament: **PLA**, nozzle 220 C / bed 60 C
- Layer height 0.20 mm, 0.4 mm nozzle
- 8 files, 8 pieces, roughly **62 g** of filament at the walls and infill below (an estimate - the slicer is the authority)

## Before you start

- **PLA**: The default. Stiff, flat and cheap, which is what the playfield wants. Don't leave the table in a sunny window or a hot car.
- **Bambu Lab P1S**: Enclosed, so PETG/ABS/ASA are options as well as the default PLA. One nozzle, so one colour per plate unless an AMS is fitted - which is why `--variant simple` is the default. The textured PEI plate it ships with is all you need.
- Every STL is already rotated so a large flat face is on the plate. **Do not let the slicer auto-orient them.**
- `orientation: diagonal` in `parts.csv` means the part only fits when turned 45 degrees on the plate; the slicer's arrange will usually do it, but check nothing is red before you send it.

## Plates

One plate for the lot - the textured PEI it came with is fine. The playfield tiles print face down so the playing surface comes off the plate dead flat, and the felt goes over it, so the plate's texture does not matter. (With `--felt 0` you would want a smooth plate for those tiles.)

## Settings by group

### Fit-test coupon

| file | qty | material | walls | infill | plate | size (mm) | ~g | note |
|---|---|---|---|---|---|---|---|---|
| `test_hole_gauge.stl` | 1 | PLA | 4 | 30% | textured | 97.2 x 21.4 x 5.0 | 9 | five holes, -0.4 to +0.4 mm; drop a ball through each and note which one you want (nominal 11.43 mm) |
| `test_playfield_corner.stl` | 1 | PLA | 4 | 30% | textured | 71.4 x 60.0 x 5.0 | 17 | a corner of the real slab: checks thickness, flatness and the hole over felt |
| `test_wall.stl` | 1 | PLA | 3 | 15% | textured | 19.0 x 60.0 x 40.3 | 12 | checks wall height against the slab and the clamp flange |
| `test_ledge.stl` | 1 | PLA | 3 | 15% | textured | 5.0 x 56.0 x 4.0 | 1 | glue to the test wall, then rest the corner tile on it: the surface should land flush with the wall top |
| `test_rail.stl` | 1 | PLA | 3 | 15% | textured | 10.4 x 60.0 x 9.3 | 4 | press 2.0 mm cord into the groove; the nose should touch a ball 6.0 mm above the felt |
| `test_ramp.stl` | 1 | PLA | 2 | 6% | textured | 60.0 x 60.0 x 4.8 | 10 | the front of the return ramp; check a ball rolls down it, not along a layer line |
| `test_skittle.stl` | 1 | PLA | 2 | 8% | textured | 14.4 x 14.4 x 16.0 | 1 | must stand up, and topple when a ball brushes it |
| `test_clamp.stl` | 1 | PLA | 4 | 40% | textured | 46.5 x 47.0 x 14.0 | 9 | hook it over the test wall's flange and onto a 25 mm desk |

## Plates (at most 1 print jobs)

`preview_plates.png` shows one workable arrangement. It is a plain shelf pack, so the slicer's own arrange will often do better - treat the count as an upper bound.

## Supports

None. Every part is posed so nothing overhangs more than 45 degrees - the skittle caps and the ledge strips are drawn that way on purpose. If your slicer wants to add supports, the part is in the wrong orientation.

