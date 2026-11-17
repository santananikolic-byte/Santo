# -*- coding: utf-8 -*-
"""Eigenes Gehirn einrichten - JARVIS unabhängig machen.

    ./jarvis.sh gehirn eigen [modell]   Ollama finden oder laden, starten, das passende Modell holen, umstellen
    ./jarvis.sh gehirn claude           zurück auf Claude (über das Abo)
    ./jarvis.sh gehirn                  zeigen, womit JARVIS gerade denkt

"Eigen" heißt: Das Modell läuft auf diesem Mac (über Ollama), nichts geht an eine fremde Firma, es kostet nichts und
hat kein Limit. Dafür ist ein Modell, das auf einen iMac passt, deutlich schwächer als Claude.

Welches Modell: nach dem Arbeitsspeicher des Macs. Die Größen stammen aus der Modellbibliothek von Ollama
(ollama.com/library/gemma3, geprüft am 16.11.2026); gemma3 versteht Deutsch und Bilder (Bildschirmfoto).
"""

import json
import os
import platform
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request

OLLAMA_ZIP = "https://ollama.com/download/Ollama-darwin.zip"
APP_PROGRAMM = "Ollama.app/Contents/Resources/ollama"
ORTE = ("/Applications/" + APP_PROGRAMM, "~/Applications/" + APP_PROGRAMM, "/usr/local/bin/ollama",
        "/opt/homebrew/bin/ollama")
# (Arbeitsspeicher unter … GB, Modell, Größe des Downloads in GB, Kontextfenster)
MODELLE = ((12, "gemma3:4b", 3.4, 8192), (10 ** 6, "gemma3:12b", 8.2, 16384))
RESERVE_GB = 3  # so viel Platz soll auf der Festplatte nach dem Laden mindestens frei bleiben


class GehirnFehler(Exception):
    """Etwas bei der Einrichtung hat nicht geklappt - der Text sagt, was zu tun ist."""


def arbeitsspeicher_gb():
    """Arbeitsspeicher dieses Rechners in GB (0, wenn nicht feststellbar)."""
    try:
        if platform.system() == "Darwin":
            roh = subprocess.run(["sysctl", "-n", "hw.memsize"], capture_output=True, text=True, timeout=5).stdout  # noqa: S603
            return int(roh.strip()) / 2 ** 30
        return os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES") / 2 ** 30
    except (OSError, ValueError, subprocess.SubprocessError):
        return 0


def modell_fuer(gb):
    """(Modell, Größe in GB, Kontextfenster) passend zum Arbeitsspeicher. Unbekannt (0) gilt als klein."""
    for grenze, modell, groesse, kontext in MODELLE:
        if gb < grenze:
            return modell, groesse, kontext
    return MODELLE[-1][1:]


def kontext_fuer(modell, gb):
    """Kontextfenster für ein selbst gewähltes Modell: groß nur mit genug Arbeitsspeicher."""
    return 16384 if gb >= 12 else 8192


def ollama_finden():
    """Pfad des Programms ``ollama`` oder None."""
    kandidaten = [os.environ.get("JARVIS_OLLAMA"), shutil.which("ollama")] + [os.path.expanduser(o) for o in ORTE]
    for pfad in kandidaten:
        if pfad and os.path.isfile(pfad) and os.access(pfad, os.X_OK):
            return pfad
    return None


def _holen(adresse, pfad, daten=None, timeout=5):
    """Anfrage an Ollama auf diesem Mac (nie über einen Proxy)."""
    rumpf = json.dumps(daten).encode("utf-8") if daten is not None else None
    anfrage = urllib.request.Request(adresse + pfad, data=rumpf, method="POST" if daten is not None else "GET",  # noqa: S310
                                     headers={"Content-Type": "application/json"} if daten is not None else {})
    oeffner = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with oeffner.open(anfrage, timeout=timeout) as antwort:  # noqa: S310 - Adresse ist auf localhost begrenzt
        return json.loads(antwort.read().decode("utf-8"))


def laeuft(adresse):
    try:
        _holen(adresse, "/api/tags", timeout=3)
        return True
    except (urllib.error.URLError, OSError, ValueError):
        return False


def geladen(adresse, modell):
    """Ist das Modell schon auf dem Mac?"""
    try:
        namen = [m.get("name", "") for m in _holen(adresse, "/api/tags").get("models") or []]
    except (urllib.error.URLError, OSError, ValueError):
        return False
    return any(n == modell or (":" not in modell and n.split(":")[0] == modell) for n in namen)


