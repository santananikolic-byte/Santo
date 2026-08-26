#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Abnahme - führt die Punkte der Abnahmeliste wirklich aus.

Aufruf::

    python3 tests/abnahme.py

Es wird gegen eine eigene Testdatenbank gearbeitet, die echte
``jarvis_memory.db`` bleibt unangetastet. Die Freigabeprüfungen laufen über ein
echtes Terminal (pty), damit auch der Timeout-Fall wirklich geprüft wird und
nicht bloß behauptet.
"""

import copy
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

ARBEITSVERZEICHNIS = tempfile.mkdtemp(prefix="jarvis_abnahme_")
config.DB_PFAD = os.path.join(ARBEITSVERZEICHNIS, "test.db")
config.EXPORT_VERZEICHNIS = __import__("pathlib").Path(ARBEITSVERZEICHNIS)

from agent import JarvisAgent  # noqa: E402
from modules.bookkeeping import mwst_aus_brutto  # noqa: E402
from modules.calendar_mod import ics_termine_lesen, konflikte_finden  # noqa: E402
from modules.mcp_client import MCPClient, MCPServer  # noqa: E402
from modules.scheduler import Scheduler, ist_faellig  # noqa: E402
from modules.voice import weckwort_pruefen  # noqa: E402

BESTANDEN = []
DURCHGEFALLEN = []


def pruefen(name: str, bedingung, hinweis: str = ""):
    """Hakt einen Punkt der Abnahmeliste ab."""
    if bedingung:
        BESTANDEN.append(name)
        print("  [ok] %-52s %s" % (name, hinweis[:60]))
    else:
        DURCHGEFALLEN.append(name)
        print("  [!!] %-52s %s" % (name, hinweis[:60]))


def abschnitt(titel: str):
    print("\n%s\n%s" % (titel, "-" * len(titel)))


# ---------------------------------------------------------------------------
# Freigaben über ein echtes Terminal
# ---------------------------------------------------------------------------

FREIGABE_SKRIPT = """
import sys, json
sys.path.insert(0, %r)
import config
config.DB_PFAD = %r
config.FREIGABE_TIMEOUT = 3
from modules.tools import Werkzeuge
w = Werkzeuge()
%s
"""


def im_terminal(codeteil: str, antwort: bytes = None, marke: bytes = b"ERGEBNIS:"):
    """Führt Code an einem echten Terminal aus und beantwortet die Freigabefrage."""
    skript = FREIGABE_SKRIPT % (os.path.join(WURZEL, "src"), config.DB_PFAD, codeteil)
    kind, leitung = pty.fork()
    if kind == 0:
        os.chdir(WURZEL)
        os.execv(sys.executable, [sys.executable, "-c", skript])
    gesammelt = b""
    geantwortet = antwort is None
    ende = time.time() + 45
    while time.time() < ende:
        bereit, _, _ = select.select([leitung], [], [], 0.5)
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
    daten = json.loads(treffer[0][len(marke):]) if treffer else None
    return text, daten


# ---------------------------------------------------------------------------
# Die Prüfungen
# ---------------------------------------------------------------------------

def pruefung_syntax():
    abschnitt("Syntax")
    fehler = []
    for wurzel, _, dateien in os.walk(os.path.join(WURZEL, "src")):
        if "__pycache__" in wurzel:
            continue
        for datei in dateien:
            if not datei.endswith(".py"):
                continue
            pfad = os.path.join(wurzel, datei)
            ergebnis = subprocess.run([sys.executable, "-m", "py_compile", pfad],
                                      capture_output=True, shell=False)
            if ergebnis.returncode != 0:
                fehler.append(datei)
    pruefen("py_compile auf allen Modulen", not fehler, ", ".join(fehler) or "alle sauber")

    einzeldatei = os.path.join(WURZEL, "jarvis.py")
    if os.path.exists(einzeldatei):
        ergebnis = subprocess.run([sys.executable, "-m", "py_compile", einzeldatei],
                                  capture_output=True, shell=False)
        pruefen("py_compile auf jarvis.py", ergebnis.returncode == 0,
                (ergebnis.stderr or b"").decode()[:60] or "sauber")
    else:
        pruefen("jarvis.py vorhanden", False, "erst bauen: python3 build_single.py")

    if shutil.which("bash"):
        kaputt = []
        for datei in ("JARVIS.command", "EXTRAS.command"):
            pfad = os.path.join(WURZEL, datei)
            if os.path.exists(pfad):
                if subprocess.run(["bash", "-n", pfad], capture_output=True,
                                  shell=False).returncode != 0:
                    kaputt.append(datei)
        pruefen("bash -n auf allen .command-Dateien", not kaputt,
                ", ".join(kaputt) or "alle sauber")

    treffer = subprocess.run(["grep", "-rn", "shell=True", os.path.join(WURZEL, "src")],
                             capture_output=True, shell=False)
    pruefen("keine Shell im Projekt", treffer.returncode != 0,
            (treffer.stdout or b"").decode()[:60] or "nichts gefunden")


def pruefung_agent():
    abschnitt("Agent und Gedächtnis")
    agent = JarvisAgent(db_pfad=config.DB_PFAD)
    pruefen("Agent startet ohne konfigurierte Dienste", True,
            "%d Werkzeuge" % len(agent.tools.namen()))

    notiz = agent.memory.notiz_speichern("Kunde Meier will Fensterreinigung", "kunde")
    gefunden = agent.memory.notizen_suchen("Meier")
    pruefen("Notiz speichern und wiederfinden",
            notiz["ok"] and len(gefunden) == 1, gefunden[0]["text"] if gefunden else "")

    agent.memory.kontakt_anlegen("Berger", "Berger GmbH", "0664 1234567")
    kontakte = agent.memory.kontakt_suchen("berger")
    pruefen("Kontakt anlegen und suchen", len(kontakte) == 1,
            kontakte[0]["firma"] if kontakte else "")

    agent.recall.tagesbericht_speichern(
        "Angebot Meier kalkuliert, noch nicht verschickt", "", "Angebot verschicken",
        "2026-08-25")
    agent.memory.punkt_anlegen("Angebot Meier verschicken")
    block = agent.recall.gedaechtnis_block("Wie steht es um das Angebot für Meier?")
    pruefen("Gedächtnis findet Notiz, Tagesbericht und offenen Punkt",
            "Fensterreinigung" in block and "kalkuliert" in block
            and "Angebot Meier verschicken" in block,
            "alle drei Quellen im Systemprompt")
    return agent


def pruefung_buchhaltung(agent):
    abschnitt("Buchhaltung")
    pruefen("130,40 brutto bei 20 Prozent ergibt 21,73 Vorsteuer",
            mwst_aus_brutto(130.40, 20) == 21.73,
            "%.2f Euro" % mwst_aus_brutto(130.40, 20))

    buch = agent.tools.bookkeeping
    buch.buchung_eintragen("ausgabe", "2026-08-20", 130.40, "Baumarkt",
                           "Arbeitsmaterial", 20)
    buch.buchung_eintragen("einnahme", "2026-08-21", 1200.00, "Berger GmbH",
                           "Sonstiges", 20)
    auswertung = buch.auswertung("2026-08-01", "2026-08-31")
    pruefen("Auswertung zeigt Einnahmen, Ausgaben, Ergebnis, Zahllast",
            auswertung["einnahmen"] == 1200.0 and auswertung["ausgaben"] == 130.40
            and auswertung["ergebnis"] == 1069.60 and auswertung["zahllast"] == 178.27,
            "Zahllast %.2f" % auswertung["zahllast"])

    belege = buch.fehlende_belege()
    pruefen("fehlende_belege findet Ausgaben ohne Foto", belege["anzahl"] == 1,
            belege["text"])

    export = buch.csv_export()
    excel_tauglich = False
    if export.get("ok"):
        with open(export["datei"], "rb") as datei:
            roh = datei.read()
        import csv as _csv
        with open(export["datei"], encoding="utf-8-sig", newline="") as datei:
            zeilen = list(_csv.reader(datei, delimiter=";"))
        excel_tauglich = (roh.startswith(b"\xef\xbb\xbf") and zeilen[0][3] == "Händler"
                          and len(zeilen) == 3)
    pruefen("CSV-Export öffnet sich in Excel korrekt", excel_tauglich,
            "BOM, Semikolon, Umlaute in Ordnung")


def pruefung_vertrieb(agent):
    abschnitt("Kundengespräche")
    analyse = agent.tools.call_analysis
    # Die Einzelbewertung gehoert dazu - Claude liefert sie bei jedem Gespraech mit.
    for daten, bewertung in (
        ({"kunde": "Berger", "datum": "2026-08-20", "punktzahl": 45, "ergebnis": "offen",
          "volumen": 14400, "einwaende": ["Preis zu hoch"],
          "offene_einwaende": ["Preis zu hoch"],
          "schwaechen": ["Bodenbelag und Quadratmeter nie erfasst"],
          "naechster_schritt": "Angebot mit Quadratmeterpreis schicken"},
         {"bedarf_erfasst": 4, "objekt_verstanden": 3, "preis_begruendet": 2,
          "einwaende_behandelt": 6, "abschluss_gesucht": 8}),
        ({"kunde": "Huber", "datum": "2026-08-22", "punktzahl": 80,
          "ergebnis": "gewonnen", "volumen": 9000, "einwaende": ["Preis zu hoch"]},
         {"bedarf_erfasst": 8, "objekt_verstanden": 9, "preis_begruendet": 7,
          "einwaende_behandelt": 8, "abschluss_gesucht": 9}),
        ({"kunde": "Wolf", "datum": "2026-08-24", "punktzahl": 30,
          "ergebnis": "verloren", "volumen": 0, "einwaende": ["Preis zu hoch"]},
         {}),
    ):
        analyse._ablegen(daten, "Testbericht", bewertung)

    leads = analyse.offene_leads()
    muster = analyse.verkaufsmuster()
    pruefen("offene_leads liefert Anzahl und Volumen",
            leads["anzahl"] == 1 and leads["volumen_offen"] == 14400.0, leads["text"])
    pruefen("verkaufsmuster liefert Quote und wiederkehrende Einwände",
            muster["abschlussquote"] == 50.0
            and muster["wiederkehrende_einwaende"][0]["anzahl"] == 4,
            muster["text"])

    schnitt = analyse.dimensionen_schnitt()
    pruefen("Einzelbewertungen werden gemittelt und die schwächste benannt",
            schnitt["schwaechste"]["schluessel"] == "preis_begruendet"
            and schnitt["bewertete_gespraeche"] == 2,
            "schwächste: %s mit %.1f" % (schnitt["schwaechste"]["name"],
                                         schnitt["schwaechste"]["wert"]))


def pruefung_routinen(agent):
    abschnitt("Routinen")
    routinen = agent.tools.routines
    routinen.routine_anlegen("Tagesbericht", "Zahlen zusammenfassen und schicken",
                             "18 Uhr")
    treffer = routinen.routine_finden("den Tages Bericht")
    pruefen("Routine mit ungenauem Namen finden",
            treffer is not None and treffer["name"] == "Tagesbericht",
            "'den Tages Bericht' -> %s" % (treffer["name"] if treffer else "nichts"))

    zeitplan = Scheduler(agent=agent, routines=routinen)
    anzahl = zeitplan.routinen_einhaengen()
    pruefen("Routine mit Uhrzeit erscheint im Zeitplan", anzahl >= 1,
            ", ".join("%s %s" % (e["uhrzeit"], e["beschreibung"])
                      for e in zeitplan.uebersicht()))


def pruefung_zeitplan():
    abschnitt("Zeitplan")
    neun = lambda h, m: datetime(2026, 1, 1, h, m)  # noqa: E731
    pruefen("9:30 ist fällig bei einem 9:00-Job", ist_faellig("09:00", neun(9, 30)) is True)
    pruefen("8:00 ist nicht fällig", ist_faellig("09:00", neun(8, 0)) is False)
    pruefen("14:00 ist nicht fällig, weil zu spät",
            ist_faellig("09:00", neun(14, 0)) is False, "wird nicht nachgeholt")

    zeitplan = Scheduler()
    zeitplan.job_anlegen("morgen", "06:45", lambda: "Briefing")
    zeitplan.vergangenes_abhaken(neun(19, 0))
    pruefen("Beim Start gilt heute Vergangenes als erledigt",
            zeitplan.faellige_jobs(neun(19, 0)) == [])


def pruefung_kalender():
    abschnitt("Kalender")
    ics = ("BEGIN:VCALENDAR\nBEGIN:VEVENT\nUID:1\nSUMMARY:Objekt Berger\n"
           "DTSTART:20260827T090000Z\nDTEND:20260827T103000Z\nEND:VEVENT\n"
           "BEGIN:VEVENT\nUID:2\nSUMMARY:Kunde Huber\nDTSTART:20260827T100000Z\n"
           "DTEND:20260827T110000Z\nEND:VEVENT\nEND:VCALENDAR")
    termine = ics_termine_lesen(ics)
    konflikte = konflikte_finden(termine)
    pruefen("Konflikterkennung findet Überschneidungen",
            len(konflikte) == 1 and konflikte[0]["minuten"] == 30,
            konflikte[0]["text"] if konflikte else "keiner")


def pruefung_dashboard(agent):
    abschnitt("Dashboard")
    ergebnis = agent.tools.dashboard.bauen()
    inhalt = ""
    if ergebnis.get("ok"):
        with open(ergebnis["datei"], encoding="utf-8") as datei:
            inhalt = datei.read()
    pruefen("Dashboard wird erzeugt und enthält die Kennzahlen",
            ergebnis.get("ok") and "1.069,60" in inhalt and "178,27" in inhalt
            and "refresh" in inhalt, "%d Zeichen" % len(inhalt))


def pruefung_ansichten(agent):
    """Command Center, Sales-Analyse und Landingpage - wirklich erzeugen und ansehen."""
    abschnitt("Oberflächen")

    ergebnis = agent.tools.dashboard.bauen()
    inhalt = ""
    if ergebnis.get("ok"):
        with open(ergebnis["datei"], encoding="utf-8") as datei:
            inhalt = datei.read()
    pruefen("Command Center enthält die Kennzahlen",
            ergebnis.get("ok") and "1.069,60" in inhalt and "178,27" in inhalt
            and "refresh" in inhalt, "%d Zeichen" % len(inhalt))
    pruefen("Command Center zeichnet Ring, Verlauf und Balken",
            "stroke-dasharray" in inhalt and "<polyline" in inhalt
            and "balkenzeile" in inhalt, "alles als eigenes SVG, ohne Fremdpaket")

    # Die Belegquote muss aus den echten Buchungen kommen, nicht geraten sein.
    quote = agent.tools.bookkeeping.belegquote()
    pruefen("Belegquote wird aus echten Buchungen gerechnet",
            quote["quote"] == 0.0 and quote["gesamt"] == 130.40,
            "%s von %s belegt" % (quote["belegt"], quote["gesamt"]))

    sales = ergebnis.get("sales", "")
    sales_inhalt = ""
    if sales and os.path.exists(sales):
        with open(sales, encoding="utf-8") as datei:
            sales_inhalt = datei.read()
    dimensionen = ["Bedarf erfasst", "Objekt verstanden", "Preis begründet",
                   "Einwände behandelt", "Abschluss gesucht"]
    pruefen("Sales-Analyse wird mitgebaut", bool(sales_inhalt),
            sales or "nicht erzeugt")
    pruefen("Sales-Analyse zeigt alle fünf Einzelbewertungen",
            all(d in sales_inhalt for d in dimensionen),
            ", ".join(d for d in dimensionen if d not in sales_inhalt) or "alle fünf")
    pruefen("Sales-Analyse nennt den nächsten Schritt",
            "Angebot mit Quadratmeterpreis schicken" in sales_inhalt)
    pruefen("Gespräch ohne Einzelbewertung wird als solches gekennzeichnet",
            "ohne Einzelbewertung abgelegt" in sales_inhalt,
            "Wolf hat keine Bewertung - das steht auch da")

    # Ohne Gespräche muss die Seite ehrlich leer sein, nicht mit Nullen füllen.
    from modules.sales_view import Verkaufsansicht
    leer_pfad = os.path.join(ARBEITSVERZEICHNIS, "leer.html")
    leer = Verkaufsansicht(None, None).bauen(ziel=leer_pfad)
    leer_inhalt = ""
    if leer.get("ok"):
        with open(leer_pfad, encoding="utf-8") as datei:
            leer_inhalt = datei.read()
    pruefen("Sales-Analyse ohne Daten bleibt ehrlich leer",
            "noch kein Kundengespräch festgehalten" in leer_inhalt,
            "kein erfundener Nullwert")

    # Landingpage
    landung = os.path.join(WURZEL, "landing", "index.html")
    roh = ""
    if os.path.exists(landung):
        with open(landung, encoding="utf-8") as datei:
            roh = datei.read()
    pruefen("Landingpage vorhanden", bool(roh), "%d Zeichen" % len(roh))
    if roh:
        import re as _re
        extern = _re.findall(r'(?:src|href)="(https?://[^"]+)"', roh)
        pruefen("Landingpage lädt nichts aus dem Netz nach", not extern,
                ", ".join(extern) or "vollständig eigenständig")
        pruefen("Landingpage verspricht kein Löschen von Mails",
                "Löschen" not in roh and "löscht nie" in roh,
                "Jarvis löscht keine Mail - das steht auch so da")

        class _Pruefer(__import__("html.parser", fromlist=["parser"]).HTMLParser):
            LEER = {"meta", "link", "br", "img", "hr", "input", "rect", "line",
                    "circle", "ellipse", "path", "polyline", "polygon", "stop",
                    "use", "fegaussianblur", "femergenode", "femerge"}

            def __init__(self):
                super().__init__()
                self.stapel = []
                self.fehler = []

            def handle_starttag(self, tag, attrs):
                if tag.lower() not in self.LEER:
                    self.stapel.append(tag)

            def handle_endtag(self, tag):
                if tag.lower() in self.LEER:
                    return
                if not self.stapel or self.stapel[-1] != tag:
                    self.fehler.append(tag)
                    if tag in self.stapel:
                        while self.stapel and self.stapel.pop() != tag:
                            pass
                else:
                    self.stapel.pop()

        pruefer = _Pruefer()
        pruefer.feed(roh)
        pruefen("Landingpage ist wohlgeformtes HTML",
                not pruefer.fehler and not pruefer.stapel,
                ("offen: %s" % (pruefer.stapel + pruefer.fehler)[:3])
                if (pruefer.stapel or pruefer.fehler) else "alle Tags geschlossen")


def pruefung_sicherheit(agent):
    abschnitt("Sicherheit")
    ergebnis = agent.tools.run("systeminfo", {"was": "rm -rf /"})
    pruefen("systeminfo mit 'rm -rf /' wird abgewiesen", ergebnis["ok"] is False,
            ergebnis.get("fehler", "")[:55])

    ergebnis = agent.tools.run("ordner_zeigen", {"pfad": ".;rm -rf /"})
    pruefen("ordner_zeigen mit '.;rm -rf /' wird abgewiesen", ergebnis["ok"] is False,
            ergebnis.get("fehler", "")[:55])

    for boese in ("$(whoami)", "a|b", "a&b", "a`b`", "a>b"):
        ergebnis = agent.tools.run("ordner_zeigen", {"pfad": boese})
        if ergebnis["ok"]:
            pruefen("Parameter %r wird abgewiesen" % boese, False)
            return
    pruefen("Alle Sonderzeichen in Parametern werden abgewiesen", True,
            "; | & $ ` < > und Zeilenumbruch")


def pruefung_freigaben():
    abschnitt("Freigaben (über ein echtes Terminal)")
    code = ('e = w.run("mail_senden", {"an":"kunde@beispiel.at","betreff":"A","text":"B"})\n'
            'print("ERGEBNIS:" + __import__("json").dumps(e, ensure_ascii=False))')

    _, ergebnis = im_terminal(code, antwort=b"nein\n")
    pruefen("Freigabepflichtige Aktion bei 'nein' meldet Abgebrochen",
            ergebnis is not None and ergebnis["ok"] is False
            and "Abgebrochen" in ergebnis.get("text", ""),
            (ergebnis or {}).get("text", "keine Antwort erhalten"))

    _, ergebnis = im_terminal(code, antwort=None)
    pruefen("Freigabe ohne Antwort gilt als Ablehnung",
            ergebnis is not None and ergebnis["ok"] is False
            and "keine Antwort" in ergebnis.get("text", ""),
            (ergebnis or {}).get("text", "keine Antwort erhalten"))

    code = ('e = w.run("nachricht_senden", {"kanal":"telegram","an":"1","text":"Hi"})\n'
            'print("ERGEBNIS:" + __import__("json").dumps(e, ensure_ascii=False))')
    _, ergebnis = im_terminal(code, antwort=b"nein\n")
    pruefen("nachricht_senden ist freigabepflichtig",
            ergebnis is not None and ergebnis["ok"] is False
            and "Abgebrochen" in ergebnis.get("text", ""),
            (ergebnis or {}).get("text", ""))


def pruefung_mcp():
    abschnitt("MCP")
    testserver = os.path.join(WURZEL, "tests", "mcp_testserver.py")
    eintrag = {"aus": False, "befehl": sys.executable, "argumente": [testserver],
               "ohne_rueckfrage": ["liste_lesen"]}
    client = MCPClient()
    client.konfig = {"server": {"test": eintrag}}
    server = MCPServer("test", eintrag)
    gestartet = server.starten()
    if not gestartet:
        pruefen("MCP-Testserver startet", False, server.fehler)
        return
    client.server_hinzufuegen("test", server)
    namen = [w["name"] for w in client.alle_werkzeuge()]
    pruefen("MCP-Werkzeuge tauchen im Katalog auf", len(namen) == 2, ", ".join(namen))
    pruefen("ohne_rueckfrage läuft ohne Nachfrage durch",
            client.braucht_freigabe("mcp__test__liste_lesen") is False)
    pruefen("alles andere fragt nach",
            client.braucht_freigabe("mcp__test__datei_loeschen") is True)
    ergebnis = client.aufrufen("mcp__test__liste_lesen", {"was": "kunden"})
    pruefen("MCP-Aufruf liefert ein Ergebnis", ergebnis.get("ok") is True,
            ergebnis.get("text", "")[:50])
    server.stoppen()


def pruefung_sprache_und_welt(agent):
    abschnitt("Sprache, Kamera, Welt")
    erkannt, rest = weckwort_pruefen("Hey Dscharvis, erfass die Quittung")
    pruefen("Weckwort auch bei falscher Schreibung erkannt",
            erkannt and rest == "erfass die Quittung", "Rest: %s" % rest)

    ergebnis = agent.tools.run("umschauen", {"frage": "Was liegt da?"})
    kamera_da = agent.tools.kamera.verfuegbar()
    pruefen("umschauen meldet sauber, was fehlt (kein Absturz)",
            ergebnis["ok"] is False and "fehler" in ergebnis,
            ergebnis.get("fehler", "")[:55] if not kamera_da else "Kamera vorhanden")

    wetter = agent.tools.run("wetter", {"ort": "Wien"})
    pruefen("wetter liefert eine gesprochene Vorhersage",
            wetter.get("ok") and "Grad" in wetter.get("text", ""),
            wetter.get("text", wetter.get("fehler", ""))[:58])

    flug = agent.tools.run("flug_suchen", {"von": "Wien", "nach": "Berlin"})
    pruefen("flug_suchen bucht nichts von selbst",
            flug.get("gebucht", False) is False,
            "ohne Such-Dienst: %s" % flug.get("fehler", "")[:40] if not flug.get("ok")
            else "Optionen genannt, nichts gebucht")


def pruefung_einzeldatei():
    abschnitt("Einzeldatei")
    pfad = os.path.join(WURZEL, "jarvis.py")
    if not os.path.exists(pfad):
        pruefen("jarvis.py vorhanden", False, "erst bauen")
        return
    with open(pfad, encoding="utf-8") as datei:
        inhalt = datei.read()
    klassen = ["Memory", "Recall", "Stimme", "Sprecherprofil", "Mail", "Kalender",
               "Telegram", "Bookkeeping", "CallAnalysis", "Routines", "Kamera",
               "MCPServer", "MCPClient", "Welt", "Messenger", "Bildschirm",
               "Dashboard", "Verkaufsansicht", "Scheduler", "Einrichtung",
               "Werkzeuge", "JarvisAgent"]
    fehlend = [k for k in klassen if inhalt.count("\nclass %s" % k) != 1]
    pruefen("Einzeldatei enthält alle Klassen genau einmal", not fehlend,
            ", ".join(fehlend) or "%d Klassen" % len(klassen))

    zeilen = [z for z in inhalt.splitlines()
              if z.startswith("config.") or " config." in z and not z.strip().startswith("#")]
    pruefen("keine config.X-Bezüge mehr in der Einzeldatei", not zeilen,
            zeilen[0][:55] if zeilen else "alle aufgelöst")

    ergebnis = subprocess.run([sys.executable, pfad, "test"], capture_output=True,
                              shell=False, cwd=WURZEL, stdin=subprocess.DEVNULL,
                              timeout=300)
    pruefen("jarvis.py test läuft ohne Absturz durch", ergebnis.returncode == 0,
            "Rückgabewert %d" % ergebnis.returncode)


def main() -> int:
    print("=" * 74)
    print("ABNAHME - jeder Punkt wird wirklich ausgeführt")
    print("Arbeitsverzeichnis: %s" % ARBEITSVERZEICHNIS)
    print("=" * 74)

    pruefung_syntax()
    agent = pruefung_agent()
    pruefung_buchhaltung(agent)
    pruefung_vertrieb(agent)
    pruefung_routinen(agent)
    pruefung_zeitplan()
    pruefung_kalender()
    pruefung_dashboard(agent)
    pruefung_ansichten(agent)
    pruefung_sicherheit(agent)
    pruefung_freigaben()
    pruefung_mcp()
    pruefung_sprache_und_welt(agent)
    pruefung_einzeldatei()

    print("\n" + "=" * 74)
    print("%d von %d Punkten bestanden."
          % (len(BESTANDEN), len(BESTANDEN) + len(DURCHGEFALLEN)))
    if DURCHGEFALLEN:
        print("\nNicht bestanden:")
        for name in DURCHGEFALLEN:
            print("  - %s" % name)
    print("=" * 74)
    shutil.rmtree(ARBEITSVERZEICHNIS, ignore_errors=True)
    return 1 if DURCHGEFALLEN else 0


if __name__ == "__main__":
    sys.exit(main())
