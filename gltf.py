#!/usr/bin/env python3
"""Export the same model the printer gets, as a glTF binary for the game.

    python gltf.py                      # -> godot/assets/, life size
    python gltf.py --size standard      # the table you are actually printing
    python gltf.py --return sorted

`table.py` is the one model. The STL exporter slices it into printable
pieces; this writes the *assembled* thing as a single `.glb`, plus the
`layout.json` the game needs to know where the holes and spots are. Nothing
is modelled twice, so a change to the table shows up in both.

Two things change on the way out:

* **Life size.** The game defaults to a real league table (47.6 mm ball,
  800 x 1420 mm bed) rather than a desk-sized one. Godot's physics is
  happiest around human scale, and in VR you want to stand at a real table.
  It is the same generator either way — only `--ball` differs.
* **Metres, Y up.** Millimetres and Z-up become metres and Y-up, which is
  what glTF and Godot expect.

Faces are flat-shaded on purpose: a printed object has facets, and it saves
sharing vertices between faces that disagree about their normal.
"""
from __future__ import annotations

import json
import os
import struct

import numpy as np

import barbilliards as bb
import table as T

REAL_BALL = 47.6              # a league ball: the game's default scale
MM = 0.001                    # millimetres -> metres

#: Parts that belong in the playing scene. The cue, the clamps and the
#: scoreboard are parked off to one side in the assembled model, so they
#: would show up in mid-air; the game supplies its own.
SCENE_ROLES = ("playfield", "frame", "ramp", "rail", "play")
SKIP = ("cue_", "clamp_", "desk_clamp", "score_", "test_", "skittle", "hole_ring")


def srgb_to_linear(c: float) -> float:
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def hex_linear(h: str):
    h = h.lstrip("#")
    return [srgb_to_linear(int(h[i:i + 2], 16) / 255.0) for i in (0, 2, 4)] + [1.0]


def to_gltf_space(v: np.ndarray, scale=MM) -> np.ndarray:
    """Z-up millimetres -> Y-up metres. A rotation, so winding is unchanged."""
    out = np.empty_like(v)
    out[:, 0] = v[:, 0] * scale
    out[:, 1] = v[:, 2] * scale
    out[:, 2] = -v[:, 1] * scale
    return out


def flat_triangles(mesh):
    """(positions, normals) with one vertex per corner and a per-face normal."""
    v = to_gltf_space(mesh.v)
    tri = v[mesh.f]                                   # (n, 3, 3)
    n = np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0])
    length = np.linalg.norm(n, axis=1, keepdims=True)
    length[length == 0] = 1.0
    n = n / length
    return (tri.reshape(-1, 3).astype("<f4"),
            np.repeat(n, 3, axis=0).astype("<f4"))


class GLB:
    """A minimal glTF 2.0 binary writer: meshes, flat normals, flat colours."""

    def __init__(self):
        self.bin = bytearray()
        self.views, self.accessors = [], []
        self.meshes, self.nodes, self.materials = [], [], []
        self._material_of = {}

    def _view(self, data: bytes) -> int:
        while len(self.bin) % 4:
            self.bin.append(0)
        self.views.append(dict(buffer=0, byteOffset=len(self.bin), byteLength=len(data)))
        self.bin.extend(data)
        return len(self.views) - 1

    def _accessor(self, arr: np.ndarray) -> int:
        view = self._view(arr.tobytes())
        self.accessors.append(dict(
            bufferView=view, componentType=5126, count=len(arr), type="VEC3",
            min=[float(x) for x in arr.min(0)], max=[float(x) for x in arr.max(0)]))
        return len(self.accessors) - 1

    def material(self, colour: str) -> int:
        if colour not in self._material_of:
            self.materials.append(dict(
                name=colour,
                pbrMetallicRoughness=dict(baseColorFactor=hex_linear(colour),
                                          metallicFactor=0.0, roughnessFactor=0.75),
                doubleSided=False))
            self._material_of[colour] = len(self.materials) - 1
        return self._material_of[colour]

    def add(self, name: str, mesh, colour: str, extras=None):
        pos, nrm = flat_triangles(mesh)
        self.meshes.append(dict(name=name, primitives=[dict(
            attributes=dict(POSITION=self._accessor(pos), NORMAL=self._accessor(nrm)),
            material=self.material(colour), mode=4)]))
        node = dict(name=name, mesh=len(self.meshes) - 1)
        if extras:
            node["extras"] = extras
        self.nodes.append(node)

    def add_point(self, name: str, xyz, extras=None):
        """An empty node — a spot the game needs to know about."""
        p = to_gltf_space(np.asarray([xyz], float))[0]
        node = dict(name=name, translation=[float(x) for x in p])
        if extras:
            node["extras"] = extras
        self.nodes.append(node)

    def write(self, path: str, extras=None):
        while len(self.bin) % 4:
            self.bin.append(0)
        doc = dict(
            asset=dict(version="2.0", generator="pocket_bar_billiards/gltf.py"),
            scene=0, scenes=[dict(nodes=list(range(len(self.nodes))))],
            nodes=self.nodes, meshes=self.meshes, materials=self.materials,
            accessors=self.accessors, bufferViews=self.views,
            buffers=[dict(byteLength=len(self.bin))])
        if extras:
            doc["extras"] = extras
        js = json.dumps(doc, separators=(",", ":")).encode()
        js += b" " * (-len(js) % 4)
        total = 12 + 8 + len(js) + 8 + len(self.bin)
        with open(path, "wb") as fh:
            fh.write(struct.pack("<4sII", b"glTF", 2, total))
            fh.write(struct.pack("<II", len(js), 0x4E4F534A))      # 'JSON'
            fh.write(js)
            fh.write(struct.pack("<II", len(self.bin), 0x004E4942))  # 'BIN'
            fh.write(self.bin)
        return total


