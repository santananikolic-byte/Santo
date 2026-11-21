# -*- coding: utf-8 -*-
"""Angebot als druckbare HTML-Datei (Sales-Agent).

- Der Betrag kommt immer vom Inhaber – nie geschätzt oder vorgeschlagen.
- Fehlende Angaben (Anbieter, Anschrift, Umsatzsteuer, Gültigkeit, Lieferzeit) erscheinen als gelb
  markierte Felder. Sie lassen sich im Browser anklicken und ausfüllen (contenteditable, ohne
  JavaScript); danach „Drucken → Als PDF sichern“. Änderungen im Browser werden nicht gespeichert.
- Solange das Angebot im Status „entwurf“ ist, steht groß „ENTWURF – vor Versand prüfen“ darauf.

Zwei Arten:
- ``einmalig`` (Standard): ein Paket zum Festpreis (z. B. Webseiten- oder Google-Profil-Paket).
- ``reinigung_dauerauftrag``: regelmäßige Reinigung mit Leistungsverzeichnis (Bereich, Fläche, Turnus) und
  monatlicher Pauschale. Den Monatspreis gibt der Inhaber an oder er kommt aus einer abgeschlossenen
  Kalkulation (Finance-Agent, ``kalkulation_reinigung``). Ist deren Preis OFFEN (kein Stundensatz), wird
  kein Angebot erstellt. Vertragsbeginn, Laufzeit und Kündigungsfrist bleiben gelbe Felder, bis der
  Inhaber sie festlegt.
"""

import datetime
import os
from decimal import Decimal

from . import bereinigen, datum_deutsch, esc, liste_bereinigen
from . import kalkulation as kalk_modul
from ..wallet import betrag_in_cent, euro

ARTEN = ("einmalig", "reinigung_dauerauftrag")
DAUER_TITEL = "Angebot: Regelmäßige Reinigung (Dauerauftrag)"
PREIS_OFFEN_MELDUNG = ("Der Preis der Kalkulation ist OFFEN, weil kein Stundensatz festgelegt ist. Bitte erst den "
                       "Stundensatz festlegen (Einstellungen) und neu rechnen – oder den Monatspreis selbst als "
                       "betrag angeben.")

STANDARD_TITEL = "Angebot: Webseiten-Paket"
STANDARD_POSITION = "Webseiten-Paket (eine Seite, für Handy und Computer)"
STANDARD_LEISTUNGEN = [
    "Eine Webseite mit Leistungen, Einsatzgebiet, Erreichbarkeit und Kontakt",
    "Gut lesbar auf Handy, Tablet und Computer",
    "Anrufen und E-Mail mit einem Fingertipp",
    "Ohne Fremddienste: keine Tracker, keine fremden Schriftarten",
    "Platz für Impressum und Datenschutzerklärung (Texte liefert der Kunde)",
    "Übergabe als fertige Datei",
]
NICHT_ENTHALTEN = "Domain und Hosting, Rechtstexte (Impressum, Datenschutzerklärung), Fotos und Logo-Gestaltung, " \
                  "laufende Pflege."


