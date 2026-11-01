#!/usr/bin/env python3
"""Desk bar billiards - build the printable parts.

    python barbilliards.py                      # mini table, one colour, P1S
    python barbilliards.py --coupon             # the 1-hour fit test, print this first
    python barbilliards.py --size standard      # the full 1/2" table
    python barbilliards.py --variant full       # coloured rings, all clamp sizes
    python barbilliards.py --printer mk4 --material petg
    python barbilliards.py --list               # printers, materials, sizes

Writes `<out>/*.stl` plus `parts.csv`, `print_plan.md` and `layout.json`.
Every part is checked watertight and checked to fit the chosen printer before
it is written; a failure is a bug in the design, not something to override.

The geometry lives in `table.py` (composed from `components.py`); the
machine and filament data live in `profiles.py`.
"""
from __future__ import annotations

import argparse
import csv
import dataclasses
import json
import math
import os
import sys

import profiles as P
import table as T


# --------------------------------------------------------------------- CLI
def parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        description="Generate the printable parts for a desk bar billiards table.")
    ap.add_argument("--size", default="mini", help="table size preset (default: mini)")
    ap.add_argument("--printer", default="p1s", help="printer profile (default: p1s)")
    ap.add_argument("--material", default="pla", help="filament profile (default: pla)")
    ap.add_argument("--variant", default="simple", choices=("simple", "full"),
                    help="simple = one colour and fewest pieces (default); "
                         "full = coloured hole rings, every clamp size, two cues")
    ap.add_argument("--coupon", action="store_true",
                    help="build the small fit-test set instead of the table")
    ap.add_argument("--slope", type=float, default=3.0, help="ball-return slope, degrees")
    ap.add_argument("--ball", type=float, default=None, help="override the ball diameter, mm")
    ap.add_argument("--cord", type=float, default=None, help="override the cushion cord, mm")
    ap.add_argument("--felt", type=float, default=1.0, help="felt thickness, mm (0 = none)")
    ap.add_argument("--desk", type=float, default=25.0, help="desk top thickness, mm")
    ap.add_argument("--colour", default="#8a5a2b", help="the one filament colour, for --variant simple")
    ap.add_argument("--return", dest="ball_return", default="shared",
                    choices=("shared", "sorted"),
                    help="shared = one trough, as a real table does (default); "
                         "sorted = a lane per hole, so a returned ball shows what "
                         "it scored")
    ap.add_argument("--bed", type=float, default=None,
                    help="override the printer's bed with a square one, mm")
    ap.add_argument("--out", default="stl", help="output directory (default: stl)")
    ap.add_argument("--list", action="store_true", help="list profiles and exit")
    ap.add_argument("--fit", action="store_true",
                    help="report which table sizes fit this printer, and exit")
    return ap


def spec_from(args) -> T.Spec:
    pr = P.printer(args.printer)
    if args.bed:
        pr = P.Printer(**{**pr.__dict__, "key": f"{pr.key}-{args.bed:.0f}",
                          "name": f"{pr.name} ({args.bed:.0f} mm bed)",
                          "bed": (args.bed, args.bed), "square_bed": True})
    return T.Spec(size=P.size(args.size), printer=pr, material=P.material(args.material),
                  variant=args.variant, slope=args.slope,
                  ball=args.ball or P.size(args.size).ball,
                  cord=args.cord or P.size(args.size).cord,
                  felt=args.felt, desk=args.desk,
                  cues=1 if args.variant == "simple" else 2, colour=args.colour,
                  sorted_return=args.ball_return == "sorted")


def build(args) -> T.Design:
    spec = spec_from(args)
    if spec.material.needs_enclosure and not spec.printer.enclosed:
        raise SystemExit(f"{spec.material.name} needs an enclosed printer; "
                         f"{spec.printer.name} is open-frame")
    if spec.slope < 2.0:
        raise SystemExit("--slope below 2 degrees will not return balls reliably")
    return T.coupon(spec) if args.coupon else T.design(spec)


