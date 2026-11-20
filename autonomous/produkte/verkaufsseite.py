# -*- coding: utf-8 -*-
"""Verkaufsseite für das erste Angebot.

Zwei Varianten (Eingabe ``angebot``):
- ``google_profil`` (Standard, Empfehlung der Marktrecherche): „Google-Profil-Paket“
- ``webseite`` (Stufe 2): „Webseiten-Paket“

Ehrlichkeitsregeln:
- Preis und Lieferzeit erscheinen NUR, wenn der Inhaber sie eingegeben hat. Sonst steht dort
  sichtbar „wird vom Inhaber festgelegt“. Ein Preisvorschlag aus der Marktrecherche kommt nie
  auf die Seite.
- Der Leistungsumfang beschreibt genau das, was der Generator (webseite.py) tatsächlich liefert.
- Keine erfundenen Referenzen, Kundenzahlen oder Bewertungen.
"""

import os

from . import (SYMBOLE, bereinigen, css_seite, email_pruefen, esc, platzhalter_rechtliches,
               telefon_pruefen)
from . import google_profil, webseite
from ..wallet import betrag_in_cent, euro

ENTWURF_HINWEIS = ("ENTWURF – Verkaufsseite. Vor der Veröffentlichung legt der Inhaber Preis, Lieferzeit, "
                   "Kontakt, Impressum und Datenschutz fest.")

ENTHALTEN = [
    "Eine Seite mit Ihren Leistungen, Ihrem Einsatzgebiet und Ihrer Erreichbarkeit",
    "Gut lesbar auf Handy, Tablet und Computer",
    "Anrufen und E-Mail mit einem Fingertipp",
    "Ohne Fremddienste: keine Tracker, keine fremden Schriftarten; die Seite selbst setzt keine Cookies",
    "Platz für Impressum und Datenschutzerklärung (die Texte liefern Sie)",
    "Übergabe als fertige Datei, die auf üblichem Webspace läuft",
]
NICHT_ENTHALTEN = [
    "Domain und Hosting",
    "Rechtstexte (Impressum, Datenschutzerklärung) und Rechtsberatung",
    "Fotos und Logo-Gestaltung",
    "Laufende Pflege und spätere Änderungen",
]
VON_IHNEN = [
    "Firmenname, Branche und Ort",
    "Ihre Leistungen (Stichworte genügen)",
    "Einsatzgebiet und Erreichbarkeit",
    "Telefon und/oder E-Mail für Kundenanfragen",
    "Texte für Impressum und Datenschutzerklärung",
]


ANGEBOTE = ("google_profil", "webseite")
STANDARD_ANGEBOT = "google_profil"  # Empfehlung der Marktrecherche (autonomous/docs/MARKTANALYSE.md)


def eingabe_pruefen(eingabe):
    if not isinstance(eingabe, dict):
        raise ValueError("Eingabe muss ein Objekt sein.")
    d = {}
    angebot = eingabe.get("angebot")
    if angebot in (None, ""):
        angebot = STANDARD_ANGEBOT
    if not isinstance(angebot, str) or angebot not in ANGEBOTE:
        raise ValueError("angebot muss 'google_profil' oder 'webseite' sein.")
    d["angebot"] = angebot
    preis = eingabe.get("preis")
    d["preis_cent"] = betrag_in_cent(preis) if preis not in (None, "") else None
    d["lieferzeit"] = bereinigen(eingabe.get("lieferzeit"), 60, streng=True, name="lieferzeit")
    d["preis_hinweis"] = bereinigen(eingabe.get("preis_hinweis"), 160, streng=True, name="preis_hinweis")
    d["anbieter"] = bereinigen(eingabe.get("anbieter"), 80, streng=True, name="anbieter")
    d["region"] = bereinigen(eingabe.get("region"), 60, streng=True, name="region") or "NRW"
    d["telefon"], d["telefon_link"] = telefon_pruefen(eingabe.get("telefon"))
    d["email"] = email_pruefen(eingabe.get("email"))
    return d


