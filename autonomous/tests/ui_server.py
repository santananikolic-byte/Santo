#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Startet AUTONOMOUS mit einem leeren, temporären Datenordner, führt die UI-Prüfung
(ui_pruefung.js, Playwright/Chromium) aus und stoppt den Server wieder.

    python3 autonomous/tests/ui_server.py
    UI_BILDER=/pfad python3 autonomous/tests/ui_server.py   # zusätzlich Bildschirmfotos

Voraussetzung: Node.js und Playwright mit Chromium. Echte Daten werden nicht berührt.
"""

import datetime
import json
import os
import shutil
import socket
import sqlite3
import subprocess
import sys
import tempfile
import time
import urllib.request

HIER = os.path.dirname(os.path.abspath(__file__))
PROJEKT = os.path.dirname(os.path.dirname(HIER))


def freier_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def testdaten_anlegen(daten):
    """Erkennbare TESTDATEN für Auftrags-Radar und Marktbericht – ohne Internet, mit dem echten Datenbank-Schema.

    Die Tabellen entstehen über die echten Migrationen (autonomous.db.Datenbank); eingefügt wird direkt per
    sqlite3. Fristen relativ zu heute, damit die Prüfung an jedem Tag gleich läuft."""
    sys.path.insert(0, PROJEKT)
    from autonomous.db import Datenbank  # noqa: E402 – erst nach dem Pfad
    pfad = os.path.join(daten, "autonomous.db")
    Datenbank(pfad).schliessen()
    heute = datetime.date.today()
    jetzt = datetime.datetime.now().astimezone().isoformat(timespec="seconds")

    def tag(n, uhr=None):
        d = (heute + datetime.timedelta(days=n)).isoformat()
        return d + " " + uhr if uhr else d

    zeilen = [
        # id, quelle, extern_id, titel, vergabestelle, ort, plz, region, frist, veroeffentlicht, verfahren, punkte,
        # begruendung, status
        ("ui_test_1", "evergabe_nrw", "TEST-1", "TESTDATEN – Unterhaltsreinigung Rathaus (UI-Prüfung)",
         "Teststadt (Testdaten)", "Leverkusen", "51373", None, tag(2, "10:00"), tag(-3), "Öffentliche Ausschreibung", 95,
         ["Suchbegriff „unterhaltsreinigung“ im Titel", "Region passt (PLZ-Bereich 51)", "Frist sehr knapp"], "neu"),
        ("ui_test_2", "service_bund", "TEST-2", "TESTDATEN – Glasreinigung Schulzentrum (UI-Prüfung)",
         "Testkreis (Testdaten)", "Köln", "50667", None, tag(10, "12:00"), tag(-1), "Beschränkte Ausschreibung", 80,
         ["Suchbegriff „glasreinigung“ im Titel", "Region passt (PLZ-Bereich 50)"], "interessant"),
        ("ui_test_3", "ted", "TEST-3", "TESTDATEN – Gebäudereinigung Verwaltung, EU-weit (UI-Prüfung)",
         "Testbehörde (Testdaten)", "Düsseldorf", None, "DEA11", tag(20), tag(-5), "Offenes Verfahren", 65,
         ["Reinigungsleistung (CPV)", "Region NRW (NUTS DEA11)", "vermutlich großer Auftrag – Eignung prüfen (−10)"], "neu"),
        ("ui_test_4", "service_bund", "TEST-4", "TESTDATEN – Straßenreinigung Gewerbegebiet (UI-Prüfung)",
         "Testgemeinde (Testdaten)", "Hamburg", "20095", None, tag(15), tag(-2), "Öffentliche Ausschreibung", 20,
         ["Ausschlussbegriff „straßenreinigung“", "Region außerhalb"], "neu"),
        ("ui_test_5", "evergabe_nrw", "TEST-5", "TESTDATEN – Abgelaufene Fensterreinigung (UI-Prüfung)",
         "Teststadt (Testdaten)", "Bonn", "53111", None, tag(-1, "09:00"), tag(-20), "Öffentliche Ausschreibung", 90,
         ["Suchbegriff „fensterreinigung“ im Titel"], "neu"),
        # Dieselbe Ausschreibung wie ui_test_2, so wie TED sie meldet (Vorspann „Deutschland – Leistungsart – “,
        # Sitz der Vergabestelle in Klammern, Frist ohne Uhrzeit): mögliche Doppelte, standardmäßig ausgeblendet
        ("ui_test_6", "ted", "TEST-6", "Deutschland – Gebäudereinigung – TESTDATEN – Glasreinigung Schulzentrum (UI-Prüfung)",
         "Testkreis (Testdaten) (Köln)", None, None, "DEA23", tag(10), tag(-1), "Offenes Verfahren", 80,
         ["Reinigungsleistung (CPV)", "Region NRW (NUTS DEA23)"], "neu"),
        # Fristen heute und morgen (wenig Punkte, darum nur mit „alle Punktzahlen“ sichtbar)
        ("ui_test_7", "service_bund", "TEST-7", "TESTDATEN – Treppenhausreinigung, Frist heute (UI-Prüfung)",
         "Testgemeinde (Testdaten)", "Bremen", "28195", None, tag(0), tag(-4), "Öffentliche Ausschreibung", 30,
         ["Region außerhalb"], "neu"),
        ("ui_test_8", "service_bund", "TEST-8", "TESTDATEN – Büroreinigung, Frist morgen (UI-Prüfung)",
         "Testgemeinde (Testdaten)", "Bremen", "28195", None, tag(1), tag(-4), "Öffentliche Ausschreibung", 30,
         ["Region außerhalb"], "neu"),
    ]
    con = sqlite3.connect(pfad)
    try:
        # Täglicher Überlebensplan aus: Er würde beim Start sofort Bewerbungs-Mappen für die Testdaten anstoßen und
        # deren Status ändern. Den Knopf „Überlebensplan erstellen“ prüft die UI-Prüfung am Ende selbst.
        con.execute("INSERT INTO einstellungen (schluessel, wert, geaendert) VALUES (?,?,?)",
                    ("ueberlebensplan_taeglich", "false", jetzt))
        for (aid, quelle, extern, titel, stelle, ort, plz, region, frist, veroeffentlicht, verfahren, punkte, gruende,
             status) in zeilen:
            con.execute(
                "INSERT INTO ausschreibungen (id, quelle, extern_id, titel, vergabestelle, ort, plz, region, frist,"
                " veroeffentlicht, verfahren, link, cpv, punkte, begruendung, status, gefunden, aktualisiert)"
                " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (aid, quelle, extern, titel, stelle, ort, plz, region, frist, veroeffentlicht, verfahren,
                 "https://example.invalid/testdaten/" + extern, json.dumps(["90911200"]), punkte,
                 json.dumps(gruende, ensure_ascii=False), status, jetzt, jetzt))
        for quelle, ergebnis, gefunden, neu, passend, meldung in (
                ("ted", "ok", 1, 1, 1, None),
                ("service_bund", "ok", 2, 2, 1, None),
                ("evergabe_nrw", "fehler", 0, 0, 0, "TESTDATEN – Quelle nicht erreichbar (simuliert für die UI-Prüfung)")):
            con.execute("INSERT INTO suchlaeufe (zeit, quelle, ergebnis, gefunden, neu, passend, meldung) "
                        "VALUES (?,?,?,?,?,?,?)", (jetzt, quelle, ergebnis, gefunden, neu, passend, meldung))
        # KI-Protokoll: ein Eintrag eines bekannten Agenten und einer mit unbekanntem Namen (muss als reiner Text
        # erscheinen). Von gestern, damit sie nicht in das heutige Tageslimit zählen. Den Eintrag „Modell testen“
        # erzeugt die Prüfung selbst über den echten Knopf.
        gestern = (datetime.datetime.now() - datetime.timedelta(days=1)).astimezone().isoformat(timespec="seconds")
        for agent in ("research", "<i>unbekannt</i>"):
            con.execute("INSERT INTO modellaufrufe (zeit, anbieter, modell, agent, aufgabe_id, zeichen_ein, zeichen_aus,"
                        " kosten_cent, ergebnis) VALUES (?,?,?,?,?,?,?,?,?)",
                        (gestern, "TESTDATEN", "testmodell", agent, None, 10, 0, 0, "fehler"))
        # Ein erkennbarer TESTDATEN-Marktbericht (echtes Schema der Tabelle „aufgaben“, Ergebnis wie vom
        # Research-Agenten) – so lässt sich die Berichtsliste ohne Internet prüfen.
        ergebnis = {"zeitraum_tage": 90, "bericht_url": "/produkte/marktberichte/ui_test_mb/bericht.html",
                    "kennzahlen": {"ausschreibungen_ted_gesamt": 3, "zuschlaege_ted_gesamt": 1, "wettbewerber_anzahl": 1},
                    "ki_zusammenfassung": None, "hinweis": "TESTDATEN – nur für die UI-Prüfung"}
        con.execute("INSERT INTO aufgaben (id, titel, typ, ersteller, verantwortlich, status, prioritaet, erstellt,"
                    " aktualisiert, gestartet, beendet, eingabe, ergebnis, versuche) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    ("ui_test_mb", "TESTDATEN – Marktbericht (UI-Prüfung)", "marktbericht", "eigentuemer", "research",
                     "abgeschlossen", 3, jetzt, jetzt, jetzt, jetzt, json.dumps({"zeitraum_tage": 90}),
                     json.dumps(ergebnis, ensure_ascii=False), 1))
        # Ein erkennbarer TESTDATEN-Lauf des KI-Prüfstands (Ergebnis wie von ki/pruefstand.py) – so lässt sich die
        # Anzeige ohne echtes Modell prüfen. „fehler“ je Modell ist die Zahl der Fälle ohne Antwort.
        pruefstand = {"modelle": [
            {"modell": "TESTDATEN-modell-a", "punkte": 100, "max": 120, "prozent": 83, "kritisch": 1, "fehler": 0,
             "dauer_s": 61.5, "faelle": []},
            {"modell": "TESTDATEN-modell-b", "punkte": 60, "max": 120, "prozent": 50, "kritisch": 6, "fehler": 2,
             "dauer_s": 90.0, "faelle": []}],
            "bestes_modell": "TESTDATEN-modell-a", "empfehlung": "TESTDATEN – Empfehlung nur für die UI-Prüfung.",
            "faelle_anzahl": 15, "regeln_eigenes_modell": None, "hinweis": "TESTDATEN – nur für die UI-Prüfung"}
        con.execute("INSERT INTO aufgaben (id, titel, typ, ersteller, verantwortlich, status, prioritaet, erstellt,"
                    " aktualisiert, gestartet, beendet, eingabe, ergebnis, versuche) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    ("ui_test_ps", "TESTDATEN – KI-Prüfstand (UI-Prüfung)", "ki_pruefstand", "eigentuemer", "research",
                     "abgeschlossen", 3, jetzt, jetzt, jetzt, jetzt, json.dumps({}),
                     json.dumps(pruefstand, ensure_ascii=False), 1))
        con.commit()
    finally:
        con.close()
    bericht = os.path.join(daten, "produkte", "marktberichte", "ui_test_mb")
    os.makedirs(bericht, exist_ok=True)
    with open(os.path.join(bericht, "bericht.html"), "w", encoding="utf-8") as f:
        f.write("<!doctype html><html lang=\"de\"><meta charset=\"utf-8\"><title>TESTDATEN</title>"
                "<p>TESTDATEN – Marktbericht nur für die UI-Prüfung.</p></html>")


def main():
    daten = tempfile.mkdtemp(prefix="autonomous-ui-")
    testdaten_anlegen(daten)
    port = freier_port()
    umgebung = dict(os.environ, AUTONOMOUS_DATEN=daten, AUTONOMOUS_PORT=str(port))
    server = subprocess.Popen([sys.executable, "-m", "autonomous", "start"], cwd=PROJEKT, env=umgebung,
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        oeffner = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        for _ in range(150):
            try:
                with oeffner.open("http://127.0.0.1:%d/status" % port, timeout=1):
                    break
            except OSError:
                time.sleep(0.1)
        else:
            print("Testserver startet nicht.")
            return 1
        with open(os.path.join(daten, "zugang.txt")) as f:
            schluessel = f.read().strip()
        url = "http://127.0.0.1:%d/?k=%s" % (port, schluessel)
        return subprocess.call(["node", os.path.join(HIER, "ui_pruefung.js"), url], cwd=PROJEKT)
    finally:
        server.terminate()
        try:
            server.wait(10)
        except subprocess.TimeoutExpired:
            server.kill()
        shutil.rmtree(daten, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