def eingabe_pruefen(eingabe, kalk=None):
    """Prüft die Eingabe. ``kalk`` = Ergebnis von ``kalkulation.aus_aufgabe`` (nur für Daueraufträge)."""
    if not isinstance(eingabe, dict):
        raise ValueError("Eingabe muss ein Objekt sein.")
    art = bereinigen(eingabe.get("art"), 40)
    hat_kalk = kalk is not None or eingabe.get("kalkulation_aufgabe_id") not in (None, "")
    art = art or ("reinigung_dauerauftrag" if hat_kalk else "einmalig")
    if art not in ARTEN:
        raise ValueError("Unbekannte Angebotsart – erlaubt: einmalig, reinigung_dauerauftrag.")
    if art == "reinigung_dauerauftrag":
        return _dauerauftrag_pruefen(eingabe, kalk)
    if hat_kalk:
        raise ValueError("Eine Kalkulation passt nur zur Angebotsart reinigung_dauerauftrag.")
    if eingabe.get("betrag") in (None, ""):
        raise ValueError("Pflichtfeld fehlt: betrag (den Preis legt der Inhaber fest).")
    return {
        "art": "einmalig",
        "betrag_cent": betrag_in_cent(eingabe.get("betrag")),
        "kontakt_id": bereinigen(eingabe.get("kontakt_id"), 64) or None,
        "produkt_id": bereinigen(eingabe.get("produkt_id"), 64) or None,
        "titel": bereinigen(eingabe.get("titel"), 120, streng=True, name="titel"),
        "leistungen": liste_bereinigen(eingabe.get("leistungen"), 120, 15, name="Leistung"),
        "lieferzeit": bereinigen(eingabe.get("lieferzeit"), 80, streng=True, name="lieferzeit"),
        "gueltig_bis": bereinigen(eingabe.get("gueltig_bis"), 40, streng=True, name="gueltig_bis"),
        "preis_hinweis": bereinigen(eingabe.get("preis_hinweis"), 160, streng=True, name="preis_hinweis"),
        "anbieter": bereinigen(eingabe.get("anbieter"), 120, streng=True, name="anbieter"),
        "anbieter_anschrift": bereinigen(eingabe.get("anbieter_anschrift"), 200, streng=True, name="anbieter_anschrift"),
        "anbieter_kontakt": bereinigen(eingabe.get("anbieter_kontakt"), 200, streng=True, name="anbieter_kontakt"),
    }


def _gemeinsam(eingabe):
    return {
        "kontakt_id": bereinigen(eingabe.get("kontakt_id"), 64) or None,
        "produkt_id": bereinigen(eingabe.get("produkt_id"), 64) or None,
        "titel": bereinigen(eingabe.get("titel"), 120, streng=True, name="titel"),
        "gueltig_bis": bereinigen(eingabe.get("gueltig_bis"), 40, streng=True, name="gueltig_bis"),
        "preis_hinweis": bereinigen(eingabe.get("preis_hinweis"), 160, streng=True, name="preis_hinweis"),
        "anbieter": bereinigen(eingabe.get("anbieter"), 120, streng=True, name="anbieter"),
        "anbieter_anschrift": bereinigen(eingabe.get("anbieter_anschrift"), 200, streng=True, name="anbieter_anschrift"),
        "anbieter_kontakt": bereinigen(eingabe.get("anbieter_kontakt"), 200, streng=True, name="anbieter_kontakt"),
    }


def positionen_pruefen(roh):
    """Leistungsverzeichnis von Hand: Liste aus Texten oder {bezeichnung, flaeche_m2?, turnus?}."""
    if not isinstance(roh, list) or not roh:
        raise ValueError("Pflichtfeld fehlt: positionen (Leistungsverzeichnis, z. B. Treppenhaus 1× pro Woche).")
    if len(roh) > kalk_modul.MAX_POSITIONEN:
        raise ValueError("Zu viele Positionen (höchstens %d)." % kalk_modul.MAX_POSITIONEN)
    ergebnis = []
    for nr, p in enumerate(roh, start=1):
        if isinstance(p, str):
            p = {"bezeichnung": p}
        if not isinstance(p, dict):
            raise ValueError("Position %d muss Text oder Objekt sein." % nr)
        bezeichnung = bereinigen(p.get("bezeichnung"), 80, streng=True, name="Bezeichnung (Position %d)" % nr)
        if not bezeichnung:
            raise ValueError("Position %d: Bezeichnung fehlt." % nr)
        flaeche = None
        if p.get("flaeche_m2") not in (None, ""):
            flaeche = float(kalk_modul.zahl(p.get("flaeche_m2"), "Fläche in m² (Position %d)" % nr,
                                            Decimal("0.01"), Decimal(1_000_000)))
        turnus = bereinigen(p.get("turnus"), 40, streng=True, name="Turnus (Position %d)" % nr)
        ergebnis.append({"bezeichnung": bezeichnung, "flaeche_m2": flaeche, "turnus": turnus})
    return ergebnis


