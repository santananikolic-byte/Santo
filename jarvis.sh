#!/bin/bash
# JARVIS-Server starten und stoppen.
#
#   ./jarvis.sh start     im Hintergrund starten
#   ./jarvis.sh stopp     beenden
#   ./jarvis.sh status    läuft er? seit wann? wie viele Anfragen?
#   ./jarvis.sh logs [N]  die letzten N Log-Einträge (Standard 20)
#   ./jarvis.sh oeffnen   Statusseite im Browser öffnen
#
# Der Server ist nur auf diesem Mac erreichbar (127.0.0.1) und läuft nur,
# solange der Mac an ist. Beschreibung: JARVIS-SERVER.md

cd "$(dirname "$0")" || exit 1

PYTHON="${JARVIS_PYTHON:-python3}"

if ! "$PYTHON" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)' 2>/dev/null; then
    echo "JARVIS braucht Python 3.9 oder neuer ($PYTHON fehlt oder ist zu alt)."
    exit 1
fi

datenordner() {
    "$PYTHON" -c 'from jarvis_core import konfig; print(konfig.daten_ordner_ermitteln())'
}

adresse() {
    "$PYTHON" -c 'from jarvis_core import konfig; print(konfig.laden().adresse)'
}

case "${1:-status}" in
    start)
        if "$PYTHON" -m jarvis_core status >/dev/null 2>&1; then
            echo "JARVIS läuft schon: $(adresse)"
            exit 0
        fi
        ORDNER="$(datenordner)" || exit 1
        mkdir -p "$ORDNER/logs"
        nohup "$PYTHON" -m jarvis_core serve >>"$ORDNER/logs/konsole.log" 2>&1 &
        PROZESS=$!
        for _ in $(seq 1 50); do
            # Ist der Prozess schon wieder beendet (z. B. Port belegt), nicht weiter warten.
            if ! kill -0 "$PROZESS" 2>/dev/null; then
                break
            fi
            if "$PYTHON" -m jarvis_core status >/dev/null 2>&1; then
                echo "JARVIS läuft: $(adresse)"
                exit 0
            fi
            sleep 0.2
        done
        kill "$PROZESS" 2>/dev/null
        echo "JARVIS ist nicht gestartet. Letzte Meldungen:"
        tail -5 "$ORDNER/logs/konsole.log"
        exit 1
        ;;
    stopp|stop)
        "$PYTHON" -m jarvis_core stopp
        ;;
    status)
        "$PYTHON" -m jarvis_core status
        ;;
    logs)
        "$PYTHON" -m jarvis_core logs "${2:-20}"
        ;;
    oeffnen|öffnen)
        open "$(adresse)" 2>/dev/null || echo "Im Browser öffnen: $(adresse)"
        ;;
    *)
        echo "So: ./jarvis.sh start | stopp | status | logs [N] | oeffnen"
        exit 2
        ;;
esac
