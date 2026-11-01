#!/usr/bin/env python3
"""Previews, the scored layout plan and the 1:1 felt template.

    python render.py                        # -> previews/ for the default build
    python render.py --out previews --size standard
    python render.py --coupon               # just the coupon, laid out on a plate

Takes every `barbilliards.py` option, so the pictures always match the STLs.
A passing `check.py` does not prove the geometry *looks* right — open the
PNGs after any change.

The renderer is a small z-buffered software rasteriser, so the only
dependencies are numpy and matplotlib.
"""
from __future__ import annotations

import math
import os

import matplotlib
import numpy as np

matplotlib.use("Agg")
import matplotlib.pyplot as plt                                    # noqa: E402
from matplotlib.backends.backend_pdf import PdfPages                # noqa: E402
from matplotlib.patches import Arc, Circle, Rectangle               # noqa: E402

import barbilliards as bb                                           # noqa: E402
import table as T                                                   # noqa: E402
from meshlib import lathe, prism, rect                               # noqa: E402

PAGE_W, PAGE_H, PAGE_M = 210.0, 297.0, 12.0        # A4 portrait, mm


def hexrgb(h):
    h = h.lstrip("#")
    return np.array([int(h[i:i + 2], 16) for i in (0, 2, 4)]) / 255.0


# ----------------------------------------------------------------- assembly
def scene(design: T.Design, exploded=False, cutaway=False, desk=True):
    """[(mesh, rgb)] for the whole table, in assembled position."""
    lay = design.layout
    skip = ("cue_", "clamp_shim", "skittle", "hole_ring", "test_")
    items = []
    for part in design.parts:
        if part.name.startswith(skip):
            continue
        if part.name.startswith("desk_clamp") and not part.name.endswith(
                f"_{design.spec.desk:.0f}mm"):
            continue
        if cutaway and part.role in ("playfield", "rail"):
            continue
        dz = 0
        if exploded:
            dz = 70 if part.role == "rail" else 35 if part.role == "playfield" else 0
        mesh = part.mesh.translate(0, 0, dz)
        items.append((mesh, hexrgb(part.colour)))
        if part.name.startswith("desk_clamp"):
            items.append((mesh.mirror_x(), hexrgb(part.colour)))

    if not cutaway:
        lift = 35 if exploded else 0
        ring = next((p for p in design.parts if p.name.startswith("hole_ring")), None)
        if ring is not None:
            for score, x, y in design.holes:
                items.append((ring.mesh.translate(x, y, lift),
                              hexrgb(T.RING_COLOUR[score])))
        peg = next((p for p in design.parts if p.name.startswith("skittle")), None)
        if peg is not None:
            bx, by = lay["peg_black"]
            items.append((peg.mesh.translate(0, 0, lift),
                          hexrgb(T.PALETTE["skittle_black"] if design.spec.rings
                                 else peg.colour)))
            for wx, wy in lay["peg_white"]:
                items.append((peg.mesh.translate(wx - bx, wy - by, lift),
                              hexrgb(T.PALETTE["skittle_white"] if design.spec.rings
                                     else peg.colour)))
    if desk and not exploded:
        o = lay["overall"]
        slab = prism(rect(o["x0"] - 60, o["y0"], o["x1"] + 60, o["y1"] + 90), [],
                     -25, 0, "xy")
        items.append((slab, hexrgb("#d9c7a7")))
    return items


def plate_scene(design: T.Design):
    """Every piece in its print pose on its build plate, plates side by side."""
    pr = design.spec.printer
    width, height = pr.usable
    items = []
    for i, (material, placed) in enumerate(bb.pack_plates(design)):
        dx = i * (pr.bed[0] + 40)
        shade = "#3b3b3b" if material == design.spec.material.key else "#2b3b45"
        items.append((prism(rect(dx - pr.edge_margin, -pr.edge_margin,
                                 dx + width + pr.edge_margin, height + pr.edge_margin),
                            [], -4, -1, "xy"), hexrgb(shade)))
        for part, mesh in placed:
            items.append((mesh.translate(dx, 0, 0), hexrgb(part.colour)))
    return items


