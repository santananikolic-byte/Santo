# -*- coding: utf-8 -*-
"""Generator für das empfohlene erste Angebot: das „Google-Profil-Paket“.

Das Paket besteht aus drei druckbaren, mobil lesbaren Arbeitsunterlagen (je eine HTML-Datei
ohne JavaScript und ohne externe Ressourcen):

- ``profil-entwurf.html``      – Ausfüllvorlage für das Google-Unternehmensprofil
- ``pruefliste.html``          – Profil-Check zum Abhaken beim Termin vor Ort
- ``uebergabe-anleitung.html`` – Kurzanleitung für den Kunden

Ehrlichkeitsregeln:
- Deterministisch aus den Eingaben, kein Modell. Nichts wird hinzuerfunden (keine Bewertungen,
  Kundenzahlen, Jahre oder Zertifikate). Was fehlt, bleibt als gelber Platzhalter sichtbar.
- Kategorien sind nur Suchbegriff-VORSCHLÄGE – die Auswahlliste gibt Google vor.
- AUTONOMOUS trägt nichts bei Google ein und hat keinen Zugang zu Google. Das Eintragen geschieht
  beim Termin vor Ort durch bzw. mit dem Inhaber.
- Keine Zusagen zu Dauer der Bestätigung oder zur Platzierung bei Google.
"""

import datetime
import re

from . import bereinigen, email_pruefen, esc, esc_zeilen, liste_bereinigen, telefon_pruefen
from .qualitaet import BESCHREIBUNG_MAX, enthaelt_link, enthaelt_telefon
from .webseite import BEISPIEL_HINWEIS, thema_fuer

ANGEBOT_NAME = "Google-Profil-Paket für kleine Handwerks-, Bau- und Reinigungsbetriebe in NRW"

# Logische Rollen der drei Unterlagen → Dateinamen
DATEIEN = {"entwurf": "profil-entwurf.html", "pruefliste": "pruefliste.html",
           "uebergabe": "uebergabe-anleitung.html"}
# Beispiel-Unterlagen neben einer Verkaufsseite im Produktordner
BEISPIEL_IM_PRODUKT = {"entwurf": "beispiel.html", "pruefliste": "beispiel-pruefliste.html",
                       "uebergabe": "beispiel-uebergabe.html"}
# Committete Beispiele in autonomous/beispiele
BEISPIEL_COMMITTET = {"entwurf": "google-profil-entwurf.html", "pruefliste": "google-profil-pruefliste.html",
                      "uebergabe": "google-profil-uebergabe.html"}
ROLLEN = ("entwurf", "pruefliste", "uebergabe")

FELDER = ("firma", "branche", "ort", "leistungen", "telefon", "email", "webseite", "adresse", "einzugsgebiet",
          "oeffnungszeiten", "gruendungsjahr", "besonderheiten", "anbieter", "anbieter_kontakt")
LAENGEN = {"firma": 80, "branche": 60, "ort": 60, "webseite": 200, "adresse": 200, "einzugsgebiet": 200,
           "oeffnungszeiten": 200, "besonderheiten": 400, "anbieter": 80, "anbieter_kontakt": 120}
MAX_LEISTUNGEN = 20

# Erkennbar fiktive Musterfirma (gleiche Firma wie im Webseiten-Beispiel; „.example“ ist eine
# reservierte, nie vergebene Endung, die Telefonnummer ist eine Beispielnummer)
BEISPIEL_DATEN = {
    "firma": "Musterfirma Reinigung (Beispiel)",
    "branche": "Gebäudereinigung",
    "ort": "Musterstadt",
    "leistungen": ["Unterhaltsreinigung für Büros und Praxen", "Treppenhausreinigung", "Glas- und Fensterreinigung",
                   "Grundreinigung nach Umbau oder Auszug", "Baureinigung"],
    "telefon": "01234 567890",
    "email": "kontakt@musterfirma.example",
    "webseite": "www.musterfirma.example",
    "einzugsgebiet": "Musterstadt und Umgebung (bis etwa 30 km)",
    "oeffnungszeiten": "Mo–Fr 7–18 Uhr\nSa nach Vereinbarung",
    "besonderheiten": "Reinigung auch am frühen Morgen oder am Abend möglich.",
}

