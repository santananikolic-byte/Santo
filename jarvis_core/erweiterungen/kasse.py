# -*- coding: utf-8 -*-
"""Kasse - einfache Einnahmen-Ausgaben-Übersicht für Vater und Sohn.

WICHTIG, ehrlich gesagt: Das ist eine Übersicht für euch. Es ist KEINE Buchhaltung und KEIN GoBD-konformes
Kassenbuch (keine Unveränderbarkeit, keine Verfahrensdokumentation, keine Steuerlogik wie Umsatzsteuer oder
Abschreibung). Die Buchhaltung bleibt beim Steuerberater. Dieser Hinweis steht deshalb in jeder Ausgabe.

* ``buchung_erfassen``: eine Einnahme oder Ausgabe festhalten (Betrag in Euro, gespeichert in Cent) - nur mit echten
  Beträgen, nichts wird geschätzt. Der Beleg ist nur ein Verweis auf eine Datei, sie wird nicht gelesen oder kopiert.
* ``buchungen_anzeigen``: ein Monat mit Summen je Kategorie, Saldo und Vergleich zum Vormonat.
* ``buchung_loeschen``: löscht eine Buchung - nur mit eurem ausdrücklichen Ja (Freigabe mit Vorschau).
* ``kassen_export``: CSV für den Steuerberater (Semikolon, deutsche Beträge, UTF-8 mit BOM für Excel), gegen
  CSV-Injection abgesichert. Die Datei liegt in der Werkstatt; verschickt wird sie von JARVIS nie.

Gemeinsame Tabelle ``betrieb.BUCHUNGEN``. Einnahmen aus bezahlten Rechnungen legt die Erweiterung „Rechnungen“ mit
``rechnung_id`` an: Die zählt die Kasse mit, legt sie aber nie selbst an. Bucht jemand eine Rechnungszahlung von
Hand und es gibt schon eine Buchung mit gleichem Betrag und Datum aus einer Rechnung, kommt ein Hinweis.

Grenzen: keine Umsatzsteuer-Aufteilung, keine Bank-Anbindung, kein Abgleich mit Kontoauszügen, keine Änderung einer
Buchung (Fehler: löschen und neu erfassen). Nur für den Geschäftsbereich.
"""

import datetime
import os
import re

from . import (FREI, FREIGABE, MELDUNG, Baustein, P, Werkzeug, WerkzeugFehler, einzeilig, fremdtext, heute, muster,
               werkstatt_datei)
from .. import betrieb
from ..werkzeuge import pfad_aufloesen

NAME = "Kasse"
BEREICH = "betrieb"
BESCHREIBUNG = "Einfache Einnahmen-Ausgaben-Übersicht mit Monatssummen und CSV für den Steuerberater (keine Buchhaltung)."
PRIORITAET = 55
GRUENDLICH = False
FUER_AGENTEN = {"buchungen_anzeigen": ("finanzleiter", "kosten", "liquiditaet", "steuerberater_vorbereitung")}

KATEGORIEN_EINNAHME = ("Reinigung", "Bau", "Sonstiges", "Rechnung")
KATEGORIEN_AUSGABE = ("Material", "Fahrzeug", "Personal", "Subunternehmer", "Miete", "Versicherung", "Werbung", "Büro",
                      "Gebühren", "Sonstiges")
KATEGORIEN = {"einnahme": KATEGORIEN_EINNAHME, "ausgabe": KATEGORIEN_AUSGABE}
ART_NAME = {"einnahme": "Einnahme", "ausgabe": "Ausgabe"}
HINWEIS = ("Hinweis: Das ist eine Übersicht für euch - keine Buchhaltung und kein GoBD-konformes Kassenbuch. "
           "Die Buchhaltung bleibt beim Steuerberater.")
MONATE = ("Januar", "Februar", "März", "April", "Mai", "Juni", "Juli", "August", "September", "Oktober", "November",
          "Dezember")
