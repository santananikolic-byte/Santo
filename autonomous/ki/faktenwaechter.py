# -*- coding: utf-8 -*-
"""Faktenwächter: prüft KI-Text gegen die Eingabe – im Code, nicht im Prompt.

Ein KI-Vorschlag wird verworfen, wenn er Angaben enthält, die NICHT in der Eingabe standen: Zahlen (auch als Wort,
z. B. „drei“), Telefonnummern, E-Mail- und Internetadressen, Preise und Geldbeträge, Firmennamen (mit Rechtsform wie
GmbH) und Personennamen nach „Herr“/„Frau“. Dazu kommen neue Zusagen (garantiert, kostenlos, verbindlich …),
fehlende Pflichtteile (Platzhalter, Abmeldehinweis) und – vor dem Aufruf – Anweisungen, die in Fremddaten stecken.

Grenzen (ehrlich): Firmennamen ohne Rechtsform und erfundene Aussagen ohne Zahl oder Namen erkennt er nicht. Darum
bleibt jeder KI-Text gekennzeichnet („KI-Entwurf – ungeprüft“) und der deterministische Text die Hauptausgabe."""

import re
import unicodedata

ARTEN = {"zahl": "Zahl", "telefon": "Telefonnummer", "email": "E-Mail-Adresse", "internetadresse": "Internetadresse",
         "preis": "Preis/Geldbetrag", "firma": "Firmenname", "person": "Personenname", "zusage": "Zusage",
         "fehlt": "fehlt", "geheimnis": "Muster wie Passwort/Schlüssel", "anweisung": "Anweisung in den Daten"}

_EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
_URL = re.compile(r"(?:https?://|www\.)[^\s<>\"'\])]+|\b[a-z0-9][a-z0-9-]*(?:\.[a-z0-9-]+)*\.(?:de|com|net|org|eu|info|"
                  r"nrw|koeln|ruhr|berlin|io|biz)\b(?:/[^\s<>\"'\])]*)?", re.I)
_TELEFON = re.compile(r"(?<![\w.,])(?:\+|0)\d[\d /()\-]{4,}\d")
_WAEHRUNG = re.compile(r"€|\beur\b|\beuro\b", re.I)
_GELD = re.compile(r"(\d+(?:[.,]\d+)*)\s*(?:€|eur\b|euro\b)|(?:€|\beur\b|\beuro\b)\s*(\d+(?:[.,]\d+)*)", re.I)
_ZAHL = re.compile(r"(?<!\w)\d+(?:[.,]\d+)*")
_AUFZAEHLUNG = re.compile(r"^[ \t]*\d{1,2}[.)](?=[ \t])", re.M)
_ZAHLWORT = re.compile(r"\b(zwei|drei|vier|fünf|sechs|sieben|acht|neun|zehn|elf|zwölf|zwanzig|dreißig|vierzig|fünfzig|"
                       r"hundert|tausend|dutzend|million(?:en)?|milliarde(?:n)?)(?:mal|fach)?\b")
_ZAHLWERT = {"zwei": "2", "drei": "3", "vier": "4", "fünf": "5", "sechs": "6", "sieben": "7", "acht": "8", "neun": "9",
             "zehn": "10", "elf": "11", "zwölf": "12", "zwanzig": "20", "dreißig": "30", "vierzig": "40",
             "fünfzig": "50", "hundert": "100", "tausend": "1000", "dutzend": "12", "million": "1000000",
             "millionen": "1000000", "milliarde": "1000000000", "milliarden": "1000000000"}
_RECHTSFORM = (r"(?:GmbH\s*&\s*Co\.?\s*KG|gGmbH|GmbH|mbH|AG|KGaA|KG|OHG|GbR|UG(?:\s*\(haftungsbeschränkt\))?|"
               r"e\.\s?K\.|e\.\s?V\.|SE|Ltd\.?|Inc\.?|LLC)")
_FIRMA = re.compile(r"((?:[A-ZÄÖÜ0-9][\w&.\-]*[ \t]+){1,4})(" + _RECHTSFORM + r")(?![\w])")
_FUELLWOERTER = {"der", "die", "das", "den", "dem", "des", "ein", "eine", "einer", "einem", "einen", "wir", "sie",
                 "ihr", "ihre", "ihrer", "ihrem", "ihren", "unser", "unsere", "bei", "mit", "für", "von", "vom", "zur",
                 "zum", "am", "im", "an", "auf", "aus", "und", "oder", "als", "wie", "firma", "sehr", "liebe", "hallo",
                 "guten", "tag", "herr", "frau", "auch", "nur", "schon", "jetzt", "heute"}
