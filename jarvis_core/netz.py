# -*- coding: utf-8 -*-
"""Netz - JARVIS' eigener Zugang zum Internet, ohne fremde KI.

Suchen (über die HTML-Suche von DuckDuckGo, ohne Konto und ohne Schlüssel) und öffentliche Seiten lesen. Alles, was
von hier kommt, ist eine unvertrauenswürdige Außenquelle: Daten, keine Anweisungen.

Schutz:

* nur http und https, nur die Standard-Ports, keine Zugangsdaten in der Adresse;
* nur öffentliche Adressen: Der Rechnername wird aufgelöst, und JEDE gefundene Adresse muss öffentlich sein (kein
  localhost, kein Heimnetz, kein Gerät im WLAN). Verbunden wird genau mit der geprüften Adresse;
* Weiterleitungen werden einzeln geprüft (höchstens 4);
* höchstens 600 KB und 15 Sekunden je Seite, nur Text (HTML, Text, JSON, XML);
* JARVIS meldet sich ehrlich mit eigenem Namen. Lehnt eine Seite den Zugriff ab, wird nichts umgangen.
"""

import html
import html.parser
import http.client
import ipaddress
import re
import socket
import ssl
import threading
import time
import urllib.parse

KENNUNG = "JARVIS/1 (persoenlicher Assistent; liest oeffentliche Seiten im Auftrag seines Nutzers)"
MAX_BYTES = 600000
ZEIT = 15
MAX_UMLEITUNGEN = 4
SUCHE = "https://html.duckduckgo.com/html/"
SUCH_PAUSE = 3.0  # Sekunden zwischen zwei Suchen - JARVIS fragt höflich, nicht im Dauerfeuer
TEXT_ARTEN = ("text/html", "text/plain", "application/xhtml+xml", "application/json", "application/xml", "text/xml")
UMLEITUNG = (301, 302, 303, 307, 308)

_RECHNER = re.compile(r"^[a-z0-9]([a-z0-9.\-]{0,251}[a-z0-9])?$")
_letzte_suche = [0.0]
_such_sperre = threading.Lock()


class NetzFehler(Exception):
    """Etwas im Internet hat nicht geklappt - der Text sagt dem Nutzer, was."""


def adresse_pruefen(url):
    """Zerlegt und prüft eine Adresse. Gibt (schema, rechner, port, pfad) zurück; wirft NetzFehler."""
    try:
        teile = urllib.parse.urlsplit((url or "").strip())
        port = teile.port
    except ValueError:
        raise NetzFehler("Das ist keine gültige Internetadresse.") from None
    if teile.scheme not in ("http", "https"):
        raise NetzFehler("Geöffnet werden nur Adressen mit http:// oder https://.")
    if teile.username or teile.password:
        raise NetzFehler("Adressen mit Zugangsdaten werden nicht geöffnet.")
    rechner = (teile.hostname or "").rstrip(".").lower()
    if not rechner:
        raise NetzFehler("Die Adresse hat keinen Rechnernamen.")
    try:
        rechner = rechner.encode("idna").decode("ascii")  # Umlaute im Namen (z. B. köln.de) in die technische Form
    except UnicodeError:
        raise NetzFehler("Der Rechnername in der Adresse ist ungültig.") from None
    if not _RECHNER.match(rechner):
        raise NetzFehler("Der Rechnername in der Adresse ist ungültig.")
    standard = 443 if teile.scheme == "https" else 80
    if port not in (None, standard):
        raise NetzFehler("Geöffnet werden nur die üblichen Ports (80 und 443).")
    pfad = teile.path or "/"
    if teile.query:
        pfad += "?" + teile.query
    return teile.scheme, rechner, standard, pfad


def oeffentlich(adresse):
    """Ist das eine öffentliche Adresse im Internet (nicht localhost, Heimnetz, Geräte-Adressen)?"""
    try:
        ip = ipaddress.ip_address(adresse)
    except ValueError:
        return False
    if ip.version == 6 and ip.ipv4_mapped is not None:
        ip = ip.ipv4_mapped
    return bool(ip.is_global) and not ip.is_multicast


def aufloesen(rechner, port):
    """Alle Adressen eines Rechners - jede einzelne muss öffentlich sein."""
    try:
        infos = socket.getaddrinfo(rechner, port, type=socket.SOCK_STREAM)
    except (socket.gaierror, UnicodeError, OSError):
        raise NetzFehler("Der Rechner %s wurde nicht gefunden (Internet an?)." % rechner) from None
    adressen = []
    for info in infos:
        if info[4][0] not in adressen:
            adressen.append(info[4][0])
    if not adressen or not all(oeffentlich(a) for a in adressen):
        raise NetzFehler("%s ist keine öffentliche Adresse im Internet. JARVIS öffnet nichts im eigenen Netz." % rechner)
    return adressen


