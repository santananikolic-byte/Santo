#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Startet AUTONOMOUS mit einem leeren, temporären Datenordner, führt die UI-Prüfung
(ui_pruefung.js, Playwright/Chromium) aus und stoppt den Server wieder.

    python3 autonomous/tests/ui_server.py
    UI_BILDER=/pfad python3 autonomous/tests/ui_server.py   # zusätzlich Bildschirmfotos

Voraussetzung: Node.js und Playwright mit Chromium. Echte Daten werden nicht berührt.
"""

import os
import shutil
import socket
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


def main():
    daten = tempfile.mkdtemp(prefix="autonomous-ui-")
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
