#!/usr/bin/env bash
# Runs the Godot project (main.tscn, in "play" mode — same as double-clicking
# Run in the editor) against a virtual display, shared over VNC (:5900) and
# noVNC's browser client (:6080), so it's viewable/interactive without a
# native VNC client or a native Godot install.
set -euo pipefail

Xvfb :99 -screen 0 1280x720x24 -nolisten tcp &
for _ in $(seq 1 50); do
    [ -S /tmp/.X11-unix/X99 ] && break
    sleep 0.1
done

x11vnc -display :99 -forever -shared -nopw -rfbport 5900 -bg -o /tmp/x11vnc.log -quiet
websockify --web=/usr/share/novnc 6080 localhost:5900 &

exec env DISPLAY=:99 godot --display-driver x11 --rendering-driver opengl3 "$@"
