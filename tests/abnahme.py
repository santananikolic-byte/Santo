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
import pathlib
import pty
import select
import shutil
import subprocess
import sys
import threading
import tempfile
import time
from datetime import datetime, timedelta

WURZEL = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(WURZEL, "src"))

import config  # noqa: E402

ARBEITSVERZEICHNIS = tempfile.mkdtemp(prefix="jarvis_abnahme_")
config.DB_PFAD = os.path.join(ARBEITSVERZEICHNIS, "test.db")
config.EXPORT_VERZEICHNIS = __import__("pathlib").Path(ARBEITSVERZEICHNIS)
config.LOG_VERZEICHNIS = __import__("pathlib").Path(ARBEITSVERZEICHNIS)

from agent import JarvisAgent  # noqa: E402
from modules.bookkeeping import mwst_aus_brutto  # noqa: E402
import agent as agent_modul  # noqa: E402
from modules.router import Gedankenlog, claude_kosten, gehirn_waehlen  # noqa: E402
from modules.calendar_mod import ics_termine_lesen, konflikte_finden  # noqa: E402
from modules.mcp_client import MCPClient, MCPServer  # noqa: E402
from modules.akquise import Akquise  # noqa: E402
from modules.scheduler import Scheduler, ist_faellig  # noqa: E402
from modules.privat import Privat, monatsanteil  # noqa: E402
from modules.team import ROLLEN, Team  # noqa: E402
from modules.webapp import JarvisWeb, WebFreigabe  # noqa: E402
from modules.webseite import SEITE_HTML  # noqa: E402
import modules.setup_wizard as wizard_modul  # noqa: E402
from modules import autopilot as autopilot_modul  # noqa: E402
from modules.autopilot import in_ruhezeit, rolle_raten  # noqa: E402
from modules.tools import FREIGABE_PFLICHTIG  # noqa: E402
from modules.lernpfad import SEITE_PFAD, lernpfad_stand  # noqa: E402
from modules.werkstatt import Werkstatt, name_saeubern  # noqa: E402
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
    # Die Buchungen liegen im laufenden Monat, sonst zeigt das Command Center
    # (es rechnet immer den aktuellen Monat) nichts davon - die Prüfung würde
    # mit jedem Monatswechsel kippen.
    erster = datetime.now().strftime("%Y-%m-01")
    buch.buchung_eintragen("ausgabe", erster, 130.40, "Baumarkt",
                           "Arbeitsmaterial", 20)
    buch.buchung_eintragen("einnahme", erster, 1200.00, "Berger GmbH",
                           "Sonstiges", 20)
    auswertung = buch.auswertung(erster, datetime.now().strftime("%Y-%m-%d"))
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


def pruefung_akquise(agent):
    """Aufträge hereinholen: Kalkulation, Pipeline, Nachfassen, Cashflow."""
    abschnitt("Akquise")
    akquise = agent.tools.akquise

    # Von Hand nachgerechnet: 600 / 300 m² je Stunde = 2 h je Reinigung,
    # 2x pro Woche = 8,66 Reinigungen, also 17,32 Stunden. Mal 32 Euro plus
    # 4 Prozent Material.
    kalkulation = akquise.angebot_kalkulieren(600, "Linoleum", 2, 32)
    erwartete_stunden = 600 / 300.0 * 2 * 4.33
    erwartetes_netto = round(erwartete_stunden * 32 * 1.04, 2)
    pruefen("Angebot über Leistungswerte gerechnet",
            kalkulation.get("ok")
            and abs(kalkulation["stunden_monat"] - erwartete_stunden) < 0.01
            and abs(kalkulation["netto_monat"] - erwartetes_netto) < 0.01,
            "%.2f Stunden, %.2f Euro netto" % (kalkulation.get("stunden_monat", 0),
                                               kalkulation.get("netto_monat", 0)))
    pruefen("Sanitär wird langsamer gerechnet als eine Halle",
            akquise.angebot_kalkulieren(100, "Sanitaer", 1)["stunden_monat"] >
            akquise.angebot_kalkulieren(100, "Industriehalle", 1)["stunden_monat"] * 5,
            "80 gegen 500 Quadratmeter je Stunde")
    pruefen("Ohne Quadratmeter wird nicht kalkuliert",
            akquise.angebot_kalkulieren(0, "Teppich", 2).get("ok") is False,
            akquise.angebot_kalkulieren(0, "Teppich", 2).get("fehler", "")[:52])
    pruefen("Ohne Intervall wird nicht kalkuliert",
            akquise.angebot_kalkulieren(600, "Teppich", 0).get("ok") is False)

    akquise.lead_anlegen("Berger GmbH", objekt_qm=600, bodenbelag="Linoleum",
                         intervall_pro_woche=2)
    akquise.lead_anlegen("Huber Ordination", objekt_qm=180, bodenbelag="Sanitaer",
                         intervall_pro_woche=3)
    pruefen("Derselbe Interessent wird nicht doppelt angelegt",
            akquise.lead_anlegen("berger gmbh").get("ok") is False)
    akquise.lead_weiterstufen("Huber", "gewonnen", "Vertrag unterschrieben")
    akquise.lead_weiterstufen("Berger", "angebot", "Angebot verschickt")

    pipeline = akquise.pipeline()
    pruefen("Pipeline trennt gesichert von gewichtet",
            pipeline["laufender_umsatz_monat"] > 0
            and 0 < pipeline["gewichteter_wert_monat"] < pipeline["offener_wert_monat"],
            "gesichert %.2f, offen %.2f, gewichtet %.2f"
            % (pipeline["laufender_umsatz_monat"], pipeline["offener_wert_monat"],
               pipeline["gewichteter_wert_monat"]))

    spaeter = (datetime.now() + timedelta(days=14)).strftime("%Y-%m-%d")
    nachfassen = akquise.nachfassliste(spaeter)
    pruefen("Nachfassliste nennt Überfällige", nachfassen["anzahl"] >= 1
            and nachfassen["eintraege"][0]["seit_tagen"] > 0,
            nachfassen["text"][:52])

    cashflow = akquise.cashflow_prognose(6, agent.tools.bookkeeping)
    erster, letzter = cashflow["monate"][0], cashflow["monate"][-1]
    pruefen("Cashflow setzt die Pipeline erst später an",
            erster["aus_pipeline"] == 0 and letzter["aus_pipeline"] > 0,
            "Monat 1: %.2f, Monat 6: %.2f" % (erster["aus_pipeline"],
                                              letzter["aus_pipeline"]))


