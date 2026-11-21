# -*- coding: utf-8 -*-
"""Kalkulation für einen Reinigungs-Dauerauftrag (deterministisch, ohne Modell).

Rechenweg – jeder Schritt steht im Ergebnis, damit ihr ihn nachrechnen könnt:

  Reinigungen pro Monat     = Eingabe pro Monat  oder  Eingabe pro Woche × 52 ÷ 12
  Stunden je Position/Monat = Fläche (m²) ÷ Leistungswert (m²/h) × Reinigungen pro Monat
  Anfahrtsstunden/Monat     = Anfahrten pro Monat × Anfahrt (Minuten) ÷ 60
  Reinigungskosten          = Reinigungsstunden × Stundensatz
  Material                  = Reinigungskosten × Material-%
  Anfahrtskosten            = Anfahrtsstunden × Stundensatz
  Zwischensumme             = Reinigungskosten + Material + Anfahrtskosten
  Zuschlag (Wagnis/Gewinn)  = Zwischensumme × Zuschlag-%
  Preis pro Monat (netto)   = Zwischensumme + Zuschlag
  Preis pro Jahr (netto)    = Preis pro Monat × 12

Grundsätze:
- Der Stundensatz kommt vom Inhaber (Eingabe oder Einstellung ``stundensatz_cent``). Fehlt er, werden die
  Stunden trotzdem gerechnet, der Preis bleibt „OFFEN“. Es wird NIE ein Satz angenommen.
- Leistungswerte (m²/h) sind Eingaben des Inhabers. Es werden keine Normwerte behauptet.
- Geld wird in Cent gerechnet, gerundet wird kaufmännisch auf volle Cent bei jedem Geldschritt.
- Alle Beträge sind netto. Umsatzsteuer bleibt ein offener Punkt (keine Steuerberatung).
"""

import datetime
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

from . import bereinigen
from ..wallet import betrag_in_cent, euro

OFFEN = "OFFEN – Stundensatz festlegen"
MAX_POSITIONEN = 30
LEISTUNGSWERT_WARNUNG = Decimal(2000)   # m²/h – darüber ist eine Eingabe offensichtlich unrealistisch

# Wissen mit Quelle (aus jarvis_core/wissenspakete/kalkulation.md, Stand 09.11.2026)
WISSEN_STAND = "09.11.2026"
MINDESTLOHN_QUELLE = ("Bundesamt für Justiz: Mindestlöhne in der Gebäudereinigung (TV Mindestlohn vom 15.11.2024, "
                      "Verordnung vom 23.01.2025) – https://www.gesetze-im-internet.de/tvmindestlohngeb_ude_2024/"
                      "BJNR0160B0025.html")
MINDESTLOHN_LG1_CENT = 1500   # Innen- und Unterhaltsreinigung, seit 01.01.2026
MINDESTLOHN_LG6_CENT = 1840   # Glas- und Fassadenreinigung, seit 01.01.2026
VERORDNUNG_ENDE = datetime.date(2027, 1, 1)
UST_QUELLE = "§ 13b Umsatzsteuergesetz – https://www.gesetze-im-internet.de/ustg_1980/__13b.html"
GLAS_WOERTER = ("glas", "fenster", "fassade")

STUNDENSATZ_DECKT = ("Ein Stundensatz muss Lohn, Lohnnebenkosten, Fahrzeuge, Versicherung, Verwaltung, Ausfälle und "
                     "Gewinn decken – Material und Zuschlag nur dann, wenn ihr sie hier nicht getrennt eingebt. Der "
                     "Mindestlohn ist nur die Untergrenze für den LOHN, nicht für den Stundensatz.")


