#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Den Mac steuern: Kurzbefehle, Fensterlayouts, Lautstärke.

**Kurzbefehle.** Licht, Szenen und Fokus laufen über benannte Kurzbefehle in einem
Ordner der Kurzbefehle-App (Standard ``Jarvis``). Ausgeführt wird nur, was in der
*aktuellen* Liste dieses Ordners steht; ein erfundener oder fremder Name läuft
nie. Eine Eingabe geht über die Standardeingabe in den Kurzbefehl (nie über
Dateien: ``-i``/``-o`` brauchen seit macOS 13.2 Vollzugriff auf die Festplatte
und scheitern still). **Die Ausgabe eines Kurzbefehls wird nie weitergegeben** -
ein Kurzbefehl wie "Kontakte holen" wäre sonst eine Hintertür zu Kontakten,
Kalender und Nachrichten. Zurück kommt nur "gelaufen" oder ein Fehlertext. Ob
vorher gefragt wird (erster Lauf eines Namens, Lauf nach fremdem Text), regelt
das Werkzeug in ``tools.py``; hier liegt nur, was dafür gemerkt werden muss.

**Fenster.** Feste Layouts (zentrale, arbeiten, praesentation) öffnen die
Seiten von Jarvis als eigene Chrome-Fenster mit eigenem Profil, auf dem
gewünschten Bildschirm. Claude schreibt dabei nie freies AppleScript.

