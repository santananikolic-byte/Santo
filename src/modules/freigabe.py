#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Freigaben mit Was, Warum und Wie - lesbar statt rohem JSON.

Vor allem mit Wirkung nach außen fragt Jarvis nach. Damit jemand Ja sagen
kann, muss die Frage drei Dinge beantworten:

* **Was** passiert - "eine Mail an kunde@firma.at schicken, Betreff Angebot".
* **Warum** - das schreibt Claude selbst ins Feld ``begruendung``. Fehlt es,
  steht das sichtbar da, statt still zu fehlen.
* **Wie** - über welchen Weg es hinausgeht, und was dabei bekannt wird.

Je Werkzeug gibt es dafür eine kleine Funktion in ``FREIGABE_ANGABEN``
(Argumente rein, ``(was, wie)`` raus) - keine Vorlagensprache, die niemand
lesen kann. Werkzeuge, die nur Kennungen bekommen (eine Termin-id, eine
Message-ID), tragen in ``FREIGABE_AUFLOESEN`` einen Auflöser ein, der daraus
Lesbares macht. Scheitert er, zeigt die Freigabe die rohen Argumente.

Die Beschreibung wandert als JSON durch die Freigabewege (Terminal,
Telegram, Stimme, Browser). Wege, die nichts davon wissen, bekommen weiter den
alten Text - ``freigabe_lesen`` erkennt beides.
"""

import json

import config

# Ein Wert in den Argumenten darf so lang sein, bevor er gekürzt wird.
# Adresse, Pfad und Empfänger bleiben immer ganz - die muss man sehen.
ARGUMENT_GRENZE = 400
NIE_KUERZEN = ("adresse", "url", "pfad", "an")

OHNE_BEGRUENDUNG = "(ohne Begründung – Jarvis hat keinen Grund genannt)"

# Diese Aktionen gibt keine Geste frei - nur Klick oder Stimme. Die Gestenprüfung
# selbst kommt später; die Liste steht schon hier, damit alle sie kennen.
GESTE_GESPERRT = {"skript_ausfuehren", "bildschirm_bedienen", "browser_auftrag", "browser_schritt",
                  "datei_schreiben", "ordnen_ausfuehren", "ordnen_rueckgaengig",
                  "autopilot_schalten"}


def argumente_kuerzen(argumente: dict) -> dict:
    """Kürzt jedes lange Textfeld für sich - Empfänger, Pfad und Adresse nie."""
    kurz = {}
    for schluessel, wert in (argumente or {}).items():
        if isinstance(wert, str) and len(wert) > ARGUMENT_GRENZE and schluessel not in NIE_KUERZEN:
            kurz[schluessel] = "%s … (%d Zeichen insgesamt)" % (wert[:ARGUMENT_GRENZE], len(wert))
        else:
            kurz[schluessel] = wert
    return kurz


def _wert_kurz(wert, grenze: int = 120) -> str:
    """Ein Wert als eine Zeile, höchstens ``grenze`` Zeichen. Fehlt er: ``?``."""
    if wert is None or wert == "":
        return "?"
    text = " ".join(str(wert).split())
    return text if len(text) <= grenze else text[:grenze].rstrip() + " …"


def lesbarer_name(name: str) -> str:
    """``mcp__kalender__loeschen`` wird ``kalender, loeschen``, ``mail_senden`` ``mail senden``."""
    return str(name or "").replace("mcp__", "").replace("__", ", ").replace("_", " ").strip()


def _argumente_zeile(argumente: dict, grenze: int = 160) -> str:
    """Die Argumente als kurze Zeile ``name: wert; name: wert`` - ohne die Begründung."""
    teile = ["%s: %s" % (k, _wert_kurz(v, 60)) for k, v in (argumente or {}).items()
             if k != "begruendung"]
    return _wert_kurz("; ".join(teile), grenze) if teile else ""


# -- Was und Wie je Werkzeug ------------------------------------------------
# Jede Funktion bekommt die Argumente (samt Zusatzfeldern eines Auflösers) und
# gibt (was, wie) zurück. "was" steht nach "Ich soll ..." - ohne Punkt am Ende.
# Der erste Satz von "wie" wird im Dienst laut gesagt.

def _angaben_mail_senden(a: dict) -> tuple:
    k = _wert_kurz
    return ("eine Mail an %s schicken, Betreff „%s“. Sie beginnt mit: %s"
            % (k(a.get("an")), k(a.get("betreff")), k(a.get("text"))),
            "Per SMTP vom eingerichteten Postfach. Der ganze Text steht in den Details.")


def _angaben_termin_anlegen(a: dict) -> tuple:
    k = _wert_kurz
    ort = " in %s" % k(a.get("ort")) if a.get("ort") else ""
    return ("den Termin „%s“ am %s (%s Minuten) eintragen%s"
            % (k(a.get("titel")), k(a.get("beginn")), a.get("dauer_minuten") or 60, ort),
            "Im Kalender %s über CalDAV."
            % (config.CALDAV_KALENDER or "des eingerichteten Kontos"))


NACHRICHT_WEGE = {
    "telegram": "Über den Telegram-Bot.",
    "mail": "Per SMTP vom eingerichteten Postfach.",
    "imessage": "Über die Nachrichten-App des Macs mit deiner eigenen Nummer.",
    "sms": "Über die Nachrichten-App des Macs mit deiner eigenen Nummer.",
    "whatsapp": "Über den angeschlossenen WhatsApp-Dienst.",
}


def _angaben_nachricht_senden(a: dict) -> tuple:
    k = _wert_kurz
    kanal = str(a.get("kanal") or "").strip().lower()
    an = a.get("an") or ("dich selbst" if kanal == "telegram" else None)
    art = " als Sprachnachricht" if a.get("als_sprache") else ""
    return ("per %s an %s%s schreiben: %s" % (k(kanal), k(an), art, k(a.get("text"))),
            NACHRICHT_WEGE.get(kanal, "Über den Kanal %s." % k(kanal)))


def _angaben_anrufen(a: dict) -> tuple:
    k = _wert_kurz
    return ("%s anrufen und ansagen: %s" % (k(a.get("nummer")), k(a.get("ansage"))),
            "Ein Twilio-Anruf von deiner Twilio-Nummer. Die Ansage wird zweimal vorgelesen.")


def _angaben_sms_senden(a: dict) -> tuple:
    k = _wert_kurz
    twilio = bool(config.TWILIO_SID and config.TWILIO_TOKEN and config.TWILIO_NUMMER)
    return ("%s eine SMS schicken: %s" % (k(a.get("nummer")), k(a.get("text"))),
            "Über Twilio von deiner Twilio-Nummer." if twilio
            else "Über die Nachrichten-App des Macs mit deiner eigenen Nummer.")


def _angaben_skript_ausfuehren(a: dict) -> tuple:
    k = _wert_kurz
    liste = a.get("argumente") or []
    zusatz = " mit %s" % k(" ".join(str(x) for x in liste), 80) if liste else ""
    return ("das Skript %s aus der Werkstatt ausführen%s" % (k(a.get("name")), zusatz),
            "Mit Python in der Werkstatt. Der Code steht vollständig in der Frage.")


def _angaben_bildschirm_bedienen(a: dict) -> tuple:
    return ("den Bildschirm bedienen: %s" % _wert_kurz(a.get("ziel"), 160),
            "Schritt für Schritt über Bildschirmfotos. Jeder Schritt wird einzeln bestätigt.")


def _angaben_browser_auftrag(a: dict) -> tuple:
    start = " Er beginnt bei %s." % _wert_kurz(a.get("start")) if a.get("start") else ""
    return ("im Browser: %s" % _wert_kurz(a.get("ziel"), 160),
            "Klickt nur Beschriftungen, meldet sich nirgends an und kauft nichts.%s" % start)


def _angaben_browser_oeffnen(a: dict) -> tuple:
    return ("die Adresse %s öffnen" % _wert_kurz(a.get("adresse"), 300),
            "Im eingebauten Browser. Die Adresse selbst geht dabei ins Netz.")


def _angaben_autopilot_schalten(a: dict) -> tuple:
    if a.get("an"):
        return ("den Autopiloten einschalten",
                "Er arbeitet dann im Hintergrund, legt Entwürfe ins Postfach und schickt "
                "nichts ab.")
    return ("den Autopiloten ausschalten",
            "Bis du ihn wieder einschaltest, arbeitet er nicht mehr.")


def _angaben_datei_schreiben(a: dict) -> tuple:
    tun = "ersetzen" if a.get("ueberschreiben") else "neu anlegen"
    return ("die Datei %s %s, sie beginnt mit: %s"
            % (_wert_kurz(a.get("pfad"), 300), tun, _wert_kurz(a.get("inhalt"), 80)),
            "Nur in den freigegebenen Ordnern deines Benutzerordners. Der Inhalt steht in "
            "den Details.")


FREIGABE_ANGABEN = {
    "mail_senden": _angaben_mail_senden,
    "termin_anlegen": _angaben_termin_anlegen,
    "nachricht_senden": _angaben_nachricht_senden,
    "anrufen": _angaben_anrufen,
    "sms_senden": _angaben_sms_senden,
    "skript_ausfuehren": _angaben_skript_ausfuehren,
    "bildschirm_bedienen": _angaben_bildschirm_bedienen,
    "browser_auftrag": _angaben_browser_auftrag,
    "browser_oeffnen": _angaben_browser_oeffnen,
    "autopilot_schalten": _angaben_autopilot_schalten,
    "datei_schreiben": _angaben_datei_schreiben,
}

# Werkzeugname -> funktion(werkzeuge, argumente) -> dict mit Zusatzfeldern, die
# "was" lesbar machen (etwa der Titel eines Termins statt seiner Kennung).
# Die Zusatzfelder landen nur in der Angaben-Funktion, nicht in den Argumenten.
FREIGABE_AUFLOESEN = {}

# Die Pakete tragen ihre Einträge zwischen ihren Marken ein, etwa
# FREIGABE_ANGABEN["termine_absagen"] = _angaben_termine_absagen.
# [P1 Bühne] Anfang
# [P1 Bühne] Ende
# [P2 Weltlage] Anfang
# [P2 Weltlage] Ende
# [P3 Telefon] Anfang
# [P3 Telefon] Ende
# [P4 Büro] Anfang
# [P4 Büro] Ende
# [P5 Sicht] Anfang
# [P5 Sicht] Ende
# [P6 Stimme] Anfang
# [P6 Stimme] Ende
# [P7 Start] Anfang
# [P7 Start] Ende


def _angaben_unbekannt(name: str, a: dict) -> tuple:
    """Für Werkzeuge ohne eigenen Eintrag, auch die von MCP-Diensten."""
    zeile = _argumente_zeile(a)
    if str(name).startswith("mcp__"):
        teile = str(name).split("__")
        dienst = teile[1] if len(teile) > 1 else "?"
        werkzeug = "__".join(teile[2:]) or "?"
        was = "beim Dienst „%s“ das Werkzeug „%s“ ausführen" % (dienst, werkzeug)
        wie = ("Über den angeschlossenen Dienst „%s“. Was das Werkzeug genau tut, "
               "bestimmt dieser Dienst." % dienst)
    else:
        was = "%s ausführen" % (lesbarer_name(name) or "ein Werkzeug")
        wie = "Über das Werkzeug %s." % name
    return (was + (", mit: %s" % zeile if zeile else ""), wie)


def freigabe_beschreiben(name: str, argumente: dict, zusatz: dict = None) -> dict:
    """Was, Warum und Wie einer Freigabe - plus die gekürzten Argumente.

    ``zusatz`` kommt von einem Auflöser (``FREIGABE_AUFLOESEN``) und macht
    "was" lesbar. Geht beim Beschreiben etwas schief, zeigt die Freigabe die
    rohen Argumente - eine Frage ganz ohne Inhalt darf es nie geben.
    """
    argumente = argumente if isinstance(argumente, dict) else {}
    felder = dict(argumente)
    if isinstance(zusatz, dict):
        felder.update(zusatz)
    angaben = FREIGABE_ANGABEN.get(name)
    was, wie = "", ""
    if angaben is not None:
        try:
            was, wie = angaben(felder)
        except Exception as fehler:
            print("[freigabe] Beschreibung für %s fehlgeschlagen: %s" % (name, fehler))
            was, wie = "", ""
        if not was and zusatz:
            # Vielleicht lag es an den Zusatzfeldern - dann eben mit den rohen Argumenten.
            try:
                was, wie = angaben(dict(argumente))
            except Exception:
                was, wie = "", ""
    if not was:
        was, wie_unbekannt = _angaben_unbekannt(name, argumente)
        wie = wie or wie_unbekannt
    warum = " ".join(str(argumente.get("begruendung") or "").split())
    sichtbar = {k: v for k, v in argumente_kuerzen(argumente).items() if k != "begruendung"}
    return {"was": str(was), "warum": warum or OHNE_BEGRUENDUNG, "wie": str(wie or ""),
            "argumente": sichtbar}


# -- Lesen auf der anderen Seite --------------------------------------------

def freigabe_lesen(details) -> dict:
    """Erkennt eine Beschreibung aus :func:`freigabe_beschreiben`.

    Gibt ``{"was", "warum", "wie", "argumente"}`` zurück - oder ``None`` für
    alten Freitext (etwa den Code eines Skripts) und alte Argument-JSONs.
    """
    if isinstance(details, dict):
        daten = details
    else:
        text = str(details or "").strip()
        if not text.startswith("{"):
            return None
        try:
            daten = json.loads(text)
        except ValueError:
            return None
    if not isinstance(daten, dict) or not daten.get("was"):
        return None
    argumente = daten.get("argumente")
    return {"was": str(daten.get("was") or ""), "warum": str(daten.get("warum") or ""),
            "wie": str(daten.get("wie") or ""),
            "argumente": argumente if isinstance(argumente, dict) else {}}


def erster_satz(text: str) -> str:
    """Der erste Satz eines Textes - mit großem Anfang und Punkt am Ende."""
    text = " ".join(str(text or "").split())
    if not text:
        return ""
    for ende in (". ", "! ", "? "):
        stelle = text.find(ende)
        if stelle >= 0:
            text = text[:stelle + 1]
    text = text[0].upper() + text[1:]
    return text if text[-1] in ".!?" else text + "."


def freigabe_text(aktion: str, details) -> str:
    """Die Freigabe als Klartext für Terminal und Telegram.

    Neue Beschreibungen werden zu "Was / Warum / Wie / Details", alter Text
    bleibt, wie er ist.
    """
    lesbar = freigabe_lesen(details)
    if lesbar is None:
        return str(details or "")
    try:
        argumente = json.dumps(lesbar["argumente"], ensure_ascii=False, default=str)
    except (TypeError, ValueError):
        argumente = str(lesbar["argumente"])
    return ("Was:     %s\nWarum:   %s\nWie:     %s\nDetails: %s"
            % (lesbar["was"], lesbar["warum"], lesbar["wie"], argumente))
