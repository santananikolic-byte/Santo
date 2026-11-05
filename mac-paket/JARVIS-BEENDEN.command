#!/bin/bash
# Doppelklick: beendet JARVIS. Deine Daten bleiben erhalten.
cd "$(dirname "$0")" || exit 1
chmod +x ./*.command ./jarvis.sh 2>/dev/null
export JARVIS_PAKET=1
echo
./jarvis.sh stopp
echo
[ "${JARVIS_OHNE_PAUSE:-0}" = "1" ] || read -r -t 15 -p "  (Enter zum Schließen) " _
exit 0
