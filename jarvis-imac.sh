#!/bin/bash
# Richtet Jarvis für das Terminal auf dem iMac (oder jedem anderen Mac) ein.
#
#   curl -fsSL https://raw.githubusercontent.com/santananikolic-byte/Santo/claude/jarvis-voice-assistant-70695g/jarvis-imac.sh | bash
#
# Danach liegt „Jarvis“ auf dem Schreibtisch - Doppelklick genügt. Dieselbe
# Zeile später noch einmal ausgeführt holt die neueste Fassung; Gedächtnis und
# Schlüssel in ~/.jarvis-terminal bleiben dabei unangetastet.

set -e

QUELLE="https://raw.githubusercontent.com/santananikolic-byte/Santo/claude/jarvis-voice-assistant-70695g/jarvis_terminal.py"
ZIEL="$HOME/Jarvis-Terminal"
STARTER="$HOME/Desktop/Jarvis.command"

if [ "$(uname)" != "Darwin" ]; then
    echo "Das ist für den Mac gedacht."
    exit 1
fi

# python3 und das Ohr für „Hey Jarvis“ brauchen Apples Befehlszeilenwerkzeuge.
if ! xcode-select -p >/dev/null 2>&1; then
    echo "Apples Befehlszeilenwerkzeuge fehlen noch."
    echo "Gleich öffnet sich ein Fenster: bitte auf „Installieren“ klicken."
    echo "Wenn es fertig ist, diese Zeile einfach noch einmal ausführen."
    xcode-select --install >/dev/null 2>&1 || true
    exit 1
fi

echo "Jarvis wird eingerichtet …"
mkdir -p "$ZIEL"
curl -fsSL "$QUELLE" -o "$ZIEL/jarvis_terminal.py.neu"
mv "$ZIEL/jarvis_terminal.py.neu" "$ZIEL/jarvis_terminal.py"

cat > "$STARTER" <<EOF
#!/bin/bash
cd "$ZIEL" && exec python3 jarvis_terminal.py
EOF
chmod +x "$STARTER"

echo "Fertig. Auf dem Schreibtisch liegt jetzt „Jarvis“ – Doppelklick genügt."
echo "Jarvis startet jetzt in einem neuen Fenster."
open "$STARTER"
