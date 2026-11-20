#!/bin/bash
# Doppelklick: startet AUTONOMOUS im Hintergrund und öffnet die Oberfläche im Browser.
# Braucht nur Python 3 (auf dem Mac vorhanden oder über die Apple-Entwicklerwerkzeuge).
cd "$(dirname "$0")" || exit 1
PORT="${AUTONOMOUS_PORT:-8770}"
if ! command -v python3 >/dev/null 2>&1; then
    echo "Python 3 fehlt. Bitte einmal im Terminal 'xcode-select --install' ausführen und danach erneut doppelklicken."
    read -r -p "Enter zum Schließen ..." _
    exit 1
fi
mkdir -p autonomous/daten
if ! curl -s --max-time 2 "http://127.0.0.1:$PORT/status" >/dev/null 2>&1; then
    echo "AUTONOMOUS wird gestartet ..."
    nohup python3 -m autonomous start >> autonomous/daten/server.log 2>&1 &
    for _ in $(seq 1 30); do
        sleep 0.5
        curl -s --max-time 1 "http://127.0.0.1:$PORT/status" >/dev/null 2>&1 && break
    done
fi
if ! curl -s --max-time 2 "http://127.0.0.1:$PORT/status" >/dev/null 2>&1; then
    echo "Start fehlgeschlagen. Letzte Meldungen:"
    tail -n 20 autonomous/daten/server.log
    read -r -p "Enter zum Schließen ..." _
    exit 1
fi
LINK="$(python3 -m autonomous link)"
echo "AUTONOMOUS läuft: $LINK"
echo "(Auf dem iPhone: siehe ANLEITUNG in autonomous/README.md)"
if command -v open >/dev/null 2>&1; then open "$LINK"; fi