def _einmal(url, daten=None):
    """Genau eine Anfrage, ohne Weiterleitungen. Gibt (Status, Kopfzeilen, Inhalt, abgeschnitten) zurück."""
    schema, rechner, port, pfad = adresse_pruefen(url)
    sock, grund = None, None
    for ip in aufloesen(rechner, port):
        try:
            sock = socket.create_connection((ip, port), timeout=ZEIT)
            if schema == "https":
                sock = ssl.create_default_context().wrap_socket(sock, server_hostname=rechner)
            break
        except (OSError, ssl.SSLError) as fehler:
            sock, grund = None, fehler
    if sock is None:
        raise NetzFehler("Keine Verbindung zu %s (%s)." % (rechner, grund))
    verbindung = http.client.HTTPConnection(rechner, port, timeout=ZEIT)
    verbindung.sock = sock  # genau die geprüfte Adresse, kein zweites Auflösen
    kopf = {"Host": rechner, "User-Agent": KENNUNG, "Accept": "text/html,text/plain,application/json;q=0.9,*/*;q=0.1",
            "Accept-Language": "de,en;q=0.7", "Accept-Encoding": "identity", "Connection": "close"}
    if daten is not None:
        kopf["Content-Type"] = "application/x-www-form-urlencoded"
    try:
        verbindung.request("POST" if daten is not None else "GET", pfad, body=daten, headers=kopf)
        antwort = verbindung.getresponse()
        roh = antwort.read(MAX_BYTES + 1)
        return antwort.status, {k.lower(): v for k, v in antwort.getheaders()}, roh[:MAX_BYTES], len(roh) > MAX_BYTES
    except (OSError, http.client.HTTPException) as fehler:
        raise NetzFehler("%s hat nicht geantwortet (%s)." % (rechner, type(fehler).__name__)) from None
    finally:
        verbindung.close()


def holen(url, daten=None):
    """Eine Seite holen, Weiterleitungen einzeln geprüft. Gibt (endgültige Adresse, Art, Text, abgeschnitten) zurück."""
    for _ in range(MAX_UMLEITUNGEN + 1):
        status, kopf, roh, abgeschnitten = _einmal(url, daten)
        if status in UMLEITUNG and kopf.get("location"):
            url, daten = urllib.parse.urljoin(url, kopf["location"]), None
            continue
        rechner = adresse_pruefen(url)[1]
        if status in (401, 403, 429):
            raise NetzFehler("%s lehnt den Zugriff ab (Status %d). JARVIS umgeht keine Sperren." % (rechner, status))
        if status >= 400:
            raise NetzFehler("%s antwortet mit einem Fehler (Status %d)." % (rechner, status))
        art = (kopf.get("content-type") or "").split(";")[0].strip().lower()
        if art and art not in TEXT_ARTEN:
            raise NetzFehler("Das ist keine Textseite (%s). Lesen kann JARVIS nur Text - PDFs und Bilder nicht." % art)
        return url, art or "text/html", _dekodieren(roh, kopf.get("content-type") or ""), abgeschnitten
    raise NetzFehler("Zu viele Weiterleitungen.")


def _dekodieren(roh, inhaltsart):
    zeichensatz = re.search(r"charset=([\w.\-]+)", inhaltsart, re.IGNORECASE)
    if not zeichensatz:
        zeichensatz = re.search(rb"<meta[^>]+charset=[\"']?([\w.\-]+)", roh[:4000], re.IGNORECASE)
    name = zeichensatz.group(1) if zeichensatz else "utf-8"
    if isinstance(name, bytes):
        name = name.decode("ascii", "replace")
    try:
        return roh.decode(name, "replace")
    except LookupError:
        return roh.decode("utf-8", "replace")


class _Leser(html.parser.HTMLParser):
    """HTML -> lesbarer Text: ohne Skripte, Stile, Menüs und Fußzeilen."""

    WEG = ("script", "style", "noscript", "svg", "template", "nav", "footer", "aside", "form", "iframe", "head")
    BLOCK = ("p", "div", "br", "li", "tr", "h1", "h2", "h3", "h4", "section", "article", "table", "ul", "ol", "dd", "dt")

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.teile, self.titel, self._weg, self._im_titel = [], "", 0, False

    def handle_starttag(self, tag, attrs):
        if tag == "title":
            self._im_titel = True
        if tag in self.WEG:
            self._weg += 1
        elif tag in self.BLOCK:
            self.teile.append("\n")

    def handle_endtag(self, tag):
        if tag == "title":
            self._im_titel = False
        if tag in self.WEG and self._weg:
            self._weg -= 1
        elif tag in self.BLOCK:
            self.teile.append("\n")

    def handle_data(self, data):
        if self._im_titel:
            self.titel += data
        elif not self._weg:
            self.teile.append(data)


