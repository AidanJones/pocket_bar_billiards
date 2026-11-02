#!/usr/bin/env python3
"""The same table, built in wood: cut list, marking out and a build guide.

    python woodwork.py                        # -> wood/ + previews/wood_plan.png
    python woodwork.py --size standard        # takes every barbilliards.py option
    python woodwork.py --ball 47.6 --cord 10  # a full-size league table

The play is not redesigned here. Everything a ball touches or needs room
for - the playing area, the holes and where they are, the cushion height,
the headroom under the bed, the slope of the return, the tray, the gate's
gaps, the skittle spots - comes from `table.Dims` and `table.design()`, the
one model. What changes is how it is built: sheet and strip thicknesses
picked from what a timber merchant sells, holes from the drill bits and
hole saws you can buy, a hardboard ramp on tapered bearers instead of
printed wedges, and rails ripped from hardwood. So the wooden table plays
exactly like the printed one of the same size.

The small parts stay printed (skittles, cue tip and butt, scoreboard) or
bought (balls, cord); see the guide this writes.

Nothing here touches files except `main()`; `check.py` builds a `Wood` and
applies `rules()` to it.
"""
from __future__ import annotations

import csv
import math
import os
from dataclasses import dataclass

import barbilliards as bb
import table as T

#: Sheet thicknesses a timber merchant stocks (birch ply, MDF), mm.
SHEETS = (3.0, 6.0, 9.0, 12.0, 15.0, 18.0)
#: A full sheet, and a quarter of one (what most merchants will cut to).
FULL_SHEET = (2440.0, 1220.0)
#: Forstner bits (to 35 mm) and hole saws above that, mm.
BITS = tuple(range(8, 31)) + (32, 35, 38, 40, 45, 50, 51, 54, 57, 60, 64, 67, 70, 76)
#: A bed resting on the frame and battens needs a little room; ply moves.
WOOD_GAP = 1.0


def _sheet(at_least: float) -> float:
    """The thinnest stocked sheet at least this thick (the thickest if none)."""
    return next((t for t in SHEETS if t >= at_least), SHEETS[-1])


def _bit(at_least: float) -> float:
    return next((b for b in BITS if b >= at_least), math.ceil(at_least))


@dataclass
class Cut:
    name: str
    qty: int
    stock: str                    # what it is cut from
    t: float                      # thickness
    w: float                      # width (across the grain, or the short side)
    length: float
    note: str = ""


