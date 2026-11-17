# -*- coding: utf-8 -*-
"""Rechner - JARVIS rechnet nie im Kopf: genau, mit Rechenweg (Muster-Erweiterung für alle anderen).

* ``rechnen``: Grundrechenarten mit deutschen Zahlen ("12,5 * 4 + 19 %"), exakt (Decimal) und mit Rechenweg.
* ``reinigung_kalkulieren``: Preis einer Reinigung aus Fläche, Leistungswert und Stundensatz - jede Zahl kommt vom
  Nutzer, nichts ist geschätzt. Der Rechenweg steht dabei, damit Vater und Sohn ihn prüfen können.
* Sofort-Antwort: "Was ist 17 * 23?" beantwortet JARVIS ohne Modell - schnell und ohne Rechenfehler.

Warum das wichtig ist: Sprachmodelle verrechnen sich, besonders kleine. Ein Preis, der falsch gerechnet ist, kostet
Geld oder den Auftrag.
"""

import ast
import operator
import re
from decimal import ROUND_HALF_UP, Decimal, DivisionByZero, InvalidOperation, Overflow, getcontext

from . import FREI, Baustein, P, Werkzeug, WerkzeugFehler, einstellung, einstellung_setzen, heute, muster
from .. import betrieb

NAME = "Rechner"
BEREICH = "gehirn"
BESCHREIBUNG = "Rechnet exakt mit Rechenweg und kalkuliert Reinigungspreise aus euren eigenen Werten."
PRIORITAET = 40
GRUENDLICH = False
IMMER_SICHTBAR = ("rechnen",)
FUER_AGENTEN = {
    "rechnen": ("kalkulationsleiter", "kalk_unterhalt", "kalk_treppenhaus", "kalk_glas", "kalk_grundreinigung",
                "kalk_bauend", "kalk_winterdienst", "kalk_hausmeister", "kalk_gruenpflege", "kalk_bau",
                "kalk_entruempelung", "stundensatz", "angebotsschreiber", "nachkalkulation", "finanzleiter",
                "rechnung", "liquiditaet", "kosten"),
    "reinigung_kalkulieren": ("kalkulationsleiter", "kalk_unterhalt", "kalk_treppenhaus", "kalk_glas",
                              "kalk_grundreinigung", "kalk_bauend", "angebotsschreiber"),
}

MAX_AUSDRUCK = 200
WOCHEN_JE_MONAT = Decimal(52) / Decimal(12)  # 4,333… - so rechnen Reinigungsbetriebe Monatspreise
_OPERATOREN = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul, ast.Div: operator.truediv}
_ZEICHEN = {ast.Add: "+", ast.Sub: "-", ast.Mult: "×", ast.Div: ":"}
_ERLAUBT = re.compile(r"^[\d\s.,+\-*/×x:÷()%]+$")
_FRAGE = re.compile(r"^(?:(?:hey |ok )?jarvis[,!.:]?\s*)?(?P<frage>was (?:ist|sind|ergibt|macht)|wie ?viel (?:ist|sind|macht|"
                    r"ergibt)|rechne(?: mal| bitte)?|berechne)?\s*(?P<ausdruck>[\d\s.,+\-*/×x:÷()%]+?)\s*(?P<ende>[=?]?)"
                    r"[!.]*$", re.IGNORECASE)


class RechenFehler(WerkzeugFehler):
    """Ausdruck nicht rechenbar - der Text sagt, warum."""


# ------------------------------------------------------------- rechnen ---

def _zahl(text):
    """Deutsche Zahl -> Decimal: "1.234,5" -> 1234.5, "12,5" -> 12.5, "1234.5" -> 1234.5."""
    t = text.strip()
    if "," in t:
        t = t.replace(".", "").replace(",", ".")
    elif t.count(".") > 1 or re.match(r"^\d{1,3}\.\d{3}$", t):
        t = t.replace(".", "")
    return Decimal(t)


