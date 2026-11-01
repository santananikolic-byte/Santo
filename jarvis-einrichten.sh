#!/bin/bash
# ---------------------------------------------------------------------------
# JARVIS einrichten und starten. Eine Zeile im Terminal, mehr ist nicht nötig:
#
#   bash -c "$(curl -fsSL https://raw.githubusercontent.com/santananikolic-byte/Santo/claude/jarvis-voice-assistant-70695g/jarvis-einrichten.sh)"
#
# Das Skript holt den Code nach ~/Santo (oder aktualisiert ihn), prüft Python und
# Claude Code, bietet an, Fehlendes zu installieren, startet JARVIS und öffnet ihn
# im Browser. Es löscht nichts und fragt vor jeder Installation.
#
# Zum Ausprobieren ohne Mac: JARVIS_NUR_PRUEFEN=1 bash jarvis-einrichten.sh   (ändert nichts)
#                            JARVIS_TESTLAUF=1 bash jarvis-einrichten.sh      (läuft komplett, ohne Mac-Prüfung)
# ---------------------------------------------------------------------------

set -u

REPO="https://github.com/santananikolic-byte/Santo.git"
ZWEIG="${JARVIS_ZWEIG:-claude/jarvis-voice-assistant-70695g}"
ZIEL="${JARVIS_ZIEL:-$HOME/Santo}"
PYTHON="${JARVIS_PYTHON:-python3}"
NUR_PRUEFEN="${JARVIS_NUR_PRUEFEN:-0}"
TESTLAUF="${JARVIS_TESTLAUF:-0}"

sage()    { printf "  %s\n" "$1"; }
gut()     { printf "  \033[32m[ok]\033[0m %s\n" "$1"; }
hinweis() { printf "  \033[33m[--]\033[0m %s\n" "$1"; }
schlimm() { printf "  \033[31m[!!]\033[0m %s\n" "$1"; }
schritt() { printf "\n  \033[1m%s\033[0m\n" "$1"; }

# Rückfrage mit j/n. Gelesen wird direkt vom Terminal, auch wenn das Skript durch eine Pipe kommt.
frage_ja() {
    local antwort=""
    if [ "${JARVIS_JA:-0}" = "1" ]; then return 0; fi
    printf "  %s [j/n] " "$1"
    if ! read -r antwort 2>/dev/null < /dev/tty; then printf "\n"; return 1; fi
    case "$antwort" in j|J|ja|Ja|JA|y|Y|yes|Yes) return 0 ;; *) return 1 ;; esac
}

claude_finden() {
    local p
    for p in "$(command -v claude 2>/dev/null)" "$HOME/.local/bin/claude" "$HOME/.claude/local/claude" /opt/homebrew/bin/claude /usr/local/bin/claude; do
        if [ -n "$p" ] && [ -x "$p" ]; then printf "%s" "$p"; return 0; fi
    done
    return 1
}

printf "\n  ============================================================\n"
printf "   JARVIS wird eingerichtet\n"
printf "  ============================================================\n"

# --- 1. Mac ------------------------------------------------------------------
schritt "1. Mac prüfen"
SYSTEM="$(uname -s 2>/dev/null || echo unbekannt)"
if [ "$SYSTEM" != "Darwin" ] && [ "$NUR_PRUEFEN" != "1" ] && [ "$TESTLAUF" != "1" ]; then
    schlimm "JARVIS ist für den Mac gebaut (Stimme, Mitteilungen). Auf $SYSTEM läuft er nicht."
    exit 1
fi
gut "$SYSTEM $(sw_vers -productVersion 2>/dev/null)"

# --- 2. Apple-Werkzeuge (liefern Git und Python) -------------------------------
schritt "2. Apple-Entwicklerwerkzeuge prüfen"
if [ "$NUR_PRUEFEN" != "1" ] && [ "$TESTLAUF" != "1" ] && ! xcode-select -p >/dev/null 2>&1; then
    schlimm "Auf diesem Mac fehlen die Apple-Entwicklerwerkzeuge. Sie bringen Git und Python mit."
    sage "Jetzt öffnet sich ein Fenster von Apple. Klick auf „Installieren“ und warte, bis es fertig ist"
    sage "(ein paar Minuten). Danach DIESELBE Zeile einfach noch einmal einfügen."
    xcode-select --install >/dev/null 2>&1
    exit 1
fi
gut "vorhanden"

# --- 3. Python ---------------------------------------------------------------
schritt "3. Python prüfen"
if ! command -v "$PYTHON" >/dev/null 2>&1; then
    schlimm "Python (python3) wurde nicht gefunden."
    sage "Lösung: Die Apple-Entwicklerwerkzeuge installieren (Schritt 2) oder Python von python.org holen."
    exit 1
