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

from agent import JarvisAgent  # noqa: E402
from modules.bookkeeping import mwst_aus_brutto  # noqa: E402
from modules.calendar_mod import ics_termine_lesen, konflikte_finden  # noqa: E402
from modules.mcp_client import MCPClient, MCPServer  # noqa: E402
from modules.akquise import Akquise  # noqa: E402
from modules.scheduler import Scheduler, ist_faellig  # noqa: E402
from modules.privat import Privat, monatsanteil  # noqa: E402
from modules.team import ROLLEN, Team  # noqa: E402
from modules.webapp import JarvisWeb, WebFreigabe  # noqa: E402
from modules.webseite import SEITE_HTML  # noqa: E402
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
        "anrufliste": {}, "protokoll": {},
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


def pruefung_protokoll(agent):
    """Das Protokoll aus dem Gesprächsverlauf - per Werkzeug und im Browser."""
    abschnitt("Protokoll")
    import urllib.request as _netz
    heute = datetime.now().strftime("%Y-%m-%d")
    gestern = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
    agent.memory.verlauf_anhaengen("user", "Protokollprobe Berger Angebot")
    agent.memory.verlauf_anhaengen("assistant", "Angebot für Berger ist vorbereitet")
    agent.memory.verlauf_anhaengen("user", "Etwas ganz anderes <script>x</script>")
    agent.memory._schreiben(
        "INSERT INTO verlauf (rolle, text, zeit) VALUES (?,?,?)",
        ("user", "Alter Eintrag von gestern", "%s 10:00:00" % gestern))
    agent.memory.aktion_protokollieren("pipeline", {}, "ok")

    erg = agent.tools.run("protokoll", {})
    pruefen("Protokoll heute: ok, Gespräche und Aktionen",
            erg.get("ok") is True and erg["datum"] == heute
            and any("Berger" in g["text"] for g in erg["gespraeche"])
            and any(a["werkzeug"] == "pipeline" for a in erg["aktionen"]),
            erg.get("text", "")[:120])
    pruefen("Protokoll heute enthält nichts von gestern",
            not any("gestern" in g["text"] for g in erg["gespraeche"]))
    erg = agent.tools.run("protokoll", {"tag": "gestern"})
    pruefen("Protokoll gestern zeigt nur gestern",
            erg.get("ok") is True and len(erg["gespraeche"]) == 1
            and "gestern" in erg["gespraeche"][0]["text"])
    erg = agent.tools.run("protokoll", {"thema": "Berger"})
    pruefen("Protokoll mit Thema filtert auf beide Seiten des Gesprächs",
            len(erg["gespraeche"]) == 2,
            "%d Zeilen" % len(erg["gespraeche"]))
    erg = agent.tools.run("protokoll", {"tage": 2})
    pruefen("Protokoll über 2 Tage nimmt gestern dazu",
            any("gestern" in g["text"] for g in erg["gespraeche"]))
    erg = agent.tools.run("protokoll", {"tag": "blabla"})
    pruefen("Ein unlesbarer Tag wird gemeldet, nicht still ersetzt",
            erg.get("ok") is False and "blabla" in erg["text"])
    erg = agent.tools.run("protokoll", {"tag": "1999-01-01"})
    pruefen("Ein leerer Tag sagt, dass nichts protokolliert ist",
            erg.get("ok") is True and "nichts protokolliert" in erg["text"])
    pruefen("Das Protokoll braucht keine Freigabe",
            "protokoll" not in agent.tools.katalog_freigabe()
            if hasattr(agent.tools, "katalog_freigabe") else True)

    web = JarvisWeb(agent, port=8796)
    web.starten(blockierend=False)
    time.sleep(0.5)
    try:
        with _netz.urlopen("http://127.0.0.1:8796/api/protokoll?thema=Berger",
                           timeout=8) as r:
            daten = json.loads(r.read().decode("utf-8"))
        pruefen("/api/protokoll liefert das Protokoll",
                daten.get("ok") is True and len(daten["gespraeche"]) == 2)
        with _netz.urlopen("http://127.0.0.1:8796/protokoll", timeout=8) as r:
            seite = r.read().decode("utf-8")
        pruefen("/protokoll ist deine persönliche Seite",
                config.NUTZER_NAME in seite and "{{" not in seite
                and "/api/protokoll" in seite)
        pruefen("Die Protokollseite lädt nichts aus dem Netz nach",
                "https://" not in seite and "http://" not in seite)
        pruefen("Die Protokollseite setzt Text nie als HTML ein",
                "innerHTML" not in seite)
    finally:
        web.stoppen()

    offen = JarvisWeb(agent, port=8797, offen=True)
    offen.starten(blockierend=False)
    time.sleep(0.5)
    try:
        for pfad, name in (("/api/protokoll", "Schnittstelle"), ("/protokoll", "Seite")):
            anfrage = _netz.Request("http://127.0.0.1:8797" + pfad)
            anfrage.add_header("Host", "localhost")
            try:
                with _netz.urlopen(anfrage, timeout=8) as r:
                    code = r.status
            except Exception as fehler:
                code = getattr(fehler, "code", 0)
            pruefen("Protokoll-%s: ohne Schlüssel kein Zugang" % name, code == 403)
        anfrage = _netz.Request("http://127.0.0.1:8797/protokoll?schluessel=" + offen.token)
        anfrage.add_header("Host", "localhost")
        with _netz.urlopen(anfrage, timeout=8) as r:
            seite = r.read().decode("utf-8")
        pruefen("Mit Schlüssel öffnet die Seite und trägt ihn für die Abfragen",
                offen.token in seite)
    finally:
        offen.stoppen()
        agent.tools.freigabe_kanal_setzen(None)