def _dauerauftrag_pruefen(eingabe, kalk):
    if eingabe.get("kalkulation_aufgabe_id") not in (None, "") and kalk is None:
        raise ValueError("Kalkulation nicht geladen.")
    d = _gemeinsam(eingabe)
    d["art"] = "reinigung_dauerauftrag"
    if eingabe.get("positionen") not in (None, "", []):
        d["positionen"] = positionen_pruefen(eingabe.get("positionen"))
    elif kalk:
        d["positionen"] = positionen_pruefen(kalk["positionen"])
    else:
        d["positionen"] = positionen_pruefen(None)
    if eingabe.get("betrag") not in (None, ""):
        d["betrag_cent"] = betrag_in_cent(eingabe.get("betrag"))
        d["preis_quelle"] = ("vom Inhaber angegeben (Kalkulation hatte keinen Preis)"
                             if kalk and kalk["preis_monat_cent"] is None else "vom Inhaber angegeben")
    elif kalk and kalk["preis_monat_cent"]:
        d["betrag_cent"] = kalk["preis_monat_cent"]
        d["preis_quelle"] = "aus Kalkulation %s" % kalk["aufgabe_id"]
    elif kalk:
        raise ValueError(PREIS_OFFEN_MELDUNG)
    else:
        raise ValueError("Pflichtfeld fehlt: betrag (Monatspreis netto – legt der Inhaber fest) oder "
                         "kalkulation_aufgabe_id.")
    d["kalkulation_aufgabe_id"] = kalk["aufgabe_id"] if kalk else None
    for name, laenge in (("objekt", 200), ("vertragsbeginn", 60), ("laufzeit", 80), ("kuendigungsfrist", 80)):
        d[name] = bereinigen(eingabe.get(name), laenge, streng=True, name=name)
    return d


def inhalt_bauen(d, angebot_id, kontakt=None, produkt=None, heute=None):
    """Alle Angaben, aus denen die Datei entsteht (wird in angebote.inhalt gespeichert)."""
    heute = heute or datetime.date.today().isoformat()
    if d.get("art") == "reinigung_dauerauftrag":
        return _inhalt_dauerauftrag(d, angebot_id, kontakt, heute)
    position = STANDARD_POSITION
    titel = d["titel"] or STANDARD_TITEL
    if produkt:
        position = bereinigen(produkt.get("name"), 120) or position
        if not d["titel"]:
            titel = "Angebot: %s" % position
    return {
        "art": "einmalig",
        "nr": "ANG-%s-%s" % (heute.replace("-", ""), angebot_id[-4:].upper()),
        "datum": heute,
        "titel": titel,
        "position": position,
        "leistungen": d["leistungen"] or list(STANDARD_LEISTUNGEN),
        "paket_hinweis": not d["leistungen"],
        "betrag_cent": d["betrag_cent"],
        "lieferzeit": d["lieferzeit"],
        "gueltig_bis": d["gueltig_bis"],
        "preis_hinweis": d["preis_hinweis"],
        "anbieter": d["anbieter"],
        "anbieter_anschrift": d["anbieter_anschrift"],
        "anbieter_kontakt": d["anbieter_kontakt"],
        "empfaenger": {
            "firma": (kontakt or {}).get("firma") or "",
            "ansprechpartner": (kontakt or {}).get("ansprechpartner") or "",
            "ort": (kontakt or {}).get("ort") or "",
        },
        "kontakt_id": (kontakt or {}).get("id"),
        "produkt_id": (produkt or {}).get("id"),
    }


def _empfaenger(kontakt):
    return {"firma": (kontakt or {}).get("firma") or "",
            "ansprechpartner": (kontakt or {}).get("ansprechpartner") or "",
            "ort": (kontakt or {}).get("ort") or ""}