MAX_ZEILEN_TEXT = 40
MAX_ZEILEN_EXPORT = 20000
KOPF_EXPORT = ("Nr", "Datum", "Art", "Kategorie", "Betrag in Euro", "Text", "Beleg", "Kundenauftrag", "Rechnung")
OHNE_KATEGORIE = "Ohne Kategorie"
BOM = "\ufeff"  # Excel erkennt daran UTF-8
# Spaltenausdruck: Kategorie, wie sie angezeigt wird (Buchungen aus Rechnungen ohne Kategorie heißen "Rechnung")
_KAT_SQL = ("COALESCE(NULLIF(kategorie, ''), CASE WHEN rechnung_id IS NOT NULL THEN 'Rechnung' ELSE '%s' END)"
            % OHNE_KATEGORIE)


# ------------------------------------------------------------ Hilfen ---

def _monat(text):
    """"2026-11" oder "11.2026" (leer: dieser Monat) -> "2026-11". Wirft WerkzeugFehler."""
    t = (text or "").strip()
    if not t:
        return heute().strftime("%Y-%m")
    m = re.match(r"^(\d{4})-(\d{1,2})$", t) or re.match(r"^()(\d{1,2})\.(\d{4})$", t)
    if m:
        jahr, monat = (m.group(1), m.group(2)) if m.group(1) else (m.group(3), m.group(2))
        if 1 <= int(monat) <= 12 and 2000 <= int(jahr) <= 2100:
            return "%s-%02d" % (jahr, int(monat))
    raise WerkzeugFehler("Monat bitte als JJJJ-MM, z. B. 2026-11 (nicht %r)." % t[:30])


def _vormonat(monat):
    jahr, nr = int(monat[:4]), int(monat[5:7])
    return "%d-%02d" % (jahr - 1, 12) if nr == 1 else "%d-%02d" % (jahr, nr - 1)


def _monat_text(monat):
    return "%s %s" % (MONATE[int(monat[5:7]) - 1], monat[:4])


def _kategorie(art, text):
    """Eine feste Kategorie (Groß/klein egal) -> ihre richtige Schreibweise. Leer: "Sonstiges"."""
    t = " ".join(str(text or "").split())
    if not t:
        return "Sonstiges"
    for k in KATEGORIEN[art]:
        if k.lower() == t.lower() or (k == "Büro" and t.lower() == "buero") or (k == "Gebühren" and t.lower() == "gebuehren"):
            return k
    raise WerkzeugFehler("Kategorie %r gibt es bei %s nicht. Möglich: %s."
                         % (t[:40], "Einnahmen" if art == "einnahme" else "Ausgaben", ", ".join(KATEGORIEN[art])))


def _kategorie_filter(text):
    """Filter beim Anzeigen: irgendeine feste Kategorie (aus beiden Listen) - gibt die richtige Schreibweise zurück."""
    t = " ".join(str(text or "").split())
    if not t:
        return None
    for k in KATEGORIEN_EINNAHME + KATEGORIEN_AUSGABE:
        if k.lower() == t.lower() or (k == "Büro" and t.lower() == "buero") or (k == "Gebühren" and t.lower() == "gebuehren"):
            return k
    raise WerkzeugFehler("Kategorie %r gibt es nicht. Möglich: %s | %s." % (
        t[:40], ", ".join(KATEGORIEN_EINNAHME), ", ".join(k for k in KATEGORIEN_AUSGABE if k not in KATEGORIEN_EINNAHME)))


