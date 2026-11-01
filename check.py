#!/usr/bin/env python3
"""Design-rule checks. Run after every change:

    python check.py                     # the default build (mini, simple, P1S)
    python check.py --size standard     # takes every barbilliards.py option
    python check.py --coupon
    python check.py --all               # sweep every size x variant x printer

Exits non-zero if any rule is broken. These are the invariants in AGENTS.md
section 6: don't weaken one to make a change pass — fix the geometry, or ask.
Nothing is written to disk.
"""
from __future__ import annotations

import math
import sys

import barbilliards as bb
import profiles as P
import table as T


class Checker:
    def __init__(self, verbose=True):
        self.fails = []
        self.count = 0
        self.verbose = verbose

    def rule(self, ok, msg):
        self.count += 1
        if self.verbose:
            print(("PASS  " if ok else "FAIL  ") + msg)
        if not ok:
            self.fails.append(msg)


def _hole_x(holes, lanes, i):
    """The X of the hole that feeds lane `i` (its centre minus the nudge)."""
    return lanes[i][1] - lanes[i][3]


def run(design: T.Design, rows, chk: Checker):
    d, spec = design.dims, design.spec
    B, r, H = d.ball, d.hole_r, design.holes
    pr = spec.printer
    coupon = design.layout.get("coupon", False)

    # --- 1. every part is a printable solid that fits the plate -----------
    # (bb.measure() has already refused anything that is not; this re-states
    # the rule so a sweep reports it rather than crashing.)
    chk.rule(all(r_["orientation"] in ("straight", "diagonal") for r_ in rows),
             f"all {len(rows)} parts fit {pr.name}")
    thin = [r_ for r_ in rows if min(float(v) for v in r_["size_mm"].split(" x ")) < pr.min_wall]
    chk.rule(not thin, f"no part thinner than {pr.min_wall:.1f} mm (two perimeters)"
                       + (f" - {thin[0]['file']}" if thin else ""))
    tall = [r_ for r_ in rows if float(r_["size_mm"].split(" x ")[2]) > pr.height]
    chk.rule(not tall, f"no part taller than the {pr.height:.0f} mm gantry")

    # --- one filament for the simple variant -----------------------------
    if spec.variant == "simple":
        mats = {r_["material"] for r_ in rows}
        cols = {r_["colour"] for r_ in rows}
        chk.rule(len(mats) == 1, f"simple variant uses one material ({', '.join(sorted(mats))})")
        chk.rule(len(cols) == 1, f"simple variant uses one colour ({', '.join(sorted(cols))})")
        plates = {r_["plate"] for r_ in rows}
        chk.rule(len(plates) == 1 or spec.felt <= 0,
                 "simple variant with felt needs only one build plate")

    # --- 2/3/4. a ball can be potted and comes back ----------------------
    chk.rule(d.hole_open >= B + 1.5, f"hole opening {d.hole_open:.1f} >= ball + 1.5")
    chk.rule(d.slope >= 2.0, f"ramp slope {d.slope:.1f} >= 2 deg")
    if not coupon:
        for s_, _x, y in H:
            gap = d.zp - d.splice_t - d.ramp_z(y)
            chk.rule(gap >= B + 3, f"{s_:>3} hole: {gap:.1f} mm headroom under the slab "
                                   f"(incl. splice) >= ball + 3")
        beam = d.zp - d.beam_drop - d.ramp_z(d.y_fb0)
        chk.rule(beam >= B + 3, f"ball passes under the front/apron beams ({beam:.1f} mm)")
        tray = d.ramp_z(d.y_lip1) + d.lip_h
        chk.rule(d.lip_h >= 0.8 * B, f"tray lip {d.lip_h:.1f} mm holds the balls in")
        chk.rule(tray > d.ramp_z(d.y_lip1) + 0.5 * B, "tray lip stands above the ramp foot")

    # --- 5. the gate really stops balls ----------------------------------
    if not coupon:
        side = d.xi - d.g_w
        chk.rule(side < B / 2, f"gate side gap {side:.2f} < half a ball")
        chk.rule(d.g_bot - d.ramp_z(d.g_y0) < B / 2, "gate bottom gap < half a ball")
        chk.rule(d.slot > d.gate_t, f"gate slot {d.slot:.2f} wider than the {d.gate_t:.2f} mm gate")
        chk.rule(d.slot - d.gate_t < B / 2, "gate slot is not itself a ball-sized gap")
        chk.rule(d.g_top + 8 > d.zt + d.rail_h, "gate grip stands above the rails to be lifted")

    # --- 6. holes sit in the playing area, clear of each other -----------
    for s_, x, y in H:
        chk.rule(abs(x) + r + 3 <= d.half_width and 3 + r <= y <= d.length - r - 3,
                 f"{s_:>3} hole inside the cushions")
    for i in range(len(H)):
        for j in range(i + 1, len(H)):
            dist = ((H[i][1] - H[j][1]) ** 2 + (H[i][2] - H[j][2]) ** 2) ** 0.5
            chk.rule(dist >= 2 * r + B,
                     f"holes {H[i][0]}@{H[i][1]:.0f} and {H[j][0]}@{H[j][1]:.0f} "
                     "at least a ball apart")

    # --- 7. skittles can't fall in, and a ball fits under the cap -------
    chk.rule(d.peg_cap >= d.hole_d + 3, f"skittle cap {d.peg_cap:.1f} wider than a hole")
    chk.rule(d.peg_rim - 0.8 >= B + 1.0, f"ball rolls under the cap rim "
                                         f"({d.peg_rim - 0.8:.1f} mm)")
    lay = design.layout
    for nm, (x, y) in [("black", lay["peg_black"])] + [("white", p) for p in lay["peg_white"]] \
            + [("white-alt", p) for p in lay["peg_white_alt"]]:
        dist = min(((x - hx) ** 2 + (y - hy) ** 2) ** 0.5 for _, hx, hy in H)
        chk.rule(dist >= r + d.peg_base / 2 + 0.5, f"{nm} skittle base clear of every hole")

    # --- 8. cushions behave like a real table ---------------------------
    nose = d.cush_z - (d.zt + d.felt)
    chk.rule(0.60 * B <= nose <= 0.70 * B,
             f"cushion nose at {nose / B:.2f} x ball diameter (0.60-0.70)")
    chk.rule(d.rail_h >= 0.9 * B, f"rails {d.rail_h:.1f} mm, at least 0.9 x ball")
    chk.rule(d.groove_r * 2 >= d.cord, "cord groove is not narrower than the cord")
    chk.rule(d.cush_z + d.cord / 2 <= d.zt + d.rail_h,
             "cord sits fully inside the rail, not above it")

    # --- 9. tile seams and splices stay away from holes -----------------
    if not coupon:
        for axis, key in (("lengthways", "playfield_x"), ("crossways", "playfield_y")):
            coords = [x for _, x, _ in H] if key.endswith("x") else [y for _, _, y in H]
            for c in design.cuts[key][1:-1]:
                chk.rule(all(abs(c - h) > r + 3 for h in coords),
                         f"{axis} tile seam at {c:.1f} clear of every hole")
        for part in design.parts:
            if not part.name.startswith("splice"):
                continue
            lo, hi = part.mesh.v.min(0), part.mesh.v.max(0)
            clash = [s_ for s_, hx, hy in H
                     if lo[0] - r < hx < hi[0] + r and lo[1] - r < hy < hi[1] + r]
            chk.rule(not clash, f"{part.name} covers no hole"
                                + (f" (fouls {clash})" if clash else ""))

    # --- 11b. the scored return sorts, and nothing jams -----------------
    if spec.sorted_return and not coupon:
        fin_t = max(2.0, 5 * pr.nozzle)
        bounds, lanes = T.return_lanes(d, H, fin_t)
        need = B + 1.0 + fin_t
        chk.rule(len(lanes) == len(H), f"a lane for each of the {len(H)} holes")
        for i, (score, _x, _y, _off) in enumerate(lanes):
            width = bounds[i + 1] - bounds[i]
            chk.rule(width >= need, f"{score:>3} lane {width:.1f} mm >= ball + "
                                    f"{1.0 + fin_t:.1f}")
        for b in bounds[1:-1]:
            fouled = [s_ for s_, hx, _hy in H if abs(hx - b) < r + fin_t / 2]
            chk.rule(not fouled, f"lane wall at x={b:.1f} is clear of every hole"
                                 + (f" (fouls {fouled})" if fouled else ""))
        for i, (score, _x, hy, offset) in enumerate(lanes):
            if offset == 0.0:
                continue
            hx = _hole_x(H, lanes, i)
            j = max(k for k in range(len(bounds) - 1) if bounds[k] < hx)
            chk.rule(lanes[j][2] < hy,
                     f"{score} chute crosses the {lanes[j][0]} lane, which is "
                     "finished with by then")
        for part in design.parts:
            if part.name.startswith("return_chute"):
                v = part.mesh.v
                head = d.zp - v[:, 2].max()
                chk.rule(head >= B, f"{part.name}: {head:.1f} mm of headroom >= a ball")
                rise = v[:, 2].max() - v[:, 2].min()
                span = v[:, 0].max() - v[:, 0].min()
                angle = math.degrees(math.atan2(rise, span))
                chk.rule(angle >= 10.0,
                         f"{part.name}: {angle:.1f} deg of cross-slope >= 10 "
                         "(a ball will not roll off less)")
                # Its underside is flat while the ramp climbs under it.
                gap = (v[:, 1].max() - v[:, 1].min()) * math.tan(math.radians(d.slope))
                chk.rule(gap < B / 2,
                         f"{part.name}: {gap:.1f} mm gap beneath it < half a ball")
                # A chute eats into the lane it delivers to, and a lane
                # is only about a ball and a half wide. What is left
                # between its low edge and the lane's far wall has to be
                # wider than a ball, or the ball jams on the chute's edge
                # instead of rolling off it.
                xs, zs = v[:, 0], v[:, 2]
                left, right = xs.min(), xs.max()
                low_x, far = left, None
                if zs[xs <= left + 1e-6].max() > zs[xs >= right - 1e-6].max():
                    low_x = right
                for b0, b1 in zip(bounds, bounds[1:]):
                    if b0 <= low_x <= b1:
                        # The ball carries on the way the chute was falling,
                        # so the wall that stops it is the one beyond.
                        far = b0 if low_x == left else b1
                if far is None:
                    far = min(bounds, key=lambda b: abs(b - low_x))
                channel = abs(far - low_x) - fin_t / 2
                chk.rule(channel >= B + 0.5,
                         f"{part.name}: {channel:.1f} mm of lane left beyond "
                         f"its low edge, room for a {B:.1f} mm ball")
            if part.name.startswith("lane_fin"):
                top = part.mesh.v[:, 2].max()
                chk.rule(abs(top - d.zp) < 1e-6, f"{part.name} reaches the slab above")
        scored = sorted(lane[0] for lane in lanes)
        chk.rule(scored == sorted(s_ for s_, _x, _y in H),
                 "every score has somewhere to land")

    # --- 12. the scoreboard works as a mechanism ------------------------
    if not coupon:
        neck, shaft = 2 * d.sb_neck_r, 2 * d.sb_shaft_r
        chk.rule(neck >= shaft, f"marker shaft {shaft:.2f} passes the {neck:.2f} mm neck")
        chk.rule(neck - shaft <= 0.4, "marker is a friction fit, not a rattle")
        chk.rule(2 * d.sb_foot_r > neck,
                 f"marker foot {2 * d.sb_foot_r:.2f} > neck {neck:.2f}: it cannot come out")
        chk.rule(d.sb_foot_t < d.sb_track_t, "marker foot runs free in its channel")
        chk.rule(2 * d.sb_foot_r < 2 * d.sb_track_r, "marker foot fits the channel width")
        chk.rule(d.sb_pitch > 2 * d.sb_knob_r,
                 "neighbouring markers do not touch, so a reading is unambiguous")
        chk.rule(d.sb_bay_r > d.sb_neck_r, "a bay is wider than a neck, so it reads")
        chk.rule(d.sb_row_pitch - 2 * d.sb_track_r >= 4 * spec.printer.nozzle,
                 "material left between the channels")
        reach = sum(9 * 10 ** i for i in range(d.sb_rows))
        chk.rule(reach >= 999, f"scoreboard reaches {reach}")
        for nm in ("score_back", "score_track", "score_face", "score_marker"):
            chk.rule(any(r_["file"] == nm + ".stl" for r_ in rows), f"{nm} is emitted")

    # --- 9b. the assembled table is symmetric ---------------------------
    # Left-hand parts are built by mirroring right-hand ones, which is easy
    # to get subtly wrong: a mirrored profile placed at an unmirrored origin
    # is the right shape in the wrong place, so it still prints, still fits
    # the bed and still passes every other rule here.
    by_name = {p.name: p for p in design.parts}
    for part in design.parts:
        if "_left" not in part.name:
            continue
        twin = by_name.get(part.name.replace("_left", "_right"))
        chk.rule(twin is not None, f"{part.name} has a right-hand twin")
        if twin is None:
            continue
        lo, hi = part.mesh.v.min(0), part.mesh.v.max(0)
        tlo, thi = twin.mesh.v.min(0), twin.mesh.v.max(0)
        mirrored = (abs(lo[0] + thi[0]) < 1e-6 and abs(hi[0] + tlo[0]) < 1e-6
                    and abs(lo[1] - tlo[1]) < 1e-6 and abs(hi[2] - thi[2]) < 1e-6)
        chk.rule(mirrored, f"{part.name} sits opposite {twin.name} "
                           f"(x {lo[0]:.1f}..{hi[0]:.1f} vs {tlo[0]:.1f}..{thi[0]:.1f})")
    span = [(p_.mesh.v.min(0)[0], p_.mesh.v.max(0)[0]) for p_ in design.parts
            if p_.role in ("frame", "rail", "playfield", "ramp")]
    if span:
        chk.rule(abs(min(s_[0] for s_ in span) + max(s_[1] for s_ in span)) < 1e-6,
                 "the assembled table is centred on x = 0")

    # --- 10. printability ----------------------------------------------
    chk.rule(not any(r_["supports"] == "yes" for r_ in rows), "no part needs supports")
    if not coupon:
        pf = [r_ for r_ in rows if r_["file"].startswith("playfield")]
        chk.rule(all(r_["plate"] == ("smooth" if spec.felt <= 0 else "textured") for r_ in pf),
                 "playfield tiles ask for the right build plate")
        chk.rule(len(pf) == (len(design.cuts["playfield_x"]) - 1)
                 * (len(design.cuts["playfield_y"]) - 1), "every playfield tile is emitted")