def _inhalt_dauerauftrag(d, angebot_id, kontakt, heute):
    return {
        "art": "reinigung_dauerauftrag",
        "nr": "ANG-%s-%s" % (heute.replace("-", ""), angebot_id[-4:].upper()),
        "datum": heute,
        "titel": d["titel"] or DAUER_TITEL,
        "positionen": d["positionen"],
        "betrag_cent": d["betrag_cent"],
        "abrechnung": "monatlich",
        "preis_quelle": d["preis_quelle"],
        "kalkulation_aufgabe_id": d["kalkulation_aufgabe_id"],
        "objekt": d["objekt"],
        "vertragsbeginn": d["vertragsbeginn"],
        "laufzeit": d["laufzeit"],
        "kuendigungsfrist": d["kuendigungsfrist"],
        "gueltig_bis": d["gueltig_bis"],
        "preis_hinweis": d["preis_hinweis"],
        "anbieter": d["anbieter"],
        "anbieter_anschrift": d["anbieter_anschrift"],
        "anbieter_kontakt": d["anbieter_kontakt"],
        "empfaenger": _empfaenger(kontakt),
        "kontakt_id": (kontakt or {}).get("id"),
        "produkt_id": None,
    }


def betrag_text(inhalt):
    """Betrag für Listen und Meldungen – bei Daueraufträgen mit „pro Monat (netto)“."""
    if inhalt.get("art") == "reinigung_dauerauftrag":
        return "%s pro Monat (netto)" % euro(inhalt["betrag_cent"])
    return euro(inhalt["betrag_cent"])


def _feld(wert, platzhalter, offen):
    """Gefüllter Wert oder gelbes, im Browser ausfüllbares Feld."""
    if wert:
        return esc(wert)
    return '<span class="feld" contenteditable="true" data-offen="%s">%s</span>' % (esc(offen), esc(platzhalter))


CSS = (
    "@page{size:A4;margin:16mm 16mm 18mm}*{box-sizing:border-box}"
    "body{margin:0;background:#eef0f3;color:#111827;font-family:system-ui,-apple-system,'Segoe UI',Roboto,"
    "'Helvetica Neue',Arial,sans-serif;font-size:15px;line-height:1.5;overflow-wrap:anywhere}"
    ".blatt{background:#fff;max-width:210mm;margin:24px auto;padding:16mm 15mm;box-shadow:0 2px 12px rgba(0,0,0,.08)}"
    ".entwurf{border:3px solid #b91c1c;color:#b91c1c;font-weight:800;text-align:center;padding:8px 12px;"
    "letter-spacing:.05em;margin:0 0 18px}"
    ".nur-bildschirm{background:#eff6ff;border:1px solid #bfdbfe;color:#1e3a8a;border-radius:8px;padding:10px 14px;"
    "margin:0 0 18px;font-size:.9rem}"
    ".kopfzeile{display:flex;flex-wrap:wrap;justify-content:space-between;gap:16px 32px;margin-bottom:28px}"
    ".kopfzeile h1{margin:0;font-size:1.9rem;letter-spacing:.02em}.angebotsdaten{text-align:right}"
    "address{font-style:normal;margin:0 0 26px}h2{font-size:1.15rem;margin:0 0 14px}"
    ".feld{background:#fff3bf;border-bottom:1px dashed #b45309;padding:0 3px;border-radius:2px}"
    ".feld:focus{outline:2px solid #b45309}"
    "table{width:100%;border-collapse:collapse;margin:16px 0}"
    "th,td{text-align:left;padding:10px 8px;border-bottom:1px solid #e5e7eb;vertical-align:top}"
    "th{font-size:.85rem;text-transform:uppercase;letter-spacing:.04em;color:#4b5563}"
    ".betrag{text-align:right;white-space:nowrap}.pos{width:3em}"
    "td ul{margin:6px 0 0;padding-left:18px;color:#374151}"
    ".summe td{font-weight:800;border-top:2px solid #111827;border-bottom:none}"
    "dl{display:grid;grid-template-columns:max-content 1fr;gap:6px 16px;margin:18px 0}dt{font-weight:700}dd{margin:0}"
    ".klein{font-size:.9rem;color:#374151}.unterschrift{margin-top:36px}"
    "@media (max-width:600px){.blatt{margin:0;padding:20px 16px}.angebotsdaten{text-align:left}"
    "th,td{padding:8px 4px}}"
    "@media print{body{background:#fff}.blatt{box-shadow:none;margin:0;padding:0;max-width:none}"
    ".nur-bildschirm{display:none}.feld{background:none;border:none}}"
)