# ---------------------------------------------------------------- Zahlen
def zahl(wert, name, minimum=None, maximum=None, ganz=False, null_erlaubt=False):
    """Zahl aus Eingabe (auch deutsche Schreibweise „12,5“) als Decimal. Wirft ValueError mit klarer Meldung."""
    if wert is None or isinstance(wert, bool) or (isinstance(wert, str) and not wert.strip()):
        raise ValueError("Pflichtfeld fehlt oder ist leer: %s" % name)
    if isinstance(wert, (int, float)):
        text = repr(wert) if isinstance(wert, float) else str(wert)
    elif isinstance(wert, str):
        text = wert.strip().replace(" ", "").replace(" ", "")
        if "," in text:
            text = text.replace(".", "").replace(",", ".")
    else:
        raise ValueError("%s muss eine Zahl sein." % name)
    try:
        d = Decimal(text)
    except InvalidOperation:
        raise ValueError("%s muss eine Zahl sein (z. B. 12,5)." % name)
    if not d.is_finite():
        raise ValueError("%s muss eine Zahl sein." % name)
    if ganz and d != d.to_integral_value():
        raise ValueError("%s muss eine ganze Zahl sein." % name)
    if d == 0 and null_erlaubt:
        return d
    if minimum is not None and d < minimum:
        raise ValueError("%s muss mindestens %s sein." % (name, deutsch(minimum)))
    if maximum is not None and d > maximum:
        raise ValueError("%s darf höchstens %s sein." % (name, deutsch(maximum)))
    return d


def deutsch(d, stellen=None):
    """Decimal → deutsche Schreibweise (Tausenderpunkt, Komma). Ohne ``stellen`` ohne unnötige Nullen."""
    d = Decimal(d)
    if stellen is not None:
        d = d.quantize(Decimal(1).scaleb(-stellen), rounding=ROUND_HALF_UP)
        text = "{:,.{}f}".format(d, stellen)
    else:
        d = d.normalize()
        text = "{:,f}".format(d)
        if "." in text:
            text = text.rstrip("0").rstrip(".")
    return text.replace(",", "§").replace(".", ",").replace("§", ".")


def _cent(d):
    return int(Decimal(d).quantize(Decimal(1), rounding=ROUND_HALF_UP))


# ---------------------------------------------------------------- Eingabe
def eingabe_pruefen(eingabe):
    """Prüft und normalisiert die Eingabe. Liefert ein dict mit Decimal-Werten (nicht JSON) – nur intern."""
    if not isinstance(eingabe, dict):
        raise ValueError("Eingabe muss ein Objekt sein.")
    roh = eingabe.get("positionen")
    if not isinstance(roh, list) or not roh:
        raise ValueError("Pflichtfeld fehlt: positionen (mindestens eine Fläche, z. B. Treppenhaus).")
    if len(roh) > MAX_POSITIONEN:
        raise ValueError("Zu viele Positionen (höchstens %d)." % MAX_POSITIONEN)
    positionen = []
    for nr, p in enumerate(roh, start=1):
        if not isinstance(p, dict):
            raise ValueError("Position %d muss ein Objekt sein." % nr)
        bezeichnung = bereinigen(p.get("bezeichnung"), 80, streng=True, name="Bezeichnung (Position %d)" % nr)
        if not bezeichnung:
            raise ValueError("Position %d: Bezeichnung fehlt (z. B. „Treppenhaus“)." % nr)
        flaeche = zahl(p.get("flaeche_m2"), "Fläche in m² (Position %d)" % nr, Decimal("0.01"), Decimal(1_000_000))
        if p.get("leistungswert_m2_h") in (None, ""):
            raise ValueError("Position %d: Leistungswert in m²/h fehlt (euer Wert – am besten selbst messen)." % nr)
        lw = zahl(p.get("leistungswert_m2_h"), "Leistungswert in m²/h (Position %d)" % nr, maximum=Decimal(100_000))
        if lw <= 0:
            raise ValueError("Position %d: Leistungswert muss größer als 0 sein." % nr)
        pro_monat, pro_woche = p.get("reinigungen_pro_monat"), p.get("reinigungen_pro_woche")
        hat_monat = pro_monat not in (None, "")
        hat_woche = pro_woche not in (None, "")
        if hat_monat == hat_woche:
            raise ValueError("Position %d: bitte genau eins angeben – reinigungen_pro_monat ODER "
                             "reinigungen_pro_woche." % nr)
        if hat_woche:
            woche = zahl(pro_woche, "Reinigungen pro Woche (Position %d)" % nr, Decimal("0.01"), Decimal(21))
            monat = woche * 52 / 12
            turnus = "%s× pro Woche" % deutsch(woche)
        else:
            woche = None
            monat = zahl(pro_monat, "Reinigungen pro Monat (Position %d)" % nr, Decimal("0.01"), Decimal(100))
            turnus = "%s× pro Monat" % deutsch(monat)
        positionen.append({"bezeichnung": bezeichnung, "flaeche_m2": flaeche, "leistungswert_m2_h": lw,
                           "reinigungen_pro_monat": monat, "reinigungen_pro_woche": woche, "turnus": turnus})

    stundensatz = eingabe.get("stundensatz")
    stundensatz_cent = None  # None = nicht angegeben (dann gilt die Einstellung; 0 dort = OFFEN)
    if isinstance(stundensatz, bool):
        raise ValueError("Stundensatz ungültig – bitte in Euro angeben, z. B. 38,50.")
    if stundensatz not in (None, "") and str(stundensatz).strip() not in ("0", "0,0", "0,00", "0.0", "0.00"):
        try:
            stundensatz_cent = betrag_in_cent(stundensatz)
        except (ValueError, TypeError):
            raise ValueError("Stundensatz ungültig – bitte in Euro angeben, z. B. 38,50.")
    werte = {}
    for name, beschriftung, maximum in (("material_prozent", "Material in %", Decimal(100)),
                                        ("zuschlag_prozent", "Zuschlag in %", Decimal(100)),
                                        ("anfahrten_pro_monat", "Anfahrten pro Monat", Decimal(100)),
                                        ("anfahrt_minuten", "Minuten je Anfahrt", Decimal(300))):
        w = eingabe.get(name)
        werte[name] = Decimal(0) if w in (None, "") else zahl(w, beschriftung, Decimal(0), maximum, null_erlaubt=True)
    return {"positionen": positionen, "stundensatz_cent": stundensatz_cent, **werte}


