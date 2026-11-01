#!/usr/bin/env python3
"""Reusable printable components.

This is the vocabulary `table.py` builds the table out of. Nothing in here
knows anything about bar billiards: every function takes dimensions and
returns a `Mesh` (or a list of them) plus, where it matters, the pose that
puts a large flat face on the print bed. Reuse these, or add to them, rather
than writing fresh triangle soup — a component is tested by every design
that uses it.

Two shape engines only (see `meshlib`): `prism()` extrudes a 2D outline with
holes along one axis, `lathe()` revolves an (r, z) profile. There is no CSG,
so a hole can only run along a part's extrusion axis.

Conventions
-----------
* Everything is millimetres.
* Profile helpers return points in a local *(u, z)* frame where `u = 0` is
  the working face and `u` grows away from it. `place()` maps that frame
  into world coordinates, so the same profile serves a left and a right
  hand part.
* A component returns geometry in its final assembled position; the print
  pose is carried separately as a `Part.pose` and applied on export.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

from meshlib import Mesh, circle, lathe, prism, rect


# ------------------------------------------------------------------ parts
#: Roles group parts in the bill of materials and in the print plan.
ROLES = ("playfield", "frame", "ramp", "rail", "play", "mount", "cue", "test")


@dataclass
class Part:
    """One printable file, plus everything the slicer and the builder need."""
    name: str
    mesh: Mesh
    role: str = "frame"
    qty: int = 1
    material: str = "pla"
    colour: str = "#c8c8c8"
    walls: int = 3
    infill: int = 15
    supports: bool = False
    plate: str = "textured"            # "smooth" when a face must come out flat
    pose: tuple[str, float] | None = None   # ("x"|"y", degrees) to lay it flat
    note: str = ""

    def __post_init__(self):
        if self.role not in ROLES:
            raise ValueError(f"{self.name}: unknown role {self.role!r}")
        self.mesh.name = self.name


class PartList(list):
    """A list of `Part` that refuses duplicate names."""

    def add(self, name, mesh, **kw) -> Part:
        if any(p.name == name for p in self):
            raise ValueError(f"duplicate part name {name!r}")
        p = Part(name, mesh, **kw)
        self.append(p)
        return p

    @property
    def pieces(self) -> int:
        return sum(p.qty for p in self)


# -------------------------------------------------------- profile plumbing
def place(profile, origin_u=0.0, origin_z=0.0, u_dir=1.0):
    """Map a local (u, z) profile into a 2D plane at `origin`, facing `u_dir`.

    `u_dir = -1` mirrors it, which is how a left-hand part is made from the
    same profile as its right-hand twin.
    """
    return [(origin_u + u_dir * u, origin_z + z) for u, z in profile]


def arc(radius, centre_u, centre_z, start_deg, end_deg, n=12, u_dir=1.0):
    """Points along a circular arc in a (u, z) profile, inclusive of both ends."""
    out = []
    for k in range(n + 1):
        t = math.radians(start_deg + (end_deg - start_deg) * k / n)
        out.append((centre_u + u_dir * radius * math.cos(t), centre_z + radius * math.sin(t)))
    return out


# ------------------------------------------------------------- the splitter
def plan_cuts(lo, hi, max_len, avoid=(), margin=0.0, reach=40.0, step=0.5):
    """Split the span [lo, hi] into equal-ish pieces no longer than `max_len`.

    Each cut is then nudged, within +-`reach`, to keep at least `margin` of
    clear material away from every `(centre, radius)` in `avoid` — that is
    what keeps a tile seam from running through a hole.

    Returns the piece edges, so `len(edges) - 1` pieces.
    """
    if hi - lo <= max_len and not avoid:
        return [lo, hi]
    n_min = max(1, math.ceil((hi - lo) / max_len))
    for n in range(n_min, n_min + 12):
        cuts = []
        for k in range(1, n):
            ideal = lo + (hi - lo) * k / n
            best, best_score = None, -1e9
            for i in range(-int(reach / step), int(reach / step) + 1):
                c = ideal + i * step
                clear = min([abs(c - ac) - ar for ac, ar in avoid] or [1e9])
                if clear <= margin:
                    continue
                score = min(clear, margin + 8.0) - 0.01 * abs(c - ideal)
                if score > best_score:
                    best, best_score = c, score
            if best is None:
                break
            cuts.append(best)
        else:
            edges = [lo] + cuts + [hi]
            if all(b - a <= max_len + 1e-6 for a, b in zip(edges, edges[1:])):
                return edges
    raise SystemExit(
        f"cannot split a {hi - lo:.0f} mm span into <= {max_len:.0f} mm pieces "
        f"while clearing {len(avoid)} obstacle(s) — try a bigger printer or a "
        f"smaller --size")


# ----------------------------------------------------------------- panels
def panel(x0, y0, x1, y1, z0, z1, holes=()):
    """A flat plate in the XY plane with vertical through holes.

    `holes` are `(x, y, radius)`; they must sit fully inside the plate and
    not touch each other (no CSG to rescue overlaps).
    """
    cuts = [circle(hx, hy, hr, 56) for hx, hy, hr in holes]
    return prism(rect(x0, y0, x1, y1), cuts, z0, z1, "xy")


def flat_plate(width, height, z0, z1, cutouts=()):
    """A rectangular plate in the XY plane, centred on the origin, with
    arbitrary cut-out polygons (slots, windows) through its thickness."""
    outline = rect(-width / 2, -height / 2, width / 2, height / 2)
    return prism(outline, list(cutouts), z0, z1, "xy")


def tiled_panel(x0, y0, x1, y1, z0, z1, holes, max_tile, margin, keep=1.0):
    """A panel too big for the bed, cut into tiles that miss every hole.

    Returns `(tiles, x_edges, y_edges)` where each tile is
    `(col, row, mesh)`. A hole is given to the tile it falls inside; `keep`
    is how far inside the tile edge a hole centre must be to count, which
    `plan_cuts` has already guaranteed via `margin`.
    """
    xs = plan_cuts(x0, x1, max_tile, [(hx, hr) for hx, _, hr in holes], margin)
    ys = plan_cuts(y0, y1, max_tile, [(hy, hr) for _, hy, hr in holes], margin)
    tiles = []
    for i, (a, b) in enumerate(zip(xs, xs[1:])):
        for j, (c, d) in enumerate(zip(ys, ys[1:])):
            mine = [h for h in holes if a + keep < h[0] < b - keep and c + keep < h[1] < d - keep]
            tiles.append((i, j, panel(a, c, b, d, z0, z1, mine)))
    return tiles, xs, ys


def strap_profile(centre, half_width, z0, z1):
    """Cross-section of a thin strap glued under a panel seam.

    Extrude it along the seam with `strip()` or `split_strip()`; `half_width`
    is how far it reaches either side of the seam (keep it clear of holes).
    """
    return rect(centre - half_width, z0, centre + half_width, z1)


def clear_half_width(centre, obstacles, radius, want, keep=1.5, floor=3.0):
    """How wide a strap can be at `centre` without touching an obstacle."""
    clear = min([abs(centre - o) - radius for o in obstacles] or [1e9])
    return max(floor, min(want, clear - keep))


# ------------------------------------------------------------------ strips
def strip(profile, w0, w1, plane, holes=()):
    """A constant cross-section bar: a 2D profile extruded along one axis."""
    return prism(profile, list(holes), w0, w1, plane)


def split_strip(profile, lo, hi, plane, max_len, avoid=(), margin=0.0):
    """The same bar, cut into bed-sized lengths.

    Returns `(meshes, edges)`. One mesh means it fitted whole.
    """
    edges = plan_cuts(lo, hi, max_len, avoid, margin)
    return [strip(profile, a, b, plane) for a, b in zip(edges, edges[1:])], edges


def wedge(w0, w1, u0, u1, z_at, plane="yz"):
    """A ramp: flat on the desk, its top face rising linearly from u0 to u1.

    `z_at(u)` gives the top surface height, so the same helper serves any
    slope or a curved return.
    """
    profile = [(u0, 0.0), (u1, 0.0), (u1, z_at(u1)), (u0, z_at(u0))]
    return strip(profile, w0, w1, plane)


# ------------------------------------------------------- rails and cushions
def grooved_rail_profile(depth, height, groove_z, groove_r, n=12):
    """Rail cross-section in (u, z): u = 0 is the cushion face, z = 0 its foot.

    A semicircular groove is cut into the face at `groove_z` so a bought
    silicone cord sits half buried in it and becomes the cushion nose.
    """
    body = [(0.0, 0.0), (depth, 0.0), (depth, height), (0.0, height)]
    return body + arc(groove_r, 0.0, groove_z, 90, -90, n)


def wall_profile(thickness, height, flange_w=0.0, flange_t=0.0):
    """Side wall cross-section in (u, z): u = 0 is the inside face.

    With a flange it grows an outward foot at the bottom for a desk clamp to
    hook over, which also gives the part a large flat face to print on.
    """
    if flange_w <= 0:
        return rect(0.0, 0.0, thickness, height)
    return [(0.0, 0.0), (thickness + flange_w, 0.0), (thickness + flange_w, flange_t),
            (thickness, flange_t), (thickness, height), (0.0, height)]


def ledge_profile(depth, z_top, lip=1.0):
    """A shelf for a panel edge to rest on, in (u, z) with u growing inward.

    Triangular underneath so it prints against a wall without supports.
    """
    return [(0.0, z_top), (depth, z_top), (depth, z_top - lip), (0.0, z_top - lip - depth)]


# ------------------------------------------------------------ turned parts
def funnel_ring(opening_r, seat_r, z0, z1, flange=0.8, flange_out=2.0, n=64):
    """A collar that lines a hole: straight bore, small flange on top.

    Printed flange-down and pressed into the panel over the felt, it hides
    the cut edge of the felt and gives the hole a clean rim.
    """
    profile = [
        (opening_r, z0), (seat_r, z0), (seat_r, z1),
        (seat_r + flange_out, z1), (seat_r + flange_out * 0.6, z1 + flange),
        (opening_r, z1 + flange),
    ]
    return lathe(profile, n)


def mushroom_peg(cap_d, base_d, height, rim_frac=0.74, n=72):
    """A bar billiards skittle: wide cap, slim waist, small foot.

    The cap underside is a 45 degree cone so it prints upright with no
    supports, and the dome on top is drawn into the profile.
    """
    cap_r, base_r = cap_d / 2, base_d / 2
    stem_r = base_d * 0.32
    z_rim = height * rim_frac
    z_cone = z_rim - (cap_r - stem_r)      # 45 degrees
    if z_cone <= 4.0:
        raise ValueError("skittle too short for a 45 degree cap underside")
    profile = [(0, 0), (base_r, 0), (base_r, 1.2), (stem_r * 1.25, 2.6),
               (stem_r, 4.0), (stem_r, z_cone), (cap_r, z_rim - 0.8), (cap_r, z_rim)]
    for k in range(1, 9):               # dome
        t = k / 8 * math.pi / 2
        profile.append((cap_r * math.cos(t), z_rim + (height - z_rim) * math.sin(t)))
    profile[-1] = (0, height)
    return lathe(profile, n), z_rim


def dowel_ferrule(dowel_d, socket, length, tip_r=3.0, clr=0.15, n=48):
    """A cue tip: a socket that glues onto a bought dowel, domed on the end."""
    r_o = dowel_d / 2 + 1.2
    prof = [(0, socket), (dowel_d / 2 + clr, socket), (dowel_d / 2 + clr, 0),
            (r_o, 0), (r_o, length)]
    for k in range(1, 7):
        t = k / 6 * math.pi / 2
        prof.append((r_o * math.cos(t), length + tip_r * math.sin(t)))
    prof[-1] = (0, length + tip_r)
    return lathe(prof, n)


def dowel_butt(dowel_d, socket, length, grip_r, clr=0.15, n=48):
    """A cue butt: a long socket with a flared grip."""
    prof = [(0, socket), (dowel_d / 2 + clr, socket), (dowel_d / 2 + clr, 0),
            (grip_r, 0), (grip_r, 6), (grip_r - 2.0, length), (0, length)]
    return lathe(prof, n)


# ---------------------------------------------------------------- mounting
def hook_clamp_profile(desk_t, reach, jaw, flange_t, gap=7.5, lip=5.0):
    """A C-hook that drops over a flange and grips under a desk top.

    (u, z) with u = 0 at the front face of the table and z = 0 at desk
    level. Sized so one clamp covers `desk_t` +- 4 mm with a tapped-in shim.
    """
    z1 = -desk_t - gap
    z0 = z1 - lip
    return [(-7, z0), (reach, z0), (reach, z1), (0, z1), (0, flange_t),
            (jaw, flange_t), (jaw, flange_t + lip), (-7, flange_t + lip)]


def taper_shim(length, t0, t1, width):
    """A wedge tapped in to take up slack. Extruded across X."""
    return strip([(0, 0), (length, 0), (length, t1), (0, t0)], 0, width, "xz")


def drop_bar(half_width, z_bottom, z_band, tab_half, z_tab, finger_r, max_width=None):
    """A bar that drops into a slot: a wide band with a raised centre grip.

    Returns `[(suffix, outline, holes)]` ready to extrude across the slot.
    One piece if it fits the bed; otherwise a centre piece carrying the grip
    plus plain wings either side, butt-glued end to end — the seams land in
    the deep band, well away from the grip.
    """
    finger = circle(0.0, z_tab - finger_r - 2.0, finger_r, 40)
    tab = [(tab_half, z_band), (tab_half, z_tab), (-tab_half, z_tab), (-tab_half, z_band)]

    def band(u0, u1, cap=()):
        return [(u0, z_bottom), (u1, z_bottom), (u1, z_band)] + list(cap) + [(u0, z_band)]

    if max_width is None or 2 * half_width <= max_width:
        return [("", band(-half_width, half_width, tab), [finger])]

    cut = tab_half + 8.0
    if 2 * cut > max_width:
        raise SystemExit("the gate grip alone is wider than the bed; use a smaller --size")
    pieces = [("_grip", band(-cut, cut, tab), [finger])]
    for side, (lo, hi) in (("left", (-half_width, -cut)), ("right", (cut, half_width))):
        edges = plan_cuts(lo, hi, max_width)
        for k, (a, b) in enumerate(zip(edges, edges[1:])):
            suffix = f"_{side}" + (f"_{k + 1}" if len(edges) > 2 else "")
            pieces.append((suffix, band(a, b), []))
    return pieces


# ----------------------------------------------------------- sorted return
def lane_fin(w0, w1, u0, u1, floor, ceiling, clearance=0.3):
    """A thin wall that divides a sloping floor into lanes.

    `floor(u)` is the surface it stands on, so the fin's underside follows a
    ramp exactly instead of leaving a wedge of daylight — the one shape the
    prism engine can do here, since the slope runs along the profile and the
    thickness along the extrusion. It reaches `ceiling`, so it is trapped
    between the ramp and the slab above and needs no bracket.
    """
    profile = [(u0, floor(u0) + clearance), (u1, floor(u1) + clearance),
               (u1, ceiling), (u0, ceiling)]
    return strip(profile, w0, w1, "yz")


def cross_chute(w0, w1, u_high, u_low, z_floor, rise, lip=0.8):
    """A little trough that tips a ball sideways as it lands in it.

    Extruded along the direction the ball was travelling, so its floor can
    fall across that direction. Used where two holes share a centreline and
    their balls have to end up in different lanes.
    """
    return strip([(u_low, z_floor), (u_high, z_floor),
                  (u_high, z_floor + rise), (u_low, z_floor + lip)],
                 w0, w1, "xz")


# ------------------------------------------------------------- scoreboards
def _dedupe(pts, eps=1e-7):
    """Drop points that repeat the previous one (or the first, at the wrap).

    Arcs that meet end to end share a point, and a repeated vertex makes the
    triangulator produce a zero-area ear and a non-watertight mesh.
    """
    out = []
    for p in pts:
        if not out or abs(p[0] - out[-1][0]) > eps or abs(p[1] - out[-1][1]) > eps:
            out.append(p)
    while len(out) > 3 and abs(out[-1][0] - out[0][0]) <= eps and abs(out[-1][1] - out[0][1]) <= eps:
        out.pop()
    return out


def stadium_slot(centre_u, centre_z, length, radius, n=14):
    """A straight slot with semicircular ends, lying along u."""
    half = max(0.0, length / 2 - radius)
    return _dedupe(arc(radius, centre_u + half, centre_z, -90, 90, n)
                   + arc(radius, centre_u - half, centre_z, 90, 270, n))


def scalloped_slot(centre_u, centre_z, steps, pitch, bay_r, neck_r, n=8):
    """A slot with a round bay at every step, joined by a narrower neck.

    A marker running in it slides the whole way — the necks are not a
    snap fit, there is nothing here that could spring — but it settles
    visibly into a bay, so the reading is never ambiguous.
    """
    if not 0 < neck_r < bay_r:
        raise ValueError("neck must be narrower than a bay and wider than nothing")
    phi = math.degrees(math.asin(neck_r / bay_r))
    if pitch <= 2 * bay_r * math.cos(math.radians(phi)):
        raise ValueError("bays overlap: increase the pitch")
    span = (steps - 1) * pitch
    us = [centre_u - span / 2 + i * pitch for i in range(steps)]
    pts = []
    for i, u in enumerate(us):                      # bottom edge, left to right
        pts += arc(bay_r, u, centre_z,
                   180.0 if i == 0 else 180.0 + phi,
                   360.0 if i == steps - 1 else 360.0 - phi, n)
    for i in reversed(range(steps)):                # top edge, right to left
        pts += arc(bay_r, us[i], centre_z,
                   0.0 if i == steps - 1 else phi,
                   180.0 if i == 0 else 180.0 - phi, n)
    return _dedupe(pts)


def tee_marker(shaft_r, foot_r, knob_r, foot_t, face_t, knob_h, gap=0.4, n=40):
    """A scoreboard marker: wide foot, shaft through the slot, knob on top.

    Trapped between the board's plates when they are glued up, so it cannot
    come out, and pushed along with a fingertip.
    """
    z_shaft = foot_t + gap
    z_knob = z_shaft + face_t
    prof = [(0, 0), (foot_r, 0), (foot_r, foot_t), (shaft_r, foot_t),
            (shaft_r, z_knob), (knob_r, z_knob), (knob_r, z_knob + knob_h * 0.45)]
    for k in range(1, 7):                            # domed top, prints clean
        t = k / 6 * math.pi / 2
        prof.append((knob_r * math.cos(t),
                     z_knob + knob_h * 0.45 + knob_h * 0.55 * math.sin(t)))
    prof[-1] = (0, z_knob + knob_h)
    return lathe(prof, n)


# ------------------------------------------------------------ test coupons
def hole_gauge(opening_r, thickness, steps=(-0.4, -0.2, 0.0, 0.2, 0.4), pitch=None):
    """A strip of slightly different holes, for picking the real hole size.

    Print one, drop a ball through each hole and read off which diameter
    your printer and filament actually want.
    """
    pitch = pitch or 2 * opening_r + 8.0
    n = len(steps)
    span = pitch * n
    holes = [(-span / 2 + pitch * (i + 0.5), 0.0, opening_r + s / 2) for i, s in enumerate(steps)]
    depth = 2 * opening_r + 10.0
    return panel(-span / 2, -depth / 2, span / 2, depth / 2, 0, thickness, holes), [h[0] for h in holes]
