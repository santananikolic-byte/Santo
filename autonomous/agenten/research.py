# -*- coding: utf-8 -*-
"""Research-Agent: bewertet Geschäftsfelder anhand nachvollziehbarer Kriterien und Quellen.

- marktbewertung: wertet die recherchierte Marktbewertung aus (daten_vorlagen/marktbewertung.json, Quellen mit
  Abrufdatum). Die Datei gilt als NICHT vertrauenswürdige Eingabe: nur als Daten gelesen, gegen ein Schema geprüft.
- marktbericht: untersucht den Markt SELBST aus amtlichen Daten – TED-Schnittstelle des EU-Amtsblatts
  (Ausschreibungen und Zuschläge) und die vom Akquise-Agenten gesammelten Ausschreibungen. Nur lesen, nur
  freigegebene Quellen, nur wenn die Internet-Recherche eingeschaltet ist. Jede Zahl ist gezählt und mit
  Quelle, Abfrage und Abrufzeit belegt; Deutungen stehen getrennt als Annahme. Ein lokales Modell (falls
  eingestellt und erreichbar) darf nur eine gekennzeichnete Zusammenfassung ergänzen."""

import collections
import datetime
import json
import os
import re
import statistics
from urllib.parse import urlparse

from . import Agent, Blockiert
from .. import konfig, netz
from ..auftraege import PASSEND_AB, QUELLEN_NAMEN
from ..auftraege import text as fremdtext
from ..auftraege.quellen import NUTS_NAMEN, TED_CPV, TED_URL
from ..db import jetzt, neue_id
from ..ki import vorlagen
from ..modell import ModellNichtVerfuegbar
from ..produkte import datei_schreiben, esc, sicherer_pfad
from ..protokoll import sieht_nach_geheimnis_aus

STANDARD_GEWICHTE = {"nachfrage": 2, "kundenproblem": 2, "erreichbarkeit": 3, "wettbewerb": 1,
                     "differenzierung": 1, "entwicklungsaufwand": 2, "direkte_kosten": 1, "verkaufspreis": 2,
                     "lieferzeit": 1, "rechtliche_risiken": 2}


def _zahl(w):
    if isinstance(w, bool) or not isinstance(w, (int, float)):
        return None
    return w if 0 <= w <= 5 else None


def quelle_bewerten(q, heute=None):
    heute = heute or datetime.date.today()
    url = str(q.get("url", ""))
    teile = urlparse(url)
    bewertung = {"url": url[:300], "titel": str(q.get("titel", ""))[:200], "punkte": 0, "hinweise": []}
    if teile.scheme == "https":
        bewertung["punkte"] += 1
    else:
        bewertung["hinweise"].append("keine https-Adresse")
    host = (teile.hostname or "").lower()
    if host.endswith((".bund.de", ".nrw.de", "gesetze-im-internet.de", "ihk.de", ".gov", "destatis.de",
                      "europa.eu", "bundesregierung.de", "bmwk.de", "bmj.de")) or ".ihk." in host:
        bewertung["punkte"] += 2
        bewertung["hinweise"].append("amtliche/öffentliche Stelle")
    elif host:
        bewertung["punkte"] += 1
    try:
        abgerufen = datetime.date.fromisoformat(str(q.get("abgerufen", ""))[:10])
        alter = (heute - abgerufen).days
        bewertung["alter_tage"] = alter
        if alter <= 180:
            bewertung["punkte"] += 1
        else:
            bewertung["hinweise"].append("Abruf älter als 180 Tage – neu prüfen")
    except ValueError:
        bewertung["hinweise"].append("kein gültiges Abrufdatum")
    bewertung["stufe"] = ("gut" if bewertung["punkte"] >= 3 else "mittel" if bewertung["punkte"] == 2
                          else "schwach")
    return bewertung


