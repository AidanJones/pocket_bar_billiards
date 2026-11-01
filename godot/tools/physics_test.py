#!/usr/bin/env python3
"""Run the ball-return physics test in the Godot container.

    python godot/tools/physics_test.py                 # the shared return
    python godot/tools/physics_test.py --return sorted # the scored lanes

Regenerates `assets/table.glb` from the Python model first, so the thing
being simulated is always the thing the printer would get, then drops a ball
through each of the nine holes in turn and reports where it came to rest.
Exits non-zero if a ball never reaches the tray, or — with the sorted
return — lands in the wrong lane.

This is the check `check.py` cannot do: geometry rules can prove a lane is
wide enough, not that a dropped ball actually ends up in it.
"""
from __future__ import annotations

import argparse
import pathlib
import subprocess
import sys

GODOT = pathlib.Path(__file__).resolve().parent.parent
REPO = GODOT.parent


def run(cmd, **kw) -> int:
    print("$", " ".join(str(c) for c in cmd), flush=True)
    return subprocess.call(cmd, **kw)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--return", dest="ball_return", default="shared",
                    choices=("shared", "sorted"))
    ap.add_argument("--size", default="standard")
    ap.add_argument("--as-printed", action="store_true",
                    help="simulate the printed size rather than life size")
    ap.add_argument("--seconds", type=float, default=90.0,
                    help="give up after this long")
    ap.add_argument("--skip-export", action="store_true")
    args = ap.parse_args(argv)

    if not args.skip_export:
        export = [sys.executable, str(REPO / "gltf.py"),
                  "--size", args.size, "--return", args.ball_return,
                  "--out", str(GODOT / "assets")]
        if args.as_printed:
            export.append("--as-printed")
        if run(export, cwd=REPO):
            return 1

    # Only a safety net: the test quits itself when it has run every hole.
    # Headless Godot free-runs, so allow plenty of iterations per second of
    # simulated time or the engine stops before the report is printed.
    ticks = int(args.seconds * 400)
    return run(["docker", "compose", "run", "--rm", "godot",
                "--headless", "--quit-after", str(ticks), "--", "--smoke"],
               cwd=GODOT)


if __name__ == "__main__":
    raise SystemExit(main())
