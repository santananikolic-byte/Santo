# -*- coding: utf-8 -*-
"""Betrieb - die gemeinsamen Geschäftsdaten: Kunden, Kundenaufträge, Angebote, Rechnungen, Einnahmen und Ausgaben,
Mitarbeiter, Stunden, feste Kosten.

Alle Erweiterungen aus dem Bereich Betrieb (Auftragsbuch, Angebote, Rechnungen, Kasse, Liquidität, Personal,
Chefbericht …) arbeiten mit DIESEN Tabellen - so passt alles zusammen: Der Chefbericht sieht die Rechnungen, die
Liquidität die offenen Forderungen, die Kundenakte die Aufträge.

Regeln, die hier gelten:

* **Geld immer in Cent** (ganze Zahlen) - nie mit Kommazahlen rechnen. ``euro_zu_cent("1.234,56 €")`` -> 123456,
  ``euro(123456)`` -> "1.234,56 €". Gerundet wird kaufmännisch (ab ,5 auf).
* **Kundenaufträge heißen hier "auftraege"** - nicht zu verwechseln mit den Aufträgen an JARVIS' Team (Kern).
* **Angebote und Rechnungen sind Entwürfe**, bis der Nutzer sie geprüft hat (Status "geprueft"). Abgegeben,
  verschickt oder bezahlt wird nichts von JARVIS selbst - CLAUDE.md: keine Preise zusagen ohne Prüfung.
* **Keine Bankdaten**: Eine IBAN speichert JARVIS nicht (CLAUDE.md: keine Zahlungsdaten in Dateien). Auf Rechnungen
  steht ein Platzhalter, den der Nutzer selbst ausfüllt.
* Die Daten gehören zum Geschäftsbereich (``bereich(konfig)``). In anderen Bereichen zeigen die Werkzeuge sie nicht.
"""

import datetime
import json
import re
import threading
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

from .tabelle import Tabelle
from .werkzeuge import WerkzeugFehler

KUNDEN_ARTEN = ("firma", "verwaltung", "oeffentlich", "privat")
AUFTRAG_ARTEN = ("reinigung", "bau", "sonstiges")
AUFTRAG_STATUS = ("anfrage", "besichtigung", "angebot", "beauftragt", "in_arbeit", "abgeschlossen", "abgerechnet",
                  "verloren", "storniert")
AUFTRAG_OFFEN = ("anfrage", "besichtigung", "angebot")
AUFTRAG_LAUFEND = ("beauftragt", "in_arbeit")
RHYTHMEN = ("einmalig", "taeglich", "woechentlich", "14-taegig", "monatlich", "vierteljaehrlich", "jaehrlich")
ANGEBOT_STATUS = ("entwurf", "geprueft", "abgegeben", "angenommen", "abgelehnt", "abgelaufen")
RECHNUNG_STATUS = ("entwurf", "geprueft", "gestellt", "teilbezahlt", "bezahlt", "storniert")
RECHNUNG_OFFEN = ("gestellt", "teilbezahlt")
BUCHUNG_ARTEN = ("einnahme", "ausgabe")
BESCHAEFTIGUNG = ("minijob", "teilzeit", "vollzeit", "aushilfe", "subunternehmer")
KOSTEN_RHYTHMEN = ("monatlich", "vierteljaehrlich", "jaehrlich", "einmalig")
MWST_SAETZE = (19, 7, 0)
FIRMA_FELDER = ("name", "inhaber", "strasse", "plz", "ort", "telefon", "email", "webseite", "steuernummer", "ust_id")
FIRMA_PLATZHALTER = "[%s – bitte eintragen]"
BANK_PLATZHALTER = "[Bankverbindung – bitte selbst eintragen; JARVIS speichert keine Bankdaten]"
MAX_BETRAG_CENT = 10 ** 10  # 100 Millionen Euro - alles darüber ist ein Tippfehler

