# -*- coding: utf-8 -*-
"""Zeit - alles wird in UTC gespeichert (``2026-10-31T17:45:00Z``).

Die Oberfläche rechnet beim Anzeigen in die Ortszeit des Macs um. Eingaben des
Nutzers oder des Modells ("2026-11-02 09:00") gelten als Ortszeit.
"""

import datetime

FORMAT = "%Y-%m-%dT%H:%M:%SZ"


def jetzt():
    return datetime.datetime.now(datetime.timezone.utc).strftime(FORMAT)


def vor_stunden(stunden):
    return (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=stunden)).strftime(FORMAT)


def vor_minuten(minuten):
    return (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(minutes=minuten)).strftime(FORMAT)


def lokaler_tagesbeginn():
    """Mitternacht der Ortszeit, als UTC-Text."""
    lokal = datetime.datetime.now().astimezone().replace(hour=0, minute=0, second=0, microsecond=0)
    return lokal.astimezone(datetime.timezone.utc).strftime(FORMAT)


def lokal_zu_utc(text):
    """"2026-11-02 09:00", "2026-11-02T09:00:30" oder "2026-11-02" (dann 09:00) in Ortszeit -> UTC-Text."""
    text = (text or "").strip()
    if not text:
        raise ValueError("Zeitpunkt fehlt.")
    if len(text) == 10:
        text += " 09:00"
    try:
        roh = datetime.datetime.fromisoformat(text.replace("Z", ""))
    except ValueError:
        raise ValueError("Zeitpunkt nicht lesbar: %r. Erwartet: JJJJ-MM-TT oder JJJJ-MM-TT HH:MM." % text) from None
    return roh.astimezone(datetime.timezone.utc).strftime(FORMAT)


def utc_zu_lokal_text(iso):
    """Für Meldungen und Prompts: "Sa 31.10.2026 18:45"."""
    if not iso:
        return ""
    try:
        t = datetime.datetime.strptime(iso, FORMAT).replace(tzinfo=datetime.timezone.utc).astimezone()
    except ValueError:
        return iso
    tage = ("Mo", "Di", "Mi", "Do", "Fr", "Sa", "So")
    return "%s %s" % (tage[t.weekday()], t.strftime("%d.%m.%Y %H:%M"))