def _gruppen(sp, von, bis, kategorie=None):
    """Summen aus der Tabelle (SQL, ohne Obergrenze): {"einnahme": {Kategorie: (Cent, Anzahl)}, "ausgabe": {...},
    "aus_rechnungen": Cent}. ``von``/``bis`` als "JJJJ-MM-TT", beide einschließlich."""
    wo = "substr(datum, 1, 10) >= ? AND substr(datum, 1, 10) <= ?"
    werte = [von, bis]
    if kategorie:
        wo += " AND lower(%s) = lower(?)" % _KAT_SQL
        werte.append(kategorie)
    zeilen = sp.sql_lesen("SELECT art, %s AS kat, SUM(betrag_cent) AS summe, COUNT(*) AS n FROM %s WHERE %s "  # noqa: S608
                          "GROUP BY art, kat" % (_KAT_SQL, betrieb.BUCHUNGEN.name, wo), tuple(werte))
    ergebnis = {"einnahme": {}, "ausgabe": {}}
    for z in zeilen:
        if z["art"] in ergebnis:
            ergebnis[z["art"]][z["kat"]] = (int(z["summe"] or 0), int(z["n"]))
    aus_rechnungen = sp.sql_lesen("SELECT SUM(betrag_cent) AS summe FROM %s WHERE %s AND art='einnahme' "  # noqa: S608
                                  "AND rechnung_id IS NOT NULL" % (betrieb.BUCHUNGEN.name, wo), tuple(werte))
    ergebnis["aus_rechnungen"] = int(aus_rechnungen[0]["summe"] or 0)
    return ergebnis


def _summe(gruppen, art):
    return sum(c for c, _ in gruppen[art].values())


def _anzahl(gruppen):
    return sum(n for art in ("einnahme", "ausgabe") for _, n in gruppen[art].values())


def _monat_grenzen(monat):
    return monat + "-01", monat + "-31"  # Textvergleich: "2026-11-31" liegt hinter jedem Novembertag


def _buchungen(sp, von, bis, kategorie=None, ordnung="datum DESC, id DESC", limit=200):
    wo = "substr(datum, 1, 10) >= ? AND substr(datum, 1, 10) <= ?"
    werte = [von, bis]
    if kategorie:
        wo += " AND lower(%s) = lower(?)" % _KAT_SQL
        werte.append(kategorie)
    return betrieb.BUCHUNGEN.liste(sp, wo=wo, werte=werte, ordnung=ordnung, limit=limit)


def _kat_anzeige(b):
    return b.get("kategorie") or ("Rechnung" if b.get("rechnung_id") else OHNE_KATEGORIE)


def _buchung_zeile(b):
    teile = ["#%d" % b["id"], betrieb.datum_text(b["datum"]), ART_NAME.get(b["art"], b["art"]), _kat_anzeige(b),
             betrieb.euro(b["betrag_cent"])]
    zeile = " · ".join(teile)
    if b.get("text"):
        zeile += " - " + fremdtext(b["text"], 120)
    if b.get("beleg"):
        zeile += " [Beleg: %s]" % einzeilig(b["beleg"], 80)
    if b.get("auftrag_id"):
        zeile += " [Kundenauftrag #%d]" % b["auftrag_id"]
    if b.get("rechnung_id"):
        zeile += " [aus Rechnung #%d]" % b["rechnung_id"]
    return zeile


def _saldo_text(gruppen):
    e, a = _summe(gruppen, "einnahme"), _summe(gruppen, "ausgabe")
    return "Einnahmen %s, Ausgaben %s, Saldo %s" % (betrieb.euro(e), betrieb.euro(a), betrieb.euro(e - a))


def _groesste_ausgabe(gruppen):
    """(Kategorie, Cent) der größten Ausgabenkategorie oder None."""
    if not gruppen["ausgabe"]:
        return None
    kat, (cent, _) = max(gruppen["ausgabe"].items(), key=lambda x: (x[1][0], x[0]))
    return (kat, cent) if cent > 0 else None


# -------------------------------------------------------- Erfassen ---

def _gleiche_rechnungsbuchung(sp, betrag_cent, tag):
    return betrieb.BUCHUNGEN.liste(sp, wo="art='einnahme' AND rechnung_id IS NOT NULL AND betrag_cent=? "
                                          "AND substr(datum, 1, 10)=?", werte=(betrag_cent, tag), limit=3)


