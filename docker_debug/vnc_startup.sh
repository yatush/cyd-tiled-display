#!/bin/bash
export DISPLAY=:0
Xvfb :0 -screen 0 480x320x16 &
sleep 1
fluxbox &
x11vnc -display :0 -forever -nopw &
/app/novnc/utils/novnc_proxy --vnc localhost:5900 --listen 6080 &
# Internal websockify for Cloud Run (single port mode)
websockify --web /app/novnc 6081 localhost:5900 &
exec "$@"
