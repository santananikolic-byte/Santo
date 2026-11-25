#!/bin/bash
# AUTONOMOUS mit einer Zeile einrichten oder aktualisieren (Mac, Terminal):
#
#   curl -fsSL https://raw.githubusercontent.com/santananikolic-byte/Santo/claude/elegant-meitner-ho9kqz/autonomous-einrichten.sh | bash
#
# Was passiert (sonst nichts):
#   1. prüft, ob Python 3.9 oder neuer eingerichtet ist (sonst klare Meldung, nichts wird installiert)
#   2. lädt AUTONOMOUS von GitHub nach ~/AUTONOMOUS (öffentliches Repository, kein Konto nötig)
#   3. bei einer Aktualisierung bleiben eure Daten erhalten (Ordner autonomous/daten wird nie überschrieben)
#   4. Dauerbetrieb auf dem Mac: AUTONOMOUS läuft wie ein eigener Server – startet bei jeder Anmeldung von selbst
#      und nach einem Absturz neu (LaunchAgent ~/Library/LaunchAgents/de.autonomous.server.plist, nur euer Benutzer)
#   5. legt auf dem Schreibtisch „AUTONOMOUS starten“, „AUTONOMOUS stoppen“ und „AUTONOMOUS Autostart aus“ an
#   6. startet AUTONOMOUS und öffnet die Oberfläche im Browser
#   7. richtet die lokale KI ein (autonomous-ki-einrichten.sh): installiert das kostenlose Programm Ollama, falls es
#      fehlt (offizielles Skript von ollama.com – der Mac kann dabei nach eurem Passwort fragen, das geht nur an
#      macOS), lädt einmalig ein Basismodell (0,8 GB bei unter 6 GB Arbeitsspeicher, sonst 3,2 GB) und erstellt das
#      eigene Modell „autonomous“. Scheitert das, läuft AUTONOMOUS trotzdem – nur ohne KI.
# AUTONOMOUS selbst braucht kein sudo und keine Zusatzpakete. Keine bezahlten Dienste.

# Alles in einer Funktion: ein abgebrochener Download führt nichts halb aus.
haupt() {
    set -u
    ZWEIG="claude/elegant-meitner-ho9kqz"
    ZIEL="${AUTONOMOUS_ZIEL:-$HOME/AUTONOMOUS}"
    ZIP_URL="https://codeload.github.com/santananikolic-byte/Santo/zip/refs/heads/$ZWEIG"

    echo "AUTONOMOUS einrichten nach: $ZIEL"

    # 1) Python wirklich ausführbar und neu genug?
    VERSION="$(python3 -c 'import sys; print("%d.%d" % sys.version_info[:2])' 2>/dev/null)"
    if [ -z "$VERSION" ]; then
        echo "Python 3 ist nicht eingerichtet. Bitte einmal 'xcode-select --install' ausführen (Apple, kostenlos)"
        echo "und danach diese Zeile erneut einfügen."
        return 1
    fi
    if ! python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)'; then
        echo "Python $VERSION ist zu alt – AUTONOMOUS braucht Python 3.9 oder neuer."
        return 1
    fi
    echo "Python $VERSION gefunden."

    # 2) Laufende Fassung vor dem Aktualisieren sauber beenden (auch den Dauerbetrieb)
    if [ -x "$ZIEL/AUTONOMOUS-stoppen.command" ]; then
        "$ZIEL/AUTONOMOUS-stoppen.command" </dev/null >/dev/null 2>&1
    fi
    LABEL="de.autonomous.server"
    PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
    if command -v launchctl >/dev/null 2>&1; then
        launchctl bootout "gui/$(id -u)/$LABEL" >/dev/null 2>&1  # alte Fassung entladen – wird unten neu geladen
    fi

    # 3) Herunterladen und entpacken (Python statt unzip – überall vorhanden)
    TMP="$(mktemp -d)" || return 1
    trap 'rm -rf "$TMP"' RETURN
    echo "Lade AUTONOMOUS herunter ..."
    if ! curl -fsSL --max-time 300 "$ZIP_URL" -o "$TMP/autonomous.zip"; then
        echo "Download fehlgeschlagen. Bitte Internetverbindung prüfen und erneut versuchen."
        return 1
    fi
    python3 -m zipfile -e "$TMP/autonomous.zip" "$TMP/entpackt" || { echo "Entpacken fehlgeschlagen."; return 1; }
    QUELLE="$(find "$TMP/entpackt" -mindepth 1 -maxdepth 1 -type d | head -n 1)"
    if [ -z "$QUELLE" ] || [ ! -f "$QUELLE/autonomous/__main__.py" ]; then
        echo "Heruntergeladene Daten sind unvollständig – nichts wurde verändert."
        return 1
    fi

    # 4) Kopieren – eure Daten (autonomous/daten) sind nicht im Download und bleiben unberührt
    mkdir -p "$ZIEL" || return 1
    cp -R "$QUELLE/." "$ZIEL/" || { echo "Kopieren fehlgeschlagen."; return 1; }
    chmod +x "$ZIEL"/*.command "$ZIEL"/*.sh 2>/dev/null

    # 5) Dauerbetrieb (nur Mac): LaunchAgent schreiben – geladen wird er beim Starten (Schritt 7)
    if command -v launchctl >/dev/null 2>&1; then
        if (cd "$ZIEL" && python3 -m autonomous.autostart schreiben "$(command -v python3)" "$ZIEL" "$PLIST" >/dev/null) \
            && { ! command -v plutil >/dev/null 2>&1 || plutil -lint "$PLIST" >/dev/null; }; then
            echo "Dauerbetrieb eingerichtet: AUTONOMOUS startet bei jeder Anmeldung am Mac von selbst."
        else
            rm -f "$PLIST"
            echo "Dauerbetrieb konnte nicht eingerichtet werden – AUTONOMOUS startet dann nur per Doppelklick."
        fi
    fi

    # 6) Start-Symbole auf dem Schreibtisch (kleine Startdateien, die die echten Skripte aufrufen)
    if [ -d "$HOME/Desktop" ]; then
        printf '#!/bin/bash\nexec "%s/AUTONOMOUS-starten.command"\n' "$ZIEL" > "$HOME/Desktop/AUTONOMOUS starten.command"
        printf '#!/bin/bash\nexec "%s/AUTONOMOUS-stoppen.command"\n' "$ZIEL" > "$HOME/Desktop/AUTONOMOUS stoppen.command"
        chmod +x "$HOME/Desktop/AUTONOMOUS starten.command" "$HOME/Desktop/AUTONOMOUS stoppen.command"
        echo "Auf dem Schreibtisch liegen jetzt 'AUTONOMOUS starten' und 'AUTONOMOUS stoppen'."
        if [ -f "$PLIST" ]; then
            printf '#!/bin/bash\nexec "%s/AUTONOMOUS-autostart-aus.command"\n' "$ZIEL" > "$HOME/Desktop/AUTONOMOUS Autostart aus.command"
            chmod +x "$HOME/Desktop/AUTONOMOUS Autostart aus.command"
            echo "Dazu 'AUTONOMOUS Autostart aus' – schaltet den Dauerbetrieb ganz ab."
        fi
    fi

    # 7) Starten (mit Dauerbetrieb über macOS, sonst im Hintergrund) und Browser öffnen
    "$ZIEL/AUTONOMOUS-starten.command" </dev/null || return 1
    if [ -f "$ZIEL/autonomous-ki-einrichten.sh" ]; then bash "$ZIEL/autonomous-ki-einrichten.sh"; fi
}

haupt "$@"
