#!/bin/bash
# JARVIS – Extras: die seltenen Dinge, mit Nummer.
cd "$(dirname "$0")" || exit 1
chmod +x ./*.command ./jarvis.sh 2>/dev/null
export JARVIS_PAKET=1   # Hinweise zeigen dann auf das Extras-Menü statt auf Terminal-Befehle

claude_finden() {
    if [ -n "${JARVIS_CLAUDE:-}" ]; then
        [ -x "$JARVIS_CLAUDE" ] && printf "%s" "$JARVIS_CLAUDE"
        return 0
    fi
    local p
    for p in "$(command -v claude 2>/dev/null)" "$HOME/.local/bin/claude" "$HOME/.claude/local/claude" \
             /opt/homebrew/bin/claude /usr/local/bin/claude; do
        if [ -n "$p" ] && [ -x "$p" ]; then printf "%s" "$p"; return 0; fi
    done
}

echo
echo "  JARVIS – Extras"
echo
echo "  1) Leitstand öffnen"
echo "  2) Selbsttest – was läuft, was fehlt"
echo "  3) Claude-Abo anmelden (Claude Code verbinden)"
echo "  4) JARVIS beenden"
echo "  5) Handy im WLAN erlauben oder sperren"
echo "  6) Link fürs Handy zeigen"
echo "  7) Sicherung jetzt"
echo "  8) Preisrechner öffnen"
echo "  9) Notstopp – alles sofort anhalten"
echo "  0) Notstopp aufheben"
echo
read -r -p "  Nummer: " wahl
echo
case "$wahl" in
    1) ./jarvis.sh status >/dev/null 2>&1 || ./jarvis.sh start
       ./jarvis.sh oeffnen ;;
    2) ./jarvis.sh pruefen ;;
    3) C="$(claude_finden)"
       if [ -z "$C" ]; then
           echo "  Claude Code ist noch nicht installiert. Doppelklick auf JARVIS.command richtet es ein."
       elif "$C" auth login --help >/dev/null 2>&1; then
           "$C" auth login --claudeai    # Anmeldung mit dem Claude-Abo, nicht mit API-Abrechnung
       else
           echo "  Claude Code startet: Anmeldung mit dem Claude-Konto (Abo) wählen, danach /exit tippen."
           "$C"
       fi
       echo
       ./jarvis.sh provider ;;
    4) ./jarvis.sh stopp ;;
    5) read -r -p "  WLAN-Zugriff fürs Handy: an oder aus? " w
       case "$w" in
           an|aus) ./jarvis.sh lan "$w" ;;
           *) echo "  Nichts geändert." ;;
       esac ;;
    6) ./jarvis.sh link ;;
    7) ./jarvis.sh backup ;;
    8) open Preisrechner.html 2>/dev/null || echo "  Im Finder doppelklicken: $(pwd)/Preisrechner.html" ;;
    9) ./jarvis.sh notstopp ;;
    0) ./jarvis.sh entsperren ;;
    *) echo "  Nichts ausgewählt." ;;
esac
echo
[ "${JARVIS_OHNE_PAUSE:-0}" = "1" ] || read -r -p "  Enter zum Schließen " _
exit 0
