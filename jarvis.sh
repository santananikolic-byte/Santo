#!/bin/bash
# JARVIS-Server starten, stoppen und bedienen.
#
#   ./jarvis.sh start               im Hintergrund starten
#   ./jarvis.sh stopp               beenden
#   ./jarvis.sh status              läuft er? Anbieter? Was ist offen?
#   ./jarvis.sh oeffnen             Oberfläche im Browser öffnen
#   ./jarvis.sh link                Link mit Zugangsschlüssel (fürs Handy: erst "lan an")
#   ./jarvis.sh frage "…"           eine Frage stellen (der Server muss laufen)
#   ./jarvis.sh notstopp            alles anhalten, bis du entsperrst
#   ./jarvis.sh entsperren          Notstopp aufheben
#   ./jarvis.sh logs [N]            die letzten N Log-Einträge (Standard 20)
#   ./jarvis.sh provider            ist Claude Code bereit? (verbraucht kein Kontingent)
#   ./jarvis.sh backup              Sicherung der Datenbank jetzt
#   ./jarvis.sh wiederherstellen D  Datenbank aus Sicherung D zurückholen (erst stoppen)
#   ./jarvis.sh export [Datei]      alle gespeicherten Daten als JSON
#   ./jarvis.sh lan an|aus          Zugriff aus dem WLAN (iPhone) erlauben oder sperren
#   ./jarvis.sh umgebung            was JARVIS über diesen Mac erkennt
#
# Der Server ist nur auf diesem Mac erreichbar (127.0.0.1), außer du schaltest "lan an",
# und läuft nur, solange der Mac an ist. Beschreibung: JARVIS-SERVER.md

cd "$(dirname "$0")" || exit 1

PYTHON="${JARVIS_PYTHON:-python3}"

if ! "$PYTHON" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)' 2>/dev/null; then
    echo "JARVIS braucht Python 3.9 oder neuer ($PYTHON fehlt oder ist zu alt)."
    exit 1
fi

datenordner() {
    "$PYTHON" -c 'from jarvis_core import konfig; print(konfig.daten_ordner_ermitteln())'
}

laeuft() {
    "$PYTHON" -m jarvis_core status >/dev/null 2>&1
}

case "${1:-status}" in
    start)
        if laeuft; then
            echo "JARVIS läuft schon. Oberfläche: ./jarvis.sh oeffnen"
            exit 0
        fi
        ORDNER="$(datenordner)" || exit 1
        mkdir -p "$ORDNER/logs"
        nohup "$PYTHON" -m jarvis_core serve >>"$ORDNER/logs/konsole.log" 2>&1 &
        PROZESS=$!
        for _ in $(seq 1 75); do
            # Ist der Prozess schon wieder beendet (z. B. Port belegt), nicht weiter warten.
            if ! kill -0 "$PROZESS" 2>/dev/null; then
                break
            fi
            if laeuft; then
                echo "JARVIS läuft. Oberfläche öffnen: ./jarvis.sh oeffnen"
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
    oeffnen|öffnen)
        LINK="$("$PYTHON" -m jarvis_core link | head -1)" || exit 1
        open "$LINK" 2>/dev/null || echo "Im Browser öffnen: $LINK"
        ;;
    status|link|provider|notstopp|entsperren|backup|export|umgebung)
        "$PYTHON" -m jarvis_core "$@"
        ;;
    logs)
        "$PYTHON" -m jarvis_core logs "${2:-20}"
        ;;
    frage|wiederherstellen|lan)
        "$PYTHON" -m jarvis_core "$@"
        ;;
    *)
        echo "So: ./jarvis.sh start | stopp | status | oeffnen | link | frage \"…\" | notstopp | entsperren | logs [N]"
        echo "    | provider | backup | wiederherstellen DATEI | export [DATEI] | lan an|aus | umgebung"
        exit 2
        ;;
esac