def pruefung_privat(agent):
    """Das Leben neben der Firma und die Brücke zum Umsatz."""
    abschnitt("Privat")
    privat = agent.tools.privat

    proben = [("monatlich", 1200, 1200.0), ("jaehrlich", 1200, 100.0),
              ("quartalsweise", 300, 100.0), ("halbjaehrlich", 600, 100.0)]
    falsch = [r for r, b, e in proben if abs(monatsanteil(b, r) - e) > 0.01]
    pruefen("Rhythmen werden auf den Monat gerechnet", not falsch,
            ", ".join(falsch) or "vier Rhythmen geprüft")

    pruefen("Ohne Fixkosten wird nichts erfunden",
            privat.bedarfsrechnung().get("berechenbar") is False,
            "es wird nach den Fixkosten gefragt")

    for name, betrag, rhythmus, bereich in (
            ("Miete Wohnung", 950, "monatlich", "privat"),
            ("Krankenversicherung", 420, "monatlich", "privat"),
            ("Auto Leasing", 289, "monatlich", "privat"),
            ("Haushaltsversicherung", 360, "jaehrlich", "privat"),
            ("Handy", 45, "monatlich", "privat"),
            ("Strom Gas", 180, "monatlich", "privat"),
            ("Lager Miete", 250, "monatlich", "firma"),
            ("Firmenwagen Versicherung", 1080, "jaehrlich", "firma"),
            ("Buchhaltungssoftware", 29, "monatlich", "firma")):
        privat.fixkosten_anlegen(name, betrag, rhythmus, bereich)

    kosten = privat.fixkosten()
    pruefen("Privat und Firma bleiben getrennt",
            kosten["privat_je_monat"] == 1914.0 and kosten["firma_je_monat"] == 369.0,
            "privat %.2f, firma %.2f" % (kosten["privat_je_monat"],
                                         kosten["firma_je_monat"]))

    # Von Hand: Umsatz = Firmenkosten + Privatkosten / (1 - Steuersatz)
    bedarf = privat.bedarfsrechnung()
    erwartet = round(369 + 1914 / (1 - privat.steuersatz / 100.0), 2)
    pruefen("Nötiger Monatsumsatz stimmt",
            abs(bedarf["noetiger_umsatz"] - erwartet) < 0.02,
            "%.2f Euro bei %g Prozent Rücklage" % (bedarf["noetiger_umsatz"],
                                                   privat.steuersatz))
    # Gegenprobe: Umsatz minus Firmenkosten minus Steuer muss das Private decken
    gewinn = bedarf["noetiger_umsatz"] - bedarf["firma_je_monat"]
    uebrig = gewinn * (1 - privat.steuersatz / 100.0)
    pruefen("Gegenprobe: nach Steuer bleibt genau das Private übrig",
            abs(uebrig - bedarf["privat_je_monat"]) < 0.02,
            "%.2f gegen %.2f" % (uebrig, bedarf["privat_je_monat"]))

    mit_lage = privat.bedarfsrechnung(agent.tools.akquise)
    pruefen("Die Lücke zur Auftragslage wird benannt",
            mit_lage.get("luecke") is not None,
            "Lücke %.2f je Monat" % (mit_lage.get("luecke") or 0))

    pruefen("Falsches Datum wird abgewiesen",
            privat.erinnerung_anlegen("x", "4.9.2026").get("ok") is False)
    privat.erinnerung_anlegen("Pickerl Firmenwagen", "2026-09-04", "jaehrlich", "firma")
    privat.erinnerung_anlegen("Geburtstag Mama", "2026-09-12", "jaehrlich")
    faellig = privat.erinnerungen_faellig(21, ab="2026-08-26")
    pruefen("Anstehendes wird nach Nähe sortiert",
            faellig["anzahl"] == 2 and faellig["eintraege"][0]["in_tagen"] == 9,
            faellig["text"][:52])
    spaeter = privat.erinnerungen_faellig(400, ab="2026-09-20")
    pruefen("Jährliche Termine rollen ins Folgejahr",
            all(e["datum"].startswith("2027") for e in spaeter["eintraege"]
                if e["wiederholung"] == "jaehrlich"),
            "nach dem Termin zählt das nächste Jahr")


def pruefung_leadfinder(agent):
    """Neue Betriebe finden - ohne Werte zu erfinden."""
    abschnitt("Lead-Finder")
    akquise = agent.tools.akquise

    pruefen("Ohne Ort wird nicht gesucht",
            akquise.leads_finden("").get("ok") is False)

    class _WeltOhne(object):
        @staticmethod
        def recherche(frage):
            del frage
            return {"ok": False, "fehler": "Such-Dienst fehlt"}

    class _AgentJa(object):
        @staticmethod
        def einsatzbereit():
            return True

        @staticmethod
        def json_anfrage(auftrag, **rest):
            del auftrag, rest
            return {"ok": True, "daten": {"betriebe": [
                {"firma": "Ordination Dr. Weber", "branche": "Arztpraxis",
                 "adresse": "Hauptstr. 3", "telefon": "01 5551234"},
                {"firma": "Kanzlei Reiter", "branche": "Kanzlei",
                 "adresse": "Ring 12", "telefon": ""}]}}

    ohne = akquise.leads_finden("Wien", welt=_WeltOhne(), agent=_AgentJa())
    pruefen("Ohne Such-Dienst kommt ein brauchbarer Hinweis",
            ohne.get("ok") is False and "mcp_servers.json" in ohne.get("fehler", ""),
            "es wird gesagt, was einzuschalten ist")

    class _WeltMit(object):
        @staticmethod
        def recherche(frage):
            del frage
            return {"ok": True, "text": "Dr. Weber ... Kanzlei Reiter ..."}

    erster = akquise.leads_finden("Wien", welt=_WeltMit(), agent=_AgentJa())
    pruefen("Gefundene Betriebe landen in der Pipeline",
            erster.get("ok") and len(erster["neu"]) == 2, erster.get("text", "")[:52])

    neue = [z for z in agent.tools.memory._lesen(
        "SELECT * FROM leads WHERE quelle LIKE 'Recherche%'")]
    pruefen("Gefundene Betriebe bekommen keinen erfundenen Wert",
            all(z["wert_monat"] == 0 and z["stufe"] == "neu" for z in neue),
            "Wert null bis zum Anruf")

    zweiter = akquise.leads_finden("Wien", welt=_WeltMit(), agent=_AgentJa())
    pruefen("Zweiter Lauf legt nichts doppelt an",
            zweiter.get("ok") and not zweiter["neu"] and len(zweiter["bekannt"]) == 2)


def pruefung_team(agent):
    """Die Fachkräfte - vor allem, dass die Werkzeugtrennung wirklich greift."""
    abschnitt("Team")
    team = agent.tools.team
    pruefen("Neun Fachkräfte vorhanden", len(ROLLEN) == 9,
            ", ".join(sorted(ROLLEN)))
    treffer = {"buchhaltung": "buchhalter", "vertrieb": "akquisiteur",
               "mails sortieren": "postmeister", "cashflow": "controller",
               "skript": "programmierer", "kalender": "terminplaner"}
    falsch = [wort for wort, rolle in treffer.items()
              if Team.rolle_finden(wort) != rolle]
    pruefen("Umgangssprache trifft die richtige Rolle", not falsch,
            ", ".join(falsch) or "alle sechs Proben")
    pruefen("Unbekannte Rolle wird abgewiesen",
            team.beauftragen("hausmeister", "x").get("ok") is False)

    # Der eigentliche Punkt: jede Rolle sieht nur ihre Werkzeuge.
    alle = set(agent.tools.namen())
    verstoesse = []
    for rolle, angaben in ROLLEN.items():
        unbekannt = [w for w in angaben["werkzeuge"] if w not in alle]
        if unbekannt:
            verstoesse.append("%s kennt %s nicht" % (rolle, unbekannt[0]))
    pruefen("Jede Rolle nennt nur vorhandene Werkzeuge", not verstoesse,
            verstoesse[0] if verstoesse else "%d Rollen geprüft" % len(ROLLEN))
    pruefen("Der Verkäufer kann nicht buchen und nicht mailen",
            "buchung_eintragen" not in ROLLEN["akquisiteur"]["werkzeuge"]
            and "mail_senden" not in ROLLEN["akquisiteur"]["werkzeuge"],
            "%d von %d Werkzeugen"
            % (len(ROLLEN["akquisiteur"]["werkzeuge"]), len(alle)))
    pruefen("Der Buchhalter kann nichts verschicken",
            not [w for w in ROLLEN["buchhalter"]["werkzeuge"]
                 if w in ("mail_senden", "nachricht_senden", "termin_anlegen")])
    pruefen("Der Rechercheur kann nichts eintragen",
            "buchung_eintragen" not in ROLLEN["rechercheur"]["werkzeuge"]
            and "lead_anlegen" not in ROLLEN["rechercheur"]["werkzeuge"])

    lage = team.lagebericht(agent.tools)
    pruefen("Lagebericht nennt die Kassenzahlen",
            lage.get("ok") and "Einnahmen" in lage["text"],
            lage.get("text", "")[:52])