# ------------------------------------------------------------------ export
def posed(part):
    """The part rotated into its print pose and dropped onto the plate."""
    m = part.mesh.rotate(*part.pose) if part.pose else part.mesh
    return m.to_bed()


SOLID_LAYERS = 5          # top and bottom solid layers assumed when estimating


def filament_cm3(part, posed_mesh, printer) -> float:
    """Rough filament estimate in cm3: shell plus infill.

    Faces lying flat on the plate cost `SOLID_LAYERS` of solid material;
    upright faces cost `walls` perimeters. Much closer than the solid volume,
    which is wildly pessimistic for the ramp wedges at 6 % infill — but it is
    still an estimate, and the slicer is the authority.
    """
    solid = part.mesh.volume()
    shell = (posed_mesh.area(flat=True) * SOLID_LAYERS * printer.layer
             + posed_mesh.area(flat=False) * part.walls * printer.nozzle)
    shell = min(solid, shell)
    return (shell + (solid - shell) * part.infill / 100.0) / 1000.0


def pack_plates(design: T.Design, gap=6.0):
    """Arrange every piece onto build plates. Returns `[(material, [(part, mesh)])]`.

    First-fit decreasing height onto shelves, trying each piece both ways
    round, with parts that only fit at 45 degrees turned first. Each material
    gets its own plates, since you cannot print two filaments in one job.

    It is a conservative shelf pack, not the slicer's arranger: treat the
    plate count as an upper bound on the number of print jobs.
    """
    pr = design.spec.printer
    width, height = pr.usable
    square, slanted = {}, {}
    for part in design.parts:
        m = posed(part)
        ex = m.extents()
        if pr.fits(ex) == "diagonal":
            # Turn it so it runs along the bed's "/" diagonal, then it can
            # share the plate with other long strips in parallel lanes.
            m = m.rotate("z", 45 if ex[1] >= ex[0] else 135).to_bed()
            slanted.setdefault(part.material, []).append((part, m, min(ex[0], ex[1])))
        else:
            square.setdefault(part.material, []).extend([(part, m)] * part.qty)

    out = []
    for material, items in slanted.items():
        out += [(material, p) for p in _pack_lanes(items, width, height, gap)]
    for material, items in square.items():
        items.sort(key=lambda it: -min(it[1].extents()[:2]) - max(it[1].extents()[:2]))
        plates = []                 # each: {"items": [...], "shelves": [[y, h, x]]}
        for part, mesh in items:
            ex = mesh.extents()
            for plate in plates:
                if _place(plate, part, mesh, ex, width, height, gap):
                    break
            else:
                plate = {"items": [], "shelves": []}
                plates.append(plate)
                if not _place(plate, part, mesh, ex, width, height, gap):
                    raise SystemExit(f"{part.name} will not fit an empty plate")
        out += [(material, p["items"]) for p in plates]
    return out


def _pack_lanes(items, width, height, gap):
    """Long strips, already turned 45 degrees, stacked as parallel lanes.

    Each one is slid sideways by its own width, so a plate holds as many as
    the diagonal has room for rather than one apiece.
    """
    import numpy as np

    lane = np.array([-1.0, 1.0]) / math.sqrt(2.0)      # along a turned strip
    step = np.array([1.0, 1.0]) / math.sqrt(2.0)       # across the lanes
    items = sorted(items, key=lambda it: -max(it[1].extents()[:2]))
    plates, current, offset, lo, hi = [], [], 0.0, None, None
    for part, mesh, cross in items:
        # Line every strip up on the same end of the diagonal: centring them
        # instead would leave the short ones sticking out past the plate.
        mesh = mesh.translate(*(-(mesh.v[:, :2] @ lane).min() * lane), 0)
        for _ in range(part.qty):
            moved = mesh.translate(*(step * offset), 0)
            mn, mx = moved.v.min(0)[:2], moved.v.max(0)[:2]
            nlo = mn if lo is None else np.minimum(lo, mn)
            nhi = mx if hi is None else np.maximum(hi, mx)
            if current and (nhi[0] - nlo[0] > width or nhi[1] - nlo[1] > height):
                plates.append(_zero(current))
                current, offset, lo, hi = [], 0.0, None, None
                moved = mesh
                nlo, nhi = moved.v.min(0)[:2], moved.v.max(0)[:2]
            current.append((part, moved))
            lo, hi = nlo, nhi
            offset += cross + gap
    if current:
        plates.append(_zero(current))
    return plates