def _vorbereiten(ausdruck):
    """Deutsche Schreibweise -> Python-Ausdruck mit Decimal-Zahlen. "19 %" wird zu "*0,19" auf die Zahl davor;
    "100 + 19 %" heißt (wie am Taschenrechner) 100 plus 19 % von 100."""
    a = " ".join(str(ausdruck or "").split())
    if not a or len(a) > MAX_AUSDRUCK:
        raise RechenFehler("Bitte einen Ausdruck mit höchstens %d Zeichen angeben, z. B. 12,5 * 4." % MAX_AUSDRUCK)
    if not _ERLAUBT.match(a):
        raise RechenFehler("Erlaubt sind nur Zahlen, + - * / : ( ) und %.")
    a = a.replace("×", "*").replace("÷", "/").replace(":", "/")
    a = re.sub(r"(?<=[\d)\s])x(?=[\s\d(])", "*", a)
    zahlen = []

    def merken(treffer):
        zahlen.append(_zahl(treffer.group(0)))
        return "Z%d" % (len(zahlen) - 1)

    a = re.sub(r"\d+(?:[.,]\d+)*", merken, a)
    a = re.sub(r"(Z\d+)\s*%", r"P(\1)", a)  # Prozent: siehe _auswerten
    if "%" in a or "x" in a:
        raise RechenFehler("Das Prozentzeichen bitte direkt hinter eine Zahl schreiben (z. B. 19 %).")
    return a, zahlen


def _prozent(knoten):
    return (isinstance(knoten, ast.Call) and isinstance(knoten.func, ast.Name) and knoten.func.id == "P"
            and len(knoten.args) == 1 and not knoten.keywords)


def _auswerten(knoten, zahlen):
    """Wie ein Taschenrechner: "A + B %" = A plus B Prozent von A (alles links vom +), "A * B %" = B Prozent von A."""
    if isinstance(knoten, ast.Expression):
        return _auswerten(knoten.body, zahlen)
    if isinstance(knoten, ast.Name) and re.match(r"^Z\d+$", knoten.id):
        return zahlen[int(knoten.id[1:])]
    if _prozent(knoten):
        return _auswerten(knoten.args[0], zahlen) / 100
    if isinstance(knoten, ast.BinOp) and isinstance(knoten.op, (ast.Add, ast.Sub)) and _prozent(knoten.right):
        links = _auswerten(knoten.left, zahlen)
        anteil = links * _auswerten(knoten.right.args[0], zahlen) / 100
        return links + anteil if isinstance(knoten.op, ast.Add) else links - anteil
    if isinstance(knoten, ast.BinOp) and type(knoten.op) in _OPERATOREN:
        links, rechts = _auswerten(knoten.left, zahlen), _auswerten(knoten.right, zahlen)
        if isinstance(knoten.op, ast.Div) and rechts == 0:
            raise RechenFehler("Durch 0 kann man nicht teilen.")
        return _OPERATOREN[type(knoten.op)](links, rechts)
    if isinstance(knoten, ast.UnaryOp) and isinstance(knoten.op, (ast.USub, ast.UAdd)):
        wert = _auswerten(knoten.operand, zahlen)
        return -wert if isinstance(knoten.op, ast.USub) else wert
    raise RechenFehler("Dieser Ausdruck lässt sich nicht rechnen.")


def zahl_text(wert, stellen=2):
    """Decimal -> deutsche Schreibweise mit höchstens ``stellen`` Nachkommastellen: 1234.5 -> "1.234,5"."""
    gerundet = wert.quantize(Decimal(1).scaleb(-stellen), rounding=ROUND_HALF_UP).normalize()
    if gerundet == gerundet.to_integral_value():
        gerundet = gerundet.quantize(Decimal(1))
    ganz, _, rest = format(gerundet, "f").partition(".")
    vorzeichen = "-" if ganz.startswith("-") else ""
    ganz = "{:,}".format(int(ganz.lstrip("-") or 0)).replace(",", ".")
    return vorzeichen + ganz + ("," + rest if rest else "")


def rechne(ausdruck):
    """Gibt (Ergebnis als Decimal, Rechenweg-Text) zurück. Wirft RechenFehler."""
    python, zahlen = _vorbereiten(ausdruck)
    try:
        baum = ast.parse(python, mode="eval")
    except SyntaxError:
        raise RechenFehler("Der Ausdruck ist unvollständig (fehlt eine Zahl oder Klammer?).") from None
    if sum(1 for _ in ast.walk(baum)) > 200:
        raise RechenFehler("Der Ausdruck ist zu lang.")
    alt = getcontext().prec
    try:
        getcontext().prec = 28
        ergebnis = _auswerten(baum, zahlen)
    except (InvalidOperation, DivisionByZero, Overflow):
        raise RechenFehler("Das lässt sich nicht genau rechnen.") from None
    finally:
        getcontext().prec = alt
    if abs(ergebnis) >= Decimal(10) ** 15:
        raise RechenFehler("Das Ergebnis ist unrealistisch groß - bitte den Ausdruck prüfen.")
    return ergebnis, "%s = %s" % (" ".join(str(ausdruck).split()), zahl_text(ergebnis, 4))


