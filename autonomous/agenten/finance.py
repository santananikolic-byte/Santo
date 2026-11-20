# -*- coding: utf-8 -*-
"""Finance-Agent: Auswertungen, Liquidität, Wirtschaftlichkeit, Simulationsbuchungen.

Darf KEINE realen Buchungen anlegen (das kann nur der Eigentümer). Simulierte Werte sind als
SIMULATION, erwartete Werte als ERWARTET gekennzeichnet."""

from . import Agent
from ..wallet import betrag_in_cent, euro


class FinanceAgent(Agent):
    rolle = "finance"
    name = "Finance-Agent"
    beschreibung = "Budgets, Liquiditätsübersichten, Wirtschaftlichkeit; bucht nur im Simulations-Wallet."
    rechte = frozenset({"interne_auswertung", "wallet_simulation", "gedaechtnis_vorschlag"})
    aufgabentypen = {
        "finanzbericht": "Reale Finanzen, Forderungen, Budgets und Simulation getrennt zusammenfassen",
        "liquiditaet": "Liquiditätsvorschau (Eingabe optional: tage)",
        "wirtschaftlichkeit": "Deckungsbeitrag eines Angebots (Eingabe: preis, stunden, stundensatz, kosten)",
        "simulation_buchen": "Simulierte Buchung im internen Wallet (Eingabe: art, betrag, kategorie, begruendung)",
    }

    def aufgabe_finanzbericht(self, aufgabe, k):
        self.darf(k, "interne_auswertung", "finanzbericht", aufgabe)
        real = k.finanzen.uebersicht()
        return {"real": real, "forderungen_offen": [f for f in k.finanzen.forderungen() if f["status"] == "offen"],
                "simulation": k.wallet.uebersicht(),
                "trennung": "REAL und SIMULATION werden getrennt berechnet und nie addiert."}

    def aufgabe_liquiditaet(self, aufgabe, k):
        self.darf(k, "interne_auswertung", "liquiditaet", aufgabe)
        tage = int(aufgabe["eingabe"].get("tage", 30))
        if not 1 <= tage <= 365:
            raise ValueError("tage 1 bis 365")
        return k.finanzen.liquiditaet(tage)

    def aufgabe_wirtschaftlichkeit(self, aufgabe, k):
        self.darf(k, "interne_auswertung", "wirtschaftlichkeit", aufgabe)
        e = aufgabe["eingabe"]
        if e.get("preis") in (None, ""):
            raise ValueError("Preis fehlt.")
        preis = betrag_in_cent(e["preis"])
        kosten = betrag_in_cent(e["kosten"]) if e.get("kosten") not in (None, "", 0, "0") else 0
        stunden = float(e.get("stunden") or 0)
        ergebnis = {"preis": euro(preis), "direkte_kosten": euro(kosten), "stunden": stunden}
        db = preis - kosten
        ergebnis["deckungsbeitrag"] = euro(db)
        if stunden > 0:
            ergebnis["erloes_je_stunde"] = euro(round(db / stunden))
        if e.get("stundensatz") in (None, ""):
            ergebnis["stundensatz"] = "OFFEN – nicht festgelegt, daher kein Vergleich mit Soll-Stundensatz"
        else:
            soll = betrag_in_cent(e["stundensatz"])
            ergebnis["stundensatz"] = euro(soll)
            if stunden > 0:
                ergebnis["lohnt_sich"] = db / stunden >= soll
        ergebnis["hinweis"] = "Rechnung nur mit den eingegebenen Werten; keine angenommenen Zahlen."
        return ergebnis

    def aufgabe_simulation_buchen(self, aufgabe, k):
        e = aufgabe["eingabe"]
        self.darf(k, "wallet_simulation", "wallet", aufgabe)
        return k.wallet.buchen(e.get("art"), e.get("betrag"), e.get("kategorie", ""), e.get("begruendung", ""),
                               self.rolle)