KUNDEN = Tabelle("betrieb_kunden", (
    ("name", "TEXT NOT NULL"), ("art", "TEXT NOT NULL DEFAULT 'firma'"), ("ansprechpartner", "TEXT"),
    ("telefon", "TEXT"), ("email", "TEXT"), ("strasse", "TEXT"), ("plz", "TEXT"), ("ort", "TEXT"), ("quelle", "TEXT"),
    ("notiz", "TEXT"), ("erstellt", "TEXT"), ("geaendert", "TEXT")), indizes=(("name",),))

AUFTRAEGE = Tabelle("betrieb_auftraege", (
    ("kunde_id", "INTEGER"), ("titel", "TEXT NOT NULL"), ("art", "TEXT NOT NULL DEFAULT 'reinigung'"),
    ("status", "TEXT NOT NULL DEFAULT 'anfrage'"), ("ort", "TEXT"), ("beginn", "TEXT"), ("ende", "TEXT"),
    ("rhythmus", "TEXT NOT NULL DEFAULT 'einmalig'"), ("wert_cent", "INTEGER"), ("monatlich_cent", "INTEGER"),
    ("quelle", "TEXT"), ("notiz", "TEXT"), ("erstellt", "TEXT"), ("geaendert", "TEXT")),
    indizes=(("status",), ("kunde_id",)))

ANGEBOTE = Tabelle("betrieb_angebote", (
    ("nummer", "TEXT UNIQUE"), ("kunde_id", "INTEGER"), ("auftrag_id", "INTEGER"), ("titel", "TEXT NOT NULL"),
    ("positionen", "TEXT"), ("netto_cent", "INTEGER NOT NULL DEFAULT 0"), ("mwst_satz", "INTEGER NOT NULL DEFAULT 19"),
    ("mwst_cent", "INTEGER NOT NULL DEFAULT 0"), ("brutto_cent", "INTEGER NOT NULL DEFAULT 0"),
    ("status", "TEXT NOT NULL DEFAULT 'entwurf'"), ("gueltig_bis", "TEXT"), ("datei", "TEXT"), ("notiz", "TEXT"),
    ("erstellt", "TEXT"), ("geaendert", "TEXT")), json=("positionen",), indizes=(("status",), ("kunde_id",)))

RECHNUNGEN = Tabelle("betrieb_rechnungen", (
    ("nummer", "TEXT UNIQUE"), ("kunde_id", "INTEGER"), ("auftrag_id", "INTEGER"), ("angebot_id", "INTEGER"),
    ("titel", "TEXT"), ("positionen", "TEXT"), ("netto_cent", "INTEGER NOT NULL DEFAULT 0"),
    ("mwst_satz", "INTEGER NOT NULL DEFAULT 19"), ("mwst_cent", "INTEGER NOT NULL DEFAULT 0"),
    ("brutto_cent", "INTEGER NOT NULL DEFAULT 0"), ("rechnungsdatum", "TEXT"), ("leistungszeitraum", "TEXT"),
    ("faellig", "TEXT"), ("status", "TEXT NOT NULL DEFAULT 'entwurf'"), ("bezahlt_cent", "INTEGER NOT NULL DEFAULT 0"),
    ("bezahlt_am", "TEXT"), ("mahnstufe", "INTEGER NOT NULL DEFAULT 0"), ("datei", "TEXT"), ("notiz", "TEXT"),
    ("erstellt", "TEXT"), ("geaendert", "TEXT")), json=("positionen",), indizes=(("status",), ("faellig",), ("kunde_id",)))

BUCHUNGEN = Tabelle("betrieb_buchungen", (
    ("datum", "TEXT NOT NULL"), ("art", "TEXT NOT NULL"), ("betrag_cent", "INTEGER NOT NULL"), ("kategorie", "TEXT"),
    ("text", "TEXT"), ("rechnung_id", "INTEGER"), ("auftrag_id", "INTEGER"), ("beleg", "TEXT"), ("erstellt", "TEXT")),
    indizes=(("datum",),))