def _erfassen(ctx, p):
    betrieb.nur_geschaeft(ctx)
    sp = ctx.agent.speicher
    art = p["art"]
    betrag = betrieb.euro_zu_cent(p["betrag"])
    if betrag <= 0:
        raise WerkzeugFehler("Der Betrag muss größer als 0 sein. Ob Einnahme oder Ausgabe, steht bei art; "
                             "eine falsche Buchung wird gelöscht und neu erfasst.")
    tag = p.get("datum") or heute().isoformat()
    ohne_kategorie = not p.get("kategorie")
    kategorie = _kategorie(art, p.get("kategorie"))
    text = einzeilig(p.get("text") or "", 200)
    beleg = None
    if p.get("beleg"):
        beleg = einzeilig(p["beleg"], 200)
        ziel, _, _ = pfad_aufloesen(ctx.agent.konfig, beleg)  # nur Prüfung: liegt der Pfad in einem erlaubten Ordner?
        if not os.path.exists(ziel):
            beleg_hinweis = "Die Belegdatei gibt es (noch) nicht unter diesem Pfad - gespeichert ist nur der Verweis."
        else:
            beleg_hinweis = "Beleg: nur als Verweis gespeichert."
    else:
        beleg_hinweis = ""
    auftrag_id = None
    if p.get("kundenauftrag"):
        auftrag_id = int(p["kundenauftrag"])
        if not betrieb.AUFTRAEGE.holen(sp, auftrag_id):
            raise WerkzeugFehler("Ein Kundenauftrag mit der Nummer %d gibt es nicht." % auftrag_id)
    hinweise = []
    if art == "einnahme":
        for r in _gleiche_rechnungsbuchung(sp, betrag, tag):
            rechnung = betrieb.RECHNUNGEN.holen(sp, r["rechnung_id"]) or {}
            hinweise.append("ACHTUNG: Es gibt schon eine Buchung aus einer bezahlten Rechnung (#%d%s) mit gleichem Betrag "
                            "und Datum. Ist das dieselbe Zahlung, ist sie jetzt doppelt gezählt - dann die neue Buchung "
                            "mit buchung_loeschen wieder entfernen."
                            % (r["id"], ", Rechnung %s" % rechnung["nummer"] if rechnung.get("nummer") else ""))
    gleiche = betrieb.BUCHUNGEN.liste(sp, wo="art=? AND betrag_cent=? AND substr(datum, 1, 10)=? AND rechnung_id IS NULL "
                                             "AND COALESCE(text, '')=?", werte=(art, betrag, tag, text), limit=1)
    if gleiche:
        hinweise.append("Hinweis: Es gibt schon eine gleiche Buchung (#%d). Ist es keine zweite, bitte eine löschen."
                        % gleiche[0]["id"])
    if tag > heute().isoformat():
        hinweise.append("Hinweis: Das Datum liegt in der Zukunft.")
    nr = betrieb.BUCHUNGEN.anlegen(sp, datum=tag, art=art, betrag_cent=betrag, kategorie=kategorie, text=text or None,
                                   beleg=beleg, auftrag_id=auftrag_id)
    zeilen = ["Gebucht (#%d): %s %s, %s, am %s%s." % (nr, ART_NAME[art], betrieb.euro(betrag), kategorie,
                                                      betrieb.datum_text(tag),
                                                      " (keine Kategorie genannt, daher Sonstiges)" if ohne_kategorie else "")]
    if beleg_hinweis:
        zeilen.append(beleg_hinweis)
    zeilen += hinweise
    zeilen.append(HINWEIS)
    return {"text": "\n".join(zeilen)}


# --------------------------------------------------------- Anzeigen ---

