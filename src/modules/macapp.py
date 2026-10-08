#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Jarvis als richtiges Programm auf dem Mac - mit Symbol, im Programme-Ordner und im Dock.

Ein Klick auf das Gehirn-Symbol, und Jarvis öffnet sich in einem eigenen
Fenster - ohne Terminal, ohne Adressleiste. Dahinter steckt dasselbe Jarvis wie
nach dem Doppelklick auf ``JARVIS.command``:

* Läuft Jarvis noch nicht, startet die App ihn im Hintergrund (Protokoll in
  ``logs/app.log``) und wartet, bis er bereit ist.
* Läuft er schon, öffnet sie nur das Fenster.
* Das Fenster ist ein App-Fenster von Chrome oder Edge, wenn eines davon da
  ist (ohne Tabs und Adressleiste); sonst der normale Browser.

Die App wird **auf dem Mac selbst gebaut** (``python3 jarvis.py macapp``, das
erledigen Installation und erster Start). Was auf dem Rechner entsteht, ist
nicht aus dem Internet geladen - deshalb fragt macOS nicht nach einem
"nicht verifizierten Entwickler".
"""

import os
import plistlib
import shlex
import shutil
import subprocess
import tempfile
import zipfile
from pathlib import Path

import config

APP_NAME = "Jarvis.app"
BUNDLE_ID = "at.jarvis.app"
SYMBOL_GROESSEN = (16, 32, 64, 128, 256, 512)
WEB_PORT = 8765

STARTSKRIPT = r"""#!/bin/bash
# Jarvis starten - wie ein Programm. Erzeugt von "python3 jarvis.py macapp".
PROJEKT=__PROJEKT__
PYTHON=__PYTHON__
PORT=__PORT__
LOG="$PROJEKT/logs/app.log"

mkdir -p "$PROJEKT/logs"
cd "$PROJEKT" || exit 1
[ -x "$PYTHON" ] || PYTHON="$(command -v python3)"

laeuft() { nc -z 127.0.0.1 "$PORT" >/dev/null 2>&1; }

# Laeuft er schon? Dann nur das Fenster oeffnen.
if ! laeuft; then
    nohup "$PYTHON" "$PROJEKT/jarvis.py" web --ohne-browser >>"$LOG" 2>&1 &
    for _ in $(seq 1 80); do
        laeuft && break
        sleep 0.5
    done
fi

ADRESSE="http://localhost:$PORT/"
for BROWSER in "Google Chrome" "Microsoft Edge" "Brave Browser" "Chromium"; do
    if [ -d "/Applications/$BROWSER.app" ] || [ -d "$HOME/Applications/$BROWSER.app" ]; then
        # App-Fenster: ohne Tabs und Adressleiste, wie ein eigenes Programm.
        exec open -na "$BROWSER" --args --app="$ADRESSE" --window-size=1280,860
    fi
done
exec open "$ADRESSE"
"""


INSTALL_URL = ("https://raw.githubusercontent.com/santananikolic-byte/Santo/"
               "claude/new-session-o54yqu/install.sh")

# Die App zum Herunterladen: beim ersten Start richtet sie Jarvis ein, danach startet sie ihn.
DOWNLOAD_KOPF = r"""#!/bin/bash
# Jarvis - das Programm zum Herunterladen.
# Beim ersten Start holt es Jarvis nach ~/Jarvis und richtet ihn ein (im Terminal,
# weil dort die Schluessel eingegeben werden). Danach startet es Jarvis direkt.
ZIEL="$HOME/Jarvis"
if [ ! -f "$ZIEL/jarvis.py" ] || ! grep -q "^ANTHROPIC_API_KEY=sk-" "$ZIEL/config/.env" 2>/dev/null; then
    osascript -e 'tell application "Terminal" to activate' \
              -e 'tell application "Terminal" to do script "curl -fsSL __INSTALL_URL__ | bash"'
    exit 0
