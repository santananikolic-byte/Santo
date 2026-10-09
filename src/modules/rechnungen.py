#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Rechnungen, Angebote und Mahnungen - als PDF, fortlaufend nummeriert, nachverfolgt.

Eine Rechnung entsteht aus Kunde und Positionen. Jarvis vergibt die Nummer
(2026-001, 2026-002 ...), rechnet Netto, Umsatzsteuer und Brutto, setzt das
Zahlungsziel und legt ein PDF im Ordner ``rechnungen`` ab. Danach weiß er,
was offen ist, was überfällig ist und wann gemahnt wurde. Wird eine Rechnung
bezahlt, landet die Einnahme gleich in der Buchhaltung.

**Pflichtangaben (Österreich, § 11 UStG).** Name und Anschrift des
Unternehmers und des Kunden, Menge und Bezeichnung der Leistung, Zeitraum der
Leistung, Entgelt, Steuersatz und Steuerbetrag, Ausstellungsdatum, fortlaufende
Nummer und - ab 400 Euro brutto - die eigene UID. Fehlt davon etwas in den
Firmendaten, sagt Jarvis es beim Erstellen. Ohne eigene Anschrift verschickt
er keine Rechnung.

**Steuer.** Standard ist der eingestellte Satz (20 %). Als Kleinunternehmer
gibt es keine Umsatzsteuer, dafür den Vermerk. Reinigung an Gebäuden gilt als
Bauleistung: Ist der Kunde selbst ein Bauunternehmer, schuldet er die Steuer
(Übergang der Steuerschuld) - das geht mit ``steuerschuld_umkehr``.

