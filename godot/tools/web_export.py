#!/usr/bin/env python3
"""Export the game for the browser, and optionally serve it.

    python godot/tools/web_export.py            # -> web_export/index.html
    python godot/tools/web_export.py --serve    # ... and http://localhost:8070

The first run builds the `web` image, which pulls Godot's export templates
(~1 GB) — that layer is cached afterwards. The build is kept out of the
default image so the headless physics test stays a quick ~250 MB pull.
"""
from __future__ import annotations

import argparse
import os
import pathlib
import subprocess
import sys

GODOT = pathlib.Path(__file__).resolve().parent.parent
REPO = GODOT.parent
OUT = REPO / "web_export"


def run(cmd, **kw) -> int:
    print("$", " ".join(str(c) for c in cmd), flush=True)
    return subprocess.call(cmd, **kw)


# Files the container writes (web_export/, .godot/) belong to you, not root.
if hasattr(os, "getuid"):
    os.environ.setdefault("HOST_UID", str(os.getuid()))
    os.environ.setdefault("HOST_GID", str(os.getgid()))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--return", dest="ball_return", default="shared",
                    choices=("shared", "sorted"))
    ap.add_argument("--size", default="standard")
    ap.add_argument("--serve", action="store_true")
    ap.add_argument("--skip-export", action="store_true")
    args = ap.parse_args(argv)

    if not args.skip_export:
        if run([sys.executable, str(REPO / "gltf.py"), "--size", args.size,
                "--return", args.ball_return, "--out", str(GODOT / "assets")],
               cwd=REPO):
            return 1

    OUT.mkdir(exist_ok=True)
    if run(["docker", "compose", "--profile", "web", "build", "godot-web"], cwd=GODOT):
        return 1
    # Import once so the engine knows about the project, then export. The
    # compose file mounts ../web_export at /web_export, where the preset's
    # export_path (relative to /project) lands.
    run(["docker", "compose", "--profile", "web", "run", "--rm", "godot-web",
         "--headless", "--import"], cwd=GODOT)
    code = run(["docker", "compose", "--profile", "web", "run", "--rm", "godot-web",
                "--headless", "--export-release", "Web", "/web_export/index.html"],
               cwd=GODOT)
    if code:
        return code
    print(f"exported to {OUT}")
    if args.serve:
        print("serving on http://localhost:8070  (ctrl-c to stop)")
        return run(["docker", "compose", "--profile", "web", "up", "web-static"], cwd=GODOT)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