def ball_mesh(r, n=18):
    prof = ([(0, -r)]
            + [(r * math.cos(t), r * math.sin(t))
               for t in np.linspace(-math.pi / 2, math.pi / 2, n)[1:-1]]
            + [(0, r)])
    return lathe(prof, 24)


def render(items, view, path, size=(1600, 1100), balls=()):
    """Orthographic z-buffered render. `view` is (azimuth, elevation) degrees."""
    az, el = view
    a, e = math.radians(az), math.radians(el)
    fwd = np.array([math.cos(e) * math.sin(a), math.cos(e) * math.cos(a), math.sin(e)])
    up = np.array([0.0, 0.0, 1.0]) - fwd * fwd[2]
    up /= np.linalg.norm(up)
    right = np.cross(up, fwd)
    light = np.array([-0.35, -0.55, 0.75])
    light /= np.linalg.norm(light)

    items = list(items) + [(bm, hexrgb(col)) for bm, col in balls]
    V = np.vstack([m.v for m, _ in items])
    proj = np.stack([V @ right, V @ up], 1)
    mn, mx = proj.min(0), proj.max(0)
    W, H = size
    scale = 0.9 * min(W / (mx[0] - mn[0]), H / (mx[1] - mn[1]))
    cen = (mn + mx) / 2

    img = np.ones((H, W, 3)) * np.array([0.965, 0.955, 0.94])
    zb = np.full((H, W), -1e9)
    for m, col in items:
        v = m.v
        sx = (v @ right - cen[0]) * scale + W / 2
        sy = H / 2 - (v @ up - cen[1]) * scale
        depth = v @ fwd
        tri = m.f
        p0, p1, p2 = v[tri[:, 0]], v[tri[:, 1]], v[tri[:, 2]]
        nrm = np.cross(p1 - p0, p2 - p0)
        nl = np.linalg.norm(nrm, axis=1, keepdims=True)
        nl[nl == 0] = 1
        nrm = nrm / nl
        facing = nrm @ fwd
        shade = 0.38 + 0.62 * np.clip(nrm @ light, 0, 1)
        for k in np.nonzero(facing > 1e-6)[0]:
            i0, i1, i2 = tri[k]
            xs = np.array([sx[i0], sx[i1], sx[i2]])
            ys = np.array([sy[i0], sy[i1], sy[i2]])
            zs = np.array([depth[i0], depth[i1], depth[i2]])
            x0, x1 = max(int(xs.min()), 0), min(int(xs.max()) + 1, W - 1)
            y0, y1 = max(int(ys.min()), 0), min(int(ys.max()) + 1, H - 1)
            if x1 < x0 or y1 < y0:
                continue
            gx, gy = np.meshgrid(np.arange(x0, x1 + 1) + 0.5, np.arange(y0, y1 + 1) + 0.5)
            den = (ys[1] - ys[2]) * (xs[0] - xs[2]) + (xs[2] - xs[1]) * (ys[0] - ys[2])
            if abs(den) < 1e-12:
                continue
            w0 = ((ys[1] - ys[2]) * (gx - xs[2]) + (xs[2] - xs[1]) * (gy - ys[2])) / den
            w1 = ((ys[2] - ys[0]) * (gx - xs[2]) + (xs[0] - xs[2]) * (gy - ys[2])) / den
            w2 = 1 - w0 - w1
            inside = (w0 >= -1e-4) & (w1 >= -1e-4) & (w2 >= -1e-4)
            if not inside.any():
                continue
            z = w0 * zs[0] + w1 * zs[1] + w2 * zs[2]
            sub = zb[y0:y1 + 1, x0:x1 + 1]
            upd = inside & (z > sub)
            if upd.any():
                sub[upd] = z[upd]
                img[y0:y1 + 1, x0:x1 + 1][upd] = col * shade[k]
    # cheap outlines from depth discontinuities
    zz = zb.copy()
    bg = zz < -1e8
    zz[bg] = zz[~bg].min() - 50
    gx = np.abs(np.diff(zz, axis=1, prepend=zz[:, :1]))
    gy = np.abs(np.diff(zz, axis=0, prepend=zz[:1]))
    img[(gx + gy) > 2.5] *= 0.55
    plt.imsave(path, np.clip(img, 0, 1))
    return path