# Suchbegriffe für die Kategorieauswahl – ausdrücklich nur Vorschläge, keine Kategorienamen
SUCHBEGRIFFE = {
    "reinigung": ["Gebäudereinigung", "Reinigungsdienst", "Fensterreinigung", "Hausmeisterservice"],
    "bau": ["Bauunternehmen", "Bauunternehmer", "Sanierung", "Renovierung"],
    "handwerk": ["Handwerker", "Renovierung"],
}

_WEBSEITE = re.compile(r"^(?:https?://)?(?:www\.)?[A-Za-z0-9](?:[A-Za-z0-9\-]*[A-Za-z0-9])?"
                       r"(?:\.[A-Za-z0-9](?:[A-Za-z0-9\-]*[A-Za-z0-9])?)*\.[A-Za-z]{2,24}(?:/[^\s<>\"'`]*)?$")


# ---------------------------------------------------------------- Eingaben
def _ohne_link_und_telefon(feld, text):
    """Felder, die in die Beschreibung fließen, dürfen keine Links oder Telefonnummern enthalten."""
    if enthaelt_link(text) or enthaelt_telefon(text):
        raise ValueError("Bitte keine Links oder Telefonnummern in '%s' – dafür gibt es eigene Felder "
                         "(telefon, webseite)." % feld)


def eingabe_pruefen(eingabe):
    """Prüft und säubert die Eingaben. Wirft ValueError mit verständlicher Meldung."""
    if not isinstance(eingabe, dict):
        raise ValueError("Eingabe muss ein Objekt sein.")
    d = {}
    for feld in ("firma", "branche", "ort"):
        d[feld] = bereinigen(eingabe.get(feld), LAENGEN[feld], streng=True, name=feld)
        if not d[feld]:
            raise ValueError("Pflichtfeld fehlt: %s" % feld)
    d["leistungen"] = liste_bereinigen(eingabe.get("leistungen"), 80, MAX_LEISTUNGEN, name="Leistung")
    if not d["leistungen"]:
        raise ValueError("Pflichtfeld fehlt: leistungen (mindestens eine Leistung)")
    d["telefon"], d["telefon_link"] = telefon_pruefen(eingabe.get("telefon"))
    d["email"] = email_pruefen(eingabe.get("email"))
    webseite = bereinigen(eingabe.get("webseite"), LAENGEN["webseite"], streng=True, name="webseite")
    if webseite and not _WEBSEITE.fullmatch(webseite):
        raise ValueError("Webseite ungültig (Beispiel: www.firma.de).")
    d["webseite"] = webseite
    for feld in ("adresse", "einzugsgebiet", "anbieter", "anbieter_kontakt"):
        d[feld] = bereinigen(eingabe.get(feld), LAENGEN[feld], streng=True, name=feld)
    zeiten = eingabe.get("oeffnungszeiten")
    if isinstance(zeiten, str):
        zeiten = zeiten.replace(";", "\n")
    d["oeffnungszeiten"] = bereinigen(zeiten, LAENGEN["oeffnungszeiten"], mehrzeilig=True, streng=True,
                                      name="oeffnungszeiten")
    d["besonderheiten"] = bereinigen(eingabe.get("besonderheiten"), LAENGEN["besonderheiten"], streng=True,
                                     name="besonderheiten")
    jahr = eingabe.get("gruendungsjahr")
    if jahr in (None, ""):
        d["gruendungsjahr"] = ""
    else:
        if isinstance(jahr, bool) or not re.fullmatch(r"\d{4}", str(jahr).strip()):
            raise ValueError("Gründungsjahr bitte vierstellig angeben (z. B. 1998) oder leer lassen.")
        if not 1800 <= int(str(jahr).strip()) <= datetime.date.today().year:
            raise ValueError("Gründungsjahr liegt außerhalb des möglichen Bereichs.")
        d["gruendungsjahr"] = str(jahr).strip()
    for feld in ("firma", "branche", "ort", "einzugsgebiet", "besonderheiten"):
        _ohne_link_und_telefon(feld, d[feld])
    for leistung in d["leistungen"]:
        _ohne_link_und_telefon("leistungen", leistung)
    return d


# ---------------------------------------------------------------- Beschreibung
def _satz(text):
    text = text.strip().rstrip(",;:–- ")
    return text if text.endswith((".", "!", "?", "…")) else text + "."