def _anzeigen(ctx, p):
    betrieb.nur_geschaeft(ctx)
    sp = ctx.agent.speicher
    monat = _monat(p.get("monat"))
    kategorie = _kategorie_filter(p.get("kategorie"))
    von, bis = _monat_grenzen(monat)
    gruppen = _gruppen(sp, von, bis, kategorie)
    kopf = "Einnahmen und Ausgaben %s%s" % (_monat_text(monat), " - nur Kategorie %s" % kategorie if kategorie else "")
    if not _anzahl(gruppen):
        return {"text": "%s: keine Buchungen.\n%s" % (kopf, HINWEIS)}
    zeilen = [kopf + ":"]
    for art, titel in (("einnahme", "Einnahmen"), ("ausgabe", "Ausgaben")):
        zeilen.append("%s: %s (%d Buchungen)" % (titel, betrieb.euro(_summe(gruppen, art)),
                                                 sum(n for _, n in gruppen[art].values())))
        zeilen += ["  - %s: %s (%d)" % (k, betrieb.euro(c), n) for k, (c, n) in sorted(gruppen[art].items())]
    if gruppen["aus_rechnungen"]:
        zeilen.append("Davon aus bezahlten Rechnungen: %s (legt die Rechnungen-Erweiterung an)"
                      % betrieb.euro(gruppen["aus_rechnungen"]))
    saldo = _summe(gruppen, "einnahme") - _summe(gruppen, "ausgabe")
    zeilen.append("Saldo: %s" % betrieb.euro(saldo))
    vor = _vormonat(monat)
    alt = _gruppen(sp, *_monat_grenzen(vor), kategorie)
    if _anzahl(alt):
        alt_saldo = _summe(alt, "einnahme") - _summe(alt, "ausgabe")
        zeilen.append("Vormonat (%s): %s. Saldo-Unterschied: %s" % (_monat_text(vor), _saldo_text(alt),
                                                                   betrieb.euro(saldo - alt_saldo)))
    else:
        zeilen.append("Vormonat (%s): keine Buchungen, kein Vergleich möglich." % _monat_text(vor))
    buchungen = _buchungen(sp, von, bis, kategorie, limit=MAX_ZEILEN_TEXT + 1)
    zeilen.append("Buchungen (neueste zuerst%s):" % (", die ersten %d" % MAX_ZEILEN_TEXT if len(buchungen) > MAX_ZEILEN_TEXT
                                                      else ""))
    zeilen += ["- " + _buchung_zeile(b) for b in buchungen[:MAX_ZEILEN_TEXT]]
    zeilen.append(HINWEIS)
    return {"text": "\n".join(zeilen)}


# --------------------------------------------------------- Löschen ---

def _loeschen_vorbereiten(ctx, p):
    betrieb.nur_geschaeft(ctx)
    if not betrieb.BUCHUNGEN.holen(ctx.agent.speicher, int(p["id"])):
        raise WerkzeugFehler("Eine Buchung mit der Nummer %d gibt es nicht." % int(p["id"]))
    return {}


def _loeschen_vorschau(ctx, p):
    b = betrieb.BUCHUNGEN.holen(ctx.agent.speicher, int(p["id"]))
    if not b:
        return "Die Buchung #%d gibt es nicht mehr - es passiert nichts." % int(p["id"])
    zeilen = ["Diese Buchung wird gelöscht und kann nicht zurückgeholt werden (nur neu erfassen):", _buchung_zeile(b)]
    if b.get("rechnung_id"):
        zeilen.append("Sie stammt aus einer bezahlten Rechnung; die Rechnung selbst bleibt unverändert.")
    return "\n".join(zeilen)


def _loeschen(ctx, p):
    betrieb.nur_geschaeft(ctx)
    sp = ctx.agent.speicher
    b = betrieb.BUCHUNGEN.holen(sp, int(p["id"]))
    if not b:
        raise WerkzeugFehler("Eine Buchung mit der Nummer %d gibt es nicht (mehr)." % int(p["id"]))
    betrieb.BUCHUNGEN.loeschen(sp, b["id"])
    return {"text": "Gelöscht: %s\n%s" % (_buchung_zeile(b), HINWEIS)}


# ---------------------------------------------------------- Export ---

def csv_zelle(wert):
    """Eine Zelle für CSV mit Semikolon: gegen CSV-Injection gesichert (beginnt der Text mit = + - @ oder Tab/Zeilen-
    umbruch - auch nach Leerzeichen -, kommt ein ' davor, dann rechnet Excel nicht) und bei Bedarf in Anführungszeichen."""
    text = "" if wert is None else str(wert)
    if text and (text[0] in "=+-@\t\r\n" or text.lstrip()[:1] in ("=", "+", "-", "@")):
        text = "'" + text
    if any(z in text for z in ';"\r\n'):
        text = '"%s"' % text.replace('"', '""')
    return text


