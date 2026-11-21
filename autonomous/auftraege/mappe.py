# -*- coding: utf-8 -*-
"""Bewerbungs-Mappe zu einer Ausschreibung: druckbare Arbeitsunterlage (HTML ohne JavaScript).

Sie bereitet nur vor. Registrieren auf Vergabeplattformen, Unterlagen herunterladen und das Angebot
abgeben macht ausschließlich der Inhaber. Alle Fremdinhalte werden escaped.
"""

import html
import json

from . import QUELLEN_NAMEN, datum_deutsch, tage_bis
from ..wallet import euro

# Aus jarvis_core/wissenspakete/auftraege.md (Stand 09.11.2026) und kalkulation.md (Stand 09.11.2026)
QUELLEN = {
    "q1": ("Bundesamt für Justiz: Mindestlöhne in der Gebäudereinigung (TV Mindestlohn vom 15.11.2024, "
           "Verordnung vom 23.01.2025)", "https://www.gesetze-im-internet.de/tvmindestlohngeb_ude_2024/BJNR0160B0025.html"),
    "q2": ("Bergische IHK: Vergabemarktplatz NRW",
           "https://www.ihk.de/bergische/starthilfe/unternehmensfuehrung/oeffentliches-auftragswesen/"
           "vergabemarktplatz-nrw-1413908"),
    "q3": ("Universität Bielefeld: Hinweise zur Einreichung von Teilnahmeanträgen und Angeboten (UVgO)",
           "https://www.uni-bielefeld.de/verwaltung/dezernat-f/infos-dienstleister/"
           "UVgO-Formular_312_322-Hinweise_Einreichung_Teilnahmeantrage.pdf"),
    "q4": ("cosinex-Blog, 04.02.2025: Präqualifikation – alles, was Vergabestellen und Bieter wissen müssen",
           "https://blog.cosinex.de/2025/02/04/praequalifikation-alles-was-vergabestellen-und-bieter-wissen-muessen/"),
    "q5": ("Vergabeblog, 21.01.2026: EU-Schwellenwerte wurden zum 01.01.2026 angepasst",
           "https://vergabeblog.de/2026-01-21/eu-schwellenwerte-wurden-zum-01-01-2026-angepasst/"),
}

NACHWEISE = (
    "Gewerbeanmeldung oder Auszug aus dem Handelsregister",
    "Bescheinigung in Steuersachen vom Finanzamt",
    "Unbedenklichkeitsbescheinigung der Krankenkasse(n)",
    "Unbedenklichkeitsbescheinigung der Berufsgenossenschaft",
    "Nachweis der Betriebshaftpflichtversicherung",
    "Referenzen über vergleichbare Aufträge (Objekt, Umfang, Zeitraum, Ansprechpartner – nur mit deren Zustimmung)",
    "Eigenerklärungen laut Formularen der Vergabestelle (z. B. zu Ausschlussgründen)",
    "Falls vorhanden: Eintrag in einem Präqualifikations-Verzeichnis (AVPQ für Liefer- und Dienstleistungen, "
    "PQ-VOB für Bauleistungen) – erspart viele Einzelnachweise",
)

CSS = (
    "*{box-sizing:border-box}html{-webkit-text-size-adjust:100%}"
    "body{margin:0;font-family:system-ui,-apple-system,'Segoe UI',Roboto,Arial,sans-serif;font-size:16px;"
    "line-height:1.55;color:#111827;background:#f3f4f6;overflow-wrap:break-word}"
    ".blatt{max-width:860px;margin:0 auto;background:#fff;padding:28px 22px 40px}"
    "h1{font-size:1.55rem;line-height:1.25;margin:.2em 0 .4em}h2{font-size:1.15rem;margin:1.8em 0 .6em;"
    "padding-bottom:.25em;border-bottom:2px solid #e5e7eb}"
    ".hinweis{background:#fef3c7;border:1px solid #f59e0b;color:#78350f;border-radius:10px;padding:12px 14px;"
    "font-weight:600}"
    ".frist{display:inline-block;margin:.4em 0;padding:6px 12px;border-radius:999px;font-weight:700;"
    "background:#e0f2fe;color:#075985}.frist.knapp{background:#fee2e2;color:#991b1b}"
    "table{width:100%;border-collapse:collapse;table-layout:fixed}"
    "th,td{text-align:left;vertical-align:top;padding:8px 6px;border-bottom:1px solid #e5e7eb}"
    "th{width:34%;color:#374151;font-weight:600}td{overflow-wrap:anywhere}"
    "a{color:#0e7490;overflow-wrap:anywhere}"
    "ol,ul{padding-left:1.3em}li{margin:.35em 0}"
    ".check{list-style:none;padding-left:0}.check li{padding-left:1.8em;text-indent:-1.8em}"
    ".check li::before{content:'\\2610';display:inline-block;width:1.8em;text-indent:0;font-size:1.1em}"
    ".offen{background:#fffbeb;border:2px dashed #d97706;border-radius:10px;padding:10px 12px}"
    ".klein{font-size:.9rem;color:#4b5563}.quellen li{font-size:.9rem}"
    "@media (max-width:520px){th,td{display:block;width:100%;padding:4px 0}th{border-bottom:none;padding-top:10px}}"
    "@media print{body{background:#fff}.blatt{padding:0}a{color:#000}}"
)


