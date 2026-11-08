# -*- coding: utf-8 -*-
"""Viele Leben durchspielen (Monte-Carlo) - mit Spielgeld und ausgedachtem Markt.

Die Ergebnisse sagen nur etwas über die Spielregeln unter den Annahmen aus, nicht über den echten Markt.
"""

import random
from statistics import median

from .gehirne import RegelGehirn
from .kolonie import Kolonie
from .regeln import STANDARD, euro
from .welt import MarktAnnahmen, SimWelt


def ein_leben(regeln=STANDARD, annahmen=None, saat=0, max_stunden=24 * 30, kopierfreude=True):
    zufall = random.Random(saat)
    k = Kolonie(regeln)
    k.gruenden()
    welt = SimWelt(annahmen or MarktAnnahmen(), zufall)
    gehirn = RegelGehirn(zufall, kopierfreude=kopierfreude)
    while k.lebende() and k.stunde < max_stunden:
        k.runde(gehirn, welt)
    k.pruefen()
    return k


def viele_leben(anzahl=1000, regeln=STANDARD, annahmen=None, max_stunden=24 * 30, kopierfreude=True, saat=1):
    ergebnisse = []
    for i in range(anzahl):
        k = ein_leben(regeln, annahmen, saat * 100003 + i, max_stunden, kopierfreude)
        erster = k.agenten["A1"]
        ergebnisse.append({
            "ueberlebt": bool(k.lebende()),
            "lebensdauer": (k.stunde if erster.lebt else erster.gestorben),
            "kolonie_dauer": k.stunde,
            "agenten_gesamt": len(k.agenten),
            "besitzer": k.besitzer_bekommen,
            "verkaeufe": sum(1 for b in k.journal if b["art"] == "einnahme"),
        })
    n = len(ergebnisse)
    ueberlebt = sum(e["ueberlebt"] for e in ergebnisse)
    return {
        "laeufe": n, "max_stunden": max_stunden,
        "ueberlebensquote": ueberlebt / n if n else 0,
        "median_lebensdauer_stunden": median(e["lebensdauer"] for e in ergebnisse) if n else 0,
        "median_besitzer_cent": median(e["besitzer"] for e in ergebnisse) if n else 0,
        "schnitt_besitzer_cent": sum(e["besitzer"] for e in ergebnisse) // n if n else 0,
        "max_besitzer_cent": max((e["besitzer"] for e in ergebnisse), default=0),
        "ohne_einen_verkauf": sum(1 for e in ergebnisse if e["verkaeufe"] == 0) / n if n else 0,
        "schnitt_agenten": sum(e["agenten_gesamt"] for e in ergebnisse) / n if n else 0,
    }


def bericht(z):
    return "\n".join([
        f"SIMULATION mit Spielgeld: {z['laeufe']} Leben, je höchstens {z['max_stunden'] // 24} Tage.",
        "(Markt ausgedacht - Annahmen, keine echten Zahlen.)",
        f"  Kolonie lebt am Ende noch:     {z['ueberlebensquote'] * 100:.1f} %",
        f"  Ohne einen einzigen Verkauf:   {z['ohne_einen_verkauf'] * 100:.1f} %",
        f"  Lebensdauer erster Agent:      Median {z['median_lebensdauer_stunden']} Stunden "
        f"(wer bis zum Ende lebt, zählt mit {z['max_stunden']})",
        f"  Agenten pro Kolonie:           Schnitt {z['schnitt_agenten']:.1f}",
        f"  Was du als Besitzer bekommst:  Median {euro(z['median_besitzer_cent'])}, "
        f"Schnitt {euro(z['schnitt_besitzer_cent'])}, bester Lauf {euro(z['max_besitzer_cent'])}",
        "  Hinweis: Der Schnitt kommt von wenigen Glückstreffern. Typisch ist der Median.",
    ])
