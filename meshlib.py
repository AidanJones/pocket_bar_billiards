"""Tiny dependency-light mesh toolkit (numpy only).

Builds watertight solids by construction rather than CSG:
  * prism()  - a 2D polygon (with holes) extruded along an axis
  * lathe()  - a 2D (r, z) profile revolved about the Z axis
Plus a binary STL writer and a manifold checker.
"""
import math
import struct

import numpy as np


# ----------------------------------------------------------------- 2D helpers
def area2(poly):
    p = np.asarray(poly, float)
    x, y = p[:, 0], p[:, 1]
    return float(np.dot(x, np.roll(y, -1)) - np.dot(np.roll(x, -1), y))


def ccw(poly):
    return list(poly) if area2(poly) > 0 else list(poly)[::-1]


def cw(poly):
    return list(poly)[::-1] if area2(poly) > 0 else list(poly)


def circle(cx, cy, r, n=48, start=0.0):
    """Circumscribed polygon so printed holes are never undersized."""
    rr = r / math.cos(math.pi / n)
    return [(cx + rr * math.cos(start + 2 * math.pi * i / n),
             cy + rr * math.sin(start + 2 * math.pi * i / n)) for i in range(n)]


def rect(x0, y0, x1, y1):
    return [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]


def _seg_intersect(p, q, A, B, eps=1e-9):
    """Does segment p-q properly cross any of the segments A[i]-B[i]?"""
    d = q - p
    e = B - A
    den = d[0] * e[:, 1] - d[1] * e[:, 0]
    w = A - p
    with np.errstate(divide="ignore", invalid="ignore"):
        t = (w[:, 0] * e[:, 1] - w[:, 1] * e[:, 0]) / den
        u = (w[:, 0] * d[1] - w[:, 1] * d[0]) / den
    ok = (np.abs(den) > eps) & (t > eps) & (t < 1 - eps) & (u > eps) & (u < 1 - eps)
    return bool(ok.any())


def triangulate(outer, holes=()):
    """Ear-clipping triangulation of a polygon with holes.

    Returns (points Nx2, triangles Mx3, loops) where loops are index lists
    (outer CCW, holes CW) used to build the side walls of a prism."""
    outer = ccw(outer)
    holes = [cw(h) for h in holes]
    pts = list(outer)
    loops = [list(range(len(outer)))]
    hole_idx = []
    for h in holes:
        s = len(pts)
        pts.extend(h)
        idx = list(range(s, s + len(h)))
        hole_idx.append(idx)
        loops.append(idx)
    P = np.asarray(pts, float)

    poly = list(loops[0])
    # bridge holes, rightmost first
    order = sorted(range(len(hole_idx)), key=lambda k: -P[hole_idx[k], 0].max())
    remaining = [hole_idx[k] for k in order]
    while remaining:
        h = remaining.pop(0)
        m_local = int(np.argmax(P[h, 0]))
        M = P[h[m_local]]
        # all edges currently present (poly + remaining holes + this hole)
        edges = [(poly[i], poly[(i + 1) % len(poly)]) for i in range(len(poly))]
        for hh in remaining + [h]:
            edges += [(hh[i], hh[(i + 1) % len(hh)]) for i in range(len(hh))]
        A = P[[a for a, _ in edges]]
        B = P[[b for _, b in edges]]
        cand = sorted(range(len(poly)), key=lambda i: np.sum((P[poly[i]] - M) ** 2))
        chosen = None
        for i in cand:
            Q = P[poly[i]]
            if np.allclose(Q, M):
                continue
            if not _seg_intersect(M, Q, A, B):
                chosen = i
                break
        if chosen is None:
            raise RuntimeError("could not bridge hole")
        hp = h[m_local:] + h[:m_local + 1]
        poly = poly[:chosen + 1] + hp + [poly[chosen]] + poly[chosen + 1:]

    # ear clipping
    tris = []
    V = list(poly)
    guard = 0
    while len(V) > 3:
        n = len(V)
        found = False
        for i in range(n):
            ia, ib, ic = V[i - 1], V[i], V[(i + 1) % n]
            a, b, c = P[ia], P[ib], P[ic]
            cr = (b[0] - a[0]) * (c[1] - b[1]) - (b[1] - a[1]) * (c[0] - b[0])
            if cr <= 1e-12:
                continue
            others = [v for v in V if v not in (ia, ib, ic)]
            if others:
                Q = P[others]
                d1 = (b[0] - a[0]) * (Q[:, 1] - a[1]) - (b[1] - a[1]) * (Q[:, 0] - a[0])
                d2 = (c[0] - b[0]) * (Q[:, 1] - b[1]) - (c[1] - b[1]) * (Q[:, 0] - b[0])
                d3 = (a[0] - c[0]) * (Q[:, 1] - c[1]) - (a[1] - c[1]) * (Q[:, 0] - c[0])
                inside = (d1 >= -1e-9) & (d2 >= -1e-9) & (d3 >= -1e-9)
                # coincident duplicates (bridge endpoints) are fine
                same = np.all(np.isclose(Q[:, None, :], np.array([a, b, c])[None]), axis=2).any(1)
                if (inside & ~same).any():
                    continue
            tris.append((ia, ib, ic))
            del V[i]
            found = True
            break
        if not found:
            # drop a degenerate (collinear) vertex and carry on
            for i in range(len(V)):
                a, b, c = P[V[i - 1]], P[V[i]], P[V[(i + 1) % len(V)]]
                cr = (b[0] - a[0]) * (c[1] - b[1]) - (b[1] - a[1]) * (c[0] - b[0])
                if abs(cr) < 1e-9:
                    del V[i]
                    found = True
                    break
        if not found:
            raise RuntimeError("ear clipping failed")
        guard += 1
        if guard > 100000:
            raise RuntimeError("ear clipping runaway")
    tris.append(tuple(V))
    return P, np.asarray(tris, int), loops


