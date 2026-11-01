#!/usr/bin/env python3
"""Printer, filament and table-size profiles.

Data, not geometry. Everything the generator needs to know about *where* a
part will be printed and *what* it will be printed in lives here, so adding
a machine or a filament is a dict entry rather than a code change.

`Printer` answers "will this part fit, and how should it be sliced?".
`Material` answers "how big a gap do two parts need to slide together?".
`Size`     answers "how big is the table?" (one bought ball + one bought cord).
"""
from __future__ import annotations

import math
from dataclasses import dataclass


# --------------------------------------------------------------- printers
@dataclass(frozen=True)
class Printer:
    key: str
    name: str
    bed: tuple[float, float]          # usable plate, mm (x, y)
    height: float                     # max object height, mm
    edge_margin: float = 8.0          # keep-off at each edge (brim, skirt, clips)
    nozzle: float = 0.4
    layer: float = 0.2
    enclosed: bool = False
    square_bed: bool = True           # may a long part be turned 45 degrees?
    smooth_plate: str = "smooth PEI / glass"
    textured_plate: str = "textured PEI"
    notes: str = ""

    # -- plate geometry ---------------------------------------------------
    @property
    def usable(self) -> tuple[float, float]:
        return (self.bed[0] - 2 * self.edge_margin, self.bed[1] - 2 * self.edge_margin)

    @property
    def max_tile(self) -> float:
        """Largest edge of a part that must sit square on the plate."""
        return min(self.usable)

    def max_strip(self, cross: float) -> float:
        """Longest a strip `cross` mm wide can be and still fit the plate.

        Long thin parts (walls, rails) are turned 45 degrees on a square bed,
        which buys a lot of length; on a rectangular bed they stay square to
        the axes and the long side of the plate is the limit.
        """
        ux, uy = self.usable
        if not self.square_bed:
            return max(ux, uy) if cross <= min(ux, uy) else min(ux, uy)
        u = min(ux, uy)
        if cross >= u:
            return u
        return u * math.sqrt(2) - cross

    def fits(self, ext) -> str | None:
        """How a part with bounding box `ext` fits the plate, or None."""
        ux, uy = self.usable
        if ext[2] > self.height:
            return None
        a, b = sorted(ext[:2], reverse=True)
        if (a <= ux and b <= uy) or (a <= uy and b <= ux):
            return "straight"
        if self.square_bed and b <= min(ux, uy) and (a + b) / math.sqrt(2) <= min(ux, uy):
            return "diagonal"
        return None

    # -- slicing ----------------------------------------------------------
    def quantise(self, mm: float) -> float:
        """Round a vertical dimension to a whole number of layers."""
        return round(mm / self.layer) * self.layer

    @property
    def min_wall(self) -> float:
        """Thinnest wall worth printing: two perimeters."""
        return 2 * self.nozzle


PRINTERS: dict[str, Printer] = {
    "p1s": Printer(
        "p1s", "Bambu Lab P1S", bed=(256, 256), height=256, edge_margin=8,
        nozzle=0.4, layer=0.2, enclosed=True, square_bed=True,
        notes="Enclosed, so PETG/ABS/ASA are options as well as the default "
              "PLA. One nozzle, so one colour per plate unless an AMS is "
              "fitted - which is why `--variant simple` is the default. The "
              "textured PEI plate it ships with is all you need.",
    ),
    "p1p": Printer(
        "p1p", "Bambu Lab P1P", bed=(256, 256), height=256, edge_margin=8,
        nozzle=0.4, layer=0.2, enclosed=False, square_bed=True,
        notes="Same plate as the P1S but open-frame: stick to PLA/PETG.",
    ),
    "x1c": Printer(
        "x1c", "Bambu Lab X1 Carbon", bed=(256, 256), height=256, edge_margin=8,
        nozzle=0.4, layer=0.2, enclosed=True, square_bed=True,
        notes="As the P1S, plus lidar first-layer inspection.",
    ),
    "a1": Printer(
        "a1", "Bambu Lab A1", bed=(256, 256), height=256, edge_margin=8,
        nozzle=0.4, layer=0.2, enclosed=False, square_bed=True,
        notes="Bed slinger: slow the long playfield tiles down or they ring.",
    ),
    "a1mini": Printer(
        "a1mini", "Bambu Lab A1 mini", bed=(180, 180), height=180, edge_margin=8,
        nozzle=0.4, layer=0.2, enclosed=False, square_bed=True,
        notes="Small plate; expect roughly twice as many pieces.",
    ),
    "mk4": Printer(
        "mk4", "Prusa MK4 / MK3S", bed=(250, 210), height=210, edge_margin=8,
        nozzle=0.4, layer=0.2, enclosed=False, square_bed=False,
        notes="Rectangular plate, so long parts cannot be turned 45 degrees.",
    ),
    "ender3": Printer(
        "ender3", "Creality Ender 3 (and friends)", bed=(220, 220), height=250,
        edge_margin=10, nozzle=0.4, layer=0.2, enclosed=False, square_bed=True,
        notes="Generous edge margin because the plate clips get in the way.",
    ),
}