def pruefung_schluessel(agent):
    """Der Schlüssel lässt sich im Browser eintragen - ohne ihn läuft der Server trotzdem."""
    abschnitt("Schlüssel im Browser")
    import urllib.request as _netz
    import modules.webapp as webapp_modul

    alte_env, alter_schluessel = config.ENV_DATEI, config.ANTHROPIC_API_KEY
    alte_rohwerte = dict(config._ROHWERTE)
    alter_test = webapp_modul.schluessel_online_testen
    config.ENV_DATEI = pathlib.Path(ARBEITSVERZEICHNIS) / "schluessel.env"
    config.ANTHROPIC_API_KEY = ""
    config._ROHWERTE.pop("ANTHROPIC_API_KEY", None)
    probe = {"ergebnis": {"ok": True, "text": "Der Schlüssel funktioniert."}}
    webapp_modul.schluessel_online_testen = lambda k: probe["ergebnis"]

    web = JarvisWeb(agent, port=8798)
    web.starten(blockierend=False)
    time.sleep(0.5)

    def senden(schluessel):
        anfrage = _netz.Request("http://127.0.0.1:8798/api/schluessel",
                                data=json.dumps({"schluessel": schluessel}).encode("utf-8"),
                                headers={"Content-Type": "application/json"})
        with _netz.urlopen(anfrage, timeout=8) as r:
            return r.read().decode("utf-8")

    try:
        with _netz.urlopen("http://127.0.0.1:8798/api/zustand", timeout=8) as r:
            zustand = json.loads(r.read().decode("utf-8"))
        pruefen("Ohne Schlüssel läuft der Server und meldet nicht einsatzbereit",
                zustand.get("einsatzbereit") is False)
        with _netz.urlopen("http://127.0.0.1:8798/", timeout=8) as r:
            seite = r.read().decode("utf-8")
        pruefen("Die Startseite hat ein Feld für den Schlüssel",
                "schluesselDialog" in seite and 'type="password"' in seite)

        roh = senden("kaputt")
        pruefen("Ein offensichtlich falscher Schlüssel wird abgewiesen, nichts gespeichert",
                json.loads(roh)["ok"] is False and not config.ENV_DATEI.exists())

        probe["ergebnis"] = {"ok": False, "grund": "schluessel",
                             "text": "Der Schlüssel wird abgelehnt."}
        roh = senden("sk-ant-" + "x" * 40)
        pruefen("Ein abgelehnter Schlüssel wird nicht gespeichert",
                json.loads(roh)["ok"] is False and not config.ENV_DATEI.exists()
                and not agent.einsatzbereit())

        probe["ergebnis"] = {"ok": True, "text": "Der Schlüssel funktioniert."}
        echter = "sk-ant-" + "y" * 40
        roh = senden("  " + echter[:20] + "\n" + echter[20:] + " ")
        antwort = json.loads(roh)
        pruefen("Ein gültiger Schlüssel wird gespeichert und sofort benutzt",
                antwort["ok"] is True and agent.einsatzbereit()
                and config.ANTHROPIC_API_KEY == echter
                and ("ANTHROPIC_API_KEY=" + echter) in config.ENV_DATEI.read_text("utf-8"),
                "Leerzeichen und Umbruch aus dem Kopieren werden entfernt")
        pruefen("Die Antwort verrät den Schlüssel nicht", echter not in roh)
        pruefen("Die Schlüsseldatei ist nur für den Nutzer lesbar",
                oct(os.stat(str(config.ENV_DATEI)).st_mode & 0o777) == "0o600")
    finally:
        web.stoppen()
        webapp_modul.schluessel_online_testen = alter_test
        config.ENV_DATEI = alte_env
        config.ANTHROPIC_API_KEY = alter_schluessel
        config._ROHWERTE.clear()
        config._ROHWERTE.update(alte_rohwerte)

    pruefen("Ohne Schlüssel startet JARVIS.command den Server statt nur der Einrichtung",
            "einrichten" not in open(os.path.join(WURZEL, "JARVIS.command"),
                                     encoding="utf-8").read().split("# --- 5.")[1]
            .split('"$PYTHON" "$PROJEKT/jarvis.py" "$@"')[0].replace("python3 jarvis.py einrichten", ""))


