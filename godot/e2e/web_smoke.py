#!/usr/bin/env python3
"""Load the web export in headless Chromium and play one shot.

    python godot/tools/web_export.py          # build web_export/ first
    python godot/e2e/web_smoke.py             # runs in the Playwright image

Catches the failures a headless Godot run cannot: an export that ships
without the model, a renderer the browser will not start, a page error. It
serves `web_export/`, waits for the game to log that the table loaded,
starts a game (Enter), drags back from the ball and lets go, checks the
shot was scored, and waits for the computer to take its turn. Screenshots land in `web_export/e2e_*.png`.

This file runs twice: on the host it starts the container; inside the
container (`--inside`) it drives the browser.
"""
from __future__ import annotations

import pathlib
import subprocess
import sys

HERE = pathlib.Path(__file__).resolve()
REPO = HERE.parents[2] if len(HERE.parents) > 2 else HERE.parent  # inside: /web_smoke.py
IMAGE = "mcr.microsoft.com/playwright/python:v1.48.0-jammy"
VIEW = {"width": 1280, "height": 720}


def host() -> int:
    uid = ["--user", "1000:1000"]
    try:
        import os
        uid = ["--user", f"{os.getuid()}:{os.getgid()}"]
    except AttributeError:
        pass
    cmd = ["docker", "run", "--rm", "--ipc=host", *uid, "-e", "HOME=/tmp",
           "-v", f"{REPO / 'web_export'}:/web:z",
           "-v", f"{pathlib.Path(__file__).resolve()}:/web_smoke.py:ro,z",
           IMAGE, "bash", "-c",
           "pip install -q --no-warn-script-location playwright==1.48.0 >/dev/null 2>&1; "
           "python3 /web_smoke.py --inside"]
    print("$", " ".join(cmd), flush=True)
    return subprocess.call(cmd)


def inside() -> int:
    import http.server
    import threading
    from functools import partial

    from playwright.sync_api import sync_playwright

    handler = partial(http.server.SimpleHTTPRequestHandler, directory="/web")
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 8070), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()

    logs: list[str] = []
    errors: list[str] = []
    with sync_playwright() as pw:
        browser = pw.chromium.launch(args=["--use-angle=swiftshader", "--enable-unsafe-swiftshader",
                                           "--ignore-gpu-blocklist"])
        page = browser.new_page(viewport=VIEW)
        page.on("console", lambda m: logs.append(m.text))
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.goto("http://127.0.0.1:8070/index.html")

        def wait_for(text: str, seconds: float) -> bool:
            for _ in range(int(seconds * 4)):
                if any(text in line for line in logs):
                    return True
                page.wait_for_timeout(250)
            return False

        loaded = wait_for("[table]", 90)
        page.wait_for_timeout(3000)
        page.screenshot(path="/web/e2e_menu.png")
        ok = loaded
        stray = False
        if loaded:
            # Focus the canvas well clear of the menu, then Enter plays
            # with the menu's defaults (hud.gd) — you against the computer.
            page.mouse.click(640, 30)
            page.keyboard.press("Enter")
            page.wait_for_timeout(2500)
            page.keyboard.press("w")            # a little top spin: the pad shows it
            # A click away from the ball, with no pull back, is not a shot.
            # A shot is only logged once the balls stop: give one time to.
            page.mouse.click(420, 400)
            stray = wait_for("[shot]", 12)
            # The ball waits in the D, low and centred in the player's view;
            # drag back towards the player and let go.
            page.mouse.move(640, 512)
            page.mouse.down()
            for step in range(1, 21):
                page.mouse.move(640 - step * 2, 512 + step * 7)
                page.wait_for_timeout(30)
            page.screenshot(path="/web/e2e_aim.png")
            page.mouse.up()
            ok = wait_for("[shot]", 40)
            page.wait_for_timeout(1000)
            page.screenshot(path="/web/e2e_after.png")
            # Unless the shot potted something, the computer plays next.
            if ok and not any("[shot] +" in line for line in logs):
                ok = wait_for("[ai]", 40)
                page.wait_for_timeout(1500)
                page.screenshot(path="/web/e2e_computer.png")
        browser.close()
    server.shutdown()

    for line in logs:
        if line.startswith("[") or "ERROR" in line:
            print("  console:", line)
    for e in errors:
        print("  PAGE ERROR:", e)
    print("table loaded:", loaded, "| shot resolved:", ok, "| stray click played a shot:", stray,
          "| page errors:", len(errors))
    return 0 if ok and not stray and not errors else 1


if __name__ == "__main__":
    sys.exit(inside() if "--inside" in sys.argv else host())
