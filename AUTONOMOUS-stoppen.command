#!/bin/bash
# Doppelklick: beendet AUTONOMOUS sauber (Aufgaben bleiben gespeichert).
cd "$(dirname "$0")" || exit 1
PID_DATEI="autonomous/daten/autonomous.pid"
PID="$(cat "$PID_DATEI" 2>/dev/null)"
case "$PID" in ''|*[!0-9]*) PID="" ;; esac
# Nur beenden, wenn die Nummer wirklich zu AUTONOMOUS gehört – nach einem Absturz kann sie inzwischen
# zu einem ganz anderen Programm gehören.
if [ -n "$PID" ] && kill -0 "$PID" 2>/dev/null && ps -p "$PID" -o command= 2>/dev/null | grep -q -- "-m autonomous"; then
    kill -TERM "$PID"
    for _ in $(seq 1 20); do
        sleep 0.5
        kill -0 "$PID" 2>/dev/null || break
    done
    echo "AUTONOMOUS beendet."
else
    echo "AUTONOMOUS läuft nicht."
    rm -f "$PID_DATEI"
fi