def starten(programm, adresse, log_datei, warten=40):
    """Ollama starten und warten, bis es antwortet. Gibt True zurück, wenn es läuft."""
    if laeuft(adresse):
        return True
    app = programm.split("/Contents/Resources/")[0] if "/Contents/Resources/" in programm else None
    if app and platform.system() == "Darwin":
        subprocess.run(["open", "-a", app, "--args", "hidden"], capture_output=True, timeout=20)  # noqa: S603
    else:
        os.makedirs(os.path.dirname(log_datei), exist_ok=True)
        with open(log_datei, "ab") as log:
            subprocess.Popen([programm, "serve"], stdout=log, stderr=log, stdin=subprocess.DEVNULL,  # noqa: S603
                             start_new_session=True)
    ende = time.time() + warten
    while time.time() < ende:
        if laeuft(adresse):
            return True
        time.sleep(0.5)
    return False


def installieren(sage):
    """Ollama für den Mac laden und nach /Applications (oder ~/Applications) legen - ohne Passwort.
    Gibt den Pfad des Programms zurück; wirft GehirnFehler."""
    if platform.system() != "Darwin":
        raise GehirnFehler("Automatisch laden kann JARVIS Ollama nur auf dem Mac. Anleitung: https://ollama.com/download")
    ziel = "/Applications" if os.access("/Applications", os.W_OK) else os.path.expanduser("~/Applications")
    os.makedirs(ziel, exist_ok=True)
    ordner = tempfile.mkdtemp(prefix="jarvis_ollama_")
    try:
        archiv = os.path.join(ordner, "Ollama-darwin.zip")
        sage("Lade Ollama (etwa 230 MB) …")
        lauf = subprocess.run(["curl", "--fail", "--location", "--progress-bar", "-o", archiv, OLLAMA_ZIP], timeout=1800)  # noqa: S603
        if lauf.returncode != 0:
            raise GehirnFehler("Das Laden von Ollama hat nicht geklappt. Läuft das Internet? Dann dieselbe Zeile nochmal.")
        if subprocess.run(["unzip", "-q", archiv, "-d", ordner], timeout=600).returncode != 0:  # noqa: S603
            raise GehirnFehler("Das Auspacken von Ollama hat nicht geklappt.")
        if os.path.isdir(os.path.join(ziel, "Ollama.app")):
            raise GehirnFehler("In %s liegt schon ein Ollama, das sich nicht starten ließ. Bitte Ollama einmal von Hand "
                               "öffnen (Programme → Ollama) und die Zeile wiederholen." % ziel)
        shutil.move(os.path.join(ordner, "Ollama.app"), ziel)
    except (OSError, subprocess.SubprocessError) as fehler:
        raise GehirnFehler("Ollama ließ sich nicht einrichten (%s)." % fehler) from None
    finally:
        shutil.rmtree(ordner, ignore_errors=True)
    return os.path.join(ziel, APP_PROGRAMM)


def probe(adresse, modell, kontext, timeout=300):
    """Eine kleine echte Frage an das Modell. Gibt (Antwort, Sekunden) zurück; wirft GehirnFehler."""
    start = time.time()
    try:
        daten = _holen(adresse, "/api/chat", {"model": modell, "stream": False, "keep_alive": "30m",
                                              "options": {"num_ctx": kontext},
                                              "messages": [{"role": "user", "content": "Sag in einem kurzen deutschen "
                                                                                       "Satz, dass du bereit bist."}]},
                       timeout=timeout)
    except (urllib.error.URLError, OSError, ValueError) as fehler:
        raise GehirnFehler("Das Modell hat auf die Probefrage nicht geantwortet (%s)." % fehler) from None
    antwort = ((daten.get("message") or {}).get("content") or "").strip() if isinstance(daten, dict) else ""
    if not antwort:
        raise GehirnFehler("Das Modell hat auf die Probefrage nichts geantwortet: %s" % str(daten)[:200])
    return " ".join(antwort.split())[:200], time.time() - start


