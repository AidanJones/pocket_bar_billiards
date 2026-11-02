#!/usr/bin/env python3
"""Run the game's tests in the Godot container.

    python godot/tools/game_test.py            # rules unit tests + table scenarios
    python godot/tools/game_test.py --rules    # just the rules (a few seconds)

The rules tests (tests/test_rules.gd) check the scoring with no table. The
scenarios (tests/test_game.gd) set balls out on the real table, play shots
through the physics and check what the game made of them. `--fixed-fps`
steps the physics as fast as the machine allows instead of in real time.
"""
from __future__ import annotations

import os
import pathlib
import subprocess
import sys

GODOT = pathlib.Path(__file__).resolve().parent.parent


def godot(summary: str, *args: str) -> int:
    env = dict(os.environ, HOST_UID=str(os.getuid()) if hasattr(os, "getuid") else "1000",
               HOST_GID=str(os.getgid()) if hasattr(os, "getgid") else "1000")
    # A script error leaves Godot running, not exiting: cap the frames.
    cmd = ["docker", "compose", "run", "--rm", "godot", "--headless", "--quit-after", "200000", *args]
    out = subprocess.run(cmd, cwd=GODOT, env=env, capture_output=True, text=True, timeout=1200)
    for line in out.stdout.splitlines():
        if line.startswith(("[", "  ", "SCRIPT ERROR", "ERROR")) or "FAIL" in line:
            if "OpenXR" not in line:
                print(line)
    # A script error does not stop Godot, so passing means the summary line
    # was printed, nothing failed to compile, and the exit code was clean.
    broken = "SCRIPT ERROR" in out.stdout + out.stderr or summary not in out.stdout
    if out.returncode != 0 or broken:
        print(out.stderr[-3000:])
        for line in (out.stdout + out.stderr).splitlines():
            if "SCRIPT ERROR" in line or "at: " in line and "res://" in line:
                print(line)
        return 1
    return 0


def main() -> int:
    failed = godot("[rules]", "--script", "res://tests/test_rules.gd")
    if "--rules" not in sys.argv:
        failed |= godot("[game-test]", "--fixed-fps", "120", "--", "--scenarios")
    print("PASS" if failed == 0 else "FAILED")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
