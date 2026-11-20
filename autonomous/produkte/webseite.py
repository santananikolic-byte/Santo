# -*- coding: utf-8 -*-
"""Generator für das erste Angebot: eine Ein-Seiten-Webseite für kleine Betriebe.

Deterministisch (kein Modell nötig): Die Seite entsteht nur aus den Eingaben des Inhabers.
Es wird nichts hinzuerfunden – keine Referenzen, keine Jahreszahlen, keine Kundenstimmen.
Ergebnis: eine einzelne HTML-Datei mit eingebettetem CSS, ohne JavaScript und ohne externe
Ressourcen. Impressum und Datenschutz sind deutlich markierte Platzhalter.
"""

from . import (SYMBOLE, bereinigen, css_seite, email_pruefen, esc, esc_zeilen, liste_bereinigen,
               platzhalter_rechtliches, telefon_pruefen)

ENTWURF_HINWEIS = "ENTWURF – vor der Veröffentlichung Impressum und Datenschutz ausfüllen und diesen Hinweis entfernen."
ENTWURF_OFFEN = "Entwurfshinweis vor der Veröffentlichung entfernen"
BEISPIEL_HINWEIS = "BEISPIEL – fiktive Musterfirma. Alle Angaben sind erfunden; es gibt diese Firma nicht."

# Erkennbar fiktive Musterfirma für die Beispielseite (Telefonnummer und Domain sind Platzhalter;
# „.example“ ist eine reservierte, nie vergebene Endung)
BEISPIEL_DATEN = {
    "firma": "Musterfirma Reinigung (Beispiel)",
    "branche": "Gebäudereinigung",
    "ort": "Musterstadt",
    "leistungen": ["Unterhaltsreinigung für Büros und Praxen", "Treppenhausreinigung", "Glas- und Fensterreinigung",
                   "Grundreinigung nach Umbau oder Auszug", "Baureinigung"],
    "telefon": "01234 567890",
    "email": "kontakt@musterfirma.example",
    "slogan": "Saubere Büros, Praxen und Treppenhäuser – regelmäßig oder einmalig.",
    "einzugsgebiet": "Musterstadt und Umgebung (bis etwa 30 km)",
    "oeffnungszeiten": "Mo–Fr 7–18 Uhr\nSa nach Vereinbarung",
}

LAENGEN = {"firma": 80, "branche": 60, "ort": 60, "slogan": 160, "einzugsgebiet": 200, "oeffnungszeiten": 200,
           "ueber_uns": 1200}
FELDER = ("firma", "branche", "ort", "leistungen", "telefon", "email", "slogan", "einzugsgebiet",
          "oeffnungszeiten", "ueber_uns")


def eingabe_pruefen(eingabe):
    """Prüft und säubert die Eingaben. Wirft ValueError mit verständlicher Meldung."""
    if not isinstance(eingabe, dict):
        raise ValueError("Eingabe muss ein Objekt sein.")
    d = {}
    for feld in ("firma", "branche", "ort"):
        d[feld] = bereinigen(eingabe.get(feld), LAENGEN[feld], streng=True, name=feld)
        if not d[feld]:
            raise ValueError("Pflichtfeld fehlt: %s" % feld)
    d["leistungen"] = liste_bereinigen(eingabe.get("leistungen"), 80, 12, name="Leistung")
    if not d["leistungen"]:
        raise ValueError("Pflichtfeld fehlt: leistungen (mindestens eine Leistung)")
    d["slogan"] = bereinigen(eingabe.get("slogan"), LAENGEN["slogan"], streng=True, name="slogan")
    d["einzugsgebiet"] = bereinigen(eingabe.get("einzugsgebiet"), LAENGEN["einzugsgebiet"], streng=True,
                                    name="einzugsgebiet")
    zeiten = eingabe.get("oeffnungszeiten")
    if isinstance(zeiten, str):
        zeiten = zeiten.replace(";", "\n")
    d["oeffnungszeiten"] = bereinigen(zeiten, LAENGEN["oeffnungszeiten"], mehrzeilig=True, streng=True,
                                      name="oeffnungszeiten")
    d["ueber_uns"] = bereinigen(eingabe.get("ueber_uns"), LAENGEN["ueber_uns"], mehrzeilig=True, streng=True,
                                name="ueber_uns")
    d["telefon"], d["telefon_link"] = telefon_pruefen(eingabe.get("telefon"))
    d["email"] = email_pruefen(eingabe.get("email"))
    return d


