#!/bin/bash
# AUTONOMOUS – lokales KI-Modell „autonomous“ einrichten (Mac oder Linux). Einzeln nutzbar:
#
#   bash autonomous-ki-einrichten.sh
#
# Was passiert (sonst nichts):
#   1. prüft Python (3.9 oder neuer) und den Arbeitsspeicher (mindestens 4 GB)
#   2. wählt das Basismodell nach Arbeitsspeicher: unter 6 GB gemma3:1b, sonst gemma3:4b (im Prüfstand gemessen);
#      gemma3:12b nur auf ausdrücklichen Wunsch (AUTONOMOUS_KI_BASIS=gemma3:12b) – nicht geprüft
#   3. installiert Ollama, falls es fehlt – mit dem offiziellen Installationsskript von ollama.com (kostenlos)
#   4. startet Ollama, falls es nicht läuft
#   5. lädt das Basismodell, falls es fehlt (vorher: genug Speicherplatz?)
#   6. erstellt das eigene Modell „autonomous“ (Basismodell + fest eingebaute Arbeitsregeln, nicht neu trainiert)
#   7. prüft das Modell mit einem echten Probeaufruf und stellt erst DANN AUTONOMOUS um (Anbieter „ollama“, Modell
#      „autonomous“) – über die Einstellungen des Projekts, nie per SQL von Hand
# Mehrfach ausführen schadet nicht. Bricht etwas ab, bleibt AUTONOMOUS unverändert und läuft weiter wie bisher.
# Es stellt keine Fragen. Nur das offizielle Ollama-Installationsskript kann auf dem Mac nach dem Mac-Passwort fragen
# (für den Befehl „ollama“) – das Passwort geht nur an macOS, nie an AUTONOMOUS.
#
# Einstellbar (optional): AUTONOMOUS_KI_BASIS=gemma3:4b (Basismodell selbst wählen), AUTONOMOUS_PYTHON (Python),
# AUTONOMOUS_OLLAMA (Pfad zum Programm ollama), AUTONOMOUS_KI_RESERVE_MIB (frei bleibender Platz, Standard 2048),
# AUTONOMOUS_KI_WARTEN_S (Wartezeit auf den Ollama-Start, Standard 60), OLLAMA_MODELS (Modellordner).
# Nur für Tests: AUTONOMOUS_KI_RAM_MIB (erkannten Arbeitsspeicher vorgeben).

set -u
exec </dev/null   # nie von der Tastatur lesen (auch nicht bei „curl … | bash“)

meldung() { printf '%s\n' "$*"; }
abbruch() {
    printf 'ABBRUCH: %s\n' "$1" >&2
    printf 'AUTONOMOUS ist nicht verändert und läuft weiter wie bisher (ohne dieses KI-Modell).\n' >&2
    exit 1
}

HIER="$(cd "$(dirname "$0")" && pwd)" || abbruch "Ordner des Skripts nicht gefunden."
cd "$HIER" || abbruch "Ordner $HIER nicht lesbar."
[ -f "$HIER/autonomous/ki/einrichten.py" ] || abbruch "Ordner autonomous fehlt – das Skript gehört in den AUTONOMOUS-Ordner."
MODELL="autonomous"
TMP_DIR="$(mktemp -d)" || abbruch "Kein temporärer Ordner möglich."
trap 'rm -rf "$TMP_DIR"' EXIT

meldung "== Lokales KI-Modell für AUTONOMOUS einrichten =="

# 1) Python
PY="${AUTONOMOUS_PYTHON:-python3}"
if ! "$PY" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)' 2>/dev/null; then
    abbruch "Python 3.9 oder neuer fehlt (Mac: einmal 'xcode-select --install' ausführen)."
fi
helfer() { "$PY" -m autonomous.ki.einrichten "$@"; }