# -------------------------------------------------------------- layout plan
def layout_plan(design: T.Design, path):
    d, lay = design.dims, design.layout
    felt = lay["felt"]
    fig, ax = plt.subplots(figsize=(6.2, 10))
    ax.add_patch(Rectangle((felt["x0"], felt["y0"]), felt["x1"] - felt["x0"],
                           felt["y1"] - felt["y0"], fc="#2f6b3a", ec="#5b3a1e", lw=6))
    for score, x, y in design.holes:
        ax.add_patch(Circle((x, y), d.hole_r + 2, fc=T.RING_COLOUR[score], ec="#111", lw=0.8))
        ax.add_patch(Circle((x, y), d.hole_open / 2, fc="#0d1a10"))
        ax.text(x, y + d.hole_d * 0.95, str(score), ha="center", va="bottom",
                color="white", fontsize=10, fontweight="bold")
    for xy, fc, ec in [(lay["peg_black"], "#222", "#000")] + \
                      [(w, "#f4f4f4", "#555") for w in lay["peg_white"]]:
        ax.add_patch(Circle(xy, d.peg_cap / 2, fc=fc, ec=ec, lw=1, alpha=0.95))
    for w in lay["peg_white_alt"]:
        ax.add_patch(Circle(w, d.peg_cap / 2, fc="none", ec="#f4f4f4", ls="--", lw=1))
    ax.plot([felt["x0"], felt["x1"]], [lay["baulk_y"]] * 2, color="white", lw=0.8)
    ax.add_patch(Arc((0, lay["baulk_y"]), 2 * lay["d_radius"], 2 * lay["d_radius"],
                     theta1=180, theta2=360, color="white", lw=0.8))
    ax.add_patch(Circle(lay["d_spot"], 1.6, fc="white"))
    ax.add_patch(Circle(lay["red_spot"], 1.6, fc="#e74c3c"))
    ax.text(0, lay["d_spot"][1] - lay["d_radius"] - 8, "D  (play from here)",
            color="white", ha="center", fontsize=8)
    ax.text(lay["red_spot"][0] + 5, lay["red_spot"][1], "red spot", color="#ffb3a8",
            fontsize=8, va="center")
    ax.text(lay["peg_white_alt"][1][0], lay["peg_white_alt"][1][1] - 16,
            "alt. white\nposition", color="#dfe", fontsize=6.5, ha="center", va="top")
    ax.annotate("", xy=(felt["x1"] + 14, felt["y0"]), xytext=(felt["x1"] + 14, felt["y1"]),
                arrowprops=dict(arrowstyle="<->", lw=0.8))
    ax.text(felt["x1"] + 18, (felt["y0"] + felt["y1"]) / 2, f"{d.length:.0f} mm",
            rotation=90, va="center", fontsize=8)
    ax.annotate("", xy=(felt["x0"], felt["y1"] + 14), xytext=(felt["x1"], felt["y1"] + 14),
                arrowprops=dict(arrowstyle="<->", lw=0.8))
    ax.text(0, felt["y1"] + 18, f"{d.width:.0f} mm", ha="center", fontsize=8)
    ax.text(0, felt["y0"] - 26, "PLAYER END", ha="center", fontsize=9, fontweight="bold")
    ax.text(0, felt["y1"] + 26, f"{design.spec.size.name}  -  ball {d.ball:.2f} mm  -  "
            f"1:{1 / d.scale:.2f}", ha="center", fontsize=7, color="#555")
    ax.set_xlim(felt["x0"] - 20, felt["x1"] + 32)
    ax.set_ylim(felt["y0"] - 34, felt["y1"] + 34)
    ax.set_aspect("equal")
    ax.axis("off")
    fig.tight_layout()
    fig.savefig(path, dpi=160)
    plt.close(fig)