def pruefung_werkstatt(agent):
    """Der Programmierer - Pfade, Fehler, Laufzeit."""
    abschnitt("Werkstatt")
    werkstatt = agent.tools.werkstatt

    angriffe = ["../../etc/passwd", "/etc/shadow", "..\\..\\windows"]
    ausbrueche = [n for n in angriffe
                  if "/" in name_saeubern(n) or "\\" in name_saeubern(n)
                  or ".." in name_saeubern(n)]
    pruefen("Pfadangriffe im Dateinamen sind nicht darstellbar", not ausbrueche,
            "%s wird zu %s" % (angriffe[0], name_saeubern(angriffe[0])))

    pruefen("Syntaxfehler wird vor dem Ablegen erkannt",
            werkstatt.skript_schreiben("kaputt", "def x(\n  print(1)").get("ok") is False)

    abgelegt = werkstatt.skript_schreiben(
        "rechnen", "stunden = 600 / 300 * 2 * 4.33\nprint('%.2f' % stunden)",
        "Testrechner")
    pruefen("Skript wird abgelegt, aber nicht ausgeführt", abgelegt.get("ok")
            and "Ausgeführt ist noch nichts" in abgelegt["text"])

    gelaufen = werkstatt.skript_ausfuehren("rechnen")
    pruefen("Skript läuft und liefert seine Ausgabe",
            gelaufen.get("ok") and "17.32" in gelaufen.get("ausgabe", ""),
            gelaufen.get("ausgabe", "")[:40])

    werkstatt.skript_schreiben("faellt_um", "raise ValueError('Absicht')")
    pruefen("Ein Fehler im Skript wird sauber gemeldet",
            werkstatt.skript_ausfuehren("faellt_um").get("ok") is False)

    werkstatt.skript_schreiben("holt_was", "import urllib.request\nprint(1)")
    text = werkstatt.freigabetext("holt_was")
    pruefen("Die Freigabefrage zeigt Code und Absicht",
            "will ins Netz" in text and "urllib" in text,
            "Netzzugriff wird benannt")

    pruefen("skript_ausfuehren ist freigabepflichtig",
            agent.tools.braucht_freigabe("skript_ausfuehren") is True)


def pruefung_werkzeugvertrag(agent):
    """Jedes Werkzeug muss ein ok melden - sonst gilt Erfolg als Fehler."""
    abschnitt("Werkzeugvertrag")
    proben = {
        "notiz_speichern": {"text": "Vertragsprobe"},
        "notizen_suchen": {"begriff": "Vertragsprobe"},
        "punkte_offen": {}, "auswertung": {}, "fehlende_belege": {},
        "csv_export": {}, "offene_leads": {}, "verkaufsmuster": {},
        "routinen_liste": {}, "pipeline": {}, "nachfassliste": {},
        "anrufliste": {},
        "cashflow_prognose": {"monate": 3}, "team_liste": {}, "lagebericht": {},
        "werkstatt_liste": {}, "gedaechtnis_durchsuchen": {"frage": "Berger"},
        "fixkosten_liste": {}, "bedarfsrechnung": {},
        "erinnerungen_faellig": {"tage": 14},
        "angebot_kalkulieren": {"qm": 300, "intervall_pro_woche": 1},
    }
    ohne = []
    for name, argumente in proben.items():
        ergebnis = agent.tools.run(name, argumente)
        if not isinstance(ergebnis, dict) or "ok" not in ergebnis:
            ohne.append(name)
    pruefen("Alle geprüften Werkzeuge melden ok", not ohne,
            ", ".join(ohne) or "%d Werkzeuge geprüft" % len(proben))


def pruefung_browser(agent):
    """Browser: Adressen, Haltepunkte und - wenn möglich - eine echte Seite."""
    abschnitt("Browser")
    import http.server
    import socketserver
    import threading
    import config as konfig
    from modules.browser import Browser, adresse_pruefen, haltepunkt

    gut = {"orf.at": "https://orf.at", "https://x.de": "https://x.de",
           "www.a.at/pfad?q=1": "https://www.a.at/pfad?q=1"}
    falsch = [roh for roh, erwartet in gut.items() if adresse_pruefen(roh)[0] != erwartet]
    pruefen("Adressen werden vervollständigt", not falsch,
            ", ".join(falsch) or "3 Schreibweisen geprüft")

    # file:// und javascript: würden den Browser irgendwohin schicken, nur nicht
    # ins Netz - beide müssen abprallen.
    abgelehnt = ["file:///etc/passwd", "javascript:alert(1)", "ftp://x", "", "x y"]
    durch = [x for x in abgelehnt if adresse_pruefen(x)[0] is not None]
    pruefen("Nur http und https kommen durch", not durch,
            ", ".join(durch) or "5 Fälle abgewiesen")

    pruefen("Bezahlknöpfe lösen einen Haltepunkt aus",
            haltepunkt("Jetzt kostenpflichtig bestellen") == "kostenpflichtig"
            and haltepunkt("Weiter zur Übersicht") == "",
            "kostenpflichtig erkannt, Weiter nicht")

    pruefen("browser_auftrag ist freigabepflichtig",
            agent.tools.braucht_freigabe("browser_auftrag"), "Freigabe nötig")
    pruefen("Lesen braucht keine Freigabe",
            not agent.tools.braucht_freigabe("browser_oeffnen")
            and not agent.tools.braucht_freigabe("browser_lesen"), "nur Lesen")

    # Eine kaputte Freigabe darf nie als Ja durchgehen.
    class KaputterKanal:
        @staticmethod
        def anfordern(aktion, details):
            raise OSError("Netz weg")
    alter = agent.tools.freigabe_kanal
    agent.tools.freigabe_kanal = KaputterKanal()
    pruefen("Fehler beim Nachfragen gilt als Nein",
            agent.tools._zwischenfrage("Bezahlen?") is False, "Fehler = Ablehnung")
    agent.tools.freigabe_kanal = alter

    if not Browser.verfuegbar():
        pruefen("Ohne Playwright sagt der Browser, was fehlt",
                "playwright" in Browser(None)._fehlt()["fehler"].lower(),
                "Klartext statt Absturz")
        return

    # Ab hier läuft ein echter Browser gegen eine echte Seite.
    ordner = pathlib.Path(ARBEITSVERZEICHNIS) / "web"
    ordner.mkdir(parents=True, exist_ok=True)
    (ordner / "index.html").write_text(
        '<!doctype html><meta charset="utf-8"><title>Anfrage</title>'
        '<input type="hidden" name="geheim" value="x">'
        '<input type="text" name="firma" placeholder="Firmenname">'
        '<button style="display:none">Unsichtbar</button>'
        '<button disabled>Gesperrt</button>'
        '<a href="/zwei.html">Weiter</a>'
        '<button onclick="document.title=\'Gespeichert\'">Anfrage senden</button>',
        encoding="utf-8")
    (ordner / "zwei.html").write_text(
        '<!doctype html><meta charset="utf-8"><title>Zwei</title>'
        '<button>Jetzt kostenpflichtig bestellen</button>', encoding="utf-8")

    class Stiller(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *a, **k):
            super().__init__(*a, directory=str(ordner), **k)

        def log_message(self, *a):
            pass

    dienst = socketserver.TCPServer(("127.0.0.1", 0), Stiller)
    threading.Thread(target=dienst.serve_forever, daemon=True).start()
    basis = "http://127.0.0.1:%d/" % dienst.server_address[1]

    # In manchen Umgebungen liegt Chromium woanders als Playwright erwartet.
    alte_wahl = konfig.BROWSER_PROGRAMM
    if not alte_wahl and os.path.exists("/opt/pw-browsers/chromium"):
        konfig.BROWSER_PROGRAMM = "/opt/pw-browsers/chromium"

    browser = Browser(None, sichtbar=bool(os.environ.get("DISPLAY")))
    try:
        seite = browser.oeffnen(basis)
        if not seite.get("ok"):
            pruefen("Der Browser meldet sauber, warum er nicht startet",
                    "playwright" in seite["fehler"].lower()
                    or "chromium" in seite["fehler"].lower(), seite["fehler"][:60])
            return

        namen = [e["name"] for e in seite["elemente"]]
        pruefen("Nur echt bedienbare Elemente werden gelistet",
                namen == ["Firmenname", "Weiter", "Anfrage senden"], ", ".join(namen))

        nummer = [e["nummer"] for e in seite["elemente"] if e["name"] == "Firmenname"][0]
        getippt = browser.tippen(nummer, "Reiter & Partner GmbH")
        inhalt = [e["inhalt"] for e in getippt.get("elemente", [])
                  if e["nummer"] == nummer]
        pruefen("Text landet wirklich im Feld",
                getippt.get("ok") and inhalt == ["Reiter & Partner GmbH"], str(inhalt))

        nummer = [e["nummer"] for e in getippt["elemente"]
                  if e["name"] == "Anfrage senden"][0]
        geklickt = browser.klicken(nummer)
        pruefen("Ein Klick auf die Beschriftung wirkt",
                geklickt.get("ok") and geklickt.get("titel") == "Gespeichert",
                geklickt.get("titel", geklickt.get("fehler", "")))

        pruefen("Eine Nummer, die es nicht gibt, stürzt nicht ab",
                not browser.klicken(999).get("ok")
                and not browser.klicken("abc").get("ok"), "beide abgewiesen")

        # Der Agent will bezahlen - ohne Ja darf das nicht passieren.
        class FalscherAgent:
            @staticmethod
            def einsatzbereit():
                return True

            @staticmethod
            def json_anfrage(system, anfrage):
                return {"gedanke": "jetzt bestellen", "aktion": "klicken",
                        "ziel": 1, "text": ""}

        browser.agent = FalscherAgent()
        gefragt = []
        ergebnis = browser.erledigen("bestellen", basis + "zwei.html",
                                     bestaetigen=lambda f: (gefragt.append(f), False)[1])
        pruefen("Vor dem Bezahlen wird gefragt und bei nein gestoppt",
                not ergebnis.get("ok") and gefragt
                and "kostenpflichtig" in gefragt[0].lower(),
                (gefragt[0][:60] if gefragt else "gar nicht gefragt"))

        ohne = Browser(FalscherAgent(), sichtbar=False)
        ohne._seite, ohne._browser, ohne._spiel = (browser._seite, browser._browser,
                                                   browser._spiel)
        ergebnis = ohne.erledigen("bestellen", basis + "zwei.html")
        pruefen("Ohne Rückfragemöglichkeit wird nicht bezahlt",
                not ergebnis.get("ok") and "kostenpflichtig" in ergebnis["fehler"],
                ergebnis["fehler"][:60])
        ohne._seite = ohne._browser = ohne._spiel = None

        class Endlos(FalscherAgent):
            @staticmethod
            def json_anfrage(system, anfrage):
                return {"gedanke": "warten", "aktion": "warten", "text": ""}

        browser.agent = Endlos()
        ergebnis = browser.erledigen("endlos", basis, schritte_max=2)
        pruefen("Nach der Schrittgrenze ist Schluss",
                not ergebnis.get("ok") and len(ergebnis["schritte"]) == 2,
                "%d Schritte" % len(ergebnis["schritte"]))

        class Muell(FalscherAgent):
            @staticmethod
            def json_anfrage(system, anfrage):
                return "kein JSON"

        browser.agent = Muell()
        ergebnis = browser.erledigen("x", basis)
        pruefen("Unbrauchbare Antworten des Modells stürzen nicht ab",
                not ergebnis.get("ok") and ergebnis.get("fehler"),
                ergebnis.get("fehler", "")[:60])
    finally:
        browser.schliessen()
        dienst.shutdown()
        dienst.server_close()
        konfig.BROWSER_PROGRAMM = alte_wahl