Jarvis hilft beim Schreiben. Die fachliche Prüfung bleibt beim Steuerberater.
"""

import json
import os
import re
import sqlite3
from datetime import datetime, timedelta

import config
from modules.memory import Memory, db_schema_anlegen, heute_datum, zeitstempel
from modules.pdf_dokument import PDF_SEITE_BREITE, PdfDokument, pdf_textbreite, pdf_umbrechen

SCHEMA_RECHNUNGEN = """
CREATE TABLE IF NOT EXISTS rechnungen (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    art TEXT NOT NULL,
    nummer TEXT NOT NULL UNIQUE,
    bezug TEXT DEFAULT '',
    kunde TEXT NOT NULL,
    adresse TEXT DEFAULT '',
    email TEXT DEFAULT '',
    kunde_uid TEXT DEFAULT '',
    datum TEXT NOT NULL,
    leistung TEXT DEFAULT '',
    faellig TEXT DEFAULT '',
    positionen TEXT DEFAULT '[]',
    netto REAL DEFAULT 0,
    mwst_satz REAL DEFAULT 0,
    mwst REAL DEFAULT 0,
    brutto REAL DEFAULT 0,
    vermerk TEXT DEFAULT '',
    status TEXT DEFAULT 'offen',
    bezahlt_am TEXT DEFAULT '',
    bezahlt_betrag REAL DEFAULT 0,
    mahnstufe INTEGER DEFAULT 0,
    mahn_spesen REAL DEFAULT 0,
    mahn_frist TEXT DEFAULT '',
    gemahnt_am TEXT DEFAULT '',
    mahn_pdf TEXT DEFAULT '',
    pdf TEXT DEFAULT '',
    gesendet_am TEXT DEFAULT '',
    notiz TEXT DEFAULT '',
    angelegt TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_rechnungen_status ON rechnungen(art, status);
"""

RECHNUNG_ZAHLUNGSZIEL = 14   # Tage
ANGEBOT_GUELTIG_TAGE = 30
MAHNUNG_FRIST_TAGE = 10
MAHNSTUFEN = ("Zahlungserinnerung", "1. Mahnung", "2. Mahnung")
KLEINBETRAG_GRENZE = 400.0   # brutto: darunter reicht eine Kleinbetragsrechnung
GROSSBETRAG_GRENZE = 10000.0  # brutto: darüber braucht es die UID des Kunden
VERMERK_KLEINUNTERNEHMER = ("Umsatzsteuerfrei aufgrund der Kleinunternehmerregelung "
                            "gemäß § 6 Abs. 1 Z 27 UStG.")
VERMERK_UMKEHR = ("Übergang der Steuerschuld gemäß § 19 Abs. 1a UStG (Bauleistung). "
                  "Die Umsatzsteuer ist vom Leistungsempfänger abzuführen.")
DOKUMENT_ARTEN = {"rechnung": "Rechnung", "angebot": "Angebot", "storno": "Stornorechnung"}
# Später dazugekommene Spalten - ältere Datenbanken bekommen sie beim Start.
RECHNUNG_NEUE_SPALTEN = (("bezahlt_betrag", "REAL DEFAULT 0"), ("mahn_spesen", "REAL DEFAULT 0"),
                         ("mahn_frist", "TEXT DEFAULT ''"))

# Briefbogen: Ränder 2 cm, Akzentfarbe Petrol.
BRIEF_LINKS = 56.7
BRIEF_RECHTS = PDF_SEITE_BREITE - 56.7
BRIEF_UNTEN = 760.0
BRIEF_AKZENT = (0.0, 0.42, 0.5)
BRIEF_GRAU = 0.42


def rechnung_euro(betrag) -> str:
    """1234.5 -> '1.234,50 €'."""
    try:
        betrag = float(betrag)
    except (TypeError, ValueError):
        betrag = 0.0
    text = "{:,.2f}".format(betrag).replace(",", "#").replace(".", ",").replace("#", ".")
    return text + " €"


def rechnung_datum(iso: str) -> str:
    """'2026-10-09' -> '09.10.2026'. Alles andere bleibt, wie es ist."""
    try:
        return datetime.strptime(str(iso)[:10], "%Y-%m-%d").strftime("%d.%m.%Y")
    except ValueError:
        return str(iso or "")


def rechnung_menge(wert) -> str:
    """4.333 -> '4,33', 2.0 -> '2'."""
    try:
        wert = float(wert)
    except (TypeError, ValueError):
        return str(wert or "")
    if wert == int(wert):
        return str(int(wert))
    return ("%.2f" % wert).rstrip("0").rstrip(".").replace(".", ",")


def _zahl_lesen(wert):
    """Zahl aus Text wie '1.250,50 €', '45,-' oder 45. Gibt None zurück, wenn es keine ist."""
    if isinstance(wert, (int, float)) and not isinstance(wert, bool):
        return float(wert)
    text = re.sub(r"[^\d,.\-]", "", str(wert or "")).rstrip("-").rstrip(",.")
    if not text or text in ("-", ".", ","):
        return None
    if "," in text and "." in text:
        # Was zuletzt steht, trennt die Cent: 1.250,50 (deutsch) oder 1,250.50 (englisch).
        if text.rfind(",") > text.rfind("."):
            text = text.replace(".", "").replace(",", ".")
        else:
            text = text.replace(",", "")
    elif "," in text:  # deutsche Schreibweise: Komma trennt die Cent
        text = text.replace(",", ".") if text.count(",") == 1 else text.replace(",", "")
    elif re.fullmatch(r"-?\d{1,3}(\.\d{3})+", text):
        text = text.replace(".", "")  # 1.250 oder 2.000.000: Tausenderpunkte
    try:
        return float(text)
    except ValueError:
        return None


def positionen_pruefen(positionen, preise_brutto: bool = False, satz: float = 0.0):
    """Macht aus dem, was das Modell schickt, saubere Positionen. Gibt (liste, fehler)."""
    if isinstance(positionen, str):
        try:
            positionen = json.loads(positionen)
        except ValueError:
            return [], ("Die Positionen sind unlesbar. Sag mir je Leistung: was, wie "
                        "viel und zu welchem Preis.")
    if isinstance(positionen, dict):
        positionen = [positionen]
    ergebnis = []
    for nr, roh in enumerate(positionen or [], 1):
        if not isinstance(roh, dict):
            continue
        bezeichnung = " ".join(str(roh.get("bezeichnung") or roh.get("text")
                                   or roh.get("leistung") or "").split())
        menge = _zahl_lesen(roh.get("menge"))
        menge = 1.0 if menge is None or menge == 0 else menge
        preis = _zahl_lesen(roh.get("einzelpreis", roh.get("preis")))
        if preis is None:
            betrag = _zahl_lesen(roh.get("betrag"))
            preis = None if betrag is None else betrag / menge
        if not bezeichnung:
            return [], "Bei Position %d fehlt, was gemacht wurde." % nr
        if preis is None:
            return [], "Bei '%s' fehlt der Preis." % bezeichnung[:60]
        brutto_zeile = round(menge * preis, 2)
        if preise_brutto and satz:
            preis = preis / (1.0 + satz / 100.0)
        ergebnis.append({
            "_brutto": brutto_zeile,
            "bezeichnung": bezeichnung[:300],
            "menge": round(menge, 3),
            "einheit": " ".join(str(roh.get("einheit") or ("pauschal" if menge == 1 else
                                                         "")).split())[:20],
            "einzelpreis": round(preis, 4),
            "betrag": round(menge * preis, 2),
            "turnus": str(roh.get("turnus") or "")[:20],
        })
    if not ergebnis:
        return [], "Es fehlen die Positionen: was wurde gemacht, und zu welchem Preis?"
    if preise_brutto and satz:
        # Gesagt war ein Bruttopreis. Damit am Ende genau der herauskommt, wird die
        # Steuer aus der Bruttosumme gerechnet und ein Rundungscent der letzten
        # Position zugeschlagen - sonst würden aus 3 x 10 Euro brutto 29,99 Euro.
        brutto = round(sum(p["_brutto"] for p in ergebnis), 2)
        netto_ziel = round(brutto - round(brutto * satz / (100.0 + satz), 2), 2)
        rest = round(netto_ziel - sum(p["betrag"] for p in ergebnis), 2)
        ergebnis[-1]["betrag"] = round(ergebnis[-1]["betrag"] + rest, 2)
    for position in ergebnis:
        position.pop("_brutto", None)
    return ergebnis, ""


def summen_rechnen(positionen: list, satz: float) -> list:
    """Netto, Steuer, Brutto - getrennt nach Turnus (monatlich, einmalig ...)."""
    gruppen = {}
    for position in positionen:
        gruppen.setdefault(position.get("turnus") or "", []).append(position)
    ergebnis = []
    for turnus, liste in gruppen.items():
        netto = round(sum(p["betrag"] for p in liste), 2)
        steuer = round(netto * satz / 100.0, 2)
        ergebnis.append({"turnus": turnus, "netto": netto, "mwst": steuer,
                         "brutto": round(netto + steuer, 2)})
    return ergebnis


def _dateiname(text: str) -> str:
    sauber = re.sub(r"[^A-Za-z0-9ÄÖÜäöüß]+", "-", str(text or "")).strip("-")
    for alt, neu in (("Ä", "Ae"), ("Ö", "Oe"), ("Ü", "Ue"), ("ä", "ae"), ("ö", "oe"),
                     ("ü", "ue"), ("ß", "ss")):
        sauber = sauber.replace(alt, neu)
    return sauber[:40] or "Kunde"


def _zeilen(text: str) -> list:
    """Eine Adresse in Zeilen - mit Zeilenumbruch oder mit Komma getrennt."""
    teile = re.split(r"\n|,", str(text or ""))
    return [" ".join(t.split()) for t in teile if t.strip()]


class Rechnungen:
    """Schreibt Rechnungen, Angebote und Mahnungen und behält den Überblick."""

    def __init__(self, memory: Memory = None, bookkeeping=None, mail=None, akquise=None,
                 ordner: str = None):
        self.memory = memory or Memory()
        self.bookkeeping = bookkeeping
        self.mail = mail
        self.akquise = akquise
        self.ordner = str(ordner or config.RECHNUNGEN_VERZEICHNIS)
        db_schema_anlegen(SCHEMA_RECHNUNGEN, self.memory.db_pfad)
        vorhanden = {z["name"] for z in self.memory._lesen("PRAGMA table_info(rechnungen)")}
        for spalte, art in RECHNUNG_NEUE_SPALTEN:
            if spalte not in vorhanden:
                self.memory._schreiben("ALTER TABLE rechnungen ADD COLUMN %s %s"
                                       % (spalte, art))

    # -- Grundlagen -----------------------------------------------------------

    @staticmethod
    def _steuersatz() -> float:
        return 0.0 if config.KLEINUNTERNEHMER else float(config.STANDARD_MWST)

    @staticmethod
    def fehlende_firmendaten(brutto: float = 0.0) -> list:
        """Was in den Firmendaten fehlt, damit die Rechnung vollständig ist."""
        fehlt = []
        if not (config.FIRMA_ADRESSE or "").strip():
            fehlt.append("deine Firmenadresse")
        if not config.KLEINUNTERNEHMER and brutto > KLEINBETRAG_GRENZE \
                and not (config.FIRMA_UID or "").strip():
            fehlt.append("deine UID-Nummer")
        if not (config.FIRMA_IBAN or "").strip():
            fehlt.append("deine IBAN")
        return fehlt

    def _naechste_nummer(self, art: str) -> str:
        """Fortlaufend je Jahr. Rechnung und Storno teilen sich eine Reihe."""
        jahr = datetime.now().year
        if art == "angebot":
            praefix, arten = "A%d-" % jahr, ("angebot",)
        else:
            praefix, arten = "%d-" % jahr, ("rechnung", "storno")
        zeilen = self.memory._lesen(
            "SELECT nummer FROM rechnungen WHERE nummer LIKE ? AND art IN (%s)"
            % ",".join("?" * len(arten)), (praefix + "%",) + arten)
        hoechste = 0
        for zeile in zeilen:
            treffer = re.match(re.escape(praefix) + r"(\d+)$", zeile["nummer"])
            if treffer:
                hoechste = max(hoechste, int(treffer.group(1)))
        # Wer schon Rechnungen aus einem anderen Programm hat, macht dort weiter.
        start = re.match(r"(\d{4})-(\d+)$", (config.RECHNUNG_START or "").strip())
        if art != "angebot" and start and int(start.group(1)) == jahr:
            hoechste = max(hoechste, int(start.group(2)) - 1)
        return "%s%03d" % (praefix, hoechste + 1)

    def _anlegen(self, werte: dict) -> dict:
        """Speichert ein Dokument mit frischer Nummer - auch wenn zwei gleichzeitig kommen."""
        for _ in range(5):
            werte["nummer"] = self._naechste_nummer(werte["art"])
            spalten = sorted(werte)
            try:
                werte["id"] = self.memory._schreiben(
                    "INSERT INTO rechnungen (%s) VALUES (%s)"
                    % (", ".join(spalten), ",".join("?" * len(spalten))),
                    tuple(werte[s] for s in spalten))
                return werte
            except sqlite3.IntegrityError:
                continue
        raise RuntimeError("Es ließ sich keine freie Nummer vergeben.")

    def finden(self, nummer: str):
        """Ein Dokument über seine Nummer.

        Versteht '2026-007', '2026-7', '7' (das jüngste Jahr) und für Angebote
        'A2026-003', 'A3' oder 'Angebot 3'. Ein Angebot wird nie mit einer
        Rechnung verwechselt.
        """
        text = " ".join(str(nummer or "").split()).upper()
        angebot = "ANGEBOT" in text
        for wort in ("STORNORECHNUNG", "RECHNUNG", "ANGEBOT", "NUMMER", "NR."):
            text = text.replace(wort, " ")
        text = text.strip(" .:#")
        treffer = re.fullmatch(r"(A?)\s*(?:(\d{4})\s*-\s*)?(\d{1,4})", text)
        if not treffer:
            return None
        angebot = angebot or bool(treffer.group(1))
        bedingung = "art = 'angebot'" if angebot else "art != 'angebot'"
        if treffer.group(2):
            gesucht = "%s%s-%03d" % ("A" if angebot else "", treffer.group(2),
                                     int(treffer.group(3)))
            zeilen = self.memory._lesen(
                "SELECT * FROM rechnungen WHERE upper(nummer)=? AND %s" % bedingung,
                (gesucht,))
        else:
            zeilen = self.memory._lesen(
                "SELECT * FROM rechnungen WHERE nummer LIKE ? AND %s ORDER BY id DESC"
                % bedingung, ("%%-%03d" % int(treffer.group(3)),))
        return dict(zeilen[0]) if zeilen else None

    def _kunde_ergaenzen(self, kunde: str, adresse: str, email: str):
        """Fehlt Adresse oder Mail, schaut Jarvis in Kontakten und Interessenten nach."""
        if adresse and email:
            return adresse, email
        # Nur ein Eintrag, dessen Name oder Firma genau der Kunde ist - und Adresse
        # und Mail aus demselben. Sonst landet die Privatadresse einer Putzkraft, in
        # deren Notiz "Praxis Huber" steht, auf der Rechnung an die Praxis.
        gesucht = " ".join(kunde.split()).lower()
        quellen = []
        try:
            quellen += self.memory._lesen(
                "SELECT name, firma, email, adresse FROM kontakte WHERE lower(trim(name))=? "
                "OR lower(trim(firma))=? ORDER BY id DESC LIMIT 5", (gesucht, gesucht))
        except sqlite3.Error:
            pass
        try:
            quellen += self.memory._lesen(
                "SELECT firma AS name, firma, email, adresse FROM leads "
                "WHERE lower(trim(firma))=? ORDER BY id DESC LIMIT 5", (gesucht,))
        except sqlite3.Error:
            pass  # ohne Akquise gibt es die Tabelle nicht
        for treffer in quellen:
            if (treffer.get("adresse") or "").strip() or (treffer.get("email") or "").strip():
                return (adresse or (treffer.get("adresse") or "").strip(),
                        email or (treffer.get("email") or "").strip())
        return adresse, email

    # -- Rechnung -------------------------------------------------------------

    def rechnung_erstellen(self, kunde: str, positionen, adresse: str = "", email: str = "",
                           leistungszeitraum: str = "", zahlungsziel_tage=None,
                           kunde_uid: str = "", steuerschuld_umkehr: bool = False,
                           preise_brutto: bool = False, notiz: str = "") -> dict:
        """Schreibt eine Rechnung als PDF und merkt sie sich als offen."""
        kunde = " ".join(str(kunde or "").split())[:120]
        if not kunde:
            return {"ok": False, "fehler": "An wen geht die Rechnung?"}
        umkehr = bool(steuerschuld_umkehr) and not config.KLEINUNTERNEHMER
        satz = 0.0 if umkehr else self._steuersatz()
        liste, fehler = positionen_pruefen(positionen, preise_brutto, satz)
        if fehler:
            return {"ok": False, "fehler": fehler}
        for position in liste:
            position["turnus"] = ""  # eine Rechnung hat genau eine Summe
        summe = summen_rechnen(liste, satz)[0]
        if summe["brutto"] <= 0:
            return {"ok": False, "fehler": "Die Rechnung ergibt null oder weniger. "
                                           "Für Gutschriften gibt es das Storno."}
        kunde_uid = " ".join(str(kunde_uid or "").split()).upper()[:20]
        if umkehr and not kunde_uid:
            return {"ok": False, "fehler": "Für den Übergang der Steuerschuld brauche ich "
                                           "die UID-Nummer des Kunden."}
        adresse, email = self._kunde_ergaenzen(kunde, str(adresse or "").strip(),
                                               str(email or "").strip())
        try:
            tage = int(float(zahlungsziel_tage))
        except (TypeError, ValueError):
            tage = RECHNUNG_ZAHLUNGSZIEL
        tage = max(0, min(tage, 120))
        heute = heute_datum()
        leistung = " ".join(str(leistungszeitraum or "").split())[:80] \
            or rechnung_datum(heute)
        vermerk = VERMERK_UMKEHR if umkehr else (
            VERMERK_KLEINUNTERNEHMER if config.KLEINUNTERNEHMER else "")

        eintrag = self._anlegen({
            "art": "rechnung", "bezug": "", "kunde": kunde, "adresse": adresse[:300],
            "email": email[:120], "kunde_uid": kunde_uid, "datum": heute,
            "leistung": leistung,
            "faellig": (datetime.now() + timedelta(days=tage)).strftime("%Y-%m-%d"),
            "positionen": json.dumps(liste, ensure_ascii=False),
            "netto": summe["netto"], "mwst_satz": satz, "mwst": summe["mwst"],
            "brutto": summe["brutto"], "vermerk": vermerk, "status": "offen",
            "notiz": str(notiz or "")[:500], "angelegt": zeitstempel()})
        pfad = self._pdf_schreiben(eintrag)

        eigene = self.fehlende_firmendaten(summe["brutto"])
        beim_kunden = []
        if summe["brutto"] > KLEINBETRAG_GRENZE and not adresse:
            beim_kunden.append("die Anschrift")
        if summe["brutto"] > GROSSBETRAG_GRENZE and not kunde_uid and not umkehr:
            beim_kunden.append("die UID-Nummer (ab 10.000 Euro Pflicht)")
        text = ("Rechnung %s an %s über %s ist fertig, zahlbar bis %s."
                % (eintrag["nummer"], kunde, rechnung_euro(summe["brutto"]),
                   rechnung_datum(eintrag["faellig"])))
        if eigene:
            text += (" Es fehlt noch %s - trag das unter Autopilot, Firmendaten ein, dann "
                     "schreibe ich sie neu." % " und ".join(eigene))
        if beim_kunden:
            text += (" Vom Kunden fehlt %s - sag sie mir, dann schreibe ich die Rechnung "
                     "neu." % " und ".join(beim_kunden))
        if email and not eigene and not beim_kunden:
            text += " Soll ich sie an %s schicken?" % email
        hinweise = eigene + ["vom Kunden " + h for h in beim_kunden]
        return {"ok": True, "nummer": eintrag["nummer"], "pdf": pfad,
                "brutto": summe["brutto"], "netto": summe["netto"], "mwst": summe["mwst"],
                "faellig": eintrag["faellig"], "email": email, "fehlt": hinweise,
                "text": text}

    def neu_schreiben(self, nummer: str, adresse: str = "", email: str = "",
                      kunde_uid: str = "") -> dict:
        """Schreibt das PDF neu - etwa nachdem Firmendaten oder Kundendaten ergänzt wurden.

        Nummer, Datum und Beträge bleiben, wie sie sind: Das ist eine Berichtigung,
        keine neue Rechnung.
        """
        eintrag = self.finden(nummer)
        if eintrag is None:
            return {"ok": False, "fehler": "Die Nummer %s finde ich nicht." % nummer}
        neu = {"adresse": str(adresse or "").strip()[:300],
               "email": str(email or "").strip()[:120],
               "kunde_uid": " ".join(str(kunde_uid or "").split()).upper()[:20]}
        for feld, wert in neu.items():
            if wert:
                eintrag[feld] = wert
                self.memory._schreiben("UPDATE rechnungen SET %s=? WHERE id=?" % feld,
                                       (wert, eintrag["id"]))
        pfad = self._pdf_schreiben(eintrag)
        return {"ok": True, "pdf": pfad,
                "text": "%s %s ist neu geschrieben." % (DOKUMENT_ARTEN.get(
                    eintrag["art"], "Dokument"), eintrag["nummer"])}

    # -- Angebot --------------------------------------------------------------

    def angebot_erstellen(self, kunde: str, positionen=None, adresse: str = "",
                          email: str = "", kalkulation: dict = None, gueltig_tage=None,
                          notiz: str = "") -> dict:
        """Ein Angebot als PDF - aus einer Kalkulation oder aus eigenen Positionen."""
        kunde = " ".join(str(kunde or "").split())[:120]
        if not kunde:
            return {"ok": False, "fehler": "Für wen ist das Angebot?"}
        if kalkulation:
            if not kalkulation.get("ok"):
                return kalkulation
            positionen = []
            for nr, posten in enumerate(kalkulation.get("posten") or []):
                positionen.append(dict(posten, turnus="monatlich" if nr < 2 else "einmalig"))
        satz = self._steuersatz()
        liste, fehler = positionen_pruefen(positionen, False, satz)
        if fehler:
            return {"ok": False, "fehler": fehler}
        summen = summen_rechnen(liste, satz)
        haupt = summen[0]
        adresse, email = self._kunde_ergaenzen(kunde, str(adresse or "").strip(),
                                               str(email or "").strip())
        try:
            tage = int(float(gueltig_tage))
        except (TypeError, ValueError):
            tage = ANGEBOT_GUELTIG_TAGE
        tage = max(1, min(tage, 180))
        leistung = ""
        if kalkulation:
            leistung = "%.0f m², %gx pro Woche" % (kalkulation["qm"],
                                                    kalkulation["intervall_pro_woche"])
        eintrag = self._anlegen({
            "art": "angebot", "bezug": "", "kunde": kunde, "adresse": adresse[:300],
            "email": email[:120], "kunde_uid": "", "datum": heute_datum(),
            "leistung": leistung,
            "faellig": (datetime.now() + timedelta(days=tage)).strftime("%Y-%m-%d"),
            "positionen": json.dumps(liste, ensure_ascii=False),
            "netto": haupt["netto"], "mwst_satz": satz, "mwst": haupt["mwst"],
            "brutto": haupt["brutto"],
            "vermerk": VERMERK_KLEINUNTERNEHMER if config.KLEINUNTERNEHMER else "",
            "status": "offen", "notiz": str(notiz or "")[:500], "angelegt": zeitstempel()})
        pfad = self._pdf_schreiben(eintrag)
        teile = [("%s %s" % (rechnung_euro(s["netto"]), s["turnus"])).strip() + " netto"
                 for s in summen]
        text = "Angebot %s für %s ist fertig: %s. Gültig bis %s." % (
            eintrag["nummer"], kunde, ", ".join(teile), rechnung_datum(eintrag["faellig"]))
        if email:
            text += " Soll ich es an %s schicken?" % email
        return {"ok": True, "nummer": eintrag["nummer"], "pdf": pfad, "netto": haupt["netto"],
                "brutto": haupt["brutto"], "email": email, "text": text}

    # -- Überblick ------------------------------------------------------------

    def liste(self, art: str = "", status: str = "", limit: int = 50) -> list:
        bedingungen, werte = [], []
        if art:
            bedingungen.append("art=?")
            werte.append(art)
        if status:
            bedingungen.append("status=?")
            werte.append(status)
        zeilen = self.memory._lesen(
            "SELECT * FROM rechnungen %s ORDER BY id DESC LIMIT ?"
            % (("WHERE " + " AND ".join(bedingungen)) if bedingungen else ""),
            tuple(werte) + (int(limit),))
        heute = heute_datum()
        ergebnis = []
        for zeile in zeilen:
            eintrag = dict(zeile)
            eintrag.pop("positionen", None)
            eintrag["datei"] = os.path.basename(eintrag.get("pdf") or "")
            eintrag["mahn_datei"] = os.path.basename(eintrag.get("mahn_pdf") or "")
            ueber = 0
            if eintrag["art"] == "rechnung" and eintrag["status"] == "offen" \
                    and eintrag["faellig"] and eintrag["faellig"] < heute:
                ueber = (datetime.strptime(heute, "%Y-%m-%d")
                         - datetime.strptime(eintrag["faellig"], "%Y-%m-%d")).days
            eintrag["ueberfaellig_tage"] = ueber
            eintrag["offen_betrag"] = round(eintrag["brutto"]
                                            - float(eintrag.get("bezahlt_betrag") or 0), 2)
            ergebnis.append(eintrag)
        return ergebnis

    def offene(self) -> dict:
        """Alle offenen Rechnungen - die überfälligen zuerst."""
        offen = self.liste("rechnung", "offen", 500)
        offen.sort(key=lambda r: (-r["ueberfaellig_tage"], r["faellig"]))
        ueber = [r for r in offen if r["ueberfaellig_tage"] > 0]
        summe = round(sum(r["offen_betrag"] for r in offen), 2)
        if not offen:
            text = "Alle Rechnungen sind bezahlt."
        else:
            text = "%d Rechnungen sind offen, zusammen %s." % (len(offen), rechnung_euro(summe))
            if len(offen) == 1:
                text = "Eine Rechnung ist offen: %s." % rechnung_euro(summe)
            if ueber:
                text += " Überfällig: %s." % "; ".join(
                    "%s an %s, %s, seit %d Tagen" % (r["nummer"], r["kunde"],
                                                     rechnung_euro(r["offen_betrag"]),
                                                     r["ueberfaellig_tage"])
                    for r in ueber[:4])
        return {"ok": True, "anzahl": len(offen), "summe": summe,
                "ueberfaellig": len(ueber), "rechnungen": offen, "text": text}

    # -- Zahlung, Mahnung, Storno ------------------------------------------------

    def bezahlt(self, nummer: str, datum: str = "", betrag=None) -> dict:
        """Hakt eine Rechnung als bezahlt ab und bucht die Einnahme."""
        eintrag = self.finden(nummer)
        if eintrag is None or eintrag["art"] != "rechnung":
            return {"ok": False, "fehler": "Die Rechnung %s finde ich nicht." % nummer}
        if eintrag["status"] == "bezahlt":
            return {"ok": True, "text": "Rechnung %s ist schon als bezahlt eingetragen."
                                        % eintrag["nummer"]}
        if eintrag["status"] == "storniert":
            return {"ok": False, "fehler": "Rechnung %s ist storniert." % eintrag["nummer"]}
        datum = str(datum or "").strip()[:10] or heute_datum()
        try:
            datetime.strptime(datum, "%Y-%m-%d")
        except ValueError:
            datum = heute_datum()
        schon = round(float(eintrag.get("bezahlt_betrag") or 0), 2)
        rest = round(eintrag["brutto"] - schon, 2)
        gezahlt = _zahl_lesen(betrag)
        gezahlt = rest if gezahlt is None or gezahlt <= 0 else round(gezahlt, 2)
        summe = round(schon + gezahlt, 2)
        fertig = summe >= eintrag["brutto"] - 0.01
        self.memory._schreiben(
            "UPDATE rechnungen SET status=?, bezahlt_am=?, bezahlt_betrag=? WHERE id=?",
            ("bezahlt" if fertig else "offen", datum, summe, eintrag["id"]))
        if fertig:
            text = "Rechnung %s von %s ist bezahlt." % (eintrag["nummer"], eintrag["kunde"])
        else:
            text = ("Teilzahlung zu Rechnung %s: %s eingegangen, offen bleiben %s."
                    % (eintrag["nummer"], rechnung_euro(gezahlt),
                       rechnung_euro(eintrag["brutto"] - summe)))
        if self.bookkeeping is not None:
            # Die Steuer anteilig, damit die Buchung genau zu dieser Zahlung passt.
            anteil = gezahlt / eintrag["brutto"] if eintrag["brutto"] else 1.0
            buchung = self.bookkeeping.buchung_eintragen(
                "einnahme", datum, gezahlt, eintrag["kunde"], "Reinigungsleistung",
                eintrag["mwst_satz"], round(eintrag["mwst"] * anteil, 2), "Überweisung",
                beleg_pfad=eintrag.get("pdf") or "",
                notiz="Rechnung %s" % eintrag["nummer"])
            if buchung.get("ok"):
                text += " %s als Einnahme gebucht." % rechnung_euro(gezahlt)
        if summe > eintrag["brutto"] + 0.01:
            text += " Achtung: Bezahlt wurden %s statt %s." % (
                rechnung_euro(summe), rechnung_euro(eintrag["brutto"]))
        return {"ok": True, "nummer": eintrag["nummer"], "bezahlt": fertig,
                "offen": round(max(eintrag["brutto"] - summe, 0.0), 2), "text": text}

    def mahnung_erstellen(self, nummer: str, spesen=None) -> dict:
        """Schreibt die nächste Mahnstufe als PDF: Erinnerung, 1. und 2. Mahnung."""
        eintrag = self.finden(nummer)
        if eintrag is None or eintrag["art"] != "rechnung":
            return {"ok": False, "fehler": "Die Rechnung %s finde ich nicht." % nummer}
        if eintrag["status"] != "offen":
            return {"ok": False, "fehler": "Rechnung %s ist nicht offen (%s)."
                                           % (eintrag["nummer"], eintrag["status"])}
        stufe = min(int(eintrag["mahnstufe"] or 0) + 1, len(MAHNSTUFEN))
        spesen = round(max(_zahl_lesen(spesen) or 0.0, 0.0), 2)
        frist = (datetime.now() + timedelta(days=MAHNUNG_FRIST_TAGE)).strftime("%Y-%m-%d")
        eintrag.update(mahnstufe=stufe, mahn_spesen=spesen, mahn_frist=frist,
                       gemahnt_am=heute_datum())
        pfad = self._mahnung_schreiben(eintrag)
        self.memory._schreiben(
            "UPDATE rechnungen SET mahnstufe=?, gemahnt_am=?, mahn_pdf=?, mahn_spesen=?, "
            "mahn_frist=? WHERE id=?",
            (stufe, heute_datum(), pfad, spesen, frist, eintrag["id"]))
        text = "%s zu Rechnung %s an %s ist fertig, neue Frist %s." % (
            MAHNSTUFEN[stufe - 1], eintrag["nummer"], eintrag["kunde"], rechnung_datum(frist))
        if eintrag["email"]:
            text += " Soll ich sie an %s schicken?" % eintrag["email"]
        return {"ok": True, "nummer": eintrag["nummer"], "stufe": stufe, "pdf": pfad,
                "text": text}

    def stornieren(self, nummer: str, grund: str = "", rueckzahlung: bool = False) -> dict:
        """Storniert eine Rechnung mit einer Stornorechnung - gelöscht wird nie etwas.

        Ist schon Geld gekommen, wäre die Einnahme sonst weiter gebucht. Dann nur
        mit ``rueckzahlung``: Jarvis bucht die Rückzahlung, die Steuer mit.
        """
        eintrag = self.finden(nummer)
        if eintrag is None or eintrag["art"] != "rechnung":
            return {"ok": False, "fehler": "Die Rechnung %s finde ich nicht." % nummer}
        if eintrag["status"] == "storniert":
            return {"ok": True, "text": "Rechnung %s ist schon storniert." % eintrag["nummer"]}
        gezahlt = round(float(eintrag.get("bezahlt_betrag") or 0), 2)
        if eintrag["status"] == "bezahlt" and not gezahlt:
            gezahlt = eintrag["brutto"]  # vor der Teilzahlungs-Spalte abgehakt
        if gezahlt and not rueckzahlung:
            return {"ok": False, "fehler": "Auf Rechnung %s sind schon %s eingegangen. Ein "
                                           "Storno heißt dann: Geld zurück. Sag 'storniere "
                                           "mit Rückzahlung', dann buche ich die Rückzahlung "
                                           "gleich mit." % (eintrag["nummer"],
                                                            rechnung_euro(gezahlt))}
        positionen = json.loads(eintrag["positionen"] or "[]")
        for position in positionen:
            position["einzelpreis"] = -position["einzelpreis"]
            position["betrag"] = -position["betrag"]
        storno = self._anlegen({
            "art": "storno", "bezug": eintrag["nummer"], "kunde": eintrag["kunde"],
            "adresse": eintrag["adresse"], "email": eintrag["email"],
            "kunde_uid": eintrag["kunde_uid"], "datum": heute_datum(),
            "leistung": eintrag["leistung"], "faellig": "",
            "positionen": json.dumps(positionen, ensure_ascii=False),
            "netto": -eintrag["netto"], "mwst_satz": eintrag["mwst_satz"],
            "mwst": -eintrag["mwst"], "brutto": -eintrag["brutto"],
            "vermerk": eintrag["vermerk"], "status": "erledigt",
            "notiz": str(grund or "")[:300], "angelegt": zeitstempel()})
        pfad = self._pdf_schreiben(storno)
        self.memory._schreiben("UPDATE rechnungen SET status='storniert' WHERE id=?",
                               (eintrag["id"],))
        text = ("Rechnung %s ist storniert, die Stornorechnung hat die Nummer %s."
                % (eintrag["nummer"], storno["nummer"]))
        if gezahlt and self.bookkeeping is not None:
            anteil = gezahlt / eintrag["brutto"] if eintrag["brutto"] else 1.0
            buchung = self.bookkeeping.buchung_eintragen(
                "ausgabe", heute_datum(), gezahlt, eintrag["kunde"], "Rückzahlung",
                eintrag["mwst_satz"], round(eintrag["mwst"] * anteil, 2), "Überweisung",
                beleg_pfad=pfad, notiz="Storno %s zu Rechnung %s" % (storno["nummer"],
                                                                     eintrag["nummer"]))
            if buchung.get("ok"):
                text += " Die Rückzahlung über %s ist gebucht." % rechnung_euro(gezahlt)
        return {"ok": True, "nummer": storno["nummer"], "pdf": pfad, "text": text}

    def angebot_status(self, nummer: str, status: str) -> dict:
        """Ein Angebot als angenommen oder abgelehnt markieren."""
        eintrag = self.finden(nummer)
        if eintrag is None or eintrag["art"] != "angebot":
            return {"ok": False, "fehler": "Das Angebot %s finde ich nicht." % nummer}
        if status not in ("angenommen", "abgelehnt", "offen"):
            return {"ok": False, "fehler": "Der Stand muss angenommen oder abgelehnt sein."}
        self.memory._schreiben("UPDATE rechnungen SET status=? WHERE id=?",
                               (status, eintrag["id"]))
        if self.akquise is not None and status != "offen":
            lead = self.akquise.lead_finden(eintrag["kunde"])
            if lead is not None:
                self.akquise.lead_weiterstufen(
                    lead["firma"], "gewonnen" if status == "angenommen" else "verloren",
                    "Angebot %s %s" % (eintrag["nummer"], status))
        return {"ok": True, "text": "Angebot %s an %s ist %s." % (
            eintrag["nummer"], eintrag["kunde"], status)}

    # -- Versand ----------------------------------------------------------------

    def versandfertig(self, nummer: str, an: str = "", was: str = "") -> dict:
        """Prüft vor dem Senden alles und baut die Mail - ohne sie zu senden."""
        eintrag = self.finden(nummer)
        if eintrag is None:
            return {"ok": False, "fehler": "Die Nummer %s finde ich nicht." % nummer}
        an = str(an or eintrag["email"] or "").strip()
        if "@" not in an:
            return {"ok": False, "fehler": "An welche Mailadresse soll %s %s gehen?"
                                           % (DOKUMENT_ARTEN[eintrag["art"]], eintrag["nummer"])}
        if eintrag["art"] != "angebot" and not (config.FIRMA_ADRESSE or "").strip():
            return {"ok": False, "fehler": "Ohne deine Firmenadresse ist die Rechnung nicht "
                                           "gültig. Trag sie unter Autopilot, Firmendaten ein "
                                           "und sag dann 'Rechnung %s neu schreiben'."
                                           % eintrag["nummer"]}
        mahnung = str(was or "").lower().startswith("mahn")
        if mahnung and not (eintrag["mahn_pdf"] and eintrag["mahnstufe"]):
            return {"ok": False, "fehler": "Zu Rechnung %s gibt es noch keine Mahnung."
                                           % eintrag["nummer"]}
        if mahnung and (eintrag["art"] != "rechnung" or eintrag["status"] != "offen"):
            return {"ok": False, "fehler": "Rechnung %s ist %s - da geht keine Mahnung mehr "
                                           "raus." % (eintrag["nummer"], eintrag["status"])}
        # Immer frisch schreiben: Wurden Firmendaten inzwischen ergänzt, soll nicht das
        # alte PDF ohne sie hinausgehen. Nummer und Beträge stehen fest.
        pfad = self._mahnung_schreiben(eintrag) if mahnung else self._pdf_schreiben(eintrag)
        gruss = "Mit freundlichen Grüßen\n%s\n%s" % (config.NUTZER_NAME, config.FIRMA)
        if mahnung:
            stufe = MAHNSTUFEN[max(1, int(eintrag["mahnstufe"])) - 1]
            betreff = "%s zu Rechnung %s" % (stufe, eintrag["nummer"])
            offen = round(eintrag["brutto"] - float(eintrag.get("bezahlt_betrag") or 0)
                          + float(eintrag.get("mahn_spesen") or 0), 2)
            text = ("Sehr geehrte Damen und Herren,\n\nanbei erhalten Sie unsere %s zu "
                    "Rechnung %s. Offen sind %s, bitte bis %s. Sollten Sie inzwischen bezahlt "
                    "haben, betrachten Sie dieses Schreiben bitte als gegenstandslos.\n\n%s"
                    % (stufe, eintrag["nummer"], rechnung_euro(offen),
                       rechnung_datum(eintrag.get("mahn_frist") or ""), gruss))
        elif eintrag["art"] == "angebot":
            betreff = "Angebot %s - %s" % (eintrag["nummer"], config.FIRMA)
            text = ("Sehr geehrte Damen und Herren,\n\nvielen Dank für Ihr Interesse. Anbei "
                    "erhalten Sie unser Angebot %s. Es gilt bis %s. Für Fragen bin ich gern "
                    "für Sie da.\n\n%s" % (eintrag["nummer"],
                                           rechnung_datum(eintrag["faellig"]), gruss))
        else:
            art = DOKUMENT_ARTEN[eintrag["art"]]
            betreff = "%s %s - %s" % (art, eintrag["nummer"], config.FIRMA)
            text = ("Sehr geehrte Damen und Herren,\n\nanbei erhalten Sie unsere %s %s über "
                    "%s%s.\n\nVielen Dank für Ihren Auftrag.\n\n%s"
                    % (art, eintrag["nummer"], rechnung_euro(abs(eintrag["brutto"])),
                       (", zahlbar bis %s" % rechnung_datum(eintrag["faellig"]))
                       if eintrag["art"] == "rechnung" else "", gruss))
        return {"ok": True, "eintrag": eintrag, "an": an, "betreff": betreff, "text": text,
                "pdf": pfad}

    def senden(self, nummer: str, an: str = "", was: str = "", text: str = "") -> dict:
        """Schickt Rechnung, Angebot oder Mahnung als PDF. Die Freigabe holt der Katalog ein."""
        if self.mail is None or not self.mail.senden_moeglich():
            return {"ok": False, "fehler": "Der Mailversand ist nicht eingerichtet. Das PDF "
                                           "liegt im Ordner rechnungen - du kannst es auch "
                                           "selbst anhängen."}
        bereit = self.versandfertig(nummer, an, was)
        if not bereit.get("ok"):
            return bereit
        ergebnis = self.mail.senden(bereit["an"], bereit["betreff"],
                                    str(text or "").strip() or bereit["text"],
                                    anhaenge=[bereit["pdf"]])
        if not ergebnis.get("ok"):
            return ergebnis
        self.memory._schreiben("UPDATE rechnungen SET gesendet_am=? WHERE id=?",
                               (zeitstempel(), bereit["eintrag"]["id"]))
        return {"ok": True, "text": "%s ist an %s raus." % (bereit["betreff"], bereit["an"])}

    # -- PDF ----------------------------------------------------------------------

    def _ordner_anlegen(self):
        os.makedirs(self.ordner, exist_ok=True)

    def _mahnung_schreiben(self, eintrag: dict) -> str:
        """Schreibt die Mahnung der aktuellen Stufe - mit gemerkter Frist und Spesen."""
        self._ordner_anlegen()
        stufe = max(1, min(int(eintrag["mahnstufe"] or 1), len(MAHNSTUFEN)))
        frist = eintrag.get("mahn_frist") or (
            datetime.now() + timedelta(days=MAHNUNG_FRIST_TAGE)).strftime("%Y-%m-%d")
        pfad = os.path.join(self.ordner, "Mahnung%d_%s_%s.pdf" % (
            stufe, eintrag["nummer"], _dateiname(eintrag["kunde"])))
        self._mahnung_pdf(eintrag, stufe, float(eintrag.get("mahn_spesen") or 0),
                          frist).speichern(pfad)
        return pfad

    def _pdf_schreiben(self, eintrag: dict) -> str:
        """Schreibt das PDF eines Dokuments und merkt sich den Pfad."""
        self._ordner_anlegen()
        art = DOKUMENT_ARTEN.get(eintrag["art"], "Dokument")
        pfad = os.path.join(self.ordner, "%s_%s_%s.pdf" % (
            art, eintrag["nummer"], _dateiname(eintrag["kunde"])))
        self._dokument_pdf(eintrag).speichern(pfad)
        self.memory._schreiben("UPDATE rechnungen SET pdf=? WHERE nummer=?",
                               (pfad, eintrag["nummer"]))
        return pfad

    @staticmethod
    def _fusszeile(dokument: PdfDokument, seite: int, seiten: int):
        """Firmendaten unten auf jeder Seite, dazu die Seitenzahl."""
        mitte = PDF_SEITE_BREITE / 2.0
        dokument.linie(BRIEF_LINKS, 786, BRIEF_RECHTS, 786, 0.4, 0.75)
        zeile1 = "  ·  ".join(t for t in [config.FIRMA] + _zeilen(config.FIRMA_ADRESSE)
                              + [config.FIRMA_TELEFON, config.FIRMA_EMAIL] if t)
        zeile2 = "  ·  ".join(t for t in [
            ("UID: %s" % config.FIRMA_UID) if config.FIRMA_UID else "",
            ("IBAN: %s" % config.FIRMA_IBAN) if config.FIRMA_IBAN else "",
            ("BIC: %s" % config.FIRMA_BIC) if config.FIRMA_BIC else ""] if t)
        dokument.text(mitte, 798, zeile1, 7.5, ausrichtung="mitte", farbe=BRIEF_GRAU)
        dokument.text(mitte, 808, zeile2, 7.5, ausrichtung="mitte", farbe=BRIEF_GRAU)
        if seiten > 1:
            dokument.text(BRIEF_RECHTS, 822, "Seite %d von %d" % (seite, seiten), 7.5,
                          ausrichtung="rechts", farbe=BRIEF_GRAU)

    def _briefkopf(self, titel: str, eintrag: dict, angaben: list) -> PdfDokument:
        """Kopf, Anschrift und Eckdaten - für alle Dokumente gleich."""
        dok = PdfDokument("%s %s" % (titel, eintrag["nummer"]), config.FIRMA)
        dok.fusszeile = self._fusszeile
        dok.text(BRIEF_LINKS, 64, config.FIRMA, 18, True, farbe=BRIEF_AKZENT)
        if config.NUTZER_NAME and config.NUTZER_NAME != "Chef":
            dok.text(BRIEF_LINKS, 79, "Inhaber: %s" % config.NUTZER_NAME, 8.5,
                     farbe=BRIEF_GRAU)
        # Rechts oben höchstens fünf Zeilen, sonst stoßen sie an die Linie darunter.
        adresse = _zeilen(config.FIRMA_ADRESSE)
        kontakt = [z for z in (("Tel. %s" % config.FIRMA_TELEFON) if config.FIRMA_TELEFON
                               else "", config.FIRMA_EMAIL) if z]
        if len(adresse) + len(kontakt) > 5:
            adresse = adresse[:1] + [", ".join(adresse[1:])]
        zeilen = adresse + kontakt
        y, abstand = (52, 11) if len(zeilen) <= 4 else (45, 10)
        for zeile in zeilen[:5]:
            dok.text(BRIEF_RECHTS, y, zeile[:70], 8.5, ausrichtung="rechts", farbe=BRIEF_GRAU)
            y += abstand
        dok.linie(BRIEF_LINKS, 96, BRIEF_RECHTS, 96, 1.2, BRIEF_AKZENT)

        # Anschriftfeld - passt in das Fenster eines Kuverts.
        absender = "  ·  ".join([config.FIRMA] + _zeilen(config.FIRMA_ADRESSE))
        dok.text(BRIEF_LINKS, 140, absender[:110], 7, farbe=BRIEF_GRAU)
        dok.linie(BRIEF_LINKS, 143, BRIEF_LINKS + 230, 143, 0.3, 0.7)
        y = 160
        for nr, zeile in enumerate([eintrag["kunde"]] + _zeilen(eintrag["adresse"])[:5]):
            dok.text(BRIEF_LINKS, y, zeile[:60], 10.5, fett=(nr == 0))
            y += 14

        y = 160
        for name, wert in angaben:
            if wert:
                dok.text(352, y, name, 8.5, farbe=BRIEF_GRAU)
                # Passt ein Wert (etwa ein ausführlicher Leistungszeitraum) nicht neben
                # die Beschriftung, steht er umbrochen darunter - nie darüber gedruckt.
                if pdf_textbreite(wert, 9) > BRIEF_RECHTS - 352 - pdf_textbreite(name, 8.5) - 8:
                    y += 11
                    zeilen = pdf_umbrechen(wert, BRIEF_RECHTS - 352, 9)[:4]
                else:
                    zeilen = [wert]
                for zeile in zeilen:
                    dok.text(BRIEF_RECHTS, y, zeile, 9, ausrichtung="rechts")
                    y += 11
                y += 3
        dok.text(BRIEF_LINKS, 262, "%s %s" % (titel, eintrag["nummer"]), 15, True)
        return dok

    def _tabelle(self, dok: PdfDokument, y: float, positionen: list) -> float:
        """Positionen mit Kopfzeile; bricht auf neue Seiten um."""
        spalten = [(BRIEF_LINKS + 4, "Pos.", "links"), (BRIEF_LINKS + 32, "Leistung", "links"),
                   (342, "Menge", "rechts"), (354, "Einheit", "links"),
                   (462, "Einzelpreis", "rechts"), (BRIEF_RECHTS - 4, "Betrag", "rechts")]

        def kopf(y):
            dok.flaeche(BRIEF_LINKS, y, BRIEF_RECHTS - BRIEF_LINKS, 18, 0.92)
            for x, name, ausrichtung in spalten:
                dok.text(x, y + 12.5, name, 8.5, True, ausrichtung)
            return y + 24

        y = kopf(y)
        for nr, position in enumerate(positionen, 1):
            zeilen = pdf_umbrechen(position["bezeichnung"], 222, 9.5)
            hoehe = len(zeilen) * 12 + 6
            if y + hoehe > BRIEF_UNTEN:
                dok.neue_seite()
                y = kopf(70)
            dok.text(spalten[0][0], y + 6, str(nr), 9.5)
            for i, zeile in enumerate(zeilen):
                dok.text(spalten[1][0], y + 6 + i * 12, zeile, 9.5)
            dok.text(spalten[2][0], y + 6, rechnung_menge(position["menge"]), 9.5,
                     ausrichtung="rechts")
            dok.text(spalten[3][0], y + 6, position["einheit"], 9.5)
            dok.text(spalten[4][0], y + 6, rechnung_euro(position["einzelpreis"]), 9.5,
                     ausrichtung="rechts")
            dok.text(spalten[5][0], y + 6, rechnung_euro(position["betrag"]), 9.5,
                     ausrichtung="rechts")
            y += hoehe
            dok.linie(BRIEF_LINKS, y - 2, BRIEF_RECHTS, y - 2, 0.3, 0.82)
        return y + 6

    @staticmethod
    def _platz(dok: PdfDokument, y: float, hoehe: float, unten: float = BRIEF_UNTEN) -> float:
        if y + hoehe > unten:
            dok.neue_seite()
            return 70
        return y

    def _summenblock(self, dok: PdfDokument, y: float, summen: list, satz: float,
                     vermerk: str) -> float:
        for summe in summen:
            y = self._platz(dok, y, 56)
            zusatz = (" " + summe["turnus"]) if summe["turnus"] else ""
            zeilen = []
            if satz:  # ohne Steuer (Kleinunternehmer, Steuerschuld beim Kunden) nur die Summe
                zeilen = [("Summe netto" + zusatz, summe["netto"], False),
                          ("USt %s %%" % rechnung_menge(satz), summe["mwst"], False)]
            zeilen.append(("Gesamtbetrag" + zusatz, summe["brutto"], True))
            for name, wert, fett in zeilen:
                if fett:
                    dok.linie(330, y - 9, BRIEF_RECHTS, y - 9, 0.6)
                    y += 3
                dok.text(334, y, name, 10.5 if fett else 9.5, fett)
                dok.text(BRIEF_RECHTS - 4, y, rechnung_euro(wert), 10.5 if fett else 9.5,
                         fett, "rechts")
                y += 15
            y += 6
        if vermerk:
            y = self._platz(dok, y, 30)
            y = dok.absatz(BRIEF_LINKS, y + 4, vermerk, BRIEF_RECHTS - BRIEF_LINKS, 9)
        return y + 6

    def _schluss(self, dok: PdfDokument, y: float, absaetze: list):
        for absatz in absaetze:
            hoehe = len(pdf_umbrechen(absatz, BRIEF_RECHTS - BRIEF_LINKS, 10)) * 13.5 + 8
            y = self._platz(dok, y, hoehe)
            y = dok.absatz(BRIEF_LINKS, y, absatz, BRIEF_RECHTS - BRIEF_LINKS, 10) + 8
        y = self._platz(dok, y, 34, unten=778)  # der Gruß darf bis knapp an die Fußzeile
        dok.text(BRIEF_LINKS, y + 4, "Mit freundlichen Grüßen", 10)
        dok.text(BRIEF_LINKS, y + 32, config.NUTZER_NAME if config.NUTZER_NAME != "Chef"
                 else config.FIRMA, 10, True)

    def _zahlungstext(self, eintrag: dict, betrag: float, bis: str) -> str:
        text = "Bitte überweisen Sie %s bis %s" % (rechnung_euro(betrag), rechnung_datum(bis))
        if config.FIRMA_IBAN:
            text += " auf das Konto IBAN %s%s" % (
                config.FIRMA_IBAN, (", BIC %s" % config.FIRMA_BIC) if config.FIRMA_BIC else "")
        return text + ". Verwendungszweck: Rechnung %s." % eintrag["nummer"]

    def _dokument_pdf(self, eintrag: dict) -> PdfDokument:
        positionen = json.loads(eintrag["positionen"] or "[]")
        art = eintrag["art"]
        satz = float(eintrag["mwst_satz"] or 0)
        if art == "angebot":
            angaben = [("Angebotsnummer", eintrag["nummer"]),
                       ("Datum", rechnung_datum(eintrag["datum"])),
                       ("Gültig bis", rechnung_datum(eintrag["faellig"])),
                       ("Objekt", eintrag["leistung"])]
            einleitung = ("vielen Dank für Ihr Interesse. Für die Reinigung Ihres Objekts "
                          "biete ich Ihnen folgende Leistungen an:")
        elif art == "storno":
            angaben = [("Nummer", eintrag["nummer"]),
                       ("Datum", rechnung_datum(eintrag["datum"])),
                       ("Zu Rechnung", eintrag["bezug"]),
                       ("Leistungszeitraum", eintrag["leistung"]),
                       ("Ihre UID", eintrag["kunde_uid"])]
            einleitung = ("hiermit stornieren wir unsere Rechnung %s vollständig. Die "
                          "folgenden Beträge werden gutgeschrieben:" % eintrag["bezug"])
        else:
            angaben = [("Rechnungsnummer", eintrag["nummer"]),
                       ("Rechnungsdatum", rechnung_datum(eintrag["datum"])),
                       ("Leistungszeitraum", eintrag["leistung"]),
                       ("Zahlbar bis", rechnung_datum(eintrag["faellig"])),
                       ("Ihre UID", eintrag["kunde_uid"])]
            einleitung = "für die erbrachten Leistungen erlaube ich mir zu verrechnen:"
        dok = self._briefkopf(DOKUMENT_ARTEN.get(art, "Dokument"), eintrag, angaben)
        y = dok.absatz(BRIEF_LINKS, 290, "Sehr geehrte Damen und Herren,",
                       BRIEF_RECHTS - BRIEF_LINKS, 10) + 4
        y = dok.absatz(BRIEF_LINKS, y, einleitung, BRIEF_RECHTS - BRIEF_LINKS, 10) + 8
        y = self._tabelle(dok, y, positionen)
        y = self._summenblock(dok, y + 8, summen_rechnen(positionen, satz), satz,
                              eintrag["vermerk"])
        if art == "angebot":
            absaetze = ["Gerne führe ich vorab eine kostenlose Probereinigung durch, damit Sie "
                        "die Qualität beurteilen können. Ich freue mich auf Ihre Zusage."]
        elif art == "storno":
            absaetze = ["Ein bereits bezahlter Betrag wird Ihnen zurücküberwiesen."]
        else:
            absaetze = [self._zahlungstext(eintrag, eintrag["brutto"], eintrag["faellig"]),
                        "Vielen Dank für Ihren Auftrag."]
        self._schluss(dok, y + 6, absaetze)
        return dok

    def _mahnung_pdf(self, eintrag: dict, stufe: int, spesen: float, frist: str) -> PdfDokument:
        titel = MAHNSTUFEN[stufe - 1]
        dok = self._briefkopf(titel, dict(eintrag, nummer="zu Rechnung %s" % eintrag["nummer"]),
                              [("Datum", rechnung_datum(heute_datum())),
                               ("Rechnungsnummer", eintrag["nummer"]),
                               ("Rechnungsdatum", rechnung_datum(eintrag["datum"])),
                               ("Fällig seit", rechnung_datum(eintrag["faellig"]))])
        einleitung = {
            1: "sicher ist es Ihnen im Alltag entgangen: Unsere Rechnung %s vom %s ist noch "
               "offen. Wir bitten Sie, den Betrag bis %s zu überweisen.",
            2: "leider konnten wir zu unserer Rechnung %s vom %s trotz Zahlungserinnerung noch "
               "keinen Zahlungseingang feststellen. Bitte überweisen Sie den offenen Betrag "
               "bis spätestens %s.",
            3: "trotz Zahlungserinnerung und Mahnung ist unsere Rechnung %s vom %s weiterhin "
               "unbezahlt. Wir fordern Sie letztmalig auf, den offenen Betrag bis %s zu "
               "begleichen.",
        }[stufe] % (eintrag["nummer"], rechnung_datum(eintrag["datum"]), rechnung_datum(frist))
        y = dok.absatz(BRIEF_LINKS, 290, "Sehr geehrte Damen und Herren,",
                       BRIEF_RECHTS - BRIEF_LINKS, 10) + 4
        y = dok.absatz(BRIEF_LINKS, y, einleitung, BRIEF_RECHTS - BRIEF_LINKS, 10) + 8
        posten = [{"bezeichnung": "Rechnung %s vom %s, fällig am %s" % (
                       eintrag["nummer"], rechnung_datum(eintrag["datum"]),
                       rechnung_datum(eintrag["faellig"])),
                   "menge": 1, "einheit": "", "einzelpreis": eintrag["brutto"],
                   "betrag": eintrag["brutto"]}]
        schon = round(float(eintrag.get("bezahlt_betrag") or 0), 2)
        if schon:
            posten.append({"bezeichnung": "Bereits bezahlt", "menge": 1, "einheit": "",
                           "einzelpreis": -schon, "betrag": -schon})
        if spesen:
            posten.append({"bezeichnung": "Mahnspesen", "menge": 1, "einheit": "",
                           "einzelpreis": spesen, "betrag": spesen})
        y = self._tabelle(dok, y, posten)
        gesamt = round(eintrag["brutto"] - schon + spesen, 2)
        y = self._platz(dok, y + 8, 30)
        dok.linie(330, y - 9, BRIEF_RECHTS, y - 9, 0.6)
        dok.text(334, y + 3, "Offener Betrag", 10.5, True)
        dok.text(BRIEF_RECHTS - 4, y + 3, rechnung_euro(gesamt), 10.5, True, "rechts")
        absaetze = [self._zahlungstext(eintrag, gesamt, frist),
                    "Sollten Sie inzwischen bezahlt haben, betrachten Sie dieses Schreiben "
                    "bitte als gegenstandslos."]
        if stufe == 3:
            absaetze.insert(1, "Nach Ablauf dieser Frist behalten wir uns vor, die Forderung "
                               "ohne weitere Ankündigung einem Inkassobüro zu übergeben oder "
                               "gerichtlich geltend zu machen. Die dadurch entstehenden "
                               "Kosten gehen zu Ihren Lasten.")
        self._schluss(dok, y + 26, absaetze)
        return dok
