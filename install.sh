#!/bin/bash
# ---------------------------------------------------------------------------
# Jarvis in einem Rutsch einrichten.
#
# Eine Zeile im Terminal, mehr muss der Nutzer nicht tun:
#
#   curl -fsSL https://raw.githubusercontent.com/santananikolic-byte/Santo/claude/jarvis-voice-assistant-70695g/install.sh | bash
#
# Das Skript laedt Jarvis nach ~/Jarvis, holt was fehlt, legt eine
# Verknuepfung auf den Schreibtisch und startet die Einrichtung.
#
# Zum Ausprobieren ohne Mac: JARVIS_NUR_PRUEFEN=1 bash install.sh
# ---------------------------------------------------------------------------

set -u

REPO="https://github.com/santananikolic-byte/Santo"
ZWEIG="claude/jarvis-voice-assistant-70695g"
ZIEL="${JARVIS_ZIEL:-$HOME/Jarvis}"
NUR_PRUEFEN="${JARVIS_NUR_PRUEFEN:-0}"

# Wird das Skript durch eine Pipe gelesen, haengt stdin an curl statt am
# Terminal - jede Rueckfrage wuerde dann ins Leere laufen. Deshalb die
# Tastatur wieder anklemmen.
# Erst in einer Unterschale probieren - schlaegt das fehl (etwa in einer
# Pipeline ohne Terminal), bleibt es still, statt eine Fehlermeldung
# auszuwerfen, die den Nutzer beunruhigt.
if [ ! -t 0 ] && (exec < /dev/tty) 2>/dev/null; then
    exec < /dev/tty
fi

sage()   { printf "  %s\n" "$1"; }
gut()    { printf "  \033[32m[ok]\033[0m %s\n" "$1"; }
ohne()   { printf "  \033[33m[--]\033[0m %s\n" "$1"; }
schlimm(){ printf "  \033[31m[!!]\033[0m %s\n" "$1"; }

printf "\n"
printf "  ============================================================\n"
printf "   JARVIS wird eingerichtet\n"
printf "  ============================================================\n\n"

# --- 1. Ist das ein Mac? ---------------------------------------------------

SYSTEM="$(uname -s 2>/dev/null || echo unbekannt)"
if [ "$SYSTEM" != "Darwin" ] && [ "$NUR_PRUEFEN" != "1" ]; then
    schlimm "Jarvis braucht einen Mac."
    sage "Zuhoeren, Sprechen und die Kamera gibt es nur unter macOS."
    sage "Auf diesem System ($SYSTEM) laeuft er nicht."
    exit 1
fi

# --- 2. Python -------------------------------------------------------------

if ! command -v python3 >/dev/null 2>&1; then
    schlimm "Auf diesem Mac fehlt Python."
    sage "Ich oeffne die Download-Seite. Installiere Python und fuehre"
    sage "diese eine Zeile danach noch einmal aus."
    command -v open >/dev/null 2>&1 && open "https://www.python.org/downloads/macos/"
    exit 1
fi
gut "Python $(python3 -c 'import sys;print("%d.%d"%sys.version_info[:2])')"

# --- 3. Systemwerkzeuge ----------------------------------------------------

if [ "$NUR_PRUEFEN" != "1" ]; then
    if ! command -v brew >/dev/null 2>&1; then
        for KANDIDAT in /opt/homebrew/bin/brew /usr/local/bin/brew; do
            [ -x "$KANDIDAT" ] && eval "$("$KANDIDAT" shellenv)"
        done
    fi
    if ! command -v brew >/dev/null 2>&1; then
        printf "\n"
        sage "Fuer Mikrofon, Kamera und Ton brauche ich Homebrew."
        sage "Ohne laeuft Jarvis, aber ohne Sprachaufnahme."
        printf "  Homebrew jetzt installieren? (ja/nein) "
        read -r ANTWORT
        case "$ANTWORT" in
            ja|j|Ja|J)
                /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
                for KANDIDAT in /opt/homebrew/bin/brew /usr/local/bin/brew; do
                    [ -x "$KANDIDAT" ] && eval "$("$KANDIDAT" shellenv)"
                done
                ;;
        esac
    fi
    if command -v brew >/dev/null 2>&1; then
        # portaudio: Mikrofon. imagesnap: Kamera. ffmpeg/mpg123: Ton.
        for WERKZEUG in portaudio imagesnap ffmpeg mpg123; do
            if brew list --formula "$WERKZEUG" >/dev/null 2>&1; then
                gut "$WERKZEUG"
            else
                printf "  installiere %s ...\r" "$WERKZEUG"
                if brew install "$WERKZEUG" >/dev/null 2>&1; then
                    gut "$WERKZEUG                    "
                else
                    ohne "$WERKZEUG liess sich nicht installieren"
                fi
            fi
        done
    else
        ohne "ohne Homebrew: kein Mikrofon, keine Kamera"
    fi
fi

# --- 4. Jarvis holen -------------------------------------------------------