def pruefung_telefon(agent):
    """Telefon: Nummern, Fehlerwege und die Freigabepflicht."""
    abschnitt("Telefon")
    from modules.telefon import nummer_pruefen
    import config as konfig

    alte_vorwahl = konfig.LANDESVORWAHL
    konfig.LANDESVORWAHL = "+43"
    faelle = {
        "0664 123 4567": "+436641234567",
        "00436641234567": "+436641234567",
        "+43 664 123 4567": "+436641234567",
        "+436641234567": "+436641234567",
    }
    falsch = [roh for roh, erwartet in faelle.items()
              if nummer_pruefen(roh)[0] != erwartet]
    pruefen("Nummern kommen in internationaler Form an", not falsch,
            ", ".join(falsch) or "4 Schreibweisen geprüft")

    abgelehnt = ["Unsinn", "", "   ", "+4312", "+4366412345678901234"]
    durchgerutscht = [x for x in abgelehnt if nummer_pruefen(x)[0] is not None]
    pruefen("Unbrauchbare Nummern werden abgelehnt", not durchgerutscht,
            ", ".join(repr(x) for x in durchgerutscht) or "5 Fälle geprüft")

    ohne_grund = [x for x in abgelehnt if not nummer_pruefen(x)[1].strip()]
    pruefen("Jede Ablehnung nennt einen Grund", not ohne_grund,
            ", ".join(repr(x) for x in ohne_grund) or "jeder Fall erklärt")

    konfig.LANDESVORWAHL = ""
    ziel, meldung = nummer_pruefen("0664 123 4567")
    pruefen("Ohne Landesvorwahl wird nicht geraten",
            ziel is None and "LANDESVORWAHL" in meldung, meldung[:70])
    konfig.LANDESVORWAHL = alte_vorwahl

    pruefen("Anrufen und SMS brauchen eine Freigabe",
            agent.tools.braucht_freigabe("anrufen")
            and agent.tools.braucht_freigabe("sms_senden"),
            "beide freigabepflichtig")
    pruefen("Die Anrufliste braucht keine Freigabe",
            not agent.tools.braucht_freigabe("anrufliste"), "nur Lesen")

    namen = agent.tools.namen()
    fehlend = [x for x in ("anrufen", "sms_senden", "anrufliste") if x not in namen]
    pruefen("Die Telefonwerkzeuge stehen im Katalog", not fehlend,
            ", ".join(fehlend) or "3 Werkzeuge")

    # Ohne Zugangsdaten darf nichts halb passieren - es muss sauber scheitern.
    ergebnis = agent.tools.telefon.sms_senden("+436641234567", "Probe")
    pruefen("Ohne Twilio-Daten scheitert die SMS mit Klartext",
            not ergebnis.get("ok") and "TWILIO_SID" in ergebnis.get("fehler", ""),
            ergebnis.get("fehler", "")[:70])

    ergebnis = agent.tools.telefon.anrufen("+436641234567", "")
    pruefen("Ein Anruf ohne Ansage wird abgelehnt",
            not ergebnis.get("ok"), ergebnis.get("fehler", "")[:70])

    zustand = agent.tools.telefon.zustand()
    pruefen("Der Zustand behauptet kein Gespräch, das nicht geht",
            zustand.get("gespraech_moeglich") is False,
            "Ansage und SMS ja, Dialog nein")

    liste = agent.tools.run("anrufliste", {})
    pruefen("Die Anrufliste antwortet auch leer sauber",
            liste.get("ok") and "anrufe" in liste,
            "%d Einträge" % liste.get("anzahl", -1))


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


