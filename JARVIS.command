#!/bin/bash
# ---------------------------------------------------------------------------
# Jarvis starten. Beim allerersten Mal richtet sich alles selbst ein.
#
# Der Nutzer klickt diese Datei doppelt an - mehr soll er nicht tun müssen.
# Deshalb wird hier alles geprüft und nachinstalliert, was fehlt, und jeder
# Schritt sagt auf Deutsch, was gerade passiert.
#
# Pakete werden EINZELN installiert. Bricht eines ab, laufen die anderen
# trotzdem durch - und Jarvis läuft dann eben ohne diese eine Funktion.
# ---------------------------------------------------------------------------

cd "$(dirname "$0")" || exit 1
PROJEKT="$(pwd)"
UMGEBUNG="$PROJEKT/.venv"
ENV_DATEI="$PROJEKT/config/.env"

echo ""
echo "  ============================================================"
echo "   JARVIS - persönlicher Assistent"
echo "  ============================================================"
echo ""

# --- 1. Python -------------------------------------------------------------

if ! command -v python3 >/dev/null 2>&1; then
    echo "  Auf diesem Mac ist kein Python installiert."
    echo "  Ich öffne die Download-Seite. Lade dort Python herunter,"
    echo "  installiere es und starte diese Datei danach noch einmal."
    open "https://www.python.org/downloads/macos/" 2>/dev/null
    echo ""
    read -r -p "  Enter zum Schließen "
    exit 1
fi

PY_VERSION="$(python3 -c 'import sys; print("%d.%d" % sys.version_info[:2])' 2>/dev/null)"
echo "  Python $PY_VERSION gefunden."

# --- 2. Homebrew und Systemwerkzeuge --------------------------------------

if ! command -v brew >/dev/null 2>&1; then
    echo ""
    echo "  Homebrew ist nicht installiert. Damit bekomme ich das Mikrofon,"
    echo "  die Kamera und die Tonausgabe zum Laufen. Ohne Homebrew geht"
    echo "  Jarvis trotzdem - dann aber ohne Sprachaufnahme."
    read -r -p "  Homebrew jetzt installieren? (ja/nein) " ANTWORT
    if [ "$ANTWORT" = "ja" ] || [ "$ANTWORT" = "j" ]; then
        echo "  Das dauert ein paar Minuten und fragt nach deinem Passwort."
        /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
        # Nach der Installation liegt brew je nach Mac woanders.
        for BREW_PFAD in /opt/homebrew/bin/brew /usr/local/bin/brew; do
            [ -x "$BREW_PFAD" ] && eval "$("$BREW_PFAD" shellenv)"
        done
    fi
fi

if command -v brew >/dev/null 2>&1; then
    # portaudio: Mikrofon. imagesnap: Kamera. ffmpeg und mpg123: Ton.
    for WERKZEUG in portaudio imagesnap ffmpeg mpg123; do
        if brew list --formula "$WERKZEUG" >/dev/null 2>&1; then
            echo "  [ok] $WERKZEUG"
        else
            echo "  Installiere $WERKZEUG ..."
            brew install "$WERKZEUG" >/dev/null 2>&1 \
                && echo "  [ok] $WERKZEUG" \
                || echo "  [--] $WERKZEUG ließ sich nicht installieren - das Übrige läuft weiter."
        fi
    done
fi

# --- 3. Python-Umgebung ----------------------------------------------------

if [ ! -d "$UMGEBUNG" ]; then
    echo ""
    echo "  Ich lege eine eigene Python-Umgebung an, damit nichts am System"
    echo "  verändert wird."
    python3 -m venv "$UMGEBUNG" || {
        echo "  Die Umgebung ließ sich nicht anlegen. Ich arbeite ohne sie weiter."
    }
fi

if [ -f "$UMGEBUNG/bin/activate" ]; then
    # shellcheck disable=SC1091
    . "$UMGEBUNG/bin/activate"
    PYTHON="$UMGEBUNG/bin/python"
else
    PYTHON="python3"
fi

# --- 4. Pakete einzeln installieren ---------------------------------------

