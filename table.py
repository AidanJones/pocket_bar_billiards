#!/usr/bin/env python3
"""The bar billiards table itself: parameters in, parts out.

`design(spec)` returns a `Design` — a resolved set of dimensions, the play
layout, and a `PartList` of meshes in assembled position. It touches no
files and has no import side effects, so `check.py`, `render.py` and the
`barbilliards.py` CLI can all build one and look at it.

Geometry is assembled from `components.py`; sizes come from `profiles.py`.
Nothing here hard-codes a dimension that depends on the ball or the
printer — see AGENTS.md section 5.

Coordinate system (assembled, millimetres)
  X  across the table, 0 = centreline
  Y  along it, 0 = front cushion nose, +Y towards the far end
  Z  up, 0 = desk top.  The player stands at -Y.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

import components as C
import profiles as P


# --------------------------------------------------------------- play layout
#: Hole positions in REAL-table millimetres, measured from the front cushion
#: of a ~800 x 1420 mm league table. Edit these, never the scaled values.
REAL_LENGTH = 1420.0
REAL_WIDTH = 800.0
REAL_BALL = 47.6
REAL_HOLES = [                      # (score, x, y_from_far_cushion)
    (30, -300, 90), (20, -150, 90), (10, 0, 90), (20, 150, 90), (30, 300, 90),
    (100, 0, 330),
    (50, -250, 520), (50, 250, 520),
    (200, 0, 700),
]
REAL_WHITE_PEG_X = 178.0            # league position: either side of the 100
REAL_BAULK_Y = 300.0                # D centre, from the front cushion
REAL_D_RADIUS = 60.0
REAL_RED_OFFSET = 229.0             # red spot, forward of the baulk line
REAL_PEG_H = 80.0                   # skittle height
PEG_RIM_FRAC = 0.74                 # where the cap rim sits up the skittle

#: Traditional ring / marker colours, used only by the "full" variant.
PALETTE = {
    "playfield": "#2f6b3a", "frame": "#8a5a2b", "rail": "#5b3a1e",
    "ramp": "#c9b18a", "splice": "#999999", "gate": "#c0392b",
    "mount": "#444444", "cue": "#5b3a1e", "test": "#7f8c8d",
    "ring_10": "#f2f2f2", "ring_20": "#f2f2f2", "ring_30": "#f2f2f2",
    "ring_50": "#f2c84b", "ring_100": "#222222", "ring_200": "#c0392b",
    "skittle_black": "#222222", "skittle_white": "#f2f2f2",
}
RING_COLOUR = {10: "#f2f2f2", 20: "#f2f2f2", 30: "#f2f2f2",
               50: "#f2c84b", 100: "#222222", 200: "#c0392b"}


# ---------------------------------------------------------------------- spec
@dataclass(frozen=True)
class Spec:
    """Everything the owner chooses. `resolve()` fills in the defaults."""
    size: P.Size
    printer: P.Printer
    material: P.Material
    variant: str = "simple"           # "simple" = one colour, fewest pieces
    slope: float = 3.0                # ball-return ramp, degrees
    ball: float | None = None         # override the size's ball
    cord: float | None = None         # override the size's cushion cord
    felt: float = 1.0                 # 0 to mark the bare plastic instead
    desk: float = 25.0                # desk thickness for the simple clamp
    cues: int = 1
    colour: str = "#8a5a2b"           # the one filament, for "simple"
    sorted_return: bool = False       # one lane per hole instead of one trough

    @property
    def rings(self) -> bool:
        """Separate coloured hole collars are a "full" extra."""
        return self.variant == "full"

    def hue(self, key: str) -> str:
        return self.colour if self.variant == "simple" else PALETTE.get(key, "#c8c8c8")

    def __post_init__(self):
        object.__setattr__(self, "ball", self.ball or self.size.ball)
        object.__setattr__(self, "cord", self.cord or self.size.cord)
        if self.variant not in ("simple", "full"):
            raise SystemExit("variant must be 'simple' or 'full'")
        if self.material.needs_enclosure and not self.printer.enclosed:
            raise SystemExit(f"{self.material.name} needs an enclosed printer; "
                             f"{self.printer.name} is open-frame")
        if self.slope < 2.0:
            raise SystemExit("a slope below 2 degrees will not return balls reliably")
        if self.cues < 1:
            raise SystemExit("at least one cue, surely")


# ---------------------------------------------------------------- dimensions
class Dims:
    """Every derived dimension, computed once from a `Spec`.

    Read these; never copy a number out of here into the code.
    """

    def __init__(self, spec: Spec):
        pr, mat = spec.printer, spec.material
        self.ball = ball = spec.ball
        self.scale = s = ball / REAL_BALL
        self.cord = cord = spec.cord
        self.felt = spec.felt

        # -- playing area ------------------------------------------------
        self.width = REAL_WIDTH * s                # between cushion noses
        self.length = REAL_LENGTH * s
        self.half_width = a = self.width / 2

        # -- holes -------------------------------------------------------
        self.hole_open = max(1.20 * ball, ball + 1.8)   # the ball drops through this
        self.ring_wall = max(1.0, pr.min_wall) if spec.rings else 0.0
        self.hole_d = self.hole_open + 2 * self.ring_wall   # the cut in the playfield
        self.hole_r = self.hole_d / 2

        # -- printed-wall minimums (nozzle driven, not ball driven) ------
        self.wall = max(4.0, 8 * pr.nozzle)
        self.ledge = max(4.0, self.wall)
        self.splice_w = max(16.0, 40 * pr.nozzle)
        self.splice_t = pr.quantise(max(2.0, 5 * pr.layer))
        self.trim = max(2.4, 6 * pr.nozzle)        # generic bit of meat
        self.clr = mat.fit_clearance

        # -- desk interface (sized for a desk, so not ball driven) -------
        self.flange = 15.0
        self.flange_t = 4.0
        self.dowel = 8.0                           # bought cue dowel

        # -- slab and frame ----------------------------------------------
        self.tp = pr.quantise(max(5.0, 0.40 * ball))      # playfield thickness
        self.pf_ext = max(6.0, 0.63 * ball)               # playfield under the rails
        self.under = ball + max(6.0, 0.55 * ball)         # return-path headroom
        self.tray = max(34.0, 3.2 * ball)
        self.apron = max(8.0, 2 * self.wall)
        self.beam_drop = max(8.0, 0.63 * ball)            # beams hang below the slab
        self.gate_t = max(3.0, 7 * pr.nozzle)
        self.slot = self.gate_t + 2 * self.clr

        self.p = p = a + self.pf_ext               # playfield half width
        self.xi = xi = p + self.clr                # side wall inner face
        self.xo = xi + self.wall                   # side wall outer face

        # -- Y stations (front of the table is negative) -----------------
        self.y_pf0 = -self.pf_ext
        self.y_pf1 = self.length + self.pf_ext
        self.y_bw0 = self.y_pf1 + self.clr         # back wall inner
        self.y_bw1 = self.y_bw0 + self.wall
        self.y_fb1 = self.y_pf0 - self.clr         # front beam, playfield side
        self.y_fb0 = self.y_fb1 - self.wall       # ... and rear of the gate slot
        self.y_ap1 = self.y_fb0 - self.slot        # apron beam = front of the slot
        self.y_ap0 = self.y_ap1 - self.apron
        self.y_lip1 = self.y_ap0 - self.tray       # tray lip, inner face
        self.y_lip0 = self.y_lip1 - self.wall      # front of the whole table

        # -- ball return -------------------------------------------------
        self.slope = spec.slope
        self._tan = math.tan(math.radians(spec.slope))
        self.ramp_front = max(1.6, 0.16 * ball)
        self.zp = self.ramp_z(self.y_bw0) + self.under    # playfield underside
        self.zt = self.zp + self.tp                       # playing surface

        # -- cushions and rails ------------------------------------------
        self.cush_z = self.zt + self.felt + 0.635 * ball  # cord centre height
        self.rail_h = max((self.cush_z - self.zt) + cord / 2 + self.trim, 0.95 * ball)
        self.x_face = a + cord / 2                        # rail face (cord half buried)
        self.groove_r = cord / 2 + 0.1
        self.lip_h = self.ramp_front + 0.8 * ball + self.trim

        # -- gate ("the bar drops") --------------------------------------
        self.g_y0 = self.y_fb0 - self.clr - self.gate_t
        self.g_bot = self.ramp_z(self.g_y0) + 0.8
        self.g_w = xi - 2 * self.clr
        self.g_top = self.zt + self.rail_h
        self.g_tab = max(14.0, 1.4 * ball)

        # -- skittles ----------------------------------------------------
        self.peg_h = REAL_PEG_H * s
        self.peg_cap = max(self.hole_d + 3.0, 0.85 * REAL_PEG_H * s)
        self.peg_base = 0.5 * self.peg_cap
        self.peg_rim = PEG_RIM_FRAC * self.peg_h   # ball must pass under this

        # -- scoreboard --------------------------------------------------
        # A thing for human fingers, so it is sized by the nozzle and the hand,
        # not by the ball: the Mini's scoreboard is the Large's scoreboard.
        self.sb_rows = 3                            # hundreds, tens, units
        self.sb_steps = 10                          # 0-9 on each row
        self.sb_shaft_r = max(2.0, 5 * pr.nozzle)
        self.sb_bay_r = self.sb_shaft_r + 0.6       # a marker settles in a bay
        self.sb_neck_r = self.sb_shaft_r + 0.075    # light friction, not a snap fit
        self.sb_foot_r = self.sb_shaft_r + 1.6      # wider than a neck, so captive
        self.sb_knob_r = self.sb_shaft_r + 1.4
        # Knobs must not crowd each other, or you cannot tell which bay a
        # marker is sitting in.
        self.sb_pitch = max(9.0, 2 * self.sb_knob_r + 2.5)
        self.sb_row_pitch = max(12.0, 2 * self.sb_foot_r + 6.0)
        self.sb_back_t = pr.quantise(max(1.6, 4 * pr.layer))
        self.sb_track_t = pr.quantise(max(2.4, 6 * pr.layer))
        self.sb_face_t = pr.quantise(max(1.6, 4 * pr.layer))
        self.sb_foot_t = self.sb_track_t - 0.4      # runs free between the plates
        self.sb_knob_h = max(4.5, 22 * pr.layer)
        self.sb_track_r = self.sb_foot_r + self.clr
        self.sb_run = (self.sb_steps - 1) * self.sb_pitch
        sb_margin = max(8.0, 2 * self.sb_bay_r)   # room for the paper scale
        self.sb_w = self.sb_run + 2 * max(self.sb_bay_r, self.sb_track_r) + 2 * sb_margin
        self.sb_h = ((self.sb_rows - 1) * self.sb_row_pitch
                     + 2 * self.sb_track_r + 2 * sb_margin)

        # -- how far a tile seam must stay from a hole -------------------
        self.seam_margin = max(6.0, 0.5 * ball)

    def ramp_z(self, y: float) -> float:
        """Height of the ball-return surface at Y (it rests on the desk)."""
        return self.ramp_front + (y - self.y_lip1) * self._tan

    @property
    def overall(self):
        return dict(x0=-(self.xo + self.flange), x1=self.xo + self.flange,
                    y0=self.y_lip0, y1=self.y_bw1, z_top=self.zt + self.rail_h)


# -------------------------------------------------------------------- design
@dataclass
class Design:
    spec: Spec
    dims: Dims
    holes: list                       # [(score, x, y)] scaled
    layout: dict
    parts: C.PartList
    cuts: dict = field(default_factory=dict)

    @property
    def footprint(self):
        o = self.dims.overall
        return (o["x1"] - o["x0"], o["y1"] - o["y0"], o["z_top"])


def _hole_order(holes):
    """Holes left to right, resolving a shared centreline.

    Where several holes sit on the same X they still need separate lanes, so
    the one nearest the player takes the middle slot — nothing travels over
    it — and the others go either side of it, farthest out first.
    """
    groups = {}
    for score, x, y in holes:
        groups.setdefault(round(x, 3), []).append((score, x, y))
    ordered = []
    for x in sorted(groups):
        near_first = sorted(groups[x], key=lambda h: h[2])
        if len(near_first) == 1:
            ordered += near_first
            continue
        slot = [None] * len(near_first)
        slot[len(slot) // 2] = near_first[0]
        spare = near_first[1:][::-1]            # farthest hole to the left
        for i, taken in enumerate(slot):
            if taken is None:
                slot[i] = spare.pop(0)
        ordered += slot
    return ordered


def _blocked(x, zones):
    return any(a <= x <= b for a, b in zones)


def return_lanes(d: "Dims", holes, fin_t):
    """Give every hole its own return lane. Returns `(bounds, lanes)`.

    A lane boundary is a wall standing on the ramp, so it must never pass
    under a hole: a ball landing on its edge would go either way. Most holes
    are far enough apart that the midpoint between them is clear and the ball
    drops straight into its own lane. Where two are closer than their own
    width — the 30 and the 50 are 10 mm apart on the Mini and 11.4 mm wide —
    the boundary is pushed past one of them and a chute under that hole tips
    its ball across.

    Two rules make it work. Lanes stay in X order however the layout is
    edited, so no two ever cross, which is the whole trick: crossing channels
    cannot be built here. And a ball is only ever chuted out of a lane whose
    own hole is nearer the player, so nothing is ever travelling down that
    lane when the chute fires.

    `lanes` runs left to right: `(score, x_centre, hole_y, offset)`; a
    non-zero offset is the sideways nudge that hole's chute has to give.
    """
    ordered = _hole_order(holes)
    clear = d.hole_r + fin_t / 2 + 0.5          # a fin must miss a hole by this
    min_w = d.ball + 1.0 + fin_t                # and a ball must get down a lane
    zones = [(x - clear, x + clear) for _s, x, _y in ordered]

    # Start from the obvious thing — a boundary halfway between each pair —
    # and only move the ones that would land under a hole.
    centres = _lane_centres(d, ordered)
    bounds = [-d.xi] + [(a + b) / 2 for a, b in zip(centres, centres[1:])] + [d.xi]
    for i in range(1, len(bounds) - 1):
        if not _blocked(bounds[i], zones):
            continue
        for step in (k * 0.1 for k in range(1, int(4 * d.ball / 0.1))):
            for spot in (bounds[i] - step, bounds[i] + step):
                if _blocked(spot, zones):
                    continue
                trial = bounds[:i] + [round(spot, 2)] + bounds[i + 1:]
                if all(b - a >= min_w for a, b in zip(trial, trial[1:])):
                    bounds = trial
                    break
            else:
                continue
            break
        else:
            raise SystemExit(
                f"cannot place a return lane boundary near {bounds[i]:.1f} mm "
                "without it landing under a hole. Use --return shared, or a "
                "bigger --size.")

    lanes = []
    for i, (score, hx, hy) in enumerate(ordered):
        lo, hi = bounds[i], bounds[i + 1]
        if lo + clear <= hx <= hi - clear:
            lanes.append((score, hx, hy, 0.0))              # drops straight in
        else:
            lanes.append((score, (lo + hi) / 2, hy, (lo + hi) / 2 - hx))

    for i, (score, _x, hy, offset) in enumerate(lanes):
        if offset == 0.0:
            continue
        hx = ordered[i][1]
        j = max(k for k in range(len(bounds) - 1) if bounds[k] < hx)
        if lanes[j][2] >= hy:
            raise SystemExit(
                f"the {score} would have to be chuted across the "
                f"{lanes[j][0]} lane, which is still in use that far up the "
                "table. Use --return shared.")
    return bounds, lanes


def _lane_centres(d: "Dims", ordered):
    """Where each lane would like to sit: under its hole, or spread out when
    several holes share a centreline."""
    centres = []
    for i, (_score, x, _y) in enumerate(ordered):
        same = [k for k, h in enumerate(ordered) if abs(h[1] - x) < 1e-6]
        if len(same) == 1:
            centres.append(x)
            continue
        gap = min((abs(h[1] - x) for h in ordered if abs(h[1] - x) > 1e-6),
                  default=6 * d.hole_r)
        step = gap / max(1, len(same) - 1)
        centres.append(x + (same.index(i) - (len(same) - 1) / 2) * step)
    return centres


def _spans(lo, hi, gaps, min_len=1.0):
    """[lo, hi] with every (a, b) in `gaps` cut out, dropping stubs."""
    out = [(lo, hi)]
    for a, b in gaps:
        nxt = []
        for s0, s1 in out:
            if b <= s0 or a >= s1:
                nxt.append((s0, s1))
                continue
            if s0 < a:
                nxt.append((s0, a))
            if b < s1:
                nxt.append((b, s1))
        out = nxt
    return [(a, b) for a, b in out if b - a > min_len]


def _sorted_return(d: "Dims", spec: Spec, parts: C.PartList, holes, lay):
    """Lane walls and landing chutes for the score-sorted ball return."""
    pr = spec.printer
    fin_t = max(2.0, 5 * pr.nozzle)
    bounds, lanes = return_lanes(d, holes, fin_t)
    y_lo, y_hi = d.y_lip1 + 0.3, d.y_bw0 - 0.3
    run = 2.2 * d.ball
    rise = max(2.0, 0.35 * d.ball)

    # The chutes go in first: where one crosses a lane boundary, that fin has
    # to stand aside and let the ball through.
    gaps = {}
    for i, (score, x_lane, y_hole, offset) in enumerate(lanes):
        if offset == 0.0:
            continue
        side = 1.0 if offset > 0 else -1.0
        hx = x_lane - offset
        j = max(k for k in range(len(bounds) - 1) if bounds[k] < hx)
        # start just inside the fin on the far side of the hole it lands in,
        # and finish well inside the lane it is aiming for
        u_high = (bounds[j] + fin_t / 2 + 0.5 if side > 0
                  else bounds[j + 1] - fin_t / 2 - 0.5)
        u_low = x_lane + side * ((bounds[i + 1] - bounds[i]) / 2 - 1.5)
        y0, y1 = y_hole - run / 2, y_hole + run / 2
        parts.add(f"return_chute_{i + 1}_{score}",
                  C.cross_chute(y0, y1, u_high, u_low, d.ramp_z(y1) + 0.2, rise),
                  role="ramp", colour=spec.hue("ramp"), walls=3, infill=20,
                  note=f"glue to the ramp under the {score} hole at "
                       f"x={hx:.0f}; it tips the ball sideways into lane "
                       f"{i + 1}, the {score}")
        for k, b in enumerate(bounds):
            if min(u_high, u_low) < b < max(u_high, u_low):
                gaps.setdefault(k, []).append((y0 - fin_t, y1 + fin_t))

    tall = d.zp - (d.ramp_z(y_lo) + 0.3)
    for k, xb in enumerate(bounds[1:-1], start=1):
        piece = 0
        for a, b in _spans(y_lo, y_hi, gaps.get(k, []), min_len=3 * d.ball):
            edges = C.plan_cuts(a, b, pr.max_strip(tall))
            for c0, c1 in zip(edges, edges[1:]):
                piece += 1
                parts.add(f"lane_fin_{k}_{piece}",
                          C.lane_fin(xb - fin_t / 2, xb + fin_t / 2, c0, c1,
                                     d.ramp_z, d.zp),
                          role="ramp", colour=spec.hue("splice"), walls=3, infill=20,
                          note="stands on the ramp, trapped against the slab above; "
                               "glue along its top edge")

    lay["return_lanes"] = [
        dict(score=score, x0=round(bounds[i], 2), x1=round(bounds[i + 1], 2),
             centre=round(x, 2), chute=offset != 0.0)
        for i, (score, x, _y, offset) in enumerate(lanes)]
    return bounds, lanes


def _add_strip(parts, name, profile, lo, hi, plane, max_len, note="", **kw):
    """Add an extruded bar, cut into `name_1..n` if it will not fit the bed.

    Every long part of the frame goes through here, so a smaller printer
    costs extra glue joints rather than failing the build.
    """
    pieces, edges = C.split_strip(profile, lo, hi, plane, max_len)
    if len(pieces) == 1:
        parts.add(name, pieces[0], note=note, **kw)
    else:
        joined = (note + "; " if note else "") + "glue the pieces end to end on a flat surface"
        for k, mesh in enumerate(pieces):
            parts.add(f"{name}_{k + 1}", mesh, note=joined, **kw)
    return edges


def _layout(d: Dims, spec: Spec):
    """Scaled hole, skittle and marking positions."""
    s = d.scale
    holes = [(score, x * s, (REAL_LENGTH - y) * s) for score, x, y in REAL_HOLES]
    y_of = {score: y for score, _, y in holes}
    x50 = abs([x for score, x, _ in holes if score == 50][0])

    stand_off = d.hole_r + 1.5 + d.peg_base / 2
    peg_black = (0.0, y_of[200] - stand_off)
    peg_white = [(-REAL_WHITE_PEG_X * s, y_of[100]), (REAL_WHITE_PEG_X * s, y_of[100])]
    peg_white_alt = [(-x50, y_of[50] - stand_off), (x50, y_of[50] - stand_off)]

    baulk_y = REAL_BAULK_Y * s
    lay = dict(
        ball=d.ball, cord=d.cord, scale=d.scale, variant=spec.variant,
        printer=spec.printer.key, material=spec.material.key,
        playing_width=d.width, playing_length=d.length,
        hole_opening=d.hole_open, playfield_hole=d.hole_d, rings=spec.rings,
        holes=[dict(score=sc, x=round(x, 2), y=round(y, 2)) for sc, x, y in holes],
        peg_black=peg_black, peg_white=peg_white, peg_white_alt=peg_white_alt,
        peg_cap=d.peg_cap, peg_base=d.peg_base,
        baulk_y=baulk_y, d_spot=(0.0, baulk_y), d_radius=REAL_D_RADIUS * s,
        red_spot=(0.0, baulk_y + REAL_RED_OFFSET * s),
        felt=dict(x0=-d.x_face, x1=d.x_face, y0=-d.cord / 2, y1=d.length + d.cord / 2),
        playfield=dict(x0=-d.p, x1=d.p, y0=d.y_pf0, y1=d.y_pf1),
        overall=d.overall, zp=d.zp, zt=d.zt,
        ramp_front=d.ramp_front, ramp_far=d.ramp_z(d.y_bw0), slope=d.slope,
    )
    return holes, lay


def design(spec: Spec) -> Design:
    """Build the whole table. Returns meshes in assembled position."""
    d = Dims(spec)
    pr = spec.printer
    holes, lay = _layout(d, spec)
    parts = C.PartList()
    cuts = {}

    # ------------------------------------------------------- playfield
    hole_xy = [(x, y, d.hole_r) for _, x, y in holes]
    tiles, xs, ys = C.tiled_panel(-d.p, d.y_pf0, d.p, d.y_pf1, d.zp, d.zt,
                                  hole_xy, pr.max_tile, d.seam_margin)
    cuts["playfield_x"], cuts["playfield_y"] = xs, ys
    bare = spec.felt <= 0
    for col, row, mesh in tiles:
        parts.add(f"playfield_r{row + 1}_c{col + 1}", mesh, role="playfield",
                  colour=spec.hue("playfield"), material=spec.material.key,
                  walls=4, infill=30, plate="smooth" if bare else "textured",
                  pose=("x", 180),
                  note="printed TOP FACE DOWN so the playing surface is dead flat"
                       + (" - it is the bare playing surface, so it needs a smooth plate"
                          if bare else " - felt covers it, so any plate will do"))

    # splice plates under every seam, glued on from below
    strap = dict(role="playfield", colour=spec.hue("splice"), walls=3, infill=100)
    for i, xc in enumerate(xs[1:-1]):
        hw = C.clear_half_width(xc, [x for _, x, _ in holes], d.hole_r, d.splice_w / 2)
        _add_strip(parts, f"splice_long_{i + 1}",
                   C.strap_profile(xc, hw, d.zp - d.splice_t, d.zp),
                   d.y_pf0 + d.ledge + 1, d.y_pf1 - d.ledge - 1, "xz",
                   pr.max_strip(2 * hw),
                   note="glue under the lengthways tile seam", **strap)
    for i, yc in enumerate(ys[1:-1]):
        hw = C.clear_half_width(yc, [y for _, _, y in holes], d.hole_r, d.splice_w / 2)
        reach = d.p - d.ledge - 1
        _add_strip(parts, f"splice_cross_{i + 1}",
                   C.strap_profile(yc, hw, d.zp - d.splice_t, d.zp),
                   -reach, reach, "yz", pr.max_strip(2 * hw),
                   note="glue under the crossways tile seam", **strap)

    # coloured hole collars ("full" only; "simple" leaves a plain bored hole)
    if spec.rings:
        ring = C.funnel_ring(d.hole_open / 2, d.hole_r - 0.15,
                             d.zp - 0.5, d.zt + d.felt, flange_out=2.0)
        counts = {"white": 5, "yellow": 2, "black": 1, "red": 1}
        hues = {"white": PALETTE["ring_10"], "yellow": PALETTE["ring_50"],
                "black": PALETTE["ring_100"], "red": PALETTE["ring_200"]}
        for cname, qty in counts.items():
            parts.add(f"hole_ring_{cname}", ring, role="playfield", qty=qty,
                      colour=hues[cname], walls=3, infill=30, pose=("x", 180),
                      note="print flange down; press into the hole over the felt")

    # ------------------------------------------------------- side walls
    wall_prof = C.wall_profile(d.wall, d.zt, d.flange, d.flange_t)
    ledge_prof = C.ledge_profile(d.ledge, d.zp, lip=1.0)
    wall_len = pr.max_strip(d.wall + d.flange)
    wall_edges = C.plan_cuts(d.y_lip0, d.y_bw1, wall_len)
    ledge_edges = C.plan_cuts(d.y_pf0 + d.ledge + 0.5, d.y_pf1 - d.ledge - 0.5,
                              pr.max_strip(1.0 + d.ledge))
    cuts["wall_y"], cuts["ledge_y"] = wall_edges, ledge_edges
    for side, sign in (("right", 1), ("left", -1)):
        prof = C.place(wall_prof, d.xi, 0.0, sign)
        for k, (a, b) in enumerate(zip(wall_edges, wall_edges[1:])):
            parts.add(f"side_wall_{side}_{k + 1}", C.strip(prof, a, b, "xz"),
                      role="frame", colour=spec.hue("frame"),
                      note="stands on its own flange; piece _1 is the front")
        lp = C.place(ledge_prof, d.xi, 0.0, sign)
        for k, (a, b) in enumerate(zip(ledge_edges, ledge_edges[1:])):
            parts.add(f"ledge_strip_{side}_{k + 1}", C.strip(lp, a, b, "xz"),
                      role="frame", colour=spec.hue("frame"),
                      pose=("y", 90 * sign),
                      note="glue inside the wall, flat top level with the slab underside")

    # ------------------------------------------------------- end frame
    half = d.xi - 0.2
    frame = dict(role="frame", colour=spec.hue("frame"))
    back = [(d.y_bw0, 0), (d.y_bw1, 0), (d.y_bw1, d.zt), (d.y_bw0, d.zt),
            (d.y_bw0, d.zp), (d.y_bw0 - d.ledge, d.zp), (d.y_bw0 - d.ledge, d.zp - 1),
            (d.y_bw0, d.zp - 1 - d.ledge)]
    _add_strip(parts, "back_wall", back, -half, half, "yz", pr.max_strip(d.zt),
               pose=("x", -90), note="ledge faces inward", **frame)

    front = [(d.y_fb0, d.zp - d.beam_drop), (d.y_fb1, d.zp - d.beam_drop),
             (d.y_fb1, d.zp - 1 - d.ledge), (d.y_fb1 + d.ledge, d.zp - 1),
             (d.y_fb1 + d.ledge, d.zp), (d.y_fb1, d.zp), (d.y_fb1, d.zt), (d.y_fb0, d.zt)]
    _add_strip(parts, "front_beam", front, -half, half, "yz",
               pr.max_strip(d.tp + d.beam_drop), pose=("x", 90),
               note="ledge faces the far end; its front face is the back of the gate slot",
               **frame)

    apron = [(d.y_ap0, d.zt - d.tp), (d.y_ap1 - 3, d.zt - d.tp), (d.y_ap1 - 3, d.zp - d.beam_drop),
             (d.y_ap1, d.zp - d.beam_drop), (d.y_ap1, d.zt), (d.y_ap0, d.zt)]
    _add_strip(parts, "apron_beam", apron, -half, half, "yz", pr.max_strip(d.apron),
               pose=("x", 180),
               note=f"glue {d.slot:.1f} mm in front of the front beam: that gap is the gate slot",
               **frame)

    lip = [(d.y_lip0, 0), (d.y_lip1, 0), (d.y_lip1, d.lip_h), (d.y_lip0, d.lip_h)]
    _add_strip(parts, "tray_lip", lip, -half, half, "yz", pr.max_strip(d.wall),
               note="front of the ball tray; sits at the desk edge", **frame)

    # ------------------------------------------------------- ball return
    rx = C.plan_cuts(-(d.xi - 0.5), d.xi - 0.5, pr.max_tile)
    ry = C.plan_cuts(d.y_lip1 + 0.3, d.y_bw0 - 0.3, pr.max_tile)
    cuts["ramp_x"], cuts["ramp_y"] = rx, ry
    for i, (x0, x1) in enumerate(zip(rx, rx[1:])):
        for j, (y0, y1) in enumerate(zip(ry, ry[1:])):
            parts.add(f"ramp_r{j + 1}_c{i + 1}", C.wedge(x0, x1, y0, y1, d.ramp_z),
                      role="ramp", colour=spec.hue("ramp"), walls=2, infill=6,
                      note="thin end to the front; nobody sees these, keep the infill low")

    # ------------------------------------------------------------- rails
    rail_prof = C.grooved_rail_profile(d.xo - d.x_face, d.rail_h,
                                       d.cush_z - d.zt, d.groove_r)
    rail_edges = C.plan_cuts(d.y_fb0, d.y_bw1, pr.max_strip(d.rail_h))
    cuts["rail_y"] = rail_edges
    for side, sign in (("right", 1), ("left", -1)):
        prof = C.place(rail_prof, d.x_face, d.zt, sign)
        for k, (a, b) in enumerate(zip(rail_edges, rail_edges[1:])):
            parts.add(f"rail_side_{side}_{k + 1}", C.strip(prof, a, b, "xz"),
                      role="rail", colour=spec.hue("rail"), pose=("y", 90 * sign),
                      note="groove faces inward; stagger its seams off the wall seams")

    end_rail = dict(role="rail", colour=spec.hue("rail"))
    far_face = d.length + d.cord / 2
    far = C.place(C.grooved_rail_profile(d.y_bw1 - far_face, d.rail_h,
                                         d.cush_z - d.zt, d.groove_r),
                  far_face, d.zt, 1)
    _add_strip(parts, "rail_far", far, -d.x_face, d.x_face, "yz", pr.max_strip(d.rail_h),
               pose=("x", -90), note="fits between the side rails", **end_rail)
    front_face = -d.cord / 2
    frt = C.place(C.grooved_rail_profile(front_face - d.y_fb0, d.rail_h,
                                         d.cush_z - d.zt, d.groove_r),
                  front_face, d.zt, -1)
    _add_strip(parts, "rail_front", frt, -d.x_face, d.x_face, "yz", pr.max_strip(d.rail_h),
               pose=("x", 90), note="fits between the side rails", **end_rail)

    if spec.sorted_return:
        _sorted_return(d, spec, parts, holes, lay)

    # --------------------------------------------------- time-bar gate
    bars = C.drop_bar(d.g_w, d.g_bot, d.zt + 2, d.g_tab, d.g_top + 8,
                      max(5.0, 0.5 * d.ball),
                      max_width=pr.max_strip(d.g_top + 8 - d.g_bot))
    for suffix, outline, bores in bars:
        parts.add(f"time_bar_gate{suffix}",
                  C.strip(outline, d.g_y0, d.g_y0 + d.gate_t, "xz", holes=bores),
                  role="play", colour=spec.hue("gate"), walls=4, infill=25, pose=("x", 90),
                  note="drop it into the slot when time is up"
                       + ("" if suffix == "" else "; glue the pieces edge to edge first"))

    # ----------------------------------------------------------- skittles
    peg, _ = C.mushroom_peg(d.peg_cap, d.peg_base, d.peg_h, PEG_RIM_FRAC)
    seat = d.zt + d.felt
    if spec.variant == "simple":
        parts.add("skittle", peg.translate(*lay["peg_black"], seat), role="play", qty=3,
                  colour=spec.hue("skittle_white"), walls=2, infill=8,
                  note="print upright, no supports; keep them light so they topple")
    else:
        for key, nm, qty, at in (("skittle_black", "skittle_black", 1, lay["peg_black"]),
                                 ("skittle_white", "skittle_white", 2, lay["peg_white"][0])):
            parts.add(nm, peg.translate(*at, seat), role="play", qty=qty,
                      colour=PALETTE[key], walls=2, infill=8,
                      note="print upright, no supports; keep them light so they topple")

    # -------------------------------------------------------- scoreboard
    _scoreboard(d, spec, parts)

    # --------------------------------------------------------- cue parts
    park = (0.0, d.y_lip0 - 60.0, 0.0)
    parts.add("cue_tip_ferrule",
              C.dowel_ferrule(d.dowel, socket=14, length=18).translate(*park),
              role="cue", qty=spec.cues, colour=spec.hue("cue"), walls=3, infill=30,
              note=f"glue onto an {d.dowel:.0f} mm dowel; face it with a 9 mm leather disc")
    parts.add("cue_butt",
              C.dowel_butt(d.dowel, socket=70, length=80, grip_r=9.0).translate(30, park[1], 0),
              role="cue", qty=spec.cues, colour=spec.hue("cue"), walls=3, infill=15)

    # ------------------------------------------------------- desk mounting
    jaw_w = d.flange - 1.0
    # "simple" is one filament for the whole table, so the clamps are printed in
    # it too; PETG is the better plastic here and "full" uses it.
    clamp_mat = spec.material.key if spec.variant == "simple" else "petg"
    clamp_hint = ("" if spec.variant == "full" else
                  " (PETG survives the flexing better, if you have a second spool)")
    desks = [spec.desk] if spec.variant == "simple" else [18, 25, 32, 40]
    for desk in desks:
        prof = C.place(C.hook_clamp_profile(desk, reach=40, jaw=16, flange_t=d.flange_t),
                       d.y_lip0, 0.0, 1)
        parts.add(f"desk_clamp_{desk:.0f}mm",
                  C.strip(prof, d.xo + 0.5, d.xo + 0.5 + jaw_w, "yz"),
                  role="mount", qty=2, material=clamp_mat, colour=spec.hue("mount"),
                  walls=4, infill=40, pose=("y", 90),
                  note=f"for desks about {desk - 4:.0f}-{desk + 4:.0f} mm thick"
                       + clamp_hint)
    parts.add("clamp_shim", C.taper_shim(50, 3.0, 12.0, jaw_w)
              .translate(d.xo + 60, d.y_lip0, -60),
              role="mount", qty=2, material=clamp_mat, colour=spec.hue("mount"),
              walls=3, infill=25, note="tap in between clamp jaw and desk underside")

    return Design(spec=spec, dims=d, holes=holes, layout=lay, parts=parts, cuts=cuts)


def scoreboard_rows(d: Dims):
    """Y centre of each slider row, top first: hundreds, tens, units."""
    return [((d.sb_rows - 1) / 2 - i) * d.sb_row_pitch for i in range(d.sb_rows)]


def scoreboard_bays(d: Dims):
    """X centre of each of the ten positions, 0 on the left."""
    return [-d.sb_run / 2 + i * d.sb_pitch for i in range(d.sb_steps)]


def _scoreboard(d: Dims, spec: Spec, parts: C.PartList):
    """A slider scoreboard: three rows of 0-9 for hundreds, tens and units.

    Three flat plates glued into a sandwich with the markers already inside,
    so a marker cannot fall out. The middle plate is the channel a marker's
    foot runs in; the top plate's slot is scalloped, so each of the ten
    positions is unmistakable. Every piece is a plate with holes or a turned
    peg, which is all the geometry engine can do — there is no snap fit
    anywhere, because nothing printed flat like this would spring.
    """
    rows = scoreboard_rows(d)
    qty = 1 if spec.variant == "simple" else 2
    board = dict(role="play", colour=spec.hue("frame"), walls=3, infill=30, qty=qty)

    z0 = 0.0
    parts.add("score_back", C.flat_plate(d.sb_w, d.sb_h, z0, z0 + d.sb_back_t),
              note="the backing plate. Print a second set for your opponent",
              **board)

    z1 = z0 + d.sb_back_t
    channels = [C.stadium_slot(0.0, y, d.sb_run + 2 * d.sb_track_r, d.sb_track_r)
                for y in rows]
    parts.add("score_track", C.flat_plate(d.sb_w, d.sb_h, z1, z1 + d.sb_track_t, channels),
              note="the middle plate: each slot is the channel a marker's foot runs in",
              **board)

    z2 = z1 + d.sb_track_t
    bays = [C.scalloped_slot(0.0, y, d.sb_steps, d.sb_pitch, d.sb_bay_r, d.sb_neck_r)
            for y in rows]
    parts.add("score_face", C.flat_plate(d.sb_w, d.sb_h, z2, z2 + d.sb_face_t, bays),
              note="the top plate; the ten bays in a row are its digits. Glue the "
                   "paper scale from the template PDF alongside the rows",
              **board)

    marker = C.tee_marker(d.sb_shaft_r, d.sb_foot_r, d.sb_knob_r,
                          d.sb_foot_t, d.sb_face_t, d.sb_knob_h)
    parts.add("score_marker", marker.translate(0, 0, z1), role="play",
              qty=d.sb_rows * qty, colour=spec.hue("gate"), walls=3, infill=40,
              note="one per row. Drop them into the channels before gluing the top "
                   "plate on; sand the shaft if one is stiff")


# ------------------------------------------------------------- test coupons
def coupon(spec: Spec) -> Design:
    """A small set of parts that exercises every fit, in about an hour.

    Same components, same dimensions, just short: if the coupon is right the
    whole table will be, and if it is not you have lost an hour rather than
    two days.
    """
    d = Dims(spec)
    holes, lay = _layout(d, spec)
    parts = C.PartList()
    hue = spec.hue("test")
    run = max(60.0, 5 * d.ball)                   # how long each sample is

    gauge, centres = C.hole_gauge(d.hole_open / 2, d.tp)
    parts.add("test_hole_gauge", gauge, role="test", colour=hue, walls=4, infill=30,
              plate="smooth" if spec.felt <= 0 else "textured", pose=("x", 180),
              note="five holes, -0.4 to +0.4 mm; drop a ball through each and "
                   f"note which one you want (nominal {d.hole_open:.2f} mm)")

    y200 = [y for sc, _, y in holes if sc == 200][0]
    x0, x1 = -d.p, -d.p + run + d.hole_d
    parts.add("test_playfield_corner",
              C.panel(x0, y200 - run / 2, x1, y200 + run / 2, d.zp, d.zt,
                      [(x0 + (x1 - x0) / 2, y200, d.hole_r)]),
              role="test", colour=hue, walls=4, infill=30,
              plate="smooth" if spec.felt <= 0 else "textured", pose=("x", 180),
              note="a corner of the real slab: checks thickness, flatness and the "
                   "hole over felt")

    wall_prof = C.place(C.wall_profile(d.wall, d.zt, d.flange, d.flange_t), d.xi, 0.0, -1)
    parts.add("test_wall", C.strip(wall_prof, 0, run, "xz"), role="test", colour=hue,
              note="checks wall height against the slab and the clamp flange")
    ledge_prof = C.place(C.ledge_profile(d.ledge, d.zp, 1.0), d.xi, 0.0, -1)
    parts.add("test_ledge", C.strip(ledge_prof, 2, run - 2, "xz"), role="test",
              colour=hue, pose=("y", -90), note="glue to the test wall, then rest the "
              "corner tile on it: the surface should land flush with the wall top")

    rail_prof = C.place(C.grooved_rail_profile(d.xo - d.x_face, d.rail_h,
                                               d.cush_z - d.zt, d.groove_r),
                        d.x_face, d.zt, -1)
    parts.add("test_rail", C.strip(rail_prof, 0, run, "xz"), role="test", colour=hue,
              pose=("y", -90),
              note=f"press {d.cord:.1f} mm cord into the groove; the nose should touch a "
                   f"ball {d.cush_z - d.zt - d.felt:.1f} mm above the felt")

    parts.add("test_ramp", C.wedge(-run / 2, run / 2, d.y_lip1 + 0.3,
                                   d.y_lip1 + 0.3 + run, d.ramp_z),
              role="test", colour=hue, walls=2, infill=6,
              note="the front of the return ramp; check a ball rolls down it, not "
                   "along a layer line")

    peg, _ = C.mushroom_peg(d.peg_cap, d.peg_base, d.peg_h, PEG_RIM_FRAC)
    parts.add("test_skittle", peg, role="test", colour=hue, walls=2, infill=8,
              note="must stand up, and topple when a ball brushes it")

    prof = C.place(C.hook_clamp_profile(spec.desk, reach=40, jaw=16, flange_t=d.flange_t),
                   d.y_lip0, 0.0, 1)
    parts.add("test_clamp", C.strip(prof, d.xo + 0.5, d.xo + 0.5 + d.flange - 1.0, "yz"),
              role="test", material=spec.material.key, colour=hue, walls=4, infill=40,
              pose=("y", 90),
              note=f"hook it over the test wall's flange and onto a {spec.desk:.0f} mm desk")

    lay["coupon"] = True
    lay["gauge_steps"] = [round(d.hole_open + s, 2) for s in (-0.4, -0.2, 0.0, 0.2, 0.4)]
    return Design(spec=spec, dims=d, holes=holes, layout=lay, parts=parts,
                  cuts={"gauge_x": centres})