# ------------------------------------------------------------ felt template
def felt_template(design: T.Design, path):
    """True-scale cutting and marking template, tiled onto A4 (print at 100 %)."""
    d, lay = design.dims, design.layout
    felt = lay["felt"]
    vw, vh = PAGE_W - 2 * PAGE_M, PAGE_H - 2 * PAGE_M - 10
    x0, x1 = felt["x0"] - 6, felt["x1"] + 6
    y0, y1 = felt["y0"] - 6, felt["y1"] + 6
    nx, ny = math.ceil((x1 - x0) / vw), math.ceil((y1 - y0) / vh)
    with PdfPages(path) as pdf:
        fig = plt.figure(figsize=(PAGE_W / 25.4, PAGE_H / 25.4))
        fig.text(0.08, 0.92, "Desk bar billiards - felt & marking template",
                 fontsize=14, fontweight="bold")
        lines = [
            f"{design.spec.size.name} table   ball {d.ball:.2f} mm   "
            f"scale 1:{1 / d.scale:.2f}",
            f"playing area {d.width:.1f} x {d.length:.1f} mm",
            "",
            "PRINT AT 100% / 'Actual size' - check the 50 mm bar on every page.",
            "Pages are numbered row-col; tape them together on the",
            f"alignment crosses ({ny} rows x {nx} cols).",
            "",
            "Solid outline  = felt cut line (it butts up to the rail cushions).",
            f"Hole circles   = cut the felt at {d.hole_d:.1f} mm.",
            "Black dot      = black skittle.   White dots = white skittles.",
            "Dashed circles = alternative white position (in front of the 50s).",
            "Red dot = red-ball spot.   White dot in the D = starting spot.",
            "",
            "Mark the spots through the paper with an awl or a fine pen, then",
            "cut the holes with a sharp craft knife.",
        ]
        for i, t in enumerate(lines):
            fig.text(0.08, 0.86 - i * 0.025, t, fontsize=9, family="monospace")
        pdf.savefig(fig)
        plt.close(fig)

        for r in range(ny):
            for c in range(nx):
                fig = plt.figure(figsize=(PAGE_W / 25.4, PAGE_H / 25.4))
                ax = fig.add_axes([PAGE_M / PAGE_W, (PAGE_M + 10) / PAGE_H,
                                   vw / PAGE_W, vh / PAGE_H])
                vx0, vy1 = x0 + c * vw, y1 - r * vh
                ax.set_xlim(vx0, vx0 + vw)
                ax.set_ylim(vy1 - vh, vy1)
                ax.set_aspect("equal")
                ax.axis("off")
                ax.add_patch(Rectangle((felt["x0"], felt["y0"]), felt["x1"] - felt["x0"],
                                       felt["y1"] - felt["y0"], fc="none", ec="black", lw=1.0))
                for score, x, y in design.holes:
                    ax.add_patch(Circle((x, y), d.hole_r, fc="none", ec="black", lw=0.8))
                    ax.plot([x - 2, x + 2], [y, y], "k", lw=0.4)
                    ax.plot([x, x], [y - 2, y + 2], "k", lw=0.4)
                    ax.text(x, y + d.hole_r + 1.5, str(score), ha="center", fontsize=7)
                ax.add_patch(Circle(lay["peg_black"], 1.5, fc="black"))
                for w in lay["peg_white"]:
                    ax.add_patch(Circle(w, 1.5, fc="white", ec="black", lw=0.6))
                for w in lay["peg_white_alt"]:
                    ax.add_patch(Circle(w, d.peg_base / 2, fc="none", ec="black",
                                        ls="--", lw=0.5))
                ax.add_patch(Circle(lay["red_spot"], 1.5, fc="red"))
                ax.add_patch(Circle(lay["d_spot"], 1.2, fc="white", ec="black", lw=0.6))
                ax.plot([felt["x0"], felt["x1"]], [lay["baulk_y"]] * 2, "k", lw=0.5)
                ax.add_patch(Arc((0, lay["baulk_y"]), 2 * lay["d_radius"],
                                 2 * lay["d_radius"], theta1=180, theta2=360, lw=0.5))
                ax.plot([0, 0], [felt["y0"], felt["y1"]], color="0.7", lw=0.3, ls=":")
                for gx in np.arange(math.floor(x0 / 40) * 40, x1 + 40, 40):
                    for gy in np.arange(math.floor(y0 / 40) * 40, y1 + 40, 40):
                        ax.plot([gx - 3, gx + 3], [gy, gy], color="0.55", lw=0.3)
                        ax.plot([gx, gx], [gy - 3, gy + 3], color="0.55", lw=0.3)
                fig.text(PAGE_M / PAGE_W, 0.5 * PAGE_M / PAGE_H + 0.012,
                         f"page {r + 1}-{c + 1}   (row {r + 1} of {ny}, "
                         f"col {c + 1} of {nx})   far end is UP", fontsize=7)
                bar = fig.add_axes([0.62, 0.5 * PAGE_M / PAGE_H, 50 / PAGE_W, 4 / PAGE_H])
                bar.axis("off")
                bar.add_patch(Rectangle((0, 0), 1, 1, fc="black", transform=bar.transAxes))
                fig.text(0.62 + 52 / PAGE_W, 0.5 * PAGE_M / PAGE_H, "50 mm", fontsize=7)
                pdf.savefig(fig)
                plt.close(fig)
    return nx * ny