def erzeugen(inhalt, entwurf=True):
    """Druckbare Angebotsseite. ``entwurf=True`` zeigt den ENTWURF-Hinweis (auch im Ausdruck)."""
    if inhalt.get("art") == "reinigung_dauerauftrag":
        return _erzeugen_dauerauftrag(inhalt, entwurf)
    e = inhalt["empfaenger"]
    betrag = esc(euro(inhalt["betrag_cent"]))
    if e.get("ansprechpartner"):
        anrede = "Guten Tag %s," % esc(e["ansprechpartner"])
    else:
        anrede = "Sehr geehrte Damen und Herren,"
    leistungen = "".join("<li>%s</li>" % esc(l) for l in inhalt["leistungen"])
    teile = [
        "<!DOCTYPE html>\n<!-- Erstellt mit AUTONOMOUS (Sales-Agent). Ohne JavaScript. -->\n"
        '<html lang="de">\n<head>\n<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n',
        "<title>%s %s – %s</title>\n" % ("ENTWURF" if entwurf else "Angebot", esc(inhalt["nr"]),
                                         esc(e.get("firma") or "Empfänger offen")),
        "<style>%s</style>\n</head>\n<body>\n<main class=\"blatt\">\n" % CSS,
    ]
    if entwurf:
        teile.append('<p class="entwurf" role="note">ENTWURF – vor Versand prüfen · nicht verbindlich</p>\n')
    teile.append('<p class="nur-bildschirm">Gelb markierte Felder können Sie hier im Browser anklicken und '
                 'ausfüllen. Danach: Drucken → „Als PDF sichern“. Änderungen im Browser werden nicht gespeichert.</p>\n')
    teile.append(
        '<header class="kopfzeile"><div class="absender"><strong>%s</strong><br>%s<br>%s</div>'
        '<div class="angebotsdaten"><h1>Angebot</h1><p>Nr. %s<br>Datum: %s</p></div></header>\n'
        % (_feld(inhalt["anbieter"], "[Ihr Firmenname und Rechtsform]", "Firmenname des Anbieters ergänzen"),
           _feld(inhalt["anbieter_anschrift"], "[Straße, PLZ Ort]", "Anschrift des Anbieters ergänzen"),
           _feld(inhalt["anbieter_kontakt"], "[Telefon · E-Mail]", "Kontakt des Anbieters ergänzen"),
           esc(inhalt["nr"]), esc(datum_deutsch(inhalt["datum"]))))
    teile.append(
        "<address>%s<br>%s%s<br>%s %s</address>\n"
        % (_feld(e.get("firma"), "[Firma des Empfängers]", "Empfänger ergänzen"),
           (esc(e["ansprechpartner"]) + "<br>") if e.get("ansprechpartner") else "",
           _feld("", "[Straße, Hausnummer]", "Anschrift des Empfängers ergänzen"),
           _feld("", "[PLZ]", "Postleitzahl des Empfängers ergänzen"),
           _feld(e.get("ort"), "[Ort]", "Ort des Empfängers ergänzen")))
    teile.append("<h2>%s</h2>\n<p>%s</p>\n<p>gern bieten wir Ihnen die folgenden Leistungen an:</p>\n"
                 % (esc(inhalt["titel"]), anrede))
    teile.append(
        '<table><thead><tr><th class="pos">Pos.</th><th>Leistung</th><th class="betrag">Betrag</th></tr></thead>'
        '<tbody><tr><td class="pos">1</td><td><strong>%s</strong><ul>%s</ul></td><td class="betrag">%s</td></tr>'
        '<tr class="summe"><td></td><td>Gesamtpreis</td><td class="betrag">%s</td></tr></tbody></table>\n'
        % (esc(inhalt["position"]), leistungen, betrag, betrag))
    teile.append('<p class="klein">%s</p>\n' % _feld(inhalt["preis_hinweis"],
                                                    "[Angabe zur Umsatzsteuer – vom Inhaber zu ergänzen]",
                                                    "Umsatzsteuer-Hinweis ergänzen"))
    teile.append("<dl><dt>Lieferzeit</dt><dd>%s</dd><dt>Angebot gültig bis</dt><dd>%s</dd></dl>\n"
                 % (_feld(inhalt["lieferzeit"], "[Lieferzeit – vom Inhaber festzulegen]", "Lieferzeit festlegen"),
                    _feld(inhalt["gueltig_bis"], "[Datum – vom Inhaber festzulegen]", "Gültigkeit festlegen")))
    if inhalt.get("paket_hinweis"):
        teile.append('<p class="klein"><strong>Nicht enthalten:</strong> %s</p>\n' % esc(NICHT_ENTHALTEN))
    teile.append("<p>Bei Fragen sind wir gern für Sie da.</p>\n<p>Mit freundlichen Grüßen</p>\n"
                 '<p class="unterschrift">%s</p>\n' % _feld("", "[Name, Unterschrift]", "Unterschrift ergänzen"))
    teile.append("</main>\n</body>\n</html>\n")
    return "".join(teile)


