# -*- coding: utf-8 -*-
"""Dubletten-Erkennung: dieselbe Ausschreibung aus mehreren Quellen (z. B. TED und service.bund.de).

Regel – bewusst KONSERVATIV (lieber eine Dublette übersehen als zwei verschiedene Ausschreibungen
zusammenwerfen), abgeleitet aus echten Live-Daten vom 22.11.2026:

Zwei Einträge aus VERSCHIEDENEN Quellen gelten als dieselbe Ausschreibung, wenn
  1. die Angebotsfrist auf denselben Tag fällt,
  2. der Titel nach Bereinigung gleich ist (bei TED fällt der Vorspann „Deutschland – Leistungsart – “ weg;
     Groß-/Kleinschreibung, Leerzeichen und Strich-Varianten zählen nicht) und
  3. entweder der Titel mindestens zwei markante Wörter hat (keine Allerweltswörter wie „Reinigung“) –
     oder die Vergabestellen ähnlich sind und sich die bekannten Orte nicht widersprechen.

Der Ort ist bewusst kein Pflichtmerkmal: TED nennt oft den Sitz der Vergabestelle (z. B. Münster),
service.bund.de den Leistungsort (z. B. Warendorf) – bei echten Dubletten weichen die Orte also ab.

Es wird nichts gespeichert und kein Status verändert: Die Gruppen werden bei jedem Abruf neu ermittelt.
"""

import re

from . import QUELLEN_NAMEN

# Welcher Eintrag einer Gruppe vorne steht: zuerst einer, den der Eigentümer schon bearbeitet hat,
# dann die Quelle mit den direktesten Unterlagen, dann die höhere Punktzahl.
QUELLEN_VORRANG = {"evergabe_nrw": 0, "service_bund": 1, "ted": 2}

ALLERWELT = frozenset("""
deutschland reinigung reinigungen reinigungsdienst reinigungsdienste reinigungsleistung reinigungsleistungen
reinigungsdienstleistung reinigungsdienstleistungen reinigungsarbeiten gebäudereinigung gebaeudereinigung
gebäudereinigungsleistung gebäudereinigungsleistungen gebäudereinigungsarbeiten unterhaltsreinigung
unterhaltsreinigungen unterhaltsreinigungsleistung unterhaltsreinigungsleistungen glasreinigung
glasreinigungsleistung glasreinigungsleistungen fensterreinigung grundreinigung sonderreinigung baureinigung
bauendreinigung baufertigstellung glas fenster unterhalts wohnungs gebäude gebäuden
und oder sowie der die das den dem des für fuer in im von vom zur zum mit auf an am bei aus nach über ueber
ein eine einer einem einen durchführung vergabe vergaben ausschreibung vertrag verträge rahmenvertrag
rahmenverträge rahmenvereinbarung leistung leistungen dienstleistung dienstleistungen offenes offene verfahren
eu-weit eu los lose objekt objekte objekten liegenschaft liegenschaften standort standorte diverse verschiedene
verschiedenen stadt gemeinde kreis landkreis jahr jahre monate inkl wartung inspektion
""".split())

STELLE_ALLERWELT = frozenset("""
stadt gemeinde kreis landkreis zentrale zentraler zentrales vergabestelle vergabe fachbereich abteilung amt referat
gmbh ag und für fuer der die das des recht einkauf dienste service verwaltung bau
""".split())

_KEIN_ORT = ("", "k.a.", "k. a.", "keine angabe")


def titel_bereinigt(e):
    """Titel zum Vergleichen: TED-Vorspann weg, klein, Striche und Leerzeichen vereinheitlicht."""
    t = str(e.get("titel") or "")
    if e.get("quelle") == "ted":
        teile = t.split(" – ")  # TED trennt mit Gedankenstrich und Leerzeichen; „Wohnungs-“ bleibt heil
        if len(teile) >= 3 and teile[0].strip().lower() == "deutschland":
            t = " – ".join(teile[2:])
    t = t.lower().replace("–", "-").replace("—", "-")
    return re.sub(r"\s+", " ", t).strip(" .,;:-")


def markante_woerter(titel):
    """Wörter, die eine Ausschreibung kennzeichnen (Orte, Namen, Aktenzeichen) – keine Allerweltswörter."""
    ergebnis = set()
    for w in re.findall(r"[0-9a-zäöüß]+(?:[-_][0-9a-zäöüß]+)*", titel.lower()):
        if w in ALLERWELT:
            continue
        if re.search(r"[a-zäöüß]", w):
            if len(w) >= 3:
                ergebnis.add(w)
        elif len(re.sub(r"\D", "", w)) >= 4 and not re.fullmatch(r"(19|20)\d\d", w):
            ergebnis.add(w)  # Aktenzeichen/Vergabenummer, keine Jahreszahl
    return ergebnis


