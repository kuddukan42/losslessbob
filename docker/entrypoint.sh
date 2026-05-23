#!/bin/bash
set -e

# Virtual framebuffer — 1280x900 is wide enough for all tabs
Xvfb :1 -screen 0 1280x900x24 -nolisten tcp &

# Give X time to initialise before VNC attaches
sleep 1

# VNC server — no password, localhost only (websockify is the public gateway)
x11vnc -display :1 -nopw -listen 127.0.0.1 -xkb -forever -quiet -bg

# websockify bridges WebSocket (browser) → VNC TCP and serves the noVNC JS client
websockify --web /usr/share/novnc 6080 127.0.0.1:5900 &

# Launch LosslessBob (Flask + PyQt6)
exec python3 main.py