# --------------------------------------------------------------------- meshes
class Mesh:
    def __init__(self, v, f, name="part"):
        self.v = np.asarray(v, float)
        self.f = np.asarray(f, int)
        self.name = name

    def volume(self):
        a, b, c = self.v[self.f[:, 0]], self.v[self.f[:, 1]], self.v[self.f[:, 2]]
        return float(np.einsum("ij,ij->i", a, np.cross(b, c)).sum() / 6.0)

    def area(self, flat=None):
        """Surface area. `flat=True`/`False` splits it by face orientation.

        "Flat" means roughly parallel to the bed (|nz| > 0.7), which is what
        decides whether a face costs solid layers or perimeters.
        """
        a, b, c = self.v[self.f[:, 0]], self.v[self.f[:, 1]], self.v[self.f[:, 2]]
        n = np.cross(b - a, c - a)
        mag = np.linalg.norm(n, axis=1)
        keep = np.ones(len(mag), bool)
        if flat is not None:
            with np.errstate(divide="ignore", invalid="ignore"):
                nz = np.abs(np.where(mag > 0, n[:, 2] / np.where(mag > 0, mag, 1), 0))
            keep = (nz > 0.7) if flat else (nz <= 0.7)
        return float(mag[keep].sum() / 2.0)

    def fix_orientation(self):
        if self.volume() < 0:
            self.f = self.f[:, ::-1]
        return self

    def translate(self, dx=0, dy=0, dz=0):
        return Mesh(self.v + [dx, dy, dz], self.f.copy(), self.name)

    def mirror_x(self):
        v = self.v.copy()
        v[:, 0] *= -1
        return Mesh(v, self.f[:, ::-1].copy(), self.name)

    def rotate(self, axis, deg):
        """Rotate about a world axis through the origin ("x", "y" or "z")."""
        t = math.radians(deg)
        c, s = math.cos(t), math.sin(t)
        R = {"x": [[1, 0, 0], [0, c, -s], [0, s, c]],
             "y": [[c, 0, s], [0, 1, 0], [-s, 0, c]],
             "z": [[c, -s, 0], [s, c, 0], [0, 0, 1]]}[axis]
        return Mesh(self.v @ np.asarray(R, float).T, self.f.copy(), self.name)

    def to_bed(self):
        """Drop onto z=0 and centre in XY (for export)."""
        mn, mx = self.v.min(0), self.v.max(0)
        c = (mn + mx) / 2
        return self.translate(-c[0], -c[1], -mn[2])

    def extents(self):
        return self.v.max(0) - self.v.min(0)

    def check(self):
        """Return (watertight, consistently_oriented)."""
        e = np.concatenate([self.f[:, [0, 1]], self.f[:, [1, 2]], self.f[:, [2, 0]]])
        directed = {}
        for a, b in map(tuple, e):
            directed[(a, b)] = directed.get((a, b), 0) + 1
        oriented = all(c == 1 for c in directed.values())
        und = {}
        for (a, b), c in directed.items():
            k = (min(a, b), max(a, b))
            und[k] = und.get(k, 0) + c
        watertight = all(c == 2 for c in und.values())
        return watertight, oriented

    def write_stl(self, path):
        v, f = self.v, self.f
        with open(path, "wb") as fh:
            fh.write(self.name.encode()[:80].ljust(80, b" "))
            fh.write(struct.pack("<I", len(f)))
            for t in f:
                a, b, c = v[t[0]], v[t[1]], v[t[2]]
                n = np.cross(b - a, c - a)
                ln = np.linalg.norm(n)
                n = n / ln if ln > 0 else n
                fh.write(struct.pack("<12fH", *n, *a, *b, *c, 0))