def beschreibung_bauen(d):
    """Sachlicher Beschreibungsentwurf aus den Eingaben, höchstens 750 Zeichen.

    Rückgabe (text, gekuerzt). Passen nicht alle Leistungen hinein, werden die ersten genannt und
    „und weitere“ angehängt; reicht das nicht, wird am Wortende mit „…“ gekürzt."""
    kopf = "%s – %s aus %s." % (d["firma"], d["branche"], d["ort"])
    rest = []
    if d["einzugsgebiet"]:
        rest.append("Einsatzgebiet: %s" % _satz(d["einzugsgebiet"]))
    if d["gruendungsjahr"]:
        rest.append("Gegründet %s." % d["gruendungsjahr"])
    if d["besonderheiten"]:
        rest.append(_satz(d["besonderheiten"]))
    wege = [w for w, da in (("telefonisch", d["telefon"]), ("per E-Mail", d["email"])) if da]
    if wege:
        rest.append("Anfragen gern %s." % " oder ".join(wege))

    def mit(anzahl):
        teile = [kopf]
        if anzahl:
            liste = ", ".join(d["leistungen"][:anzahl])
            teile.append("Leistungen: %s%s" % (liste, " und weitere." if anzahl < len(d["leistungen"]) else "."))
        return " ".join(teile + rest)

    anzahl = len(d["leistungen"])
    text = mit(anzahl)
    gekuerzt = False
    while len(text) > BESCHREIBUNG_MAX and anzahl > 1:
        anzahl -= 1
        gekuerzt = True
        text = mit(anzahl)
    if len(text) > BESCHREIBUNG_MAX:
        text = text[:BESCHREIBUNG_MAX - 1].rsplit(" ", 1)[0].rstrip(",;:–- ") + "…"
        gekuerzt = True
    return text, gekuerzt


def suchbegriffe(d):
    begriffe, gesehen = [], set()
    for b in [d["branche"]] + SUCHBEGRIFFE[thema_fuer(d["branche"])] + d["leistungen"][:3]:
        if b.lower() not in gesehen:
            gesehen.add(b.lower())
            begriffe.append(b)
    return begriffe[:8]


# ---------------------------------------------------------------- Gestaltung
CSS = (
    ":root{--dunkel:#0f172a;--primaer:#0e7490;--rand:#e2e8f0;--leise:#475569;--text:#1f2937;"
    "--gelb:#fffbeb;--gelbrand:#d97706;--gelbtext:#78350f}"
    "*{box-sizing:border-box}html{-webkit-text-size-adjust:100%}"
    "body{margin:0;font-family:system-ui,-apple-system,'Segoe UI',Roboto,'Helvetica Neue',Arial,sans-serif;"
    "font-size:17px;line-height:1.55;color:var(--text);background:#f1f5f9;overflow-wrap:break-word}"
    ".blatt{max-width:860px;margin:0 auto;padding:16px 16px 40px}"
    ".entwurf{background:#fef3c7;color:#78350f;border-bottom:1px solid #fcd34d;padding:8px 16px;"
    "text-align:center;font-size:.9rem;font-weight:600}"
    ".dok-nav{display:flex;flex-wrap:wrap;gap:8px;margin:8px 0 16px}"
    ".dok-nav a{display:inline-flex;align-items:center;min-height:44px;padding:8px 14px;border:1px solid var(--rand);"
    "border-radius:10px;background:#fff;color:var(--dunkel);text-decoration:none;font-weight:600}"
    ".dok-nav a[aria-current=page]{background:var(--primaer);border-color:var(--primaer);color:#fff}"
    "a:focus-visible{outline:3px solid var(--primaer);outline-offset:3px}"
    "h1{font-size:clamp(1.5rem,5vw,2.1rem);line-height:1.2;margin:.3em 0 .25em;color:var(--dunkel)}"
    ".unter{color:var(--leise);margin:0 0 1.1em;font-weight:600}"
    "section{background:#fff;border:1px solid var(--rand);border-radius:14px;padding:16px 18px 6px;margin:0 0 14px}"
    "h2{font-size:1.15rem;line-height:1.3;margin:0 0 .6em;color:var(--dunkel)}"
    "p{margin:0 0 .8em}dl{margin:0 0 .8em}"
    ".feld{display:grid;grid-template-columns:minmax(0,11em) minmax(0,1fr);gap:4px 16px;padding:8px 0;"
    "border-top:1px solid var(--rand)}.feld:first-child{border-top:0}"
    ".feld dt{font-weight:700}.feld dd{margin:0;min-width:0}"
    ".klaeren{background:var(--gelb);border:2px dashed var(--gelbrand);border-radius:10px;padding:8px 12px;"
    "color:var(--gelbtext)}"
    ".hinweis{color:var(--leise);font-size:.95rem}"
    ".beschreibung{background:#f8fafc;border:1px solid var(--rand);border-radius:10px;padding:12px 14px;"
    "margin:0 0 .5em}"
    ".zaehler{font-size:.9rem;color:var(--leise);font-weight:600}"
    ".tags{display:flex;flex-wrap:wrap;gap:8px;list-style:none;padding:0;margin:0 0 .8em}"
    ".tags li{border:1px solid var(--rand);border-radius:999px;padding:4px 12px;background:#f8fafc;min-width:0}"
    ".punkte{margin:0 0 .8em;padding-left:1.3em}.punkte li{margin:0 0 .25em}"
    ".haken{list-style:none;margin:0 0 .8em;padding:0;display:grid;gap:10px}"
    ".haken li{display:flex;gap:10px;align-items:flex-start}.haken li>span:last-child{min-width:0}"
    ".kasten{flex:none;width:22px;height:22px;border:2px solid var(--dunkel);border-radius:5px;margin-top:2px;"
    "background:#fff}"
    ".bereich-klaeren{background:var(--gelb);border-color:var(--gelbrand)}"
    ".linie{display:inline-block;min-width:12em;border-bottom:1px solid var(--gelbtext)}"
    "footer{color:var(--leise);font-size:.9rem;margin-top:18px}"
    "@media (max-width:560px){.feld{grid-template-columns:minmax(0,1fr)}.blatt{padding:12px 12px 32px}}"
    "@media print{body{background:#fff;font-size:12pt}.dok-nav,.nur-bildschirm{display:none}"
    "section{break-inside:avoid;border-color:#94a3b8}.klaeren{border-color:#000;color:#000}"
    ".entwurf{border:1px solid #000}}"
)


