# -*- coding: utf-8 -*-
"""Bewertung von Ausschreibungen: deterministisch, nachvollziehbar, 0–100 Punkte.

Jeder Punkt hat eine Begründung in Klartext. Es werden KEINE Auftragswerte geschätzt.

Bausteine:
- Leistung passt eindeutig (Gebäude-, Unterhalts-, Glasreinigung … im Titel, „Reinigung“ zusammen mit
  einem Gebäude wie Schule oder Rathaus, ein eigener Suchbegriff oder Reinigungs-CPV bei TED) +35
- nur das allgemeine Wort „Reinigung“ (ohne Gebäudebezug)               +20 (Hinweis)
- Kernleistung Gebäude-/Unterhaltsreinigung im Titel                    +10
- technische Anlage statt Gebäude (Aufzug, Kanal-Sammler, Kläranlage …) −30
- Lieferung von Waren statt Dienstleistung (Reinigungsmittel, Hygieneartikel …) −40
- Ausschlussbegriff im Titel (z. B. Straßenreinigung, Kanal)            −60
- Region passt (PLZ-Bereich bzw. NUTS-Region)                           +35
- Vergabemarktplatz NRW ohne genauen Ort                                +25
- Region unbekannt                                                        0 (Hinweis)
- Region unbekannt, aber Ortsangabe außerhalb NRW (z. B. Berlin)         −50
- Region außerhalb                                                      −50
- Frist ≥ 14 Tage +20 · 7–13 Tage +10 · unter 7 Tage 0 (Warnung) · unbekannt +5
- Hinweise auf einen großen Auftrag (EU-weit, Lose, viele Objekte …)    −10 (Hinweis, kein Ausschluss)
"""

import re

from . import PASSEND_AB, tage_bis
from .quellen import TED_CPV

KERN = ("gebäudereinigung", "unterhaltsreinigung", "glasreinigung", "glas- und unterhaltsreinigung",
        "treppenhausreinigung", "büroreinigung", "fensterreinigung")
ALLGEMEIN = ("reinigung",)  # zu allgemein, um allein als Treffer zu zählen
STARK = KERN + ("grundreinigung", "bauendreinigung", "baureinigung", "sonderreinigung", "reinigungsleistung",
                "reinigungsdienst", "fassadenreinigung", "glas- und fensterreinigung")
OBJEKTE = ("schule", "rathaus", "kita", "kindergarten", "kindertages", "verwaltung", "büro", "gebäude", "turnhalle",
           "sporthalle", "liegenschaft", "wohnanlage", "treppenhaus", "praxis", "dienststelle", "kaserne",
           "jugendzentrum", "bürgerhaus", "feuerwache", "bibliothek", "museum", "immobilie", "objekt")
LIEFERUNG = ("beschaffung von", "lieferung", "artikel", "reinigungsmittel", "hygienematerial", "hygieneartikel",
             "verbrauchsmaterial", "reinigungsgerät", "reinigungsmaschine", "reinigungsautomat")
# Ortsangaben, die sicher außerhalb von NRW liegen (nur genutzt, wenn keine PLZ/NUTS bekannt ist)
AUSSERHALB_NRW = ("berlin", "hamburg", "bremen", "münchen", "bayern", "sachsen", "thüringen", "brandenburg",
                  "hessen", "schleswig", "mecklenburg", "rheinland-pfalz", "saarland", "baden-württemberg",
                  "stuttgart", "hannover", "dresden", "leipzig", "frankfurt", "nürnberg", "magdeburg", "erfurt",
                  "potsdam", "kiel", "rostock", "mainz", "wiesbaden", "saarbrücken", "schwerin")
TECHNIK = ("aufzug", "aufzüge", "hauptsammler", "sammler", "befahrung", "wasserhaltung", "rohrleitung",
           "kläranlage", "abscheider", "lüftung", "schornstein", "heizung", "kanalnetz", "sinkkasten",
           "straßeneinl", "regenrückhalte", "pumpwerk", "brunnen")
GROSS_MUSTER = (
    (re.compile(r"\beu-weit", re.I), "EU-weites Verfahren"),
    (re.compile(r"\bvgv\b", re.I), "EU-Verfahren nach VgV"),
    (re.compile(r"\blose?\b|\(\d+\s+lose\)|\blos\s+\d", re.I), "in Lose aufgeteilt"),
    (re.compile(r"\bin\s+(\d{2,})\s+(objekten|liegenschaften|gebäuden|standorten)", re.I), "viele Objekte"),
    (re.compile(r"verschiedenen\s+liegenschaften|mehrere(n)?\s+liegenschaften", re.I), "mehrere Liegenschaften"),
    (re.compile(r"rahmenvertrag|rahmenvereinbarung", re.I), "Rahmenvertrag"),
    (re.compile(r"bundesanstalt für immobilienaufgaben|bundeswehr", re.I), "große Bundesvergabestelle"),
)


def _norm(t):
    return " ".join(str(t or "").lower().split())