**Einspeisbar.** Alles läuft über ``ausfuehren(befehl, timeout)`` - Prüfungen
speisen eigene Antworten ein, nichts öffnet dabei ein Fenster.
"""

import json
import os
import re
import socket
import sqlite3
import time

import config
from modules.hardware import befehl_lauf, systembefehl
from modules.memory import db_schema_anlegen, db_verbindung, zeitstempel

KURZBEFEHL_TIMEOUT = 60
KURZBEFEHL_MAX_NAMEN = 60
# Wie bei den übrigen Werkzeugen: Zeichen, die in einer Eingabe nichts zu suchen haben.
KURZBEFEHL_VERBOTENE_ZEICHEN = set(";|&$`\n<>")
KURZBEFEHL_FEHLT_TEXT = "Kurzbefehle gibt es erst ab macOS 12 – hier fehlt das Programm shortcuts."

SCHEMA_KURZBEFEHLE = """
CREATE TABLE IF NOT EXISTS kurzbefehle_bekannt (
    name TEXT PRIMARY KEY,
    erstmals TEXT NOT NULL
);
"""

# Die Ports der Anzeige: der Dienst zeigt auf 8766 (nur die Zentrale und das Gehirn),
# die Web-App auf 8765 (auch die Hauptseite). Wie run.anzeige_oeffnen: erst der Dienst.
STEUERUNG_PORT_DIENST = 8766
STEUERUNG_PORT_WEB = 8765
FENSTER_ANZEIGESEITEN = ("/zentrale", "/gehirn")

# Fensterlayouts. "rahmen" ist [links, oben, breite, hoehe] als Anteil des Bildschirms.
# "bildschirm": 0 ist der Hauptbildschirm; "anzeige" steht für ANZEIGE_BILDSCHIRM (Standard 1).
LAYOUTS = {
    "zentrale": [{"seite": "/zentrale", "bildschirm": "anzeige", "rahmen": [0, 0, 1, 1]}],
    "arbeiten": [{"seite": "/", "bildschirm": 0, "rahmen": [0.6, 0, 0.4, 1]},
                 {"seite": "/zentrale", "bildschirm": "anzeige", "rahmen": [0, 0, 1, 1]}],
    "praesentation": [{"seite": "/zentrale", "bildschirm": 0, "rahmen": [0, 0, 1, 1]}],
}

BEDIENUNGSHILFEN_HINWEIS = ("Für das Verschieben von Fenstern braucht Jarvis die Bedienungshilfen "
                            "(Systemeinstellungen > Datenschutz & Sicherheit > Bedienungshilfen).")
AUTOMATION_HINWEIS = ("Für das Verschieben von Fenstern braucht Jarvis die Erlaubnis für System Events "
                      "(Systemeinstellungen > Datenschutz & Sicherheit > Automation).")

# Die Bildschirme, wie macOS sie meldet (Ursprung unten links). Die Umrechnung auf
# oben links macht bildschirme_lesen.
BILDSCHIRME_JXA = (
    'ObjC.import("AppKit");'
    'var s = $.NSScreen.screens, a = [];'
    'for (var i = 0; i < s.count; i++) {'
    ' var f = s.objectAtIndex(i).frame;'
    ' a.push({x: f.origin.x, y: f.origin.y, w: f.size.width, h: f.size.height});'
    '}'
    'JSON.stringify(a);'
)


def _eine_zeile(text, grenze=160) -> str:
    kurz = " ".join(str(text or "").split())
    return kurz if len(kurz) <= grenze else kurz[:grenze].rstrip() + " …"


# ---------------------------------------------------------------------------
# Kurzbefehle
# ---------------------------------------------------------------------------

def kurzbefehl_ordner(ordner=None) -> str:
    return str(ordner or config.KURZBEFEHL_ORDNER or "Jarvis").strip() or "Jarvis"


def kurzbefehle_liste(ordner=None, ausfuehren=None) -> dict:
    """Die Kurzbefehle im Ordner der Kurzbefehle-App. Gibt ``{"ok", "namen", "text"}`` zurück."""
    ordner = kurzbefehl_ordner(ordner)
    code, ausgabe, fehler = befehl_lauf(ausfuehren or systembefehl,
                                        ["shortcuts", "list", "-f", ordner], 15)
    if code == 127:
        return {"ok": False, "namen": [], "text": KURZBEFEHL_FEHLT_TEXT, "fehler": KURZBEFEHL_FEHLT_TEXT}
    if code != 0:
        text = ("Die Kurzbefehle ließen sich nicht lesen (%s). Gibt es in der Kurzbefehle-App "
                "einen Ordner '%s'?" % (_eine_zeile(fehler or ausgabe, 100) or "Code %d" % code, ordner))
        return {"ok": False, "namen": [], "text": text, "fehler": text}
    namen = []
    for zeile in ausgabe.splitlines():
        zeile = zeile.strip()
        if zeile and zeile not in namen:
            namen.append(zeile)
    if not namen:
        return {"ok": True, "namen": [],
                "text": "Im Ordner '%s' der Kurzbefehle-App liegt noch nichts. Leg dort Kurzbefehle wie "
                        "'Licht Büro an' an – nur solche, die nichts nach außen schicken." % ordner}
    sichtbar = namen[:KURZBEFEHL_MAX_NAMEN]
    return {"ok": True, "namen": sichtbar,
            "text": "Im Ordner '%s': %s%s." % (ordner, ", ".join(sichtbar),
                                              (" und %d weitere" % (len(namen) - len(sichtbar)))
                                              if len(namen) > len(sichtbar) else "")}


def kurzbefehl_finden(name, namen) -> str:
    """Der Name aus der Liste, der gemeint ist - sonst leer. Groß- und Kleinschreibung zählt nicht mit."""
    name = str(name or "").strip()
    if not name:
        return ""
    if name in namen:
        return name
    normal = " ".join(name.split()).casefold()
    treffer = [n for n in namen if " ".join(n.split()).casefold() == normal]
    return treffer[0] if len(treffer) == 1 else ""


def kurzbefehl_eingabe_pruefen(text) -> tuple:
    """Prüft die Eingabe eines Kurzbefehls. Gibt ``(ok, Meldung)`` zurück."""
    text = str(text if text is not None else "")
    if len(text) > 500:
        return False, "Der Wert ist zu lang."
    treffer = sorted({z for z in text if z in KURZBEFEHL_VERBOTENE_ZEICHEN})
    if treffer:
        return False, ("Der Wert enthält die Zeichen %s. Solche Werte führe ich grundsätzlich nicht aus."
                       % ", ".join(repr(z) for z in treffer))
    return True, ""


def kurzbefehl_pruefen(name, eingabe="", ausfuehren=None, ordner=None, pruefer=None) -> dict:
    """Darf dieser Kurzbefehl laufen? Der Name muss in der Liste des Ordners stehen.

    Gibt ``{"ok": True, "name", "eingabe"}`` mit dem Namen aus der Liste zurück,
    sonst ``{"ok": False, "fehler"}``. Gestartet wird hier nichts.
    """
    ordner = kurzbefehl_ordner(ordner)
    liste = kurzbefehle_liste(ordner, ausfuehren)
    if not liste["ok"]:
        return {"ok": False, "fehler": liste["text"]}
    echt = kurzbefehl_finden(name, liste["namen"])
    if not echt:
        vorhanden = ", ".join(liste["namen"]) if liste["namen"] else "noch keiner"
        return {"ok": False,
                "fehler": "Den Kurzbefehl '%s' gibt es im Ordner %s nicht. Vorhanden: %s."
                          % (_eine_zeile(name, 60) or "(leer)", ordner, vorhanden)}
    eingabe = "" if eingabe is None else str(eingabe)
    if eingabe.strip():
        ok, meldung = (pruefer or kurzbefehl_eingabe_pruefen)(eingabe)
        if not ok:
            return {"ok": False, "fehler": "Die Eingabe für den Kurzbefehl ist nicht zulässig. %s" % meldung}
    else:
        eingabe = ""
    return {"ok": True, "name": echt, "eingabe": eingabe}


def kurzbefehl_ausfuehren(name, eingabe="", ausfuehren=None, ordner=None, pruefer=None,
                          timeout=KURZBEFEHL_TIMEOUT) -> dict:
    """Führt einen Kurzbefehl aus dem Ordner aus: ``shortcuts run <Name>``, Eingabe über stdin.

    Die Ausgabe des Kurzbefehls wird verworfen. Zurück kommt nur, ob er gelaufen ist.
    """
    pruefung = kurzbefehl_pruefen(name, eingabe, ausfuehren, ordner, pruefer)
    if not pruefung["ok"]:
        return pruefung
    echt = pruefung["name"]
    code, _verworfen, fehler = befehl_lauf(ausfuehren or systembefehl, ["shortcuts", "run", echt],
                                           timeout, eingabe=pruefung["eingabe"])
    if code == 127:
        return {"ok": False, "fehler": KURZBEFEHL_FEHLT_TEXT}
    if code == 124:
        return {"ok": False, "name": echt,
                "fehler": "Der Kurzbefehl '%s' hat nach %d Sekunden nicht geantwortet. Fragt er etwas "
                          "ab? Dann einmal von Hand starten und die Rückfragen beantworten." % (echt, timeout)}
    if code != 0:
        grund = _eine_zeile(fehler, 160)
        return {"ok": False, "name": echt,
                "fehler": "Der Kurzbefehl ist fehlgeschlagen%s" % ((": " + grund) if grund else " (Code %d)." % code)}
    return {"ok": True, "name": echt,
            "text": "Der Kurzbefehl '%s' ist gelaufen. Was er getan hat, sehe ich nicht." % echt}


def kurzbefehl_bekannt(name, db_pfad=None) -> bool:
    """Wurde dieser Name schon einmal freigegeben? Im Zweifel ``False`` - dann wird gefragt."""
    try:
        db_schema_anlegen(SCHEMA_KURZBEFEHLE, db_pfad)
        verbindung = db_verbindung(db_pfad)
        try:
            zeile = verbindung.execute("SELECT 1 FROM kurzbefehle_bekannt WHERE name = ?",
                                       (str(name),)).fetchone()
        finally:
            verbindung.close()
        return zeile is not None
    except sqlite3.Error:
        return False


def kurzbefehl_merken(name, db_pfad=None) -> bool:
    """Vermerkt einen Namen als freigegeben - danach läuft er ohne Rückfrage."""
    try:
        db_schema_anlegen(SCHEMA_KURZBEFEHLE, db_pfad)
        verbindung = db_verbindung(db_pfad)
        try:
            verbindung.execute("INSERT OR IGNORE INTO kurzbefehle_bekannt (name, erstmals) VALUES (?, ?)",
                               (str(name), zeitstempel()))
            verbindung.commit()
        finally:
            verbindung.close()
        return True
    except sqlite3.Error as fehler:
        print("[steuerung] Der Kurzbefehl ließ sich nicht vermerken: %s" % fehler)
        return False


# ---------------------------------------------------------------------------
# Bildschirme und Fenster
# ---------------------------------------------------------------------------

def bildschirme_lesen(text) -> list:
    """Liest die Ausgabe von ``BILDSCHIRME_JXA`` als ``[{"x", "y", "w", "h"}]``.

    macOS misst von unten links, Fenster werden von oben links gesetzt: Die
    Oberkante eines Bildschirms ist ``Höhe des Hauptbildschirms - (y + h)``.
    Der erste Bildschirm ist der Hauptbildschirm. Unlesbares ergibt eine leere Liste.
    """
    zeilen = [z for z in str(text or "").strip().splitlines() if z.strip()]
    daten = None
    for kandidat in (str(text or "").strip(), zeilen[-1] if zeilen else ""):
        try:
            daten = json.loads(kandidat)
            break
        except ValueError:
            continue
    if not isinstance(daten, list):
        return []
    roh = []
    for eintrag in daten:
        try:
            roh.append(tuple(float(eintrag[k]) for k in ("x", "y", "w", "h")))
        except (TypeError, KeyError, ValueError):
            return []
    if not roh or any(w <= 0 or h <= 0 for _, _, w, h in roh):
        return []
    haupt = roh[0][3]
    return [{"x": int(round(x)), "y": int(round(haupt - (y + h))), "w": int(round(w)), "h": int(round(h))}
            for x, y, w, h in roh]


def bildschirme(ausfuehren=None) -> list:
    """Die Bildschirme mit Ursprung oben links: ``[{"x", "y", "w", "h"}]``, der Hauptbildschirm zuerst."""
    code, ausgabe, _ = befehl_lauf(ausfuehren or systembefehl,
                                   ["osascript", "-l", "JavaScript", "-e", BILDSCHIRME_JXA], 10)
    return bildschirme_lesen(ausgabe) if code == 0 else []


def steuerung_port_belegt(port) -> bool:
    """Lauscht auf diesem Anschluss jemand?"""
    try:
        with socket.create_connection(("127.0.0.1", int(port)), timeout=0.5):
            return True
    except OSError:
        return False


def anzeige_port_waehlen(seite, port_belegt=None):
    """Der Anschluss, auf dem diese Seite läuft - ``None``, wenn keiner.

    Zentrale und Gehirn zeigt der Dienst (8766) oder die Web-App (8765), der
    Dienst zuerst. Die Hauptseite gibt es nur in der Web-App.
    """
    belegt = port_belegt or steuerung_port_belegt
    reihe = ((STEUERUNG_PORT_DIENST, STEUERUNG_PORT_WEB) if seite in FENSTER_ANZEIGESEITEN
             else (STEUERUNG_PORT_WEB,))
    for port in reihe:
        if belegt(port):
            return port
    return None


def chrome_vorhanden() -> bool:
    """Ist Google Chrome installiert?"""
    return any(os.path.isdir(os.path.expanduser(pfad)) for pfad in
               ("/Applications/Google Chrome.app", "~/Applications/Google Chrome.app"))


def layout_fenster(layout) -> list:
    """Die Fenster eines Layouts, mit dem Bildschirm als Zahl (``ANZEIGE_BILDSCHIRM`` eingesetzt)."""
    fenster = []
    for eintrag in LAYOUTS.get(str(layout or "").strip().lower(), []):
        kopie = dict(eintrag)
        if kopie.get("bildschirm") == "anzeige":
            kopie["bildschirm"] = max(0, int(config.ANZEIGE_BILDSCHIRM))
        fenster.append(kopie)
    return fenster


def _korrektur_hinweis(text) -> str:
    """Welche Erlaubnis fehlt, wenn System Events das Fenster nicht verschieben darf?"""
    if "-1719" in text or "-25211" in text or "assistive" in text.lower():
        return BEDIENUNGSHILFEN_HINWEIS
    if "-1743" in text:
        return AUTOMATION_HINWEIS
    return ""


def _fenster_nachziehen(ausfuehren, suchmuster, rahmen, pause) -> str:
    """Rückt das neueste Fenster des Anzeige-Chrome mit System Events zurecht.

    Gefunden wird nur der Chrome-Prozess mit dem eigenen Profil (``pgrep``, der älteste
    Treffer ist der Hauptprozess): Ein Fenster des Chrome, in dem der Nutzer sonst
    arbeitet, wird nie angefasst. Gibt einen Hinweis zurück, wenn eine Erlaubnis fehlt -
    sonst leer; ohne gefundenen Prozess bleibt es bei der Position, die Chrome übernommen hat.
    """
    pid = ""
    for _ in range(3):
        pause(1.0)
        code, ausgabe, _ = befehl_lauf(ausfuehren, ["pgrep", "-of", suchmuster], 5)
        treffer = ausgabe.split()[0] if code == 0 and ausgabe.split() else ""
        if treffer.isdigit():
            pid = treffer
            break
    if not pid:
        return ""
    x, y, breite, hoehe = rahmen
    skript = ["osascript",
              "-e", 'tell application "System Events"',
              "-e", "tell (first process whose unix id is %s)" % pid,
              "-e", "set position of window 1 to {%d, %d}" % (x, y),
              "-e", "set size of window 1 to {%d, %d}" % (breite, hoehe),
              "-e", "end tell",
              "-e", "end tell"]
    code, ausgabe, fehler = befehl_lauf(ausfuehren, skript, 10)
    return _korrektur_hinweis("%s %s" % (ausgabe, fehler)) if code != 0 else ""


def fenster_anordnen(layout, ausfuehren=None, port_belegt=None, chrome_da=None, pause=None) -> dict:
    """Ordnet die Fenster nach einem festen Layout (zentrale, arbeiten, praesentation).

    Jede Seite von Jarvis öffnet als Chrome-Fenster mit eigenem Profil
    (``--app``), auf dem Bildschirm des Layouts. Danach rückt System Events das
    Fenster gerade, falls Chrome die Position nicht übernommen hat; ohne
    Bedienungshilfen bleibt es bei Chromes Position, und es steht ein Hinweis da.
    Gibt ``{"ok", "text", "fenster", "hinweise"}`` zurück.
    """
    name = str(layout or "").strip().lower()
    if name not in LAYOUTS:
        return {"ok": False, "fehler": "Das Layout '%s' kenne ich nicht. Möglich: %s."
                                       % (_eine_zeile(layout, 40) or "(leer)", ", ".join(sorted(LAYOUTS)))}
    ausf = ausfuehren or systembefehl
    if not (chrome_da or chrome_vorhanden)():
        return {"ok": False, "fehler": "Für Anzeige-Fenster brauche ich Google Chrome."}
    schirme = bildschirme(ausf)
    if not schirme:
        return {"ok": False, "fehler": "Ich konnte die Bildschirme nicht auslesen – ohne sie setze ich "
                                       "kein Fenster."}
    pause = pause or time.sleep
    hinweise, fenster = [], []
    profil = "--user-data-dir=%s" % (config.PROFIL_VERZEICHNIS / "chrome-anzeige")
    suchmuster = "user-data-dir=" + re.escape(str(config.PROFIL_VERZEICHNIS / "chrome-anzeige"))
    korrigieren = True
    for eintrag in layout_fenster(name):
        seite = eintrag["seite"]
        port = anzeige_port_waehlen(seite, port_belegt)
        if port is None:
            hinweise.append("Die Anzeige läuft gerade nicht – starte JARVIS oder den Dienst." if seite in FENSTER_ANZEIGESEITEN
                            else "Die Hauptseite gibt es nur in der Web-App (Doppelklick auf JARVIS), "
                                 "der Dienst zeigt nur die Zentrale.")
            continue
        index = eintrag["bildschirm"]
        if index >= len(schirme):
            hinweise.append("Bildschirm %d gibt es nicht – %s kommt auf den Hauptbildschirm."
                            % (index, "die Seite " + seite))
            index = 0
        schirm = schirme[index]
        links, oben, breite, hoehe = eintrag["rahmen"]
        x, y = schirm["x"] + int(round(links * schirm["w"])), schirm["y"] + int(round(oben * schirm["h"]))
        b, h = int(round(breite * schirm["w"])), int(round(hoehe * schirm["h"]))
        befehl = ["open", "-na", "Google Chrome", "--args", profil, "--no-first-run",
                  "--no-default-browser-check", "--app=http://localhost:%d%s" % (port, seite),
                  "--window-position=%d,%d" % (x, y), "--window-size=%d,%d" % (b, h)]
        code, ausgabe, fehler = befehl_lauf(ausf, befehl, 20)
        if code != 0:
            hinweise.append("Das Fenster %s ließ sich nicht öffnen: %s"
                            % (seite, _eine_zeile(fehler or ausgabe, 100) or "Code %d" % code))
            continue
        fenster.append({"seite": seite, "bildschirm": index, "port": port,
                        "position": [x, y], "groesse": [b, h]})
        if korrigieren:
            hinweis = _fenster_nachziehen(ausf, suchmuster, (x, y, b, h), pause)
            if hinweis:
                korrigieren = False
                if hinweis not in hinweise:
                    hinweise.append(hinweis)
    if not fenster:
        return {"ok": False, "fenster": [], "hinweise": hinweise,
                "fehler": " ".join(hinweise) or "Es ließ sich kein Fenster öffnen."}
    text = "%s: %s geöffnet." % (name, ", ".join("%s auf Bildschirm %d" % (f["seite"], f["bildschirm"])
                                                  for f in fenster))
    if hinweise:
        text += " " + " ".join(hinweise)
    return {"ok": True, "text": text, "fenster": fenster, "hinweise": hinweise}


# ---------------------------------------------------------------------------
# Lautstärke
# ---------------------------------------------------------------------------

def lautstaerke_setzen(prozent, ausfuehren=None) -> dict:
    """Stellt die Lautstärke des Macs (0 bis 100) ein."""
    wert = prozent
    if isinstance(wert, str):
        try:
            wert = float(wert.strip().rstrip("%").strip())
        except ValueError:
            wert = None
    if isinstance(wert, bool) or not isinstance(wert, (int, float)) or wert != wert \
            or wert in (float("inf"), float("-inf")) or wert != int(wert) or not 0 <= int(wert) <= 100:
        return {"ok": False, "fehler": "Die Lautstärke geht von 0 bis 100."}
    wert = int(wert)
    code, ausgabe, fehler = befehl_lauf(ausfuehren or systembefehl,
                                        ["osascript", "-e", "set volume output volume %d" % wert], 8)
    if code != 0:
        return {"ok": False, "fehler": "Die Lautstärke ließ sich nicht ändern: %s"
                                       % (_eine_zeile(fehler or ausgabe, 100) or "Code %d" % code)}
    return {"ok": True, "prozent": wert, "text": "Die Lautstärke steht auf %d Prozent." % wert}