class _Dokument:
    """Kleine Hilfe, damit jede Unterlage gleich aufgebaut ist und alles escaped wird."""

    def __init__(self, markieren):
        self.markieren = markieren

    def offen(self, text, offen, element="p", klasse="klaeren"):
        """Gelber Platzhalter. ``offen`` wird als offener Punkt gemeldet (nur wenn markieren=True)."""
        attr = ' data-offen="%s"' % esc(offen) if (offen and self.markieren) else ""
        return '<%s class="%s"%s>%s</%s>' % (element, klasse, attr, text, element)

    @staticmethod
    def felder(paare):
        """paare: [(Bezeichnung, fertiges HTML, id oder None)]"""
        zeilen = []
        for titel, inhalt, ident in paare:
            attr = ' id="%s"' % ident if ident else ""
            zeilen.append('<div class="feld"><dt>%s</dt><dd%s>%s</dd></div>' % (esc(titel), attr, inhalt))
        return "<dl>%s</dl>" % "".join(zeilen)

    @staticmethod
    def haken(eintraege):
        return '<ul class="haken">%s</ul>' % "".join(
            '<li><span class="kasten" aria-hidden="true"></span><span>%s</span></li>' % e for e in eintraege)


def _nav(namen, aktiv):
    titel = {"entwurf": "Profil-Entwurf", "pruefliste": "Prüfliste", "uebergabe": "Übergabe-Anleitung"}
    links = "".join('<a href="%s"%s>%s</a>' % (esc(namen[r]), ' aria-current="page"' if r == aktiv else "",
                                               titel[r]) for r in ROLLEN)
    return '<nav class="dok-nav" aria-label="Unterlagen des Google-Profil-Pakets">%s</nav>' % links


def _seite(titel, h1, unter, banner, nav, abschnitte, fuss):
    return ("<!DOCTYPE html>\n<!-- Erstellt mit AUTONOMOUS (Product-Agent): ohne JavaScript, ohne externe Dienste. -->\n"
            '<html lang="de">\n<head>\n<meta charset="utf-8">\n'
            '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
            "<title>%s</title>\n<style>%s</style>\n</head>\n<body>\n%s"
            '<div class="blatt">\n%s\n<header><h1>%s</h1><p class="unter">%s</p></header>\n<main>\n%s</main>\n'
            "<footer>%s</footer>\n</div>\n</body>\n</html>\n"
            % (titel, CSS, banner, nav, h1, unter, "".join(abschnitte), fuss))


def _abschnitt(titel, inhalt, klasse=None):
    attr = ' class="%s"' % klasse if klasse else ""
    return "<section%s><h2>%s</h2>%s</section>\n" % (attr, esc(titel), inhalt)


