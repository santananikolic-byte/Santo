#!/bin/bash
# Doppelklick: startet AUTONOMOUS im Hintergrund und öffnet die Oberfläche im Browser.
# Braucht nur Python 3.9 oder neuer (auf dem Mac über die Apple-Entwicklerwerkzeuge vorhanden).
cd "$(dirname "$0")" || exit 1
PORT="${AUTONOMOUS_PORT:-8770}"

ende_mit_fehler() {
    echo ""
    echo "$1"
    read -r -p "Enter zum Schließen ..." _
    exit 1
}

# 1) Python wirklich ausführbar? (Auf dem Mac gibt es /usr/bin/python3 auch ohne Entwicklerwerkzeuge –
#    dann startet es nicht, sondern bietet die Installation an.)
VERSION="$(python3 -c 'import sys; print("%d.%d" % sys.version_info[:2])' 2>/dev/null)"
if [ -z "$VERSION" ]; then
    ende_mit_fehler "Python 3 ist nicht eingerichtet. Bitte im Terminal einmal 'xcode-select --install' ausführen
(Apple-Entwicklerwerkzeuge, kostenlos), danach erneut doppelklicken."
fi
if ! python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)' 2>/dev/null; then
    ende_mit_fehler "Python $VERSION ist zu alt – AUTONOMOUS braucht Python 3.9 oder neuer."
fi

# 2) Läuft AUTONOMOUS schon? (Antwort muss wirklich von AUTONOMOUS kommen, nicht von einem anderen Programm.)
ist_autonomous() {
    curl -s --max-time 2 "http://127.0.0.1:$PORT/status" 2>/dev/null | grep -q '"system": *"AUTONOMOUS"'
}
port_belegt() {
    curl -s -o /dev/null --max-time 2 "http://127.0.0.1:$PORT/" 2>/dev/null
}

# Dauerbetrieb (nur Mac): Ist der LaunchAgent eingerichtet, startet macOS AUTONOMOUS – sonst wie bisher hier.
DIENST="gui/$(id -u)/de.autonomous.server"
PLIST="$HOME/Library/LaunchAgents/de.autonomous.server.plist"
mit_dauerbetrieb() {
    command -v launchctl >/dev/null 2>&1 && [ -f "$PLIST" ]
}

umask 077  # Datenordner und Protokoll nur für den eigenen Benutzer lesbar
mkdir -p autonomous/daten
touch autonomous/daten/server.log
chmod -R go-rwx autonomous/daten 2>/dev/null  # auch Dateien älterer Fassungen nachträglich schützen
if ! ist_autonomous; then
    if port_belegt; then
        ende_mit_fehler "Port $PORT ist von einem anderen Programm belegt. Entweder das Programm beenden oder
AUTONOMOUS mit anderem Port starten:  AUTONOMOUS_PORT=8771 ./AUTONOMOUS-starten.command"
    fi
    if mit_dauerbetrieb; then
        echo "AUTONOMOUS wird gestartet (Dauerbetrieb über macOS, Python $VERSION) ..."
        if launchctl print "$DIENST" >/dev/null 2>&1; then
            launchctl kickstart "$DIENST" >/dev/null 2>&1                     # geladen, aber gerade beendet
        else
            launchctl bootstrap "gui/$(id -u)" "$PLIST" >/dev/null 2>&1       # laden – startet sofort
        fi
    else
        echo "AUTONOMOUS wird gestartet (Python $VERSION) ..."
        nohup python3 -m autonomous start >> autonomous/daten/server.log 2>&1 &
    fi
    for _ in $(seq 1 40); do
        sleep 0.5
        ist_autonomous && break
    done
fi
if ! ist_autonomous; then
    echo "Start fehlgeschlagen. Letzte Meldungen aus autonomous/daten/server.log:"
    tail -n 20 autonomous/daten/server.log
    ende_mit_fehler "Bitte diese Meldungen an den Entwickler weitergeben."
fi
LINK="$(python3 -m autonomous link)"
echo "AUTONOMOUS läuft: $LINK"
echo "Beenden: Doppelklick auf AUTONOMOUS-stoppen.command (Daten bleiben gespeichert)."
if command -v open >/dev/null 2>&1; then open "$LINK"; fi