class ResearchAgent(Agent):
    rolle = "research"
    name = "Research-Agent"
    beschreibung = "Untersucht Märkte, Wettbewerber und Zielgruppen; trennt Belege von Annahmen."
    rechte = frozenset({"lokale_recherche", "interne_auswertung", "gedaechtnis_vorschlag", "lokales_modell",
                        "web_lesen", "datei_erstellen"})
    aufgabentypen = {
        "marktbewertung": "Geschäftsfelder nach Kriterien gewichten und ranken (Eingabe optional: gewichte)",
        "quellen_pruefen": "Aktualität und Qualität von Quellen bewerten (Eingabe: quellen[])",
        "marktbericht": "Markt selbst untersuchen aus amtlichen Daten (TED) und gesammelten Ausschreibungen: "
                        "Nachfrage, Wettbewerber, Zielgruppen, Anforderungen (Eingabe optional: zeitraum_tage "
                        "30–730)",
    }

    def _laden(self):
        pfad = os.path.join(konfig.VORLAGEN, "marktbewertung.json")
        if not os.path.exists(pfad):
            raise ValueError("Keine Marktbewertung vorhanden (daten_vorlagen/marktbewertung.json fehlt).")
        with open(pfad, encoding="utf-8") as f:
            daten = json.load(f)
        if not isinstance(daten, dict) or not isinstance(daten.get("felder"), list):
            raise ValueError("Marktbewertung hat ein ungültiges Format.")
        return daten, pfad

    def aufgabe_marktbewertung(self, aufgabe, k):
        self.darf(k, "lokale_recherche", "marktbewertung", aufgabe)
        daten, pfad = self._laden()
        gewichte = dict(STANDARD_GEWICHTE)
        for name, w in (aufgabe["eingabe"].get("gewichte") or {}).items():
            if name in gewichte and _zahl(w) is not None:
                gewichte[name] = w
        rangliste = []
        for feld in daten["felder"][:50]:
            if not isinstance(feld, dict):
                continue
            punkte = feld.get("punkte") or {}
            summe = gewicht = 0
            fehlend = []
            for krit, g in gewichte.items():
                p = _zahl(punkte.get(krit))
                if p is None:
                    fehlend.append(krit)
                    continue
                summe += p * g
                gewicht += g
            quellen = [quelle_bewerten(q) for q in (feld.get("quellen") or [])[:20] if isinstance(q, dict)]
            rangliste.append({
                "id": str(feld.get("id", ""))[:60], "name": str(feld.get("name", ""))[:200],
                "wert": round(summe / gewicht, 2) if gewicht else None,
                "fehlende_kriterien": fehlend,
                "belegstatus": str(feld.get("belegstatus", "unbekannt"))[:30],
                "quellen": quellen,
                "quellen_gut": sum(1 for q in quellen if q["stufe"] == "gut"),
            })
        rangliste.sort(key=lambda r: (r["wert"] is None, -(r["wert"] or 0)))
        empfehlung = daten.get("empfehlung") or {}
        ergebnis = {
            "stand": daten.get("stand"), "gewichte": gewichte, "rangliste": rangliste,
            "empfehlung_aus_recherche": {k2: empfehlung.get(k2) for k2 in ("feld_id", "angebot",
                                                                         "preis_vorschlag_eur", "begruendung")},
            "spitze_nach_gewichtung": rangliste[0]["id"] if rangliste else None,
            "quelle": "datei:" + os.path.relpath(pfad, konfig.PROJEKT),
            "einordnung": "Punktwerte sind begründete Einschätzungen der Recherche, keine Messwerte. "
                          "Preise sind VORSCHLÄGE – Entscheidung beim Inhaber.",
        }
        if rangliste:
            self.darf(k, "gedaechtnis_vorschlag", "marktbewertung", aufgabe)
            k.gedaechtnis.merken("vorschlag", "Erstes Angebot", "Nach Gewichtung vorne: %s (Wert %s). Empfehlung "
                                 "der Recherche: %s" % (rangliste[0]["name"], rangliste[0]["wert"],
                                                        empfehlung.get("angebot")),
                                 ergebnis["quelle"], self.rolle, aufgabe["id"])
        return ergebnis

    def aufgabe_quellen_pruefen(self, aufgabe, k):
        self.darf(k, "lokale_recherche", "quellen_pruefen", aufgabe)
        quellen = aufgabe["eingabe"].get("quellen") or []
        if not isinstance(quellen, list) or not quellen:
            raise ValueError("Eingabe 'quellen' (Liste) fehlt.")
        return {"bewertungen": [quelle_bewerten(q) for q in quellen[:50] if isinstance(q, dict)]}

    # ------------------------------------------------------------------ Marktbericht (PDF 0, 5.2)
    def aufgabe_marktbericht(self, aufgabe, k):
        if not k.einstellungen.hole("internet_recherche_erlaubt"):
            # Klar blockiert – der Orchestrator bricht ab, keine Wiederholung, kein Abruf
            raise Blockiert("Internet-Recherche ist ausgeschaltet (Einstellungen → einmal einschalten)")
        e = aufgabe["eingabe"] or {}
        zeitraum = zeitraum_pruefen(e.get("zeitraum_tage"))
        nuts = [n for n in (e.get("region_nuts") or k.einstellungen.hole("region_nuts") or ["DEA"])
                if isinstance(n, str) and re.fullmatch(r"DE[A-Z0-9]{0,3}", n)][:10] or ["DEA"]
        self.darf(k, "interne_auswertung", "marktbericht", aufgabe)
        heute = datetime.date.today()
        start = heute - datetime.timedelta(days=zeitraum)
        abgerufen = jetzt()

        teile, fehler, abfragen = {}, {}, []
        for art, typen, felder in (("ausschreibungen", "cn-standard cn-social", FELDER_AUSSCHREIBUNG),
                                   ("zuschlaege", "can-standard can-social", FELDER_ZUSCHLAG)):
            abfrage = ted_abfrage(nuts, start, typen)
            abfragen.append(abfrage)
            try:
                teile[art] = self._ted_holen(k, aufgabe, abfrage, felder)
            except (netz.NetzFehler, ValueError) as f:
                fehler[art] = str(f)[:300]
        if not teile:
            raise RuntimeError("TED nicht erreichbar – kein Marktbericht möglich (%s)" % "; ".join(fehler.values()))

        cn, cn_gesamt = teile.get("ausschreibungen", ([], None))
        can, can_gesamt = teile.get("zuschlaege", ([], None))
        abschnitte = {
            "nachfrage": _nicht_verfuegbar("Ausschreibungen", fehler.get("ausschreibungen")) if cn_gesamt is None
            else dict(nachfrage_auswerten(cn), beleg="gezählt",
                      grundlage="Ausgewertet: %d von %d EU-weiten Ausschreibungen laut TED im Zeitraum %s bis %s "
                                "(Abfrage siehe Quellen)." % (len(cn), cn_gesamt, _datum_de(start.isoformat()), _datum_de(heute.isoformat()))),
            "wettbewerber": _nicht_verfuegbar("Zuschläge", fehler.get("zuschlaege")) if can_gesamt is None
            else dict(zuschlaege_auswerten(can), verfuegbar=True, beleg="gezählt",
                      grundlage="Ausgewertet: %d von %d Zuschlagsbekanntmachungen laut TED im Zeitraum %s bis %s."
                                % (len(can), can_gesamt, _datum_de(start.isoformat()), _datum_de(heute.isoformat()))),
            "zielgruppen": dict(zielgruppen_auswerten(cn + can), beleg="gezählt",
                                grundlage="Auftraggeber aus %d ausgewerteten TED-Bekanntmachungen (je Bekanntmachung "
                                          "einmal gezählt)." % len(cn + can)),
            "anforderungen": dict(anforderungen_zaehlen(cn), beleg="gezählt",
                                  grundlage="Begriffe in den Titeln von %d ausgewerteten Ausschreibungen (je Titel "
                                            "einmal gezählt)." % len(cn)),
            "gesammelt": dict(gesammelt_auswerten(k, start), beleg="gezählt",
                              grundlage="Vom Akquise-Agenten gesammelte Ausschreibungen (TED, service.bund.de, "
                                        "Vergabemarktplatz NRW), gefunden seit %s." % _datum_de(start.isoformat())),
        }
        w = abschnitte["wettbewerber"]
        kennzahlen = {
            "ausschreibungen_ted_gesamt": cn_gesamt, "ausschreibungen_ausgewertet": len(cn),
            "zuschlaege_ted_gesamt": can_gesamt, "zuschlaege_ausgewertet": len(can),
            "wettbewerber_anzahl": w.get("anzahl_unternehmen") if w.get("verfuegbar") else None,
            "angebote_je_los_median": w.get("angebote_je_los", {}).get("median") if w.get("verfuegbar") else None,
            "angebotsfrist_median_tage": abschnitte["nachfrage"].get("angebotsfrist_median_tage"),
            "gesammelte_ausschreibungen": abschnitte["gesammelt"]["anzahl"],
        }
        quellen = [
            {"titel": "TED – Suchschnittstelle des Amtsblatts der EU (offizielle Schnittstelle)", "url": TED_URL,
             "abfragen": abfragen, "abgerufen": abgerufen,
             "bewertung": quelle_bewerten({"titel": "TED", "url": TED_URL, "abgerufen": heute.isoformat()}),
             "fehler": fehler or None},
            {"titel": "Gesammelte Ausschreibungen (Tabelle ausschreibungen, Akquise-Agent)",
             "url": "datei:autonomous/daten/autonomous.db", "abfragen": ["gefunden >= %s" % start.isoformat()],
             "abgerufen": abgerufen, "bewertung": {"stufe": "mittel", "hinweise": [
                 "eigene Sammlung – nur so vollständig wie die bisherigen Suchläufe"]}},
        ]
        annahmen = [
            "Annahme: EU-weite Ausschreibungen (TED) liegen über den EU-Schwellenwerten und betreffen eher größere "
            "Aufträge; kleinere Aufträge stehen eher auf service.bund.de und dem Vergabemarktplatz NRW.",
            "Annahme: Ein Auftragswert von 0 oder 1 € in einer Zuschlagsbekanntmachung ist ein Platzhalter "
            "(Wert nicht veröffentlicht); er zählt nicht als Wert.",
            "Annahme: Auftragswerte gelten meist für die gesamte Vertragslaufzeit, nicht pro Jahr.",
            "Hinweis: Unternehmensnamen werden nicht zusammengeführt – Schreibvarianten zählen getrennt.",
            "Hinweis: Titel sind Kurzbeschreibungen; Begriffszählungen zeigen Schwerpunkte, keine vollständigen "
            "Leistungsverzeichnisse.",
        ]
        bid = neue_id("mb_")
        ki, ki_hinweis = self._ki_zusammenfassung(k, aufgabe, kennzahlen, abschnitte)
        daten = {"bericht_id": bid, "zeitraum_tage": zeitraum, "von": start.isoformat(), "bis": heute.isoformat(),
                 "region_nuts": nuts, "kennzahlen": kennzahlen, "abschnitte": abschnitte, "quellen": quellen,
                 "annahmen": annahmen, "ki_zusammenfassung": ki, "ki_hinweis": ki_hinweis, "abgerufen": abgerufen}
        pfad = sicherer_pfad("marktberichte", bid, "bericht.html")
        self.darf(k, "datei_erstellen", "marktbericht:%s/bericht.html" % bid, aufgabe, datei_pfad=pfad)
        datei_schreiben(pfad, bericht_html(daten))
        self.darf(k, "gedaechtnis_vorschlag", "marktbericht", aufgabe)
        k.gedaechtnis.merken("hypothese", "Marktbericht Reinigung (%s, %d Tage)" % (", ".join(nuts), zeitraum),
                             _kurzfassung(kennzahlen, abschnitte), "research:marktbericht %s" % bid, self.rolle,
                             aufgabe["id"])
        return dict(daten, bericht_url="/produkte/marktberichte/%s/bericht.html" % bid, dateien=[pfad])

    def _ted_holen(self, k, aufgabe, abfrage, felder):
        """Alle Seiten einer TED-Abfrage (höchstens MARKT_SEITEN). Liefert (Bekanntmachungen, Gesamtzahl laut TED)."""
        bekanntmachungen, gesamt = [], 0
        for seite in range(1, MARKT_SEITEN + 1):
            koerper = json.dumps({"query": abfrage, "fields": felder, "limit": MARKT_SEITE,
                                  "page": seite}).encode("utf-8")
            self.darf(k, "web_lesen", "ted", aufgabe, url=TED_URL)
            antwort = netz.abrufen(TED_URL, methode="POST", daten=koerper, kopf={"Content-Type": "application/json"})
            try:
                d = json.loads(antwort.text())
            except ValueError:
                raise ValueError("TED: Antwort ist kein gültiges JSON")
            if not isinstance(d, dict) or not isinstance(d.get("notices"), list):
                raise ValueError("TED: unerwartetes Antwortformat")
            gesamt = int(d.get("totalNoticeCount") or 0)
            neu = [n for n in d["notices"] if isinstance(n, dict)]
            bekanntmachungen.extend(neu)
            if len(neu) < MARKT_SEITE or len(bekanntmachungen) >= gesamt:
                break
        return bekanntmachungen, gesamt

    def _ki_zusammenfassung(self, k, aufgabe, kennzahlen, abschnitte):
        if not k.modell.verfuegbar():
            return None, ("Ohne KI-Zusammenfassung: kein Modell eingestellt (Einstellungen → Modell). "
                          "Der Bericht ist ohne sie vollständig.")
        self.darf(k, "lokales_modell", "marktbericht", aufgabe)
        daten = {"kennzahlen": kennzahlen,
                 "nachfrage": {x: abschnitte["nachfrage"].get(x) for x in ("nach_region", "verfahren")},
                 "wettbewerber_top": (abschnitte["wettbewerber"].get("top") or [])[:5],
                 "anforderungen": (abschnitte["anforderungen"].get("begriffe") or [])[:6]}
        try:
            g = k.modell.frage_gekennzeichnet(*vorlagen.marktbericht_zusammenfassung(daten), agent=self.rolle,
                                              aufgabe_id=aufgabe["id"], max_zeichen=2000)
        except ModellNichtVerfuegbar as f:
            return None, "KI-Zusammenfassung nicht möglich: %s – der Bericht ist ohne sie vollständig." % f
        if sieht_nach_geheimnis_aus(g["text"]):
            # Lieber ohne Zusammenfassung als ein abgelehnter Bericht: Modelltext ist nicht vertrauenswürdig
            k.protokoll.warnung("research", "KI-Zusammenfassung verworfen (Muster wie Passwort/Schlüssel)")
            return None, ("KI-Zusammenfassung verworfen: Der Text enthielt ein Muster wie ein Passwort oder einen "
                          "Schlüssel. Der Bericht ist ohne sie vollständig.")
        return g, "KI-Zusammenfassung vom lokalen Modell – ungeprüft, nur als Lesehilfe."