def _banner(text, offen=None, markieren=True):
    if not text:
        return ""
    attr = ' data-offen="%s"' % esc(offen) if (offen and markieren) else ""
    return '<div class="entwurf" role="note"%s>%s</div>\n' % (attr, esc(text))


# ---------------------------------------------------------------- Die drei Unterlagen
def _entwurf(d, namen, beispiel):
    dok = _Dokument(markieren=not beispiel)
    firma = esc(d["firma"])
    text, gekuerzt = beschreibung_bauen(d)
    abschnitte = []

    abschnitte.append(_abschnitt("Unternehmensname", dok.felder([("Name im Profil", firma, "firmenname")]) +
                                 '<p class="hinweis">Genau so, wie der Betrieb im Geschäftsleben heißt (Schild, '
                                 'Briefkopf, Handelsregister). Keine Orte, Leistungen oder Werbung anhängen – das '
                                 'widerspricht den Google-Richtlinien.</p>'))

    tags = "".join("<li>%s</li>" % esc(b) for b in suchbegriffe(d))
    abschnitte.append(_abschnitt("Kategorie (Vorschlag)", dok.offen(
        "<strong>VORSCHLAG – bitte in der Google-Auswahlliste prüfen.</strong> Google gibt die Kategorien vor; die "
        "genaue Bezeichnung kann abweichen. Diese Suchbegriffe helfen beim Finden:",
        "Hauptkategorie in der Google-Auswahlliste auswählen (vor Ort)") +
        '<ul class="tags">%s</ul><p class="hinweis">Eine Hauptkategorie wählen, die den Kern des Betriebs trifft. '
        'Weitere Kategorien nur, wenn der Betrieb diese Leistungen wirklich anbietet.</p>' % tags))

    beschreibung = ('<div id="beschreibung-text" class="beschreibung">%s</div>'
                    '<p class="zaehler">%d von höchstens %d Zeichen</p>' % (esc(text), len(text), BESCHREIBUNG_MAX))
    if gekuerzt:
        beschreibung += dok.offen("Gekürzt: Nicht alle Leistungen passen in %d Zeichen. Vor Ort gemeinsam "
                                  "auswählen, welche genannt werden." % BESCHREIBUNG_MAX,
                                  "Beschreibung wurde gekürzt – Auswahl der Leistungen vor Ort klären")
    beschreibung += ('<p class="hinweis">Sachlich und ehrlich: keine Links, keine Telefonnummern, keine Preise oder '
                     'Sonderangebote (dafür gibt es eigene Felder). Vor Ort mit dem Inhaber durchlesen und '
                     'anpassen.</p>')
    abschnitte.append(_abschnitt("Beschreibung (Entwurf)", beschreibung))

    abschnitte.append(_abschnitt("Leistungen", '<ul class="punkte">%s</ul><p class="hinweis">Im Profil als '
                                 'Leistungen eintragen, soweit Google das für die gewählte Kategorie anbietet.</p>'
                                 % "".join("<li>%s</li>" % esc(l) for l in d["leistungen"])))

    gebiet = []
    if d["adresse"]:
        gebiet.append(("Adresse", esc(d["adresse"]), None))
    if d["einzugsgebiet"]:
        gebiet.append(("Servicegebiet", esc(d["einzugsgebiet"]), None))
    inhalt = dok.felder(gebiet) if gebiet else dok.offen("Adresse oder Servicegebiet: vor Ort klären.",
                                                         "Adresse oder Servicegebiet klären (vor Ort)")
    inhalt += ('<p class="hinweis">Faustregel: Kommen Kunden zum Betrieb, wird die Adresse angezeigt. Fährt der Betrieb '
               'zu den Kunden, wird ein Servicegebiet angegeben und eine Wohnadresse nicht öffentlich angezeigt. '
               'Vor Ort klären.</p>')
    abschnitte.append(_abschnitt("Standort und Einsatzgebiet", inhalt))

    if d["oeffnungszeiten"]:
        zeiten = dok.felder([("Öffnungszeiten", esc_zeilen(d["oeffnungszeiten"]), None)])
    else:
        zeiten = dok.offen("Öffnungszeiten: offen – vom Inhaber festzulegen.", "Öffnungszeiten festlegen (Inhaber)")
    abschnitte.append(_abschnitt("Öffnungszeiten", zeiten + '<p class="hinweis">An Feiertage und Betriebsurlaub '
                                                            'denken.</p>'))

    kontakt = [("Telefon", esc(d["telefon"]) if d["telefon"] else "nicht angegeben", None),
               ("E-Mail", esc(d["email"]) if d["email"] else "nicht angegeben", None),
               ("Webseite", esc(d["webseite"]) if d["webseite"] else "keine angegeben", None)]
    inhalt = dok.felder(kontakt)
    if not (d["telefon"] or d["email"]):
        inhalt += dok.offen("Kein Kontaktweg angegeben – Telefon oder E-Mail vor Ort klären.",
                            "Kontaktweg klären (Telefon oder E-Mail)")
    abschnitte.append(_abschnitt("Kontaktwege", inhalt))

    weitere = [("Gründungsjahr", esc(d["gruendungsjahr"]) if d["gruendungsjahr"] else
                "nicht angegeben – nur eintragen, wenn sicher bekannt", None)]
    if d["besonderheiten"]:
        weitere.append(("Besonderheiten", esc(d["besonderheiten"]), None))
    abschnitte.append(_abschnitt("Weitere Angaben", dok.felder(weitere)))

    abschnitte.append(_abschnitt("Fotos beim Termin vor Ort", dok.haken([
        "Außenansicht, Firmenschild oder Eingang (falls vorhanden)",
        "Team bei der Arbeit – nur mit Einwilligung jeder abgebildeten Person",
        "Firmenfahrzeuge",
        "Arbeitsbeispiele, auch vorher und nachher – nur mit Einverständnis der Kunden",
        "Werkzeug, Maschinen und Ausstattung",
    ]) + '<p class="hinweis">Nur echte, eigene Fotos. Keine Personen ohne Einwilligung. Keine Kundenadressen, '
         'Hausnummern, Klingelschilder oder Kfz-Kennzeichen von Kunden erkennbar.</p>'))

    klaeren = ["Gibt es schon ein Profil (auch doppelt oder unter altem Namen)?",
               "Wer hat heute Zugriff? Der Betrieb bleibt Inhaber; wir werden nur als Verwalter eingetragen.",
               "Hauptkategorie gemeinsam in der Google-Auswahlliste auswählen.",
               "Bestätigung durch Google: Verfahren und Dauer bestimmt Google – keine Zusage an den Kunden.",
               "Einwilligungen für Fotos mit Personen einholen."]
    if not d["oeffnungszeiten"]:
        klaeren.append("Öffnungszeiten festlegen.")
    if not (d["telefon"] or d["email"]):
        klaeren.append("Telefon oder E-Mail für Kundenanfragen festlegen.")
    if not (d["adresse"] or d["einzugsgebiet"]):
        klaeren.append("Adresse oder Servicegebiet festlegen.")
    abschnitte.append(_abschnitt("Vor Ort zu klären", dok.haken(esc(k) for k in klaeren), "bereich-klaeren"))

    if beispiel:
        banner = _banner(BEISPIEL_HINWEIS)
    else:
        banner = _banner("ARBEITSUNTERLAGE – Entwurf der Profilangaben. Vor Ort mit dem Inhaber prüfen; nicht "
                         "ungeprüft bei Google eintragen.")
    fuss = ("Erstellt mit AUTONOMOUS aus den eingegebenen Angaben. Nichts davon ist bei Google eingetragen – das "
            "geschieht beim Termin vor Ort durch den Inhaber oder mit seiner Zustimmung.")
    return _seite("Google-Profil – Entwurf: %s" % firma, "Google-Profil: Entwurf der Angaben",
                  "%s · %s · %s" % (firma, esc(d["branche"]), esc(d["ort"])), banner, _nav(namen, "entwurf"),
                  abschnitte, fuss)