# ---------------------------------------------------------------- Rechnung
def berechnen(d, stundensatz_einstellung_cent=0, heute=None):
    """Rechnet mit den geprüften Eingaben. Ergebnis ist JSON-fähig und enthält den vollständigen Rechenweg."""
    heute = heute or datetime.date.today()
    warnungen, hinweise, rechenweg = [], [], []

    if d["stundensatz_cent"]:
        satz, satz_quelle = d["stundensatz_cent"], "Eingabe"
    elif stundensatz_einstellung_cent:
        satz, satz_quelle = int(stundensatz_einstellung_cent), "Einstellungen"
    else:
        satz, satz_quelle = None, "offen"

    positionen, stunden_reinigung = [], Decimal(0)
    for p in d["positionen"]:
        stunden = p["flaeche_m2"] / p["leistungswert_m2_h"] * p["reinigungen_pro_monat"]
        stunden_reinigung += stunden
        if p["reinigungen_pro_woche"] is not None:
            monat_text = "%s × 52 ÷ 12 = %s Reinigungen/Monat" % (deutsch(p["reinigungen_pro_woche"]),
                                                                  deutsch(p["reinigungen_pro_monat"], 2))
        else:
            monat_text = "%s Reinigungen/Monat" % deutsch(p["reinigungen_pro_monat"])
        if p["reinigungen_pro_woche"] is not None:
            faktor = "%s (= %s × 52 ÷ 12)" % (deutsch(p["reinigungen_pro_monat"], 2), deutsch(p["reinigungen_pro_woche"]))
        else:
            faktor = deutsch(p["reinigungen_pro_monat"])
        rechnung = "%s: %s m² ÷ %s m²/h × %s = %s h/Monat" % (
            p["bezeichnung"], deutsch(p["flaeche_m2"]), deutsch(p["leistungswert_m2_h"]), faktor, deutsch(stunden, 2))
        rechenweg.append(rechnung)
        if p["leistungswert_m2_h"] > LEISTUNGSWERT_WARNUNG:
            warnungen.append("%s: Leistungswert %s m²/h ist ungewöhnlich hoch – bitte prüfen (am besten mit einer "
                             "Probereinigung selbst messen)." % (p["bezeichnung"], deutsch(p["leistungswert_m2_h"])))
        positionen.append({
            "bezeichnung": p["bezeichnung"], "flaeche_m2": float(p["flaeche_m2"]),
            "leistungswert_m2_h": float(p["leistungswert_m2_h"]),
            "reinigungen_pro_monat": float(round(p["reinigungen_pro_monat"], 4)),
            "reinigungen_pro_woche": float(p["reinigungen_pro_woche"]) if p["reinigungen_pro_woche"] is not None else None,
            "turnus": p["turnus"], "reinigungen_text": monat_text,
            "stunden_monat": float(round(stunden, 2)), "rechnung": rechnung,
        })

    anfahrt_stunden = d["anfahrten_pro_monat"] * d["anfahrt_minuten"] / 60
    if d["anfahrten_pro_monat"] and not d["anfahrt_minuten"]:
        warnungen.append("Anfahrten angegeben, aber keine Minuten je Anfahrt – Anfahrt wird mit 0 h gerechnet.")
    if anfahrt_stunden:
        rechenweg.append("Anfahrt: %s × %s min ÷ 60 = %s h/Monat" % (
            deutsch(d["anfahrten_pro_monat"]), deutsch(d["anfahrt_minuten"]), deutsch(anfahrt_stunden, 2)))
    stunden_gesamt = stunden_reinigung + anfahrt_stunden
    rechenweg.append("Stunden gesamt: %s h Reinigung + %s h Anfahrt = %s h/Monat" % (
        deutsch(stunden_reinigung, 2), deutsch(anfahrt_stunden, 2), deutsch(stunden_gesamt, 2)))

    ergebnis = {
        "positionen": positionen,
        "stunden_reinigung_monat": float(round(stunden_reinigung, 2)),
        "anfahrt": {"anfahrten_pro_monat": float(d["anfahrten_pro_monat"]),
                    "minuten": float(d["anfahrt_minuten"]), "stunden_monat": float(round(anfahrt_stunden, 2))},
        "stunden_gesamt_monat": float(round(stunden_gesamt, 2)),
        "material_prozent": float(d["material_prozent"]),
        "zuschlag_prozent": float(d["zuschlag_prozent"]),
        "stundensatz_cent": satz,
        "stundensatz": euro(satz) if satz else OFFEN,
        "stundensatz_quelle": satz_quelle,
        "netto": True,
    }

    if satz is None:
        for schluessel in ("reinigungskosten_cent", "material_cent", "anfahrtskosten_cent", "zwischensumme_cent",
                           "zuschlag_cent", "preis_monat_cent", "preis_jahr_cent"):
            ergebnis[schluessel] = None
        ergebnis["preis_monat"] = OFFEN
        ergebnis["preis_jahr"] = OFFEN
        warnungen.append("Kein Stundensatz festgelegt – die Stunden sind gerechnet, der Preis bleibt OFFEN. Den "
                         "Stundensatz legt ihr fest (Einstellungen oder Eingabe); AUTONOMOUS nimmt keinen an.")
        rechenweg.append("Preis: OFFEN – ohne Stundensatz kein Preis")
    else:
        reinigung = _cent(stunden_reinigung * satz)
        material = _cent(Decimal(reinigung) * d["material_prozent"] / 100)
        anfahrt = _cent(anfahrt_stunden * satz)
        zwischen = reinigung + material + anfahrt
        zuschlag = _cent(Decimal(zwischen) * d["zuschlag_prozent"] / 100)
        monat = zwischen + zuschlag
        rechenweg += [
            "Reinigungskosten: %s h × %s = %s" % (deutsch(stunden_reinigung, 2), euro(satz), euro(reinigung)),
            "Material: %s × %s %% = %s" % (euro(reinigung), deutsch(d["material_prozent"]), euro(material)),
            "Anfahrtskosten: %s h × %s = %s" % (deutsch(anfahrt_stunden, 2), euro(satz), euro(anfahrt)),
            "Zwischensumme: %s + %s + %s = %s" % (euro(reinigung), euro(material), euro(anfahrt), euro(zwischen)),
            "Zuschlag (Wagnis/Gewinn): %s × %s %% = %s" % (euro(zwischen), deutsch(d["zuschlag_prozent"]),
                                                          euro(zuschlag)),
            "Preis pro Monat (netto): %s + %s = %s" % (euro(zwischen), euro(zuschlag), euro(monat)),
            "Preis pro Jahr (netto): %s × 12 = %s" % (euro(monat), euro(monat * 12)),
        ]
        ergebnis.update({"reinigungskosten_cent": reinigung, "material_cent": material, "anfahrtskosten_cent": anfahrt,
                         "zwischensumme_cent": zwischen, "zuschlag_cent": zuschlag, "preis_monat_cent": monat,
                         "preis_jahr_cent": monat * 12, "preis_monat": euro(monat), "preis_jahr": euro(monat * 12)})
        warnungen += _lohn_warnungen(satz, d["positionen"], heute)
        hinweise.append(STUNDENSATZ_DECKT)

    if heute >= VERORDNUNG_ENDE:
        warnungen.append("Die Mindestlohn-Angaben haben den Stand %s; die Verordnung ist am 01.01.2027 ausgelaufen. "
                         "Aktuelle Werte prüfen, bevor ihr dem Vergleich vertraut." % WISSEN_STAND)
    else:
        hinweise.append("Branchen-Mindestlohn Gebäudereinigung: Lohngruppe 1 15,00 €/h, Lohngruppe 6 (Glas- und "
                        "Fassadenreinigung) 18,40 €/h seit 01.01.2026. Die Verordnung läuft am 01.01.2027 aus – neu "
                        "prüfen. Für Daueraufträge, die ins Jahr 2027 laufen: Preisanpassung bei Änderung von Tarif- "
                        "oder Mindestlohn vereinbaren (Wortlaut vom Steuerberater oder Anwalt prüfen lassen).")
    hinweise.append("Leistungswerte (m²/h) sind eure Eingaben. Am verlässlichsten: Probereinigung mit Stoppuhr je "
                    "Raumart – sie hängen stark von Möblierung, Verschmutzung und Boden ab.")
    hinweise.append("Alle Beträge netto. Umsatzsteuer ist ein offener Punkt: je nach Auftraggeber Regelbesteuerung "
                    "oder Steuerschuldnerschaft des Leistungsempfängers (§ 13b UStG) – mit dem Steuerberater klären. "
                    "Keine Steuer- oder Rechtsberatung.")
    ergebnis.update({"rechenweg": rechenweg, "warnungen": warnungen, "hinweise": hinweise,
                     "quellen": [MINDESTLOHN_QUELLE + " (Stand %s)" % WISSEN_STAND, UST_QUELLE],
                     "einordnung": "Rechnung nur mit euren Eingaben. Keine angenommenen Werte, keine Normzahlen."})
    return ergebnis