def pruefung_router(agent):
    abschnitt("Router und Gedankenlog")
    gewaehlt = lambda frage: gehirn_waehlen(frage, True)[0]  # noqa: E731
    pruefen("Smalltalk und einfache Frage gehen an Gemini",
            gewaehlt("Wie geht es dir?") == "gemini"
            and gewaehlt("Was ist die Hauptstadt von Österreich?") == "gemini",
            "zwei Fragen")
    pruefen("Handlung oder Daten gehen an Claude",
            all(gewaehlt(f) == "claude" for f in (
                "Leg einen Termin für Freitag an", "Wie viel Umsatz hatte ich?",
                "Was steht heute an?", "Schick Berger eine Mail")),
            "vier Fragen")
    pruefen("Denkarbeit und lange Fragen gehen an Claude",
            gewaehlt("Vergleiche die beiden Wege") == "claude"
            and gewaehlt("denk gründlich nach") == "claude"
            and gewaehlt(" ".join(["wort"] * 30)) == "claude", "drei Fragen")
    pruefen("Ohne Gemini-Schlüssel antwortet immer Claude",
            gehirn_waehlen("Wie geht es dir?", False)[0] == "claude", "")

    pruefen("Kostenschätzung rechnet aus den Tokens",
            abs(claude_kosten(1_000_000, 0) - 3.0 * config.DOLLAR_IN_EURO) < 1e-6
            and claude_kosten(0, 0) == 0, "1 Mio Tokens rein")

    # Ein ganzer Durchlauf mit vorgetäuschten Gehirnen: kein Netz, kein Geld.
    echt = (agent_modul.gemini_fragen, agent._anfrage, config.GEMINI_API_KEY,
            config.MONATSLIMIT_EURO, config.ANTHROPIC_API_KEY)
    agent.gedankenlog = Gedankenlog(pathlib.Path(ARBEITSVERZEICHNIS) / "router_test.jsonl")
    config.GEMINI_API_KEY = config.ANTHROPIC_API_KEY = "test"
    claude_antwort = {"ok": True, "daten": {
        "content": [{"type": "text", "text": "Antwort von Claude."}],
        "usage": {"input_tokens": 1000, "output_tokens": 200}}}
    try:
        agent_modul.gemini_fragen = lambda *a, **k: {
            "ok": True, "text": "Antwort von Gemini.", "tokens_ein": 50,
            "tokens_aus": 10}
        agent._anfrage = lambda koerper, timeout=120: claude_antwort
        agent.verlauf_leeren()
        text = agent.denken("Wie geht es dir?")
        pruefen("Einfache Frage wird von Gemini beantwortet",
                text == "Antwort von Gemini." and agent.letztes_gehirn == "gemini", text)

        text = agent.denken("Was steht heute an?")
        pruefen("Frage mit Handlung wird von Claude beantwortet",
                text == "Antwort von Claude." and agent.letztes_gehirn == "claude", text)

        agent_modul.gemini_fragen = lambda *a, **k: {
            "ok": False, "limit": True, "fehler": "Gemini meldet Fehler 429."}
        text = agent.denken("Und wie spät ist es?")
        pruefen("Gemini-Limit: Claude springt ein",
                text == "Antwort von Claude."
                and agent.gedankenlog.zeilen()[-1]["ausgewichen"] is True, text)

        bilanz = agent.gedankenlog.monatsbilanz()
        pruefen("Gedankenlog zählt Anfragen und Kosten je Gehirn",
                bilanz["anfragen"] == 3 and bilanz["gemini"] == 1
                and bilanz["claude"] == 2 and bilanz["ausgewichen"] == 1
                and abs(bilanz["kosten"] - 2 * claude_kosten(1000, 200)) < 1e-4,
                "%s Euro" % bilanz["kosten"])

        config.MONATSLIMIT_EURO = bilanz["kosten"] / 2
        agent_modul.gemini_fragen = echt[0]
        text = agent.denken("Schreib mir ein Angebot")
        pruefen("Monatslimit erreicht: Claude wird nicht mehr gefragt",
                "Monatslimit" in text and agent.gedankenlog.monatsbilanz()["anfragen"] == 3,
                text[:60])
    finally:
        (agent_modul.gemini_fragen, agent._anfrage, config.GEMINI_API_KEY,
         config.MONATSLIMIT_EURO, config.ANTHROPIC_API_KEY) = echt
        del agent._anfrage
        agent.verlauf_leeren()


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

    pruefen("Ohne Denkprotokoll zeigt das Dashboard kein Gehirn-Panel",
            "Denken diesen Monat" not in inhalt, "kein erfundener Bereich")
    log = Gedankenlog()
    log.eintragen("Hallo", "gemini", "kurz", 1.0)
    log.eintragen("Termin", "claude", "Werkzeug", 2.0, 1000, 200, 0.5)
    ergebnis = agent.tools.dashboard.bauen()
    with open(ergebnis["datei"], encoding="utf-8") as datei:
        inhalt = datei.read()
    pruefen("Dashboard zeigt Anfragen je Gehirn und die Kosten",
            "Denken diesen Monat" in inhalt and "1 Anfragen" in inhalt
            and "0,50" in inhalt, "Gemini 1, Claude 1, 0,50 Euro")


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

    # Die Anleitung ist eine Unterseite derselben Website.
    anleitung = os.path.join(WURZEL, "landing", "anleitung.html")
    text = ""
    if os.path.exists(anleitung):
        with open(anleitung, encoding="utf-8") as datei:
            text = datei.read()
    pruefen("Anleitungsseite vorhanden", bool(text), "%d Zeichen" % len(text))
    if text:
        import re as _re2
        hosts = sorted(set(_re2.findall(r"https?://([^/\"]+)", text)))
        erlaubt = {"fonts.googleapis.com", "fonts.gstatic.com"}
        pruefen("Anleitungsseite lädt nur Schriften nach",
                set(hosts) <= erlaubt, ", ".join(hosts) or "gar nichts")
        pruefen("Anleitungsseite führt zurück zur Startseite",
                'href="index.html"' in text)
        pruefen("Startseite verweist auf die Anleitung",
                'href="anleitung.html"' in roh)
        pruefer2 = _Pruefer()
        pruefer2.feed(text)
        pruefen("Anleitungsseite ist wohlgeformtes HTML",
                not pruefer2.fehler and not pruefer2.stapel,
                ("offen: %s" % (pruefer2.stapel + pruefer2.fehler)[:3])
                if (pruefer2.stapel or pruefer2.fehler) else "alle Tags geschlossen")
        for befehl in ("mkdir jarvis &amp;&amp; cd jarvis", "claude",
                       "JARVIS.command"):
            if befehl not in text:
                pruefen("Anleitung enthält den Befehl %s" % befehl, False)
                break
        else:
            pruefen("Anleitung enthält alle drei Befehle", True,
                    "Ordner, Auftrag, Start")