def _pruefliste(d, namen, beispiel):
    dok = _Dokument(markieren=not beispiel)
    firma = esc(d["firma"])
    abschnitte = [
        _abschnitt("Vor dem Termin", dok.haken([
            "Bei Google und in Google Maps nach dem Firmennamen und dem Ort suchen: Gibt es schon ein Profil?",
            "Auch nach altem Namen, früherer Adresse und Telefonnummer suchen (doppelte Profile).",
            "Klären, wer heute Zugriff auf ein vorhandenes Profil hat.",
            "Einwilligungen für Fotos mit Personen vorbereiten.",
        ])),
        _abschnitt("Zugriff – der Betrieb bleibt Inhaber", dok.haken([
            "Wir nehmen keine Passwörter an. Der Inhaber meldet sich selbst an.",
            "Der Inhaber lädt uns als Verwalter ein – nicht als Inhaber.",
            "Neues Profil: Der Inhaber legt es mit seinem eigenen Google-Konto an.",
            "Bestätigung (Verifizierung) durch Google anstoßen. Verfahren und Dauer bestimmt Google – dem Kunden "
            "keine Dauer zusagen.",
            "Doppelte Profile nicht eigenmächtig löschen, sondern mit dem Inhaber klären.",
        ])),
        _abschnitt("Angaben prüfen", dok.haken([
            "Name genau wie im Geschäftsleben – ohne Orte, Leistungen oder Werbung.",
            "Hauptkategorie und weitere Kategorien passen zu den echten Leistungen.",
            "Adresse oder Servicegebiet stimmt (Wohnadresse nicht öffentlich, wenn Kunden nicht vorbeikommen).",
            "Telefonnummer stimmt und ist erreichbar.",
            "Webseite stimmt (falls vorhanden).",
            "Öffnungszeiten stimmen, auch an Feiertagen.",
            "Beschreibung höchstens %d Zeichen, sachlich, ohne Links und Telefonnummern." % BESCHREIBUNG_MAX,
            "Leistungen eingetragen.",
        ])),
        _abschnitt("Fotos", dok.haken([
            "Nur echte, eigene Fotos.",
            "Personen nur mit Einwilligung.",
            "Keine Kundenadressen, Hausnummern, Klingelschilder oder Kfz-Kennzeichen von Kunden erkennbar.",
        ])),
        _abschnitt("Bewertungen – nur echte Kunden", dok.haken([
            "Link zum Bewerten aus dem Profil holen und dem Inhaber geben.",
            "Keine gekauften Bewertungen, keine selbst geschriebenen Bewertungen.",
            "Keine Belohnungen (Rabatt, Gutschein, Geschenk) für Bewertungen.",
            "Alle Kunden gleich behandeln: nicht gezielt nur zufriedene Kunden um eine Bewertung bitten.",
        ])),
        _abschnitt("Übergabe", dok.haken([
            "Kurzanleitung übergeben und kurz zeigen.",
            "Der Inhaber prüft alle Angaben und bestätigt sie.",
            "Der Inhaber entscheidet, ob wir Verwalter bleiben.",
        ])),
    ]
    banner = _banner(BEISPIEL_HINWEIS) if beispiel else _banner("ARBEITSUNTERLAGE – Prüfliste für den Termin vor Ort.")
    return _seite("Google-Profil – Prüfliste: %s" % firma, "Prüfliste für den Termin vor Ort",
                  "%s · %s" % (firma, esc(d["ort"])), banner, _nav(namen, "pruefliste"), abschnitte,
                  "Zum Abhaken ausdrucken. Allgemeine Hinweise ohne Gewähr – keine Rechtsberatung.")