def _liste(eintraege, symbol):
    return '<ul class="liste">%s</ul>' % "".join(
        "<li>%s<span>%s</span></li>" % (SYMBOLE[symbol], esc(e)) for e in eintraege)


def _offen(text, offen):
    return '<p class="platzhalter" data-offen="%s">%s</p>' % (esc(offen), esc(text))


CSS_ZUSATZ = (
    ".schritte{list-style:none;counter-reset:schritt;margin:28px 0 0;padding:0;display:grid;"
    "grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:16px}"
    ".schritte li{counter-increment:schritt;background:#fff;border:1px solid var(--rand);border-radius:16px;"
    "padding:20px}"
    ".schritte li::before{content:counter(schritt);display:flex;align-items:center;justify-content:center;"
    "width:36px;height:36px;border-radius:50%;background:var(--akzent);color:#fff;font-weight:800;margin-bottom:10px}"
    ".schritte h3{margin-bottom:.3em}.schritte p{margin:0;color:var(--leise)}"
    ".preisbox{background:#fff;border:2px solid var(--akzent);border-radius:18px;padding:24px;max-width:560px}"
    ".preis{font-size:2.4rem;font-weight:800;color:var(--dunkel);margin:0 0 .2em}"
    "details{background:#fff;border:1px solid var(--rand);border-radius:12px;padding:14px 18px}"
    "details+details{margin-top:12px}summary{cursor:pointer;font-weight:700}details p{margin:.6em 0 0}"
)