# ---------------------------------------------------------------------- Marktbericht: Hilfen
MARKT_SEITEN = 5
MARKT_SEITE = 100
FELDER_AUSSCHREIBUNG = ["publication-number", "publication-date", "notice-type", "notice-title", "buyer-name",
                        "buyer-city", "buyer-legal-type", "place-of-performance", "procedure-type",
                        "classification-cpv", "deadline-receipt-tender-date-lot"]
# Keine personenbezogenen Felder (winner-person, winner-email, buyer-email …) – nur Firmen und Zahlen
FELDER_ZUSCHLAG = ["publication-number", "publication-date", "notice-type", "buyer-name", "buyer-city",
                   "buyer-legal-type", "place-of-performance", "procedure-type", "winner-name", "winner-city",
                   "winner-size", "total-value", "total-value-cur", "received-submissions-type-code",
                   "received-submissions-type-val"]
# Bezeichnungen der eForms-Codes (Code wird immer mit angezeigt)
AUFTRAGGEBER_ARTEN = {
    "la": "Kommunale Behörde (Stadt, Gemeinde, Kreis)", "ra": "Regionale Behörde (Land)",
    "cga": "Zentrale Behörde (Bund)", "body-pl": "Einrichtung des öffentlichen Rechts",
    "body-pl-la": "Einrichtung des öffentlichen Rechts (kommunal kontrolliert)",
    "body-pl-ra": "Einrichtung des öffentlichen Rechts (vom Land kontrolliert)",
    "body-pl-cga": "Einrichtung des öffentlichen Rechts (vom Bund kontrolliert)",
    "pub-undert": "Öffentliches Unternehmen", "pub-undert-la": "Öffentliches Unternehmen (kommunal kontrolliert)",
    "pub-undert-ra": "Öffentliches Unternehmen (vom Land kontrolliert)",
    "pub-undert-cga": "Öffentliches Unternehmen (vom Bund kontrolliert)",
}
VERFAHREN = {"open": "Offenes Verfahren", "restricted": "Nicht offenes Verfahren",
             "neg-w-call": "Verhandlungsverfahren mit Teilnahmewettbewerb",
             "neg-wo-call": "Verhandlungsverfahren ohne Teilnahmewettbewerb", "comp-dial": "Wettbewerblicher Dialog",
             "innovation": "Innovationspartnerschaft", "oth-single": "Sonstiges (einstufig)",
             "oth-mult": "Sonstiges (mehrstufig)"}
