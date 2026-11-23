#!/bin/bash
# Doppelklick: schaltet den Dauerbetrieb auf dem Mac (Autostart) ganz aus und beendet AUTONOMOUS.
# Eure Daten bleiben erhalten. Wieder einschalten: die Einrichtungszeile im Terminal erneut ausführen.
cd "$(dirname "$0")" || exit 1
DIENST="gui/$(id -u)/de.autonomous.server"
PLIST="$HOME/Library/LaunchAgents/de.autonomous.server.plist"
if command -v launchctl >/dev/null 2>&1 && launchctl print "$DIENST" >/dev/null 2>&1; then
    ./AUTONOMOUS-stoppen.command >/dev/null  # beendet AUTONOMOUS sauber und entlädt den Dienst
fi
if [ -f "$PLIST" ]; then
    rm -f "$PLIST"
    echo "Autostart ist aus: AUTONOMOUS ist beendet und startet nicht mehr von selbst."
else
    echo "Der Autostart war schon aus."
fi
echo "Starten bei Bedarf: Doppelklick auf 'AUTONOMOUS starten'. Eure Daten bleiben erhalten."