def _uebergabe(d, namen, beispiel):
    dok = _Dokument(markieren=not beispiel)
    firma = esc(d["firma"])
    abschnitte = []
    if not beispiel:
        abschnitte.append(dok.offen("Vor der Übergabe prüfen: Stimmen alle Angaben? Dieser Kasten erscheint nicht "
                                    "im Ausdruck.", "Übergabe-Anleitung vor der Übergabe prüfen (Inhaber)",
                                    element="div", klasse="klaeren nur-bildschirm"))
    abschnitte += [
        _abschnitt("Sie sind Inhaber", "<p>Das Google-Profil von %s gehört Ihnen. Wir sind nur als Verwalter "
                   "eingetragen – so lange Sie das möchten.</p>" % firma),
        _abschnitt("Uns als Verwalter entfernen", "<p>In den Einstellungen Ihres Profils sehen Sie, welche Personen "
                   "Zugriff haben. Dort können Sie uns jederzeit entfernen. Dafür müssen Sie niemanden fragen.</p>"),
        _abschnitt("Angaben ändern, zum Beispiel Öffnungszeiten", "<p>Melden Sie sich mit dem Google-Konto an, mit "
                   "dem das Profil verbunden ist. Suchen Sie dann bei Google nach Ihrem Firmennamen: Als Inhaber "
                   "sehen Sie Ihr Profil mit einer Möglichkeit zum Bearbeiten.</p><p>Denken Sie an Feiertage und "
                   "Betriebsurlaub.</p>"),
        _abschnitt("Fotos ergänzen", "<p>Neue, echte Fotos zeigen, wie Sie arbeiten. Zeigen Sie nur Personen, die "
                   "einverstanden sind. Adressen oder Kennzeichen Ihrer Kunden dürfen nicht erkennbar sein.</p>"),
        _abschnitt("Auf Bewertungen antworten", "<p>Bleiben Sie sachlich und freundlich, auch bei Kritik. Bedanken "
                   "Sie sich, schreiben Sie kurz, was Sie tun, und bieten Sie ein Gespräch an.</p><p>Nennen Sie "
                   "keine Namen, Adressen oder Auftragsdetails Ihrer Kunden.</p>"),
        _abschnitt("Um Bewertungen bitten", "<p>In Ihrem Profil finden Sie einen Link, mit dem Kunden Sie bewerten "
                   "können. Geben Sie ihn Ihren Kunden – allen, nicht nur den zufriedenen.</p><p><strong>Nicht "
                   "erlaubt:</strong> Bewertungen kaufen, selbst schreiben oder schreiben lassen und Belohnungen "
                   "(zum Beispiel Rabatte) für Bewertungen.</p>"),
        _abschnitt("Wenn etwas anders aussieht", "<p>Google ändert seine Oberfläche gelegentlich. Dann heißen Knöpfe "
                   "anders oder sind an anderer Stelle. Suchen Sie in der Google-Hilfe nach "
                   "„Unternehmensprofil“ oder fragen Sie uns.</p>"),
    ]
    if d["anbieter"] or d["anbieter_kontakt"]:
        felder = []
        if d["anbieter"]:
            felder.append(("Ansprechpartner", esc(d["anbieter"]), None))
        if d["anbieter_kontakt"]:
            felder.append(("Kontakt", esc(d["anbieter_kontakt"]), None))
        ansprech = dok.felder(felder)
    else:
        ansprech = dok.offen('Ansprechpartner: <span class="linie"></span><br>Telefon: <span class="linie"></span>',
                             "Ansprechpartner und Telefonnummer des Anbieters eintragen")
    abschnitte.append(_abschnitt("Fragen? Ihr Ansprechpartner", ansprech))
    banner = _banner(BEISPIEL_HINWEIS) if beispiel else ""
    return _seite("Ihr Google-Profil – Kurzanleitung: %s" % firma, "Ihr Google-Profil – kurz erklärt",
                  "Für %s" % firma, banner, _nav(namen, "uebergabe"), abschnitte,
                  "Allgemeine Hinweise ohne Gewähr – keine Rechtsberatung.")


