# -*- coding: utf-8 -*-
"""Learning-Agent: wertet Qualität, Fehler und Zeitaufwand aus und schlägt Verbesserungen vor.

Ändert NIE produktive Regeln selbst – Vorschläge landen als VORSCHLAG im Gedächtnis."""

import datetime

from . import Agent


def _sekunden(a, b):
    try:
        return (datetime.datetime.fromisoformat(b) - datetime.datetime.fromisoformat(a)).total_seconds()
    except (TypeError, ValueError):
        return None


class LearningAgent(Agent):
    rolle = "learning"
    name = "Learning-Agent"
    beschreibung = "Analysiert Qualität, Fehler und Zeitaufwand; schlägt Verbesserungen vor (ohne sie umzusetzen)."
    rechte = frozenset({"interne_auswertung", "gedaechtnis_vorschlag"})
    aufgabentypen = {"auswertung": "Aufgaben je Rolle auswerten und Verbesserungen vorschlagen"}

    def aufgabe_auswertung(self, aufgabe, k):
        self.darf(k, "interne_auswertung", "auswertung", aufgabe)
        rollen = {}
        for a in k.db.alle("SELECT verantwortlich, status, gestartet, beendet, fehler, versuche FROM aufgaben "
                           "WHERE status IN ('abgeschlossen','fehlgeschlagen','abgebrochen')"):
            r = rollen.setdefault(a["verantwortlich"], {"abgeschlossen": 0, "fehlgeschlagen": 0, "abgebrochen": 0,
                                                        "dauer": [], "fehler": {}, "wiederholungen": 0})
            r[a["status"]] += 1
            r["wiederholungen"] += max(0, (a["versuche"] or 1) - 1)
            d = _sekunden(a["gestartet"], a["beendet"])
            if d is not None:
                r["dauer"].append(d)
            if a["fehler"]:
                kurz = a["fehler"].split(":")[0][:60]
                r["fehler"][kurz] = r["fehler"].get(kurz, 0) + 1
        bericht, vorschlaege = {}, []
        for rolle, r in rollen.items():
            n = r["abgeschlossen"] + r["fehlgeschlagen"]
            quote = round(100 * r["abgeschlossen"] / n) if n else None
            bericht[rolle] = {"abgeschlossen": r["abgeschlossen"], "fehlgeschlagen": r["fehlgeschlagen"],
                              "abgebrochen": r["abgebrochen"], "erfolgsquote_prozent": quote,
                              "mittlere_dauer_s": round(sum(r["dauer"]) / len(r["dauer"]), 2) if r["dauer"] else None,
                              "haeufigste_fehler": sorted(r["fehler"].items(), key=lambda x: -x[1])[:3],
                              "wiederholungen": r["wiederholungen"]}
            if quote is not None and n >= 3 and quote < 70:
                vorschlaege.append("Rolle %s: Erfolgsquote %s%% – häufigster Fehler: %s. Eingaben prüfen."
                                   % (rolle, quote, bericht[rolle]["haeufigste_fehler"][:1]))
            if r["abgebrochen"] >= 3:
                vorschlaege.append("Rolle %s: %d Abbrüche – oft durch abgelehnte Freigaben oder Sperren. "
                                   "Aufgaben vorher besser abstimmen." % (rolle, r["abgebrochen"]))
        if vorschlaege:
            self.darf(k, "gedaechtnis_vorschlag", "lernen", aufgabe)
            k.gedaechtnis.merken("vorschlag", "Verbesserungen", "\n".join(vorschlaege), "learning:auswertung",
                                 self.rolle, aufgabe["id"])
        return {"rollen": bericht, "vorschlaege": vorschlaege,
                "hinweis": "Nur Vorschläge. Regeln werden nicht automatisch geändert."}