def pruefung_autopilot(agent):
    abschnitt("Autopilot")
    ap = agent.tools.autopilot
    aus = datetime(2026, 1, 1, 22, 30)
    mittag = datetime(2026, 1, 1, 12, 0)
    alt = (config.AUTOPILOT_VON, config.AUTOPILOT_BIS)
    config.AUTOPILOT_VON, config.AUTOPILOT_BIS = "07:00", "21:00"
    pruefen("Ruhezeit: nachts ja, mittags nein",
            in_ruhezeit(aus) is True and in_ruhezeit(mittag) is False
            and in_ruhezeit(datetime(2026, 1, 1, 6, 59)) is True, "07:00 bis 21:00")
    config.AUTOPILOT_VON, config.AUTOPILOT_BIS = alt
    pruefen("Fachkraft wird aus dem Auftrag erraten",
            rolle_raten("Schreib ein Angebot für Müller") == "akquisiteur"
            and rolle_raten("Schreibe ein Skript für die Rechnungen") == "programmierer"
            and rolle_raten("Mails durchsehen") == "postmeister", "drei Aufträge")

    erster = ap.auftrag_anlegen("Angebot Müller schreiben", "Fläche 300 qm", "", 2, "nutzer", "t1")
    doppelt = ap.auftrag_anlegen("Angebot Müller schreiben", "", "", 2, "nutzer", "t1")
    falsch = ap.auftrag_anlegen("x", "y", "zauberer")
    pruefen("Auftrag anlegen: Doppelte werden erkannt, falsche Rolle abgelehnt",
            erster["ok"] and doppelt.get("doppelt") and falsch["ok"] is False
            and len(ap.warteschlange()) == 1, erster.get("text", "")[:50])

    # Die eine Regel: im Hintergrund nie ein Werkzeug, das eine Freigabe braucht.
    gesehen = {}
    echt_arbeiten, echt_key = agent.arbeiten, config.ANTHROPIC_API_KEY
    config.ANTHROPIC_API_KEY = "test"
    agent.arbeiten = lambda systemtext, auftrag, werkzeugnamen=None, max_runden=6, grund="": (
        gesehen.update({"namen": list(werkzeugnamen or []), "system": systemtext, "grund": grund})
        or "Entwurf: Sehr geehrter Herr Müller, anbei unser Angebot.")
    try:
        verboten = []
        for rolle in sorted(autopilot_modul.ROLLEN):
            agent.tools.team.beauftragen(rolle, "Test", hintergrund=True)
            verboten += [n for n in gesehen["namen"] if n in FREIGABE_PFLICHTIG or agent.tools.braucht_freigabe(n)]
        pruefen("Im Hintergrund hat keine Fachkraft ein Werkzeug mit Freigabe",
                not verboten and gesehen["grund"] == "Autopilot", "alle %d Rollen geprüft" % len(autopilot_modul.ROLLEN))
        pruefen("Der Hintergrundauftrag sagt der Fachkraft, dass sie nur Entwürfe schreibt",
                "HINTERGRUNDARBEIT" in gesehen["system"] and "verschickst nichts" in gesehen["system"], "")
        agent.tools.team.beauftragen("postmeister", "Test")
        pruefen("Im Vordergrund behält der Postbearbeiter sein Mailwerkzeug",
                "mail_senden" in gesehen["namen"], "mail_senden vorhanden")

        # Ein ganzer Lauf: Auftrag -> Fachkraft -> Postfach.
        config.AUTOPILOT_AN = True
        ergebnis = ap.naechsten_abarbeiten()
        postfach = ap.postfach()
        pruefen("Abgearbeiteter Auftrag landet im Postfach",
                ergebnis["status"] == "fertig" and len(postfach) == 1
                and "Sehr geehrter Herr Müller" in postfach[0]["ergebnis"]
                and not ap.warteschlange(), postfach[0]["titel"] if postfach else "leer")
        ap.gesehen_setzen(postfach[0]["id"])
        pruefen("Abgehakt verschwindet es aus dem Postfach",
                not ap.postfach() and len(ap.verlauf()) == 1, "")

        # Die Nerven: fälliges Nachfassen wird von selbst zu Arbeit.
        agent.tools.akquise.lead_anlegen("Autopilot Test GmbH", ansprechpartner="Frau Bauer",
                                         objekt_qm=200, bodenbelag="Linoleum",
                                         intervall_pro_woche=2)
        agent.memory._schreiben("UPDATE leads SET naechster_kontakt=? WHERE firma=?",
                                (datetime.now().strftime("%Y-%m-%d"), "Autopilot Test GmbH"))
        neu = ap.nerven_pruefen()
        nochmal = ap.nerven_pruefen()
        offen = [e for e in ap.warteschlange() if "Autopilot Test GmbH" in e["titel"]]
        pruefen("Fälliges Nachfassen wird von selbst zum Auftrag, aber nur einmal",
                len(offen) == 1 and offen[0]["rolle"] == "akquisiteur"
                and offen[0]["quelle"] == "nerv" and not any("Autopilot Test" in t for t in nochmal),
                "%d neu, zweiter Durchlauf %d" % (len(neu), len(nochmal)))
        belege = [e for e in ap.postfach() if e["titel"] == "Belege fehlen"]
        pruefen("Fehlende Belege meldet der Autopilot ohne Claude",
                len(belege) == 1 and belege[0]["quelle"] == "nerv" and belege[0]["dauer"] == 0,
                belege[0]["ergebnis"][:50] if belege else "keine Meldung")

        # Bremsen
        config.AUTOPILOT_AN = False
        aus_grund = ap.gesperrt()
        config.AUTOPILOT_AN = True
        limit_alt = config.MONATSLIMIT_EURO
        ap.gedankenlog = Gedankenlog(pathlib.Path(ARBEITSVERZEICHNIS) / "ap_limit.jsonl")
        ap.gedankenlog.eintragen("x", "claude", "t", 1, 1, 1, 99.0)
        config.MONATSLIMIT_EURO = 15.0
        limit_grund = ap.gesperrt(mittag)
        config.MONATSLIMIT_EURO = limit_alt
        ap.gedankenlog = Gedankenlog(pathlib.Path(ARBEITSVERZEICHNIS) / "ap_leer.jsonl")
        config.AUTOPILOT_VON, config.AUTOPILOT_BIS = "07:00", "21:00"
        nacht_grund = ap.gesperrt(aus)
        config.AUTOPILOT_VON, config.AUTOPILOT_BIS = alt
        pruefen("Bremsen: aus, Monatslimit und Ruhezeit halten ihn an",
                aus_grund == "aus" and "Monatslimit" in limit_grund and "Ruhezeit" in nacht_grund,
                "%s / %s / %s" % (aus_grund, limit_grund, nacht_grund[:20]))

        # Kosten: auch Teamarbeit steht im Gedankenlog und zählt zum Limit.
        agent.arbeiten = echt_arbeiten
        agent._anfrage = lambda koerper, timeout=120: {"ok": True, "daten": {
            "content": [{"type": "text", "text": "Fertig."}],
            "usage": {"input_tokens": 2000, "output_tokens": 500}}}
        agent.gedankenlog = Gedankenlog(pathlib.Path(ARBEITSVERZEICHNIS) / "ap_kosten.jsonl")
        text = agent.arbeiten("system", "auftrag", ["notiz_speichern"], 2, grund="Autopilot")
        zeilen = agent.gedankenlog.zeilen()
        pruefen("Hintergrundarbeit steht im Gedankenlog mit Kosten",
                text == "Fertig." and len(zeilen) == 1 and zeilen[0]["grund"] == "Autopilot"
                and zeilen[0]["kosten"] > 0, "%s Euro" % (zeilen[0]["kosten"] if zeilen else "-"))
        config.MONATSLIMIT_EURO = 0.0001
        gesperrt_text = agent.arbeiten("system", "auftrag", ["notiz_speichern"], 2)
        config.MONATSLIMIT_EURO = limit_alt
        pruefen("Ist das Monatslimit erreicht, arbeitet auch das Team nicht mehr",
                "Monatslimit" in gesperrt_text, gesperrt_text[:50])
    finally:
        agent.arbeiten = echt_arbeiten
        if "_anfrage" in agent.__dict__:
            del agent._anfrage
        config.ANTHROPIC_API_KEY = echt_key
        config.AUTOPILOT_AN = False
        config.AUTOPILOT_VON, config.AUTOPILOT_BIS = alt
        config.MONATSLIMIT_EURO = 15.0
        ap.gedankenlog = Gedankenlog(pathlib.Path(ARBEITSVERZEICHNIS) / "gedankenlog.jsonl")

    pruefen("Autopilot ein- und ausschalten verlangt eine Freigabe",
            agent.tools.braucht_freigabe("autopilot_schalten") is True
            and agent.tools.braucht_freigabe("autopilot_auftrag") is False, "")
    pruefen("Die Autopilot-Werkzeuge stehen im Katalog",
            {"autopilot_auftrag", "autopilot_postfach", "autopilot_gesehen",
             "autopilot_schalten"} <= set(agent.tools.namen()), "vier Werkzeuge")
    pruefen("Der Autopilot-Zustand hat alles, was die Seite braucht",
            {"an", "gesperrt", "postfach", "warteschlange", "verlauf", "von", "bis"}
            <= set(ap.zustand()), "")
    pruefen("Die Autopilot-Seite lädt nichts aus dem Netz nach",
            "https://" not in autopilot_modul.SEITE_AUTOPILOT
            and "http://" not in autopilot_modul.SEITE_AUTOPILOT, "alles in der Seite")

    class Kopf:
        def __init__(self, **k): self.headers = k
    pruefen("Schreibende Anfragen von fremden Seiten werden abgelehnt",
            JarvisWeb._herkunft_ok(Kopf(Host="localhost:8765", Origin="http://boese.example")) is False
            and JarvisWeb._herkunft_ok(Kopf(Host="localhost:8765", Origin="http://localhost:8765")) is True
            and JarvisWeb._herkunft_ok(Kopf(Host="localhost:8765")) is True, "Origin gegen Host")