printf "\n"
NEUINSTALLATION="ja"
if [ -d "$ZIEL/.git" ]; then
    NEUINSTALLATION="nein"
    sage "Jarvis liegt schon in $ZIEL - ich hole nur die Neuerungen."
    # Einstellungen und Gedaechtnis bleiben unangetastet: beide stehen in
    # .gitignore und werden von git nie ueberschrieben.
    ( cd "$ZIEL" && git fetch --quiet origin "$ZWEIG" \
        && git checkout --quiet -B jarvis "origin/$ZWEIG" ) \
        && gut "aktualisiert" || ohne "Aktualisierung fehlgeschlagen, ich nehme den vorhandenen Stand"
elif command -v git >/dev/null 2>&1; then
    sage "Ich lade Jarvis nach $ZIEL"
    if git clone --quiet --branch "$ZWEIG" --depth 1 "$REPO" "$ZIEL"; then
        gut "geladen"
    else
        schlimm "Der Download ist fehlgeschlagen. Ist das Internet da?"
        exit 1
    fi
else
    sage "Ich lade Jarvis nach $ZIEL"
    ARCHIV="$(mktemp -t jarvis).zip"
    if curl -fsSL "$REPO/archive/refs/heads/$ZWEIG.zip" -o "$ARCHIV"; then
        AUSPACKEN="$(mktemp -d)"
        unzip -q "$ARCHIV" -d "$AUSPACKEN"
        mkdir -p "$ZIEL"
        cp -R "$AUSPACKEN"/*/. "$ZIEL"/
        rm -rf "$ARCHIV" "$AUSPACKEN"
        gut "geladen"
    else
        schlimm "Der Download ist fehlgeschlagen. Ist das Internet da?"
        exit 1
    fi
fi

cd "$ZIEL" || exit 1
chmod +x JARVIS.command EXTRAS.command 2>/dev/null

# --- 5. Python-Pakete ------------------------------------------------------

printf "\n"
if [ ! -d "$ZIEL/.venv" ]; then
    sage "Ich lege eine eigene Python-Umgebung an, damit am System nichts"
    sage "veraendert wird."
    python3 -m venv "$ZIEL/.venv" >/dev/null 2>&1 || ohne "Umgebung nicht anlegbar, ich nehme das System-Python"
fi
if [ -x "$ZIEL/.venv/bin/python" ]; then
    PYTHON="$ZIEL/.venv/bin/python"
else
    PYTHON="python3"
fi

"$PYTHON" -m pip install --quiet --upgrade pip >/dev/null 2>&1
printf "\n"
sage "Pakete - jedes einzeln, damit ein Fehlschlag nicht alles mitreisst:"
for PAKET in numpy sounddevice faster-whisper pyautogui pillow playwright; do
    printf "  %-16s\r" "$PAKET"
    if "$PYTHON" -m pip install --quiet "$PAKET" >/dev/null 2>&1; then
        gut "$PAKET            "
    else
        ohne "$PAKET - Jarvis laeuft ohne diese Funktion"
    fi
done

# Playwright bringt den Browser nicht mit - der kommt in einem zweiten Schritt.
if "$PYTHON" -c "import playwright" >/dev/null 2>&1; then
    printf "  %-16s\r" "Browser"
    if "$PYTHON" -m playwright install chromium >/dev/null 2>&1; then
        gut "Browser            "
    else
        ohne "Browser - Jarvis kann dann keine Webseiten selbst bedienen"
    fi
fi

# --- 6. Verknuepfung auf dem Schreibtisch ----------------------------------

if [ -d "$HOME/Desktop" ] && [ "$NUR_PRUEFEN" != "1" ]; then
    ln -sf "$ZIEL/JARVIS.command" "$HOME/Desktop/Jarvis.command" 2>/dev/null \
        && gut "Verknuepfung auf dem Schreibtisch angelegt"
fi

# --- 7. Selbsttest ---------------------------------------------------------

printf "\n"
sage "Ich pruefe mich einmal selbst ..."
printf "\n"
"$PYTHON" "$ZIEL/jarvis.py" test < /dev/null 2>&1 | tail -n 22

if [ "$NUR_PRUEFEN" = "1" ]; then
    printf "\n"
    gut "Pruefdurchlauf beendet - eingerichtet und gestartet wird hier nichts."
    exit 0
fi

# --- 8. Einrichtung und Start ---------------------------------------------

printf "\n"
if grep -q "^ANTHROPIC_API_KEY=sk-" "$ZIEL/config/.env" 2>/dev/null; then
    sage "Jarvis ist schon eingerichtet. Ich starte ihn."
    printf "\n"
    exec "$PYTHON" "$ZIEL/jarvis.py"
fi

printf "  ============================================================\n"
printf "   Jarvis startet jetzt. Im Browser erscheint ein Feld, in das\n"
printf "   du deinen Anthropic-Schluessel einfuegst. Danach geht es los.\n"
printf "   (Die gefuehrte Einrichtung mit Sprache: jarvis.py einrichten)\n"
printf "  ============================================================\n\n"
exec "$PYTHON" "$ZIEL/jarvis.py"