def _lohn_warnungen(satz, positionen, heute):
    if heute >= VERORDNUNG_ENDE:
        return []
    warnungen = []
    quelle = " Quelle: %s (Stand %s)." % (MINDESTLOHN_QUELLE, WISSEN_STAND)
    if satz < MINDESTLOHN_LG1_CENT:
        warnungen.append("Der Stundensatz %s liegt unter dem Branchen-Mindestlohn der Gebäudereinigung (Lohngruppe 1: "
                         "15,00 €/h seit 01.01.2026) – damit ist nicht einmal der Lohn gedeckt.%s"
                         % (euro(satz), quelle))
    elif satz < MINDESTLOHN_LG6_CENT and any(w in p["bezeichnung"].lower() for p in positionen for w in GLAS_WOERTER):
        warnungen.append("Glas-/Fenster-/Fassadenreinigung dabei: Der Stundensatz %s liegt unter dem Mindestlohn der "
                         "Lohngruppe 6 (18,40 €/h seit 01.01.2026).%s" % (euro(satz), quelle))
    return warnungen


# ---------------------------------------------------------------- Übernahme ins Angebot
def aus_aufgabe(aufgabe):
    """Liest eine abgeschlossene Kalkulations-Aufgabe für ein Angebot aus.

    Gibt {aufgabe_id, positionen:[{bezeichnung, flaeche_m2, turnus}], preis_monat_cent|None} zurück."""
    if not aufgabe:
        raise KeyError("Kalkulation nicht gefunden.")
    if aufgabe.get("typ") != "kalkulation_reinigung":
        raise ValueError("Die angegebene Aufgabe ist keine Reinigungs-Kalkulation.")
    if aufgabe.get("status") != "abgeschlossen" or not isinstance(aufgabe.get("ergebnis"), dict):
        raise ValueError("Die Kalkulation ist noch nicht abgeschlossen.")
    e = aufgabe["ergebnis"]
    positionen = []
    for p in (e.get("positionen") or [])[:MAX_POSITIONEN]:
        if isinstance(p, dict) and p.get("bezeichnung"):
            positionen.append({"bezeichnung": str(p["bezeichnung"])[:80],
                               "flaeche_m2": p.get("flaeche_m2"), "turnus": str(p.get("turnus") or "")[:40]})
    if not positionen:
        raise ValueError("Die Kalkulation enthält keine Positionen.")
    preis = e.get("preis_monat_cent")
    if preis is not None and (isinstance(preis, bool) or not isinstance(preis, int) or preis <= 0):
        raise ValueError("Die Kalkulation enthält keinen gültigen Preis.")
    return {"aufgabe_id": aufgabe["id"], "positionen": positionen, "preis_monat_cent": preis}