def bewerten(e, einstellungen, bezug=None):
    """Gibt (punkte 0–100, begruendung [str], passend bool) zurück."""
    titel = _norm(e.get("titel"))
    such = [_norm(s) for s in (einstellungen.get("suchbegriffe") or [])]
    aus = [_norm(s) for s in (einstellungen.get("ausschlussbegriffe") or [])]
    punkte, gruende = 0, []

    # Leistung
    stark = [s for s in STARK + tuple(x for x in such if x not in ALLGEMEIN) if s and s in titel]
    allgemein = [s for s in such if s in ALLGEMEIN and s in titel] or [s for s in ALLGEMEIN if s in titel]
    objekt = [o for o in OBJEKTE if o in titel]
    reinigungs_cpv = [c for c in e.get("cpv") or [] if c in TED_CPV]
    if stark:
        punkte += 35
        gruende.append("+35 Leistung passt: „%s“ im Titel" % stark[0])
    elif allgemein and objekt:
        punkte += 35
        gruende.append("+35 Leistung passt: Reinigung von Gebäuden („%s“)" % objekt[0])
    elif reinigungs_cpv:
        punkte += 35
        gruende.append("+35 Leistung passt: Reinigungs-Code (CPV %s)" % reinigungs_cpv[0])
    elif allgemein:
        punkte += 20
        gruende.append("+20 nur allgemein „Reinigung“ – prüfen, ob Gebäudereinigung gemeint ist")
    else:
        gruende.append("0 kein Suchbegriff im Titel")
    if any(k in titel for k in KERN):
        punkte += 10
        gruende.append("+10 Kernleistung (Gebäude-, Unterhalts- oder Glasreinigung)")
    technik = [t for t in TECHNIK if t in titel]
    if technik and not any(k in titel for k in KERN):
        punkte -= 30
        gruende.append("−30 vermutlich technische Anlage statt Gebäudereinigung („%s“)" % technik[0])
    lieferung = [w for w in LIEFERUNG if w in titel]
    if lieferung:
        punkte -= 40
        gruende.append("−40 vermutlich Lieferung von Waren statt Dienstleistung („%s“)" % lieferung[0])
    ausschluss = [s for s in aus if s and s in titel]
    if ausschluss:
        punkte -= 60
        gruende.append("−60 passt nicht zu uns: „%s“" % ausschluss[0])

    # Region
    plz, quelle = e.get("plz"), e.get("quelle")
    region_plz = set(einstellungen.get("region_plz") or [])
    region_nuts = [n for n in einstellungen.get("region_nuts") or []]
    if plz:
        if plz[:2] in region_plz:
            punkte += 35
            gruende.append("+35 Region passt (PLZ %s)" % plz)
        else:
            punkte -= 50
            gruende.append("−50 außerhalb unserer Region (PLZ %s)" % plz)
    elif quelle == "ted" and e.get("nuts"):
        if any(c.startswith(n) for c in e["nuts"] for n in region_nuts):
            punkte += 35
            gruende.append("+35 Region passt (Ausführungsort %s)" % ", ".join(e["nuts"][:3]))
        else:
            punkte -= 50
            gruende.append("−50 außerhalb unserer Region (%s)" % ", ".join(e["nuts"][:3]))
    elif quelle == "evergabe_nrw":
        punkte += 25
        gruende.append("+25 Vergabemarktplatz NRW – Auftrag vermutlich in NRW, genauer Ort in den Unterlagen")
    else:
        ortstext = _norm(" ".join(str(e.get(f) or "") for f in ("ort", "titel", "vergabestelle")))
        fremd = [n for n in AUSSERHALB_NRW if re.search(r"\b%s\b" % re.escape(n), ortstext)]
        if fremd:
            punkte -= 50
            gruende.append("−50 vermutlich außerhalb von NRW (Ortsangabe „%s“)" % fremd[0])
        else:
            gruende.append("0 Ort unbekannt – in den Unterlagen prüfen")

    # Frist
    tage = tage_bis(e.get("frist"), bezug)
    if tage is None:
        punkte += 5
        gruende.append("+5 Frist nicht angegeben – in den Unterlagen prüfen")
    elif tage < 0:
        gruende.append("0 Frist abgelaufen")
    elif tage >= 14:
        punkte += 20
        gruende.append("+20 genug Zeit (%d Tage bis zur Frist)" % tage)
    elif tage >= 7:
        punkte += 10
        gruende.append("+10 Frist in %d Tagen" % tage)
    else:
        gruende.append("0 Achtung: sehr knapp – nur noch %d Tag(e) bis zur Frist" % tage)

    # Größe (Hinweis, kein Ausschluss)
    groesse = [name for muster, name in GROSS_MUSTER
               if muster.search(" ".join(str(e.get(f) or "") for f in ("titel", "vergabestelle", "verfahren")))]
    if quelle == "ted" and "EU-weites Verfahren" not in groesse:
        groesse.insert(0, "EU-weites Verfahren")
    if groesse:
        punkte -= 10
        gruende.append("−10 vermutlich großer Auftrag (%s) – Eignung und Kapazität prüfen"
                       % ", ".join(dict.fromkeys(groesse)))

    punkte = max(0, min(100, punkte))
    return punkte, gruende, punkte >= PASSEND_AB