def build(design: T.Design) -> GLB:
    """The assembled table, plus an empty node at every hole and spot."""
    glb = GLB()
    lay, d = design.layout, design.dims
    for part in design.parts:
        if part.role not in SCENE_ROLES or part.name.startswith(SKIP):
            continue
        glb.add(part.name, part.mesh, part.colour, extras=dict(role=part.role))

    peg = next((p for p in design.parts if p.name.startswith("skittle")), None)
    if peg is not None:
        bx, by = lay["peg_black"]
        glb.add("skittle_black", peg.mesh, T.PALETTE["skittle_black"],
                extras=dict(role="skittle", colour="black"))
        for i, (wx, wy) in enumerate(lay["peg_white"]):
            glb.add(f"skittle_white_{i + 1}", peg.mesh.translate(wx - bx, wy - by, 0),
                    T.PALETTE["skittle_white"], extras=dict(role="skittle", colour="white"))

    for score, x, y in design.holes:
        glb.add_point(f"hole_{score}_{x:.0f}", (x, y, d.zt),
                      extras=dict(role="hole", score=score, radius=d.hole_open / 2 * MM))
    glb.add_point("spot_d", (*lay["d_spot"], d.zt + d.felt), extras=dict(role="spot"))
    glb.add_point("spot_red", (*lay["red_spot"], d.zt + d.felt), extras=dict(role="spot"))
    return glb


def game_layout(design: T.Design) -> dict:
    """What the game needs that the mesh does not say: sizes, spots, rules."""
    d, lay = design.dims, design.layout
    return dict(
        units="metres", up="+Y", player_at="+Z",
        ball_diameter=d.ball * MM, ball_radius=d.ball / 2 * MM,
        playing_width=d.width * MM, playing_length=d.length * MM,
        surface_y=(d.zt + d.felt) * MM,
        cushion_y=d.cush_z * MM,
        hole_radius=d.hole_open / 2 * MM,
        holes=[dict(score=s, x=x * MM, z=-y * MM) for s, x, y in design.holes],
        d_spot=dict(x=lay["d_spot"][0] * MM, z=-lay["d_spot"][1] * MM),
        red_spot=dict(x=lay["red_spot"][0] * MM, z=-lay["red_spot"][1] * MM),
        d_radius=lay["d_radius"] * MM,
        baulk_z=-lay["baulk_y"] * MM,
        skittles=[dict(colour="black", x=lay["peg_black"][0] * MM,
                       z=-lay["peg_black"][1] * MM)]
        + [dict(colour="white", x=w[0] * MM, z=-w[1] * MM) for w in lay["peg_white"]],
        skittle_cap_radius=d.peg_cap / 2 * MM,
        return_lanes=[dict(score=la["score"], x0=la["x0"] * MM, x1=la["x1"] * MM)
                      for la in lay.get("return_lanes", [])],
        scale_vs_real=round(d.ball / T.REAL_BALL, 4),
    )


def main(argv=None) -> int:
    ap = bb.parser()
    ap.set_defaults(out="godot/assets", bed=4000, size="standard")
    ap.add_argument("--game-ball", type=float, default=REAL_BALL,
                    help="ball diameter for the exported scene, mm "
                         f"(default {REAL_BALL} = a real league table)")
    ap.add_argument("--as-printed", action="store_true",
                    help="export at the printed size instead of life size")
    args = ap.parse_args(argv)
    if not args.as_printed and args.ball is None:
        args.ball = args.game_ball
    design = bb.build(args)

    os.makedirs(args.out, exist_ok=True)
    glb = build(design)
    size = glb.write(os.path.join(args.out, "table.glb"),
                     extras=dict(generator="pocket_bar_billiards"))
    layout = game_layout(design)
    with open(os.path.join(args.out, "table_layout.json"), "w", encoding="utf-8") as fh:
        json.dump(layout, fh, indent=1)

    tris = sum(glb.accessors[prim["attributes"]["POSITION"]]["count"] // 3
               for m in glb.meshes for prim in m["primitives"])
    print(f"{args.out}/table.glb  {size / 1024:.0f} kB  "
          f"{len(glb.meshes)} meshes, ~{tris} triangles")
    print(f"ball {design.dims.ball:.1f} mm, playing area "
          f"{design.dims.width / 1000:.2f} x {design.dims.length / 1000:.2f} m "
          f"(1:{1 / design.dims.scale:.2f})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
