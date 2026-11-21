# -*- coding: utf-8 -*-
"""Learning-Agent: wertet Qualität, Fehler und Zeitaufwand aus und schlägt Verbesserungen vor.

Ändert NIE produktive Regeln selbst – Vorschläge landen als VORSCHLAG im Gedächtnis."""

import datetime

from . import Agent


# Rückmeldungen echter Interessenten (Werte wie in der Datenbank, Migration 3)
ANGEBOT_ARTEN = ("google_profil", "webseite", "reinigung", "sonstiges")
KANAELE = ("gespraech", "telefon", "brief", "email", "vor_ort", "sonstiges")
REAKTIONEN = ("interessiert", "neutral", "abgelehnt", "keine_antwort")
GRUENDE = ("preis", "kein_bedarf", "spaeter", "hat_anbieter", "vertrauen", "leistung_unklar", "sonstiges")
GRUND_BEI = ("abgelehnt", "neutral")          # nur bei diesen Reaktionen ist ein Grund erlaubt
SCHWELLE = 5                                   # erst ab so vielen Rückmeldungen je Angebot aussagekräftig
ANGEBOT_NAMEN = {"google_profil": "Google-Profil-Paket", "webseite": "Webseiten-Paket",
                 "reinigung": "Reinigung (Dauerauftrag)", "sonstiges": "Sonstiges"}
# Was ein häufiger Grund nahelegt – nur Vorschläge, Entscheidung beim Inhaber
GRUND_VORSCHLAG = {
    "preis": "Preis oder Leistungsumfang prüfen – Entscheidung Inhaber.",
    "leistung_unklar": "Leistungsbeschreibung und Verkaufsseite verständlicher machen.",
    "kein_bedarf": "Zielgruppe prüfen: Viele Angesprochene haben keinen Bedarf.",
    "hat_anbieter": "Unterschied zum bisherigen Anbieter klarer zeigen oder später erneut nachfragen.",
    "vertrauen": "Vertrauen stärken: Ablauf, Ansprechpartner und echte Beispiele zeigen – keine erfundenen "
                 "Referenzen.",
    "spaeter": "Wiedervorlage planen: Termin für die erneute Nachfrage beim Kontakt eintragen.",
}


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
    aufgabentypen = {
        "auswertung": "Aufgaben je Rolle auswerten und Verbesserungen vorschlagen",
        "rueckmeldungen_auswerten": "Rückmeldungen echter Interessenten je Angebot auswerten und Verbesserungen "
                                    "vorschlagen (ändert nichts selbst)",
    }

    def aufgabe_rueckmeldungen_auswerten(self, aufgabe, k):
        """Zählt nur, was der Eigentümer erfasst hat. Vorschläge erst ab SCHWELLE Rückmeldungen je Angebot."""
        self.darf(k, "interne_auswertung", "rueckmeldungen", aufgabe)
        zeilen = k.db.alle("SELECT angebot_art, reaktion, grund FROM rueckmeldungen")
        if not zeilen:
            return {"gesamt": 0, "je_angebot": {}, "vorschlaege": [],
                    "hinweis": "Keine Rückmeldungen erfasst – es gibt noch nichts auszuwerten. Rückmeldungen trägt "
                               "der Inhaber nach echten Gesprächen ein."}
        je_angebot = {}
        for z in zeilen:
            e = je_angebot.setdefault(z["angebot_art"], {"anzahl": 0, "reaktionen": {r: 0 for r in REAKTIONEN},
                                                         "gruende": {}})
            e["anzahl"] += 1
            e["reaktionen"][z["reaktion"]] += 1
            if z["grund"]:
                e["gruende"][z["grund"]] = e["gruende"].get(z["grund"], 0) + 1
        vorschlaege = []
        for art in sorted(je_angebot, key=lambda a: ANGEBOT_ARTEN.index(a) if a in ANGEBOT_ARTEN else 99):
            e = je_angebot[art]
            n = e["anzahl"]
            gruende = sorted(e["gruende"].items(), key=lambda x: (-x[1], GRUENDE.index(x[0])))
            e["gruende"] = [[g, anzahl] for g, anzahl in gruende]
            e["quote_interessiert_prozent"] = round(100 * e["reaktionen"]["interessiert"] / n)
            e["aussagekraeftig"] = n >= SCHWELLE
            if n < SCHWELLE:
                e["hinweis"] = "Erst %d von %d Rückmeldungen – noch nicht aussagekräftig." % (n, SCHWELLE)
                continue
            name = ANGEBOT_NAMEN.get(art, art)
            for i, (g, anzahl) in enumerate(gruende):
                # „häufig“ = mindestens 2-mal und mindestens ein Viertel aller Rückmeldungen zu diesem Angebot
                if anzahl >= 2 and 4 * anzahl >= n and g in GRUND_VORSCHLAG:
                    rang = "häufigster Grund" if i == 0 else "häufiger Grund"
                    vorschlaege.append("%s: %s „%s“ (%d von %d Rückmeldungen) – %s"
                                       % (name, rang, g, anzahl, n, GRUND_VORSCHLAG[g]))
            ohne = e["reaktionen"]["keine_antwort"]
            if 2 * ohne >= n:
                vorschlaege.append("%s: %d von %d ohne Antwort – Ansprache oder Kanal prüfen (z. B. persönlich "
                                   "statt Brief)." % (name, ohne, n))
        if vorschlaege:
            self.darf(k, "gedaechtnis_vorschlag", "rueckmeldungen", aufgabe)
            k.gedaechtnis.merken("vorschlag", "Rückmeldungen", "\n".join(vorschlaege),
                                 "learning:rueckmeldungen_auswerten", self.rolle, aufgabe["id"])
        return {"gesamt": len(zeilen), "je_angebot": je_angebot, "vorschlaege": vorschlaege,
                "hinweis": "Aussagekräftig erst ab %d Rückmeldungen je Angebot. Nur Vorschläge – Preise, Texte und "
                           "Regeln ändert der Agent nie selbst." % SCHWELLE}

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