def _betrag_csv(cent):
    """Deutsche Schreibweise ohne Tausenderpunkt und ohne €: 123456 -> "1234,56" (so liest Excel sie als Zahl)."""
    return betrieb.euro(cent, zeichen=False).replace(".", "")


def csv_zeile(zellen):
    return ";".join(csv_zelle(z) for z in zellen)


def csv_inhalt(sp, monat):
    """(CSV-Text mit BOM am Anfang, Anzahl Buchungen) oder (None, 0), wenn der Monat leer ist."""
    von, bis = _monat_grenzen(monat)
    buchungen = _buchungen(sp, von, bis, ordnung="datum ASC, id ASC", limit=MAX_ZEILEN_EXPORT + 1)
    if not buchungen:
        return None, 0
    if len(buchungen) > MAX_ZEILEN_EXPORT:
        raise WerkzeugFehler("Mehr als %d Buchungen in einem Monat - das ist sicher ein Fehler, bitte prüfen." % MAX_ZEILEN_EXPORT)
    zeilen = [csv_zeile(["Hinweis", "Übersicht des Betriebs - keine Buchhaltung und kein GoBD-konformes Kassenbuch; "
                                    "die Buchhaltung macht der Steuerberater. Zeitraum: %s" % _monat_text(monat)]),
              csv_zeile(KOPF_EXPORT)]
    summen = {"einnahme": 0, "ausgabe": 0}
    for b in buchungen:
        if b["art"] in summen:
            summen[b["art"]] += int(b["betrag_cent"])
        nummer = ""
        if b.get("rechnung_id"):
            rechnung = betrieb.RECHNUNGEN.holen(sp, b["rechnung_id"]) or {}
            nummer = rechnung.get("nummer") or "#%d" % b["rechnung_id"]
        zeilen.append(csv_zeile([b["id"], betrieb.datum_text(b["datum"]), ART_NAME.get(b["art"], b["art"]),
                                 _kat_anzeige(b), _betrag_csv(b["betrag_cent"]), b.get("text") or "",
                                 b.get("beleg") or "", b.get("auftrag_id") or "", nummer]))
    zeilen.append(csv_zeile([]))
    zeilen.append(csv_zeile(["", "", "Summe Einnahmen", "", _betrag_csv(summen["einnahme"])]))
    zeilen.append(csv_zeile(["", "", "Summe Ausgaben", "", _betrag_csv(summen["ausgabe"])]))
    return BOM + "\r\n".join(zeilen) + "\r\n", len(buchungen)


def _export(ctx, p):
    betrieb.nur_geschaeft(ctx)
    monat = _monat(p.get("monat"))
    inhalt, anzahl = csv_inhalt(ctx.agent.speicher, monat)
    if inhalt is None:
        raise WerkzeugFehler("Im %s gibt es keine Buchungen - es gibt nichts zu exportieren." % _monat_text(monat))
    pfad = werkstatt_datei(ctx.agent, "export", "Einnahmen-Ausgaben %s.csv" % monat, inhalt)
    return {"text": "CSV-Datei erstellt: %s (%d Buchungen, Semikolon-getrennt, deutsche Beträge, öffnet in Excel oder "
                    "Numbers per Doppelklick). Sie liegt nur in eurer Werkstatt - verschickt wurde nichts; an den "
                    "Steuerberater schickt ihr sie selbst.\n%s" % (pfad, anzahl, HINWEIS)}


# ------------------------------------------------------------- Hooks ---

