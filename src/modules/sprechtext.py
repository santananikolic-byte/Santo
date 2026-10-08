#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Sprechtext - aus geschriebenem Text wird Text, den ein Mensch so sagen würde.

Eine Stimme klingt nicht nur wegen des Klangs künstlich, sondern wegen dem,
was sie vorliest. Wer "1.069,60 €" liest, sagt nicht "eins Punkt null sechs
neun Komma sechzig Euro-Zeichen". Wer "z. B." liest, hält nicht an einem Punkt
an. Und ein Text, der in einem Stück an die Sprachausgabe geht, stockt oder
wiederholt sich gern mitten im Satz: lange Texte sind die häufigste Ursache
für Aussetzer und Schleifen.

Deshalb drei Schritte, alle ohne Netz und ohne Abhängigkeiten:

1. **Schreiben in Sprechen übersetzen**: Zahlen, Beträge, Daten, Uhrzeiten,
   Einheiten und Abkürzungen werden ausgeschrieben, Markdown, Links und Code
   fallen weg.
2. **In Atemabschnitte teilen**: kurze, in sich geschlossene Stücke, die an
   Satzenden und Kommas trennen, nie mitten in einer Zahl.
3. **Schleifen abfangen**: ein Satz, der zweimal hintereinander kommt, oder
   ein Wort, das dreimal hintereinander steht, wird einmal gesprochen.