def erzeugen(d, beispiel_link="beispiel.html", banner=ENTWURF_HINWEIS, uebergabe_link="beispiel-uebergabe.html"):
    """Baut die Verkaufsseite aus geprüften Eingaben (Ergebnis von eingabe_pruefen)."""
    if d.get("angebot", STANDARD_ANGEBOT) == "google_profil":
        return _erzeugen_google(d, beispiel_link, banner, uebergabe_link)
    region = esc(d["region"])
    marke = esc(d["anbieter"]) if d["anbieter"] else "Webseiten-Paket"
    beispiel = esc(beispiel_link)
    teile = [
        "<!DOCTYPE html>\n<!-- Erstellt mit AUTONOMOUS (Product-Agent): ohne JavaScript, ohne externe Dienste. -->\n"
        '<html lang="de">\n<head>\n<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n',
        "<title>Webseiten-Paket für Handwerk, Bau und Reinigung – %s</title>\n" % region,
        '<meta name="description" content="Eigene Webseite für kleine Handwerks-, Bau- und Reinigungsbetriebe in %s: '
        'Leistungen, Einsatzgebiet und Kontakt auf einer Seite, gut lesbar auf dem Handy.">\n' % region,
        "<style>%s%s</style>\n</head>\n<body>\n" % (css_seite("verkauf"), CSS_ZUSATZ),
    ]
    if banner:
        teile.append('<div class="entwurf" role="note" data-offen="Entwurfshinweis vor der Veröffentlichung '
                     'entfernen">%s</div>\n' % esc(banner))
    teile.append('<header class="kopf"><div class="wrap kopf-innen"><a class="marke" href="#titel">%s</a>'
                 '<a class="knopf klein" href="#anfrage">Anfragen</a></div></header>\n<main>\n' % marke)

    teile.append(
        '<section class="held" aria-labelledby="titel"><div class="wrap">'
        '<p class="dachzeile">Für Handwerk, Bau und Reinigung in %s</p>'
        '<h1 id="titel">Ihre eigene Firmen-Webseite – eine Seite, alles Wichtige</h1>'
        '<p class="slogan">Wir erstellen für kleine Betriebe eine übersichtliche Webseite: Ihre Leistungen, Ihr '
        'Einsatzgebiet und direkter Kontakt per Anruf oder E-Mail – gut lesbar auf jedem Handy.</p>'
        '<div class="aktionen"><a class="knopf weiss" href="#anfrage">Unverbindlich anfragen</a>'
        '<a class="knopf umriss" href="%s">Beispiel ansehen</a></div></div></section>\n' % (region, beispiel))

    abschnitte = [
        ("leistung", '<h2>Das ist enthalten</h2><p class="einleitung">Webseiten-Paket für kleine Handwerks-, Bau- '
                     'und Reinigungsbetriebe in %s.</p><div class="zwei"><div>%s</div>'
                     '<div><h3>Nicht enthalten</h3>%s</div></div>'
         % (region, _liste(ENTHALTEN, "haken"), _liste(NICHT_ENTHALTEN, "kreuz"))),
        ("ablauf", '<h2>So läuft es ab</h2><ol class="schritte">'
                   '<li><h3>Anfrage</h3><p>Sie melden sich per Telefon oder E-Mail. Wir klären Leistungen, '
                   'Einsatzgebiet und Kontaktdaten.</p></li>'
                   '<li><h3>Angebot</h3><p>Sie erhalten ein schriftliches Angebot zum Paketpreis. Erst mit Ihrer '
                   'Zusage geht es los.</p></li>'
                   '<li><h3>Lieferung</h3><p>Sie bekommen den fertigen Entwurf zur Durchsicht.</p></li>'
                   '<li><h3>Abnahme</h3><p>Sie prüfen alles. Erst nach Ihrer Abnahme ist die Seite fertig.</p></li>'
                   '</ol>'),
        ("beispiel", '<div class="zwei"><div><h2>Beispiel</h2><p>So kann das Ergebnis aussehen: '
                     '<a href="%s">Beispielseite einer fiktiven Musterfirma</a>. Die Musterfirma ist erfunden – '
                     'sie zeigt nur Aufbau und Gestaltung.</p></div><div><h2>Das brauchen wir von Ihnen</h2>%s'
                     '</div></div>' % (beispiel, _liste(VON_IHNEN, "haken"))),
    ]

    # Preis und Lieferzeit: nur Angaben des Inhabers, sonst sichtbarer Platzhalter
    if d["preis_cent"] is not None:
        preis = '<p class="preis">%s</p><p>Paketpreis für den oben beschriebenen Umfang.</p>' % esc(euro(d["preis_cent"]))
        if d["preis_hinweis"]:
            preis += "<p>%s</p>" % esc(d["preis_hinweis"])
        else:
            preis += _offen("Angabe zur Umsatzsteuer: wird vom Inhaber ergänzt.",
                            "Umsatzsteuer-Hinweis zum Preis ergänzen (Inhaber)")
    else:
        preis = _offen("Preis: wird vom Inhaber festgelegt.", "Preis festlegen (Inhaber)")
    if d["lieferzeit"]:
        liefer = "<p><strong>Lieferzeit:</strong> %s</p>" % esc(d["lieferzeit"])
    else:
        liefer = _offen("Lieferzeit: wird vom Inhaber festgelegt.", "Lieferzeit festlegen (Inhaber)")
    abschnitte.append(("preis", '<h2>Preis</h2><div class="preisbox">%s%s</div>' % (preis, liefer)))

    abschnitte.append(("fragen", '<h2>Häufige Fragen</h2>'
                       '<details><summary>Brauche ich technisches Wissen?</summary><p>Für die Inhalte nicht: Sie '
                       'liefern die Angaben, wir bauen daraus die Seite. Zum Veröffentlichen brauchen Sie einen '
                       'Webspace mit Domain – das ist nicht im Paket enthalten.</p></details>'
                       '<details><summary>Wo liegt die Seite später?</summary><p>Bei einem Webspace Ihrer Wahl. Die '
                       'Seite ist eine einzelne Datei und läuft auf üblichem Webspace.</p></details>'
                       '<details><summary>Ist die Seite rechtssicher?</summary><p>Impressum und Datenschutzerklärung '
                       'liefern Sie. Wir bauen sie ein, geben aber keine Rechtsberatung.</p></details>'))

    kontakt = []
    if d["telefon"]:
        kontakt.append('<a class="knopf" href="tel:%s">%s %s</a>' % (esc(d["telefon_link"]), SYMBOLE["telefon"],
                                                                     esc(d["telefon"])))
    if d["email"]:
        kontakt.append('<a class="knopf" href="mailto:%s">%s %s</a>' % (esc(d["email"]), SYMBOLE["mail"],
                                                                        esc(d["email"])))
    anfrage = '<h2>Anfrage</h2><p class="einleitung">Rufen Sie an oder schreiben Sie eine E-Mail. Die Anfrage ist ' \
              'unverbindlich.</p>'
    if d["anbieter"]:
        anfrage += "<p><strong>Anbieter:</strong> %s</p>" % esc(d["anbieter"])
    else:
        anfrage += _offen("Anbieter: Firmenname wird vom Inhaber ergänzt.", "Firmennamen des Anbieters ergänzen")
    if kontakt:
        anfrage += '<div class="aktionen">%s</div>' % "".join(kontakt)
    else:
        anfrage += _offen("Kontakt: Telefon und E-Mail werden vom Inhaber ergänzt.",
                          "Kontaktdaten des Anbieters ergänzen (Telefon oder E-Mail)")
    abschnitte.append(("anfrage", anfrage))

    for i, (anker, inhalt) in enumerate(abschnitte):
        klasse = "abschnitt alt" if i % 2 else "abschnitt"
        teile.append('<section id="%s" class="%s"><div class="wrap">%s</div></section>\n' % (anker, klasse, inhalt))
    teile.append(platzhalter_rechtliches())
    teile.append('</main>\n<footer class="fuss"><div class="wrap"><span>%s</span><nav aria-label="Rechtliches">'
                 '<a href="#impressum">Impressum</a><a href="#datenschutz">Datenschutz</a></nav></div></footer>\n'
                 '</body>\n</html>\n' % marke)
    return "".join(teile)