PAKET_MARKE="$PROJEKT/.pakete_installiert"
if [ ! -f "$PAKET_MARKE" ]; then
    echo ""
    echo "  Ich installiere die benötigten Pakete. Jedes einzeln - wenn eines"
    echo "  fehlschlägt, läuft der Rest trotzdem."
    echo ""
    "$PYTHON" -m pip install --upgrade pip >/dev/null 2>&1

    # numpy und sounddevice: Mikrofon. faster-whisper: Spracherkennung ohne
    # Kosten. pyautogui und pillow: Bildschirmsteuerung.
    for PAKET in numpy sounddevice faster-whisper pyautogui pillow playwright; do
        printf "  %-16s " "$PAKET"
        if "$PYTHON" -m pip install "$PAKET" >/dev/null 2>&1; then
            echo "[ok]"
        else
            echo "[--] nicht installiert, Jarvis läuft ohne diese Funktion"
        fi
    done
    # Playwright braucht nach dem Paket noch den Browser selbst. Ohne diesen
    # zweiten Schritt ist das Paket da, aber nichts laesst sich oeffnen.
    if "$PYTHON" -c "import playwright" >/dev/null 2>&1; then
        printf "  %-16s " "Browser"
        if "$PYTHON" -m playwright install chromium >/dev/null 2>&1; then
            echo "[ok]"
        else
            echo "[--] Jarvis kann dann keine Webseiten selbst bedienen"
        fi
    fi
    touch "$PAKET_MARKE"
    echo ""
    echo "  Für die Stimmerkennung gibt es noch das Paket resemblyzer."
    echo "  Es ist groß (etwa zwei Gigabyte) und nur nötig, wenn Jarvis"
    echo "  ausschließlich auf deine Stimme reagieren soll."
    read -r -p "  Jetzt mitinstallieren? (ja/nein) " ANTWORT
    if [ "$ANTWORT" = "ja" ] || [ "$ANTWORT" = "j" ]; then
        "$PYTHON" -m pip install resemblyzer \
            && echo "  [ok] resemblyzer" \
            || echo "  [--] resemblyzer nicht installiert"
    fi
fi

# --- 5. Einrichten oder starten -------------------------------------------

BRAUCHT_EINRICHTUNG="ja"
if [ -f "$ENV_DATEI" ] && grep -q "^ANTHROPIC_API_KEY=sk-" "$ENV_DATEI" 2>/dev/null; then
    BRAUCHT_EINRICHTUNG="nein"
fi

echo ""
if [ "$BRAUCHT_EINRICHTUNG" = "ja" ]; then
    echo "  Jarvis ist noch nicht eingerichtet. Ich starte die Einrichtung."
    echo "  Ich lese dir alles vor - du musst nichts mitlesen."
    echo ""
    "$PYTHON" "$PROJEKT/jarvis.py" einrichten
    echo ""
    echo "  ============================================================"
    echo "   WICHTIG: Schließe dieses Fenster jetzt komplett und starte"
    echo "   JARVIS.command danach neu. Sonst greifen die erteilten"
    echo "   Rechte nicht."
    echo "  ============================================================"
    echo ""
    read -r -p "  Enter zum Schließen "
    exit 0
fi

# Einmalig: Jarvis als Programm mit Symbol (Dock, Programme, Schreibtisch).
if [ "$(uname)" = "Darwin" ] && [ ! -d "/Applications/Jarvis.app" ] && [ ! -d "$HOME/Applications/Jarvis.app" ]; then
    "$PYTHON" "$PROJEKT/jarvis.py" macapp >/dev/null 2>&1 \
        && echo "  Jarvis liegt jetzt auch als Programm im Dock - das Gehirn-Symbol."
fi

echo "  Ich starte und oeffne mich im Browser. Abbrechen mit Strg und C."
echo ""
"$PYTHON" "$PROJEKT/jarvis.py" "$@"
ERGEBNIS=$?

echo ""
if [ $ERGEBNIS -ne 0 ] && [ $ERGEBNIS -ne 130 ]; then
    echo "  Jarvis hat sich mit einem Fehler beendet (Code $ERGEBNIS)."
    echo "  Ein Selbsttest zeigt, woran es liegt:"
    echo "     Doppelklick auf EXTRAS.command, dann Punkt 1"
fi
read -r -p "  Enter zum Schließen "