def _e(t):
    return html.escape(str(t if t is not None else ""), quote=True)


def _q(*schluessel):
    return "".join('<sup>[%s]</sup>' % s[1:] for s in schluessel)


def erzeugen(a, einstellungen, erstellt_am):
    """a: Zeile aus der Tabelle ausschreibungen. erstellt_am: ISO-Zeitstempel."""
    tage = tage_bis(a.get("frist"))
    begruendung = a.get("begruendung") or "[]"
    if isinstance(begruendung, str):
        try:
            begruendung = json.loads(begruendung)
        except ValueError:
            begruendung = []
    if tage is None:
        frist_text, knapp = "Frist nicht angegeben – in den Vergabeunterlagen nachsehen", False
    elif tage < 0:
        frist_text, knapp = "Frist am %s abgelaufen" % datum_deutsch(a["frist"]), True
    else:
        frist_text, knapp = "Frist: %s – noch %d Tag(e) (Stand %s)" % (
            datum_deutsch(a["frist"]), tage, datum_deutsch(erstellt_am[:10])), tage < 7
    satz = einstellungen.get("stundensatz_cent") or 0
    stundensatz = ("<strong>%s</strong> pro Stunde (aus den Einstellungen)" % _e(euro(satz))) if satz > 0 else \
        '<span class="offen"><strong>OFFEN – bitte in den Einstellungen festlegen.</strong> Ohne festen Stundensatz ' \
        'kein Angebotspreis.</span>'
    zeilen = [
        ("Titel", _e(a.get("titel"))),
        ("Vergabestelle", _e(a.get("vergabestelle") or "nicht angegeben")),
        ("Ort / Region", _e(" · ".join(x for x in (a.get("plz"), a.get("ort"), a.get("region")) if x)
                            or "nicht angegeben – in den Unterlagen prüfen")),
        ("Verfahren", _e(a.get("verfahren") or "nicht angegeben")),
        ("Quelle", _e(QUELLEN_NAMEN.get(a.get("quelle"), a.get("quelle")))),
        ("Original-Bekanntmachung", '<a href="%s" rel="noopener noreferrer">%s</a>' % (_e(a.get("link")),
                                                                                   _e(a.get("link")))),
        ("Veröffentlicht", _e(datum_deutsch(a.get("veroeffentlicht")) if a.get("veroeffentlicht")
                              else "nicht angegeben")),
        ("Bewertung", "%d von 100 Punkten" % int(a.get("punkte") or 0)),
    ]
    tabelle = "".join("<tr><th>%s</th><td>%s</td></tr>" % z for z in zeilen)
    gruende = "".join("<li>%s</li>" % _e(g) for g in begruendung[:12])
    nachweise = "".join("<li>%s</li>" % _e(n) for n in NACHWEISE)
    quellen = "".join('<li>[%s] %s – <a href="%s" rel="noopener noreferrer">%s</a></li>' % (
        k[1:], _e(t), _e(u), _e(u)) for k, (t, u) in QUELLEN.items())
    return """<!doctype html>
<html lang="de"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex">
<title>Bewerbungs-Mappe: %(titel_kurz)s</title>
<style>%(css)s</style></head>
<body><main class="blatt">
<p class="hinweis">Arbeitsunterlage zur Vorbereitung – es wurde NICHTS abgegeben und nichts angemeldet.
Registrierung, Download der Vergabeunterlagen und die Abgabe des Angebots macht nur der Inhaber.</p>
<h1>Bewerbungs-Mappe</h1>
<p><strong>%(titel)s</strong></p>
<p class="frist%(knapp)s">%(frist)s</p>

<h2>Eckdaten</h2>
<table>%(tabelle)s</table>
<p class="klein">Warum diese Ausschreibung vorgeschlagen wurde (automatische Bewertung, keine Garantie):</p>
<ul class="klein">%(gruende)s</ul>

<h2>Nächste Schritte</h2>
<ol>
<li>Original-Bekanntmachung öffnen (Link oben) und die <strong>Vergabeunterlagen</strong> herunterladen. Dafür ist
auf der Vergabeplattform meist eine kostenlose Registrierung nötig%(q23)s – die nimmt der Inhaber selbst vor.</li>
<li>Unterlagen lesen: Leistungsbeschreibung (Flächen, Turnus, Objekte), Eignungskriterien, Zuschlagskriterien,
Fristen für Bieterfragen und für das Angebot.</li>
<li>Falls angeboten oder gefordert: Ortsbesichtigung vereinbaren.</li>
<li>Kalkulieren (Flächen, Leistungswerte, Turnus, Anfahrt, Material) – siehe unten.</li>
<li>Nachweise zusammenstellen – Checkliste unten.</li>
<li>Angebot <strong>fristgerecht elektronisch</strong> über die Vergabeplattform abgeben%(q3)s –
<strong>nur durch den Inhaber</strong>. AUTONOMOUS gibt nie selbst ein Angebot ab.</li>
</ol>

<h2>Typische Nachweise (Checkliste)</h2>
<p class="hinweis">Typisch – verbindlich sind nur die Vergabeunterlagen der Ausschreibung. Die Liste ist eine
Einschätzung aus unserem Wissenspaket „Öffentliche Aufträge in NRW“ (Stand 09.11.2026)%(q4)s.</p>
<ul class="check">%(nachweise)s</ul>

<h2>Kalkulation – Grundlage</h2>
<p>Unser Stundensatz: %(stundensatz)s</p>
<p>Untergrenze für jeden Preis sind die Löhne: Mindestlohn in der Gebäudereinigung 2026 –
Lohngruppe 1 (Innen- und Unterhaltsreinigung) <strong>15,00 €</strong> pro Stunde, Lohngruppe 6 (Glas- und
Fassadenreinigung) <strong>18,40 €</strong> pro Stunde%(q1)s. <strong>Stand 2026: Die Verordnung läuft am 01.01.2027
aus – vor der Angebotsabgabe neu prüfen.</strong> Ein Stundensatz muss zusätzlich Lohnnebenkosten, Ausfallzeiten,
Material, Fahrten, Verwaltung und Gewinn decken.</p>
<p class="klein">EU-weite Verfahren gibt es ab einem geschätzten Auftragswert von 216.000 € netto für Liefer- und
Dienstleistungen (Städte, Länder; 140.000 € bei obersten und oberen Bundesbehörden), Stand 2026/2027%(q5)s. Der Wert
dieser Ausschreibung ist hier nicht bekannt – er steht, falls angegeben, in den Unterlagen.</p>

<h2>Quellen</h2>
<ul class="quellen">%(quellen)s</ul>
<p class="klein">Erstellt von AUTONOMOUS (Akquise-Agent) am %(erstellt)s. Allgemeine Hinweise ohne Gewähr –
keine Rechtsberatung.</p>
</main></body></html>
""" % {"titel_kurz": _e((a.get("titel") or "")[:80]), "css": CSS, "titel": _e(a.get("titel")),
       "knapp": " knapp" if knapp else "", "frist": _e(frist_text), "tabelle": tabelle,
       "gruende": gruende or "<li>keine Angaben</li>", "nachweise": nachweise, "stundensatz": stundensatz,
       "q1": _q("q1"), "q23": _q("q2", "q3"), "q3": _q("q3"), "q4": _q("q4"), "q5": _q("q5"),
       "quellen": quellen, "erstellt": _e(datum_deutsch(erstellt_am[:10]))}