def werkzeuge():
    return [
        Werkzeug("buchung_erfassen", "Hält eine echte Einnahme oder Ausgabe fest (Betrag in Euro, z. B. 45,90). "
                 "Nur Beträge, die der Nutzer genannt hat - nie schätzen. Beleg = nur Pfad als Verweis.",
                 _erfassen,
                 [P("art", True, art="wahl", wahl=("einnahme", "ausgabe")),
                  P("betrag", True, hilfe="Euro, z. B. 45,90", maximal=20),
                  P("datum", art="tag", hilfe="JJJJ-MM-TT oder TT.MM.JJJJ, Standard heute"),
                  P("kategorie", hilfe="Einnahme: %s. Ausgabe: %s" % (", ".join(KATEGORIEN_EINNAHME),
                                                                        ", ".join(KATEGORIEN_AUSGABE)), maximal=40),
                  P("text", hilfe="kurz, z. B. Diesel Tankstelle", maximal=200),
                  P("beleg", hilfe="Pfad in der Werkstatt oder downloads:..., nur als Verweis", maximal=200),
                  P("kundenauftrag", art="zahl", hilfe="Nummer des Kundenauftrags", bereich=(1, 10 ** 9))],
                 stufe=MELDUNG),
        Werkzeug("buchungen_anzeigen", "Zeigt die Einnahmen und Ausgaben eines Monats: Summen je Kategorie, Saldo, "
                 "Vergleich mit dem Vormonat und die einzelnen Buchungen.", _anzeigen,
                 [P("monat", hilfe="JJJJ-MM, Standard: dieser Monat", maximal=10),
                  P("kategorie", hilfe="nur diese Kategorie, z. B. Material", maximal=40)],
                 stufe=FREI, liefert_daten=True),
        Werkzeug("buchung_loeschen", "Löscht eine Buchung (nur mit Freigabe des Nutzers). Nummer aus buchungen_anzeigen.",
                 _loeschen, [P("id", True, art="zahl", hilfe="Nummer der Buchung", bereich=(1, 10 ** 9))],
                 stufe=FREIGABE, vorschau=_loeschen_vorschau, vorbereiten=_loeschen_vorbereiten, nur_chat=True,
                 risiko="Löschen von Buchungsdaten kann nicht rückgängig gemacht werden."),
        Werkzeug("kassen_export", "Schreibt die Buchungen eines Monats als CSV für den Steuerberater in die Werkstatt "
                 "(Ordner export). Versendet nichts.", _export,
                 [P("monat", hilfe="JJJJ-MM, Standard: dieser Monat", maximal=10)], stufe=MELDUNG),
    ]


def bausteine():
    return [Baustein(
        "kasse", "KASSE (Einnahmen und Ausgaben - Übersicht, keine Buchhaltung)",
        muster(r"\beinnahme", r"\bausgabe", r"\bkasse", r"ausgegeben", r"eingenommen", r"\bbeleg", r"quittung",
               r"tankquittung", r"\bsaldo"),
        (),
        "- Mit \"buchung_erfassen\" hältst du nur echte Beträge fest, die der Nutzer genannt hat. Fehlt Betrag oder "
        "Art (Einnahme/Ausgabe), frag nach - nie schätzen oder runden.\n"
        "- Kategorie nur aus der festen Liste; sag dem Nutzer, welche du genommen hast. Ein Beleg (Quittung, "
        "Tankquittung) wird nur als Pfad verwiesen, JARVIS liest ihn dabei nicht.\n"
        "- Bezahlte Rechnungen bucht die Rechnungen-Erweiterung selbst. Bucht der Nutzer eine Rechnungszahlung von "
        "Hand, weise auf mögliche Doppelzählung hin.\n"
        "- Löschen (\"buchung_loeschen\") braucht das ausdrückliche Ja des Nutzers.\n"
        "- Das ist eine Übersicht für euch, keine Buchhaltung und kein GoBD-konformes Kassenbuch: Steuerfragen und "
        "die Buchhaltung gehören zum Steuerberater. \"kassen_export\" erstellt nur die CSV-Datei, verschickt nichts.",
        {})]