"""

import re

EINER = ["null", "ein", "zwei", "drei", "vier", "fünf", "sechs", "sieben", "acht",
         "neun", "zehn", "elf", "zwölf", "dreizehn", "vierzehn", "fünfzehn",
         "sechzehn", "siebzehn", "achtzehn", "neunzehn"]
ZEHNER = ["", "", "zwanzig", "dreißig", "vierzig", "fünfzig", "sechzig",
          "siebzig", "achtzig", "neunzig"]
MONATE = ["Januar", "Februar", "März", "April", "Mai", "Juni", "Juli", "August",
          "September", "Oktober", "November", "Dezember"]

ABKUERZUNGEN = [
    (r"\bz\.\s?B\.", "zum Beispiel"), (r"\bd\.\s?h\.", "das heißt"),
    (r"\bu\.\s?a\.", "unter anderem"), (r"\bu\.\s?U\.", "unter Umständen"),
    (r"\bv\.\s?a\.", "vor allem"), (r"\bs\.\s?o\.", "siehe oben"),
    (r"\busw\.", "und so weiter"), (r"\betc\.", "und so weiter"),
    (r"\bca\.", "circa"), (r"\bbzw\.", "beziehungsweise"),
    (r"\bevtl\.", "eventuell"), (r"\bggf\.", "gegebenenfalls"),
    (r"\binkl\.", "inklusive"), (r"\bexkl\.", "exklusive"),
    (r"\bmax\.", "maximal"), (r"\bNr\.", "Nummer"), (r"\bTel\.", "Telefon"),
    (r"\bStr\.", "Straße"), (r"\bMio\.", "Millionen"), (r"\bMrd\.", "Milliarden"),
    (r"\bvgl\.", "vergleiche"), (r"\bggü\.", "gegenüber"),
    (r"\bDr\.", "Doktor"), (r"\bProf\.", "Professor"), (r"\bHr\.", "Herr"),
    (r"\bFr\.", "Frau"),
]

# Einheit nach einer Zahl -> gesprochene Form. Nur direkt hinter Ziffern.
EINHEITEN = [
    (r"m²|m2|qm", "Quadratmeter", "Quadratmeter"), (r"km", "Kilometer", "Kilometer"),
    (r"kg", "Kilogramm", "Kilogramm"), (r"min", "Minuten", "Minute"),
    (r"Std\.?|h", "Stunden", "Stunde"), (r"cm", "Zentimeter", "Zentimeter"),
    (r"mm", "Millimeter", "Millimeter"), (r"l", "Liter", "Liter"),
]


# -- Zahlen -------------------------------------------------------------------

def _unter_hundert(n: int, eins_voll: bool) -> str:
    if n < 20:
        return "eins" if (n == 1 and eins_voll) else EINER[n]
    einer, zehner = n % 10, n // 10
    if einer == 0:
        return ZEHNER[zehner]
    return ("ein" if einer == 1 else EINER[einer]) + "und" + ZEHNER[zehner]


def _unter_tausend(n: int, eins_voll: bool) -> str:
    hunderter, rest = n // 100, n % 100
    teile = ""
    if hunderter:
        teile = ("ein" if hunderter == 1 else EINER[hunderter]) + "hundert"
    if rest:
        teile += _unter_hundert(rest, eins_voll)
    return teile


def zahl_wort(n: int) -> str:
    """Eine ganze Zahl als deutsches Zahlwort. ``1069`` -> ``eintausendneunundsechzig``."""
    n = int(n)
    if n < 0:
        return "minus " + zahl_wort(-n)
    if n == 0:
        return "null"
    teile = []
    for grenze, einzahl, mehrzahl in ((10**12, "eine Billion", "Billionen"),
                                      (10**9, "eine Milliarde", "Milliarden"),
                                      (10**6, "eine Million", "Millionen")):
        if n >= grenze:
            menge, n = divmod(n, grenze)
            teile.append(einzahl if menge == 1
                         else "%s %s" % (zahl_wort(menge), mehrzahl))
    text = " ".join(teile)
    tausend, rest = divmod(n, 1000)
    unten = ""
    if tausend:
        unten = ("ein" if tausend == 1 else _unter_tausend(tausend, False)) + "tausend"
    if rest:
        unten += _unter_tausend(rest, True)
    return (text + " " + unten).strip() if unten else text


def jahr_wort(jahr: int) -> str:
    """Jahreszahlen: 1985 -> neunzehnhundertfünfundachtzig, 2026 -> zweitausendsechsundzwanzig."""
    if 1100 <= jahr <= 1999:
        hundert, rest = divmod(jahr, 100)
        text = _unter_hundert(hundert, False) + "hundert"
        return text + (_unter_hundert(rest, True) if rest else "")
    return zahl_wort(jahr)


def tag_stamm(tag: int) -> str:
    """Stamm der Ordnungszahl: 1 -> erst, 3 -> dritt, 7 -> siebt, 20 -> zwanzigst."""
    sonder = {1: "erst", 3: "dritt", 7: "siebt", 8: "acht"}
    if tag in sonder:
        return sonder[tag]
    if tag < 20:
        return EINER[tag] + "t"
    return zahl_wort(tag) + "st"


def tag_wort(tag: int, davor: str = "") -> str:
    """Ein Datumstag gesprochen. Die Endung hängt vom Wort davor ab:
    "am sechsten", "der sechste", sonst "sechster"."""
    davor = (davor or "").lower().rstrip()
    if re.search(r"\b(am|vom|zum|dem|den|beim|ab|bis|zum|im)$", davor):
        endung = "en"
    elif re.search(r"\bder$", davor):
        endung = "e"
    else:
        endung = "er"
    return tag_stamm(tag) + endung


def _dezimal_wort(ganz: str, nachkomma: str) -> str:
    stellen = " ".join(EINER[int(z)] if z != "1" else "eins" for z in nachkomma)
    return "%s Komma %s" % (zahl_wort(int(ganz)), stellen)


def _zahl_aus(text: str) -> int:
    return int(text.replace(".", ""))


# -- Schreiben -> Sprechen --------------------------------------------------------

def _betrag(treffer) -> str:
    ganz = treffer.group("ganz")
    cent = treffer.group("cent")
    euro = _zahl_aus(ganz)
    wort = "%s Euro" % ("ein" if euro == 1 else zahl_wort(euro))
    if cent and int(cent):
        c = int(cent.ljust(2, "0")[:2])
        if euro == 0:
            return "%s Cent" % ("ein" if c == 1 else zahl_wort(c))
        return "%s %s" % (wort, zahl_wort(c))
    return wort


def _datum(treffer) -> str:
    tag, monat = int(treffer.group(1)), int(treffer.group(2))
    jahr = treffer.group(3)
    if not (1 <= tag <= 31 and 1 <= monat <= 12):
        return treffer.group(0)
    davor = treffer.string[max(0, treffer.start() - 12):treffer.start()]
    text = "%s %s" % (tag_wort(tag, davor), MONATE[monat - 1])
    if jahr:
        j = int(jahr)
        if j < 100:
            j += 1900 if j > 40 else 2000
        text += " " + jahr_wort(j)
        return text
    # "bis 12.10. Danach": der Punkt nach dem Monat war auch das Satzende.
    danach = treffer.string[treffer.end():]
    if not danach.strip() or re.match(r"\s+[A-ZÄÖÜ]", danach):
        text += "."
    return text


def _uhrzeit(treffer) -> str:
    stunde, minute = int(treffer.group(1)), int(treffer.group(2))
    if stunde > 24 or minute > 59:
        return treffer.group(0)
    text = "%s Uhr" % ("ein" if stunde == 1 else zahl_wort(stunde))
    return text + (" %s" % zahl_wort(minute) if minute else "")


def schreiben_zu_sprechen(text: str) -> str:
    """Wandelt Geschriebenes in Gesprochenes um. Siehe Modulkopf."""
    if not text:
        return ""
    t = str(text)

    # Code und Gliederung fallen weg
    t = re.sub(r"```.*?(```|$)", " Den Code zeige ich dir auf dem Bildschirm. ", t, flags=re.S)
    t = re.sub(r"`([^`]*)`", r"\1", t)
    t = re.sub(r"!\[[^\]]*\]\([^)]*\)", " ", t)
    t = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", t)
    t = re.sub(r"^\s{0,3}#{1,6}\s*", "", t, flags=re.M)
    t = re.sub(r"^\s*[-*•·]\s+", "", t, flags=re.M)
    t = re.sub(r"^\s*\d+[.)]\s+(?!(?:%s)\b)" % "|".join(MONATE), "", t, flags=re.M)
    t = re.sub(r"[*_~>]+", " ", t)
    t = re.sub(r"[\U0001F300-\U0001FAFF☀-➿️]", "", t)
    t = t.replace("|", ", ")
    # Jede Zeile ist ein eigener Gedanke: ohne Satzzeichen würde sie an die nächste kleben.
    zeilen = [z.strip() for z in t.splitlines() if z.strip()]
    t = " ".join(z if re.search(r"[.!?:;,]$", z) else z + "." for z in zeilen)

    # Links und Adressen
    t = re.sub(r"https?://(?:www\.)?([^\s/]+)\S*",
               lambda m: "ein Link zu " + m.group(1).replace(".", " Punkt "), t)
    t = re.sub(r"([\w.+-]+)@([\w-]+(?:\.[\w-]+)+)",
               lambda m: "%s ät %s" % (m.group(1).replace(".", " Punkt "),
                                      m.group(2).replace(".", " Punkt ")), t)

    # Daten, Uhrzeiten, Beträge, Prozent, Zahlen
    t = re.sub(r"\b(\d{1,2})\.(\d{1,2})\.(\d{4}|\d{2})?(?!\d)", _datum, t)
    # "3. März": ausgeschriebener Monat mit Ordnungszahl davor.
    t = re.sub(r"\b(\d{1,2})\.\s?(%s)\b" % "|".join(MONATE),
               lambda m: "%s %s" % (tag_wort(int(m.group(1)), m.string[max(0, m.start() - 12):m.start()]),
                                    m.group(2)) if 1 <= int(m.group(1)) <= 31 else m.group(0), t)
    t = re.sub(r"\b(\d{1,2}):(\d{2})(?:\s?Uhr)?\b", _uhrzeit, t)
    # "45 €/h", "130 km/h": der Schrägstrich ist ein "pro".
    pro = {"h": "Stunde", "std": "Stunde", "std.": "Stunde", "stunde": "Stunde", "m²": "Quadratmeter",
           "m2": "Quadratmeter", "qm": "Quadratmeter", "monat": "Monat", "tag": "Tag",
           "woche": "Woche", "stück": "Stück", "stk": "Stück", "stk.": "Stück"}
    t = re.sub(r"(\d)\s?km\s?/\s?h(?![\wäöüß])", r"\1 Kilometer pro Stunde", t)
    t = re.sub(r"(€|EUR|Euro)\s?/\s?(h|Std\.?|Stunde|m²|m2|qm|Monat|Tag|Woche|Stück|Stk\.?)(?![\wäöüß])",
               lambda m: "%s pro %s" % (m.group(1), pro.get(m.group(2).lower(), m.group(2))), t)
    # Ein Minus vor einem Betrag oder einer Prozentzahl wird gesprochen.
    t = re.sub(r"(?<![\w.,])[-−–]\s?(?=\d[\d.,]*\s?(?:€|EUR|Euro|%))", "minus ", t)
    betrag = r"(?P<ganz>\d{1,3}(?:\.\d{3})+|\d+)(?:,(?P<cent>\d{1,2}))?"
    t = re.sub(betrag + r"\s?(?:€|EUR|Euro)(?![\wäöüß])", _betrag, t)
    t = re.sub(r"(?:€|EUR)\s?" + betrag, _betrag, t)
    t = re.sub(r"(\d+(?:,\d+)?)\s?%",
               lambda m: re.sub(r"(\d+),(\d+)", lambda d: _dezimal_wort(d.group(1), d.group(2)),
                                m.group(1)) + " Prozent", t)
    for muster, mehrzahl, einzahl in EINHEITEN:
        t = re.sub(r"(?P<zahl>\d+(?:[.,]\d+)*)\s?(?:%s)(?![\wäöüß])" % muster,
                   lambda m, mz=mehrzahl, ez=einzahl: "%s %s" % (
                       m.group("zahl"), ez if m.group("zahl") == "1" else mz), t)
    t = re.sub(r"\b\d{1,3}(?:\.\d{3})+\b", lambda m: zahl_wort(_zahl_aus(m.group(0))), t)
    t = re.sub(r"\b(\d+),(\d+)\b", lambda m: _dezimal_wort(m.group(1), m.group(2)), t)

    # Abkürzungen und Zeichen
    for muster, wort in ABKUERZUNGEN:
        t = re.sub(muster, wort, t)
    # "usw." stand am Satzende: der Punkt gehört dann wieder dahin.
    t = re.sub(r"\bund so weiter(?=\s+[A-ZÄÖÜ])", "und so weiter.", t)
    t = t.replace("&", " und ").replace("€", " Euro ").replace("→", ", ").replace("->", ", ")
    t = re.sub(r"\s[–—-]\s", ", ", t)
    t = t.replace("…", ".").replace("...", ".")
    t = re.sub(r"[„“”\"»«]", "", t)
    t = re.sub(r"\s*[()\[\]]\s*", ", ", t)
    t = re.sub(r"\s*/\s*", " ", t)

    # Aufräumen: doppelte Zeichen, Leerzeichen vor Satzzeichen
    t = re.sub(r"\s+", " ", t)
    t = re.sub(r"\s+([,.;:!?])", r"\1", t)
    t = re.sub(r"([,;:])\s*([,;:.!?])", r"\2", t)
    t = re.sub(r"([.!?])\s*,", r"\1", t)
    t = re.sub(r"^[,;:\s]+", "", t)
    return t.strip()


# -- Schleifen ----------------------------------------------------------------------

def schleifen_entfernen(text: str) -> str:
    """Spricht Wiederholungen einmal: drei gleiche Wörter und doppelte Sätze."""
    t = re.sub(r"\b([\wäöüÄÖÜß]+)(?:[\s,]+\1\b){2,}", r"\1", text, flags=re.I)
    saetze = re.findall(r"[^.!?]+[.!?]*\s*", t)
    gesehen, behalten = set(), []
    for satz in saetze:
        schluessel = re.sub(r"\W+", " ", satz).strip().lower()
        if len(schluessel) > 15 and schluessel in gesehen:
            continue
        gesehen.add(schluessel)
        behalten.append(satz)
    return "".join(behalten).strip() if behalten else t.strip()


# -- Atemabschnitte ---------------------------------------------------------------------

def abschnitte(text: str, ziel: int = 170, maximum: int = 260) -> list:
    """Teilt gesprochenen Text in Stücke, die man in einem Atemzug sagt.

    Getrennt wird an Satzenden, zu lange Sätze an Kommas und Bindewörtern. Nie
    mitten in einem Wort. Sehr kurze Stücke werden mit dem nächsten verbunden,
    denn ein Stück mit zwei Wörtern klingt abgehackt.
    """
    text = (text or "").strip()
    if not text:
        return []
    saetze = [s.strip() for s in re.findall(r"[^.!?]+[.!?]*", text) if s.strip()]
    stuecke = []
    for satz in saetze:
        while len(satz) > maximum:
            fenster = satz[:maximum]
            schnitt = max(fenster.rfind(", "), fenster.rfind("; "), fenster.rfind(": "))
            if schnitt < ziel // 3:
                schnitt = max(fenster.rfind(" und "), fenster.rfind(" aber "),
                              fenster.rfind(" oder "), fenster.rfind(" weil "))
            if schnitt < ziel // 3:
                schnitt = fenster.rfind(" ")
            if schnitt <= 0:
                schnitt = maximum
            stuecke.append(satz[:schnitt + 1].strip())
            satz = satz[schnitt + 1:].strip()
        if satz:
            stuecke.append(satz)

    verbunden = []
    for stueck in stuecke:
        if verbunden and (len(verbunden[-1]) < 45 or len(stueck) < 25) \
                and len(verbunden[-1]) + 1 + len(stueck) <= ziel:
            verbunden[-1] += " " + stueck
        else:
            verbunden.append(stueck)
    return verbunden


def sprechtext(text: str) -> str:
    """Der ganze Text, zum Sprechen vorbereitet - in einem Stück."""
    return schleifen_entfernen(schreiben_zu_sprechen(text))


def sprechstuecke(text: str, ziel: int = 170) -> list:
    """Der Text, zum Sprechen vorbereitet und in Atemabschnitte geteilt."""
    return abschnitte(sprechtext(text), ziel)


# Satzzeichen anderer Schriften, die ``abschnitte`` sonst nicht als Satzende erkennt.
_FREMDE_SATZZEICHEN = {"؟": "?", "؛": ";", "،": ",", "۔": ".",
                       "。": ".", "！": "!", "？": "?"}
_DEZIMALPUNKT = "․"  # sieht aus wie ein Punkt, trennt aber keinen Satz


def abschnitte_ziffernsicher(text: str, ziel: int = 170) -> list:
    """Wie :func:`abschnitte`, aber ein Punkt zwischen zwei Ziffern ist kein Satzende.

    Nötig für Text, dessen Zahlen nicht ausgeschrieben sind ("12.50 EUR"): sonst risse
    ``abschnitte`` mitten in der Zahl.
    """
    geschuetzt = re.sub(r"(?<=\d)\.(?=\d)", _DEZIMALPUNKT, str(text or ""))
    return [stueck.replace(_DEZIMALPUNKT, ".") for stueck in abschnitte(geschuetzt, ziel)]


def sprechstuecke_fremd(text: str, ziel: int = 220) -> list:
    """Wie :func:`sprechstuecke`, aber für Text in einer anderen Sprache als Deutsch.

    Zahlen, Beträge und Daten bleiben, wie sie sind: Die deutsche Zahlenschreibung
    (``schreiben_zu_sprechen``) würde "12.50" zu "zwölf Komma fünfzig" machen, mitten
    in einem türkischen oder englischen Satz. Es fallen nur Markdown-Zeichen,
    Schleifen und Steuerzeichen weg, dann wird in Atemabschnitte geteilt.
    """
    t = re.sub(r"[\x00-\x08\x0b-\x1f\x7f]", " ", str(text or ""))
    t = t.translate({ord(k): v for k, v in _FREMDE_SATZZEICHEN.items()})
    t = re.sub(r"```.*?```", " ", t, flags=re.S)
    t = re.sub(r"[*_`~]{1,3}", "", t)
    t = re.sub(r"(?m)^\s*#{1,6}\s*", "", t)
    t = re.sub(r"\s+", " ", t).strip()
    if not t:
        return []
    return abschnitte_ziffernsicher(schleifen_entfernen(t), ziel)