MITARBEITER = Tabelle("betrieb_mitarbeiter", (
    ("name", "TEXT NOT NULL"), ("taetigkeit", "TEXT"), ("beschaeftigung", "TEXT"), ("stundenlohn_cent", "INTEGER"),
    ("wochenstunden", "REAL"), ("eintritt", "TEXT"), ("austritt", "TEXT"), ("telefon", "TEXT"), ("notiz", "TEXT"),
    ("aktiv", "INTEGER NOT NULL DEFAULT 1"), ("erstellt", "TEXT"), ("geaendert", "TEXT")))

STUNDEN = Tabelle("betrieb_stunden", (
    ("mitarbeiter_id", "INTEGER NOT NULL"), ("auftrag_id", "INTEGER"), ("datum", "TEXT NOT NULL"),
    ("minuten", "INTEGER NOT NULL"), ("notiz", "TEXT"), ("erstellt", "TEXT")),
    indizes=(("datum",), ("mitarbeiter_id",)))

FIXKOSTEN = Tabelle("betrieb_fixkosten", (
    ("name", "TEXT NOT NULL"), ("betrag_cent", "INTEGER NOT NULL"), ("rhythmus", "TEXT NOT NULL DEFAULT 'monatlich'"),
    ("faellig_tag", "INTEGER"), ("kategorie", "TEXT"), ("beginn", "TEXT"), ("ende", "TEXT"), ("notiz", "TEXT"),
    ("erstellt", "TEXT"), ("geaendert", "TEXT")))

TABELLEN = (KUNDEN, AUFTRAEGE, ANGEBOTE, RECHNUNGEN, BUCHUNGEN, MITARBEITER, STUNDEN, FIXKOSTEN)

_nummer_sperre = threading.Lock()


# ------------------------------------------------------------------- Geld ---

def euro_zu_cent(wert):
    """Ein Betrag in EURO (Text oder Zahl) -> ganze Cent. "1.234,56 €" -> 123456, "12,5" -> 1250, "1234.5" -> 123450,
    "1.234" -> 123400 (deutscher Tausenderpunkt). Wirft WerkzeugFehler bei Unlesbarem."""
    if isinstance(wert, bool):
        raise WerkzeugFehler("Betrag nicht lesbar: %r." % (wert,))
    if isinstance(wert, (int, Decimal)):
        betrag = Decimal(wert)
    elif isinstance(wert, float):
        betrag = Decimal(repr(wert))
    else:
        text = re.sub(r"(?i)\s|€|eur(o)?\b", "", str(wert or "").replace(" ", ""))
        if not re.match(r"^-?[\d.,]*\d[\d.,]*$", text):
            raise WerkzeugFehler("Betrag nicht lesbar: %r. Beispiel: 1.234,56" % (wert,))
        if "," in text and "." in text:  # das hintere Zeichen trennt die Cent ab
            tausend, dezimal = (".", ",") if text.rfind(",") > text.rfind(".") else (",", ".")
            text = text.replace(tausend, "").replace(dezimal, ".")
        elif "," in text:
            if text.count(",") > 1:
                raise WerkzeugFehler("Betrag nicht lesbar: %r." % (wert,))
            text = text.replace(",", ".")
        elif text.count(".") > 1 or re.search(r"\.\d{3}$", text):
            text = text.replace(".", "")  # 1.234 oder 1.234.567: Tausenderpunkte
        try:
            betrag = Decimal(text)
        except InvalidOperation:
            raise WerkzeugFehler("Betrag nicht lesbar: %r." % (wert,)) from None
    cent = int((betrag * 100).quantize(Decimal(1), rounding=ROUND_HALF_UP))
    if abs(cent) >= MAX_BETRAG_CENT:
        raise WerkzeugFehler("Der Betrag %r ist unrealistisch groß - bitte prüfen." % (wert,))
    return cent


def euro(cent, zeichen=True):
    """123456 -> "1.234,56 €" (deutsches Format)."""
    cent = int(cent or 0)
    vorzeichen = "-" if cent < 0 else ""
    ganz, rest = divmod(abs(cent), 100)
    text = "%s%s,%02d" % (vorzeichen, "{:,}".format(ganz).replace(",", "."), rest)
    return text + " €" if zeichen else text