def _stelle(e):
    s = str(e.get("vergabestelle") or "").lower()
    s = re.sub(r"\s*\([^()]*\)\s*$", "", s)  # „(Ort)“ am Ende – bei TED der Sitz der Vergabestelle
    return re.sub(r"[^0-9a-zäöüß]+", " ", s).strip()


def stellen_aehnlich(a, b):
    sa, sb = _stelle(a), _stelle(b)
    if not sa or not sb:
        return False
    if len(sa) >= 6 and len(sb) >= 6 and (sa in sb or sb in sa):
        return True
    wa = {w for w in sa.split() if len(w) >= 4 and w not in STELLE_ALLERWELT}
    wb = {w for w in sb.split() if len(w) >= 4 and w not in STELLE_ALLERWELT}
    return len(wa & wb) >= 2


def _ort(e):
    if e.get("quelle") == "ted":
        m = re.search(r"\(([^()]+)\)\s*$", str(e.get("vergabestelle") or ""))
        o = m.group(1) if m else ""
    else:
        o = str(e.get("ort") or "")
    o = o.split("(")[0].strip().lower()
    return None if o in _KEIN_ORT else o


def orte_widersprechen(a, b):
    oa, ob = _ort(a), _ort(b)
    return bool(oa and ob and oa != ob and oa not in ob and ob not in oa)


def ist_dublette(a, b):
    if not a.get("quelle") or a.get("quelle") == b.get("quelle"):
        return False
    tag = str(a.get("frist") or "")[:10]
    if not tag or tag != str(b.get("frist") or "")[:10]:
        return False
    titel = titel_bereinigt(a)
    if not titel or titel != titel_bereinigt(b):
        return False
    if len(markante_woerter(titel)) >= 2:
        return True
    return stellen_aehnlich(a, b) and not orte_widersprechen(a, b)


def _rang(e):
    bearbeitet = e.get("status") not in (None, "neu")
    return (0 if bearbeitet else 1, QUELLEN_VORRANG.get(e.get("quelle"), 9), -(e.get("punkte") or 0), str(e.get("id")))


def gruppen(eintraege):
    """Gruppen gleicher Ausschreibungen (nur Gruppen mit mindestens zwei Einträgen), Haupteintrag zuerst."""
    eintraege = list(eintraege)
    eltern = list(range(len(eintraege)))

    def wurzel(i):
        while eltern[i] != i:
            eltern[i] = eltern[eltern[i]]
            i = eltern[i]
        return i

    # Nur Einträge mit gleichem Frist-Tag und gleichem bereinigtem Titel kommen überhaupt infrage
    toepfe = {}
    for i, e in enumerate(eintraege):
        schluessel = (str(e.get("frist") or "")[:10], titel_bereinigt(e))
        if schluessel[0] and schluessel[1]:
            toepfe.setdefault(schluessel, []).append(i)
    for indizes in toepfe.values():
        for x in range(len(indizes)):
            for y in range(x + 1, len(indizes)):
                i, j = indizes[x], indizes[y]
                if ist_dublette(eintraege[i], eintraege[j]):
                    eltern[wurzel(i)] = wurzel(j)
    sammlung = {}
    for i in range(len(eintraege)):
        sammlung.setdefault(wurzel(i), []).append(i)
    ergebnis = [sorted((eintraege[i] for i in g), key=_rang) for g in sammlung.values() if len(g) > 1]
    return sorted(ergebnis, key=lambda g: eintraege.index(g[0]))


def anreichern(eintraege):
    """Setzt je Eintrag `auch_gefunden_bei` (die anderen Fundstellen) und `vermutlich_gleich_wie`
    (ID des Haupteintrags oder None). Verändert keinen Status."""
    for e in eintraege:
        e["auch_gefunden_bei"] = []
        e["vermutlich_gleich_wie"] = None
    for gruppe in gruppen(eintraege):
        haupt = gruppe[0]
        for e in gruppe:
            e["auch_gefunden_bei"] = [{"quelle": o.get("quelle"), "quelle_name": QUELLEN_NAMEN.get(o.get("quelle"), o.get("quelle")),
                                       "id": o.get("id"), "link": o.get("link")} for o in gruppe if o is not e]
            if e is not haupt:
                e["vermutlich_gleich_wie"] = haupt.get("id")
    return eintraege