def thema_fuer(branche):
    b = branche.lower()
    if any(w in b for w in ("reinig", "putz", "sauber", "glas", "fenster", "hausmeister", "gebäudeservice",
                            "facility")):
        return "reinigung"
    if any(w in b for w in ("bau", "maurer", "beton", "sanierung", "abbruch", "dach", "zimmer", "estrich",
                            "pflaster", "fliesen")):
        return "bau"
    return "handwerk"


def _banner(text, offen):
    if not text:
        return ""
    attr = ' data-offen="%s"' % esc(offen) if offen else ""
    return '<div class="entwurf" role="note"%s>%s</div>\n' % (attr, esc(text))


def _absatz_mehrzeilig(text):
    return "".join("<p>%s</p>" % esc_zeilen(teil) for teil in text.split("\n\n") if teil.strip())


def erzeugen(d, banner=ENTWURF_HINWEIS, banner_offen=ENTWURF_OFFEN):
    """Baut die HTML-Seite aus geprüften Eingaben (Ergebnis von eingabe_pruefen)."""
    firma, branche, ort = esc(d["firma"]), esc(d["branche"]), esc(d["ort"])
    tel_link = esc(d["telefon_link"])
    beschreibung = "%s in %s: %s" % (d["branche"], d["ort"], ", ".join(d["leistungen"][:4]))
    if len(beschreibung) > 155:
        beschreibung = beschreibung[:152].rstrip() + "…"

    teile = [
        "<!DOCTYPE html>\n<!-- Erstellt mit AUTONOMOUS (Product-Agent): ohne JavaScript, ohne externe Dienste. -->\n"
        '<html lang="de">\n<head>\n<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n',
        "<title>%s – %s in %s</title>\n" % (firma, branche, ort),
        '<meta name="description" content="%s">\n' % esc(beschreibung),
        "<style>%s</style>\n</head>\n<body>\n" % css_seite(thema_fuer(d["branche"])),
        _banner(banner, banner_offen),
    ]

    # Kopfzeile
    if d["telefon"]:
        kopf_knopf = '<a class="knopf klein" href="tel:%s">%s Anrufen</a>' % (tel_link, SYMBOLE["telefon"])
    else:
        kopf_knopf = '<a class="knopf klein" href="#kontakt">Kontakt</a>'
    teile.append('<header class="kopf"><div class="wrap kopf-innen"><a class="marke" href="#titel">%s</a>%s'
                 '</div></header>\n<main>\n' % (firma, kopf_knopf))

    # Großer Einstieg
    slogan = esc(d["slogan"]) if d["slogan"] else "Ihr Ansprechpartner für %s in %s." % (branche, ort)
    knoepfe = []
    if d["telefon"]:
        knoepfe.append('<a class="knopf weiss" href="tel:%s">%s %s</a>' % (tel_link, SYMBOLE["telefon"],
                                                                         esc(d["telefon"])))
    if d["email"]:
        knoepfe.append('<a class="knopf umriss" href="mailto:%s">%s E-Mail schreiben</a>' % (esc(d["email"]),
                                                                                         SYMBOLE["mail"]))
    if not knoepfe:
        knoepfe.append('<a class="knopf weiss" href="#kontakt">Zum Kontakt</a>')
    teile.append('<section class="held" aria-labelledby="titel"><div class="wrap">'
                 '<p class="dachzeile">%s · %s</p><h1 id="titel">%s</h1><p class="slogan">%s</p>'
                 '<div class="aktionen">%s</div></div></section>\n' % (branche, ort, firma, slogan, "".join(knoepfe)))

    # Abschnitte mit abwechselndem Hintergrund
    abschnitte = []
    karten = "".join('<li class="karte">%s<span>%s</span></li>' % (SYMBOLE["haken"], esc(l)) for l in d["leistungen"])
    abschnitte.append(("leistungen", '<h2 id="h-leistungen">Unsere Leistungen</h2>'
                                     '<p class="einleitung">%s in %s – das bieten wir an:</p>'
                                     '<ul class="karten">%s</ul>' % (branche, ort, karten)))
    if d["ueber_uns"]:
        abschnitte.append(("ueber-uns", '<h2 id="h-ueber-uns">Über uns</h2>%s' % _absatz_mehrzeilig(d["ueber_uns"])))

    if d["einzugsgebiet"]:
        gebiet = '<div><h2>Einsatzgebiet</h2><p class="mit-symbol">%s<span>%s</span></p></div>' % (
            SYMBOLE["ort"], esc(d["einzugsgebiet"]))
    else:
        gebiet = '<div><h2>Standort</h2><p class="mit-symbol">%s<span>%s</span></p></div>' % (SYMBOLE["ort"], ort)
    zeiten = ""
    if d["oeffnungszeiten"]:
        zeiten = '<div><h2>Erreichbarkeit</h2><p class="mit-symbol">%s<span>%s</span></p></div>' % (
            SYMBOLE["uhr"], esc_zeilen(d["oeffnungszeiten"]))
    abschnitte.append(("gebiet", '<div class="zwei">%s%s</div>' % (gebiet, zeiten)))

    kontakt = []
    if d["telefon"]:
        kontakt.append('<li>%s<a href="tel:%s">%s</a></li>' % (SYMBOLE["telefon"], tel_link, esc(d["telefon"])))
    if d["email"]:
        kontakt.append('<li>%s<a href="mailto:%s">%s</a></li>' % (SYMBOLE["mail"], esc(d["email"]), esc(d["email"])))
    kontakt.append('<li>%s<span>%s, %s</span></li>' % (SYMBOLE["ort"], firma, ort))
    luecke = ""
    if not (d["telefon"] or d["email"]):
        luecke = ('<p class="platzhalter" data-offen="Kontaktweg ergänzen (Telefon oder E-Mail)">'
                  'Kontaktdaten fehlen – bitte Telefon oder E-Mail ergänzen.</p>')
    abschnitte.append(("kontakt", '<h2 id="h-kontakt">Kontakt</h2><p class="einleitung">So erreichen Sie uns:</p>'
                                  '%s<ul class="liste">%s</ul>' % (luecke, "".join(kontakt))))

    for i, (anker, inhalt) in enumerate(abschnitte):
        klasse = "abschnitt alt" if i % 2 else "abschnitt"
        teile.append('<section id="%s" class="%s"><div class="wrap">%s</div></section>\n' % (anker, klasse, inhalt))

    teile.append(platzhalter_rechtliches())
    teile.append('</main>\n<footer class="fuss"><div class="wrap"><span>© %s</span><nav aria-label="Rechtliches">'
                 '<a href="#impressum">Impressum</a><a href="#datenschutz">Datenschutz</a></nav></div></footer>\n'
                 '</body>\n</html>\n' % firma)
    return "".join(teile)


def einschraenkungen(d):
    liste = [
        "Impressum und Datenschutzerklärung sind Platzhalter – muss der Inhaber ausfüllen (keine Rechtsberatung).",
        "Kein Hosting und keine Domain enthalten – die Datei muss auf einen Webspace hochgeladen werden.",
        "Keine Fotos und kein Logo (in Version 1 nicht vorgesehen).",
        "Texte stammen nur aus den Eingaben; ihre inhaltliche Richtigkeit ist nicht geprüft.",
    ]
    if not d["telefon"]:
        liste.append("Keine Telefonnummer angegeben.")
    if not d["email"]:
        liste.append("Keine E-Mail-Adresse angegeben.")
    return liste