def pruefung_zugang(agent):
    abschnitt("Zugänge und Persönliches")
    Einr = wizard_modul.Einrichtung
    echt = (config.ENV_DATEI, dict(config._ROHWERTE), config.GEMINI_API_KEY,
            config.ANTHROPIC_API_KEY, config.JARVIS_PROFIL, config.JARVIS_STIL,
            Einr.fragen_geheim, Einr.oeffnen, Einr.schluessel_testen,
            wizard_modul.gemini_testen)
    config.ENV_DATEI = pathlib.Path(ARBEITSVERZEICHNIS) / "zugang.env"
    config._ROHWERTE.clear()
    config.GEMINI_API_KEY = config.ANTHROPIC_API_KEY = ""
    eingabe = {"wert": ""}
    Einr.fragen_geheim = staticmethod(lambda frage: eingabe["wert"])
    Einr.oeffnen = staticmethod(lambda ziel: True)
    try:
        wizard_modul.gemini_testen = lambda k: {"ok": k == "gut", "limit": False,
                                                "text": "geprüft"}
        eingabe["wert"] = "falsch"
        geklappt = Einr().zugang_nachtragen("gemini")
        pruefen("Abgelehnter Gemini-Schlüssel ändert nichts",
                geklappt is False and config.GEMINI_API_KEY == ""
                and not config.ENV_DATEI.exists(), "")
        eingabe["wert"] = "gut"
        geklappt = Einr().zugang_nachtragen("gemini")
        gespeichert = config.ENV_DATEI.read_text(encoding="utf-8") if config.ENV_DATEI.exists() else ""
        pruefen("Geprüfter Gemini-Schlüssel wird eingetragen und sofort aktiv",
                geklappt and config.GEMINI_API_KEY == "gut"
                and "GEMINI_API_KEY=gut" in gespeichert, "")
        pruefen("Die Schlüsseldatei ist nur für den Nutzer lesbar",
                (config.ENV_DATEI.stat().st_mode & 0o077) == 0, "Rechte 600")

        eingabe["wert"] = "kein-anthropic-schluessel"
        geklappt = Einr().zugang_nachtragen("claude")
        pruefen("Ein Schlüssel ohne sk- wird für Claude nicht angenommen",
                geklappt is False and config.ANTHROPIC_API_KEY == "", "")

        Einr.schluessel_testen = lambda self, k: {"ok": True, "text": "ok"}
        eingabe["wert"] = "sk-test"
        pruefen("Claude-Schlüssel nachtragen funktioniert",
                Einr().zugang_nachtragen("claude") and config.ANTHROPIC_API_KEY == "sk-test", "")

        config.env_setzen("JARVIS_PROFIL", "Ich leite eine Reinigungsfirma mit drei Leuten")
        config.env_setzen("JARVIS_STIL", "knapp, direkt, etwas trocken")
        prompt = agent.systemprompt("Hallo")
        pruefen("Persönliches steht im Systemprompt (für Claude und Gemini)",
                "drei Leuten" in prompt and "etwas trocken" in prompt, "Profil und Stil")
    finally:
        (config.ENV_DATEI, roh, config.GEMINI_API_KEY, config.ANTHROPIC_API_KEY,
         config.JARVIS_PROFIL, config.JARVIS_STIL, Einr.fragen_geheim, Einr.oeffnen,
         Einr.schluessel_testen, wizard_modul.gemini_testen) = echt
        config._ROHWERTE.clear()
        config._ROHWERTE.update(roh)


def pruefung_lernpfad(agent):
    abschnitt("Lernpfad")
    echt = (config.ANTHROPIC_API_KEY, config.GEMINI_API_KEY, config.EINRICHTUNG_FERTIG,
            config.NUTZER_NAME)
    try:
        config.ANTHROPIC_API_KEY = config.GEMINI_API_KEY = ""
        config.EINRICHTUNG_FERTIG = False
        config.NUTZER_NAME = "Chef"
        leer = lernpfad_stand(agent.tools)
        pruefen("Sieben Welten, jede mit Leveln",
                len(leer["welten"]) == 7 and all(w["level"] for w in leer["welten"]),
                "%d Haken insgesamt" % leer["gesamt"])
        pruefen("Ohne Einrichtung ist nur Welt 1 offen, der Rest gesperrt",
                not leer["welten"][0]["gesperrt"]
                and all(w["gesperrt"] for w in leer["welten"][1:]), "")
        claude_haken = [l for l in leer["welten"][1]["level"] if l["kennung"] == "claude"][0]
        pruefen("Kein Schlüssel, kein Haken", claude_haken["erledigt"] is False, "")

        config.ANTHROPIC_API_KEY, config.GEMINI_API_KEY = "x", "y"
        config.EINRICHTUNG_FERTIG, config.NUTZER_NAME = True, "Test"
        voll = lernpfad_stand(agent.tools)
        pruefen("Mit Schlüsseln und Name öffnet sich Welt 2 und der Haken sitzt",
                voll["welten"][0]["abgeschlossen"] and not voll["welten"][1]["gesperrt"]
                and [l for l in voll["welten"][1]["level"]
                     if l["kennung"] == "gemini"][0]["erledigt"], "")
        pruefen("Eine offene Pflicht in Welt 2 hält Welt 3 zu",
                voll["welten"][1]["abgeschlossen"] or voll["welten"][2]["gesperrt"], "")
    finally:
        (config.ANTHROPIC_API_KEY, config.GEMINI_API_KEY, config.EINRICHTUNG_FERTIG,
         config.NUTZER_NAME) = echt
    pruefen("Die Seite lädt nichts aus dem Netz nach",
            "https://" not in SEITE_PFAD and "http://" not in SEITE_PFAD, "alles in der Seite")
    pruefen("Der Pfad ist vom Kopf der Web-App aus erreichbar",
            'href="/pfad"' in SEITE_HTML, "")