class Wood:
    """A wooden build of `design`: thicknesses, stations and the cut list.

    Same frame as the printed table: X across (0 = centreline), Y along
    (0 = front cushion nose, +Y away from the player), Z up (0 = desk).
    """

    def __init__(self, design: T.Design):
        self.design = design
        d = self.d = design.dims
        B = self.ball = d.ball

        # -- stock: what drives each thickness ----------------------------
        # The bed must stay flat across its width with nine holes in it, and
        # the frame must hold it: both scale with the ball, within what is
        # sold. The ramp only carries balls; hardboard does.
        self.bed_t = _sheet(max(6.0, 0.4 * B))
        self.wall_t = _sheet(max(6.0, 0.5 * B))
        self.ramp_t = 3.0 if B < 30 else 6.0
        self.gate_t = 3.0 if B < 30 else 6.0
        self.batten = self.wall_t                     # square ledge battens
        # A rail covers the wall top and laps onto the bed by at least half
        # a ball, so it can be glued down to both.
        self.rail_w = math.ceil(max(1.2 * B, self.wall_t + WOOD_GAP + 0.6 * B))
        self.rail_h = d.rail_h
        self.bit = _bit(max(d.hole_open, B + 1.5))
        self.groove_w = math.ceil(d.cord * 2) / 2     # nearest 0.5 mm at or over the cord
        self.groove_depth = d.cord / 2 + 0.2           # half buried, as printed
        # Rails sit on the bare bed and the felt butts up to them, as on the
        # printed table, so the groove is measured from the bed top.
        self.groove_z = d.cush_z - d.zt                # above the rail's underside

        # -- across: rail over the wall, bed inside the walls ---------------
        self.x_face = d.x_face                          # cushion face (cord half buried)
        self.xo = self.x_face + self.rail_w             # outside of the walls
        self.xi = self.xo - self.wall_t
        self.p = self.xi - WOOD_GAP                     # bed half width

        # -- along: front rail over the front beam, back rail over the back wall
        self.y_fb0 = -d.cord / 2 - self.rail_w          # front beam, front face
        self.y_fb1 = self.y_fb0 + self.wall_t
        self.y_pf0 = self.y_fb1 + WOOD_GAP              # bed, front edge
        self.y_bw1 = d.length + d.cord / 2 + self.rail_w
        self.y_bw0 = self.y_bw1 - self.wall_t
        self.y_pf1 = self.y_bw0 - WOOD_GAP
        self.slot = self.gate_t + WOOD_GAP              # the gate drops in here
        self.y_ap1 = self.y_fb0 - self.slot             # apron, back face
        self.y_ap0 = self.y_ap1 - self.wall_t
        self.y_lip1 = self.y_ap0 - d.tray               # tray, inside of the lip
        self.y_lip0 = self.y_lip1 - self.wall_t         # front of the table

        # -- up: ramp on bearers, the ball's headroom, then the bed ---------
        self.tan = math.tan(math.radians(d.slope))
        self.zp = self.ramp_z(self.y_bw0) + d.under     # bed underside
        self.zt = self.zp + self.bed_t                  # playing surface (bare)
        # The beams hang below the bed for stiffness, but never into the
        # ball's way: as deep as the frame stock, less if headroom is short.
        clear = self.zp - self.ramp_z(self.y_fb0) - (B + 3.0)
        self.beam_drop = max(0.0, min(self.wall_t, clear))
        self.lip_h = self.ramp_t + 0.8 * B + 3.0
        self.g_bot = self.ramp_z(self.y_ap1) + 1.0      # gate clears the ramp
        self.g_top = self.zt + self.rail_h + max(10.0, 0.6 * B)   # a grip above the rails
        self.g_w = 2 * self.xi - 2 * WOOD_GAP
        self.bearer_h1 = self.ramp_z(self.y_bw0) - self.ramp_t   # tall end of a bearer
        inner = 2 * self.xi - 2 * self.batten
        span = 50 * self.ramp_t                         # hardboard sags past ~50 x its thickness
        self.bearers = 2 + max(0, math.ceil(inner / span) - 1)

    def ramp_z(self, y: float) -> float:
        """Top of the ramp board at Y: it lies on the desk at the lip, then rises."""
        return self.ramp_t + max(0.0, y - self.y_lip1) * self.tan

    # ------------------------------------------------------------ outputs
    @property
    def size(self):
        """Footprint on the desk and height to the rail tops, mm."""
        return (2 * self.xo, self.y_bw1 - self.y_lip0, self.zt + self.rail_h)

    def marks(self):
        """Hole centres and spots, from the bed board's front-left corner."""
        lay = self.design.layout
        x0, y0 = -self.p, self.y_pf0

        def at(x, y):
            return (x - x0, y - y0)
        out = [(f"hole {score}", *at(x, y)) for score, x, y in self.design.holes]
        out.append(("black skittle", *at(*lay["peg_black"])))
        for i, w in enumerate(lay["peg_white"]):
            out.append((f"white skittle {'LR'[i]}", *at(*w)))
        out.append(("D centre (baulk line)", *at(*lay["d_spot"])))
        out.append(("red spot", *at(*lay["red_spot"])))
        return out

    def cuts(self) -> list[Cut]:
        d, B = self.d, self.ball
        ply = lambda t: f"{t:g} mm birch ply"                     # noqa: E731
        bed_len = self.y_pf1 - self.y_pf0
        ramp_len = (self.y_bw0 - self.y_lip1) / math.cos(math.radians(d.slope))
        beam_h = self.zt - self.zp + self.beam_drop
        between = 2 * self.xi                          # fits between the side walls
        out = [
            Cut("bed", 1, f"{self.bed_t:g} mm MDF or birch ply", self.bed_t, 2 * self.p, bed_len,
                f"{len(self.design.holes)} holes, {self.bit:g} mm; the face that gets the felt up"),
            Cut("side wall", 2, ply(self.wall_t), self.wall_t, self.zt, self.y_bw1 - self.y_lip0,
                "full length, desk to the bed top"),
            Cut("back wall", 1, ply(self.wall_t), self.wall_t, self.zt, between,
                "between the side walls"),
            Cut("front beam", 1, ply(self.wall_t), self.wall_t, beam_h, between,
                "top flush with the bed top; balls pass under it"),
            Cut("apron", 1, ply(self.wall_t), self.wall_t, beam_h, between,
                f"{self.slot:g} mm in front of the front beam: that gap is the gate slot"),
            Cut("tray lip", 1, ply(self.wall_t), self.wall_t, self.lip_h, between,
                "front of the tray"),
            Cut("ramp", 1, f"{self.ramp_t:g} mm hardboard", self.ramp_t, between - 2 * self.batten,
                ramp_len, "smooth face up; the tray is its front end"),
            Cut("ramp bearer", self.bearers, "softwood strip", self.batten, self.bearer_h1,
                self.y_bw0 - self.y_lip1,
                f"tapered from nothing at the front to {self.bearer_h1:.1f} mm at the back"),
            Cut("side ledge", 2, "softwood strip", self.batten, self.batten,
                self.y_bw0 - self.y_fb1, "glued inside each side wall, top at the bed's underside"),
            Cut("end ledge", 2, "softwood strip", self.batten, self.batten,
                between - 2 * self.batten, "on the back wall and the back of the front beam"),
            Cut("side rail", 2, "hardwood strip", self.rail_h, self.rail_w,
                self.y_bw1 - self.y_fb0, "cord groove on the inside face; covers the wall top"),
            Cut("end rail", 2, "hardwood strip", self.rail_h, self.rail_w, 2 * self.x_face,
                "front and back; fits between the side rails"),
            Cut("foot strip", 2, "softwood strip", self.batten, d.flange,
                self.y_bw1 - self.y_lip0, "outside the foot of each side wall: clamp on these"),
            Cut("time-bar gate", 1, f"{self.gate_t:g} mm ply or acrylic", self.gate_t,
                self.g_top - self.g_bot, self.g_w,
                "drops into the slot; drill a finger hole near the top"),
        ]
        return out

    def stock(self):
        """Area of each sheet material, and length of each strip, needed."""
        sheets, strips = {}, {}
        for c in self.cuts():
            if "strip" in c.stock:
                key = f"{c.stock} {c.t:.0f} x {c.w:.0f} mm"
                strips[key] = strips.get(key, 0.0) + c.qty * c.length
            else:
                sheets[c.stock] = sheets.get(c.stock, 0.0) + c.qty * c.w * c.length
        return sheets, strips