fi
if ! "$PYTHON" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 8) else 1)' 2>/dev/null; then
    schlimm "Dieses Python ist zu alt: $("$PYTHON" -V 2>&1). JARVIS braucht 3.8 oder neuer."
    sage "Lösung: Systemeinstellungen → Softwareupdate ausführen, oder Python von python.org installieren."
    exit 1
fi
gut "$("$PYTHON" -V 2>&1)"

# --- 4. Code holen -----------------------------------------------------------
schritt "4. JARVIS holen nach $ZIEL"
if ! command -v git >/dev/null 2>&1; then
    schlimm "Git fehlt. Lösung: Apple-Entwicklerwerkzeuge installieren (Schritt 2)."
    exit 1
fi
if [ "$NUR_PRUEFEN" = "1" ]; then
    hinweis "Nur prüfen: es wird nichts geholt und nichts gestartet."
    exit 0
fi
if [ -d "$ZIEL/.git" ]; then
    sage "Ordner gefunden, hole die neueste Fassung …"
    if git -C "$ZIEL" pull --ff-only --quiet origin "$ZWEIG"; then
        gut "auf dem neuesten Stand"
    else
        hinweis "Aktualisieren ging nicht (kein Internet oder eigene Änderungen). Ich nehme die vorhandene Fassung."
    fi
elif [ -e "$ZIEL" ]; then
    schlimm "$ZIEL gibt es schon, aber es ist keine Git-Kopie von JARVIS."
    sage "Nichts wurde verändert. Benenne den Ordner im Finder um (zum Beispiel „Santo-alt“) und führe die Zeile nochmal aus."
    exit 1
else
    sage "Lade den Code von GitHub (ein paar Sekunden) …"
    if git clone --quiet --branch "$ZWEIG" "$REPO" "$ZIEL" 2>/dev/null || git clone --quiet "$REPO" "$ZIEL"; then
        gut "heruntergeladen"
    else
        schlimm "Herunterladen hat nicht geklappt. Läuft das Internet? Dann dieselbe Zeile nochmal."
        exit 1
    fi
fi
chmod +x "$ZIEL/jarvis.sh" "$ZIEL"/*.command 2>/dev/null

# --- 5. Claude Code (das Denken von JARVIS, über dein Claude-Abo) ---------------
schritt "5. Claude Code prüfen"
CLAUDE="$(claude_finden)"
if [ -z "$CLAUDE" ]; then
    hinweis "Claude Code ist nicht installiert. Es ist das Gehirn von JARVIS und läuft über dein Claude-Abo."
    if frage_ja "Soll ich es installieren? (offizielle Anthropic-Zeile: curl -fsSL https://claude.ai/install.sh | bash)"; then
        curl -fsSL https://claude.ai/install.sh | bash
        CLAUDE="$(claude_finden)"
    fi
fi
if [ -z "$CLAUDE" ]; then
    schlimm "Ohne Claude Code kann JARVIS nicht denken. Installieren mit dieser Zeile, danach alles nochmal:"
    sage "curl -fsSL https://claude.ai/install.sh | bash"
else
    gut "gefunden: $CLAUDE"
    if ! (cd "$ZIEL" && ./jarvis.sh provider >/dev/null 2>&1); then
        hinweis "Claude Code ist noch nicht mit deinem Claude-Abo angemeldet."
        if frage_ja "Jetzt anmelden? Claude Code startet; wähle die Anmeldung mit deinem Claude-Konto (Abo), melde dich im Browser an und tippe danach /exit."; then
            "$CLAUDE" < /dev/tty
        fi
    fi
fi

# --- 6. Checkliste, Start ------------------------------------------------------
schritt "6. Alles prüfen und JARVIS starten"
cd "$ZIEL" || exit 1
./jarvis.sh pruefen
PRUEFUNG=$?
if ! ./jarvis.sh start; then
    schlimm "JARVIS ist nicht gestartet (Grund siehe oben)."
    sage "Schick mir ein Foto vom Terminal. Dann behebe ich es."
    exit 1
fi
./jarvis.sh oeffnen

printf "\n  ============================================================\n"
if [ "$PRUEFUNG" -eq 0 ]; then
    printf "   Fertig. JARVIS läuft und ist im Browser geöffnet.\n"
else
    printf "   JARVIS läuft, kann aber noch nicht denken.\n"
fi
printf "  ============================================================\n"
if [ "$PRUEFUNG" -ne 0 ]; then
    sage "Oben steht mit ✗, was fehlt, und darunter die Lösung. Danach: cd ~/Santo && ./jarvis.sh pruefen"
fi
sage "Beim nächsten Mal: Finder → dein Benutzername → Santo → Doppelklick auf „Jarvis-starten.command“."
sage "Beenden: Doppelklick auf „Jarvis-stoppen.command“. Alles Wichtige steht in JARVIS-SERVER.md."
sage "Ist oben etwas rot, schick mir ein Foto vom Terminal. Dann behebe ich es."
printf "\n"