def mwst(netto_cent, satz):
    """(MwSt in Cent, Brutto in Cent) - kaufmännisch gerundet auf die Summe."""
    if satz not in MWST_SAETZE:
        raise WerkzeugFehler("MwSt-Satz %r gibt es nicht; möglich: %s %%." % (satz, ", ".join(map(str, MWST_SAETZE))))
    steuer = int((Decimal(int(netto_cent)) * satz / 100).quantize(Decimal(1), rounding=ROUND_HALF_UP))
    return steuer, int(netto_cent) + steuer


def menge(wert):
    """Menge als Decimal: "12,5" -> Decimal("12.5"). Wirft WerkzeugFehler."""
    text = str(wert if wert is not None else "").strip().replace(",", ".")
    try:
        zahl = Decimal(text)
    except InvalidOperation:
        raise WerkzeugFehler("Menge nicht lesbar: %r." % (wert,)) from None
    if not zahl.is_finite() or zahl <= 0 or zahl > 1000000:
        raise WerkzeugFehler("Menge %r: muss größer als 0 und realistisch sein." % (wert,))
    return zahl


def positionen_rechnen(positionen):
    """Prüft Positionen [{text, menge, einheit, einzel_cent}] und rechnet je Zeile summe_cent (Menge × Einzelpreis,
    kaufmännisch gerundet). Gibt (Positionen, Netto in Cent) zurück. So steht der Rechenweg in jeder Zeile."""
    if not positionen:
        raise WerkzeugFehler("Mindestens eine Position ist nötig.")
    if len(positionen) > 100:
        raise WerkzeugFehler("Höchstens 100 Positionen.")
    fertig, netto = [], 0
    for nr, p in enumerate(positionen, 1):
        text = " ".join(str(p.get("text") or "").split())[:300]
        if not text:
            raise WerkzeugFehler("Position %d: Beschreibung fehlt." % nr)
        anzahl = menge(p.get("menge", 1))
        einzel = int(p.get("einzel_cent"))
        if abs(einzel) >= MAX_BETRAG_CENT:
            raise WerkzeugFehler("Position %d: Einzelpreis unrealistisch." % nr)
        summe = int((anzahl * einzel).quantize(Decimal(1), rounding=ROUND_HALF_UP))
        fertig.append({"nr": nr, "text": text, "menge": format(anzahl.normalize(), "f").replace(".", ","),
                       "einheit": " ".join(str(p.get("einheit") or "").split())[:20], "einzel_cent": einzel,
                       "summe_cent": summe})
        netto += summe
    return fertig, netto


def summen(netto_cent, satz=19):
    steuer, brutto = mwst(netto_cent, satz)
    return {"netto_cent": int(netto_cent), "mwst_satz": satz, "mwst_cent": steuer, "brutto_cent": brutto}


# ----------------------------------------------------------------- Datum ---

def datum(text, heute=None):
    """"2026-11-17", "17.11.2026", "17.11.", "heute", "morgen", "gestern" -> "2026-11-17". Wirft WerkzeugFehler."""
    heute = heute or datetime.date.today()
    t = str(text or "").strip().lower()
    relativ = {"heute": 0, "morgen": 1, "übermorgen": 2, "uebermorgen": 2, "gestern": -1}
    if t in relativ:
        return (heute + datetime.timedelta(days=relativ[t])).isoformat()
    try:
        m = re.match(r"^(\d{4})-(\d{1,2})-(\d{1,2})$", t)
        if m:
            return datetime.date(int(m.group(1)), int(m.group(2)), int(m.group(3))).isoformat()
        m = re.match(r"^(\d{1,2})\.(\d{1,2})\.(\d{2}|\d{4})?$", t)
        if m:
            jahr = int(m.group(3)) if m.group(3) else heute.year
            jahr += 2000 if jahr < 100 else 0
            return datetime.date(jahr, int(m.group(2)), int(m.group(1))).isoformat()
    except ValueError:
        pass
    raise WerkzeugFehler("Datum nicht lesbar: %r. Beispiel: 17.11.2026 oder 2026-11-17." % (text,))