# ------------------------------------------------------------------- rules
def rules(w: Wood, rule) -> None:
    """The design rules (AGENTS.md section 6) restated for the wooden build.

    `rule(ok, message)` is check.Checker.rule. The play rules on the model
    itself (hole spacing, skittles, cushion height) are checked once, on
    the design; these are the ones the change of material can break.
    """
    d, B = w.d, w.ball
    rule(w.bit >= B + 1.5, f"wood: {w.bit:g} mm bit is at least ball + 1.5")
    rule(w.bit <= 1.35 * B + 2, f"wood: {w.bit:g} mm bit is not a sinkhole (<= 1.35 x ball)")
    for score, x, y in w.design.holes:
        x_edge = w.p - abs(x) - w.bit / 2
        rule(x_edge >= B / 2 and y - w.bit / 2 - w.y_pf0 >= B / 2
             and w.y_pf1 - y - w.bit / 2 >= B / 2,
             f"wood: {score:>3} hole leaves wood round it in the bed")
        gap = w.zp - w.ramp_z(y)
        if gap < B + 3:
            rule(False, f"wood: {score:>3} hole has only {gap:.1f} mm under the bed")
    rule(w.zp - w.ramp_z(w.y_bw0) >= B + 3,
         f"wood: {w.zp - w.ramp_z(w.y_bw0):.1f} mm headroom under the bed at the back")
    under_beam = w.zp - w.beam_drop - w.ramp_z(w.y_fb0)
    rule(under_beam >= B + 3, f"wood: ball passes under the front beam ({under_beam:.1f} mm)")
    rule(w.lip_h - w.ramp_t >= 0.8 * B, "wood: the tray lip holds a ball")
    rule(w.g_w / 2 < w.xi and w.xi - w.g_w / 2 < B / 2, "wood: gate side gaps < half a ball")
    rule(w.g_bot - w.ramp_z(w.y_ap1) < B / 2, "wood: gate bottom gap < half a ball")
    rule(w.slot - w.gate_t < B / 2, "wood: the gate slot is not a ball-sized gap")
    rule(w.g_top > w.zt + w.rail_h, "wood: the gate's grip stands above the rails")
    lap = w.rail_w - w.wall_t - WOOD_GAP
    rule(lap >= 0.5 * B, f"wood: rails lap {lap:.1f} mm onto the bed, enough to glue")
    rule(w.groove_w >= d.cord, "wood: cord groove is not narrower than the cord")
    rule(w.groove_z + w.groove_w / 2 <= w.rail_h - 1.0,
         "wood: cord groove sits inside the rail with wood above it")
    nose = d.cush_z - d.zt - d.felt
    rule(0.60 * B <= nose <= 0.70 * B, f"wood: cushion nose {nose / B:.2f} x ball above the felt")
    rule(w.bed_t <= SHEETS[-1] and w.wall_t <= SHEETS[-1], "wood: every sheet is a stocked thickness")
    big = max(w.cuts(), key=lambda c: c.w * c.length)
    rule(max(big.w, big.length) <= FULL_SHEET[0] and min(big.w, big.length) <= FULL_SHEET[1],
         f"wood: the biggest panel ({big.name}) comes out of one {FULL_SHEET[0]:.0f} x "
         f"{FULL_SHEET[1]:.0f} sheet")
    rule(w.bearer_h1 > 0, "wood: the ramp bearers have height at the back")


