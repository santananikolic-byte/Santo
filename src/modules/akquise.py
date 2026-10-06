#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Akquise - Aufträge hereinholen und den Cashflow daraus vorhersagen.

Das ist der Teil, der Geld bringt. Bewertung allein hilft nicht: Es braucht
eine Pipeline, die weiß, wer wann wieder angerufen werden muss, eine
Kalkulation, die aus Quadratmetern einen belastbaren Monatspreis macht, und
eine Vorhersage, die sagt, was in drei Monaten auf dem Konto ist.

Die Kalkulation rechnet, wie in der Branche wirklich gerechnet wird: über
Leistungswerte. Ein Reiniger schafft je nach Bodenbelag eine bestimmte Fläche
pro Stunde. Daraus ergeben sich Stunden, daraus der Preis. Wer stattdessen
einen Quadratmeterpreis rät, verkalkuliert sich beim ersten Sonderfall.
"""

import json
from datetime import datetime, timedelta

from modules.memory import Memory, db_schema_anlegen, heute_datum, zeitstempel

SCHEMA_AKQUISE = """
CREATE TABLE IF NOT EXISTS leads (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    firma TEXT NOT NULL,
    ansprechpartner TEXT DEFAULT '',
    telefon TEXT DEFAULT '',
    email TEXT DEFAULT '',
    adresse TEXT DEFAULT '',
    quelle TEXT DEFAULT '',
    objekt_qm REAL DEFAULT 0,
    bodenbelag TEXT DEFAULT '',
    intervall_pro_woche REAL DEFAULT 0,
    sonderleistungen TEXT DEFAULT '',
    stufe TEXT DEFAULT 'neu',
    wert_monat REAL DEFAULT 0,
    naechster_schritt TEXT DEFAULT '',
    naechster_kontakt TEXT DEFAULT '',
    notiz TEXT DEFAULT '',
    angelegt TEXT NOT NULL,
    geaendert TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS angebote (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    lead_id INTEGER,
    datum TEXT NOT NULL,
    qm REAL DEFAULT 0,
    bodenbelag TEXT DEFAULT '',
    intervall_pro_woche REAL DEFAULT 0,
    stundensatz REAL DEFAULT 0,
    stunden_monat REAL DEFAULT 0,
    netto_monat REAL DEFAULT 0,
    brutto_monat REAL DEFAULT 0,
    posten TEXT DEFAULT '',
    status TEXT DEFAULT 'entwurf',
    notiz TEXT DEFAULT '',
    angelegt TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_leads_stufe ON leads(stufe);
CREATE INDEX IF NOT EXISTS idx_leads_kontakt ON leads(naechster_kontakt);
"""

# Die Stufen, die ein Interessent durchläuft. Reihenfolge ist bewusst:
# sie bestimmt auch, wie wahrscheinlich ein Abschluss ist.
STUFEN = ["neu", "kontaktiert", "besichtigt", "angebot", "nachfassen",
          "gewonnen", "verloren"]

# Erfahrungswerte, wie sicher eine Stufe zum Auftrag führt. Bewusst
# zurückhaltend: eine zu optimistische Pipeline führt zu Fehlplanung.
WAHRSCHEINLICHKEIT = {"neu": 0.10, "kontaktiert": 0.20, "besichtigt": 0.40,
                      "angebot": 0.60, "nachfassen": 0.45, "gewonnen": 1.0,
                      "verloren": 0.0}

# Wie viele Tage nach dem letzten Schritt nachgefasst werden sollte.
NACHFASS_TAGE = {"neu": 2, "kontaktiert": 3, "besichtigt": 2, "angebot": 5,
                 "nachfassen": 7}

# Leistungswerte in Quadratmetern je Stunde. So rechnet die Branche.
LEISTUNGSWERTE = {
    "teppich": 350.0,
    "hartboden": 300.0,
    "linoleum": 300.0,
    "pvc": 300.0,
    "fliesen": 280.0,
    "naturstein": 250.0,
    "beton": 250.0,
    "parkett": 260.0,
    "treppenhaus": 150.0,
    "sanitaer": 80.0,
    "sanitär": 80.0,
    "kueche": 120.0,
    "küche": 120.0,
    "halle": 500.0,
    "industrie": 500.0,
}
LEISTUNG_STANDARD = 280.0

# Sonderleistungen, die getrennt berechnet werden. Wert ist Euro je Einheit.
SONDERLEISTUNGEN = {
    "fensterreinigung": ("je Fensterflügel", 3.50),
    "grundreinigung": ("je Quadratmeter", 2.80),
    "teppichreinigung": ("je Quadratmeter", 2.20),
    "bauschlussreinigung": ("je Quadratmeter", 4.50),
}

WOCHEN_PRO_MONAT = 4.33
MATERIALZUSCHLAG = 0.04   # Reinigungsmittel, Tücher, Verbrauch
STUNDENSATZ_STANDARD = 32.0


def leistungswert(bodenbelag: str) -> float:
    """Quadratmeter je Stunde für einen Bodenbelag."""
    schluessel = (bodenbelag or "").strip().lower()
    for name, wert in LEISTUNGSWERTE.items():
        if name in schluessel:
            return wert
    return LEISTUNG_STANDARD


def geld(betrag) -> str:
    """Deutscher Betrag mit Euro-Zeichen."""
    try:
        betrag = float(betrag)
    except (TypeError, ValueError):
        betrag = 0.0
    return ("{:,.2f}".format(betrag).replace(",", "#").replace(".", ",")
            .replace("#", ".")) + " €"


class Akquise:
    """Führt die Pipeline, kalkuliert Angebote und sagt den Cashflow vorher."""

    def __init__(self, memory: Memory = None, mwst_satz: float = 20.0):
        self.memory = memory or Memory()
        self.mwst_satz = float(mwst_satz)
        db_schema_anlegen(SCHEMA_AKQUISE, self.memory.db_pfad)

    # -- Kalkulation --------------------------------------------------------

    def angebot_kalkulieren(self, qm: float, bodenbelag: str = "",
                            intervall_pro_woche: float = 1.0,
                            stundensatz: float = None,
                            sonderleistungen: dict = None) -> dict:
        """Rechnet aus Fläche, Belag und Intervall einen Monatspreis.

        Der Weg: Fläche geteilt durch Leistungswert ergibt Stunden je
        Reinigung. Mal Reinigungen im Monat ergibt Monatsstunden. Mal
        Stundensatz ergibt den Preis. Sonderleistungen kommen getrennt dazu,
        weil sie nicht im Intervall stecken.
        """
        try:
            qm = float(qm)
        except (TypeError, ValueError):
            return {"ok": False, "fehler": "Die Quadratmeter sind keine Zahl."}
        if qm <= 0:
            return {"ok": False,
                    "fehler": "Ohne Quadratmeter kann ich nicht kalkulieren. "
                              "Frag beim Objekt nach der Fläche."}
        try:
            intervall = float(intervall_pro_woche)
        except (TypeError, ValueError):
            intervall = 1.0
        if intervall <= 0:
            return {"ok": False,
                    "fehler": "Wie oft pro Woche soll gereinigt werden? Ohne das "
                              "gibt es keinen Monatspreis."}
        satz = float(stundensatz) if stundensatz else STUNDENSATZ_STANDARD

        leistung = leistungswert(bodenbelag)
        stunden_je_reinigung = qm / leistung
        reinigungen_monat = intervall * WOCHEN_PRO_MONAT
        stunden_monat = stunden_je_reinigung * reinigungen_monat
        lohn = stunden_monat * satz
        material = lohn * MATERIALZUSCHLAG

        posten = [
            {"bezeichnung": "Unterhaltsreinigung %.0f m² bei %s, %gx pro Woche"
                            % (qm, bodenbelag or "Standardbelag", intervall),
             "menge": round(stunden_monat, 2), "einheit": "Stunden",
             "einzelpreis": satz, "betrag": round(lohn, 2)},
            {"bezeichnung": "Reinigungsmittel und Verbrauchsmaterial",
             "menge": 1, "einheit": "pauschal",
             "einzelpreis": round(material, 2), "betrag": round(material, 2)},
        ]

        einmalig = 0.0
        for name, menge in (sonderleistungen or {}).items():
            schluessel = str(name).strip().lower()
            if schluessel not in SONDERLEISTUNGEN:
                continue
            einheit, preis = SONDERLEISTUNGEN[schluessel]
            try:
                menge = float(menge)
            except (TypeError, ValueError):
                continue
            if menge <= 0:
                continue
            betrag = menge * preis
            einmalig += betrag
            posten.append({"bezeichnung": "%s (%s)" % (name.capitalize(), einheit),
                           "menge": menge, "einheit": einheit,
                           "einzelpreis": preis, "betrag": round(betrag, 2)})

        netto_monat = round(lohn + material, 2)
        mwst_monat = round(netto_monat * self.mwst_satz / 100.0, 2)
        brutto_monat = round(netto_monat + mwst_monat, 2)
        netto_einmalig = round(einmalig, 2)

        return {
            "ok": True,
            "qm": qm, "bodenbelag": bodenbelag or "Standardbelag",
            "leistungswert": leistung,
            "intervall_pro_woche": intervall,
            "stundensatz": satz,
            "stunden_je_reinigung": round(stunden_je_reinigung, 2),
            "reinigungen_monat": round(reinigungen_monat, 1),
            "stunden_monat": round(stunden_monat, 2),
            "netto_monat": netto_monat,
            "mwst_monat": mwst_monat,
            "brutto_monat": brutto_monat,
            "einmalig_netto": netto_einmalig,
            "jahreswert_netto": round(netto_monat * 12 + netto_einmalig, 2),
            "qm_preis_monat": round(netto_monat / qm, 3),
            "posten": posten,
            "text": ("%.0f Quadratmeter %s, %gmal die Woche: das sind %.1f Stunden "
                     "im Monat. Bei %s Stundensatz macht das %s netto im Monat, "
                     "%s brutto. Im Jahr %s netto.%s"
                     % (qm, bodenbelag or "Standardbelag", intervall, stunden_monat,
                        geld(satz), geld(netto_monat), geld(brutto_monat),
                        geld(netto_monat * 12),
                        (" Dazu einmalig %s für Sonderleistungen."
                         % geld(netto_einmalig)) if netto_einmalig else "")),
        }

    def angebotstext(self, kalkulation: dict, firma: str = "",
                     ansprechpartner: str = "") -> str:
        """Formt aus der Kalkulation ein Angebot, das man verschicken kann."""
        if not kalkulation.get("ok"):
            return kalkulation.get("fehler", "Die Kalkulation fehlt.")
        zeilen = []
        anrede = ("Sehr geehrte Damen und Herren," if not ansprechpartner
                  else "Sehr geehrte/r %s," % ansprechpartner)
        zeilen.append(anrede)
        zeilen.append("")
        zeilen.append("vielen Dank für Ihr Interesse. Für die Reinigung Ihres "
                      "Objekts%s unterbreite ich Ihnen folgendes Angebot:"
                      % (" (%s)" % firma if firma else ""))
        zeilen.append("")
        for posten in kalkulation["posten"]:
            zeilen.append("  %-52s %12s"
                          % (posten["bezeichnung"][:52], geld(posten["betrag"])))
        zeilen.append("")
        zeilen.append("  %-52s %12s" % ("Monatlich netto", geld(kalkulation["netto_monat"])))
        zeilen.append("  %-52s %12s" % ("Mehrwertsteuer %g Prozent" % self.mwst_satz,
                                        geld(kalkulation["mwst_monat"])))
        zeilen.append("  %-52s %12s" % ("Monatlich brutto",
                                        geld(kalkulation["brutto_monat"])))
        if kalkulation["einmalig_netto"]:
            zeilen.append("  %-52s %12s" % ("Einmalige Sonderleistungen netto",
                                            geld(kalkulation["einmalig_netto"])))
        zeilen.append("")
        zeilen.append("Der Preis beruht auf %.1f Arbeitsstunden im Monat "
                      "(%.0f m² bei %gmaliger Reinigung pro Woche)."
                      % (kalkulation["stunden_monat"], kalkulation["qm"],
                         kalkulation["intervall_pro_woche"]))
        zeilen.append("Gerne führe ich vorab eine kostenlose Probereinigung durch, "
                      "damit Sie die Qualität beurteilen können.")
        zeilen.append("")
        zeilen.append("Mit freundlichen Grüßen")
        return "\n".join(zeilen)

    # -- Pipeline -----------------------------------------------------------

    def lead_anlegen(self, firma: str, ansprechpartner: str = "", telefon: str = "",
                     email: str = "", adresse: str = "", quelle: str = "",
                     objekt_qm: float = 0, bodenbelag: str = "",
                     intervall_pro_woche: float = 0, notiz: str = "",
                     naechster_schritt: str = "") -> dict:
        """Nimmt einen Interessenten auf."""
        firma = (firma or "").strip()
        if not firma:
            return {"ok": False, "fehler": "Der Interessent braucht einen Namen."}
        vorhanden = self.memory._lesen(
            "SELECT id FROM leads WHERE lower(firma)=lower(?) LIMIT 1", (firma,))
        if vorhanden:
            return {"ok": False, "id": vorhanden[0]["id"],
                    "fehler": "%s steht schon in der Liste." % firma}
        try:
            qm = float(objekt_qm or 0)
        except (TypeError, ValueError):
            qm = 0.0
        try:
            intervall = float(intervall_pro_woche or 0)
        except (TypeError, ValueError):
            intervall = 0.0

        wert = 0.0
        if qm > 0 and intervall > 0:
            kalkulation = self.angebot_kalkulieren(qm, bodenbelag, intervall)
            if kalkulation.get("ok"):
                wert = kalkulation["netto_monat"]

        faellig = (datetime.now() + timedelta(days=NACHFASS_TAGE["neu"])
                   ).strftime("%Y-%m-%d")
        nummer = self.memory._schreiben(
            "INSERT INTO leads (firma, ansprechpartner, telefon, email, adresse, "
            "quelle, objekt_qm, bodenbelag, intervall_pro_woche, sonderleistungen, "
            "stufe, wert_monat, naechster_schritt, naechster_kontakt, notiz, "
            "angelegt, geaendert) VALUES (?,?,?,?,?,?,?,?,?,'','neu',?,?,?,?,?,?)",
            (firma, ansprechpartner, telefon, email, adresse, quelle, qm, bodenbelag,
             intervall, wert, naechster_schritt or "anrufen und Termin vereinbaren",
             faellig, notiz, zeitstempel(), zeitstempel()))
        return {"ok": True, "id": nummer, "firma": firma, "wert_monat": wert,
                "text": "%s ist aufgenommen.%s Nächster Schritt bis %s: %s"
                        % (firma,
                           (" Geschätzter Wert %s im Monat." % geld(wert)) if wert else "",
                           faellig, naechster_schritt or "anrufen und Termin vereinbaren")}

    def lead_finden(self, name: str):
        """Sucht einen Interessenten - auch bei ungenauem Namen."""
        name = (name or "").strip()
        if not name:
            return None
        genau = self.memory._lesen(
            "SELECT * FROM leads WHERE lower(firma)=lower(?) LIMIT 1", (name,))
        if genau:
            return genau[0]
        teil = self.memory._lesen(
            "SELECT * FROM leads WHERE firma LIKE ? OR ansprechpartner LIKE ? "
            "ORDER BY geaendert DESC LIMIT 1",
            ("%%%s%%" % name, "%%%s%%" % name))
        return teil[0] if teil else None

    def lead_weiterstufen(self, name: str, stufe: str, notiz: str = "",
                          naechster_schritt: str = "",
                          wert_monat: float = None) -> dict:
        """Setzt einen Interessenten auf die nächste Stufe."""
        stufe = (stufe or "").strip().lower()
        if stufe not in STUFEN:
            return {"ok": False,
                    "fehler": "'%s' ist keine Stufe. Möglich: %s."
                              % (stufe, ", ".join(STUFEN))}
        lead = self.lead_finden(name)
        if lead is None:
            return {"ok": False, "fehler": "'%s' steht nicht in der Liste." % name}

        tage = NACHFASS_TAGE.get(stufe, 0)
        faellig = ((datetime.now() + timedelta(days=tage)).strftime("%Y-%m-%d")
                   if tage else "")
        neuer_wert = lead["wert_monat"] if wert_monat is None else float(wert_monat)
        neue_notiz = ("%s | %s" % (lead["notiz"], notiz)).strip(" |") if notiz \
            else lead["notiz"]

        self.memory._schreiben(
            "UPDATE leads SET stufe=?, notiz=?, naechster_schritt=?, "
            "naechster_kontakt=?, wert_monat=?, geaendert=? WHERE id=?",
            (stufe, neue_notiz, naechster_schritt or lead["naechster_schritt"],
             faellig, neuer_wert, zeitstempel(), lead["id"]))

        if stufe == "gewonnen":
            text = ("%s ist gewonnen. %s im Monat, das sind %s im Jahr."
                    % (lead["firma"], geld(neuer_wert), geld(neuer_wert * 12)))
        elif stufe == "verloren":
            text = "%s ist verloren. %s" % (lead["firma"], notiz or "")
        else:
            text = ("%s steht jetzt auf %s.%s"
                    % (lead["firma"], stufe,
                       (" Wieder melden bis %s: %s" % (faellig, naechster_schritt))
                       if faellig and naechster_schritt else ""))
        return {"ok": True, "id": lead["id"], "stufe": stufe, "text": text}

    def pipeline(self) -> dict:
        """Alle Interessenten nach Stufen, mit Werten."""
        zeilen = self.memory._lesen("SELECT * FROM leads ORDER BY wert_monat DESC")
        nach_stufe = {stufe: [] for stufe in STUFEN}
        for zeile in zeilen:
            nach_stufe.setdefault(zeile["stufe"], []).append(zeile)

        offen = [z for z in zeilen if z["stufe"] not in ("gewonnen", "verloren")]
        gewichtet = sum(z["wert_monat"] * WAHRSCHEINLICHKEIT.get(z["stufe"], 0)
                        for z in offen)
        gewonnen = [z for z in zeilen if z["stufe"] == "gewonnen"]
        laufend = sum(z["wert_monat"] for z in gewonnen)

        uebersicht = {}
        for stufe in STUFEN:
            eintraege = nach_stufe.get(stufe, [])
            uebersicht[stufe] = {
                "anzahl": len(eintraege),
                "wert_monat": round(sum(e["wert_monat"] for e in eintraege), 2),
                "firmen": [e["firma"] for e in eintraege[:6]]}

        return {"ok": True, "stufen": uebersicht,
                "offen": len(offen),
                "offener_wert_monat": round(sum(z["wert_monat"] for z in offen), 2),
                "gewichteter_wert_monat": round(gewichtet, 2),
                "laufender_umsatz_monat": round(laufend, 2),
                "text": ("%d Interessenten offen über %s im Monat. Realistisch "
                         "gewichtet sind das %s. Laufend gesichert: %s im Monat "
                         "aus %d Aufträgen."
                         % (len(offen), geld(sum(z["wert_monat"] for z in offen)),
                            geld(gewichtet), geld(laufend), len(gewonnen)))}

    def nachfassliste(self, bis: str = "") -> dict:
        """Wer heute dran ist - und warum.

        Das ist die Liste, die morgens zählt. Ein Interessent, bei dem niemand
        nachfasst, ist verloren, ohne dass es jemand merkt.
        """
        grenze = bis or heute_datum()
        zeilen = self.memory._lesen(
            "SELECT * FROM leads WHERE stufe NOT IN ('gewonnen','verloren') "
            "AND naechster_kontakt<>'' AND naechster_kontakt<=? "
            "ORDER BY wert_monat DESC", (grenze,))
        eintraege = []
        for zeile in zeilen:
            try:
                faellig_seit = (datetime.strptime(grenze, "%Y-%m-%d") -
                                datetime.strptime(zeile["naechster_kontakt"],
                                                  "%Y-%m-%d")).days
            except ValueError:
                faellig_seit = 0
            eintraege.append({
                "id": zeile["id"], "firma": zeile["firma"],
                "ansprechpartner": zeile["ansprechpartner"],
                "telefon": zeile["telefon"], "stufe": zeile["stufe"],
                "wert_monat": zeile["wert_monat"],
                "seit_tagen": faellig_seit,
                "schritt": zeile["naechster_schritt"]})

        if not eintraege:
            text = "Heute ist niemand zum Nachfassen fällig."
        else:
            erster = eintraege[0]
            text = ("%d Interessenten sind fällig, zusammen %s im Monat. "
                    "Fang mit %s an: %s%s"
                    % (len(eintraege),
                       geld(sum(e["wert_monat"] for e in eintraege)),
                       erster["firma"], erster["schritt"],
                       (" Der Termin ist seit %d Tagen überfällig."
                        % erster["seit_tagen"]) if erster["seit_tagen"] > 0 else ""))
        return {"ok": True, "anzahl": len(eintraege), "eintraege": eintraege,
                "text": text}

    # -- Neue Interessenten finden -----------------------------------------

    def leads_finden(self, ort: str, branche: str = "", anzahl: int = 8,
                     welt=None, agent=None) -> dict:
        """Sucht Betriebe in einem Ort, die Reinigung brauchen könnten.

        Der Weg: über den Such-Dienst nach Betrieben suchen, die Trefferliste
        von Claude in Name, Adresse und Telefon zerlegen lassen und daraus
        Interessenten anlegen. Was schon in der Liste steht, wird übersprungen.

        **Was das ist und was nicht:** Das sind Betriebe, die es gibt - keine
        Interessenten. Ob sie überhaupt Bedarf haben, weiß niemand, bis
        angerufen wurde. Deshalb landen sie auf der Stufe 'neu' mit dem
        nächsten Schritt "anrufen", und ihr Wert steht auf null, bis die
        Quadratmeter bekannt sind. Eine Pipeline mit geschätzten Werten für
        Betriebe, mit denen nie jemand gesprochen hat, wäre eine Lüge.
        """
        ort = (ort or "").strip()
        if not ort:
            return {"ok": False, "fehler": "In welchem Ort soll ich suchen?"}
        if welt is None:
            return {"ok": False, "fehler": "Die Suche ist nicht verfügbar."}

        # Zuerst die Karte: echte Betriebe mit Adresse, ohne Schlüssel und ohne Raten.
        if hasattr(welt, "betriebe_suchen"):
            karte = welt.betriebe_suchen(ort, branche, anzahl)
            if karte.get("ok") and karte.get("betriebe"):
                return self._betriebe_aufnehmen(karte["betriebe"], ort, "Karte (OpenStreetMap)")

        if agent is None or not getattr(agent, "einsatzbereit", lambda: False)():
            return {"ok": False,
                    "fehler": "Ohne Anthropic-Schlüssel kann ich die Treffer nicht "
                              "auswerten."}

        branchen = branche.strip() if branche else \
            "Arztpraxen, Steuerberater, Kanzleien, Autohäuser, Fitnessstudios"
        anfrage = ("%s in %s mit Adresse und Telefonnummer" % (branchen, ort))
        gefunden = welt.recherche(anfrage)
        if not gefunden.get("ok"):
            return {"ok": False,
                    "fehler": "Für die Suche fehlt der Such-Dienst. In "
                              "config/mcp_servers.json den Eintrag 'suche' auf "
                              "\"aus\": false stellen und einen Brave-Schlüssel "
                              "eintragen. (%s)" % gefunden.get("fehler", "")[:80]}

        auftrag = (
            "Aus dieser Trefferliste sollen Betriebe für die Kaltakquise einer "
            "Gebäudereinigung herausgezogen werden.\n\n"
            "Gib ausschließlich JSON zurück: {\"betriebe\": [{\"firma\": ..., "
            "\"branche\": ..., \"adresse\": ..., \"telefon\": ...}]}\n\n"
            "Nimm höchstens %d Betriebe. Nimm nur echte, benannte Betriebe mit "
            "Ortsbezug - keine Verzeichnisse, keine Portale, keine "
            "Sammelseiten. Fehlt eine Telefonnummer oder Adresse, lass das Feld "
            "leer, statt etwas zu erfinden.\n\nTrefferliste:\n%s"
            % (int(anzahl or 8), gefunden.get("text", "")[:6000]))
        antwort = agent.json_anfrage(auftrag)
        if not antwort.get("ok"):
            return {"ok": False,
                    "fehler": "Die Trefferliste war nicht auswertbar: %s"
                              % antwort.get("fehler", "")}

        betriebe = (antwort["daten"] or {}).get("betriebe") or []
        return self._betriebe_aufnehmen(betriebe[:int(anzahl or 8)], ort, "Recherche")

    def _betriebe_aufnehmen(self, betriebe: list, ort: str, quelle: str) -> dict:
        """Nimmt gefundene Betriebe als Interessenten auf - Wert null, nächster Schritt: anrufen."""
        neu, bekannt = [], []
        for eintrag in betriebe:
            firma = str(eintrag.get("firma") or "").strip()
            if not firma:
                continue
            ergebnis = self.lead_anlegen(
                firma, telefon=str(eintrag.get("telefon") or ""),
                adresse=str(eintrag.get("adresse") or ""),
                quelle="%s %s" % (quelle, ort),
                notiz=" · ".join(x for x in (str(eintrag.get("branche") or ""),
                                              str(eintrag.get("web") or ""),
                                              str(eintrag.get("mail") or "")) if x),
                naechster_schritt="anrufen und fragen, wer die Reinigung macht")
            if ergebnis.get("ok"):
                neu.append(firma)
            else:
                bekannt.append(firma)

        if not neu:
            text = ("Ich habe %d Betriebe gefunden, aber keiner ist neu%s."
                    % (len(betriebe), " - alle stehen schon in der Liste"
                       if bekannt else ""))
        else:
            text = ("%d neue Betriebe in %s aufgenommen: %s. Sie stehen auf 'neu' "
                    "mit Wert null - was sie wert sind, weißt du erst nach dem "
                    "Anruf.%s"
                    % (len(neu), ort, ", ".join(neu[:5]),
                       (" %d kanntest du schon." % len(bekannt)) if bekannt else ""))
        return {"ok": True, "neu": neu, "bekannt": bekannt,
                "gefunden": len(betriebe), "text": text}

    # -- Cashflow -----------------------------------------------------------

    def cashflow_prognose(self, monate: int = 6, bookkeeping=None) -> dict:
        """Was in den nächsten Monaten hereinkommt.

        Gesichert sind die gewonnenen Aufträge - die laufen weiter. Dazu kommt
        die Pipeline, aber nur gewichtet nach Stufe. Ein Angebot ist kein Geld,
        und so wird es hier auch behandelt.
        """
        monate = max(1, min(24, int(monate or 6)))
        gewonnen = self.memory._lesen(
            "SELECT * FROM leads WHERE stufe='gewonnen'")
        offen = self.memory._lesen(
            "SELECT * FROM leads WHERE stufe NOT IN ('gewonnen','verloren')")

        gesichert = sum(z["wert_monat"] for z in gewonnen)
        gewichtet = sum(z["wert_monat"] * WAHRSCHEINLICHKEIT.get(z["stufe"], 0)
                        for z in offen)

        # Laufende Kosten aus der Buchhaltung, sofern vorhanden.
        kosten_monat = 0.0
        kostenquelle = "keine Buchhaltungsdaten"
        if bookkeeping is not None:
            try:
                verlauf = bookkeeping.monatsverlauf(3)
                ausgaben = [a for a in verlauf.get("einnahmen", [])]
                del ausgaben
                gesamt = bookkeeping.auswertung(
                    (datetime.now() - timedelta(days=90)).strftime("%Y-%m-%d"),
                    heute_datum())
                if gesamt.get("anzahl"):
                    kosten_monat = round(gesamt["ausgaben"] / 3.0, 2)
                    kostenquelle = "Durchschnitt der letzten 3 Monate"
            except Exception:
                kosten_monat = 0.0

        reihe = []
        jetzt = datetime.now()
        for versatz in range(monate):
            jahr, monat = jetzt.year, jetzt.month + versatz
            while monat > 12:
                monat -= 12
                jahr += 1
            # Neue Abschlüsse brauchen Anlaufzeit: im ersten Monat wirkt die
            # Pipeline noch nicht, danach steigt sie langsam ein.
            anteil = 0.0 if versatz == 0 else min(1.0, versatz / 3.0)
            erwartet = gesichert + gewichtet * anteil
            reihe.append({
                "monat": "%04d-%02d" % (jahr, monat),
                "gesichert": round(gesichert, 2),
                "aus_pipeline": round(gewichtet * anteil, 2),
                "einnahmen": round(erwartet, 2),
                "kosten": kosten_monat,
                "ergebnis": round(erwartet - kosten_monat, 2)})

        return {"ok": True, "monate": reihe,
                "gesichert_monat": round(gesichert, 2),
                "pipeline_gewichtet": round(gewichtet, 2),
                "kosten_monat": kosten_monat, "kostenquelle": kostenquelle,
                "text": ("Gesichert laufen %s im Monat herein. Aus der Pipeline "
                         "kommen realistisch %s dazu, aber erst über zwei bis drei "
                         "Monate. Bei Kosten von %s im Monat (%s) bleiben in %d "
                         "Monaten etwa %s übrig."
                         % (geld(gesichert), geld(gewichtet), geld(kosten_monat),
                            kostenquelle, monate,
                            geld(sum(m["ergebnis"] for m in reihe))))}

    def angebot_ablegen(self, lead_name: str, kalkulation: dict,
                        notiz: str = "") -> dict:
        """Legt ein kalkuliertes Angebot zum Interessenten ab."""
        if not kalkulation.get("ok"):
            return {"ok": False, "fehler": "Die Kalkulation ist nicht gültig."}
        lead = self.lead_finden(lead_name)
        nummer = self.memory._schreiben(
            "INSERT INTO angebote (lead_id, datum, qm, bodenbelag, "
            "intervall_pro_woche, stundensatz, stunden_monat, netto_monat, "
            "brutto_monat, posten, status, notiz, angelegt) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,'entwurf',?,?)",
            (lead["id"] if lead else None, heute_datum(), kalkulation["qm"],
             kalkulation["bodenbelag"], kalkulation["intervall_pro_woche"],
             kalkulation["stundensatz"], kalkulation["stunden_monat"],
             kalkulation["netto_monat"], kalkulation["brutto_monat"],
             json.dumps(kalkulation["posten"], ensure_ascii=False), notiz,
             zeitstempel()))
        if lead is not None:
            self.lead_weiterstufen(lead["firma"], "angebot",
                                   naechster_schritt="Angebot nachfassen",
                                   wert_monat=kalkulation["netto_monat"])
        return {"ok": True, "id": nummer,
                "text": "Angebot über %s im Monat abgelegt%s."
                        % (geld(kalkulation["netto_monat"]),
                           (" für %s" % lead["firma"]) if lead else "")}