# ---------------------------------------------------------------- Dauerauftrag Reinigung
CSS_DAUER = CSS + (
    ".beispiel{background:#fef3c7;border:2px solid #d97706;color:#78350f;border-radius:8px;padding:10px 14px;"
    "margin:0 0 18px;font-weight:600}"
    "h3{font-size:1rem;margin:22px 0 4px}.objekt{margin:0 0 12px}"
    "th{overflow-wrap:normal}th.pos,td.pos{width:3.6em;white-space:nowrap}"
    ".flaeche,.turnus{white-space:nowrap}"
    "@media (max-width:600px){.turnus{white-space:normal}}"
)


def _flaeche(wert):
    if wert in (None, ""):
        return "–"
    return "%s&nbsp;m²" % esc(kalk_modul.deutsch(Decimal(str(wert))))


def _erzeugen_dauerauftrag(inhalt, entwurf):
    e = inhalt["empfaenger"]
    monat = inhalt["betrag_cent"]
    anrede = ("Guten Tag %s," % esc(e["ansprechpartner"])) if e.get("ansprechpartner") else \
        "Sehr geehrte Damen und Herren,"
    zeilen = []
    for nr, p in enumerate(inhalt["positionen"], start=1):
        zeilen.append('<tr><td class="pos">%d</td><td>%s</td><td class="flaeche">%s</td><td class="turnus">%s</td>'
                      "</tr>" % (nr, esc(p["bezeichnung"]), _flaeche(p.get("flaeche_m2")),
                                 _feld(p.get("turnus"), "[Turnus festlegen]", "Turnus festlegen")))
    teile = [
        "<!DOCTYPE html>\n<!-- Erstellt mit AUTONOMOUS (Sales-Agent). Ohne JavaScript. -->\n"
        '<html lang="de">\n<head>\n<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n',
        "<title>%s %s – %s</title>\n" % ("ENTWURF" if entwurf else "Angebot", esc(inhalt["nr"]),
                                         esc(e.get("firma") or "Empfänger offen")),
        "<style>%s</style>\n</head>\n<body>\n<main class=\"blatt\">\n" % CSS_DAUER,
    ]
    if inhalt.get("beispiel_hinweis"):
        teile.append('<p class="beispiel" role="note">%s</p>\n' % esc(inhalt["beispiel_hinweis"]))
    if entwurf:
        teile.append('<p class="entwurf" role="note">ENTWURF – vor Versand prüfen · nicht verbindlich</p>\n')
    teile.append('<p class="nur-bildschirm">Gelb markierte Felder können Sie hier im Browser anklicken und '
                 "ausfüllen. Danach: Drucken → „Als PDF sichern“. Änderungen im Browser werden nicht gespeichert. "
                 "Monatspreis: %s. Intern: Ein Angebot ist keine Einnahme – als Einnahme zählt erst der geprüfte "
                 "Zahlungseingang.</p>\n" % esc(inhalt.get("preis_quelle") or "vom Inhaber angegeben"))
    teile.append(
        '<header class="kopfzeile"><div class="absender"><strong>%s</strong><br>%s<br>%s</div>'
        '<div class="angebotsdaten"><h1>Angebot</h1><p>Nr. %s<br>Datum: %s</p></div></header>\n'
        % (_feld(inhalt["anbieter"], "[Ihr Firmenname und Rechtsform]", "Firmenname des Anbieters ergänzen"),
           _feld(inhalt["anbieter_anschrift"], "[Straße, PLZ Ort]", "Anschrift des Anbieters ergänzen"),
           _feld(inhalt["anbieter_kontakt"], "[Telefon · E-Mail]", "Kontakt des Anbieters ergänzen"),
           esc(inhalt["nr"]), esc(datum_deutsch(inhalt["datum"]))))
    teile.append(
        "<address>%s<br>%s%s<br>%s %s</address>\n"
        % (_feld(e.get("firma"), "[Firma des Empfängers]", "Empfänger ergänzen"),
           (esc(e["ansprechpartner"]) + "<br>") if e.get("ansprechpartner") else "",
           _feld("", "[Straße, Hausnummer]", "Anschrift des Empfängers ergänzen"),
           _feld("", "[PLZ]", "Postleitzahl des Empfängers ergänzen"),
           _feld(e.get("ort"), "[Ort]", "Ort des Empfängers ergänzen")))
    teile.append("<h2>%s</h2>\n<p>%s</p>\n<p>gern bieten wir Ihnen die regelmäßige Reinigung für folgendes "
                 "Objekt an:</p>\n<p class=\"objekt\"><strong>Objekt:</strong> %s</p>\n"
                 % (esc(inhalt["titel"]), anrede,
                    _feld(inhalt.get("objekt"), "[Objekt / Anschrift des Objekts]", "Objekt ergänzen")))
    teile.append('<h3>Leistungsverzeichnis</h3>\n<table><thead><tr><th class="pos">Pos.</th><th>Bereich / Leistung'
                 '</th><th class="flaeche">Fläche</th><th class="turnus">Turnus</th></tr></thead><tbody>%s</tbody>'
                 "</table>\n" % "".join(zeilen))
    teile.append('<table><tbody><tr class="summe"><td>Monatliche Pauschale (netto)</td><td class="betrag">%s</td>'
                 '</tr><tr><td>entspricht im Jahr (netto)</td><td class="betrag">%s</td></tr></tbody></table>\n'
                 % (esc(euro(monat)), esc(euro(monat * 12))))
    teile.append('<p class="klein">%s</p>\n' % _feld(inhalt.get("preis_hinweis"),
                                                    "[Angabe zur Umsatzsteuer – vom Inhaber zu ergänzen]",
                                                    "Umsatzsteuer-Hinweis ergänzen"))
    teile.append('<p class="klein">%s</p>\n' % _feld(
        "", "[Preisanpassung bei Änderung von Tarif- oder Mindestlohn – Wortlaut vom Steuerberater oder Anwalt "
            "prüfen lassen]", "Preisanpassung regeln"))
    teile.append("<dl><dt>Vertragsbeginn</dt><dd>%s</dd><dt>Laufzeit</dt><dd>%s</dd><dt>Kündigungsfrist</dt>"
                 "<dd>%s</dd><dt>Angebot gültig bis</dt><dd>%s</dd></dl>\n"
                 % (_feld(inhalt.get("vertragsbeginn"), "[Datum – vom Inhaber festzulegen]", "Vertragsbeginn festlegen"),
                    _feld(inhalt.get("laufzeit"), "[Laufzeit – vom Inhaber festzulegen]", "Laufzeit festlegen"),
                    _feld(inhalt.get("kuendigungsfrist"), "[Kündigungsfrist – vom Inhaber festzulegen]",
                          "Kündigungsfrist festlegen"),
                    _feld(inhalt.get("gueltig_bis"), "[Datum – vom Inhaber festzulegen]", "Gültigkeit festlegen")))
    teile.append('<p class="klein">Leistungen außerhalb dieses Leistungsverzeichnisses nur nach gesonderter '
                 "Absprache.</p>\n")
    teile.append("<p>Bei Fragen sind wir gern für Sie da.</p>\n<p>Mit freundlichen Grüßen</p>\n"
                 '<p class="unterschrift">%s</p>\n' % _feld("", "[Name, Unterschrift]", "Unterschrift ergänzen"))
    teile.append("</main>\n</body>\n</html>\n")
    return "".join(teile)