# ------------------------------------------------------------------ output
def cut_list_csv(w: Wood, path: str) -> None:
    with open(path, "w", newline="") as f:
        out = csv.writer(f)
        out.writerow(["part", "qty", "stock", "thickness_mm", "width_mm", "length_mm", "note"])
        for c in w.cuts():
            out.writerow([c.name, c.qty, c.stock, f"{c.t:.1f}", f"{c.w:.1f}", f"{c.length:.1f}",
                          c.note])


def guide(w: Wood) -> str:
    """The build guide, as Markdown."""
    d, B, spec = w.d, w.ball, w.design.spec
    sx, sy, sz = w.size
    sheets, strips = w.stock()
    felt_in_x = w.p - w.x_face
    felt_in_y = -d.cord / 2 - w.y_pf0
    lines = [
        f"# Desk bar billiards in wood - {spec.size.name if spec.ball == spec.size.ball else 'custom'}"
        f" ({B:.2f} mm balls)",
        "",
        "Generated by `python woodwork.py` from the same model as the printed table:",
        "the playing area, holes, cushion height, return and gate are identical, so",
        "it plays the same. Only the construction is different. Measurements are",
        "millimetres. Re-run with your own `--size`, `--ball` or `--cord` rather",
        "than scaling these numbers by hand.",
        "",
        "![plan and section](../previews/wood_plan.png)",
        "",
        "## At a glance",
        "",
        "| | |",
        "|---|---|",
        f"| Ball | {B:.2f} mm (scale 1:{1 / d.scale:.2f}) |",
        f"| Playing area | {d.width:.0f} x {d.length:.0f} mm |",
        f"| On the desk | {sx:.0f} x {sy:.0f} mm, {sz:.0f} mm to the rail tops |",
        f"| Holes | {w.bit:g} mm ({'Forstner bit' if w.bit <= 35 else 'hole saw'}) |",
        f"| Bed | {w.bed_t:g} mm, {d.under:.0f} mm of room for the balls under it |",
        f"| Return | {d.slope:g} degrees, shared tray at the player's end |",
        "",
        "## Buy",
        "",
        "| Material | How much |",
        "|---|---|",
    ]
    for stock, area in sheets.items():
        lines.append(f"| {stock} | {area / 1e6:.2f} m² of parts (buy a piece with room to spare) |")
    for stock, length in strips.items():
        lines.append(f"| {stock} | {length / 1000:.2f} m |")
    lines += [
        f"| Silicone cord, {d.cord:g} mm | {2 * (d.width + d.length) / 1000 + 0.1:.1f} m (cushions) |",
        f"| Balls, {B:.2f} mm | 7 white + 1 red |",
        "| Felt (billiard cloth, or craft felt) | the playing area plus 20 mm all round |",
        "| Wood glue, spray adhesive for the felt, a few panel pins | |",
        "",
        "The skittles, the cue tip and butt, and the scoreboard are small enough to",
        f"print: `python barbilliards.py --size {spec.size.key}` (or the same `--ball`)",
        "writes `skittle.stl`, `cue_*.stl` and `score_*.stl`. To turn the skittles",
        f"instead: {d.peg_h:.1f} mm tall, a {d.peg_cap:.1f} mm cap whose rim is {d.peg_rim:.1f} mm up",
        f"(a ball must roll under it), on a {d.peg_base:.1f} mm base. Keep them light so",
        "they fall when touched.",
        "",
        "## Tools",
        "",
        f"- A saw that cuts straight (table saw or track saw; a fine handsaw and a guide at this size{'' if B < 30 else ' is hard work'})",
        f"- A {w.bit:g} mm {'Forstner bit' if w.bit <= 35 else 'hole saw'} and a drill stand or a guide block - the holes must be square",
        f"- A {w.groove_w:g} mm groove: a straight router bit, or saw kerfs, for the cord",
        "- Clamps, a square, a sharp knife for the felt",
        "",
        "## Cut list",
        "",
        "Width is the short side of a panel; for strips it is thickness x width.",
        "",
        "| Part | Qty | Stock | Thickness | Width | Length | Note |",
        "|---|---|---|---|---|---|---|",
    ]
    for c in w.cuts():
        lines.append(f"| {c.name} | {c.qty} | {c.stock} | {c.t:.1f} | {c.w:.1f} | "
                     f"{c.length:.1f} | {c.note} |")
    lines += [
        "",
        "Also in `wood/cut_list.csv`.",
        "",
        "## Marking out the bed",
        "",
        "From the bed's **front-left corner** (the player's end, on your left), with",
        "the felt face up. Mark centres with an awl, then drill.",
        "",
        "| Mark | Across (X) | Along (Y) |",
        "|---|---|---|",
    ]
    for name, x, y in w.marks():
        lines.append(f"| {name} | {x:.1f} | {y:.1f} |")
    lines += [
        "",
        "Or use the 1:1 template, `previews/felt_template_A4.pdf` (from",
        f"`python render.py --size {spec.size.key}`): its outline is the cushion line, so",
        f"set it {felt_in_x:.1f} mm in from each side edge and {felt_in_y:.1f} mm in from the",
        "front edge, and prick through the centres.",
        "",
        "## Build",
        "",
        f"1. **Bed.** Drill the nine holes at {w.bit:g} mm, square to the face, with",
        "   scrap clamped underneath so the exit does not tear out. Ease the top",
        "   edge of each hole with fine paper - a sharp edge throws the ball off.",
        f"2. **Rails.** Rip them {w.rail_w:.0f} mm wide and {w.rail_h:.1f} mm tall. Cut the cord",
        f"   groove in the inside face: {w.groove_w:g} mm wide, {w.groove_depth:.1f} mm deep,",
        f"   centred {w.groove_z:.1f} mm above the rail's underside. Cut the end rails",
        "   to fit between the side rails.",
        "3. **Frame.** Glue the back wall between the side walls at the far end,",
        "   then the front beam, the apron (with a strip of the gate stock as a",
        f"   spacer, so the slot is {w.slot:g} mm), and the tray lip. Check it is square.",
        f"4. **Ramp.** Taper the {w.bearers} bearers from nothing at the front to",
        f"   {w.bearer_h1:.1f} mm at the back - a straight line, which is the {d.slope:g} degree",
        "   slope. Stand them on the desk inside the frame, one glued against each",
        "   side wall" + (", the rest evenly between" if w.bearers > 2 else "")
        + ", and glue the hardboard on top,",
        "   smooth face up, butting against the back wall.",
        f"5. **Ledges.** Glue the side and end ledges so their tops are {w.zp:.1f} mm",
        "   above the desk - the underside of the bed. Use a block cut to that",
        "   height as a gauge rather than a ruler.",
        "6. **Felt.** Spray-glue the felt to the bed, trimmed to the cushion line",
        f"   ({felt_in_x:.1f} mm in from the sides, {felt_in_y:.1f} mm from the front edge): the",
        "   rails sit on the bare wood outside it. Cut out each hole with a sharp",
        "   knife from below, following the wood.",
        "7. **Bed in.** Lay the bed on the ledges and drop a ball through every",
        "   hole: each should roll to the tray on its own, and stop at the gate",
        "   when it is in. Then glue the bed down, weighted flat.",
        "8. **Cushions.** Glue the cord into the grooves with a bead of silicone",
        "   or contact adhesive, stretched only enough to lie straight.",
        "9. **Rails on.** Glue the side rails over the wall tops and the bare edge",
        "   of the bed, then the end rails between them. The cord should just",
        "   touch the edge of the felt.",
        f"10. **Gate.** Cut it {w.g_w:.0f} x {w.g_top - w.g_bot:.0f} mm; it should drop into the",
        "   slot freely and stand clear of the ramp by a millimetre.",
        "11. **Desk.** Glue a foot strip along the outside bottom of each side",
        "   wall and clamp the table down with two small F-clamps on those.",
        "",
        "## Checks",
        "",
        "- Before the felt: the bed is flat. A straightedge across it in each",
        "  direction shows no light; shim the ledges if not.",
        "- Before gluing the bed (step 7): every hole returns a ball to the tray.",
        "- Last: a ball rolled gently into each cushion comes back off it, and",
        "  one played firmly does not jump the rail.",
        "",
        "Rules of play: `README.md` section 7.",
        "",
    ]
    return "\n".join(lines)