GROESSEN = ("micro", "small", "medium", "large")
BEGRIFFE = (
    ("Unterhaltsreinigung", r"unterhaltsreinigung"),
    ("Glas- und Fensterreinigung", r"glasreinigung|fensterreinigung|glas- und fenster"),
    ("Grundreinigung", r"grundreinigung"),
    ("Sonderreinigung", r"sonderreinigung"),
    ("Bau- und Bauendreinigung", r"bauendreinigung|baureinigung|baufeinreinigung|bauschlussreinigung"),
    ("Treppenhaus", r"treppenh"),
    ("Schulen", r"schul"),
    ("Kitas", r"\bkita|kindertages"),
    ("Verwaltung und Rathaus", r"verwaltung|rathaus"),
    ("Bundeswehr und Kasernen", r"bundeswehr|kaserne"),
    ("Krankenhaus, Klinik, Pflege", r"krankenhaus|klinik|pflege"),
    ("Sport- und Turnhallen", r"sporthalle|turnhalle"),
    ("Aufteilung in Lose", r"\blos(e)?\b"),
    ("Rahmenvertrag", r"rahmenvertrag|rahmenvereinbarung"),
    ("Hausmeisterdienst", r"hausmeister"),
    ("Winterdienst", r"winterdienst"),
    ("Desinfektion und Hygiene", r"desinfektion|hygiene"),
)


