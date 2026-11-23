#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Echte Prüfung „iPhone im eigenen WLAN“ (WebKit = Safari-Engine, iPhone-13-Emulation, echte WLAN-Adresse).

    python3 autonomous/tests/iphone_pruefung.py

Ablauf (leerer, temporärer Datenordner – echte Daten werden nicht berührt):
  1. AUTONOMOUS starten (nur 127.0.0.1).
  2. „Mac“ (WebKit, Desktop): Einstellungen → „iPhone verbinden“ einschalten, QR-Code fotografieren.
  3. QR-Foto mit einem unabhängigen Leser (ZXing) dekodieren: Inhalt = angezeigter Link = Link des Servers.
  4. „iPhone 13“ (WebKit) öffnet den dekodierten Link über die WLAN-Adresse (nicht 127.0.0.1), lädt die Oberfläche,
     speichert eine Einstellung (echte Herkunft → klappt), fremde Herkunft → 403.
  5. „Mac“ schaltet wieder aus → die WLAN-Adresse ist nicht mehr erreichbar (Python und WebKit).

Voraussetzung: Node.js, Playwright mit WebKit, Python-Pakete zxing-cpp und Pillow (nur für diese Prüfung),
und eine private Adresse dieses Rechners (sonst gibt es nichts zu prüfen – dann Abbruch mit Meldung).
"""

import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request

HIER = os.path.dirname(os.path.abspath(__file__))
PROJEKT = os.path.dirname(os.path.dirname(HIER))
sys.path.insert(0, PROJEKT)

from autonomous import wlan  # noqa: E402 – erst nach dem Pfad

OEFFNER = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def freier_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def node(teil, url, *rest):
    """Einen Teil von iphone_pruefung.js ausführen; liefert dessen JSON-Ergebnis."""
    umgebung = dict(os.environ, NO_PROXY="*", no_proxy="*")  # WLAN-Adresse direkt, nie über einen Proxy
    lauf = subprocess.run(["node", os.path.join(HIER, "iphone_pruefung.js"), teil, url] + list(rest),
                          cwd=PROJEKT, env=umgebung, capture_output=True, text=True, timeout=180)
    zeilen = [z for z in lauf.stdout.splitlines() if z.startswith("{")]
    if not zeilen:
        return {"ok": False, "abbruch": (lauf.stderr or lauf.stdout).strip()[-500:], "pruefungen": []}
    return json.loads(zeilen[-1])


def qr_lesen(bild):
    import zxingcpp
    from PIL import Image
    return [g.text for g in zxingcpp.read_barcodes(Image.open(bild))]


def erreichbar(url):
    try:
        with OEFFNER.open(url, timeout=3):
            return True
    except urllib.error.HTTPError:
        return True  # der Server hat geantwortet
    except OSError:
        return False


def main():
    adressen = wlan.private_adressen()
    if not adressen:
        print("ABBRUCH: Dieser Rechner hat keine private Adresse (kein WLAN/LAN) – nichts zu prüfen.")
        return 2
    try:
        import zxingcpp  # noqa: F401
        from PIL import Image  # noqa: F401
    except ImportError:
        print("ABBRUCH: Für die QR-Gegenprobe fehlen zxing-cpp und Pillow (pip install zxing-cpp pillow).")
        return 2

    daten = tempfile.mkdtemp(prefix="autonomous-iphone-")
    port = freier_port()
    umgebung = dict(os.environ, AUTONOMOUS_DATEN=daten, AUTONOMOUS_PORT=str(port))
    server = subprocess.Popen([sys.executable, "-m", "autonomous", "start"], cwd=PROJEKT, env=umgebung,
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    ergebnisse = []

    def melde(ok, text):
        ergebnisse.append((bool(ok), text))
        return bool(ok)

    def uebernehmen(teil, r):
        for p in r.get("pruefungen", []):
            melde(p["ok"], p["text"])
        if r.get("abbruch"):
            melde(False, "%s: abgebrochen – %s" % (teil, r["abbruch"]))
        return r

    try:
        for _ in range(150):
            if erreichbar("http://127.0.0.1:%d/status" % port):
                break
            time.sleep(0.1)
        else:
            print("ABBRUCH: Testserver startet nicht.")
            return 1
        with open(os.path.join(daten, "zugang.txt")) as f:
            schluessel = f.read().strip()
        mac_link = "http://127.0.0.1:%d/?k=%s" % (port, schluessel)
        wlan_status = "http://%s:%d/status" % (adressen[0], port)
        melde(not erreichbar(wlan_status), "Vorher: WLAN-Adresse %s nicht erreichbar (Standard aus)" % adressen[0])

        bild = os.path.join(daten, "qr.png")
        mac = uebernehmen("Mac", node("mac", mac_link, bild))
        link = mac.get("link") or ""
        if os.path.exists(bild):
            gelesen = qr_lesen(bild)
            melde(gelesen == [link] and link.startswith("http://%s:%d/?k=" % (adressen[0], port)),
                  "QR-Code (Foto aus der Oberfläche, ZXing) = angezeigter Link: %s"
                  % ("ja" if gelesen == [link] else "NEIN – gelesen %r" % gelesen))
            iphone_link = gelesen[0] if gelesen else link
        else:
            melde(False, "QR-Foto fehlt")
            iphone_link = link
        if iphone_link:
            r = uebernehmen("iPhone", node("iphone", iphone_link))
            if r.get("webkit"):
                print("WebKit-Version: %s" % r["webkit"])
        uebernehmen("Mac aus", node("aus", mac_link))
        melde(not erreichbar(wlan_status), "Nachher: WLAN-Adresse wieder nicht erreichbar (Python)")
        if iphone_link:
            uebernehmen("iPhone weg", node("weg", iphone_link))
        melde(erreichbar("http://127.0.0.1:%d/status" % port), "Mac selbst (127.0.0.1) bleibt erreichbar")
    finally:
        server.terminate()
        try:
            server.wait(10)
        except subprocess.TimeoutExpired:
            server.kill()
        shutil.rmtree(daten, ignore_errors=True)

    for ok, text in ergebnisse:
        print(("OK      " if ok else "FEHLER  ") + text)
    fehlgeschlagen = sum(1 for ok, _ in ergebnisse if not ok)
    print("\niPhone-Prüfung: %d von %d Prüfungen bestanden." % (len(ergebnisse) - fehlgeschlagen, len(ergebnisse)))
    return 1 if fehlgeschlagen else 0


if __name__ == "__main__":
    sys.exit(main())