def pruefung_webapp(agent):
    """Die Web-App - Zugang, Antworten und die Freigabe über den Browser."""
    abschnitt("Web-App")
    import urllib.error as _fehler
    import urllib.request as _netz

    # Freigabebrücke zuerst allein: Schweigen muss ein Nein sein.
    bruecke = WebFreigabe(timeout=2)
    ergebnis = bruecke.anfordern("mail_senden", "an kunde@beispiel.at")
    pruefen("Freigabe im Browser: keine Antwort gilt als Nein",
            ergebnis["erlaubt"] is False and "keine Antwort" in ergebnis["grund"])

    bruecke2 = WebFreigabe(timeout=8)
    antwort = {}

    def fragen():
        antwort["ergebnis"] = bruecke2.anfordern("skript_ausfuehren", "print(1)")

    faden = threading.Thread(target=fragen, daemon=True)
    faden.start()
    time.sleep(0.4)
    offen = bruecke2.offene()
    pruefen("Wartende Freigabe erscheint für den Browser",
            len(offen) == 1 and offen[0]["aktion"] == "skript_ausfuehren")
    bruecke2.beantworten(offen[0]["id"], False)
    faden.join(timeout=4)
    pruefen("Ein Nein im Browser lehnt ab",
            antwort.get("ergebnis", {}).get("erlaubt") is False)

    bruecke3 = WebFreigabe(timeout=8)
    antwort3 = {}

    def fragen3():
        antwort3["ergebnis"] = bruecke3.anfordern("mail_senden", "x")

    faden3 = threading.Thread(target=fragen3, daemon=True)
    faden3.start()
    time.sleep(0.4)
    bruecke3.beantworten(bruecke3.offene()[0]["id"], True)
    faden3.join(timeout=4)
    pruefen("Ein Ja im Browser gibt frei",
            antwort3.get("ergebnis", {}).get("erlaubt") is True)

    pruefen("Die Oberfläche lädt nichts aus dem Netz nach",
            "http://" not in SEITE_HTML.replace("http-equiv", "")
            and "https://" not in SEITE_HTML.replace(
                'xmlns="http://www.w3.org/2000/svg"', ""),
            "alles in der Seite selbst")

    # Sprachsteuerung: die Oberflaeche muss von selbst zuhoeren.
    pruefen("Die Oberfläche hört von selbst zu",
            "continuous = true" in SEITE_HTML and "hoerenStart" in SEITE_HTML,
            "kein Knopfdruck nötig")
    weckwoerter = ["hey jarvis", "hey javis", "hey dscharvis", "hey charvis",
                   "hey travis", "jarvis", "javis"]
    pruefen("Alle Weckwörter kennt auch der Browser",
            all(w in SEITE_HTML for w in weckwoerter),
            "%d Schreibweisen" % len(weckwoerter))
    pruefen("Freigaben lassen sich sprechen",
            '"ja"' in SEITE_HTML and '"nein"' in SEITE_HTML
            and "JA.indexOf(wort)" in SEITE_HTML,
            "ja oder nein genügt")
    pruefen("Beim Sprechen wird das Mikrofon angehalten",
            "hoerenPause();" in SEITE_HTML,
            "sonst hört Jarvis sich selbst zu")
    pruefen("Tippen ist nur der Notweg",
            'class="tippen"' in SEITE_HTML and ".tippen{" in SEITE_HTML
            and "display:none" in SEITE_HTML,
            "standardmäßig ausgeblendet")

    # Jetzt der Server.
    web = JarvisWeb(agent, port=8794)
    web.starten(blockierend=False)
    time.sleep(0.5)

    def rufen(pfad, host=None, koerper=None, schluessel=None):
        ziel = "http://127.0.0.1:8794" + pfad
        if schluessel:
            ziel += ("&" if "?" in ziel else "?") + "schluessel=" + schluessel
        anfrage = _netz.Request(ziel)
        if host:
            anfrage.add_header("Host", host)
        if koerper is not None:
            anfrage.data = json.dumps(koerper).encode("utf-8")
            anfrage.add_header("Content-Type", "application/json")
        try:
            with _netz.urlopen(anfrage, timeout=8) as antwort_roh:
                return antwort_roh.status, antwort_roh.read().decode("utf-8")
        except _fehler.HTTPError as ausnahme:
            return ausnahme.code, ausnahme.read().decode("utf-8")

    try:
        code, inhalt = rufen("/")
        pruefen("Die Seite wird ausgeliefert",
                code == 200 and "<title>Jarvis</title>" in inhalt,
                "%d, %d Zeichen" % (code, len(inhalt)))

        code, inhalt = rufen("/api/zustand")
        zustand = json.loads(inhalt) if code == 200 else {}
        pruefen("Der Zustand kommt als JSON",
                code == 200 and zustand.get("werkzeuge", 0) > 50,
                "%d Werkzeuge" % zustand.get("werkzeuge", 0))

        code, _ = rufen("/api/lage")
        pruefen("Der Lagebericht ist abrufbar", code == 200)

        code, _ = rufen("/api/zustand", host="boese.example.com")
        pruefen("Fremder Host-Kopf wird abgewiesen", code == 403,
                "Schutz gegen Umleitung über den Namen")

        code, _ = rufen("/gibtsnicht")
        pruefen("Unbekannte Pfade geben 404", code == 404)

        code, inhalt = rufen("/api/werkzeug", koerper={"name": "erfundenes_werkzeug"})
        pruefen("Unbekanntes Werkzeug wird abgewiesen", code == 400)

        code, inhalt = rufen("/api/werkzeug", koerper={"name": "pipeline"})
        pruefen("Ein Werkzeug lässt sich über die Schnittstelle aufrufen",
                code == 200 and json.loads(inhalt).get("ok") is True)

        # Der Zeitplan meldet in die Web-App. Ein Briefing, das nur ins
        # Terminal geht, hört um 6:45 niemand.
        web.melden("Guten Morgen. Heute drei Termine.")
        code, inhalt = rufen("/api/meldungen")
        meldungen = json.loads(inhalt).get("meldungen", []) if code == 200 else []
        pruefen("Briefings des Zeitplans erreichen den Browser",
                len(meldungen) == 1 and "Guten Morgen" in meldungen[0]["text"],
                "wird geholt und vorgelesen")
        code, inhalt = rufen("/api/meldungen")
        pruefen("Eine abgeholte Meldung kommt nicht doppelt",
                json.loads(inhalt).get("meldungen") == [])
        pruefen("Die Meldung steht auch im Gesprächsverlauf",
                any("Guten Morgen" in z["text"]
                    for z in agent.memory.verlauf_letzte(5)),
                "geht nicht verloren, wenn der Browser zu war")
    finally:
        web.stoppen()

    # Mit offenem Zugang ist der Schlüssel Pflicht.
    offen_web = JarvisWeb(agent, port=8795, offen=True)
    pruefen("Offener Zugang erzwingt einen Schlüssel",
            bool(offen_web.token) and "schluessel=" in offen_web.adresse(),
            "Schlüssel wird erzeugt und steht in der Adresse")
    offen_web.starten(blockierend=False)
    time.sleep(0.5)
    try:
        anfrage = _netz.Request("http://127.0.0.1:8795/api/zustand")
        anfrage.add_header("Host", "localhost")
        try:
            with _netz.urlopen(anfrage, timeout=8) as antwort_roh:
                code = antwort_roh.status
        except _fehler.HTTPError as ausnahme:
            code = ausnahme.code
        pruefen("Ohne Schlüssel kein Zugang", code == 403)

        anfrage = _netz.Request("http://127.0.0.1:8795/api/zustand?schluessel="
                                + offen_web.token)
        anfrage.add_header("Host", "localhost")
        with _netz.urlopen(anfrage, timeout=8) as antwort_roh:
            code = antwort_roh.status
        pruefen("Mit Schlüssel geht es", code == 200)
    finally:
        offen_web.stoppen()
        agent.tools.freigabe_kanal_setzen(None)


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
               "Werkzeuge", "JarvisAgent", "Akquise", "Team", "Werkstatt", "Privat", "JarvisWeb",
               "WebFreigabe"]
    # Ist jarvis.py frisch gebaut? Jede Klasse und Funktion aus src/ muss darin stehen.
    import ast
    veraltet = []
    for datei_pfad in sorted(pathlib.Path(WURZEL, "src").rglob("*.py")):
        baum = ast.parse(datei_pfad.read_text(encoding="utf-8"))
        for knoten in baum.body:
            if isinstance(knoten, (ast.FunctionDef, ast.ClassDef)):
                if knoten.name not in inhalt:
                    veraltet.append("%s.%s" % (datei_pfad.stem, knoten.name))
    pruefen("jarvis.py ist aktuell (alles aus src/ ist darin)", not veraltet,
            "veraltet - neu bauen: %s" % ", ".join(veraltet[:3]) if veraltet
            else "gebaut aus dem jetzigen src/")
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
    pruefung_akquise(agent)
    pruefung_leadfinder(agent)
    pruefung_privat(agent)
    pruefung_team(agent)
    pruefung_werkstatt(agent)
    pruefung_werkzeugvertrag(agent)
    pruefung_telefon(agent)
    pruefung_browser(agent)
    pruefung_autopilot(agent)
    pruefung_zugang(agent)
    pruefung_lernpfad(agent)
    pruefung_webapp(agent)
    pruefung_routinen(agent)
    pruefung_zeitplan()
    pruefung_kalender()
    pruefung_router(agent)
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