def text_aus_html(quelltext):
    """Gibt (Titel, Text) zurück."""
    leser = _Leser()
    try:
        leser.feed(quelltext)
        leser.close()
    except Exception:  # noqa: BLE001, S110 - kaputtes HTML: nehmen, was bis dahin gelesen wurde
        pass
    zeilen = [" ".join(z.split()) for z in "".join(leser.teile).split("\n")]
    return " ".join(leser.titel.split())[:200], "\n".join(z for z in zeilen if z)


def seite_lesen(url, maximal=6000):
    """Eine öffentliche Seite als Text. Gibt {"url", "titel", "text", "gekuerzt"} zurück; wirft NetzFehler."""
    ziel, art, text, abgeschnitten = holen(url)
    titel = ""
    if art in ("text/html", "application/xhtml+xml"):
        titel, text = text_aus_html(text)
    if not text.strip():
        raise NetzFehler("Die Seite enthält keinen lesbaren Text (vielleicht baut sie sich erst im Browser auf).")
    return {"url": ziel, "titel": titel, "text": text[:maximal], "gekuerzt": abgeschnitten or len(text) > maximal}


class _Treffer(html.parser.HTMLParser):
    """Liest die Trefferliste der HTML-Suche: Titel, Adresse, Auszug."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.treffer, self._feld = [], None

    def handle_starttag(self, tag, attrs):
        if tag != "a":
            return
        a = dict(attrs)
        klasse = (a.get("class") or "").split()
        if "result__a" in klasse:
            self.treffer.append({"titel": "", "url": _ziel(a.get("href") or ""), "auszug": ""})
            self._feld = "titel"
        elif "result__snippet" in klasse and self.treffer:
            self._feld = "auszug"

    def handle_endtag(self, tag):
        if tag == "a":
            self._feld = None

    def handle_data(self, data):
        if self._feld and self.treffer:
            self.treffer[-1][self._feld] += data


def _ziel(verweis):
    """Die Suche verpackt die echte Adresse in ?uddg=…; hier wird sie ausgepackt."""
    verweis = html.unescape(verweis)
    if verweis.startswith("//"):
        verweis = "https:" + verweis
    teile = urllib.parse.urlsplit(verweis)
    if teile.netloc.endswith("duckduckgo.com") and teile.path.startswith("/l/"):
        return (urllib.parse.parse_qs(teile.query).get("uddg") or [""])[0]
    return verweis


def treffer_lesen(quelltext, anzahl=5):
    leser = _Treffer()
    try:
        leser.feed(quelltext)
    except Exception:  # noqa: BLE001, S110 - kaputtes HTML: nehmen, was bis dahin gelesen wurde
        pass
    liste, gesehen = [], set()
    for t in leser.treffer:
        url = t["url"].strip()
        if not url.startswith(("http://", "https://")) or url in gesehen:
            continue
        gesehen.add(url)
        liste.append({"titel": " ".join(t["titel"].split())[:160], "url": url[:500], "auszug": " ".join(t["auszug"].split())[:320]})
    return liste[:anzahl]


def suchen(frage, anzahl=5):
    """Websuche. Gibt [{"titel", "url", "auszug"}] zurück; wirft NetzFehler."""
    frage = " ".join((frage or "").split())[:300]
    if not frage:
        raise NetzFehler("Die Suchfrage fehlt.")
    with _such_sperre:
        warten = SUCH_PAUSE - (time.time() - _letzte_suche[0])
        if warten > 0:
            time.sleep(min(warten, SUCH_PAUSE))
        _letzte_suche[0] = time.time()
    _ziel_adresse, _art, text, _ab = holen(SUCHE + "?" + urllib.parse.urlencode({"q": frage, "kl": "de-de"}))
    treffer = treffer_lesen(text, anzahl)
    if not treffer and ("anomaly" in text or "captcha" in text.lower()):
        raise NetzFehler("Die Suchmaschine lehnt die automatische Suche gerade ab. Später noch einmal versuchen oder "
                         "eine Adresse direkt mit \"webseite_lesen\" öffnen.")
    return treffer