def sweep() -> int:
    """Every size x variant x printer, quietly: just the failures."""
    bad = 0
    combos = [(p_, s_, v_, r_) for p_ in P.PRINTERS for s_ in P.SIZES
              for v_ in ("simple", "full") for r_ in (False, True)]
    for pkey, skey, variant, sorted_return in combos:
                spec = T.Spec(size=P.size(skey), printer=P.printer(pkey),
                              material=P.material("pla"), variant=variant,
                              cues=1 if variant == "simple" else 2,
                              sorted_return=sorted_return)
                label = (f"{pkey:<8} {skey:<9} {variant:<7} "
                         f"{'sorted' if sorted_return else 'shared'}")
                try:
                    design = T.design(spec)
                    rows = bb.measure(design)
                except SystemExit as exc:
                    print(f"FAIL  {label}  {exc}")
                    bad += 1
                    continue
                chk = Checker(verbose=False)
                run(design, rows, chk)
                if chk.fails:
                    bad += 1
                    print(f"FAIL  {label}  {len(chk.fails)}/{chk.count}: {chk.fails[0]}")
                else:
                    print(f"ok    {label}  {chk.count} rules, {len(rows)} files")
    print(f"\n{bad} failing combination(s)")
    return bad


def main(argv=None) -> int:
    ap = bb.parser()
    ap.add_argument("--all", action="store_true",
                    help="sweep every size, variant and printer")
    args = ap.parse_args(argv)
    if args.all:
        return 1 if sweep() else 0
    design = bb.build(args)
    rows = bb.measure(design)
    chk = Checker()
    run(design, rows, chk)
    print(f"\n{len(chk.fails)} failure(s) in {chk.count} rules "
          f"({design.spec.size.key}, {design.spec.variant}, {design.spec.printer.key})")
    return 1 if chk.fails else 0


if __name__ == "__main__":
    sys.exit(main())