# -------------------------------------------------------------------- main
def main(argv=None) -> int:
    ap = bb.parser()
    ap.set_defaults(out="previews")
    args = ap.parse_args(argv)
    design = bb.build(args)
    bb.measure(design)                      # same gate as the exporter
    os.makedirs(args.out, exist_ok=True)
    out = lambda n: os.path.join(args.out, n)                       # noqa: E731

    plates = bb.pack_plates(design)
    if design.layout.get("coupon"):
        render(plate_scene(design), (0, 64), out("coupon_plate.png"), size=(1500, 1100))
        print(f"{args.out}/coupon_plate.png ({len(plates)} plate(s))")
        return 0

    d, lay = design.dims, design.layout
    balls = [(ball_mesh(d.ball / 2).translate(x, y, d.zt + d.felt + d.ball / 2), col)
             for x, y, col in [
                 (lay["red_spot"][0], lay["red_spot"][1], "#c0392b"),
                 (lay["d_spot"][0], lay["d_spot"][1], "#f6f1e3"),
                 (-0.22 * d.width, 0.60 * d.length, "#f6f1e3"),
                 (0.33 * d.width, 0.79 * d.length, "#f6f1e3")]]

    render(scene(design), (215, 36), out("preview_assembled.png"), balls=balls)
    render(scene(design, cutaway=True), (215, 36), out("preview_ball_return.png"))
    render(scene(design, exploded=True), (215, 28), out("preview_exploded.png"))
    render(plate_scene(design), (0, 64), out("preview_plates.png"),
           size=(420 * len(plates) + 420, 1100))
    layout_plan(design, out("layout_plan.png"))
    pages = felt_template(design, out("felt_template_A4.pdf"))
    print(f"{args.out}/: 4 renders ({len(plates)} build plate(s)), layout_plan.png, "
          f"felt_template_A4.pdf ({pages} template pages)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