def einschraenkungen(d):
    liste = ["Impressum und Datenschutzerklärung sind Platzhalter – muss der Inhaber ausfüllen (keine Rechtsberatung).",
             "Kein Hosting und keine Domain enthalten.",
             "Kein Anfrageformular (bewusst: ohne JavaScript und ohne Server) – Anfragen per Telefon oder E-Mail."]
    if d.get("angebot", STANDARD_ANGEBOT) == "google_profil":
        liste.append("Bestätigung und Darstellung bei Google liegen nicht in unserer Hand – die Seite verspricht "
                     "keine Platzierung und keine Dauer.")
    if d["preis_cent"] is None:
        liste.append("Preis nicht festgelegt – Entscheidung des Inhabers.")
    if not d["lieferzeit"]:
        liste.append("Lieferzeit nicht festgelegt – Entscheidung des Inhabers.")
    if not (d["telefon"] or d["email"]):
        liste.append("Kontaktdaten des Anbieters fehlen – ohne sie kann die Seite nicht veröffentlicht werden.")
    return liste


def beispiel_erzeugen():
    """Die Beispielseite der fiktiven Musterfirma (deutlich als Beispiel gekennzeichnet)."""
    return webseite.erzeugen(webseite.eingabe_pruefen(webseite.BEISPIEL_DATEN), banner=webseite.BEISPIEL_HINWEIS,
                             banner_offen=None)


def beispiele_inhalte():
    """Alle committeten Beispiele (autonomous/beispiele) als {dateiname: html}."""
    namen = google_profil.BEISPIEL_COMMITTET
    inhalte = {
        "beispiel-webseite.html": beispiel_erzeugen(),
        "verkaufsseite.html": erzeugen(eingabe_pruefen({"angebot": "google_profil"}), beispiel_link=namen["entwurf"],
                                       uebergabe_link=namen["uebergabe"]),
        "verkaufsseite-webseiten.html": erzeugen(eingabe_pruefen({"angebot": "webseite"}),
                                                 beispiel_link="beispiel-webseite.html"),
    }
    inhalte.update(google_profil.beispiel_alle(namen))
    return inhalte