_AX = {"x": 0, "y": 1, "z": 2}


def prism(outer, holes=(), w0=0.0, w1=1.0, plane="xy", name="prism"):
    """Extrude a 2D polygon (u, v) between w0 and w1.

    plane names the global axes u and v map to; w is the remaining axis,
    e.g. plane="xz" extrudes a profile drawn in X/Z along Y."""
    P, T, loops = triangulate(outer, holes)
    n = len(P)
    ui, vi = _AX[plane[0]], _AX[plane[1]]
    wi = 3 - ui - vi
    V = np.zeros((2 * n, 3))
    V[:n, ui], V[:n, vi], V[:n, wi] = P[:, 0], P[:, 1], w0
    V[n:, ui], V[n:, vi], V[n:, wi] = P[:, 0], P[:, 1], w1
    F = [T[:, ::-1], T + n]
    side = []
    for loop in loops:
        for i in range(len(loop)):
            p, q = loop[i], loop[(i + 1) % len(loop)]
            side.append((p, q, q + n))
            side.append((p, q + n, p + n))
    F.append(np.asarray(side, int))
    return Mesh(V, np.vstack(F), name).fix_orientation()


def lathe(profile, n=72, name="lathe"):
    """Revolve a closed (r, z) profile about the Z axis. Points with r == 0
    collapse onto the axis so the result is closed."""
    prof = ccw(profile)
    verts, rings = [], []
    for r, z in prof:
        if r < 1e-9:
            rings.append([len(verts)])
            verts.append((0.0, 0.0, z))
        else:
            ring = []
            for k in range(n):
                t = 2 * math.pi * k / n
                ring.append(len(verts))
                verts.append((r * math.cos(t), r * math.sin(t), z))
            rings.append(ring)
    F = []
    m = len(prof)
    for i in range(m):
        A, B = rings[i], rings[(i + 1) % m]
        if len(A) == 1 and len(B) == 1:
            continue
        for k in range(n):
            k1 = (k + 1) % n
            if len(A) == 1:
                F.append((A[0], B[k], B[k1]))
            elif len(B) == 1:
                F.append((A[k], B[0], A[k1]))
            else:
                F.append((A[k], B[k], B[k1]))
                F.append((A[k], B[k1], A[k1]))
    return Mesh(np.asarray(verts), np.asarray(F, int), name).fix_orientation()
