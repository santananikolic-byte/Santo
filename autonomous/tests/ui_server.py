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
    """Erkennbare TESTDATEN für das Auftrags-Radar – ohne Internet, mit dem echten Datenbank-Schema.

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
    ]
    con = sqlite3.connect(pfad)
    try:
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
        con.commit()
    finally:
        con.close()


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