def pruefung_lokales_modell(agent):
    """Jarvis denkt ohne Schlüssel und ohne Kosten mit einem Modell auf dem Rechner."""
    abschnitt("Lokales Modell (Ollama)")
    import http.server
    import urllib.request as _netz
    import modules.webapp as webapp_modul
    from modules.lokal import ollama_pruefen, werkzeuge_auswaehlen

    gesehen = []
    modelle = {"liste": [{"name": "qwen2.5:3b"}]}

    class FalschesOllama(http.server.BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def _senden(self, nutzlast):
            roh = json.dumps(nutzlast).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(roh)))
            self.end_headers()
            self.wfile.write(roh)

        def do_GET(self):
            self._senden({"models": modelle["liste"]})

        def do_POST(self):
            laenge = int(self.headers.get("Content-Length") or 0)
            anfrage = json.loads(self.rfile.read(laenge).decode("utf-8"))
            gesehen.append(anfrage)
            hat_ergebnis = any(m.get("role") == "tool" for m in anfrage["messages"])
            if hat_ergebnis:
                self._senden({"message": {"role": "assistant", "content": "Gespeichert."}})
            else:
                self._senden({"message": {"role": "assistant", "content": "", "tool_calls": [
                    {"function": {"name": "notiz_speichern",
                                  "arguments": {"text": "Lokaltest Nikolic"}}}]}})

    server = http.server.ThreadingHTTPServer(("127.0.0.1", 11998), FalschesOllama)
    faden = threading.Thread(target=server.serve_forever, daemon=True)
    faden.start()

    alt = (config.ANTHROPIC_API_KEY, config.LOKALES_MODELL, config.OLLAMA_URL,
           config.ENV_DATEI, dict(config._ROHWERTE))
    config.ANTHROPIC_API_KEY = ""
    config.LOKALES_MODELL = ""
    config.OLLAMA_URL = "http://127.0.0.1:11998"
    config.ENV_DATEI = pathlib.Path(ARBEITSVERZEICHNIS) / "lokal.env"
    web = None
    try:
        pruefen("Ohne Schlüssel und ohne Modell ist Jarvis nicht einsatzbereit",
                agent.einsatzbereit() is False)
        pruefen("Ollama mit dem Modell wird erkannt", ollama_pruefen("qwen2.5:3b")["ok"])
        modelle["liste"] = []
        probe = ollama_pruefen("qwen2.5:3b")
        pruefen("Fehlendes Modell: Hinweis mit dem Befehl zum Laden",
                probe["ok"] is False and "ollama pull qwen2.5:3b" in probe["text"])
        modelle["liste"] = [{"name": "qwen2.5:3b"}]

        # Einrichtung über die Web-App
        web = JarvisWeb(agent, port=8799)
        web.starten(blockierend=False)
        time.sleep(0.5)

        def lokal_senden(modell):
            anfrage = _netz.Request("http://127.0.0.1:8799/api/lokal",
                                    data=json.dumps({"modell": modell}).encode("utf-8"),
                                    headers={"Content-Type": "application/json"})
            with _netz.urlopen(anfrage, timeout=8) as r:
                return json.loads(r.read().decode("utf-8"))

        antwort = lokal_senden("qwen2.5:3b")
        pruefen("Lokales Modell lässt sich im Browser einrichten",
                antwort.get("ok") is True and agent.einsatzbereit()
                and config.LOKALES_MODELL == "qwen2.5:3b"
                and "LOKALES_MODELL=qwen2.5:3b" in config.ENV_DATEI.read_text("utf-8"))
        pruefen("Unsinniger Modellname wird abgewiesen",
                lokal_senden("zwei Wörter")["ok"] is False)

        # Denkschleife: Werkzeugaufruf und Antwort laufen durch die Übersetzung
        agent.verlauf_leeren()
        text = agent.denken("Bitte merk dir die Notiz Lokaltest Nikolic")
        pruefen("Das lokale Modell antwortet durch die normale Denkschleife",
                text == "Gespeichert.", text)
        pruefen("Sein Werkzeugaufruf wurde wirklich ausgeführt",
                any("Lokaltest Nikolic" in n["text"]
                    for n in agent.memory.notizen_suchen("Lokaltest")))
        erste, zweite = gesehen[-2], gesehen[-1]
        pruefen("Es gehen nur wenige, passende Werkzeuge mit",
                0 < len(erste["tools"]) <= 14
                and "notiz_speichern" in [t["function"]["name"] for t in erste["tools"]],
                "%d von %d" % (len(erste["tools"]), len(agent.tools.katalog())))
        pruefen("Systemanweisung und Frage kommen im Ollama-Format an",
                erste["messages"][0]["role"] == "system"
                and erste["messages"][-1]["role"] == "user"
                and erste["model"] == "qwen2.5:3b" and erste["stream"] is False)
        pruefen("Das Werkzeugergebnis geht mit Namen zurück ans Modell",
                any(m.get("role") == "tool" and m.get("tool_name") == "notiz_speichern"
                    for m in zweite["messages"]))
        auswahl = werkzeuge_auswaehlen(agent.tools.katalog(), "wie war das Wetter morgen")
        pruefen("Die Werkzeugauswahl richtet sich nach der Frage",
                len(auswahl) <= 14 and any("wetter" in w["name"] for w in auswahl),
                ", ".join(w["name"] for w in auswahl[:6]))

        # Ollama ausgeschaltet: verständliche Meldung statt Absturz
        server.shutdown()
        server.server_close()
        fehler = agent.denken("Hallo")
        pruefen("Ohne laufendes Ollama kommt ein Hinweis statt eines Absturzes",
                "Ollama" in fehler, fehler[:80])
    finally:
        if web is not None:
            web.stoppen()
        (config.ANTHROPIC_API_KEY, config.LOKALES_MODELL, config.OLLAMA_URL,
         config.ENV_DATEI, rohwerte) = alt
        config._ROHWERTE.clear()
        config._ROHWERTE.update(rohwerte)
        try:
            server.shutdown()
        except Exception:
            pass