def datum_text(iso):
    """"2026-11-17" -> "17.11.2026" (leer bleibt leer)."""
    try:
        return datetime.date.fromisoformat(str(iso)[:10]).strftime("%d.%m.%Y") if iso else ""
    except ValueError:
        return str(iso)


# ---------------------------------------------------------------- Bereich ---

def bereich(konfig):
    """Der Geschäftsbereich: "geschaeft", sonst der erste Bereich der Konfiguration."""
    bereiche = list(getattr(konfig, "bereiche", None) or ["geschaeft"])
    return "geschaeft" if "geschaeft" in bereiche else bereiche[0]


def nur_geschaeft(ctx):
    """Betriebsdaten nur im Geschäftsbereich - im privaten Gespräch bleiben sie draußen (Bereichstrennung)."""
    if ctx.bereich != bereich(ctx.agent.konfig):
        raise WerkzeugFehler("Das gehört zum Geschäftsbereich. Wechsle oben auf „%s“, dann geht es."
                             % bereich(ctx.agent.konfig).capitalize())


# ---------------------------------------------------------------- Nummern ---

def naechste_nummer(sp, art, jahr=None):
    """Fortlaufende Nummer je Art und Jahr: art "A" (Angebot) -> "A-2026-0001", "R" (Rechnung) -> "R-2026-0001".
    Rechnungsnummern müssen eindeutig und fortlaufend sein - deshalb vergibt nur diese Funktion sie."""
    if not re.match(r"^[A-Z]{1,3}$", art or ""):
        raise ValueError("art: ein bis drei Großbuchstaben")
    jahr = int(jahr or datetime.date.today().year)
    schluessel = "betrieb:nummer:%s:%d" % (art, jahr)
    with _nummer_sperre:
        nr = int(sp.meta(schluessel) or 0) + 1
        sp.meta_setzen(schluessel, str(nr))
    return "%s-%d-%04d" % (art, jahr, nr)


# ----------------------------------------------------------------- Kunden ---

def _like(text):
    return "%" + text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"


def kunde_finden(sp, angabe):
    """Kunde nach Nummer ("#12", "12") oder Name (genau, sonst Teil des Namens). Gibt den Kunden oder None zurück;
    passen mehrere, kommt ein WerkzeugFehler mit den Kandidaten (dann bitte genauer fragen)."""
    text = " ".join(str(angabe or "").split())
    if not text:
        return None
    m = re.match(r"^#?(\d{1,9})$", text)
    if m:
        return KUNDEN.holen(sp, int(m.group(1)))
    genau = KUNDEN.liste(sp, wo="lower(name)=lower(?)", werte=(text,), limit=5)
    if len(genau) == 1:
        return genau[0]
    treffer = genau or KUNDEN.liste(sp, wo="lower(name) LIKE lower(?) ESCAPE '\\'", werte=(_like(text),), limit=6)
    if len(treffer) > 1:
        raise WerkzeugFehler("Mehrere Kunden passen: %s. Bitte genauer oder mit Nummer (z. B. #%d)."
                             % ("; ".join("#%d %s" % (k["id"], k["name"]) for k in treffer[:5]), treffer[0]["id"]))
    return treffer[0] if treffer else None


def kunde_anlegen(sp, name, **felder):
    name = " ".join(str(name or "").split())[:120]
    if not name:
        raise WerkzeugFehler("Der Kunde braucht einen Namen.")
    if felder.get("art") and felder["art"] not in KUNDEN_ARTEN:
        raise WerkzeugFehler("Kundenart: %s." % ", ".join(KUNDEN_ARTEN))
    return KUNDEN.anlegen(sp, name=name, **felder)


def kunde_oder_neu(sp, angabe):
    """(Kunde, neu angelegt?) - findet den Kunden oder legt ihn mit diesem Namen an."""
    kunde = kunde_finden(sp, angabe)
    if kunde:
        return kunde, False
    if re.match(r"^#?\d+$", str(angabe or "").strip()):
        raise WerkzeugFehler("Einen Kunden mit der Nummer %s gibt es nicht." % angabe)
    return KUNDEN.holen(sp, kunde_anlegen(sp, angabe)), True


