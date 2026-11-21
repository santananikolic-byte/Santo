# -*- coding: utf-8 -*-
"""Auftrags-Radar: öffentliche Ausschreibungen finden, bewerten und vorbereiten.

Alles, was von außen kommt (Titel, Vergabestellen, Orte, Links), ist NICHT vertrauenswürdig:
Es wird gesäubert, in der Länge begrenzt, nur als Daten gespeichert und beim Einbau in HTML
immer escaped. Abgegeben wird nichts – das macht ausschließlich der Inhaber.
"""

import datetime
import re

QUELLEN_NAMEN = {
    "ted": "TED (EU-Amtsblatt)",
    "service_bund": "service.bund.de",
    "evergabe_nrw": "Vergabemarktplatz NRW",
}
STUFEN = ("neu", "interessant", "abgelehnt", "vorbereitet", "abgegeben", "gewonnen", "verloren")
PASSEND_AB = 60  # ab diesem Punktwert gilt eine Ausschreibung als „passend“

_UNSICHTBAR = re.compile(r"[\x00-\x08\x0b-\x1f\x7f​-‏‪-‮⁦-⁩﻿]")


def text(wert, laenge):
    """Fremdtext säubern: Steuer- und unsichtbare Zeichen raus, Leerraum glätten, Länge begrenzen."""
    if wert is None:
        return None
    t = _UNSICHTBAR.sub("", str(wert))
    t = " ".join(t.split())
    return t[:laenge].rstrip() or None


def heute():
    return datetime.date.today()


def tage_bis(frist, bezug=None):
    """Tage bis zur Frist (Datumsteil), None wenn unbekannt."""
    if not frist:
        return None
    try:
        datum = datetime.date.fromisoformat(str(frist)[:10])
    except ValueError:
        return None
    return (datum - (bezug or heute())).days


def datum_deutsch(frist):
    if not frist:
        return "nicht angegeben"
    s = str(frist)
    d = "%s.%s.%s" % (s[8:10], s[5:7], s[0:4])
    return d + (" um " + s[11:16] + " Uhr" if len(s) >= 16 else "")
