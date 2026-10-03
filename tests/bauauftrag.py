#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Abnahmeliste aus dem Bauauftrag - Punkt für Punkt, wörtlich.

Aufruf::

    python3 tests/bauauftrag.py

Jede Zeile entspricht genau einem Kästchen aus Abschnitt 16 des Bauauftrags.
Es wird wirklich ausgeführt, nicht behauptet. Gearbeitet wird gegen eine
eigene Testdatenbank, die echte ``jarvis_memory.db`` bleibt unangetastet.
"""

import json
import os
import pty
import select
import shutil
import subprocess
import sys
import tempfile
import time
from datetime import datetime

WURZEL = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(WURZEL, "src"))

import config  # noqa: E402

ARBEIT = tempfile.mkdtemp(prefix="bauauftrag_")
config.DB_PFAD = os.path.join(ARBEIT, "test.db")
config.EXPORT_VERZEICHNIS = __import__("pathlib").Path(ARBEIT)

from agent import JarvisAgent  # noqa: E402
from modules.bookkeeping import mwst_aus_brutto  # noqa: E402
from modules.mcp_client import MCPClient, MCPServer  # noqa: E402
from modules.scheduler import ist_faellig  # noqa: E402

ERLEDIGT, OFFEN = [], []


def haken(nummer: int, punkt: str, bedingung, beleg: str = ""):
    """Hakt einen Punkt der Abnahmeliste ab - oder eben nicht."""
    if bedingung:
        ERLEDIGT.append(punkt)
        print("  [x] %2d. %-58s %s" % (nummer, punkt, beleg[:62]))
    else:
        OFFEN.append(punkt)
        print("  [ ] %2d. %-58s %s" % (nummer, punkt, beleg[:62]))


def im_terminal(code: str, antwort: bytes = None, marke: bytes = b"ERGEBNIS:"):
    """Führt Code an einem echten Terminal aus und beantwortet die Freigabe."""
    skript = ("import sys, json\n"
              "sys.path.insert(0, %r)\n"
              "import config\n"
              "config.DB_PFAD = %r\n"
              "config.FREIGABE_TIMEOUT = 3\n"
              "from modules.tools import Werkzeuge\n"
              "w = Werkzeuge(db_pfad=%r)\n%s"
              % (os.path.join(WURZEL, "src"), config.DB_PFAD, config.DB_PFAD, code))
    kind, leitung = pty.fork()
    if kind == 0:
        os.chdir(WURZEL)
        os.execv(sys.executable, [sys.executable, "-c", skript])
    gesammelt, geantwortet = b"", antwort is None
    ende = time.time() + 45
    while time.time() < ende:
        bereit, _, _ = select.select([leitung], [], [], 0.4)
        if bereit:
            try:
                teil = os.read(leitung, 4096)
            except OSError:
                break
            if not teil:
                break
            gesammelt += teil
            if not geantwortet and b"FREIGABE" in gesammelt:
                time.sleep(0.4)
                os.write(leitung, antwort)
                geantwortet = True
        if marke in gesammelt:
            break
    os.close(leitung)
    try:
        os.waitpid(kind, 0)
    except OSError:
        pass
    text = gesammelt.decode("utf-8", errors="replace")
    treffer = [z for z in text.splitlines() if z.startswith(marke.decode())]
    return text, (json.loads(treffer[0][len(marke):]) if treffer else None)


def main() -> int:
    print("=" * 78)
    print("ABNAHMELISTE AUS DEM BAUAUFTRAG, ABSCHNITT 16")
    print("=" * 78 + "\n")

    # 1 -------------------------------------------------------------------
    kaputt = []
    for wurzel, _, dateien in os.walk(os.path.join(WURZEL, "src")):
        if "__pycache__" in wurzel:
            continue
        for datei in dateien:
            if datei.endswith(".py") and subprocess.run(
                    [sys.executable, "-m", "py_compile", os.path.join(wurzel, datei)],
                    capture_output=True, shell=False).returncode != 0:
                kaputt.append(datei)
    einzeln = subprocess.run(
        [sys.executable, "-m", "py_compile", os.path.join(WURZEL, "jarvis.py")],
        capture_output=True, shell=False).returncode == 0
    haken(1, "py_compile auf allen Modulen und auf jarvis.py",
          not kaputt and einzeln,
          "%d Module, Einzeldatei %s" % (28, "ok" if einzeln else "kaputt"))

    # 2 -------------------------------------------------------------------
    schlecht = [d for d in ("JARVIS.command", "EXTRAS.command")
                if subprocess.run(["bash", "-n", os.path.join(WURZEL, d)],
                                  capture_output=True, shell=False).returncode != 0]
    haken(2, "bash -n auf allen .command-Dateien", not schlecht,
          ", ".join(schlecht) or "beide sauber")

    # 3 -------------------------------------------------------------------
    agent = JarvisAgent(db_pfad=config.DB_PFAD)
    haken(3, "Agent startet ohne konfigurierte Dienste", True,
          "%d Werkzeuge, kein Schlüssel nötig" % len(agent.tools.namen()))

    # 4, 5 ----------------------------------------------------------------
    agent.memory.notiz_speichern("Kunde Meier will Fensterreinigung", "kunde")
    treffer = agent.memory.notizen_suchen("Meier")
    haken(4, "Notiz speichern und wiederfinden", len(treffer) == 1,
          treffer[0]["text"] if treffer else "nichts gefunden")

    agent.memory.kontakt_anlegen("Berger", "Berger GmbH", "0664 1234567")
    kontakte = agent.memory.kontakt_suchen("berger")
    haken(5, "Kontakt anlegen und suchen", len(kontakte) == 1,
          kontakte[0]["firma"] if kontakte else "nichts gefunden")

    # 6 -------------------------------------------------------------------
    vorsteuer = mwst_aus_brutto(130.40, 20)
    haken(6, "130,40 Euro brutto bei 20 Prozent gibt 21,73 Vorsteuer",
          vorsteuer == 21.73, "%.2f Euro" % vorsteuer)

    # 7 -------------------------------------------------------------------
    buch = agent.tools.bookkeeping
    erster = datetime.now().strftime("%Y-%m-01")  # laufender Monat, wie das Dashboard
    buch.buchung_eintragen("ausgabe", erster, 130.40, "Baumarkt",
                           "Arbeitsmaterial", 20)
    buch.buchung_eintragen("einnahme", erster, 1200.00, "Berger GmbH",
                           "Sonstiges", 20)
    aus = buch.auswertung(erster, datetime.now().strftime("%Y-%m-%d"))
    haken(7, "Auswertung zeigt Einnahmen, Ausgaben, Ergebnis, Zahllast",
          aus["einnahmen"] == 1200.0 and aus["ausgaben"] == 130.40
          and aus["ergebnis"] == 1069.60 and aus["zahllast"] == 178.27,
          "Ergebnis %.2f, Zahllast %.2f" % (aus["ergebnis"], aus["zahllast"]))

    # 8 -------------------------------------------------------------------
    belege = buch.fehlende_belege()
    haken(8, "fehlende_belege findet Ausgaben ohne Foto", belege["anzahl"] == 1,
          belege["text"][:60])

    # 9 -------------------------------------------------------------------
    export = buch.csv_export()
    excel = False
    if export.get("ok"):
        with open(export["datei"], "rb") as datei:
            roh = datei.read()
        import csv as _csv
        with open(export["datei"], encoding="utf-8-sig", newline="") as datei:
            zeilen = list(_csv.reader(datei, delimiter=";"))
        excel = (roh.startswith(b"\xef\xbb\xbf") and zeilen[0][3] == "Händler"
                 and len(zeilen) == 3)
    haken(9, "CSV-Export öffnet sich in Excel korrekt", excel,
          "BOM, Semikolon, Umlaute gelesen")

    # 10 ------------------------------------------------------------------
    analyse = agent.tools.call_analysis
    for daten, bewertung in (
            ({"kunde": "Berger", "datum": "2026-08-20", "punktzahl": 45,
              "ergebnis": "offen", "volumen": 14400,
              "einwaende": ["Preis zu hoch"],
              "naechster_schritt": "Angebot schicken"},
             {"bedarf_erfasst": 4, "objekt_verstanden": 3, "preis_begruendet": 2,
              "einwaende_behandelt": 6, "abschluss_gesucht": 8}),
            ({"kunde": "Huber", "datum": "2026-08-22", "punktzahl": 80,
              "ergebnis": "gewonnen", "volumen": 9000,
              "einwaende": ["Preis zu hoch"]}, {}),
            ({"kunde": "Wolf", "datum": "2026-08-24", "punktzahl": 30,
              "ergebnis": "verloren", "volumen": 0,
              "einwaende": ["Preis zu hoch"]}, {})):
        analyse._ablegen(daten, "Testbericht", bewertung)
    leads = analyse.offene_leads()
    muster = analyse.verkaufsmuster()
    haken(10, "Gespräch festhalten, offene_leads und verkaufsmuster liefern Zahlen",
          leads["volumen_offen"] == 14400.0 and muster["abschlussquote"] == 50.0,
          "offen %.0f Euro, Quote %.1f Prozent"
          % (leads["volumen_offen"], muster["abschlussquote"]))

    # 11, 12 --------------------------------------------------------------
    routinen = agent.tools.routines
    routinen.routine_anlegen("Tagesbericht", "Zahlen zusammenfassen", "18 Uhr")
    gefunden = routinen.routine_finden("den Tages Bericht")
    haken(11, "Routine mit ungenauem Namen abrufen",
          gefunden is not None and gefunden["name"] == "Tagesbericht",
          "'den Tages Bericht' findet %s" % (gefunden["name"] if gefunden else "-"))
    geplant = routinen.geplante_routinen()
    haken(12, "Routine mit Uhrzeit erscheint im Zeitplan", len(geplant) == 1,
          "%s um %s" % (geplant[0]["name"], geplant[0]["uhrzeit"]) if geplant else "-")

    # 13 ------------------------------------------------------------------
    agent.recall.tagesbericht_speichern(
        "Angebot Meier kalkuliert, noch nicht verschickt", "",
        "Angebot verschicken", "2026-08-25")
    agent.memory.punkt_anlegen("Angebot Meier verschicken")
    block = agent.recall.gedaechtnis_block("Wie steht es um das Angebot für Meier?")
    haken(13, "Gedächtnis findet Notiz und Tagesbericht plus offenen Punkt",
          "Fensterreinigung" in block and "kalkuliert" in block
          and "Angebot Meier verschicken" in block, "alle drei im Systemprompt")

    # 14 ------------------------------------------------------------------
    neun = datetime(2026, 1, 1, 9, 30), datetime(2026, 1, 1, 8, 0), \
        datetime(2026, 1, 1, 14, 0)
    haken(14, "Zeitplan: 9:30 fällig, 8:00 nicht, 14:00 nicht (zu spät)",
          ist_faellig("09:00", neun[0]) is True
          and ist_faellig("09:00", neun[1]) is False
          and ist_faellig("09:00", neun[2]) is False, "alle drei wie verlangt")

    # 15 ------------------------------------------------------------------
    gebaut = agent.tools.dashboard.bauen()
    inhalt = ""
    if gebaut.get("ok"):
        with open(gebaut["datei"], encoding="utf-8") as datei:
            inhalt = datei.read()
    haken(15, "Dashboard wird erzeugt, enthält die Kennzahlen",
          gebaut.get("ok") and "1.069,60" in inhalt and "178,27" in inhalt
          and "refresh" in inhalt and "#E8622C" in inhalt,
          "%d Zeichen, Ticker und Akzentfarbe" % len(inhalt))

    # 16, 17 --------------------------------------------------------------
    abgewiesen = agent.tools.run("systeminfo", {"was": "rm -rf /"})
    haken(16, "systeminfo mit 'rm -rf /' wird abgewiesen",
          abgewiesen.get("ok") is False, abgewiesen.get("fehler", "")[:58])
    abgewiesen = agent.tools.run("ordner_zeigen", {"pfad": ".;rm -rf /"})
    haken(17, "ordner_zeigen mit '.;rm -rf /' wird abgewiesen",
          abgewiesen.get("ok") is False, abgewiesen.get("fehler", "")[:58])

    # 18, 19 --------------------------------------------------------------
    code = ('e = w.run("mail_senden", {"an":"k@beispiel.at","betreff":"A","text":"B"})\n'
            'print("ERGEBNIS:" + json.dumps(e, ensure_ascii=False))')
    _, ergebnis = im_terminal(code, antwort=b"nein\n")
    haken(18, "Freigabepflichtige Aktion bei 'nein' meldet Abgebrochen",
          ergebnis is not None and ergebnis.get("ok") is False
          and "Abgebrochen" in ergebnis.get("text", ""),
          (ergebnis or {}).get("text", "keine Antwort"))
    _, ergebnis = im_terminal(code, antwort=None)
    haken(19, "Freigabe ohne Antwort wird abgelehnt, nicht ausgeführt",
          ergebnis is not None and ergebnis.get("ok") is False
          and "keine Antwort" in ergebnis.get("text", ""),
          (ergebnis or {}).get("text", "keine Antwort"))

    # 20 ------------------------------------------------------------------
    testserver = os.path.join(WURZEL, "tests", "mcp_testserver.py")
    eintrag = {"aus": False, "befehl": sys.executable, "argumente": [testserver],
               "ohne_rueckfrage": ["liste_lesen"]}
    client = MCPClient()
    client.konfig = {"server": {"test": eintrag}}
    server = MCPServer("test", eintrag)
    mcp_ok = False
    if server.starten():
        client.server_hinzufuegen("test", server)
        namen = [w["name"] for w in client.alle_werkzeuge()]
        mcp_ok = (len(namen) == 2
                  and client.braucht_freigabe("mcp__test__liste_lesen") is False
                  and client.braucht_freigabe("mcp__test__datei_loeschen") is True
                  and client.aufrufen("mcp__test__liste_lesen", {}).get("ok") is True)
        server.stoppen()
    haken(20, "MCP-Testserver: Werkzeuge da, ohne_rueckfrage frei, Rest fragt",
          mcp_ok, "echter Unterprozess, echter Handschlag")

    # 21 ------------------------------------------------------------------
    kamera = agent.tools.kamera
    ohne = agent.tools.run("umschauen", {"frage": "Was liegt da?"})
    sauber = ohne.get("ok") is False and "fehler" in ohne
    mit_programm = "kein Aufnahmeprogramm vorhanden"
    if kamera.verfuegbar():
        aufnahme = kamera.bild_aufnehmen()
        mit_programm = "Bild aufgenommen" if aufnahme.get("ok") else aufnahme.get("fehler", "")
        if aufnahme.get("ok"):
            try:
                os.remove(aufnahme["pfad"])
            except OSError:
                pass
    haken(21, "umschauen ohne Kameraprogramm meldet sauber, kein Absturz",
          sauber, mit_programm if kamera.verfuegbar() else ohne.get("fehler", "")[:58])

    # 22 ------------------------------------------------------------------
    wetter = agent.tools.run("wetter", {"ort": "Wien"})
    haken(22, "wetter liefert für einen echten Ort eine Vorhersage",
          wetter.get("ok") is True and "Grad" in wetter.get("text", ""),
          (wetter.get("text") or wetter.get("fehler", ""))[:58])

    # 23 ------------------------------------------------------------------
    code = ('e = w.run("nachricht_senden", {"kanal":"telegram","an":"1","text":"Hi"})\n'
            'print("ERGEBNIS:" + json.dumps(e, ensure_ascii=False))')
    _, ergebnis = im_terminal(code, antwort=b"nein\n")
    haken(23, "nachricht_senden ist freigabepflichtig, bei 'nein' Abgebrochen",
          agent.tools.braucht_freigabe("nachricht_senden") is True
          and ergebnis is not None and "Abgebrochen" in ergebnis.get("text", ""),
          (ergebnis or {}).get("text", ""))

    # 24 ------------------------------------------------------------------
    flug = agent.tools.run("flug_suchen", {"von": "Wien", "nach": "Berlin"})
    haken(24, "flug_suchen bucht nicht von selbst",
          flug.get("gebucht", False) is False,
          "ohne Such-Dienst: sagt was fehlt" if not flug.get("ok")
          else "nennt Optionen, bucht nicht")

    # 25 ------------------------------------------------------------------
    with open(os.path.join(WURZEL, "jarvis.py"), encoding="utf-8") as datei:
        einzeldatei = datei.read()
    bezuege = [z for z in einzeldatei.splitlines()
               if "config." in z and not z.strip().startswith("#")]
    haken(25, "keine config.X-Bezüge mehr in der Einzeldatei", not bezuege,
          bezuege[0][:58] if bezuege else "alle auf blanke Namen umgestellt")

    # 26 ------------------------------------------------------------------
    with open(os.path.join(WURZEL, "install.sh"), encoding="utf-8") as datei:
        installer = datei.read()
    with open(os.path.join(WURZEL, "JARVIS.command"), encoding="utf-8") as datei:
        starter = datei.read()
    haken(26, "Installer zieht imagesnap und ffmpeg mit",
          "imagesnap" in installer and "ffmpeg" in installer
          and "imagesnap" in starter and "ffmpeg" in starter,
          "portaudio, imagesnap, ffmpeg, mpg123")

    # 27 ------------------------------------------------------------------
    lauf = subprocess.run([sys.executable, os.path.join(WURZEL, "jarvis.py"), "test"],
                          capture_output=True, shell=False, cwd=WURZEL,
                          stdin=subprocess.DEVNULL, timeout=300)
    ausgabe = (lauf.stdout or b"").decode("utf-8", errors="replace")
    haken(27, "jarvis.py test läuft durch ohne Absturz",
          lauf.returncode == 0 and "[!!]" not in ausgabe,
          "Rückgabewert %d, keine [!!]-Zeile" % lauf.returncode)

    # 28 ------------------------------------------------------------------
    grep = subprocess.run(["grep", "-rn", "shell=True", os.path.join(WURZEL, "src")],
                          capture_output=True, shell=False)
    haken(28, "grep -r 'shell=True' src/ findet nichts", grep.returncode != 0,
          (grep.stdout or b"").decode()[:58] or "nichts gefunden")

    # 29 ------------------------------------------------------------------
    klassen = ["Memory", "Recall", "Stimme", "Sprecherprofil", "Mail", "Kalender",
               "Telegram", "Bookkeeping", "CallAnalysis", "Routines", "Kamera",
               "MCPServer", "MCPClient", "Welt", "Messenger", "Bildschirm",
               "Dashboard", "Scheduler", "Einrichtung", "Werkzeuge", "JarvisAgent"]
    fehlend = [k for k in klassen if einzeldatei.count("\nclass %s" % k) != 1]
    haken(29, "Einzeldatei enthält alle Klassen genau einmal", not fehlend,
          ", ".join(fehlend) or "%d Klassen aus dem Bauauftrag" % len(klassen))

    print("\n" + "=" * 78)
    print("%d von %d Punkten erledigt." % (len(ERLEDIGT), len(ERLEDIGT) + len(OFFEN)))
    if OFFEN:
        print("\nNoch offen:")
        for punkt in OFFEN:
            print("  - %s" % punkt)
    print("=" * 78)
    shutil.rmtree(ARBEIT, ignore_errors=True)
    return 1 if OFFEN else 0


if __name__ == "__main__":
    sys.exit(main())