# 2) Arbeitsspeicher und Basismodell
SYSTEM="$(uname -s)"
case "$SYSTEM" in
    Darwin) RAM_MIB=$(( $(sysctl -n hw.memsize 2>/dev/null || echo 0) / 1048576 )) ;;
    Linux) RAM_MIB=$(( $(awk '/^MemTotal:/ {print $2}' /proc/meminfo 2>/dev/null || echo 0) / 1024 )) ;;
    *) abbruch "Betriebssystem $SYSTEM wird nicht unterstützt (nur Mac und Linux)." ;;
esac
RAM_MIB="${AUTONOMOUS_KI_RAM_MIB:-$RAM_MIB}"
case "$RAM_MIB" in ''|*[!0-9]*) abbruch "Arbeitsspeicher konnte nicht ermittelt werden." ;; esac
if [ "$RAM_MIB" -lt 4096 ]; then
    abbruch "Zu wenig Arbeitsspeicher: $RAM_MIB MB gefunden, mindestens 4096 MB (4 GB) nötig."
fi
BASIS="${AUTONOMOUS_KI_BASIS:-$(helfer basis --ram-mib "$RAM_MIB")}" || abbruch "Basismodell konnte nicht gewählt werden."
helfer groesse --basis "$BASIS" >/dev/null 2>&1 || abbruch "Ungültiger Name für das Basismodell: $BASIS"
meldung "Arbeitsspeicher: $RAM_MIB MB → Basismodell $BASIS"

# 3) Ollama finden oder mit dem offiziellen Skript installieren
finde_ollama() {
    if [ -n "${AUTONOMOUS_OLLAMA:-}" ]; then
        [ -x "$AUTONOMOUS_OLLAMA" ] && { printf '%s\n' "$AUTONOMOUS_OLLAMA"; return 0; }
        return 1
    fi
    if command -v ollama >/dev/null 2>&1; then command -v ollama; return 0; fi
    for kandidat in /usr/local/bin/ollama /opt/homebrew/bin/ollama /Applications/Ollama.app/Contents/Resources/ollama \
                    "$HOME/Applications/Ollama.app/Contents/Resources/ollama"; do
        if [ -x "$kandidat" ]; then printf '%s\n' "$kandidat"; return 0; fi
    done
    return 1
}
OLLAMA="$(finde_ollama)" || OLLAMA=""
if [ -z "$OLLAMA" ]; then
    meldung "Ollama ist nicht installiert – installiere es mit dem offiziellen Skript von ollama.com ..."
    curl -fsSL --max-time 120 https://ollama.com/install.sh -o "$TMP_DIR/install.sh" \
        || abbruch "Installationsskript von ollama.com nicht ladbar (Internet prüfen)."
    head -n 1 "$TMP_DIR/install.sh" | grep -q '^#!/bin/sh' || abbruch "Installationsskript sieht unerwartet aus."
    if [ "$SYSTEM" = "Darwin" ] && ! grep -q 'Darwin' "$TMP_DIR/install.sh"; then
        abbruch "Das Installationsskript unterstützt macOS nicht mehr – Ollama bitte von ollama.com/download laden."
    fi
    [ "$SYSTEM" = "Darwin" ] && meldung "Hinweis: Der Mac fragt eventuell nach deinem Passwort (für den Befehl 'ollama')."
    sh "$TMP_DIR/install.sh" || abbruch "Installation von Ollama fehlgeschlagen."
    OLLAMA="$(finde_ollama)" || abbruch "Ollama wurde installiert, aber das Programm 'ollama' ist nicht auffindbar."
else
    meldung "Ollama ist schon installiert: $OLLAMA"
fi

