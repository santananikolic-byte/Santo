#!/bin/bash
# Doppelklick: beendet AUTONOMOUS sauber (Aufgaben bleiben gespeichert).
cd "$(dirname "$0")" || exit 1
PID_DATEI="autonomous/daten/autonomous.pid"
if [ -f "$PID_DATEI" ] && kill -0 "$(cat "$PID_DATEI")" 2>/dev/null; then
    kill -TERM "$(cat "$PID_DATEI")"
    for _ in $(seq 1 20); do
        sleep 0.5
        kill -0 "$(cat "$PID_DATEI" 2>/dev/null)" 2>/dev/null || break
    done
    echo "AUTONOMOUS beendet."
else
    echo "AUTONOMOUS läuft nicht."
    rm -f "$PID_DATEI"
fi
