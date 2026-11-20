# -*- coding: utf-8 -*-
"""Qualitätsprüfung für erzeugte Seiten (Product-Agent).

Prüft eine HTML-Datei auf Sicherheit (kein JavaScript, keine externen Ressourcen, nur erwartete
Elemente, Eingaben escaped) und Grundqualität (Mobil-Ansicht, Sprache, Titel, Hauptüberschrift,
Größe, Kontaktweg, Impressum/Datenschutz). Offene Punkte (Platzhalter) werden aus den
``data-offen``-Markierungen der Seite gesammelt – sie sind keine Fehler, sondern Aufgaben für
den Inhaber.

Die Prüfung liest die Datei nur als Daten; Inhalte werden nie ausgeführt.
"""

import os
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


def pruefen(html_text, eingaben=None, groesse=None, kontakt_pflicht=True, seite=True):
    """Prüft HTML-Text. Rückgabe: {pruefungen:[{name, ok, hinweis}], bestanden, offene_punkte}.

    ``seite=False``: Arbeitsunterlage statt veröffentlichter Webseite – dann entfallen die Prüfungen auf
    Impressum- und Datenschutz-Abschnitt."""
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

    if seite:
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


def datei_pruefen(pfad, eingaben=None, kontakt_pflicht=True, seite=True):
    with open(pfad, "rb") as f:
        roh = f.read(MAX_BYTES * 5)
    try:
        text = roh.decode("utf-8")
    except UnicodeDecodeError:
        return {"pruefungen": [{"name": "Zeichensatz UTF-8", "ok": False, "hinweis": "Datei ist kein UTF-8"}],
                "bestanden": False, "offene_punkte": []}
    return pruefen(text, eingaben, groesse=len(roh), kontakt_pflicht=kontakt_pflicht, seite=seite)


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


# ---------------------------------------------------------------- Google-Profil-Paket
BESCHREIBUNG_MAX = 750  # Höchstlänge der Unternehmensbeschreibung im Google-Unternehmensprofil

_LINK = re.compile(r"(?i)(?:https?://|www\.)\S+|\b[a-z0-9][a-z0-9\-]*\.(?:de|com|net|org|eu|info|nrw|biz|io|"
                   r"example)\b")
# Telefonnummern beginnen mit + oder 0 (z. B. „0214 123456“, „+49 214 …“); Jahreszahlen oder Normen nicht
_TELEFON = re.compile(r"(?<![\w+])(?:\+\d|0)[\d \t/().\-]{4,}\d")
# Trenner, hinter denen ein Zusatz am Firmennamen hängt („Muster GmbH – Leverkusen“, „Muster | Reinigung“)
_TRENNER = re.compile(r"\s+[-/•·:]\s+|\s*[|–—]\s*|,\s+")
_LEER = {"br", "meta", "hr", "img", "input", "link", "area", "base", "col", "embed", "source", "track", "wbr"}


def enthaelt_link(text):
    return bool(_LINK.search(text or ""))


def enthaelt_telefon(text):
    for treffer in _TELEFON.finditer(text or ""):
        if len(re.sub(r"\D", "", treffer.group())) >= 6:
            return True
    return False


class _IdText(HTMLParser):
    """Sammelt den reinen Text von Elementen mit bestimmten ids."""

    def __init__(self, ids):
        super().__init__(convert_charrefs=True)
        self.ids = set(ids)
        self.texte = {}
        self._aktiv = None
        self._tiefe = 0

    def handle_starttag(self, tag, attrs):
        if tag in _LEER:
            return
        if self._aktiv:
            self._tiefe += 1
            return
        ident = dict(attrs).get("id")
        if ident in self.ids:
            self._aktiv, self._tiefe = ident, 1
            self.texte.setdefault(ident, "")

    def handle_startendtag(self, tag, attrs):
        pass  # selbstschließende Elemente enthalten keinen Text

    def handle_endtag(self, tag):
        if self._aktiv and tag not in _LEER:
            self._tiefe -= 1
            if self._tiefe == 0:
                self._aktiv = None

    def handle_data(self, data):
        if self._aktiv:
            self.texte[self._aktiv] += data