def _zaehlen(agent):
    tag = heute().isoformat()
    stand = einstellung(agent, "rechner", "heute", {}) or {}
    stand = {"tag": tag, "anzahl": (stand.get("anzahl", 0) if stand.get("tag") == tag else 0) + 1}
    einstellung_setzen(agent, "rechner", "heute", stand)


def _rechnen(ctx, p):
    _, weg = rechne(p["ausdruck"])
    _zaehlen(ctx.agent)
    return {"text": "Gerechnet (exakt): %s" % weg}


# ---------------------------------------------------- Reinigung kalkulieren ---

def _dezimal(p, name, minimum, maximum, einheit):
    try:
        wert = _zahl(str(p[name]))
    except (InvalidOperation, ValueError):
        raise WerkzeugFehler("%s ist keine Zahl: %r." % (name, p[name])) from None
    if not minimum <= wert <= maximum:
        raise WerkzeugFehler("%s: bitte zwischen %s und %s %s." % (name, zahl_text(Decimal(minimum)),
                                                                  zahl_text(Decimal(maximum)), einheit))
    return wert


def kalkulation(flaeche, leistung, stundensatz_cent, je_woche=None, anfahrt_minuten=0, zuschlag=Decimal(0)):
    """Die Rechnung selbst (für Tests und andere Erweiterungen): Zeilen des Rechenwegs und Beträge in Cent."""
    stunden = flaeche / leistung
    arbeit = stunden * Decimal(stundensatz_cent)
    anfahrt = Decimal(anfahrt_minuten) / 60 * Decimal(stundensatz_cent)
    je_reinigung = (arbeit + anfahrt) * (1 + zuschlag / 100)
    je_reinigung_cent = int(je_reinigung.quantize(Decimal(1), rounding=ROUND_HALF_UP))
    zeilen = ["Zeit je Reinigung: %s m² : %s m²/h = %s Stunden" % (zahl_text(flaeche), zahl_text(leistung),
                                                                   zahl_text(stunden, 2)),
              "Arbeit: %s h × %s = %s" % (zahl_text(stunden, 2), betrieb.euro(stundensatz_cent),
                                          betrieb.euro(int(arbeit.quantize(Decimal(1), rounding=ROUND_HALF_UP))))]
    if anfahrt_minuten:
        zeilen.append("Anfahrt: %d min = %s h × %s = %s" % (anfahrt_minuten, zahl_text(Decimal(anfahrt_minuten) / 60, 2),
                                                          betrieb.euro(stundensatz_cent),
                                                          betrieb.euro(int(anfahrt.quantize(Decimal(1), ROUND_HALF_UP)))))
    if zuschlag:
        zeilen.append("Zuschlag: %s %%" % zahl_text(zuschlag))
    zeilen.append("Je Reinigung (netto): %s" % betrieb.euro(je_reinigung_cent))
    monat_cent = None
    if je_woche:
        monat = je_reinigung * je_woche * WOCHEN_JE_MONAT
        monat_cent = int(monat.quantize(Decimal(1), rounding=ROUND_HALF_UP))
        zeilen.append("Im Monat: %s × %s je Woche × 4,33 Wochen (52 : 12) = %s netto"
                      % (betrieb.euro(je_reinigung_cent), zahl_text(je_woche), betrieb.euro(monat_cent)))
    return zeilen, je_reinigung_cent, monat_cent


def _reinigung_kalkulieren(ctx, p):
    flaeche = _dezimal(p, "flaeche", 1, 1000000, "m²")
    leistung = _dezimal(p, "leistungswert", 1, 10000, "m²/h")
    stundensatz = betrieb.euro_zu_cent(p["stundensatz"])
    if not 100 <= stundensatz <= 50000:
        raise WerkzeugFehler("stundensatz: bitte zwischen 1 und 500 Euro je Stunde.")
    je_woche = _dezimal(p, "je_woche", Decimal("0.1"), 21, "mal je Woche") if p.get("je_woche") else None
    zuschlag = _dezimal(p, "zuschlag", 0, 100, "%") if p.get("zuschlag") else Decimal(0)
    anfahrt = int(p.get("anfahrt_minuten") or 0)
    zeilen, _, _ = kalkulation(flaeche, leistung, stundensatz, je_woche, anfahrt, zuschlag)
    _zaehlen(ctx.agent)
    return {"text": "Kalkulation (alle Werte vom Nutzer, exakt gerechnet):\n- " + "\n- ".join(zeilen) +
                    "\nHinweis: Das ist ein Rechenergebnis, kein geprüfter Preis. Vor einem Angebot prüft ihr Leistungswert "
                    "und Stundensatz selbst."}