fi
"""


def icns_schreiben(bilder: dict, ziel) -> bool:
    """Schreibt ein Mac-Symbol (.icns) aus fertigen PNG-Bildern - ohne Mac-Werkzeuge.

    ``bilder`` ordnet Kennungen PNG-Daten zu: ic07 128, ic08 256, ic09 512,
    ic10 1024 (512 doppelt), ic13 256 (128 doppelt), ic14 512 (256 doppelt).
    """
    teile = b""
    for kennung in ("ic07", "ic08", "ic09", "ic10", "ic13", "ic14"):
        daten = bilder.get(kennung)
        if daten:
            teile += kennung.encode("ascii") + (len(daten) + 8).to_bytes(4, "big") + daten
    if not teile:
        return False
    try:
        Path(ziel).write_bytes(b"icns" + (len(teile) + 8).to_bytes(4, "big") + teile)
        return True
    except OSError:
        return False


def info_plist() -> dict:
    """Die Angaben, an denen macOS ein Programm erkennt."""
    return {
        "CFBundleName": "Jarvis",
        "CFBundleDisplayName": "Jarvis",
        "CFBundleIdentifier": BUNDLE_ID,
        "CFBundleVersion": "1",
        "CFBundleShortVersionString": "1.0",
        "CFBundlePackageType": "APPL",
        "CFBundleExecutable": "Jarvis",
        "CFBundleIconFile": "Jarvis",
        "LSMinimumSystemVersion": "10.13",
        "NSHighResolutionCapable": True,
        "LSApplicationCategoryType": "public.app-category.productivity",
    }


def startskript(projekt: str, python: str, port: int = WEB_PORT) -> str:
    """Das Startskript der App - Pfade sicher in Anführungszeichen, auch mit Leerzeichen."""
    return (STARTSKRIPT.replace("__PROJEKT__", shlex.quote(str(projekt)))
            .replace("__PYTHON__", shlex.quote(str(python)))
            .replace("__PORT__", str(int(port))))


def _ausfuehren(befehl: list, timeout: int = 60) -> bool:
    try:
        return subprocess.run(befehl, capture_output=True, timeout=timeout,
                              shell=False).returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def symbol_bauen(png: Path, ziel_icns: Path, ausfuehren=None) -> bool:
    """Macht aus dem Gehirn-Bild ein Mac-Symbol (.icns) - mit sips und iconutil, beide sind dabei."""
    ausfuehren = ausfuehren or _ausfuehren
    if not png.exists() or not shutil.which("sips") or not shutil.which("iconutil"):
        return False
    satz = ziel_icns.parent / "Jarvis.iconset"
    satz.mkdir(parents=True, exist_ok=True)
    try:
        for groesse in SYMBOL_GROESSEN:
            for faktor, endung in ((1, ""), (2, "@2x")):
                pixel = groesse * faktor
                datei = satz / ("icon_%dx%d%s.png" % (groesse, groesse, endung))
                if not ausfuehren(["sips", "-z", str(pixel), str(pixel), str(png),
                                   "--out", str(datei)]):
                    return False
        return ausfuehren(["iconutil", "-c", "icns", str(satz), "-o", str(ziel_icns)])
    finally:
        shutil.rmtree(satz, ignore_errors=True)


def app_ordner() -> Path:
    """Wohin die App kommt: Programme, sonst der eigene Programme-Ordner."""
    for ordner in (Path("/Applications"), Path.home() / "Applications"):
        try:
            ordner.mkdir(parents=True, exist_ok=True)
            if os.access(ordner, os.W_OK):
                return ordner
        except OSError:
            continue
    return Path.home() / "Applications"


def ins_dock(app: Path, ausfuehren=None) -> bool:
    """Legt die App ins Dock - nur wenn sie dort noch nicht liegt."""
    ausfuehren = ausfuehren or _ausfuehren
    if not shutil.which("defaults"):
        return False
    try:
        vorhanden = subprocess.run(["defaults", "read", "com.apple.dock", "persistent-apps"],
                                   capture_output=True, text=True, timeout=20).stdout
    except (OSError, subprocess.SubprocessError):
        return False
    if str(app) in vorhanden or "at.jarvis.app" in vorhanden:
        return True
    eintrag = ("<dict><key>tile-data</key><dict><key>file-data</key><dict>"
               "<key>_CFURLString</key><string>file://%s/</string>"
               "<key>_CFURLStringType</key><integer>15</integer>"
               "</dict></dict></dict>" % str(app).replace("&", "&amp;").replace("<", "&lt;"))
    if not ausfuehren(["defaults", "write", "com.apple.dock", "persistent-apps",
                       "-array-add", eintrag]):
        return False
    return ausfuehren(["killall", "Dock"])


def app_bauen(ziel_ordner=None, projekt=None, python: str = "", dock: bool = True,
              ausfuehren=None, schreibtisch=None) -> dict:
    """Baut Jarvis.app. Gibt zurück, wo sie liegt und ob Symbol und Dock geklappt haben."""
    projekt = Path(projekt or config.BASIS).resolve()
    if not (projekt / "jarvis.py").exists():
        return {"ok": False, "fehler": "In %s liegt kein jarvis.py." % projekt}
    if not python:
        umgebung = projekt / ".venv" / "bin" / "python"
        python = str(umgebung) if umgebung.exists() else (shutil.which("python3") or "python3")
    ziel_ordner = Path(ziel_ordner) if ziel_ordner else app_ordner()
    app = ziel_ordner / APP_NAME
    inhalt = app / "Contents"
    try:
        if app.exists():
            shutil.rmtree(app)
        (inhalt / "MacOS").mkdir(parents=True)
        (inhalt / "Resources").mkdir(parents=True)
        with open(inhalt / "Info.plist", "wb") as datei:
            plistlib.dump(info_plist(), datei)
        programm = inhalt / "MacOS" / "Jarvis"
        programm.write_text(startskript(projekt, python), encoding="utf-8")
        programm.chmod(0o755)
    except OSError as fehler:
        return {"ok": False, "fehler": "Die App ließ sich nicht anlegen: %s" % fehler}

    fertig = projekt / "assets" / "Jarvis.icns"
    if fertig.exists():
        try:
            shutil.copyfile(fertig, inhalt / "Resources" / "Jarvis.icns")
            symbol = True
        except OSError:
            symbol = False
    else:
        symbol = symbol_bauen(projekt / "assets" / "jarvis_symbol.png",
                              inhalt / "Resources" / "Jarvis.icns", ausfuehren)
    im_dock = ins_dock(app, ausfuehren) if dock else False
    # Auf dem Schreibtisch: dieselbe App, statt der alten Terminal-Verknüpfung.
    schreibtisch = Path(schreibtisch) if schreibtisch else Path.home() / "Desktop"
    if schreibtisch.is_dir() and ziel_ordner != schreibtisch:
        for alt in (schreibtisch / "Jarvis.command",):
            if alt.is_symlink():
                try:
                    alt.unlink()
                except OSError:
                    pass
        verweis = schreibtisch / APP_NAME
        try:
            if verweis.is_symlink() or not verweis.exists():
                if verweis.is_symlink():
                    verweis.unlink()
                verweis.symlink_to(app)
        except OSError:
            pass
    return {"ok": True, "app": str(app), "symbol": symbol, "dock": im_dock,
            "text": "Jarvis ist jetzt ein Programm: %s%s." % (
                app, " - und liegt im Dock" if im_dock else "")}



def download_app_bauen(ziel_ordner, symbol_icns=None) -> dict:
    """Baut die Jarvis.app zum Herunterladen: installiert beim ersten Start, startet danach."""
    app = Path(ziel_ordner) / APP_NAME
    inhalt = app / "Contents"
    if app.exists():
        shutil.rmtree(app)
    (inhalt / "MacOS").mkdir(parents=True)
    (inhalt / "Resources").mkdir(parents=True)
    with open(inhalt / "Info.plist", "wb") as datei:
        plistlib.dump(info_plist(), datei)
    kopf = DOWNLOAD_KOPF.replace("__INSTALL_URL__", INSTALL_URL)
    rumpf = STARTSKRIPT.split("\n", 1)[1]      # ohne die erste Zeile (#!/bin/bash)
    rumpf = (rumpf.replace("PROJEKT=__PROJEKT__", 'PROJEKT="$ZIEL"')
             .replace("PYTHON=__PYTHON__", 'PYTHON="$ZIEL/.venv/bin/python"')
             .replace("__PORT__", str(WEB_PORT)))
    programm = inhalt / "MacOS" / "Jarvis"
    programm.write_text(kopf + rumpf, encoding="utf-8")
    programm.chmod(0o755)
    if symbol_icns and Path(symbol_icns).exists():
        shutil.copyfile(symbol_icns, inhalt / "Resources" / "Jarvis.icns")
    return {"ok": True, "app": str(app)}


def download_zip_bauen(ziel_zip, symbol_icns=None) -> dict:
    """Packt die Download-App in ein ZIP - mit Ausführungsrecht, damit sie startet."""
    arbeit = Path(tempfile.mkdtemp(prefix="jarvis_download_"))
    try:
        app = Path(download_app_bauen(arbeit, symbol_icns)["app"])
        with zipfile.ZipFile(ziel_zip, "w", zipfile.ZIP_DEFLATED) as archiv:
            for pfad in [app] + sorted(app.rglob("*")):
                name = str(pfad.relative_to(arbeit)) + ("/" if pfad.is_dir() else "")
                info = zipfile.ZipInfo(name, date_time=(2026, 10, 6, 12, 0, 0))
                info.create_system = 3  # Unix: die Rechte stehen im Archiv
                modus = 0o40755 if pfad.is_dir() else (0o100755 if os.access(pfad, os.X_OK) else 0o100644)
                info.external_attr = (modus << 16) | (0x10 if pfad.is_dir() else 0)
                info.compress_type = zipfile.ZIP_DEFLATED
                archiv.writestr(info, b"" if pfad.is_dir() else pfad.read_bytes())
        return {"ok": True, "zip": str(ziel_zip)}
    finally:
        shutil.rmtree(arbeit, ignore_errors=True)
