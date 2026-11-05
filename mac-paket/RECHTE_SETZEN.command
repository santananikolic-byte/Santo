#!/bin/bash
# Nur nötig, wenn ein Doppelklick „keine Berechtigung“ meldet: macht alle Startdateien wieder ausführbar.
cd "$(dirname "$0")" || exit 1
chmod +x ./*.command ./jarvis.sh 2>/dev/null
echo "  Rechte gesetzt. JARVIS.command kann jetzt doppelgeklickt werden."
[ "${JARVIS_OHNE_PAUSE:-0}" = "1" ] || read -r -p "  Enter zum Schließen " _
exit 0