_PERSON = re.compile(r"\b(?:Herr|Herrn|Frau)[ \t]+(?:Dr\.[ \t]*|Prof\.[ \t]*)?([A-ZÄÖÜ][a-zäöüß]+(?:-[A-ZÄÖÜ][a-zäöüß]+)?)")
# (Muster, gleichwertige Formulierung in der Eingabe – dann ist es keine NEUE Zusage)
_ZUSAGEN = ((r"\bgarantier\w*", None), (r"\bzusicher\w*", None),
            (r"\bsichern\s+(?:ihnen\s+|euch\s+)?(?:\w+\s+){0,3}zu\b", None), (r"(?<!un)\bverbindlich\w*", None),
            (r"\bfestpreis\w*", r"\bfeste[nmrs]?\s+\w*preis"), (r"\bpauschalpreis\w*", None), (r"\brabatt\w*", None),
            (r"preisnachlass\w*", None), (r"\bkostenlos\w*", None), (r"\bkostenfrei\w*", None), (r"\bgratis\b", None),
            (r"\bumsonst\b", None), (r"\bsofort\s+(?:verfügbar|beginnen|starten|anfangen|loslegen|einsatzbereit)", None),
            (r"\bnoch\s+heute\b", None), (r"\bwir\s+bestätigen\b", None),
            (r"\b(?:termin|auftrag)\s+(?:ist\s+)?(?:bestätigt|zugesagt|fest)\b", None), (r"\bzugesagt\b", None),
            (r"\bgeht\s+klar\b", None), (r"\bkein\s+problem\b", None),
            # Leistungs- und Terminzusagen auf eine Kundenanfrage (echt beobachtet im Prüfstand)
            (r"\bja,?\s+wir\s+(?:\w+\s+){0,3}(?:können|reinigen|machen|übernehmen|kommen|bieten|erledigen|fangen|"
             r"beginnen|starten)\b", None),
            (r"\bja,?\s+(?:das\s+)?(?:machen|können|übernehmen|erledigen|schaffen)\s+wir\b", None),
            (r"\b(?:ist|sind|wäre|wären)\s+(?:(?!nicht\b|kein\w*\b)\w+\s+){0,2}(?:möglich|machbar)\b", None),
            (r"\bwir\s+sind\s+(?:\w+\s+){0,5}zuständig\b", None),
            (r"\bwir\s+können\s+(?:\w+\s+){0,6}(?:montag|dienstag|mittwoch|donnerstag|freitag|samstag|morgen|"
             r"beginnen|anfangen|starten|kommen|erledigen|übernehmen|reinigen)\b", None))
_ANWEISUNG = (r"\bignorier\w*\s+(?:\w+\s+){0,4}(?:anweisung|regel|befehl|instruktion|vorgabe)",
              r"\bvergiss\s+(?:\w+\s+){0,4}(?:anweisung|regel|vorgabe)",
              r"\bignore\s+(?:\w+\s+){0,4}(?:instruction|rule|prompt)", r"\bdisregard\s+(?:\w+\s+){0,4}(?:instruction|rule)",
              r"\b(?:system\s*-?\s*prompt|systemnachricht|system\s+message)\b",
              r"\bdu\s+bist\s+(?:jetzt|ab\s+sofort|nun|ab\s+jetzt)\b", r"\byou\s+are\s+now\b",
              r"\b(?:neue|geänderte)\s+(?:anweisung|rolle|aufgabe|regeln?)\s*:", r"<\s*/?\s*daten\s*>",
              r"\bantworte\s+(?:nur|ausschließlich|ab\s+jetzt)\b")


def _vorbereiten(text):
    t = unicodedata.normalize("NFKC", str(text or "")).replace("\u00ad", "")
    return re.sub(r"[‐‑‒–—―]", "-", t)


def _ohne_markdown(text):
    return re.sub(r"[*_`#]+", " ", text)


def _kompakt(text):
    return re.sub(r"\s+", "", _vorbereiten(text).lower())