def _zero(items):
    """Shift a packed plate so its contents start at the plate origin."""
    import numpy as np

    lo = np.min([m.v.min(0) for _, m in items], axis=0)
    return [(p, m.translate(-lo[0], -lo[1], 0)) for p, m in items]


def _place(plate, part, mesh, ex, width, height, gap):
    """Try the piece on this plate, both ways round, nearest shelf first."""
    for turn in (0, 90):
        w, h = (ex[0], ex[1]) if turn == 0 else (ex[1], ex[0])
        if w > width or h > height:
            continue
        for shelf in plate["shelves"]:                       # an existing shelf
            if h <= shelf[1] and shelf[2] + w <= width:
                _put(plate, part, mesh, turn, shelf[2], shelf[0], gap)
                shelf[2] += w + gap
                return True
        top = max((s[0] + s[1] + gap for s in plate["shelves"]), default=0.0)
        if top + h <= height:                                # a new shelf
            plate["shelves"].append([top, h, w + gap])
            _put(plate, part, mesh, turn, 0.0, top, gap)
            return True
    return False


def _put(plate, part, mesh, turn, x, y, gap):
    m = mesh.rotate("z", turn).to_bed() if turn else mesh
    lo = m.v.min(0)
    plate["items"].append((part, m.translate(x - lo[0], y - lo[1], 0)))


def measure(design: T.Design) -> list[dict]:
    """Pose, validate and measure every part. Raises on anything unprintable.

    This writes nothing, so `check.py` can run the same gate as the exporter.
    """
    pr = design.spec.printer
    rows = []
    for part in design.parts:
        watertight, oriented = part.mesh.check()
        if not (watertight and oriented and part.mesh.volume() > 0):
            raise SystemExit(f"{part.name}: mesh is not a closed solid "
                             f"(watertight={watertight}, oriented={oriented})")
        m = posed(part)
        ext = m.extents()
        fit = pr.fits(ext)
        if fit is None:
            raise SystemExit(
                f"{part.name}: {ext[0]:.0f} x {ext[1]:.0f} x {ext[2]:.0f} mm does not "
                f"fit {pr.name} ({pr.bed[0]:.0f} x {pr.bed[1]:.0f} usable "
                f"{pr.usable[0]:.0f} x {pr.usable[1]:.0f}). Pick a smaller --size.")
        rows.append(dict(
            file=f"{part.name}.stl", role=part.role, qty=part.qty,
            material=part.material, colour=part.colour,
            size_mm=" x ".join(f"{e:.1f}" for e in ext),
            orientation=fit, plate=part.plate, walls=part.walls, infill=part.infill,
            supports="yes" if part.supports else "no",
            volume_cm3=round(part.mesh.volume() / 1000, 2),
            filament_cm3=round(filament_cm3(part, m, pr), 2), note=part.note))
    return rows