def einrichten(k, modell=None, frage_ja=None, sage=print):
    """Der ganze Weg zum eigenen Gehirn. Gibt 0 zurück, wenn JARVIS danach unabhängig denken kann."""
    frage_ja = frage_ja or _frage_ja
    gb = arbeitsspeicher_gb()
    if modell:
        groesse, kontext = None, kontext_fuer(modell, gb)
    else:
        modell, groesse, kontext = modell_fuer(gb)
    sage("Eigenes Gehirn für JARVIS: Modell %s%s." % (modell, " (passend zu %d GB Arbeitsspeicher)" % round(gb) if gb else ""))
    sage("Es läuft dann auf diesem Mac: ohne Claude, ohne Abo, ohne Kosten - aber schwächer und langsamer als Claude.")
    try:
        programm = ollama_finden()
        if programm is None:
            sage("Dafür braucht es das freie Programm Ollama (ollama.com). Es ist noch nicht auf diesem Mac.")
            if not frage_ja("Soll ich Ollama jetzt laden und einrichten?"):
                sage("Abgebrochen. Nichts wurde geändert.")
                return 1
            programm = installieren(sage)
        sage("Ollama: %s" % programm)
        if not starten(programm, k.ollama_adresse, os.path.join(k.daten_ordner, "logs", "ollama.log")):
            raise GehirnFehler("Ollama ist nicht gestartet. Bitte einmal von Hand öffnen (Programme → Ollama) und die "
                               "Zeile wiederholen.")
        if geladen(k.ollama_adresse, modell):
            sage("Das Modell %s ist schon auf dem Mac." % modell)
        else:
            frei = shutil.disk_usage(os.path.expanduser("~")).free / 2 ** 30
            if groesse and frei < groesse + RESERVE_GB:
                raise GehirnFehler("Auf der Festplatte sind nur %.0f GB frei. Das Modell braucht %.1f GB und etwas Reserve. "
                                   "Bitte Platz schaffen und die Zeile wiederholen." % (frei, groesse))
            if not frage_ja("Das Modell %s wird jetzt geladen%s. Das dauert je nach Internet einige Minuten. Laden?"
                            % (modell, " (%.1f GB)" % groesse if groesse else "")):
                sage("Abgebrochen. Nichts wurde geändert.")
                return 1
            umgebung = dict(os.environ, OLLAMA_HOST=k.ollama_adresse)  # das Programm spricht mit genau diesem Ollama
            if subprocess.run([programm, "pull", modell], timeout=6 * 3600, env=umgebung).returncode != 0:  # noqa: S603
                raise GehirnFehler("Das Laden des Modells hat nicht geklappt. Läuft das Internet? Dann dieselbe Zeile "
                                   "nochmal - es macht dort weiter, wo es aufgehört hat.")
        sage("Probefrage an das Modell (das erste Mal dauert länger, weil es erst in den Speicher geladen wird) …")
        antwort, sekunden = probe(k.ollama_adresse, modell, kontext)
        sage("Antwort nach %.0f Sekunden: %s" % (sekunden, antwort))
    except GehirnFehler as fehler:
        sage("FEHLER: %s" % fehler)
        sage("JARVIS bleibt bei der bisherigen Einstellung (%s)." % ("eigenes Gehirn" if k.gehirn == "lokal" else "Claude"))
        return 1
    k.aktualisieren({"gehirn": "lokal", "lokales_modell": modell, "lokal_kontext": kontext})
    sage("Fertig: JARVIS denkt jetzt mit dem eigenen Modell %s - unabhängig von Claude." % modell)
    sage("Wirksam nach einem Neustart von JARVIS. Zurück zu Claude: ./jarvis.sh gehirn claude")
    return 0


def auf_claude(k, sage=print):
    k.aktualisieren({"gehirn": "claude"})
    sage("JARVIS denkt wieder über Claude (dein Abo). Wirksam nach einem Neustart von JARVIS.")
    sage("Zurück zum eigenen Gehirn: ./jarvis.sh gehirn eigen")
    return 0


def zeigen(k, sage=print):
    if k.gehirn == "lokal":
        bereit = laeuft(k.ollama_adresse) and geladen(k.ollama_adresse, k.lokales_modell)
        sage("JARVIS denkt mit dem eigenen Modell %s auf diesem Mac - unabhängig von Claude. %s"
             % (k.lokales_modell or "(noch keins gewählt)", "Bereit." if bereit else "NICHT bereit: ./jarvis.sh gehirn eigen"))
    else:
        sage("JARVIS denkt über Claude (dein Abo). Unabhängig machen: ./jarvis.sh gehirn eigen")
    return 0


def _frage_ja(text):
    """Rückfrage mit j/n. JARVIS_JA=1 beantwortet alles mit Ja (für die Einrichtung in einem Rutsch und für Tests)."""
    if os.environ.get("JARVIS_JA") == "1":
        return True
    try:
        return input("  %s [j/n] " % text).strip().lower() in ("j", "ja", "y", "yes")
    except EOFError:
        return False


def main(argumente, k):
    wahl = argumente[0] if argumente else ""
    if wahl == "eigen":
        return einrichten(k, argumente[1] if len(argumente) > 1 else None)
    if wahl == "claude":
        return auf_claude(k)
    if wahl in ("", "status"):
        return zeigen(k)
    print("So: ./jarvis.sh gehirn eigen [modell]  |  ./jarvis.sh gehirn claude  |  ./jarvis.sh gehirn", file=sys.stderr)
    return 2
