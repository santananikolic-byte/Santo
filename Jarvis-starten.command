#!/bin/bash
# Doppelklick: holt die neueste Fassung (falls vorhanden), startet JARVIS und öffnet die Oberfläche.
cd "$(dirname "$0")" || exit 1
VORHER="$(git rev-parse HEAD 2>/dev/null)"
git pull --ff-only --quiet 2>/dev/null
NACHHER="$(git rev-parse HEAD 2>/dev/null)"
if [ -n "$VORHER" ] && [ "$VORHER" != "$NACHHER" ]; then
    echo "Neue Fassung geholt – JARVIS wird neu gestartet."
    ./jarvis.sh stopp
fi
./jarvis.sh start && ./jarvis.sh oeffnen
