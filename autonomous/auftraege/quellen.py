# -*- coding: utf-8 -*-
"""Drei öffentliche Quellen für Ausschreibungen – jeweils Abruf und Auslesen.

a) TED – offizielle Schnittstelle des EU-Amtsblatts (JSON), EU-weite Ausschreibungen.
b) service.bund.de – offizieller RSS-Feed der Ausschreibungen von Bund, Ländern und Kommunen.
c) Vergabemarktplatz NRW – öffentliche Startseite mit den neuesten Bekanntmachungen (HTML-Tabelle).

Alle Adapter liefern normierte Einträge:
{quelle, extern_id, titel, vergabestelle, ort, plz, region, frist, veroeffentlicht, verfahren, link, cpv}

Fremdinhalte werden nur gelesen, gesäubert und in der Länge begrenzt – nie ausgeführt.
"""

import datetime
import email.utils
import html.parser
import json
import re
import xml.etree.ElementTree as ET
from urllib.parse import quote, urlsplit, urlunsplit

from . import text
from ..berechtigungen import url_erlaubt

TED_URL = "https://api.ted.europa.eu/v3/notices/search"
TED_DETAIL = "https://ted.europa.eu/de/notice/-/detail/%s"
# CPV-Codes für Reinigungsleistungen (Reinigungsdienste, Gebäude-, Fenster-, Büro- und sonstige Reinigung)
TED_CPV = ("90910000", "90911000", "90911200", "90911300", "90919200", "90919000")
TED_FELDER = ["publication-number", "notice-title", "buyer-name", "buyer-city", "place-of-performance",
              "deadline-receipt-tender-date-lot", "classification-cpv", "publication-date", "notice-type"]
TED_MAX_SEITEN = 3
TED_SEITE = 100

BUND_BASIS = "https://www.service.bund.de/Content/DE/Ausschreibungen/Suche/Formular.html"
BUND_MAX_BEGRIFFE = 3

EVERGABE_URL = "https://www.evergabe.nrw.de/VMPCenter/company/welcome.do"
EVERGABE_ARTEN = {"ausschreibung": "Ausschreibung", "tnw": "Teilnahmewettbewerb",
                  "teilnahmewettbewerb": "Teilnahmewettbewerb"}

# NRW auf NUTS-2-Ebene (Regierungsbezirke)
NUTS_NAMEN = {"DEA": "Nordrhein-Westfalen", "DEA1": "Regierungsbezirk Düsseldorf", "DEA2": "Regierungsbezirk Köln",
              "DEA3": "Regierungsbezirk Münster", "DEA4": "Regierungsbezirk Detmold",
              "DEA5": "Regierungsbezirk Arnsberg"}

_DATUM_DE = re.compile(r"(\d{2})\.(\d{2})\.(\d{4})(?:\D+(\d{2}):(\d{2}))?")


class QuellenFehler(Exception):
    pass


# ---------------------------------------------------------------- Hilfen
def _datum_de(wert):
    """'10.12.2026 um 23:59 Uhr' oder '08.12.2026 09:15' → '2026-12-10 23:59' bzw. '2026-12-10'."""
    m = _DATUM_DE.search(str(wert or ""))
    if not m:
        return None
    tag, monat, jahr, std, minute = m.groups()
    try:
        datum = datetime.date(int(jahr), int(monat), int(tag)).isoformat()
    except ValueError:
        return None
    if std is not None and int(std) < 24 and int(minute) < 60:
        return "%s %s:%s" % (datum, std, minute)
    return datum


def _datum_iso(wert):
    """'2026-12-01+01:00' → '2026-12-01'."""
    m = re.match(r"(\d{4})-(\d{2})-(\d{2})", str(wert or ""))
    if not m:
        return None
    try:
        return datetime.date(int(m.group(1)), int(m.group(2)), int(m.group(3))).isoformat()
    except ValueError:
        return None


def _link_saeubern(url):
    """Fragment (#track=…) und ;jsessionid=… entfernen; nur freigegebene https-Adressen."""
    if not url:
        return None
    try:
        teile = urlsplit(str(url).strip())
    except ValueError:
        return None
    pfad = re.sub(r";jsessionid=[^/?#]*", "", teile.path, flags=re.I)
    sauber = urlunsplit((teile.scheme, teile.netloc, pfad, teile.query, ""))
    return sauber if url_erlaubt(sauber) and len(sauber) <= 500 else None