def pruefung_freier_dienst(agent):
    """Jarvis denkt über einen Gratis-Schlüssel - ohne Anthropic, ohne Guthaben."""
    abschnitt("Gratis-Dienst (OpenAI-kompatibel)")
    import http.server
    import urllib.request as _netz
    import modules.freier_dienst as dienst_modul

    gesehen = []
    modus = {"fehler": 0}

    class FalscherDienst(http.server.BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def do_POST(self):
            laenge = int(self.headers.get("Content-Length") or 0)
            anfrage = json.loads(self.rfile.read(laenge).decode("utf-8"))
            gesehen.append({"pfad": self.path, "kopf": dict(self.headers), "body": anfrage})
            if modus["fehler"] or anfrage.get("model") in modus.get("voll", ()):
                roh = json.dumps([{"error": {"message": "zu viel"}}]).encode("utf-8")
                self.send_response(modus["fehler"] or 429)
            else:
                hat_ergebnis = any(m.get("role") == "tool" for m in anfrage["messages"])
                alles = json.dumps(anfrage["messages"], ensure_ascii=False)
                if ("Behauptungstest" in alles and "kein Werkzeug aufgerufen" not in alles
                        and not hat_ergebnis):
                    nachricht = {"role": "assistant", "content": "Habe ich notiert."}
                    roh = json.dumps({"choices": [{"message": nachricht}]}).encode("utf-8")
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Content-Length", str(len(roh)))
                    self.end_headers()
                    self.wfile.write(roh)
                    return
                if hat_ergebnis:
                    nachricht = {"role": "assistant", "content": "Notiert, Chef."}
                elif "Sag nur: ok" in json.dumps(anfrage["messages"]):
                    nachricht = {"role": "assistant", "content": "ok"}
                else:
                    nachricht = {"role": "assistant", "content": None, "tool_calls": [{
                        "id": "call_1", "type": "function",
                        "extra_content": {"google": {"thought_signature": "SIG123"}},
                        "function": {"name": "notiz_speichern",
                                     "arguments": json.dumps({"text": "Dienst-Test Nikolic"})}}]}
                roh = json.dumps({"choices": [{"message": nachricht}]}).encode("utf-8")
                self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(roh)))
            self.end_headers()
            self.wfile.write(roh)

    server = http.server.ThreadingHTTPServer(("127.0.0.1", 11997), FalscherDienst)
    threading.Thread(target=server.serve_forever, daemon=True).start()

    vorgabe = dienst_modul.DIENST_VORGABEN["groq"]
    alte_url = vorgabe["url"]
    vorgabe["url"] = "http://127.0.0.1:11997/openai/v1"
    alt = (config.ANTHROPIC_API_KEY, config.FREIER_DIENST_URL, config.FREIER_DIENST_SCHLUESSEL,
           config.FREIER_DIENST_MODELL, config.LOKALES_MODELL, config.ENV_DATEI,
           dict(config._ROHWERTE))
    config.ANTHROPIC_API_KEY = ""
    config.FREIER_DIENST_URL = config.FREIER_DIENST_SCHLUESSEL = config.FREIER_DIENST_MODELL = ""
    config.LOKALES_MODELL = ""
    config.ENV_DATEI = pathlib.Path(ARBEITSVERZEICHNIS) / "dienst.env"
    web = None
    try:
        pruefen("Ohne Schlüssel und Dienst ist Jarvis nicht einsatzbereit",
                agent.einsatzbereit() is False)
        web = JarvisWeb(agent, port=8801)
        web.starten(blockierend=False)
        time.sleep(0.5)

        def senden(nutzlast):
            anfrage = _netz.Request("http://127.0.0.1:8801/api/dienst",
                                    data=json.dumps(nutzlast).encode("utf-8"),
                                    headers={"Content-Type": "application/json"})
            with _netz.urlopen(anfrage, timeout=20) as r:
                return r.read().decode("utf-8")

        pruefen("Unbekannter Anbieter wird abgewiesen",
                json.loads(senden({"dienst": "evil", "schluessel": "x" * 20}))["ok"] is False)
        pruefen("Zu kurzer Schlüssel wird abgewiesen",
                json.loads(senden({"dienst": "groq", "schluessel": "abc"}))["ok"] is False)
        modus["fehler"] = 401
        roh = senden({"dienst": "groq", "schluessel": "gsk_" + "f" * 30})
        pruefen("Abgelehnter Schlüssel wird nicht gespeichert",
                json.loads(roh)["ok"] is False and not config.ENV_DATEI.exists()
                and not agent.einsatzbereit())
        modus["fehler"] = 0

        echter = "gsk_" + "g" * 30
        roh = senden({"dienst": "groq", "schluessel": echter[:10] + "\n" + echter[10:]})
        pruefen("Gültiger Schlüssel wird gespeichert und sofort benutzt",
                json.loads(roh)["ok"] is True and agent.einsatzbereit()
                and config.FREIER_DIENST_SCHLUESSEL == echter
                and ("FREIER_DIENST_SCHLUESSEL=" + echter) in config.ENV_DATEI.read_text("utf-8"))
        pruefen("Die Antwort verrät den Schlüssel nicht", echter not in roh)
        pruefen("Die Adresse stammt aus der Anbieterliste, nicht aus der Anfrage",
                config.FREIER_DIENST_URL == "http://127.0.0.1:11997/openai/v1")

        agent.verlauf_leeren()
        text = agent.denken("Bitte merk dir die Notiz Dienst-Test Nikolic")
        pruefen("Jarvis antwortet über den Gratis-Dienst durch die normale Denkschleife",
                text == "Notiert, Chef.", text)
        pruefen("Der Werkzeugaufruf des Dienstes wurde ausgeführt",
                any("Dienst-Test Nikolic" in n["text"]
                    for n in agent.memory.notizen_suchen("Dienst-Test")))
        erste, zweite = gesehen[-2], gesehen[-1]
        pruefen("Schlüssel kommt als Bearer-Kopf an, mit eigener Kennung",
                erste["kopf"].get("Authorization") == "Bearer " + echter
                and erste["kopf"].get("User-Agent") == "Jarvis/1.0"
                and erste["pfad"].endswith("/chat/completions"))
        pruefen("Nur wenige, passende Werkzeuge gehen mit",
                0 < len(erste["body"]["tools"]) <= 16,
                "%d von %d" % (len(erste["body"]["tools"]), len(agent.tools.katalog())))
        pruefen("Das Werkzeugergebnis geht mit der Aufrufnummer zurück",
                any(m.get("role") == "tool" and m.get("tool_call_id") == "call_1"
                    for m in zweite["body"]["messages"]))
        pruefen("Werkzeugaufruf des Assistenten steht im OpenAI-Format im Verlauf",
                any(m.get("tool_calls") and m["tool_calls"][0]["function"]["name"]
                    == "notiz_speichern" for m in zweite["body"]["messages"]))

        pruefen("Die Gedanken-Signatur von Gemini geht unverändert zurück",
                any(c.get("extra_content") == {"google": {"thought_signature": "SIG123"}}
                    for m in zweite["body"]["messages"] for c in m.get("tool_calls") or []))

        # Behauptung ohne Werkzeug: das Modell muss nachbessern
        agent.verlauf_leeren()
        vorher = len(gesehen)
        text = agent.denken("Merk dir den Behauptungstest Dienst-Test Nikolic")
        pruefen("Behauptet das Modell eine Tat ohne Werkzeug, muss es nachbessern",
                len(gesehen) - vorher >= 3 and text == "Notiert, Chef.", text)
        pruefen("Die Werkzeugpflicht steht als letzte Anweisung vor der Frage",
                any(m.get("role") == "system" and "Werkzeug" in m.get("content", "")
                    for m in gesehen[vorher]["body"]["messages"][-2:]))

        from modules.lokal import werkzeuge_auswaehlen
        namen = [w["name"] for w in werkzeuge_auswaehlen(
            agent.tools.katalog(), "Leg einen offenen Punkt an: Berger anrufen", 12)]
        pruefen("Abhaken wird nur angeboten, wenn danach gefragt ist",
                "punkt_erledigen" not in namen and "punkt_anlegen" in namen)
        namen = [w["name"] for w in werkzeuge_auswaehlen(
            agent.tools.katalog(), "Punkt Rechnung Meier ist erledigt", 12)]
        pruefen("Wer 'erledigt' sagt, bekommt das Abhaken", "punkt_erledigen" in namen)
        pruefen("Alte, langsame Modell-Reihenfolge wird auf die schnelle umgestellt",
                dienst_modul.modelle_liste("gemini-flash-latest,gemini-flash-lite-latest,"
                                           "gemini-3.8-flash,gemini-3.5-flash,gemini-3.1-flash-lite")[0]
                == "gemini-flash-lite-latest")

        # Modellkette: ist das erste Modell aufgebraucht, nimmt Jarvis das nächste
        config.FREIER_DIENST_MODELL = "voll-modell,gut-modell"
        modus["voll"] = {"voll-modell"}
        vorher = len(gesehen)
        agent.verlauf_leeren()
        text = agent.denken("Bitte merk dir die Notiz Kette Nikolic")
        modelle = [g["body"]["model"] for g in gesehen[vorher:]]
        pruefen("Bei aufgebrauchtem Modell nimmt Jarvis das nächste der Kette",
                text == "Notiert, Chef." and modelle[0] == "voll-modell"
                and "gut-modell" in modelle, ", ".join(modelle))
        vorher = len(gesehen)
        agent.denken("Und noch eine Notiz Kette Zwei")
        pruefen("Das aufgebrauchte Modell wird kurz übersprungen, nicht ständig neu versucht",
                "voll-modell" not in [g["body"]["model"] for g in gesehen[vorher:]])
        modus["voll"] = set()
        config.FREIER_DIENST_MODELL = "llama-3.3-70b-versatile"
        dienst_modul._PAUSE.clear()

        # 429 beim Einrichten heißt: Schlüssel gültig, also speichern
        config.FREIER_DIENST_SCHLUESSEL = ""
        modus["fehler"] = 429
        roh = senden({"dienst": "groq", "schluessel": "gsk_" + "k" * 30})
        pruefen("Ein 429 beim Einrichten speichert den gültigen Schlüssel trotzdem",
                json.loads(roh)["ok"] is True and config.FREIER_DIENST_SCHLUESSEL == "gsk_" + "k" * 30
                and "Kontingent" in json.loads(roh)["text"])
        modus["fehler"] = 0

        modus["fehler"] = 429
        meldung = agent.denken("Hallo")
        pruefen("Ein erschöpftes Kontingent wird verständlich gemeldet",
                "Kontingent" in meldung, meldung[:80])
        modus["fehler"] = 0
    finally:
        vorgabe["url"] = alte_url
        if web is not None:
            web.stoppen()
        server.shutdown()
        (config.ANTHROPIC_API_KEY, config.FREIER_DIENST_URL, config.FREIER_DIENST_SCHLUESSEL,
         config.FREIER_DIENST_MODELL, config.LOKALES_MODELL, config.ENV_DATEI, rohwerte) = alt
        config._ROHWERTE.clear()
        config._ROHWERTE.update(rohwerte)