# ---------------------------------------------------------------- Beispiel (committet)
BEISPIEL_DATEI = "angebot-dauerauftrag.html"
BEISPIEL_STUNDENSATZ = "35,00"   # Beispielwert – kein Vorschlag
BEISPIEL_KALKULATION = {
    "positionen": [
        {"bezeichnung": "Treppenhaus mit 3 Etagen (Beispiel)", "flaeche_m2": 180, "leistungswert_m2_h": 150,
         "reinigungen_pro_woche": 1},
        {"bezeichnung": "Eingangsbereich und Kellerflur (Beispiel)", "flaeche_m2": 60, "leistungswert_m2_h": 120,
         "reinigungen_pro_monat": 2},
        {"bezeichnung": "Glas der Eingangstür (Beispiel)", "flaeche_m2": 12, "leistungswert_m2_h": 30,
         "reinigungen_pro_monat": 1},
    ],
    "stundensatz": BEISPIEL_STUNDENSATZ, "material_prozent": 5, "anfahrten_pro_monat": 4, "anfahrt_minuten": 20,
    "zuschlag_prozent": 10,
}
BEISPIEL_HINWEIS = ("BEISPIEL – fiktive Musterfirma, erfundene Namen und Zahlen. Der Monatspreis stammt aus einer "
                    "Beispielrechnung mit dem Stundensatz 35,00 € – Beispielwert, kein Vorschlag. Euren Stundensatz "
                    "legt ihr selbst fest.")


