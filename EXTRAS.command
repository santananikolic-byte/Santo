#!/bin/bash
# ---------------------------------------------------------------------------
# Seltene Funktionen. Alles, was man nicht täglich braucht, aber manchmal
# schon: Selbsttest, Dashboard, Stimme einlernen, Einrichtung wiederholen.
# ---------------------------------------------------------------------------

cd "$(dirname "$0")" || exit 1
PROJEKT="$(pwd)"

if [ -f "$PROJEKT/.venv/bin/python" ]; then
    PYTHON="$PROJEKT/.venv/bin/python"
else
    PYTHON="python3"
fi

while true; do
    echo ""
    echo "  ============================================================"
    echo "   JARVIS - seltene Funktionen"
    echo "  ============================================================"
    echo ""
    echo "   1  Selbsttest - prüft jeden Baustein"
    echo "   2  Command Center und Sales-Analyse bauen und öffnen"
    echo "   3  Briefing sofort sprechen"
    echo "   4  Abendrückblick sofort sprechen"
    echo "   5  Tippbetrieb statt Sprache"
    echo "   6  Vom Handy aus über Telegram"
    echo "   7  Stimmprofil einlernen"
    echo "   8  ElevenLabs-Stimme aussuchen"
    echo "   9  Einrichtung noch einmal durchlaufen"
    echo "  10  Einstellungen anzeigen"
    echo "  11  Buchhaltung als CSV exportieren"
    echo "  12  Neu bauen aus den Modulen"
    echo "   0  Schließen"
    echo ""
    read -r -p "  Deine Wahl: " WAHL
    echo ""

    case "$WAHL" in
        1)  "$PYTHON" "$PROJEKT/jarvis.py" test ;;
        2)  "$PYTHON" "$PROJEKT/jarvis.py" dashboard ;;
        3)  "$PYTHON" "$PROJEKT/jarvis.py" briefing ;;
        4)  "$PYTHON" "$PROJEKT/jarvis.py" abend ;;
        5)  "$PYTHON" "$PROJEKT/jarvis.py" chat ;;
        6)  "$PYTHON" "$PROJEKT/jarvis.py" telegram ;;
        7)  "$PYTHON" "$PROJEKT/jarvis.py" stimme ;;
        8)  "$PYTHON" "$PROJEKT/jarvis.py" stimmen ;;
        9)  "$PYTHON" "$PROJEKT/jarvis.py" einrichten
            echo ""
            echo "  Denk daran: Terminal einmal schließen und neu öffnen." ;;
        10) if [ -f "$PROJEKT/config/.env" ]; then
                echo "  Einstellungen in config/.env (Geheimnisse gekürzt):"
                echo ""
                sed -E 's/^([A-Z_]*(KEY|TOKEN|PASSWORT))=(.{0,6}).*/\1=\3... (gekürzt)/' \
                    "$PROJEKT/config/.env"
            else
                echo "  Es gibt noch keine Einstellungen. Bitte zuerst einrichten."
            fi ;;
        11) "$PYTHON" "$PROJEKT/jarvis.py" export ;;
        12) "$PYTHON" "$PROJEKT/build_single.py" ;;
        0)  exit 0 ;;
        *)  echo "  Die Eingabe '$WAHL' kenne ich nicht." ;;
    esac

    echo ""
    read -r -p "  Enter für das Menü "
done