def export(design: T.Design, out: str) -> list[dict]:
    """Validate, then write the STLs and the three index files."""
    rows = measure(design)
    os.makedirs(out, exist_ok=True)
    for part in design.parts:
        posed(part).write_stl(os.path.join(out, f"{part.name}.stl"))

    with open(os.path.join(out, "parts.csv"), "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]), lineterminator="\n")
        w.writeheader()
        w.writerows(rows)
    with open(os.path.join(out, "layout.json"), "w", encoding="utf-8") as fh:
        json.dump(design.layout, fh, indent=1, default=float)
    with open(os.path.join(out, "print_plan.md"), "w", encoding="utf-8") as fh:
        fh.write(print_plan(design, rows))
    return rows


ROLE_TITLES = {
    "playfield": "Playing surface", "frame": "Box and frame",
    "ramp": "Ball-return ramp", "rail": "Rails and cushions",
    "play": "Playing pieces", "mount": "Desk mounting", "cue": "Cues",
    "test": "Fit-test coupon",
}


def print_plan(design: T.Design, rows) -> str:
    spec, d = design.spec, design.dims
    pr, mat = spec.printer, spec.material
    smooth = [r for r in rows if r["plate"] == "smooth"]
    total_cm3 = sum(r["filament_cm3"] * r["qty"] for r in rows)
    out = [
        f"# Print plan - {pr.name}",
        "",
        f"- Table size: **{spec.size.name}** (ball {d.ball:.3f} mm, 1:{1 / d.scale:.2f})",
        f"- Variant: **{spec.variant}**"
        + ("  - one filament, no colour changes" if spec.variant == "simple" else ""),
        f"- Filament: **{mat.name}**, nozzle {mat.nozzle_temp} C / bed {mat.bed_temp} C",
        f"- Layer height {pr.layer:.2f} mm, {pr.nozzle:.1f} mm nozzle",
        f"- {len(rows)} files, {sum(r['qty'] for r in rows)} pieces, "
        f"roughly **{total_cm3 * 1.24:.0f} g** of filament at the walls and "
        "infill below (an estimate - the slicer is the authority)",
        "",
        "## Before you start",
        "",
        f"- **{mat.name}**: {mat.notes}",
        f"- **{pr.name}**: {pr.notes}" if pr.notes else "",
        "- Every STL is already rotated so a large flat face is on the plate. "
        "**Do not let the slicer auto-orient them.**",
        "- `orientation: diagonal` in `parts.csv` means the part only fits when "
        "turned 45 degrees on the plate; the slicer's arrange will usually do it, "
        "but check nothing is red before you send it.",
    ]
    if smooth:
        out += [
            "",
            f"## Plate change ({len(smooth)} file(s) need a smooth plate)",
            "",
            "You asked for `--felt 0`, so the printed surface *is* the playing "
            f"surface. These parts print face down: use the {pr.smooth_plate} for "
            f"them and the {pr.textured_plate} for everything else. Print them "
            "face up with ironing instead if you have only a textured plate.",
            "",
        ] + [f"- `{r['file']}`" for r in smooth]
    else:
        out += [
            "",
            "## Plates",
            "",
            f"One plate for the lot - the {pr.textured_plate} it came with is "
            "fine. The playfield tiles print face down so the playing surface "
            "comes off the plate dead flat, and the felt goes over it, so the "
            "plate's texture does not matter. (With `--felt 0` you would want a "
            "smooth plate for those tiles.)",
        ]
    out += ["", "## Settings by group", ""]
    for role in [r for r in ROLE_TITLES if any(x["role"] == r for x in rows)]:
        group = [r for r in rows if r["role"] == role]
        out += [f"### {ROLE_TITLES[role]}", "",
                "| file | qty | material | walls | infill | plate | size (mm) | ~g | note |",
                "|---|---|---|---|---|---|---|---|---|"]
        for r in group:
            out.append(f"| `{r['file']}` | {r['qty']} | {r['material'].upper()} | "
                       f"{r['walls']} | {r['infill']}% | {r['plate']} | {r['size_mm']} | "
                       f"{r['filament_cm3'] * r['qty'] * 1.24:.0f} | {r['note']} |")
        out.append("")
    out += [
        f"## Plates (at most {len(pack_plates(design))} print jobs)",
        "",
        "`preview_plates.png` shows one workable arrangement. It is a plain "
        "shelf pack, so the slicer's own arrange will often do better - treat "
        "the count as an upper bound.",
        "",
        "## Supports",
        "",
        "None. Every part is posed so nothing overhangs more than 45 degrees - "
        "the skittle caps and the ledge strips are drawn that way on purpose. "
        "If your slicer wants to add supports, the part is in the wrong "
        "orientation.",
        "",
    ]
    return "\n".join(x for x in out if x is not None) + "\n"


# ------------------------------------------------------------------ report
def report(design: T.Design, rows) -> str:
    spec, d = design.spec, design.dims
    w, l, h = design.footprint
    lines = [
        f"{spec.printer.name}  |  {spec.material.name}  |  "
        f"{spec.size.name} ({spec.variant})",
        f"ball {d.ball:.3f} mm   scale 1:{1 / d.scale:.2f}   "
        f"playing area {d.width:.0f} x {d.length:.0f} mm   hole {d.hole_open:.1f} mm",
    ]
    if design.layout.get("coupon"):
        lines.append("FIT-TEST COUPON - print this before the table")
    else:
        lines.append(f"overall {w:.0f} x {l:.0f} x {h:.0f} mm on the desk "
                     "(incl. clamp flanges)")
        lines.append(f"playfield tiles: {len(design.cuts['playfield_x']) - 1} x "
                     f"{len(design.cuts['playfield_y']) - 1}")
    diag = sum(1 for r in rows if r["orientation"] == "diagonal")
    vol = sum(r["filament_cm3"] * r["qty"] for r in rows)
    lines.append(f"{len(rows)} STL files, {sum(r['qty'] for r in rows)} pieces, "
                 f"~{vol * 1.24:.0f} g of filament"
                 + (f", {diag} must be turned 45 deg" if diag else ""))
    plates = pack_plates(design)
    per_material = {}
    for material, items in plates:
        per_material[material] = per_material.get(material, 0) + 1
    lines.append("at most " + ", ".join(f"{k} plate(s) of {m.upper()}"
                                        for m, k in per_material.items())
                 + " to print")
    return "\n".join(lines)


def fit_report(args) -> str:
    """Which sizes and variants this printer can actually manage."""
    base = spec_from(args)
    pr = base.printer
    out = [f"{pr.name}  bed {pr.bed[0]:.0f} x {pr.bed[1]:.0f} x {pr.height:.0f} mm, "
           f"usable {pr.usable[0]:.0f} x {pr.usable[1]:.0f} mm", ""]
    for key, sz in P.SIZES.items():
        for variant in ("simple", "full"):
            spec = dataclasses.replace(base, size=sz, ball=None, cord=None, variant=variant,
                                       cues=1 if variant == "simple" else 2)
            try:
                rows = measure(T.design(spec))
            except SystemExit as exc:
                out.append(f"  {key:<9} {variant:<7} NO   {exc}")
                continue
            diag = sum(1 for r in rows if r["orientation"] == "diagonal")
            out.append(f"  {key:<9} {variant:<7} ok   {len(rows):>3} files, "
                       f"{sum(r['qty'] for r in rows):>3} pieces"
                       + (f", {diag} turned 45 deg" if diag else ""))
    out += ["", "`--size` picks a row. Bigger is nicer to play on; smaller is a "
            "lot less filament and a lot less waiting."]
    return "\n".join(out)


def main(argv=None) -> int:
    args = parser().parse_args(argv)
    if args.list:
        print(P.catalogue())
        return 0
    if args.fit:
        print(fit_report(args))
        return 0
    design = build(args)
    rows = export(design, args.out)
    print(report(design, rows))
    print(f"-> {args.out}/  (parts.csv, print_plan.md, layout.json)")
    if not design.layout.get("coupon"):
        print("tip: `python barbilliards.py --coupon` first - it is an hour, not two days")
    return 0


if __name__ == "__main__":
    sys.exit(main())