def lage(agent):
    sp = agent.speicher
    monat = heute().strftime("%Y-%m")
    gruppen = _gruppen(sp, *_monat_grenzen(monat))
    e, a = _summe(gruppen, "einnahme"), _summe(gruppen, "ausgabe")
    if a > 0 and a > e:
        return ["Kasse %s: bisher mehr Ausgaben (%s) als Einnahmen (%s), Saldo %s. Nur Übersicht, keine Buchhaltung."
                % (_monat_text(monat), betrieb.euro(a), betrieb.euro(e), betrieb.euro(e - a))]
    return []


def _tag_text(wert, standard):
    if isinstance(wert, datetime.datetime):
        wert = wert.date()
    if isinstance(wert, datetime.date):
        return wert.isoformat()
    try:
        return datetime.date.fromisoformat(str(wert)[:10]).isoformat()
    except ValueError:
        return standard


def bericht(agent, von, bis):
    """Einnahmen, Ausgaben, Saldo und größte Ausgabenkategorie im Zeitraum (von/bis einschließlich)."""
    erster = heute().replace(day=1).isoformat()
    von_tag = _tag_text(von, erster)
    bis_tag = _tag_text(bis, heute().isoformat())
    gruppen = _gruppen(agent.speicher, von_tag, bis_tag)
    if not _anzahl(gruppen):
        return None
    e, a = _summe(gruppen, "einnahme"), _summe(gruppen, "ausgabe")
    zeilen = ["Einnahmen %s, Ausgaben %s, Saldo %s (%d Buchungen, %s bis %s)"
              % (betrieb.euro(e), betrieb.euro(a), betrieb.euro(e - a), _anzahl(gruppen), betrieb.datum_text(von_tag),
                 betrieb.datum_text(bis_tag))]
    gross = _groesste_ausgabe(gruppen)
    if gross:
        zeilen.append("Größte Ausgabenkategorie: %s mit %s (%d %% der Ausgaben)"
                      % (gross[0], betrieb.euro(gross[1]), (gross[1] * 100 + a // 2) // a))
    zeilen.append("Nur Übersicht, keine Buchhaltung - die macht der Steuerberater.")
    return {"titel": "Kasse (Einnahmen und Ausgaben)", "zeilen": zeilen,
            "kennzahlen": [("Einnahmen", betrieb.euro(e)), ("Ausgaben", betrieb.euro(a)), ("Saldo", betrieb.euro(e - a))]}


def anzeige(agent, bereich):
    if bereich != betrieb.bereich(agent.konfig):
        return None
    sp = agent.speicher
    monat = heute().strftime("%Y-%m")
    von, bis = _monat_grenzen(monat)
    gruppen = _gruppen(sp, von, bis)
    e, a = _summe(gruppen, "einnahme"), _summe(gruppen, "ausgabe")
    kategorien = sorted(set(gruppen["einnahme"]) | set(gruppen["ausgabe"]))
    zeilen = [[k, betrieb.euro(gruppen["einnahme"].get(k, (0, 0))[0]), betrieb.euro(gruppen["ausgabe"].get(k, (0, 0))[0])]
              for k in kategorien]
    if zeilen:
        zeilen.append(["Summe", betrieb.euro(e), betrieb.euro(a)])
    letzte = [[betrieb.datum_text(b["datum"]), ART_NAME.get(b["art"], b["art"]), _kat_anzeige(b), betrieb.euro(b["betrag_cent"]),
               b.get("text") or "", "#%d" % b["id"]] for b in _buchungen(sp, von, bis, limit=50)]
    return {"status": [("Monat", _monat_text(monat)), ("Einnahmen", betrieb.euro(e)), ("Ausgaben", betrieb.euro(a)),
                       ("Saldo", betrieb.euro(e - a))],
            "tabellen": [{"titel": "Kasse %s je Kategorie" % _monat_text(monat), "spalten": ["Kategorie", "Einnahmen", "Ausgaben"],
                          "zeilen": zeilen, "hinweis": HINWEIS},
                         {"titel": "Buchungen %s" % _monat_text(monat),
                          "spalten": ["Datum", "Art", "Kategorie", "Betrag", "Text", "Nr"], "zeilen": letzte,
                          "hinweis": HINWEIS}]}
