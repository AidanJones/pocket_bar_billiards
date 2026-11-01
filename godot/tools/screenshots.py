#!/usr/bin/env python3
"""Take the game's README screenshots, in the Godot container.

    python godot/tools/screenshots.py          # -> godot/screenshots/*.png

The game renders under Xvfb with Mesa's software OpenGL, so this needs no
GPU and no display. Each picture is a real run of the game: the mid-game
ones play a few random shots first (the autoplay test's), so they differ a
little from run to run.
"""
from __future__ import annotations

import os
import pathlib
import shlex
import subprocess
import sys

GODOT = pathlib.Path(__file__).resolve().parent.parent
OUT = GODOT / "screenshots"

#: name -> the game's own arguments (after `--`); see the top of game.gd.
SHOTS = {
    "menu": [],
    "aim": ["--start", "--aim"],
    "midgame": ["--autoplay", "--shots", "6", "--aim"],
    "overhead": ["--autoplay", "--shots", "8", "--aim", "--camera", "1"],
}


def main() -> int:
    OUT.mkdir(exist_ok=True)
    env = dict(os.environ, HOST_UID=str(os.getuid()) if hasattr(os, "getuid") else "1000",
               HOST_GID=str(os.getgid()) if hasattr(os, "getgid") else "1000")
    failed = 0
    for name, args in SHOTS.items():
        game = ["godot", "--display-driver", "x11", "--rendering-driver", "opengl3", "--resolution", "1280x720",
                "--", *args, "--screenshot", f"/project/screenshots/{name}.png"]
        # Start Xvfb by hand, as docker/vnc_entrypoint.sh does: xvfb-run's
        # ready handshake sometimes never arrives in a container.
        inner = ("Xvfb :99 -screen 0 1280x720x24 -nolisten tcp & "
                 "for i in $(seq 50); do [ -S /tmp/.X11-unix/X99 ] && break; sleep 0.1; done; "
                 "DISPLAY=:99 timeout 240 " + shlex.join(game))
        cmd = ["docker", "compose", "run", "--rm", "--entrypoint", "bash", "godot", "-c", inner]
        print("$", name, flush=True)
        result = subprocess.run(cmd, cwd=GODOT, env=env, capture_output=True, text=True,
                                timeout=300)
        if "[screenshot]" not in result.stdout:
            print(result.stdout[-2000:], result.stderr[-2000:], sep="\n")
            failed += 1
        else:
            print(f"  -> {OUT / (name + '.png')}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