def _int_text(ziffern):
    return str(int(ziffern)) if ziffern else ""


def _kanonisch(token):
    """„1.000“ und „1000“ → „1000“; „8,5“ → „8.5“; „1.250,50“ → „1250.5“; Datum „08.12.2026“ → „8.12.2026“."""
    gruppen = re.split(r"[.,]", token)
    if len(gruppen) == 1:
        return _int_text(gruppen[0])
    if all(len(g) == 3 for g in gruppen[1:]):                       # Tausendertrennung
        return _int_text("".join(gruppen))
    if all(len(g) == 3 for g in gruppen[1:-1]) and len(gruppen[-1]) != 3:   # Dezimalstellen
        nachkomma = gruppen[-1].rstrip("0")
        ganz = _int_text("".join(gruppen[:-1]))
        return ganz + ("." + nachkomma if nachkomma else "")
    return ".".join(_int_text(g) for g in gruppen)                 # Datum, Uhrzeit, Nummern


def _bekannte_zahlen(text):
    bekannt = set()
    for token in _ZAHL.findall(_AUFZAEHLUNG.sub(" ", text)):
        bekannt.add(_kanonisch(token))
        bekannt.update(_int_text(g) for g in re.split(r"[.,]", token) if g)
    for wort in _ZAHLWORT.findall(text.lower()):
        bekannt.add(_ZAHLWERT[wort])
    return bekannt


def _zahl_bekannt(token, bekannt):
    if _kanonisch(token) in bekannt:
        return True
    gruppen = [g for g in re.split(r"[.,]", token) if g]
    return len(gruppen) > 1 and all(_int_text(g) in bekannt for g in gruppen)


def _telefon_schluessel(text):
    ziffern = re.sub(r"\D", "", text)
    if text.strip().startswith("+"):
        ziffern = "0" + ziffern[3:] if ziffern.startswith("490") else ("0" + ziffern[2:] if ziffern.startswith("49")
                                                                       else ziffern)
    return ziffern


def _ist_telefon(treffer):
    return len(re.sub(r"\D", "", treffer)) >= 6


def _url_schluessel(url):
    u = url.lower().rstrip(".,;:!?/")
    u = re.sub(r"^https?://", "", u)
    return u[4:] if u.startswith("www.") else u


def befunde(ausgabe, eingabe):
    """Liste neuer Angaben in `ausgabe`, die nicht in `eingabe` stehen: [{"art": …, "wert": …}] – leer heißt ok."""
    aus, ein = _vorbereiten(ausgabe), _vorbereiten(eingabe)
    ein_klein = ein.lower()
    funde = []

    for m in _EMAIL.finditer(aus):
        if m.group(0).lower() not in ein_klein:
            funde.append(("email", m.group(0)))
    aus, ein = _EMAIL.sub(" ", aus), _EMAIL.sub(" ", ein)

    ein_urls = " ".join(_url_schluessel(m.group(0)) for m in _URL.finditer(ein))
    for m in _URL.finditer(aus):
        if _url_schluessel(m.group(0)) not in ein_urls:
            funde.append(("internetadresse", m.group(0)))
    aus, ein = _URL.sub(" ", aus), _URL.sub(" ", ein)

    bekannt = _bekannte_zahlen(_ohne_markdown(ein))   # vor dem Entfernen der Telefonnummern: Teile davon sind bekannt
    ein_tel = {_telefon_schluessel(t) for t in _TELEFON.findall(ein) if _ist_telefon(t)}
    for m in _TELEFON.finditer(aus):
        if _ist_telefon(m.group(0)) and _telefon_schluessel(m.group(0)) not in ein_tel:
            funde.append(("telefon", m.group(0).strip()))
    aus = _TELEFON.sub(lambda m: " " if _ist_telefon(m.group(0)) else m.group(0), aus)
    ein = _TELEFON.sub(lambda m: " " if _ist_telefon(m.group(0)) else m.group(0), ein)

    aus, ein = _ohne_markdown(aus), _ohne_markdown(ein)
    preis_gefunden = False
    for m in _GELD.finditer(aus):
        if not _zahl_bekannt(m.group(1) or m.group(2), bekannt):
            funde.append(("preis", m.group(0)))
            preis_gefunden = True
    aus = _GELD.sub(lambda m: m.group(0) if _zahl_bekannt(m.group(1) or m.group(2), bekannt) else " ", aus)
    waehrung = _WAEHRUNG.search(aus)
    if waehrung and not preis_gefunden and not _WAEHRUNG.search(ein):
        funde.append(("preis", waehrung.group(0)))

    for token in _ZAHL.findall(_AUFZAEHLUNG.sub(" ", aus)):
        if not _zahl_bekannt(token, bekannt):
            funde.append(("zahl", token))
    ein_woerter = set(re.findall(r"\w+", ein.lower()))
    for m in _ZAHLWORT.finditer(aus.lower()):
        if m.group(1) not in ein_woerter and _ZAHLWERT[m.group(1)] not in bekannt:
            funde.append(("zahl", m.group(0)))

    ein_kompakt = re.sub(r"\s+", " ", ein.lower())
    for m in _FIRMA.finditer(aus):
        woerter = m.group(1).split()
        while woerter and woerter[0].lower() in _FUELLWOERTER:
            woerter.pop(0)
        if not woerter:
            continue
        form = re.sub(r"\s+", " ", m.group(2).lower())
        if not any(" ".join(woerter[i:]).lower() + " " + form in ein_kompakt for i in range(len(woerter))):
            funde.append(("firma", " ".join(woerter) + " " + m.group(2)))

    for m in _PERSON.finditer(aus):
        if m.group(1).lower() not in ein_woerter and m.group(1).lower() not in ein.lower():
            funde.append(("person", m.group(0)))

    ergebnis, gesehen = [], set()
    for art, wert in funde:
        wert = re.sub(r"\s+", " ", wert).strip()[:60]
        if (art, wert) not in gesehen:
            gesehen.add((art, wert))
            ergebnis.append({"art": art, "wert": wert})
    return ergebnis