def kunde_name(sp, kunde_id):
    kunde = KUNDEN.holen(sp, kunde_id) if kunde_id else None
    return kunde["name"] if kunde else ""


# ------------------------------------------------------------------ Firma ---

def firma(sp):
    """Die eigenen Firmendaten (für Angebote und Rechnungen). Fehlendes bleibt None - nie erfunden."""
    try:
        daten = json.loads(sp.meta("betrieb:firma") or "{}")
    except ValueError:
        daten = {}
    return {feld: (str(daten.get(feld)).strip() or None) if daten.get(feld) else None for feld in FIRMA_FELDER}


def firma_setzen(sp, **felder):
    unbekannt = set(felder) - set(FIRMA_FELDER)
    if unbekannt:
        raise WerkzeugFehler("Unbekannte Firmenangabe: %s. Möglich: %s." % (", ".join(sorted(unbekannt)),
                                                                         ", ".join(FIRMA_FELDER)))
    if any(re.search(r"\bDE\d{2}[\s\d]{12,}", str(v or "")) for v in felder.values()):
        raise WerkzeugFehler("Bankdaten (IBAN) speichert JARVIS nicht - die trägst du selbst ins Dokument ein.")
    daten = firma(sp)
    for feld, wert in felder.items():
        daten[feld] = " ".join(str(wert or "").split())[:160] or None
    sp.meta_setzen("betrieb:firma", json.dumps(daten, ensure_ascii=False))
    return daten


def firma_text(sp, feld, titel):
    """Ein Feld der Firmendaten oder der Platzhalter „[Titel – bitte eintragen]“."""
    return firma(sp).get(feld) or FIRMA_PLATZHALTER % titel


# ------------------------------------------------------------- Kennzahlen ---

def kennzahlen(sp, heute=None):
    """Die wichtigsten Zahlen aus den Betriebsdaten - nur gezählt und summiert, nichts geschätzt."""
    heute = (heute or datetime.date.today()).isoformat()
    monat = heute[:7]
    offen_status = ",".join("?" * len(RECHNUNG_OFFEN))
    offen = RECHNUNGEN.liste(sp, wo="status IN (%s)" % offen_status, werte=RECHNUNG_OFFEN, limit=10000)
    ueberfaellig = [r for r in offen if r.get("faellig") and r["faellig"] < heute]
    dauer = AUFTRAEGE.liste(sp, wo="rhythmus != 'einmalig' AND status IN (?, ?)", werte=AUFTRAG_LAUFEND, limit=10000)
    return {
        "auftraege_offen": AUFTRAEGE.zaehlen(sp, "status IN (?, ?, ?)", AUFTRAG_OFFEN),
        "auftraege_laufend": AUFTRAEGE.zaehlen(sp, "status IN (?, ?)", AUFTRAG_LAUFEND),
        "dauerauftraege": len(dauer),
        "dauerauftraege_monatlich_cent": sum(int(a.get("monatlich_cent") or 0) for a in dauer),
        "angebote_offen": ANGEBOTE.zaehlen(sp, "status IN ('geprueft', 'abgegeben')"),
        "angebote_offen_cent": ANGEBOTE.summe(sp, "netto_cent", "status IN ('geprueft', 'abgegeben')"),
        "rechnungen_offen": len(offen),
        "forderungen_cent": sum(int(r["brutto_cent"]) - int(r["bezahlt_cent"]) for r in offen),
        "ueberfaellig": len(ueberfaellig),
        "ueberfaellig_cent": sum(int(r["brutto_cent"]) - int(r["bezahlt_cent"]) for r in ueberfaellig),
        "einnahmen_monat_cent": BUCHUNGEN.summe(sp, "betrag_cent", "art='einnahme' AND substr(datum, 1, 7)=?", (monat,)),
        "ausgaben_monat_cent": BUCHUNGEN.summe(sp, "betrag_cent", "art='ausgabe' AND substr(datum, 1, 7)=?", (monat,)),
        "mitarbeiter_aktiv": MITARBEITER.zaehlen(sp, "aktiv=1"),
    }