# --------------------------------------------------------------- Hooks ---

def werkzeuge():
    return [
        Werkzeug("rechnen", "Rechnet exakt mit Rechenweg: + - * / : ( ) und % (\"100 + 19 %\" = 119). Deutsche Zahlen "
                 "(12,5). Nutze es für JEDE Rechnung mit Beträgen, Mengen oder Preisen - nie im Kopf rechnen.",
                 _rechnen, [P("ausdruck", True, hilfe="z. B. 12,5 * 4 + 19 %", maximal=MAX_AUSDRUCK)],
                 stufe=FREI, liefert_daten=True),
        Werkzeug("reinigung_kalkulieren", "Kalkuliert den Preis einer Reinigung aus Fläche, Leistungswert (m² je "
                 "Stunde) und Stundensatz - mit Rechenweg. Alle Werte müssen vom Nutzer kommen, nie schätzen.",
                 _reinigung_kalkulieren,
                 [P("flaeche", True, hilfe="m², z. B. 450", maximal=20),
                  P("leistungswert", True, hilfe="m² je Stunde, z. B. 180 (von euch gemessen)", maximal=20),
                  P("stundensatz", True, hilfe="Euro je Stunde netto, z. B. 32,50", maximal=20),
                  P("je_woche", hilfe="wie oft je Woche, z. B. 2", maximal=10),
                  P("anfahrt_minuten", art="zahl", bereich=(0, 240)),
                  P("zuschlag", hilfe="Prozent, z. B. 10", maximal=10)],
                 stufe=FREI, liefert_daten=True),
    ]


def bausteine():
    return [Baustein(
        "rechner", "RECHNEN UND KALKULIEREN (exakt, mit Rechenweg)",
        muster(r"\brechne", r"\bberechne", r"kalkulier", r"\bqm\b", r"m²", r"quadratmeter", r"leistungswert",
               r"\bwie ?viel (kostet|kosten|macht|ergibt|sind)", r"\bmal\b.*\d|\d.*\bmal\b", r"\bprozent\b", r"\d\s*%"),
        (),
        "- Rechne NIE im Kopf: Jede Rechnung mit Beträgen, Mengen, Stunden oder Prozenten machst du mit \"rechnen\" "
        "und nennst den Rechenweg.\n"
        "- Für Reinigungspreise gibt es \"reinigung_kalkulieren\". Fläche, Leistungswert und Stundensatz kommen vom "
        "Nutzer - fehlt einer, frag nach (eine Frage, mit Grund). Den Stundensatz des Betriebs kennst du nicht, solange "
        "er nicht im Gedächtnis steht.\n"
        "- Ein Rechenergebnis ist noch kein Preis für den Kunden: Erst nach Prüfung durch den Nutzer wird daraus ein "
        "Angebot.",
        {})]


def sofort(agent, text, gespraech, bereich):
    """„Was ist 17 * 23?“ -> sofort, ohne Modell. Nur wenn der Text wirklich nur eine Rechnung ist."""
    treffer = _FRAGE.match(text.strip())
    if not treffer:
        return None
    ausdruck = treffer.group("ausdruck").strip()
    if not re.search(r"\d", ausdruck) or not re.search(r"\d\s*[-+*/×x:÷%]\s*[\d(]|\d\s*%", ausdruck):
        return None  # nur eine Zahl ("rechne 5") ist keine Rechnung
    if not (treffer.group("frage") or treffer.group("ende")) and not re.search(r"[+*/×x:÷%]", ausdruck):
        return None  # "3-4" allein ist eher eine Antwort ("3-4 Leute") als eine Rechnung
    if re.match(r"^\d{1,2}\.\d{1,2}\.(\d{2,4})?$", ausdruck) or re.match(r"^\d{1,2}:\d{2}$", ausdruck):
        return None  # 17.11.2026 oder 14:30 - Datum und Uhrzeit sind keine Rechnung
    try:
        _, weg = rechne(ausdruck)
    except WerkzeugFehler:
        return None  # dann soll das Modell nachfragen
    _zaehlen(agent)
    return "%s (exakt gerechnet)" % weg


def anzeige(agent, bereich):
    stand = einstellung(agent, "rechner", "heute", {}) or {}
    anzahl = stand.get("anzahl", 0) if stand.get("tag") == heute().isoformat() else 0
    return {"status": [("Heute gerechnet", "%d Mal" % anzahl)]}