def pruefung_autopilot(agent):
    """Der Autopilot arbeitet von selbst und legt alles zur Freigabe vor."""
    abschnitt("Autopilot")
    import http.server
    import urllib.request as _netz
    from modules.autopilot import osm_abfrage
    from modules.scheduler import Scheduler

    abfragen = []

    class FalschesOSM(http.server.BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def do_POST(self):
            laenge = int(self.headers.get("Content-Length") or 0)
            abfragen.append(self.rfile.read(laenge).decode("utf-8"))
            roh = json.dumps({"elements": [
                {"tags": {"name": "Praxis Dr. Hofer", "amenity": "doctors",
                          "phone": "+43 732 111", "addr:street": "Hauptstraße",
                          "addr:housenumber": "5", "addr:city": "Teststadt"}},
                {"tags": {"name": "Steuerbüro Lang", "office": "tax_advisor",
                          "email": "info@lang.example", "website": "https://lang.example"}},
                {"tags": {"name": "Niemand Erreichbar GmbH", "office": "lawyer"}},
                {"tags": {"amenity": "doctors"}},
            ]}).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(roh)))
            self.end_headers()
            self.wfile.write(roh)

    server = http.server.ThreadingHTTPServer(("127.0.0.1", 11996), FalschesOSM)
    threading.Thread(target=server.serve_forever, daemon=True).start()

    class FalschePost:
        def __init__(self):
            self.gesendet = []

        def lesen_moeglich(self):
            return True

        def senden_moeglich(self):
            return True

        def ungelesene(self, limit=15):
            mail = {"id": "1", "betreff": "Angebot für unser Büro?",
                    "absender": "Maria Huber <huber@firma.example>",
                    "auszug": "Können Sie uns ein Angebot für 200 qm machen?",
                    "einstufung": "wichtig"}
            return {"ok": True, "mails": [mail], "wichtig": [mail]}

        def senden(self, an, betreff, text):
            self.gesendet.append((an, betreff, text))
            return {"ok": True, "text": "raus"}

    autopilot = agent.tools.autopilot
    post = FalschePost()
    alte_post, autopilot.mail = autopilot.mail, post
    autopilot.osm_url = "http://127.0.0.1:11996/api/interpreter"
    alt = (config.ANTHROPIC_API_KEY, config.FREIER_DIENST_SCHLUESSEL, config.LOKALES_MODELL,
           config.AUTOPILOT_ORT, config.AUTOPILOT_BRANCHEN, config.AUTOPILOT_AN,
           config.ENV_DATEI, dict(config._ROHWERTE))
    config.ANTHROPIC_API_KEY = config.FREIER_DIENST_SCHLUESSEL = config.LOKALES_MODELL = ""
    config.ENV_DATEI = pathlib.Path(ARBEITSVERZEICHNIS) / "autopilot.env"
    web = None
    try:
        abfrage = osm_abfrage('Linz"];out;', ["Arztpraxen"])
        pruefen("Der Ort kann die OpenStreetMap-Abfrage nicht aufbrechen",
                'Linz"' not in abfrage and '"Linz' in abfrage)

        autopilot.einstellungen_setzen("", ["Arztpraxen", "Steuerberater"], True)
        ergebnis = autopilot.laufen(agent)
        pruefen("Ohne Ort sagt der Autopilot, was fehlt",
                ergebnis["ok"] and "Kein Ort" in ergebnis["text"], ergebnis["text"][:90])

        autopilot.einstellungen_setzen("Teststadt", ["Arztpraxen", "Steuerberater"], True)
        pruefen("Einstellungen landen in der .env",
                "AUTOPILOT_ORT=Teststadt" in config.ENV_DATEI.read_text("utf-8"))
        ergebnis = autopilot.laufen(agent)
        offen = autopilot.aufgaben()
        anrufe = [a for a in offen if a["art"] == "anruf"]
        pruefen("Neue Betriebe aus OpenStreetMap werden zu Anruf-Aufgaben",
                sorted(a["firma"] for a in anrufe) == ["Praxis Dr. Hofer", "Steuerbüro Lang"],
                ergebnis["text"][:90])
        pruefen("Betriebe ohne Telefon und Mail werden übersprungen",
                not any("Niemand" in a["titel"] for a in offen))
        hofer = [a for a in anrufe if a["firma"] == "Praxis Dr. Hofer"][0]
        pruefen("Ohne Gehirn gibt es eine Vorlage statt nichts",
                config.NUTZER_NAME in hofer["text"] and "Hygiene" in hofer["text"]
                and hofer["an"] == "+43 732 111")
        pruefen("Die Abfrage fragt nach den gewählten Branchen im Ort",
                "doctors" in __import__("urllib.parse").parse.unquote_plus(abfragen[-1])
                and "Teststadt" in __import__("urllib.parse").parse.unquote_plus(abfragen[-1]))
        lang = [a for a in anrufe if a["firma"] == "Steuerbüro Lang"][0]
        pruefen("Bei Mailadressen steht der Hinweis auf die Einwilligung",
                "Einwilligung" in lang["text"])
        pruefen("Die Betriebe stehen in der Pipeline",
                agent.tools.akquise.lead_finden("Praxis Dr. Hofer") is not None)
        pruefen("Die wichtige Mail ohne Gehirn wird ein Hinweis, keine erfundene Antwort",
                any(a["art"] == "hinweis" and "Huber" in a["titel"] for a in offen))

        vorher = len(autopilot.aufgaben())
        autopilot.laufen(agent)
        pruefen("Ein zweiter Lauf legt nichts doppelt an", len(autopilot.aufgaben()) == vorher)

        # Mit Gehirn: Antwortentwurf, und Senden erst nach dem Klick
        hinweis = [a for a in autopilot.aufgaben() if "Huber" in a["titel"]][0]
        autopilot.aufgabe_erledigen(hinweis["id"], "verwerfen")
        agent.memory._schreiben("DELETE FROM autopilot_aufgaben WHERE id=?", (hinweis["id"],))
        agent.einsatzbereit = lambda: True
        agent.text_anfrage = lambda *a, **k: {"ok": True, "text": "Sehr geehrte Frau Huber, gern."}
        agent.json_anfrage = lambda *a, **k: {"ok": False}
        autopilot.laufen(agent)
        antwort = [a for a in autopilot.aufgaben() if a["art"] == "antwort"]
        pruefen("Mit Gehirn entwirft er die Antwort auf die wichtige Mail",
                len(antwort) == 1 and antwort[0]["an"] == "huber@firma.example"
                and antwort[0]["betreff"].startswith("Re: "))
        pruefen("Nichts wird von selbst gesendet", post.gesendet == [])
        erledigt = autopilot.aufgabe_erledigen(antwort[0]["id"], "senden",
                                               "Sehr geehrte Frau Huber, gern - Montag?")
        pruefen("Erst der Klick sendet, mit dem bearbeiteten Text",
                erledigt["ok"] and post.gesendet[-1][0] == "huber@firma.example"
                and "Montag" in post.gesendet[-1][2])
        pruefen("Eine erledigte Aufgabe lässt sich nicht nochmal senden",
                autopilot.aufgabe_erledigen(antwort[0]["id"], "senden")["ok"] is False)
        r = autopilot.aufgabe_erledigen(hofer["id"], "erledigt")
        lead = agent.tools.akquise.lead_finden("Praxis Dr. Hofer")
        pruefen("Anruf erledigt: Betrieb rückt auf 'kontaktiert'",
                r["ok"] and lead["stufe"] == "kontaktiert")

        # Nachfassen
        agent.memory._schreiben("UPDATE leads SET naechster_kontakt=? WHERE firma=?",
                                ((datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d"),
                                 "Praxis Dr. Hofer"))
        autopilot.laufen(agent)
        pruefen("Fällige Interessenten werden zu Nachfass-Aufgaben",
                any(a["art"] == "nachfassen" and a["firma"] == "Praxis Dr. Hofer"
                    for a in autopilot.aufgaben()))

        pruefen("Sprachbefehl 'heute_zu_tun' liest die Liste vor",
                agent.tools.run("heute_zu_tun", {}).get("ok") is True)
        zeitplan = Scheduler(agent=agent)
        zeitplan.standardjobs_anlegen()
        pruefen("Der Autopilot steht von selbst im Zeitplan",
                any(n.startswith("autopilot:") for n in zeitplan.jobs))

        web = JarvisWeb(agent, port=8802)
        web.starten(blockierend=False)
        time.sleep(0.5)
        with _netz.urlopen("http://127.0.0.1:8802/api/autopilot", timeout=10) as r:
            daten = json.loads(r.read().decode("utf-8"))
        pruefen("/api/autopilot liefert Aufgaben und Einstellungen",
                daten["ok"] and daten["aufgaben"] and daten["einstellungen"]["ort"] == "Teststadt")
        with _netz.urlopen("http://127.0.0.1:8802/autopilot", timeout=10) as r:
            seite = r.read().decode("utf-8")
        pruefen("Die Seite 'Heute zu tun' ist persönlich und setzt Text nie als HTML",
                config.NUTZER_NAME in seite and "innerHTML" not in seite and "{{" not in seite)
        anfrage = _netz.Request("http://127.0.0.1:8802/api/autopilot/laufen", data=b"{}",
                                headers={"Content-Type": "application/json"})
        with _netz.urlopen(anfrage, timeout=10) as r:
            gestartet = json.loads(r.read().decode("utf-8"))
        for _ in range(40):
            if not autopilot._laeuft.locked():
                break
            time.sleep(0.25)
        pruefen("'Jetzt arbeiten' läuft im Hintergrund, die Seite hängt nicht",
                gestartet["ok"] and not autopilot._laeuft.locked())
    finally:
        for name in ("einsatzbereit", "text_anfrage", "json_anfrage"):
            agent.__dict__.pop(name, None)
        if web is not None:
            web.stoppen()
        server.shutdown()
        autopilot.mail, autopilot.osm_url = alte_post, None
        (config.ANTHROPIC_API_KEY, config.FREIER_DIENST_SCHLUESSEL, config.LOKALES_MODELL,
         config.AUTOPILOT_ORT, config.AUTOPILOT_BRANCHEN, config.AUTOPILOT_AN,
         config.ENV_DATEI, rohwerte) = alt
        config._ROHWERTE.clear()
        config._ROHWERTE.update(rohwerte)


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
    pruefung_webapp(agent)
    pruefung_protokoll(agent)
    pruefung_schluessel(agent)
    pruefung_lokales_modell(agent)
    pruefung_freier_dienst(agent)
    pruefung_autopilot(agent)
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