def drawing(w: Wood, path: str) -> None:
    """Plan of the bed (marking out), a section along the table (heights),
    and the player's end drawn larger (tray, gate slot, front beam)."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.patches import Circle, Polygon, Rectangle

    d, B = w.d, w.ball
    fig = plt.figure(figsize=(14, 9))
    grid = fig.add_gridspec(2, 2, width_ratios=[1.0, 1.7], height_ratios=[1.0, 1.25])
    plan = fig.add_subplot(grid[:, 0])
    whole = fig.add_subplot(grid[0, 1])
    front = fig.add_subplot(grid[1, 1])

    # -- plan: the bed board, from its front-left corner --------------------
    bw, bl = 2 * w.p, w.y_pf1 - w.y_pf0
    plan.add_patch(Rectangle((0, 0), bw, bl, fc="#e9d8b8", ec="#6b4a2b", lw=1.2))
    plan.add_patch(Rectangle((w.p - w.x_face, -d.cord / 2 - w.y_pf0), 2 * w.x_face,
                             d.length + d.cord, fc="#2f6b3a", ec="none", alpha=0.35))
    small = bl / 60
    for name, x, y in w.marks():
        if name.startswith("hole"):
            plan.add_patch(Circle((x, y), w.bit / 2, fc="#1b2a1e", ec="k", lw=0.6))
            plan.text(x, y + w.bit / 2 + small * 0.3, name[5:], ha="center", va="bottom",
                      fontsize=7, fontweight="bold")
            # Below the hole, unless a skittle spot sits there (the 200's black).
            crowded = any(not n.startswith("hole") and abs(sx - x) < w.bit
                          and 0 < y - sy < 2.5 * w.bit for n, sx, sy in w.marks())
            if crowded:
                plan.text(x - w.bit / 2 - small * 0.4, y, f"{x:.1f}\n{y:.1f}", ha="right",
                          va="center", fontsize=5.5)
            else:
                plan.text(x, y - w.bit / 2 - small * 0.3, f"{x:.1f}\n{y:.1f}", ha="center",
                          va="top", fontsize=5.5)
        else:
            plan.plot([x], [y], "o", ms=3, color="#c0392b" if "red" in name else "k")
            # Off to the side away from the centre line, where the holes are.
            left = x < w.p - 1.0
            plan.annotate(f"{name}\n{x:.1f}, {y:.1f}", xy=(x, y),
                          xytext=(x + (-2.5 if left else 2.5) * small, y - 1.2 * small),
                          fontsize=5.5, va="top", ha="right" if left else "left",
                          arrowprops=dict(arrowstyle="-", lw=0.4, color="0.3"))
    plan.annotate("", xy=(0, -2 * small), xytext=(bw, -2 * small),
                  arrowprops=dict(arrowstyle="<->", lw=0.7))
    plan.text(bw / 2, -2.6 * small, f"{bw:.1f}", ha="center", va="top", fontsize=8)
    plan.annotate("", xy=(-2 * small, 0), xytext=(-2 * small, bl),
                  arrowprops=dict(arrowstyle="<->", lw=0.7))
    plan.text(-2.6 * small, bl / 2, f"{bl:.1f}", ha="right", va="center", rotation=90,
              fontsize=8)
    plan.plot([0], [0], "s", color="#c0392b", ms=6)
    plan.text(small, small, "0, 0", fontsize=7, color="#c0392b")
    plan.set_title(f"Bed: {w.bed_t:g} mm, holes {w.bit:g} mm. Centres (x, y) from the\n"
                   "front-left corner; green is the felt, player at the bottom", fontsize=9)
    plan.set_xlim(-6 * small, bw + 4 * small)
    plan.set_ylim(-6 * small, bl + 2 * small)
    plan.set_aspect("equal")
    plan.axis("off")

    # -- the section, drawn twice: all of it, then the player's end -----------
    def section(ax, label_heights):
        def box(y0, y1, z0, z1, fc):
            ax.add_patch(Rectangle((y0, z0), y1 - y0, z1 - z0, fc=fc, ec="#333", lw=0.6))
        ax.add_patch(Rectangle((w.y_lip0 - 40, -3), w.y_bw1 - w.y_lip0 + 80, 3, fc="#bbb",
                               ec="none"))
        ax.add_patch(Polygon([(w.y_lip1, 0), (w.y_bw0, 0), (w.y_bw0, w.bearer_h1)],
                             fc="#d9b77e", ec="#333", lw=0.5))
        ax.add_patch(Polygon([(w.y_lip1, 0), (w.y_bw0, w.bearer_h1),
                              (w.y_bw0, w.ramp_z(w.y_bw0)), (w.y_lip1, w.ramp_t)],
                             fc="#8b6b45", ec="#333", lw=0.5))
        box(w.y_pf0, w.y_pf1, w.zp, w.zt, "#e9d8b8")
        for score, x, y in w.design.holes:
            if abs(x) < 1e-6:
                ax.add_patch(Rectangle((y - w.bit / 2, w.zp - 0.3), w.bit, w.bed_t + 0.6,
                                       fc="white", ec="none"))
        box(w.y_lip0, w.y_lip1, 0, w.lip_h, "#c8a26e")
        box(w.y_ap0, w.y_ap1, w.zp - w.beam_drop, w.zt, "#c8a26e")
        box(w.y_fb0, w.y_fb1, w.zp - w.beam_drop, w.zt, "#c8a26e")
        box(w.y_fb1, w.y_fb1 + w.batten, w.zp - w.batten, w.zp, "#d9b77e")
        box(w.y_bw0 - w.batten, w.y_bw0, w.zp - w.batten, w.zp, "#d9b77e")
        box(w.y_bw0, w.y_bw1, 0, w.zt, "#c8a26e")
        ax.add_patch(Rectangle((w.y_ap1 + WOOD_GAP / 2, w.g_bot), w.gate_t, w.g_top - w.g_bot,
                               fc="#c0392b", ec="#333", lw=0.5, alpha=0.9))
        box(w.y_fb0, -d.cord / 2, w.zt, w.zt + w.rail_h, "#6b4a2b")
        box(d.length + d.cord / 2, w.y_bw1, w.zt, w.zt + w.rail_h, "#6b4a2b")
        for y in (-d.cord / 2, d.length + d.cord / 2):
            ax.add_patch(Circle((y, d.cush_z), d.cord / 2, fc="#111"))
        ax.add_patch(Rectangle((-d.cord / 2, w.zt), d.length + d.cord, d.felt, fc="#2f6b3a",
                               ec="none"))
        for y, z in ((d.length * 0.3, w.zt + d.felt), (w.y_lip1 + B * 0.6, w.ramp_t),
                     (w.y_bw0 - 2 * B, w.ramp_z(w.y_bw0 - 2 * B))):
            ax.add_patch(Circle((y, z + B / 2), B / 2, fc="#f6f1e3", ec="k", lw=0.5))
        for z, text in label_heights:
            ax.axhline(z, color="0.6", lw=0.3, ls=":")
            ax.text(ax.get_xlim()[1], z, " " + text, fontsize=7, va="center")
        ax.set_aspect("equal")
        ax.axis("off")

    top = w.zt + w.rail_h
    whole.set_xlim(w.y_lip0 - 10, w.y_bw1 + 10)
    whole.set_ylim(-8, w.g_top + 8)
    section(whole, [])
    whole.set_title(f"Section along the centre line: the return slopes {d.slope:g} deg "
                    f"from the back wall to the tray", fontsize=9)
    whole.text(w.y_lip0, -6, "player", fontsize=7, va="top")

    reach = w.y_fb0 + 0.25 * (w.y_bw1 - w.y_lip0)
    front.set_xlim(w.y_lip0 - 6, reach)
    front.set_ylim(-6, w.g_top + 6)
    section(front, [(w.zt, f"bed top {w.zt:.1f}"), (w.zp, f"bed underside {w.zp:.1f}"),
                    (top, f"rail top {top:.1f}"), (d.cush_z, f"cord centre {d.cush_z:.1f}"),
                    (w.zp - w.beam_drop, f"beam bottom {w.zp - w.beam_drop:.1f}"),
                    (w.lip_h, f"lip {w.lip_h:.1f}"), (w.g_top, f"gate top {w.g_top:.1f}")])
    notes = [(w.y_lip0 + w.wall_t / 2, "lip"), ((w.y_ap0 + w.y_ap1) / 2, "apron"),
             (w.y_ap1 + w.slot / 2, f"gate in a {w.slot:g} slot"),
             ((w.y_fb0 + w.y_fb1) / 2, "front beam")]
    span = reach - (w.y_lip0 - 6)
    for i, (y, text) in enumerate(notes):
        # Fan the labels out: the slot, beam and apron are only millimetres apart.
        tx = y if i == 0 else w.y_ap0 + (i - 1.5) * 0.11 * span
        front.annotate(text, xy=(y, 1.0), xytext=(tx, -4.5), fontsize=7, ha="center",
                       va="top", arrowprops=dict(arrowstyle="-", lw=0.4, color="0.4"))
    front.set_title("The player's end, larger: tray, gate slot, front beam, cushion",
                    fontsize=9)
    sx, sy, sz = w.size
    fig.suptitle(f"Desk bar billiards in wood - ball {B:.2f} mm, "
                 f"{sx:.0f} x {sy:.0f} x {sz:.0f} mm (mm, heights from the desk)", fontsize=11)
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)


def main(argv=None) -> int:
    ap = bb.parser()
    ap.set_defaults(size="large", out="wood")
    ap.add_argument("--previews", default="previews", help="where the drawing goes")
    args = ap.parse_args(argv)
    # Nothing here is printed, so the printed parts' plate size must not get
    # in the way (a league table's bed is wider than any printer).
    args.bed = args.bed or 5000.0
    design = bb.build(args)
    w = Wood(design)
    fails = []
    rules(w, lambda ok, msg: None if ok else fails.append(msg))
    if fails:
        raise SystemExit("the wooden build breaks a rule:\n  " + "\n  ".join(fails))
    os.makedirs(args.out, exist_ok=True)
    os.makedirs(args.previews, exist_ok=True)
    cut_list_csv(w, os.path.join(args.out, "cut_list.csv"))
    with open(os.path.join(args.out, "wood_plan.md"), "w") as f:
        f.write(guide(w))
    drawing(w, os.path.join(args.previews, "wood_plan.png"))
    sx, sy, sz = w.size
    print(f"{args.out}/: cut_list.csv ({len(w.cuts())} parts), wood_plan.md;  "
          f"{args.previews}/wood_plan.png   ball {w.ball:.2f} mm, "
          f"{sx:.0f} x {sy:.0f} x {sz:.0f} mm, {w.bit:g} mm holes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