def _sprache(wert):
    """Mehrsprachige TED-Felder: deutsch bevorzugt, sonst mehrsprachig/englisch/irgendeine."""
    if isinstance(wert, dict):
        for schluessel in ("deu", "mul", "eng"):
            if schluessel in wert:
                return _sprache(wert[schluessel])
        for v in wert.values():
            return _sprache(v)
        return None
    if isinstance(wert, list):
        return _sprache(wert[0]) if wert else None
    return None if wert is None else str(wert)


def eintrag(quelle, extern_id, titel, link, vergabestelle=None, ort=None, plz=None, region=None, frist=None,
            veroeffentlicht=None, verfahren=None, cpv=None):
    titel = text(titel, 300)
    extern_id = text(extern_id, 120)
    if not titel or not extern_id or not link:
        return None
    return {"quelle": quelle, "extern_id": extern_id, "titel": titel, "vergabestelle": text(vergabestelle, 200),
            "ort": text(ort, 120), "plz": plz if plz and re.fullmatch(r"\d{5}", plz) else None,
            "region": text(region, 120), "frist": frist, "veroeffentlicht": veroeffentlicht,
            "verfahren": text(verfahren, 80), "link": link,
            "cpv": [c for c in (cpv or []) if re.fullmatch(r"\d{8}", str(c))][:20]}


# ---------------------------------------------------------------- a) TED
def ted_anfrage(region_nuts, stichtag, seite=1):
    nuts = [n for n in (region_nuts or ["DEA"]) if re.fullmatch(r"DE[A-Z0-9]{0,3}", n)] or ["DEA"]
    abfrage = ("classification-cpv IN (%s) AND place-of-performance IN (%s) AND "
               "deadline-receipt-tender-date-lot>=%s" % (" ".join(TED_CPV), " ".join(nuts),
                                                         stichtag.strftime("%Y%m%d")))
    koerper = {"query": abfrage, "fields": TED_FELDER, "limit": TED_SEITE, "page": int(seite)}
    return TED_URL, json.dumps(koerper).encode("utf-8")


def _nuts_beschreibung(codes):
    nrw = [c for c in codes if c.startswith("DEA")]
    if not nrw:
        return ", ".join(codes[:3]) or None
    teile = []
    for c in nrw[:4]:
        name = NUTS_NAMEN.get(c[:4]) or NUTS_NAMEN.get(c[:3])
        teile.append("%s (%s)" % (name, c) if name else c)
    return "NRW: " + "; ".join(dict.fromkeys(teile))


def ted_parsen(daten):
    try:
        d = json.loads(daten.decode("utf-8") if isinstance(daten, bytes) else daten)
    except (ValueError, UnicodeDecodeError):
        raise QuellenFehler("TED: Antwort ist kein gültiges JSON")
    if not isinstance(d, dict) or not isinstance(d.get("notices"), list):
        raise QuellenFehler("TED: unerwartetes Antwortformat")
    ergebnis = []
    for n in d["notices"][:TED_SEITE * TED_MAX_SEITEN]:
        if not isinstance(n, dict):
            continue
        nr = str(n.get("publication-number") or "")
        if not re.fullmatch(r"\d{1,9}-\d{4}", nr):
            continue
        fristen = sorted(f for f in (_datum_iso(x) for x in (n.get("deadline-receipt-tender-date-lot") or [])) if f)
        orte = n.get("place-of-performance") or []
        codes = list(dict.fromkeys(str(c) for c in orte if isinstance(c, str) and c != "DEU"))
        stadt = _sprache(n.get("buyer-city"))
        stelle = _sprache(n.get("buyer-name"))
        if stelle and stadt:
            stelle = "%s (%s)" % (stelle, stadt)
        art = str(n.get("notice-type") or "")
        verfahren = {"cn-standard": "EU-weite Ausschreibung", "cn-social": "EU-weite Ausschreibung (soziale Dienste)",
                     "cn-desg": "EU-weiter Wettbewerb"}.get(art, "EU-Bekanntmachung (%s)" % art if art else None)
        e = eintrag("ted", nr, _sprache(n.get("notice-title")), _link_saeubern(TED_DETAIL % nr),
                    vergabestelle=stelle, region=_nuts_beschreibung(codes), frist=fristen[0] if fristen else None,
                    veroeffentlicht=_datum_iso(n.get("publication-date")), verfahren=verfahren,
                    cpv=list(dict.fromkeys(n.get("classification-cpv") or [])))
        if e:
            e["nuts"] = codes[:10]
            ergebnis.append(e)
    return ergebnis, int(d.get("totalNoticeCount") or 0)