def beispiele_schreiben(ordner):
    """Schreibt die committeten Beispiele (autonomous/beispiele). Überschreibt nur diese Dateien."""
    os.makedirs(ordner, exist_ok=True)
    dateien = beispiele_inhalte()
    for name, inhalt in dateien.items():
        with open(os.path.join(ordner, name), "w", encoding="utf-8", newline="\n") as f:
            f.write(inhalt)
    return sorted(dateien)


# ---------------------------------------------------------------- Variante Google-Profil-Paket
GP_ENTHALTEN = [
    "Kurzer Check: Gibt es schon ein Profil, wer hat Zugriff, stimmen Name, Adresse, Telefon und Öffnungszeiten?",
    "Profil anlegen oder übernehmen und die Bestätigung bei Google anstoßen",
    "Alles ausfüllen: Kategorien, Leistungen, Einsatzgebiet, Öffnungszeiten und eine sachliche Beschreibung",
    "Echte Fotos bei einem Termin vor Ort – Team, Fahrzeuge, Arbeiten (nur mit Einwilligung der Abgebildeten)",
    "Ein Link, mit dem Sie Ihre Kunden um eine Bewertung bitten können",
    "Übergabe mit einer einseitigen Kurzanleitung",
]
GP_NICHT_ENTHALTEN = [
    "Keine Garantie für eine bestimmte Platzierung bei Google",
    "Keine Bewertungen – weder gekauft noch selbst geschrieben",
    "Keine Werbung bei Google (Anzeigen)",
    "Keine Rechtstexte und keine Rechtsberatung",
    "Keine laufende Pflege nach der Übergabe",
]
GP_VON_IHNEN = [
    "Ihr eigenes Google-Konto – Sie melden sich selbst an, wir brauchen kein Passwort",
    "Ihre Leistungen und Ihr Einsatzgebiet",
    "Ihre Öffnungszeiten und Kontaktdaten",
    "Zeit für einen Termin vor Ort",
    "Die Einwilligung der Personen, die auf Fotos zu sehen sein sollen",
]


# Fünf Ablaufschritte passen auf breiten Bildschirmen in eine Reihe
GP_CSS = ".schritte.fuenf{grid-template-columns:repeat(auto-fit,minmax(180px,1fr))}"