def zeitraum_pruefen(wert, standard=365):
    if wert is None or (isinstance(wert, str) and not wert.strip()):
        return standard
    if isinstance(wert, bool):
        raise ValueError("zeitraum_tage muss eine Zahl zwischen 30 und 730 sein.")
    try:
        tage = int(str(wert).strip())
    except ValueError:
        raise ValueError("zeitraum_tage muss eine Zahl zwischen 30 und 730 sein.")
    if not 30 <= tage <= 730:
        raise ValueError("zeitraum_tage muss zwischen 30 und 730 liegen.")
    return tage


def ted_abfrage(nuts, start, notice_typen):
    return ("classification-cpv IN (%s) AND place-of-performance IN (%s) AND notice-type IN (%s) AND "
            "publication-date>=%s" % (" ".join(TED_CPV), " ".join(nuts), notice_typen, start.strftime("%Y%m%d")))


def _texte(wert):
    """Mehrsprachige TED-Felder → Liste von Texten (deutsch bevorzugt)."""
    if isinstance(wert, dict):
        for schluessel in ("deu", "mul", "eng"):
            if schluessel in wert:
                return _texte(wert[schluessel])
        return _texte(next(iter(wert.values()), None))
    if isinstance(wert, list):
        return [fremdtext(x, 200) for x in wert if isinstance(x, (str, int, float)) and fremdtext(x, 200)]
    if isinstance(wert, (str, int, float)):
        t = fremdtext(wert, 300)
        return [t] if t else []
    return []


def _liste(wert):
    if isinstance(wert, list):
        return [str(x) for x in wert if isinstance(x, (str, int, float))]
    return [str(wert)] if isinstance(wert, (str, int, float)) else []


def _datum(wert):
    m = re.match(r"(\d{4})-(\d{2})-(\d{2})", str(wert or ""))
    if not m:
        return None
    try:
        return datetime.date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    except ValueError:
        return None


def _median(werte):
    werte = [w for w in werte if isinstance(w, (int, float))]
    return round(statistics.median(werte), 1) if werte else None


def _nicht_verfuegbar(was, meldung):
    return {"verfuegbar": False, "beleg": "nicht verfügbar",
            "meldung": "%s: %s" % (was, meldung or "keine Daten")}


def nachfrage_auswerten(bekanntmachungen):
    monate, regionen, verfahren, fristen = collections.Counter(), collections.Counter(), collections.Counter(), []
    for n in bekanntmachungen:
        veroeff = _datum(n.get("publication-date"))
        if veroeff:
            monate[veroeff.isoformat()[:7]] += 1
        for code in sorted({c[:4] for c in _liste(n.get("place-of-performance")) if re.fullmatch(r"DEA\d\w?", c)}):
            regionen["%s (%s)" % (NUTS_NAMEN.get(code, code), code)] += 1
        art = (_liste(n.get("procedure-type")) or ["unbekannt"])[0]
        verfahren["%s (%s)" % (VERFAHREN.get(art, "Sonstiges"), art)] += 1
        fristen_liste = sorted(d for d in (_datum(x) for x in _liste(n.get("deadline-receipt-tender-date-lot"))) if d)
        if veroeff and fristen_liste and fristen_liste[0] >= veroeff:
            fristen.append((fristen_liste[0] - veroeff).days)
    return {"nach_monat": dict(sorted(monate.items())), "nach_region": dict(regionen.most_common()),
            "verfahren": dict(verfahren.most_common()), "angebotsfrist_median_tage": _median(fristen),
            "angebotsfrist_anzahl": len(fristen)}


def zuschlaege_auswerten(bekanntmachungen):
    gewinner, groessen, orte, angebote, werte = (collections.Counter(), collections.Counter(), collections.Counter(),
                                                 [], [])
    nicht_veroeffentlicht = 0
    angebote_unklar = 0
    for n in bekanntmachungen:
        for name in set(_texte(n.get("winner-name"))):
            gewinner[name] += 1
        for g in _liste(n.get("winner-size")):
            if g in GROESSEN:
                groessen[g] += 1
        for ort in _texte(n.get("winner-city")):
            orte[ort] += 1
        codes, werte_liste = _liste(n.get("received-submissions-type-code")), _liste(
            n.get("received-submissions-type-val"))
        if len(codes) == len(werte_liste):
            # Längen oben geprüft (zip(strict=True) gibt es erst ab Python 3.10, der Mac hat 3.9)
            for code, wert in zip(codes, werte_liste):  # noqa: B905
                if code == "tenders" and re.fullmatch(r"\d{1,4}", wert):
                    angebote.append(int(wert))
        else:
            angebote_unklar += 1  # Codes und Werte passen nicht zusammen – lieber nicht zählen als falsch zählen
        wert = n.get("total-value")
        if isinstance(wert, (int, float)) and not isinstance(wert, bool) and wert > 1:
            werte.append(float(wert))
        else:
            nicht_veroeffentlicht += 1
    verteilung = collections.Counter("1" if a <= 1 else "2–5" if a <= 5 else "6–10" if a <= 10 else "über 10"
                                     for a in angebote)
    return {
        "top": [{"name": name, "zuschlaege": anzahl} for name, anzahl in gewinner.most_common(15)],
        "anzahl_unternehmen": len(gewinner),
        "groessen": {g: groessen[g] for g in GROESSEN if groessen[g]},
        "orte_top": [{"ort": o, "anzahl": a} for o, a in orte.most_common(10)],
        "angebote_je_los": {"median": _median(angebote), "lose_mit_angabe": len(angebote),
                            "bekanntmachungen_mit_unklarer_angabe": angebote_unklar,
                            "verteilung": {b: verteilung[b] for b in ("1", "2–5", "6–10", "über 10") if verteilung[b]}},
        "werte": {"veroeffentlicht": len(werte), "nicht_veroeffentlicht": nicht_veroeffentlicht,
                  "median_eur": round(statistics.median(werte), 2) if werte else None,
                  "summe_eur": round(sum(werte), 2) if werte else None},
    }