# ---------------------------------------------------------------- b) service.bund.de
def bund_urls(suchbegriffe):
    urls = []
    for begriff in list(suchbegriffe or [])[:BUND_MAX_BEGRIFFE]:
        urls.append("%s?nn=4641482&resultsPerPage=100&templateQueryString=%s&sortOrder=dateOfIssue_dt+desc"
                    "&jobsrss=true" % (BUND_BASIS, quote(str(begriff))))
    return urls


class _HtmlText(html.parser.HTMLParser):
    """Macht aus HTML-Schnipseln Text; <br> und Blockelemente werden zu Zeilenumbrüchen."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.teile = []

    def handle_starttag(self, tag, attrs):
        if tag in ("br", "p", "div", "li", "tr"):
            self.teile.append("\n")

    def handle_data(self, data):
        self.teile.append(data)

    def ergebnis(self):
        return [" ".join(z.split()) for z in "".join(self.teile).split("\n") if z.strip()]


def _html_zeilen(schnipsel):
    p = _HtmlText()
    p.feed(schnipsel or "")
    p.close()
    return p.ergebnis()


def bund_parsen(daten):
    # Erst streng als UTF-8 lesen (der Feed ist UTF-8). Andere Kodierungen (z. B. UTF-16) werden abgelehnt –
    # sonst ließe sich eine DTD an der Prüfung vorbei schmuggeln, weil diese dann nur auf die Rohbytes schaut.
    if isinstance(daten, bytes):
        try:
            text = daten.decode("utf-8")
        except UnicodeDecodeError:
            raise QuellenFehler("service.bund.de: Antwort ist kein gültiges UTF-8 – abgelehnt")
    else:
        text = str(daten)
    text = text.lstrip("﻿")
    # Steuerzeichen sind in XML 1.0 verboten. Nullbytes ließen sonst UTF-16 (ohne BOM) als „gültiges UTF-8“
    # durch – der Parser würde es dann selbst als UTF-16 erkennen und eine versteckte DTD auswerten.
    if re.search(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", text):
        raise QuellenFehler("service.bund.de: Antwort enthält Steuerzeichen – abgelehnt")
    oben = text.upper()
    if "<!DOCTYPE" in oben or "<!ENTITY" in oben:
        raise QuellenFehler("service.bund.de: Antwort enthält DTD/Entitäten – abgelehnt")
    try:
        # Als Text übergeben: der Parser ignoriert dann eine abweichende Kodierungsangabe im XML-Kopf.
        wurzel = ET.fromstring(text)
    except ET.ParseError:
        raise QuellenFehler("service.bund.de: Antwort ist kein gültiger RSS-Feed")
    ergebnis = []
    for item in wurzel.iter("item"):
        link = _link_saeubern(item.findtext("link"))
        if not link:
            continue
        m = re.search(r"/IMPORTE/Ausschreibungen/(.+?)\.html", link)
        extern_id = m.group(1) if m else urlsplit(link).path
        felder = {}
        for zeile in _html_zeilen(item.findtext("description") or ""):
            name, _, wert = zeile.partition(":")
            if wert:
                felder.setdefault(name.strip().lower(), wert.strip())
        erfuellungsort = felder.get("erfüllungsort") or ""
        mo = re.match(r"(\d{5})\s+(.*)", erfuellungsort)
        plz, ort = (mo.group(1), mo.group(2)) if mo else (None, erfuellungsort or None)
        try:
            veroeffentlicht = email.utils.parsedate_to_datetime(item.findtext("pubDate") or "").date().isoformat()
        except (TypeError, ValueError, IndexError):
            veroeffentlicht = None
        e = eintrag("service_bund", extern_id, item.findtext("title"), link, vergabestelle=felder.get("vergabestelle"),
                    ort=ort, plz=plz, region=("PLZ-Bereich %s" % plz[:2]) if plz else None,
                    frist=_datum_de(felder.get("angebotsfrist")), veroeffentlicht=veroeffentlicht,
                    verfahren="Ausschreibung (service.bund.de)")
        if e:
            ergebnis.append(e)
    return ergebnis


# ---------------------------------------------------------------- c) Vergabemarktplatz NRW
class _Tabelle(html.parser.HTMLParser):
    """Sammelt Tabellenzeilen: je Zelle Text, abbr-Titel und Links."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.zeilen, self._zeile, self._zelle = [], None, None

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "tr":
            self._zeile = []
        elif tag == "td" and self._zeile is not None:
            self._zelle = {"text": [], "titel": [], "links": []}
            self._zeile.append(self._zelle)
        elif self._zelle is not None:
            if tag == "abbr" and a.get("title"):
                self._zelle["titel"].append(a["title"])
            elif tag == "a" and a.get("href"):
                self._zelle["links"].append(a["href"])
            elif tag == "br":
                self._zelle["text"].append(" | ")

    def handle_endtag(self, tag):
        if tag == "td":
            self._zelle = None
        elif tag == "tr" and self._zeile is not None:
            self.zeilen.append(self._zeile)
            self._zeile, self._zelle = None, None

    def handle_data(self, data):
        if self._zelle is not None:
            self._zelle["text"].append(data)


