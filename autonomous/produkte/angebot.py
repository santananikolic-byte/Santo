# -*- coding: utf-8 -*-
"""Angebot als druckbare HTML-Datei (Sales-Agent).

- Der Betrag kommt immer vom Inhaber – nie geschätzt oder vorgeschlagen.
- Fehlende Angaben (Anbieter, Anschrift, Umsatzsteuer, Gültigkeit, Lieferzeit) erscheinen als gelb
  markierte Felder. Sie lassen sich im Browser anklicken und ausfüllen (contenteditable, ohne
  JavaScript); danach „Drucken → Als PDF sichern“. Änderungen im Browser werden nicht gespeichert.
- Solange das Angebot im Status „entwurf“ ist, steht groß „ENTWURF – vor Versand prüfen“ darauf.
"""

import datetime

from . import bereinigen, datum_deutsch, esc, liste_bereinigen
from ..wallet import betrag_in_cent, euro

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


def eingabe_pruefen(eingabe):
    if not isinstance(eingabe, dict):
        raise ValueError("Eingabe muss ein Objekt sein.")
    if eingabe.get("betrag") in (None, ""):
        raise ValueError("Pflichtfeld fehlt: betrag (den Preis legt der Inhaber fest).")
    return {
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


def inhalt_bauen(d, angebot_id, kontakt=None, produkt=None, heute=None):
    """Alle Angaben, aus denen die Datei entsteht (wird in angebote.inhalt gespeichert)."""
    heute = heute or datetime.date.today().isoformat()
    position = STANDARD_POSITION
    titel = d["titel"] or STANDARD_TITEL
    if produkt:
        position = bereinigen(produkt.get("name"), 120) or position
        if not d["titel"]:
            titel = "Angebot: %s" % position
    return {
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
