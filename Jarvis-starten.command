#!/bin/bash
# Doppelklick: startet den JARVIS-Server und öffnet die Statusseite.
cd "$(dirname "$0")" && ./jarvis.sh start && ./jarvis.sh oeffnen