def evergabe_parsen(quelltext):
    p = _Tabelle()
    p.feed(quelltext or "")
    p.close()
    ergebnis = []
    for zeile in p.zeilen:
        if len(zeile) < 6:
            continue
        link = next((l for z in zeile for l in z["links"] if "projectForwarding.do" in l), None)
        if not link:
            continue
        m = re.search(r"[?&]pid=(\d{1,12})", link)
        link = _link_saeubern(link)
        if not m or not link:
            continue
        zellen = [" ".join("".join(z["text"]).split()) for z in zeile]
        typ = [t.strip() for t in zellen[3].split("|") if t.strip()]
        art_roh = typ[-1] if typ else ""
        art = EVERGABE_ARTEN.get(art_roh.lower())
        if not art:  # vergebene Aufträge, Vorinformationen usw. sind keine offenen Ausschreibungen
            continue
        frist = next((f for f in (_datum_de(t) for t in zeile[1]["titel"]) if f), None)
        veroeffentlicht = next((f[:10] for f in (_datum_de(t) for t in zeile[0]["titel"]) if f), None)
        verfahren = "%s – %s" % (typ[0], art) if len(typ) > 1 else art
        e = eintrag("evergabe_nrw", "pid-" + m.group(1), zellen[2], link, vergabestelle=zellen[4], region="NRW",
                    frist=frist, veroeffentlicht=veroeffentlicht, verfahren=verfahren)
        if e:
            ergebnis.append(e)
    return ergebnis


# ---------------------------------------------------------------- Abruf je Quelle
def holen(quelle, einstellungen, abrufer, pruefen, stichtag=None):
    """Ruft eine Quelle ab und liefert normierte Einträge.

    ``abrufer(url, methode=..., daten=..., kopf=...)`` liefert ein netz.Antwort-artiges Objekt.
    ``pruefen(url)`` wird VOR jedem Abruf aufgerufen (Supervisor) und wirft, wenn er nicht erlaubt ist."""
    stichtag = stichtag or datetime.date.today()
    if quelle == "ted":
        eintraege, seite, gesamt = [], 1, None
        while seite <= TED_MAX_SEITEN:
            url, koerper = ted_anfrage(einstellungen.get("region_nuts"), stichtag, seite)
            pruefen(url)
            antwort = abrufer(url, methode="POST", daten=koerper, kopf={"Content-Type": "application/json"})
            neu, gesamt = ted_parsen(antwort.daten)
            eintraege += neu
            if not neu or len(eintraege) >= gesamt:
                break
            seite += 1
        return eintraege
    if quelle == "service_bund":
        eintraege, gesehen = [], set()
        for url in bund_urls(einstellungen.get("suchbegriffe")):
            pruefen(url)
            for e in bund_parsen(abrufer(url).daten):
                if e["extern_id"] not in gesehen:
                    gesehen.add(e["extern_id"])
                    eintraege.append(e)
        return eintraege
    if quelle == "evergabe_nrw":
        pruefen(EVERGABE_URL)
        return evergabe_parsen(abrufer(EVERGABE_URL).text())
    raise QuellenFehler("Unbekannte Quelle: %s" % quelle)
