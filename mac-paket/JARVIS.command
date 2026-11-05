#!/bin/bash
# JARVIS – Doppelklick. Prüft beim ersten Mal alles selbst, startet JARVIS und öffnet den Leitstand.
#
# Kein API-Schlüssel, kein Passwort in einer Datei: JARVIS denkt über dein Claude-Abo (Claude Code)
# oder über ein eigenes lokales Modell (Ollama). Installiert wird nur, wenn du vorher Ja sagst.
#
# Für Tests ohne Mac:  JARVIS_OHNE_PAUSE=1 (keine Wartezeiten)  JARVIS_JA=1 (alle Fragen mit Ja)
#                      JARVIS_CLAUDE=/pfad/zu/claude (ein bestimmtes Claude-Programm)
cd "$(dirname "$0")" || exit 1
chmod +x ./*.command ./jarvis.sh 2>/dev/null
export JARVIS_PAKET=1   # Hinweise zeigen dann auf das Extras-Menü statt auf Terminal-Befehle

PYTHON="${JARVIS_PYTHON:-python3}"

pause() {  # hält das Fenster offen, damit du die Meldung lesen kannst
    [ "${JARVIS_OHNE_PAUSE:-0}" = "1" ] && return 0
    read -r -p "  ${1:-Enter zum Schließen} " _
}
frage_ja() {  # Enter oder j = ja, n = nein
    [ "${JARVIS_JA:-0}" = "1" ] && return 0
    local antwort=""
    read -r -p "  $1 [Enter = ja, n = nein] " antwort || return 1
    case "$antwort" in n|N|nein|Nein|NEIN) return 1 ;; *) return 0 ;; esac
}
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
echo "  ════════════════════════════════════════"
echo "     JARVIS"
echo "  ════════════════════════════════════════"
echo

# ---------- 1. Python (Apple liefert es mit den Befehlszeilen-Werkzeugen) ----------
if ! "$PYTHON" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 8) else 1)' >/dev/null 2>&1; then
    echo "  Python fehlt noch. Apple liefert es mit einem kleinen Zusatzpaket"
    echo "  („Befehlszeilenentwicklertools“ – das ist NICHT die große Xcode-App)."
    echo
    echo "  Gleich öffnet sich ein Fenster von Apple: auf „Installieren“ klicken"
    echo "  und warten, bis es fertig ist (ein paar Minuten)."
    echo "  Danach diese Datei einfach nochmal doppelklicken."
    xcode-select --install >/dev/null 2>&1
    pause
    exit 0
fi
echo "  ✓ Python $("$PYTHON" -c 'import platform; print(platform.python_version())')"

# ---------- Läuft JARVIS schon? Dann nur den Leitstand öffnen ----------
if "$PYTHON" -m jarvis_core status >/dev/null 2>&1; then
    echo "  ✓ JARVIS läuft schon – ich öffne den Leitstand."
    ./jarvis.sh oeffnen
    exit 0
fi

# ---------- 2. Das Gehirn ----------
GEHIRN="$("$PYTHON" -c 'from jarvis_core import konfig; print(konfig.laden().gehirn)' 2>/dev/null)"
if [ "$GEHIRN" = "lokal" ]; then
    echo "  ✓ Gehirn: eigenes lokales Modell (Ollama)"
else
    CLAUDE="$(claude_finden)"
    if [ -z "$CLAUDE" ]; then
        echo
        echo "  Claude Code fehlt noch. Das ist das Gehirn von JARVIS."
        echo "  Es läuft über dein Claude-Abo – kein API-Schlüssel, keine Extrakosten."
        if frage_ja "Jetzt installieren? (offizielle Installation von Anthropic)"; then
            curl -fsSL https://claude.ai/install.sh | bash
            CLAUDE="$(claude_finden)"
        fi
    fi
    if [ -z "$CLAUDE" ]; then
        echo "  ! Ohne Claude Code kann JARVIS noch nicht denken."
        echo "    Später einfach diese Datei nochmal doppelklicken."
    elif ./jarvis.sh provider >/dev/null 2>&1; then
        echo "  ✓ Gehirn: Claude über dein Abo"
    else
        echo
        echo "  Claude Code ist noch nicht mit deinem Claude-Abo verbunden."
        echo "  Gleich öffnet sich der Browser: mit deinem Claude-Konto anmelden und erlauben."
        if frage_ja "Jetzt anmelden?"; then
            if "$CLAUDE" auth login --help >/dev/null 2>&1; then
                "$CLAUDE" auth login --claudeai          # Anmeldung mit dem Claude-Abo, nicht mit API-Abrechnung
            else
                echo "  Claude Code startet: Anmeldung mit dem Claude-Konto (Abo) wählen, danach /exit tippen."
                "$CLAUDE"
            fi
        fi
        if ./jarvis.sh provider >/dev/null 2>&1; then
            echo "  ✓ Claude-Abo verbunden"
        else
            echo "  ! Noch nicht verbunden – geht auch später: EXTRAS.command → 3"
        fi
    fi
fi

# ---------- 3. Selbsttest – nur anzeigen, wenn etwas fehlt ----------
BEREIT=1
if ! ./jarvis.sh pruefen >/dev/null 2>&1; then
    BEREIT=0
    echo
    ./jarvis.sh pruefen
fi

# ---------- 4. Start ----------
echo
if ./jarvis.sh start; then
    ./jarvis.sh oeffnen
    echo
    if [ "$BEREIT" = "1" ]; then
        echo "  Fertig. Der Leitstand ist im Browser offen."
    else
        echo "  JARVIS läuft und der Leitstand ist offen – aber er kann noch nicht alles."
        echo "  Was fehlt, steht oben mit ✗. Danach diese Datei einfach nochmal doppelklicken."
    fi
    echo "  Dieses Fenster darfst du schließen – JARVIS läuft im Hintergrund weiter."
    echo "  Beenden: JARVIS-BEENDEN.command   ·   Mehr: EXTRAS.command"
    echo
    [ "${JARVIS_OHNE_PAUSE:-0}" = "1" ] || read -r -t 30 -p "  (Enter zum Schließen) " _
    exit 0
fi
echo "  ✗ JARVIS ist nicht gestartet (der Grund steht oben)."
echo "    Mach ein Foto von diesem Fenster und schick es Claude – dann wird es behoben."
pause
exit 1