# 4) Ollama erreichbar? Sonst starten. Adresse wie in den AUTONOMOUS-Einstellungen (nur lokal erlaubt)
ADRESSE="$(helfer adresse)" || abbruch "AUTONOMOUS-Einstellungen nicht lesbar."
export OLLAMA_HOST="${ADRESSE#http://}"
erreichbar() { curl -fsS --noproxy '*' --max-time 3 "$ADRESSE/api/tags" >/dev/null 2>&1; }
if ! erreichbar; then
    meldung "Starte Ollama ..."
    if [ "$SYSTEM" = "Darwin" ] && [ -d /Applications/Ollama.app ]; then
        open -a Ollama --args hidden || true
    else
        nohup "$OLLAMA" serve >"${TMPDIR:-/tmp}/autonomous-ollama.log" 2>&1 &
    fi
    WARTEN="${AUTONOMOUS_KI_WARTEN_S:-60}"
    case "$WARTEN" in ''|*[!0-9]*) WARTEN=60 ;; esac
    i=0
    while ! erreichbar && [ "$i" -lt "$WARTEN" ]; do sleep 1; i=$((i + 1)); done
    erreichbar || abbruch "Ollama ist nicht erreichbar unter $ADRESSE – bitte das Programm Ollama öffnen und erneut versuchen."
fi
meldung "Ollama läuft unter $ADRESSE."

# 5) Basismodell laden, falls es fehlt – vorher Speicherplatz prüfen
vorhanden() {
    "$OLLAMA" list 2>/dev/null | awk 'NR > 1 {print $1}' | grep -Fqx -e "$1" -e "$1:latest"
}
if vorhanden "$BASIS"; then
    meldung "Basismodell $BASIS ist schon vorhanden."
else
    GROESSE_MIB="$(helfer groesse --basis "$BASIS")" || GROESSE_MIB=0
    RESERVE_MIB="${AUTONOMOUS_KI_RESERVE_MIB:-2048}"
    case "$RESERVE_MIB" in ''|*[!0-9]*) RESERVE_MIB=2048 ;; esac
    ORDNER="${OLLAMA_MODELS:-$HOME/.ollama}"
    while [ ! -d "$ORDNER" ] && [ "$ORDNER" != "/" ]; do ORDNER="$(dirname "$ORDNER")"; done
    FREI_MIB=$(( $(df -Pk "$ORDNER" | awk 'NR == 2 {print $4}') / 1024 ))
    NOETIG_MIB=$(( GROESSE_MIB + RESERVE_MIB ))
    if [ "$FREI_MIB" -lt "$NOETIG_MIB" ]; then
        abbruch "Zu wenig Speicherplatz: frei $FREI_MIB MB, nötig $NOETIG_MIB MB ($BASIS $GROESSE_MIB MB + $RESERVE_MIB MB Reserve)."
    fi
    meldung "Lade Basismodell $BASIS ($GROESSE_MIB MB, frei: $FREI_MIB MB) – das dauert je nach Internet einige Minuten ..."
    "$OLLAMA" pull "$BASIS" || abbruch "Download von $BASIS fehlgeschlagen."
fi

# 6) Eigenes Modell „autonomous“ erstellen (bei jedem Lauf neu – so stecken immer die aktuellen Regeln darin)
helfer modelfile --basis "$BASIS" >"$TMP_DIR/Modelfile" || abbruch "Modelfile konnte nicht erzeugt werden."
printf 'Erstelle das Modell „%s“ (Basismodell %s mit fest eingebauten Arbeitsregeln) ...\n' "$MODELL" "$BASIS"
"$OLLAMA" create "$MODELL" -f "$TMP_DIR/Modelfile" || abbruch "Erstellen des Modells $MODELL fehlgeschlagen."

# 7) Echter Probeaufruf, erst danach AUTONOMOUS umstellen
helfer einstellen --modell "$MODELL" || abbruch "Das Modell $MODELL antwortet nicht – Einstellungen bleiben, wie sie waren."

meldung ""
printf 'Fertig. AUTONOMOUS nutzt jetzt das lokale Modell „%s“ (Basis %s). Alles bleibt auf diesem Rechner.\n' "$MODELL" "$BASIS"
meldung 'Jede KI-Ausgabe ist als „KI-Entwurf – ungeprüft“ gekennzeichnet; ohne KI läuft AUTONOMOUS genauso weiter.'
meldung 'Ausschalten: in AUTONOMOUS unter Einstellungen → KI-Modell den Anbieter „keiner“ wählen.'
