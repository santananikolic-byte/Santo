#!/bin/bash
# Doppelklick: beendet AUTONOMOUS sauber (Aufgaben bleiben gespeichert).
cd "$(dirname "$0")" || exit 1
DIENST="gui/$(id -u)/de.autonomous.server"
PLIST="$HOME/Library/LaunchAgents/de.autonomous.server.plist"
PID_DATEI="autonomous/daten/autonomous.pid"
PID="$(cat "$PID_DATEI" 2>/dev/null)"
case "$PID" in ''|*[!0-9]*) PID="" ;; esac
# Nur beenden, wenn die Nummer wirklich zu AUTONOMOUS gehört – nach einem Absturz kann sie inzwischen
# zu einem ganz anderen Programm gehören.
ist_autonomous_pid() {
    [ -n "$PID" ] && kill -0 "$PID" 2>/dev/null && ps -p "$PID" -o command= 2>/dev/null | grep -q -- "-m autonomous"
}
BEENDET=""
# 1) Dauerbetrieb über macOS (LaunchAgent): sauber entladen – macOS beendet AUTONOMOUS dabei (kein Neustart)
if command -v launchctl >/dev/null 2>&1 && launchctl print "$DIENST" >/dev/null 2>&1; then
    launchctl bootout "$DIENST" >/dev/null 2>&1
    BEENDET="ja"
fi
# 2) Ohne Dauerbetrieb gestartet (oder noch übrig): selbst beenden
if ist_autonomous_pid; then
    kill -TERM "$PID"
    BEENDET="ja"
fi
for _ in $(seq 1 20); do
    ist_autonomous_pid || break
    sleep 0.5
done
if [ -n "$BEENDET" ]; then
    echo "AUTONOMOUS beendet."
    if [ -f "$PLIST" ]; then
        echo "Hinweis: Beim nächsten Anmelden am Mac startet AUTONOMOUS wieder von selbst (Autostart)."
        echo "Ganz ausschalten: Doppelklick auf 'AUTONOMOUS Autostart aus'."
    fi
else
    echo "AUTONOMOUS läuft nicht."
    rm -f "$PID_DATEI"
fi