def beispiel_dauerauftrag():
    """Beispiel-Angebot für die fiktive Musterfirma (deterministisch, für autonomous/beispiele)."""
    heute = datetime.date(2026, 11, 21)
    rechnung = kalk_modul.berechnen(kalk_modul.eingabe_pruefen(BEISPIEL_KALKULATION), 0, heute)
    kalk = kalk_modul.aus_aufgabe({"id": "a_beispiel", "typ": "kalkulation_reinigung", "status": "abgeschlossen",
                                   "ergebnis": rechnung})
    d = eingabe_pruefen({"art": "reinigung_dauerauftrag", "kalkulation_aufgabe_id": "a_beispiel",
                         "anbieter": "Musterfirma Reinigung (Beispiel)",
                         "anbieter_anschrift": "Musterstraße 1, 12345 Musterstadt",
                         "anbieter_kontakt": "Tel. 01234 567890 · kontakt@musterfirma.example",
                         "objekt": "Musterweg 5, 12345 Musterstadt (Beispiel)"}, kalk)
    inhalt = inhalt_bauen(d, "an_beispiel0bsp1", {"firma": "Muster-Hausverwaltung (Beispiel)",
                                                  "ansprechpartner": "Erika Mustermann", "ort": "Musterstadt"},
                          heute=heute.isoformat())
    inhalt["preis_quelle"] = "aus einer Beispielrechnung (Stundensatz 35,00 € – Beispielwert, kein Vorschlag)"
    inhalt["beispiel_hinweis"] = BEISPIEL_HINWEIS
    return erzeugen(inhalt, entwurf=True)


def beispiel_schreiben(ordner):
    """Schreibt das committete Beispiel (autonomous/beispiele/angebot-dauerauftrag.html)."""
    os.makedirs(ordner, exist_ok=True)
    pfad = os.path.join(ordner, BEISPIEL_DATEI)
    with open(pfad, "w", encoding="utf-8", newline="\n") as f:
        f.write(beispiel_dauerauftrag())
    return pfad