def zielgruppen_auswerten(bekanntmachungen):
    arten, auftraggeber = collections.Counter(), collections.Counter()
    for n in bekanntmachungen:
        for code in set(_liste(n.get("buyer-legal-type"))):
            arten[code] += 1
        for name in set(_texte(n.get("buyer-name"))):
            auftraggeber[name] += 1
    return {"auftraggeber_arten": [{"code": c, "bezeichnung": AUFTRAGGEBER_ARTEN.get(c, "Sonstige (Code laut TED)"),
                                    "anzahl": a} for c, a in arten.most_common()],
            "top_auftraggeber": [{"name": n, "anzahl": a} for n, a in auftraggeber.most_common(15)]}


def anforderungen_zaehlen(bekanntmachungen):
    titel = [" ".join(_texte(n.get("notice-title"))).lower() for n in bekanntmachungen]
    begriffe = []
    for name, muster in BEGRIFFE:
        anzahl = sum(1 for t in titel if re.search(muster, t))
        if anzahl:
            begriffe.append({"begriff": name, "titel_anzahl": anzahl})
    begriffe.sort(key=lambda b: -b["titel_anzahl"])
    # „Unterhaltsreinigung“ bleibt auch bei 0 Treffern sichtbar (Kernleistung)
    if not any(b["begriff"] == "Unterhaltsreinigung" for b in begriffe):
        begriffe.append({"begriff": "Unterhaltsreinigung", "titel_anzahl": 0})
    return {"begriffe": begriffe, "titel_ausgewertet": len(titel)}


def gesammelt_auswerten(k, start):
    zeilen = k.db.alle("SELECT quelle, punkte, plz, vergabestelle FROM ausschreibungen WHERE gefunden >= ?",
                       (start.isoformat(),))
    quellen = collections.Counter(QUELLEN_NAMEN.get(z["quelle"], z["quelle"]) for z in zeilen)
    plz = collections.Counter((z["plz"] or "")[:2] for z in zeilen if z["plz"])
    stellen = collections.Counter(z["vergabestelle"] for z in zeilen if z["vergabestelle"])
    return {"anzahl": len(zeilen), "nach_quelle": dict(quellen.most_common()),
            "passend": sum(1 for z in zeilen if (z["punkte"] or 0) >= PASSEND_AB), "passend_ab_punkte": PASSEND_AB,
            "nach_plz_bereich": dict(plz.most_common(10)),
            "top_vergabestellen": [{"name": n, "anzahl": a} for n, a in stellen.most_common(10)]}


def _kurzfassung(kennzahlen, abschnitte):
    teile = ["%s EU-weite Ausschreibungen und %s Zuschläge laut TED (gezählt)." % (
        kennzahlen.get("ausschreibungen_ted_gesamt"), kennzahlen.get("zuschlaege_ted_gesamt"))]
    w = abschnitte["wettbewerber"]
    if w.get("verfuegbar") and w.get("top"):
        teile.append("Häufigster Zuschlagsempfänger: %s (%d)." % (w["top"][0]["name"], w["top"][0]["zuschlaege"]))
    if kennzahlen.get("angebote_je_los_median") is not None:
        teile.append("Median Angebote je Los: %s." % kennzahlen["angebote_je_los_median"])
    teile.append("Deutung offen – Hypothese, keine Entscheidung.")
    return " ".join(teile)


