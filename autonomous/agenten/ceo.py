# -*- coding: utf-8 -*-
"""CEO-Agent: Ziele, Prioritäten, Tagesplan, Kennzahlen, Aufgabenverteilung.

Arbeitet deterministisch aus echten Daten. Erfindet keine Ergebnisse: alles im Plan stammt aus
der Datenbank; Empfehlungen werden als VORSCHLAG gespeichert, Entscheidungen trifft der Eigentümer."""

from . import Agent
from ..wallet import euro


class CeoAgent(Agent):
    rolle = "ceo"
    name = "CEO-Agent"
    beschreibung = "Verwaltet Ziele, Prioritäten und Aufgabenverteilung; erstellt Tagesplan und Kennzahlen."
    rechte = frozenset({"interne_planung", "interne_auswertung", "gedaechtnis_vorschlag", "lokale_recherche",
                        "lokales_modell"})
    aufgabentypen = {
        "tagesplan": "Nachvollziehbaren Tages- und Aufgabenplan aus echten Daten erstellen",
        "kennzahlen": "Unternehmenskennzahlen berechnen",
        "auftrag_verteilen": "Aufgabe an eine Rolle übergeben (Eingabe: rolle, typ, titel, eingabe)",
        "chancen_bewerten": "Marktbewertung anstoßen und Empfehlung als Vorschlag ablegen",
    }

    def aufgabe_kennzahlen(self, aufgabe, k):
        self.darf(k, "interne_auswertung", "kennzahlen", aufgabe)
        zahlen = k.aufgaben.zaehlen()
        beendet = zahlen["abgeschlossen"] + zahlen["fehlgeschlagen"]
        fin = k.finanzen.uebersicht()
        pipeline = {z["status"]: z["n"] for z in k.db.alle("SELECT status, COUNT(*) n FROM kontakte GROUP BY status")}
        angebote = {z["status"]: z["n"] for z in k.db.alle("SELECT status, COUNT(*) n FROM angebote GROUP BY status")}
        return {
            "aufgaben": zahlen,
            "erfolgsquote_prozent": round(100 * zahlen["abgeschlossen"] / beendet) if beendet else None,
            "einnahmen_verifiziert": euro(fin["einnahmen_verifiziert_cent"]),
            "offene_forderungen": fin["offene_forderungen"],
            "wallet_simulation": k.wallet.uebersicht()["stand"] + " (SIMULATION)",
            "kontakte_nach_status": pipeline,
            "angebote_nach_status": angebote,
            "produkte": k.db.wert("SELECT COUNT(*) FROM produkte"),
            "hinweis": "Alle Werte aus der Datenbank gezählt. Keine Schätzungen.",
        }

    def aufgabe_tagesplan(self, aufgabe, k):
        self.darf(k, "interne_planung", "tagesplan", aufgabe)
        punkte = []
        for f in k.supervisor.liste("offen"):
            punkte.append({"prio": 1, "art": "Entscheidung", "text": "Freigabe entscheiden: %s → %s"
                           % (f["aktion"], f["ziel"]), "bezug": f["id"]})
        for a in k.aufgaben.liste("fehlgeschlagen", grenze=20):
            punkte.append({"prio": 2, "art": "Fehler", "text": "Fehlgeschlagene Aufgabe prüfen: %s" % a["titel"],
                           "bezug": a["id"]})
        for z in k.ziele.liste():
            if z["status"] == "aktiv":
                punkte.append({"prio": 2 + (z["prioritaet"] > 2), "art": "Ziel", "text": z["titel"],
                               "bezug": z["id"]})
        for a in k.aufgaben.liste("bereit", grenze=30) + k.aufgaben.liste("geplant", grenze=30):
            if a["id"] != aufgabe["id"]:
                punkte.append({"prio": min(5, a["prioritaet"] + 1), "art": "Aufgabe",
                               "text": "%s (%s)" % (a["titel"], a["verantwortlich"]), "bezug": a["id"]})
        for kt in k.db.alle("SELECT id, firma, naechster_schritt FROM kontakte WHERE naechster_schritt IS NOT NULL "
                            "AND naechster_schritt != '' AND status NOT IN ('gewonnen','verloren') LIMIT 20"):
            punkte.append({"prio": 3, "art": "Vertrieb", "text": "%s: %s" % (kt["firma"], kt["naechster_schritt"]),
                           "bezug": kt["id"]})
        if not k.ziele.liste():
            punkte.append({"prio": 2, "art": "Hinweis", "text": "Noch keine Ziele festgelegt – bitte in der "
                           "CEO-Zentrale anlegen.", "bezug": None})
        punkte.sort(key=lambda p: p["prio"])
        plan = {"datum": aufgabe["erstellt"][:10], "punkte": punkte,
                "quelle": "aus Datenbank zusammengestellt (deterministisch)"}
        text = "\n".join("%d. [%s] %s" % (i + 1, p["art"], p["text"]) for i, p in enumerate(punkte)) or "Nichts offen."
        self.darf(k, "gedaechtnis_vorschlag", "tagesplan", aufgabe)
        k.gedaechtnis.merken("vorschlag", "Tagesplan " + plan["datum"], text, "ceo:tagesplan", self.rolle,
                             aufgabe["id"])
        return plan

    def aufgabe_auftrag_verteilen(self, aufgabe, k):
        e = aufgabe["eingabe"]
        self.darf(k, "interne_planung", "verteilen:%s" % e.get("rolle"), aufgabe)
        ziel = k.register.hole(e.get("rolle"))
        if ziel is None:
            raise ValueError("Unbekannte Rolle: %s" % e.get("rolle"))
        if e.get("typ") not in ziel.aufgabentypen:
            raise ValueError("Rolle %s kennt den Typ %s nicht." % (ziel.rolle, e.get("typ")))
        return {"verteilt_an": ziel.rolle, "folgeaufgaben": [
            {"titel": e.get("titel") or ziel.aufgabentypen[e["typ"]], "typ": e["typ"], "verantwortlich": ziel.rolle,
             "eingabe": e.get("eingabe") or {}, "prioritaet": int(e.get("prioritaet", 3))}]}

    def aufgabe_chancen_bewerten(self, aufgabe, k):
        self.darf(k, "interne_planung", "chancen_bewerten", aufgabe)
        return {"hinweis": "Marktbewertung an den Research-Agenten übergeben. Die Empfehlung wird als VORSCHLAG "
                           "gespeichert; entscheiden müssen Vater und Sohn.",
                "folgeaufgaben": [{"titel": "Geschäftsfelder bewerten", "typ": "marktbewertung",
                                   "verantwortlich": "research", "eingabe": aufgabe["eingabe"], "prioritaet": 2}]}
