# -*- coding: utf-8 -*-
"""Qualitätsprüfung für erzeugte Seiten (Product-Agent).

Prüft eine HTML-Datei auf Sicherheit (kein JavaScript, keine externen Ressourcen, nur erwartete
Elemente, Eingaben escaped) und Grundqualität (Mobil-Ansicht, Sprache, Titel, Hauptüberschrift,
Größe, Kontaktweg, Impressum/Datenschutz). Offene Punkte (Platzhalter) werden aus den
``data-offen``-Markierungen der Seite gesammelt – sie sind keine Fehler, sondern Aufgaben für
den Inhaber.

Die Prüfung liest die Datei nur als Daten; Inhalte werden nie ausgeführt.
"""

import re
from html.parser import HTMLParser

MAX_BYTES = 200 * 1024

ERLAUBTE_ELEMENTE = {
    "html", "head", "meta", "title", "style", "body", "header", "nav", "main", "section", "article", "aside",
    "div", "span", "p", "h1", "h2", "h3", "h4", "ul", "ol", "li", "a", "strong", "em", "small", "b", "i", "br",
    "hr", "footer", "address", "dl", "dt", "dd", "time", "figure", "figcaption", "details", "summary", "table",
    "thead", "tbody", "tr", "th", "td", "blockquote", "abbr", "sup", "sub",
    "svg", "path", "rect", "circle", "line", "polyline", "g",
}
URL_ATTRIBUTE = {"src", "href", "action", "formaction", "srcset", "poster", "data", "background", "xlink:href",
                 "cite", "manifest", "ping", "codebase", "archive", "longdesc", "usemap", "lowsrc", "dynsrc"}
ERLAUBTE_SCHEMATA = ("tel:", "mailto:")
_SCHEMA = re.compile(r"^[a-z][a-z0-9+.\-]*:")