def neue_zusagen(ausgabe, eingabe):
    """Zusagen (garantiert, kostenlos, verbindlich, Termin bestätigt …), die nicht schon in der Eingabe standen."""
    aus, ein = _vorbereiten(ausgabe).lower(), _vorbereiten(eingabe).lower()
    funde = []
    for muster, gleichwertig in _ZUSAGEN:
        m = re.search(muster, aus)
        if m and not re.search(muster, ein) and not (gleichwertig and re.search(gleichwertig, ein)):
            funde.append({"art": "zusage", "wert": m.group(0)[:60]})
    return funde


def gleicher_text(a, b):
    """Gleich bis auf Leerzeichen, Zeilenumbrüche und Groß-/Kleinschreibung."""
    return _kompakt(a) == _kompakt(b)


def platzhalter(text):
    return re.findall(r"\[[^\[\]\n]{1,120}\]", str(text or ""))


def fehlende_teile(ausgabe, pflicht):
    """Pflichtteile (z. B. Platzhalter, Abmeldehinweis), die in der Ausgabe fehlen – Leerzeichen zählen nicht."""
    aus = _kompakt(ausgabe)
    return [{"art": "fehlt", "wert": p[:60]} for p in pflicht if p and _kompakt(p) not in aus]


def verdacht_auf_anweisung(text):
    """Fremdtext, der wie eine Anweisung an eine KI aussieht (Prompt-Injection) – Liste der Fundstellen."""
    t = _vorbereiten(text).lower()
    funde = []
    for muster in _ANWEISUNG:
        m = re.search(muster, t)
        if m:
            funde.append(m.group(0)[:60])
    return funde


def zeigbar(ausschnitt):
    """Ausschnitt aus Modelltext nur zeigen, wenn er nicht wie Passwort/Schlüssel aussieht – sonst lehnte der
    Supervisor das ganze Ergebnis ab (und ein Geheimnis gehört nie in ein Ergebnis)."""
    from ..protokoll import sieht_nach_geheimnis_aus
    return "[Ausschnitt nicht gezeigt]" if sieht_nach_geheimnis_aus(ausschnitt) else ausschnitt


def kurz(funde, hoechstens=4):
    """Kurze deutsche Zusammenfassung, z. B. „Telefonnummer „0214 999999“, Zahl „3““."""
    teile = ["%s „%s“" % (ARTEN.get(b["art"], b["art"]), zeigbar(b["wert"][:40])) for b in funde[:hoechstens]]
    return ", ".join(teile) + (" …" if len(funde) > hoechstens else "")