# --------------------------------------------------------------- materials
@dataclass(frozen=True)
class Material:
    key: str
    name: str
    fit_clearance: float              # gap for a part that must slide/drop in
    nozzle_temp: int
    bed_temp: int
    needs_enclosure: bool = False
    notes: str = ""


MATERIALS: dict[str, Material] = {
    "pla": Material(
        "pla", "PLA", fit_clearance=0.30, nozzle_temp=220, bed_temp=60,
        notes="The default. Stiff, flat and cheap, which is what the playfield "
              "wants. Don't leave the table in a sunny window or a hot car.",
    ),
    "petg": Material(
        "petg", "PETG", fit_clearance=0.40, nozzle_temp=240, bed_temp=80,
        notes="Tougher and less brittle than PLA: the better choice for the "
              "desk clamps, which get bent every time you mount the table.",
    ),
    "asa": Material(
        "asa", "ASA / ABS", fit_clearance=0.45, nozzle_temp=260, bed_temp=95,
        needs_enclosure=True,
        notes="Only on an enclosed printer. Warps on the big flat tiles; "
              "use a brim and leave the door shut until the plate is cold.",
    ),
}


# ------------------------------------------------------------------- sizes
@dataclass(frozen=True)
class Size:
    key: str
    name: str
    ball: float                       # bought ball diameter, mm
    cord: float                       # bought silicone cord diameter, mm
    blurb: str = ""

    @property
    def scale(self) -> float:
        """Against a real 1 7/8 in (47.6 mm) bar billiards ball."""
        return self.ball / 47.6


SIZES: dict[str, Size] = {
    "mini": Size(
        "mini", "Mini", ball=9.525, cord=2.0,
        blurb="3/8 in balls, ~1:5 scale, roughly 200 x 360 mm on the desk. "
              "The recommended first build: about half the filament and half "
              "the print time of the standard table, and everything that can "
              "go wrong still goes wrong at this size.",
    ),
    "standard": Size(
        "standard", "Standard", ball=12.7, cord=3.0,
        blurb="1/2 in balls, ~1:3.75 scale, roughly 270 x 460 mm. The nicest "
              "one to actually play on.",
    ),
    "large": Size(
        "large", "Large", ball=15.875, cord=4.0,
        blurb="5/8 in balls, ~1:3 scale, roughly 330 x 570 mm. Needs most of "
              "a desk and a lot of filament.",
    ),
}


# ------------------------------------------------------------------ lookup
def printer(key: str) -> Printer:
    return _pick(PRINTERS, key, "printer")


def material(key: str) -> Material:
    return _pick(MATERIALS, key, "material")


def size(key: str) -> Size:
    return _pick(SIZES, key, "size")


def _pick(table, key, what):
    try:
        return table[key.lower()]
    except KeyError:
        raise SystemExit(f"unknown {what} {key!r}; try one of: {', '.join(table)}")


def catalogue() -> str:
    """Human-readable list of everything on offer (barbilliards.py --list)."""
    out = ["printers:"]
    for p in PRINTERS.values():
        out.append(f"  {p.key:<8} {p.name:<28} {p.bed[0]:.0f} x {p.bed[1]:.0f} x {p.height:.0f} mm"
                   f"{'  enclosed' if p.enclosed else ''}")
    out.append("materials:")
    for m in MATERIALS.values():
        out.append(f"  {m.key:<8} {m.name:<28} fit gap {m.fit_clearance:.2f} mm, "
                   f"{m.nozzle_temp}/{m.bed_temp} C")
    out.append("sizes:")
    for s in SIZES.values():
        out.append(f"  {s.key:<8} {s.name:<28} ball {s.ball:.3f} mm, cord {s.cord:.1f} mm, "
                   f"1:{1 / s.scale:.2f}")
    return "\n".join(out)