def _erzeugen_google(d, beispiel_link, banner, uebergabe_link):
    region = esc(d["region"])
    marke = esc(d["anbieter"]) if d["anbieter"] else "Google-Profil-Paket"
    beispiel = esc(beispiel_link)
    uebergabe = esc(uebergabe_link)
    teile = [
        "<!DOCTYPE html>\n<!-- Erstellt mit AUTONOMOUS (Product-Agent): ohne JavaScript, ohne externe Dienste. -->\n"
        '<html lang="de">\n<head>\n<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n',
        "<title>Google-Profil-Paket für Handwerk, Bau und Reinigung – %s</title>\n" % region,
        '<meta name="description" content="Google-Unternehmensprofil für kleine Handwerks-, Bau- und Reinigungsbetriebe '
        'in %s: prüfen, anlegen oder übernehmen, vollständig ausfüllen, echte Fotos – Sie bleiben Inhaber.">\n' % region,
        "<style>%s%s</style>\n</head>\n<body>\n" % (css_seite("verkauf"), CSS_ZUSATZ + GP_CSS),
    ]
    if banner:
        teile.append('<div class="entwurf" role="note" data-offen="Entwurfshinweis vor der Veröffentlichung '
                     'entfernen">%s</div>\n' % esc(banner))
    teile.append('<header class="kopf"><div class="wrap kopf-innen"><a class="marke" href="#titel">%s</a>'
                 '<a class="knopf klein" href="#anfrage">Anfragen</a></div></header>\n<main>\n' % marke)
    teile.append(
        '<section class="held" aria-labelledby="titel"><div class="wrap">'
        '<p class="dachzeile">Für Handwerk, Bau und Reinigung in %s</p>'
        '<h1 id="titel">Ihr Google-Profil – vollständig, echt und ordentlich übergeben</h1>'
        '<p class="slogan">Wer Ihren Betrieb bei Google oder Google Maps sucht, sieht dort Ihr Unternehmensprofil – '
        'mit Telefonnummer, Öffnungszeiten, Fotos und Bewertungen. Wir sorgen dafür, dass die Angaben stimmen und '
        'vollständig sind. Sie bleiben Inhaber.</p>'
        '<div class="aktionen"><a class="knopf weiss" href="#anfrage">Unverbindlich anfragen</a>'
        '<a class="knopf umriss" href="%s">Beispiel ansehen</a></div></div></section>\n' % (region, beispiel))

    abschnitte = [
        ("leistung", '<h2>Das ist enthalten</h2><p class="einleitung">Google-Profil-Paket für kleine Handwerks-, Bau- '
                     'und Reinigungsbetriebe in %s.</p><div class="zwei"><div>%s</div>'
                     '<div><h3>Nicht enthalten</h3>%s</div></div>'
         % (region, _liste(GP_ENTHALTEN, "haken"), _liste(GP_NICHT_ENTHALTEN, "kreuz"))),
        ("inhaber", '<h2>Sie bleiben Inhaber</h2><p class="einleitung">Wir fragen nie nach Ihren Passwörtern. Sie '
                    'melden sich selbst an und tragen uns als Verwalter ein. Sie können uns jederzeit wieder '
                    'entfernen – dafür müssen Sie niemanden fragen.</p>'),
        ("ablauf", '<h2>So läuft es ab</h2><ol class="schritte fuenf">'
                   '<li><h3>Anfrage</h3><p>Sie melden sich per Telefon oder E-Mail.</p></li>'
                   '<li><h3>Kurzes Gespräch</h3><p>Wir klären, ob es schon ein Profil gibt und was Sie brauchen. '
                   'Danach erhalten Sie ein schriftliches Angebot. Erst mit Ihrer Zusage geht es los.</p></li>'
                   '<li><h3>Termin vor Ort</h3><p>Wir gehen die Angaben gemeinsam durch und machen echte Fotos.</p></li>'
                   '<li><h3>Profil fertig</h3><p>Wir tragen alles ein. Die Bestätigung durch Google kann je nach '
                   'Verfahren dauern – darauf haben wir keinen Einfluss.</p></li>'
                   '<li><h3>Übergabe</h3><p>Sie erhalten die Kurzanleitung und prüfen alles. Erst nach Ihrer Abnahme '
                   'ist der Auftrag erledigt.</p></li></ol>'),
        ("beispiel", '<div class="zwei"><div><h2>Beispiel</h2><p>So bereiten wir ein Profil vor: '
                     '<a href="%s">Profil-Entwurf einer fiktiven Musterfirma</a> und die '
                     '<a href="%s">Kurzanleitung zur Übergabe</a>. Die Musterfirma ist erfunden – sie zeigt nur '
                     'Aufbau und Inhalt.</p></div><div><h2>Das brauchen wir von Ihnen</h2>%s</div></div>'
         % (beispiel, uebergabe, _liste(GP_VON_IHNEN, "haken"))),
    ]

    if d["preis_cent"] is not None:
        preis = ('<p class="preis">%s</p><p>Paketpreis für den oben beschriebenen Umfang, einmalig je Standort.</p>'
                 % esc(euro(d["preis_cent"])))
        if d["preis_hinweis"]:
            preis += "<p>%s</p>" % esc(d["preis_hinweis"])
        else:
            preis += _offen("Angabe zur Umsatzsteuer: wird vom Inhaber ergänzt.",
                            "Umsatzsteuer-Hinweis zum Preis ergänzen (Inhaber)")
    else:
        preis = _offen("Preis: wird vom Inhaber festgelegt.", "Preis festlegen (Inhaber)")
    if d["lieferzeit"]:
        liefer = "<p><strong>Lieferzeit:</strong> %s</p>" % esc(d["lieferzeit"])
    else:
        liefer = _offen("Lieferzeit: wird vom Inhaber festgelegt.", "Lieferzeit festlegen (Inhaber)")
    abschnitte.append(("preis", '<h2>Preis</h2><div class="preisbox">%s%s</div>' % (preis, liefer)))

    abschnitte.append(("fragen", '<h2>Häufige Fragen</h2>'
                       '<details><summary>Kostet das Google-Profil selbst etwas?</summary><p>Google verlangt für das '
                       'Unternehmensprofil nach unserem Kenntnisstand kein Geld. Sie bezahlen nur unsere Arbeit.</p>'
                       '</details>'
                       '<details><summary>Komme ich damit bei Google nach oben?</summary><p>Das kann niemand seriös '
                       'versprechen – über die Reihenfolge entscheidet Google. Ein vollständiges, richtiges Profil '
                       'hilft Kunden aber, Sie zu finden und zu erreichen.</p></details>'
                       '<details><summary>Brauchen Sie mein Passwort?</summary><p>Nein. Sie melden sich selbst an und '
                       'tragen uns als Verwalter ein.</p></details>'
                       '<details><summary>Was ist mit Bewertungen?</summary><p>Wir schreiben und kaufen keine '
                       'Bewertungen. Sie bekommen einen Link, mit dem Sie Ihre Kunden um eine Bewertung bitten '
                       'können.</p></details>'))

    kontakt = []
    if d["telefon"]:
        kontakt.append('<a class="knopf" href="tel:%s">%s %s</a>' % (esc(d["telefon_link"]), SYMBOLE["telefon"],
                                                                     esc(d["telefon"])))
    if d["email"]:
        kontakt.append('<a class="knopf" href="mailto:%s">%s %s</a>' % (esc(d["email"]), SYMBOLE["mail"],
                                                                        esc(d["email"])))
    anfrage = '<h2>Anfrage</h2><p class="einleitung">Rufen Sie an oder schreiben Sie eine E-Mail. Die Anfrage ist ' \
              'unverbindlich.</p>'
    if d["anbieter"]:
        anfrage += "<p><strong>Anbieter:</strong> %s</p>" % esc(d["anbieter"])
    else:
        anfrage += _offen("Anbieter: Firmenname wird vom Inhaber ergänzt.", "Firmennamen des Anbieters ergänzen")
    if kontakt:
        anfrage += '<div class="aktionen">%s</div>' % "".join(kontakt)
    else:
        anfrage += _offen("Kontakt: Telefon und E-Mail werden vom Inhaber ergänzt.",
                          "Kontaktdaten des Anbieters ergänzen (Telefon oder E-Mail)")
    abschnitte.append(("anfrage", anfrage))

    for i, (anker, inhalt) in enumerate(abschnitte):
        klasse = "abschnitt alt" if i % 2 else "abschnitt"
        teile.append('<section id="%s" class="%s"><div class="wrap">%s</div></section>\n' % (anker, klasse, inhalt))
    teile.append(platzhalter_rechtliches())
    teile.append('</main>\n<footer class="fuss"><div class="wrap"><span>%s</span><nav aria-label="Rechtliches">'
                 '<a href="#impressum">Impressum</a><a href="#datenschutz">Datenschutz</a></nav></div></footer>\n'
                 '</body>\n</html>\n' % marke)
    return "".join(teile)