def erzeugen_alle(d, namen=None, beispiel=False):
    """Erzeugt alle drei Unterlagen aus geprüften Eingaben. Rückgabe: {dateiname: html} in fester
    Reihenfolge (Entwurf, Prüfliste, Übergabe). ``beispiel=True`` setzt den Beispiel-Hinweis und
    meldet keine offenen Punkte."""
    namen = namen or DATEIEN
    bauer = {"entwurf": _entwurf, "pruefliste": _pruefliste, "uebergabe": _uebergabe}
    return {namen[r]: bauer[r](d, namen, beispiel) for r in ROLLEN}


def beispiel_alle(namen):
    return erzeugen_alle(eingabe_pruefen(BEISPIEL_DATEN), namen, beispiel=True)


def einschraenkungen(d):
    text, gekuerzt = beschreibung_bauen(d)
    liste = [
        "Arbeitsunterlagen: AUTONOMOUS trägt nichts bei Google ein und hat keinen Zugang zu Google. Das Eintragen "
        "geschieht beim Termin vor Ort durch den Inhaber oder mit seiner Zustimmung.",
        "Kategorien sind nur Suchbegriff-Vorschläge – die Auswahlliste gibt Google vor.",
        "Die Beschreibung ist ein Entwurf aus den Eingaben; ihre inhaltliche Richtigkeit ist nicht geprüft.",
        "Bestätigung (Verifizierung) und Darstellung bei Google liegen nicht in unserer Hand – keine Zusagen zu "
        "Dauer oder Platzierung.",
        "Allgemeine Hinweise zu Fotos und Bewertungen – keine Rechtsberatung.",
    ]
    if gekuerzt:
        liste.append("Beschreibung gekürzt – nicht alle Leistungen sind darin genannt.")
    if not d["oeffnungszeiten"]:
        liste.append("Öffnungszeiten nicht angegeben.")
    if not (d["telefon"] or d["email"]):
        liste.append("Kein Kontaktweg (Telefon oder E-Mail) angegeben.")
    if not (d["adresse"] or d["einzugsgebiet"]):
        liste.append("Weder Adresse noch Servicegebiet angegeben.")
    return liste