def name_zusaetze(name, eingaben=None):
    """Findet Orte oder Suchbegriffe, die hinter einem Trenner an den Firmennamen gehängt sind
    (oder „in/aus <Ort>“ am Ende). Rückgabe: Liste der Funde (leer = in Ordnung)."""
    name = " ".join(str(name or "").split())
    teile = [t for t in _TRENNER.split(name) if t.strip()]
    zusatz = " ".join(teile[1:]).lower()
    begriffe = set()
    ort = ""
    if isinstance(eingaben, dict):
        ort = str(eingaben.get("ort") or "").strip()
        for wert in [ort, eingaben.get("branche")] + list(eingaben.get("leistungen") or []):
            wert = str(wert or "").strip().lower()
            if len(wert) >= 3:
                begriffe.add(wert)
            begriffe.update(w for w in re.findall(r"[a-zäöüß]{5,}", wert))
    funde = sorted(b for b in begriffe if zusatz and b in zusatz)
    if ort and re.search(r"\s(?:in|aus|bei)\s+%s\s*$" % re.escape(ort.lower()), name.lower()):
        funde.append("„… %s“ am Ende" % ort)
    if zusatz and not funde and not isinstance(eingaben, dict):
        funde.append("Zusatz nach Trenner: %s" % zusatz[:40])
    return funde


def profil_entwurf_pruefen(html_text, eingaben=None):
    """Zusatzprüfungen für den Profil-Entwurf (Beschreibung und Unternehmensname)."""
    p = _IdText({"beschreibung-text", "firmenname"})
    try:
        p.feed(html_text)
        p.close()
    except Exception:
        pass
    text = " ".join(p.texte.get("beschreibung-text", "").split())
    name = " ".join(p.texte.get("firmenname", "").split())
    pruefungen = [
        {"name": "Beschreibung vorhanden", "ok": bool(text), "hinweis": "" if text else "fehlt"},
        {"name": "Beschreibung höchstens %d Zeichen" % BESCHREIBUNG_MAX, "ok": len(text) <= BESCHREIBUNG_MAX,
         "hinweis": "%d Zeichen" % len(text)},
        {"name": "Beschreibung ohne Links", "ok": not enthaelt_link(text),
         "hinweis": "Link gefunden" if enthaelt_link(text) else ""},
        {"name": "Beschreibung ohne Telefonnummern", "ok": not enthaelt_telefon(text),
         "hinweis": "Telefonnummer gefunden" if enthaelt_telefon(text) else ""},
    ]
    funde = name_zusaetze(name, eingaben) if name else []
    pruefungen.append({
        "name": "Firmenname ohne angehängte Orte oder Suchbegriffe", "ok": bool(name) and not funde,
        "hinweis": ("Warnung: Am Firmennamen hängt ein Zusatz (%s). Google verlangt den echten Namen ohne Orte oder "
                    "Suchbegriffe. Falls der Betrieb genau so heißt (z. B. laut Handelsregister), ist er zulässig."
                    % ", ".join(funde)) if funde else ("" if name else "Firmenname fehlt")})
    return pruefungen


def google_profil_pruefen(pfade, eingaben, namen):
    """Prüft die drei Unterlagen des Google-Profil-Pakets.

    pfade: {dateiname: pfad}; namen: {"entwurf": dateiname, "pruefliste": …, "uebergabe": …}.
    Arbeitsunterlagen sind keine Webseiten: ohne Impressum-/Datenschutz- und Kontaktpflicht, aber mit
    denselben Sicherheitsprüfungen (kein JavaScript, keine externen Ressourcen, Eingaben escaped)."""
    ergebnisse = {}
    for rolle in ("entwurf", "pruefliste", "uebergabe"):
        name = namen[rolle]
        pfad = pfade.get(name)
        if not pfad or not os.path.isfile(pfad):
            ergebnisse[name] = {"pruefungen": [{"name": "Datei vorhanden", "ok": False, "hinweis": "fehlt"}],
                                "bestanden": False, "offene_punkte": []}
            continue
        e = datei_pruefen(pfad, eingaben, kontakt_pflicht=False, seite=False)
        if rolle == "entwurf":
            with open(pfad, "rb") as f:
                text = f.read(MAX_BYTES * 5).decode("utf-8", "replace")
            e["pruefungen"] += profil_entwurf_pruefen(text, eingaben)
            e["bestanden"] = all(p["ok"] for p in e["pruefungen"])
        ergebnisse[name] = e
    fehlend = [namen[r] for r in ("entwurf", "pruefliste", "uebergabe")
               if not (pfade.get(namen[r]) and os.path.isfile(pfade[namen[r]]))]
    erster = ergebnisse[namen["entwurf"]]
    erster["pruefungen"].append({"name": "Paket vollständig (3 Unterlagen)", "ok": not fehlend,
                                 "hinweis": "fehlt: " + ", ".join(fehlend) if fehlend else ""})
    erster["bestanden"] = all(p["ok"] for p in erster["pruefungen"])
    return zusammenfassen(ergebnisse)