# ---------------------------------------------------------------------- Marktbericht: HTML (kein JS, escaped)
_CSS = (
    "*{box-sizing:border-box}body{margin:0;font-family:system-ui,-apple-system,'Segoe UI',Roboto,Arial,sans-serif;"
    "font-size:16px;line-height:1.55;color:#1f2937;background:#fff;overflow-wrap:break-word}"
    ".wrap{max-width:960px;margin:0 auto;padding:20px}h1{font-size:1.7rem;margin:.2em 0}"
    "h2{font-size:1.25rem;margin:1.6em 0 .4em;border-bottom:2px solid #0e7490;padding-bottom:.2em}"
    "h3{font-size:1.05rem;margin:1.1em 0 .3em}.leise{color:#4b5563;font-size:.92rem}"
    ".kopf{background:#0f172a;color:#fff;padding:20px}.kopf .wrap{padding:0 20px}"
    ".kacheln{display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:12px;margin:16px 0}"
    ".kachel{border:1px solid #e5e7eb;border-radius:12px;padding:12px 14px}.kachel b{display:block;font-size:1.5rem}"
    ".beleg{display:inline-block;font-size:.78rem;font-weight:700;border-radius:999px;padding:2px 10px;"
    "background:#ecfeff;color:#155e75;border:1px solid #a5f3fc}.beleg.aus{background:#fef2f2;color:#991b1b;"
    "border-color:#fecaca}table{width:100%;border-collapse:collapse;margin:8px 0 12px;font-size:.95rem}"
    "th,td{text-align:left;padding:6px 8px;border-bottom:1px solid #e5e7eb;vertical-align:top}"
    "td.zahl,th.zahl{text-align:right;white-space:nowrap}.balken{background:#e5e7eb;border-radius:4px;height:10px;"
    "min-width:60px}.balken span{display:block;height:10px;border-radius:4px;background:#0e7490}"
    ".annahme{background:#fffbeb;border:1px solid #fcd34d;border-radius:12px;padding:12px 16px}"
    ".ki{background:#f5f3ff;border:2px dashed #7c3aed;border-radius:12px;padding:12px 16px}"
    ".quelle{font-size:.88rem;word-break:break-all}.tabelle{overflow-x:auto}"
    "@media (max-width:520px){.wrap{padding:16px}th,td{padding:6px 4px}.balken{min-width:36px}"
    ".kachel b{font-size:1.3rem}}"
    "@media print{.kopf{background:none;color:#000}}"
)


def _tabelle(zeilen, kopf_links, kopf_rechts="Anzahl", mit_balken=True):
    if not zeilen:
        return '<p class="leise">Keine Daten.</p>'
    hoechst = max(z[1] for z in zeilen) or 1
    teile = ['<div class="tabelle"><table><thead><tr><th>%s</th><th class="zahl">%s</th>%s</tr></thead><tbody>'
             % (esc(kopf_links), esc(kopf_rechts), "<th>Anteil</th>" if mit_balken else "")]
    for name, zahl in zeilen:
        balken = ('<td><div class="balken"><span style="width:%d%%"></span></div></td>'
                  % max(2, round(100 * zahl / hoechst))) if mit_balken else ""
        teile.append('<tr><td>%s</td><td class="zahl">%s</td>%s</tr>' % (esc(name), esc(zahl), balken))
    teile.append("</tbody></table></div>")
    return "".join(teile)


def _zahl_text(wert):
    """Deutsche Schreibweise: 8.0 → „8“, 31.5 → „31,5“, None → „–“."""
    if wert is None:
        return "–"
    if isinstance(wert, float):
        return ("%d" % wert) if wert == int(wert) else ("%.1f" % wert).replace(".", ",")
    return str(wert)


def _datum_de(iso):
    s = str(iso or "")
    return "%s.%s.%s" % (s[8:10], s[5:7], s[0:4]) if re.match(r"\d{4}-\d{2}-\d{2}", s) else s


def _monat_de(jjjj_mm):
    s = str(jjjj_mm)
    return "%s/%s" % (s[5:7], s[0:4]) if re.match(r"\d{4}-\d{2}$", s) else s


def _euro(wert):
    if wert is None:
        return "–"
    return "{:,.0f} €".format(wert).replace(",", ".")


def _beleg(abschnitt):
    if abschnitt.get("beleg") == "gezählt":
        return '<span class="beleg">gezählt (belegt)</span>'
    return '<span class="beleg aus">nicht verfügbar</span>'