class _Sammler(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.elemente = []
        self.titel = ""
        self.h1 = 0
        self.lang = None
        self.viewport = False
        self.refresh = False
        self.offen = []
        self.ids = set()
        self.urls = []
        self.ereignisse = []
        self.stile = []
        self._im_titel = False
        self._im_stil = False

    def handle_starttag(self, tag, attrs):
        self._start(tag, attrs, leer=False)

    def handle_startendtag(self, tag, attrs):
        self._start(tag, attrs, leer=True)

    def _start(self, tag, attrs, leer):
        a = {}
        for name, wert in attrs:
            a[name.lower()] = wert or ""
        self.elemente.append(tag)
        if tag == "html":
            self.lang = a.get("lang")
        elif tag == "title" and not leer:
            self._im_titel = True
        elif tag == "h1":
            self.h1 += 1
        elif tag == "style" and not leer:
            self._im_stil = True
        elif tag == "meta":
            if a.get("name", "").lower() == "viewport" and "width=device-width" in a.get("content", "").replace(
                    " ", "").lower():
                self.viewport = True
            if a.get("http-equiv", "").lower() == "refresh":
                self.refresh = True
        if "data-offen" in a and a["data-offen"].strip():
            self.offen.append(" ".join(a["data-offen"].split()))
        if a.get("id"):
            self.ids.add(a["id"])
        for name, wert in a.items():
            if name.startswith("on"):
                self.ereignisse.append("%s %s" % (tag, name))
            if name in URL_ATTRIBUTE:
                self.urls.append((tag, name, wert))
            if name == "style":
                self.stile.append(wert)

    def handle_endtag(self, tag):
        if tag == "title":
            self._im_titel = False
        elif tag == "style":
            self._im_stil = False

    def handle_data(self, data):
        if self._im_titel:
            self.titel += data
        if self._im_stil:
            self.stile.append(data)


def _url_erlaubt(attribut, wert):
    v = re.sub(r"[\x00-\x20]", "", wert).lower()
    if not v or v.startswith("#"):
        return True
    if v.startswith("//"):
        return False
    if v.startswith(ERLAUBTE_SCHEMATA):
        return attribut == "href"
    if v.startswith("data:image/") and attribut == "src":
        return True
    return not _SCHEMA.match(v)  # relativer Verweis auf eine Datei daneben


def _externe(sammler):
    funde = []
    for tag, attribut, wert in sammler.urls:
        werte = [w.strip().split(" ")[0] for w in wert.split(",")] if attribut == "srcset" else [wert]
        for w in werte:
            if not _url_erlaubt(attribut, w):
                funde.append("%s %s=%s" % (tag, attribut, w[:80]))
    for stil in sammler.stile:
        klein = stil.lower()
        if "@import" in klein or "expression(" in klein:
            funde.append("CSS lädt fremde Inhalte (@import/expression)")
        for ziel in re.findall(r"url\(\s*['\"]?([^'\")]*)", klein):
            if not ziel.strip().startswith("data:"):
                funde.append("CSS url(%s)" % ziel[:80])
    if sammler.refresh:
        funde.append("meta refresh (automatische Weiterleitung)")
    return funde


def _eingaben_texte(eingaben):
    texte = []
    if isinstance(eingaben, dict):
        for wert in eingaben.values():
            texte += _eingaben_texte(wert)
    elif isinstance(eingaben, list):
        for wert in eingaben[:100]:
            texte += _eingaben_texte(wert)
    elif isinstance(eingaben, str):
        texte.append(eingaben)
    return texte


def pruefen(html_text, eingaben=None, groesse=None, kontakt_pflicht=True):
    """Prüft HTML-Text. Rückgabe: {pruefungen:[{name, ok, hinweis}], bestanden, offene_punkte}."""
    pruefungen = []

    def pruefung(name, ok, hinweis=""):
        pruefungen.append({"name": name, "ok": bool(ok), "hinweis": hinweis})

    s = _Sammler()
    try:
        s.feed(html_text)
        s.close()
    except Exception as fehler:  # unlesbares HTML ist ein Mangel, kein Absturz
        pruefung("HTML lesbar", False, str(fehler)[:200])

    skript = [e for e in s.elemente if e == "script"]
    js_url = [u for u in s.urls if re.sub(r"[\x00-\x20]", "", u[2]).lower().startswith(("javascript:", "vbscript:"))]
    roh = bool(re.search(r"<\s*script", html_text, re.I))
    pruefung("Kein JavaScript", not (skript or s.ereignisse or js_url or roh),
             "; ".join(["<script> gefunden"] * bool(skript or roh) + s.ereignisse[:5] +
                       ["javascript:-Verweis"] * bool(js_url)))

    externe = _externe(s)
    pruefung("Keine externen Ressourcen", not externe, "; ".join(externe[:5]))

    fremd = sorted({e for e in s.elemente if e not in ERLAUBTE_ELEMENTE})
    pruefung("Nur erwartete HTML-Elemente", not fremd, ", ".join("<%s>" % e for e in fremd[:10]))

    pruefung("Mobil-Ansicht (viewport)", s.viewport, "" if s.viewport else "meta viewport fehlt")
    pruefung('Sprache Deutsch (lang="de")', (s.lang or "").lower().startswith("de"),
             "" if s.lang else "lang-Angabe fehlt")
    pruefung("Seitentitel", bool(s.titel.strip()), "" if s.titel.strip() else "<title> fehlt oder leer")
    pruefung("Genau eine Hauptüberschrift (h1)", s.h1 == 1, "gefunden: %d" % s.h1)

    groesse = len(html_text.encode("utf-8")) if groesse is None else groesse
    pruefung("Dateigröße unter 200 KB", groesse < MAX_BYTES, "%d KB" % (groesse // 1024))

    pruefung("Impressum-Abschnitt vorhanden", "impressum" in s.ids, "" if "impressum" in s.ids else "fehlt")
    pruefung("Datenschutz-Abschnitt vorhanden", "datenschutz" in s.ids, "" if "datenschutz" in s.ids else "fehlt")

    if eingaben is None:
        pruefung("Eingaben sicher eingebaut (escaped)", True, "kein Abgleich – Eingaben nicht bekannt")
    else:
        roh_eingaben = [t for t in _eingaben_texte(eingaben) if len(t) >= 2 and any(z in t for z in '<>"')]
        offen_drin = [t[:40] for t in roh_eingaben if t in html_text]
        pruefung("Eingaben sicher eingebaut (escaped)", not offen_drin,
                 "unescaped: " + "; ".join(offen_drin[:3]) if offen_drin else "")

    kontakt = [u for u in s.urls if u[0] == "a" and u[1] == "href"
               and re.sub(r"[\x00-\x20]", "", u[2]).lower().startswith(ERLAUBTE_SCHEMATA)]
    if kontakt_pflicht:
        pruefung("Kontaktweg vorhanden (Telefon oder E-Mail)", bool(kontakt),
                 "" if kontakt else "kein tel:- oder mailto:-Verweis")

    offene = []
    for punkt in s.offen:
        if punkt not in offene:
            offene.append(punkt)
    return {"pruefungen": pruefungen, "bestanden": all(p["ok"] for p in pruefungen), "offene_punkte": offene}


def datei_pruefen(pfad, eingaben=None, kontakt_pflicht=True):
    with open(pfad, "rb") as f:
        roh = f.read(MAX_BYTES * 5)
    try:
        text = roh.decode("utf-8")
    except UnicodeDecodeError:
        return {"pruefungen": [{"name": "Zeichensatz UTF-8", "ok": False, "hinweis": "Datei ist kein UTF-8"}],
                "bestanden": False, "offene_punkte": []}
    return pruefen(text, eingaben, groesse=len(roh), kontakt_pflicht=kontakt_pflicht)


def zusammenfassen(ergebnisse):
    """Mehrere Datei-Ergebnisse {dateiname: ergebnis} zu einem Gesamtergebnis zusammenfassen."""
    pruefungen, offene = [], []
    for datei, e in ergebnisse.items():
        for p in e["pruefungen"]:
            pruefungen.append(dict(p, datei=datei))
        for punkt in e["offene_punkte"]:
            eintrag = punkt if len(ergebnisse) == 1 else "%s: %s" % (datei, punkt)
            if eintrag not in offene:
                offene.append(eintrag)
    return {"pruefungen": pruefungen, "bestanden": all(e["bestanden"] for e in ergebnisse.values()),
            "offene_punkte": offene, "dateien": ergebnisse}