def bericht_html(d):
    kz, ab = d["kennzahlen"], d["abschnitte"]
    t = ['<!doctype html><html lang="de"><head><meta charset="utf-8">'
         '<meta name="viewport" content="width=device-width,initial-scale=1">'
         '<title>Marktbericht Reinigung – %s</title><style>%s</style></head><body>' % (esc(d["bis"]), _CSS),
         '<div class="kopf"><div class="wrap"><div class="leise" style="color:#cbd5e1">AUTONOMOUS · Research-Agent'
         '</div><h1>Marktbericht Reinigung (öffentliche Auftraggeber)</h1><div>Zeitraum %s bis %s · Region %s · '
         'abgerufen %s um %s Uhr</div></div></div><div class="wrap">'
         % (esc(_datum_de(d["von"])), esc(_datum_de(d["bis"])), esc(", ".join(d["region_nuts"])),
            esc(_datum_de(d["abgerufen"][:10])), esc(d["abgerufen"][11:16]))]
    t.append('<p class="leise">Alle Zahlen sind aus amtlichen Daten <b>gezählt</b> und mit Quelle belegt. '
             'Deutungen stehen getrennt unter „Annahmen“. Keine Rechts- oder Steuerberatung.</p>')
    t.append('<div class="kacheln">')
    for titel, wert in (("Ausschreibungen laut TED", kz.get("ausschreibungen_ted_gesamt")),
                        ("Zuschläge laut TED", kz.get("zuschlaege_ted_gesamt")),
                        ("Unternehmen mit Zuschlag", kz.get("wettbewerber_anzahl")),
                        ("Angebote je Los (Median)", kz.get("angebote_je_los_median")),
                        ("Angebotsfrist (Median, Tage)", kz.get("angebotsfrist_median_tage")),
                        ("Gesammelte Ausschreibungen", kz.get("gesammelte_ausschreibungen"))):
        t.append('<div class="kachel"><span class="leise">%s</span><b>%s</b></div>' % (esc(titel), esc(_zahl_text(wert))))
    t.append("</div>")
    if d.get("ki_zusammenfassung"):
        ki = d["ki_zusammenfassung"]
        t.append('<h2>KI-Zusammenfassung</h2><div class="ki"><p><b>%s</b></p><p>%s</p></div>'
                 % (esc(ki["kennzeichnung"]), esc(ki["text"]).replace("\n", "<br>")))
    else:
        t.append('<p class="leise">%s</p>' % esc(d.get("ki_hinweis") or ""))

    n = ab["nachfrage"]
    t.append("<h2>1. Nachfrage</h2>%s<p class=\"leise\">%s</p>" % (_beleg(n), esc(n.get("grundlage") or n.get("meldung"))))
    if n.get("beleg") == "gezählt":
        t.append("<h3>Ausschreibungen je Monat</h3>" + _tabelle(
            [(_monat_de(m), a) for m, a in n["nach_monat"].items()], "Monat"))
        t.append("<h3>Nach Regierungsbezirk</h3>" + _tabelle(list(n["nach_region"].items()), "Region"))
        t.append("<h3>Verfahrensart</h3>" + _tabelle(list(n["verfahren"].items()), "Verfahren"))
        t.append('<p>Angebotsfrist im Median: <b>%s Tage</b> (aus %d Ausschreibungen mit Frist).</p>'
                 % (esc(_zahl_text(n.get("angebotsfrist_median_tage"))), n.get("angebotsfrist_anzahl", 0)))

    w = ab["wettbewerber"]
    t.append("<h2>2. Wettbewerber (Zuschläge)</h2>%s<p class=\"leise\">%s</p>"
             % (_beleg(w), esc(w.get("grundlage") or w.get("meldung"))))
    if w.get("verfuegbar"):
        t.append("<h3>Häufigste Zuschlagsempfänger</h3>" + _tabelle(
            [(x["name"], x["zuschlaege"]) for x in w["top"]], "Unternehmen", "Zuschläge"))
        t.append("<h3>Unternehmensgröße (Angaben in den Bekanntmachungen)</h3>" + _tabelle(
            [({"micro": "Kleinst", "small": "Klein", "medium": "Mittel", "large": "Groß"}[g] + " (%s)" % g, a)
             for g, a in w["groessen"].items()], "Größe"))
        al = w["angebote_je_los"]
        t.append("<h3>Angebote je Los</h3><p>Median: <b>%s</b> (aus %d Losen mit Angabe).</p>"
                 % (esc(_zahl_text(al["median"])), al["lose_mit_angabe"]) +
                 _tabelle(list(al["verteilung"].items()), "Angebote je Los", "Lose"))
        wt = w["werte"]
        t.append("<h3>Auftragswerte</h3><p>Veröffentlicht: <b>%d</b> · nicht veröffentlicht (Platzhalter oder "
                 "fehlend): <b>%d</b> · Median der veröffentlichten Werte: <b>%s</b></p>"
                 % (wt["veroeffentlicht"], wt["nicht_veroeffentlicht"], esc(_euro(wt["median_eur"]))))
        t.append("<h3>Sitz der Zuschlagsempfänger</h3>" + _tabelle(
            [(x["ort"], x["anzahl"]) for x in w["orte_top"]], "Ort"))

    z = ab["zielgruppen"]
    t.append("<h2>3. Zielgruppen (Auftraggeber)</h2>%s<p class=\"leise\">%s</p>" % (_beleg(z), esc(z["grundlage"])))
    t.append(_tabelle([("%s (%s)" % (a["bezeichnung"], a["code"]), a["anzahl"]) for a in z["auftraggeber_arten"]],
                      "Art des Auftraggebers"))
    t.append("<h3>Häufigste Auftraggeber</h3>" + _tabelle(
        [(a["name"], a["anzahl"]) for a in z["top_auftraggeber"]], "Auftraggeber", mit_balken=False))

    a = ab["anforderungen"]
    t.append("<h2>4. Anforderungen der Kunden</h2>%s<p class=\"leise\">%s</p>" % (_beleg(a), esc(a["grundlage"])))
    t.append(_tabelle([(b["begriff"], b["titel_anzahl"]) for b in a["begriffe"]], "Begriff im Titel", "Titel"))

    g = ab["gesammelt"]
    t.append("<h2>5. Gesammelte Ausschreibungen (alle drei Quellen)</h2>%s<p class=\"leise\">%s</p>"
             % (_beleg(g), esc(g["grundlage"])))
    t.append("<p>Anzahl: <b>%d</b> · davon passend (ab %d Punkten): <b>%d</b></p>"
             % (g["anzahl"], g["passend_ab_punkte"], g["passend"]))
    t.append(_tabelle(list(g["nach_quelle"].items()), "Quelle"))

    t.append('<h2>Annahmen und Hinweise</h2><div class="annahme"><ul>%s</ul></div>'
             % "".join("<li>%s</li>" % esc(x) for x in d["annahmen"]))
    t.append("<h2>Quellen</h2>")
    for q in d["quellen"]:
        b = q.get("bewertung") or {}
        t.append('<div class="quelle"><p><b>%s</b><br>%s<br>Abgerufen: %s · Quellenbewertung: %s</p><ul>%s</ul>%s</div>'
                 % (esc(q["titel"]), esc(q["url"]), esc("%s um %s Uhr" % (_datum_de(q["abgerufen"][:10]),
                                                                        q["abgerufen"][11:16])), esc(b.get("stufe", "–")),
                    "".join("<li>Abfrage: <code>%s</code></li>" % esc(x) for x in q.get("abfragen") or []),
                    '<p class="leise">Fehler: %s</p>' % esc("; ".join(q["fehler"].values())) if q.get("fehler") else ""))
    t.append('<p class="leise">Erstellt von AUTONOMOUS (lokal). Bericht-ID %s.</p></div></body></html>'
             % esc(d["bericht_id"]))
    return "".join(t)
