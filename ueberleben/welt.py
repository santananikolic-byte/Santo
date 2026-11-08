# -*- coding: utf-8 -*-
"""Die Welt: was eine Aktion bringt.

SimWelt - ein ausgedachter Markt. ALLE Zahlen darin sind Annahmen von Claude, keine Marktdaten. Sie sind nur dazu da,
die Spielmechanik durchzuspielen (Wann stirbt er? Lohnt Kopieren? Was bekommt der Besitzer?). Wer andere Annahmen
hat, ändert sie in ``MarktAnnahmen`` oder im HTML-Simulator.

EchteWelt - bringt von sich aus nie Geld. Echtes Geld kommt nur, wenn der Besitzer eine Einnahme bucht, die wirklich
auf dem Konto eingegangen ist. So kann der Agent keine Umsätze erfinden.
"""

import random
from dataclasses import dataclass, asdict

from .regeln import EURO, euro

IDEEN = [
    "Bewerbungsschreiben-Service", "Übersetzungen Deutsch-Englisch", "Produktbeschreibungen für Online-Shops",
    "Social-Media-Texte für Handwerker", "Lebenslauf-Vorlagen", "Excel-Vorlagen für Kleinbetriebe",
    "Reinigungs-Checklisten als PDF", "Angebotsvorlagen für Bau und Reinigung", "Kurzvideo-Skripte",
    "Google-Bewertungen beantworten (Textentwürfe)",
]


@dataclass
class MarktAnnahmen:
    """Annahmen für den ausgedachten Markt. Nicht geprüft, nur Spielwerte."""
    bau_min: int = 3                 # Schritte, bis ein Angebot verkaufsfertig ist (mindestens)
    bau_max: int = 12                # ... höchstens
    preis_min: int = 5 * EURO        # Preis pro Verkauf
    preis_max: int = 40 * EURO
    verkaufschance_max: int = 25     # Prozent pro Verkaufsschritt bei einer perfekten Idee
    idee_verbessern_chance: int = 30 # Prozent: ein weiterer Ideen-Schritt verbessert die Qualität

    def als_dict(self):
        return asdict(self)


class SimWelt:
    def __init__(self, annahmen: MarktAnnahmen = None, zufall: random.Random = None):
        self.a = annahmen or MarktAnnahmen()
        self.zufall = zufall or random.Random()

    def neue_idee(self):
        z, a = self.zufall, self.a
        return {"name": z.choice(IDEEN), "qualitaet": z.randint(5, 100), "bau_bedarf": z.randint(a.bau_min, a.bau_max),
                "preis": z.randint(a.preis_min // 50, a.preis_max // 50) * 50}

    def handeln(self, kolonie, agent, e):
        z, a = self.zufall, self.a
        if e.aktion == "idee":
            if not agent.idee:
                agent.idee = self.neue_idee()
                agent.fortschritt = 0
                kolonie._log(agent.id, f"hat eine Idee: {agent.idee['name']} (Qualität {agent.idee['qualitaet']}).")
            elif z.randint(1, 100) <= a.idee_verbessern_chance:
                agent.idee["qualitaet"] = min(100, agent.idee["qualitaet"] + z.randint(5, 20))
                kolonie._log(agent.id, f"verbessert die Idee auf Qualität {agent.idee['qualitaet']}.")
            elif e.details.get("neu"):
                agent.idee = self.neue_idee()
                agent.fortschritt = 0
                kolonie._log(agent.id, f"wirft die Idee weg, neue: {agent.idee['name']}.")
            else:
                kolonie._log(agent.id, "grübelt ohne Ergebnis.")
        elif e.aktion == "bauen":
            if not agent.idee:
                kolonie._log(agent.id, "will bauen, hat aber keine Idee - Stunde verschenkt.")
                return
            agent.fortschritt += 1
            kolonie._log(agent.id, f"baut ({agent.fortschritt}/{agent.idee['bau_bedarf']}).")
        elif e.aktion == "verkaufen":
            if not agent.idee or agent.fortschritt < agent.idee["bau_bedarf"]:
                kolonie._log(agent.id, "will verkaufen, das Angebot ist aber nicht fertig - niemand kauft.")
                return
            chance = a.verkaufschance_max * agent.idee["qualitaet"] // 100
            if z.randint(1, 100) <= chance:
                kolonie.einnahme(agent, agent.idee["preis"], f"Verkauf {agent.idee['name']}")
            else:
                kolonie._log(agent.id, f"findet keinen Käufer (Chance {chance} %).")


class EchteWelt:
    """Im Echt-Modus passiert drinnen nur Denkarbeit; nach außen geht alles über Freigaben."""

    def handeln(self, kolonie, agent, e):
        if e.aktion == "idee":
            neu = (e.details or {}).get("idee")
            if isinstance(neu, dict) and neu.get("name"):
                agent.idee = {k: str(v)[:300] for k, v in neu.items() if k in ("name", "zielgruppe", "angebot", "preis")}
                agent.fortschritt = 0
                kolonie._log(agent.id, f"Idee: {agent.idee.get('name')}", eigen=True)
            else:
                kolonie._log(agent.id, f"denkt nach: {e.begruendung[:200]}", eigen=True)
        elif e.aktion == "bauen":
            agent.fortschritt += 1
            kolonie._log(agent.id, f"arbeitet am Angebot: {e.begruendung[:200]}", eigen=True)


def zusammenfassung(kolonie):
    """Kurzer Text für Menschen."""
    lebend = kolonie.lebende()
    zeilen = [f"Stunde {kolonie.stunde} (Tag {kolonie.stunde // 24 + 1}). Lebende Agenten: {len(lebend)} "
              f"von {len(kolonie.agenten)}. Besitzer hat bekommen: {euro(kolonie.besitzer_bekommen)}."]
    for a in kolonie.agenten.values():
        zustand = "lebt" if a.lebt else f"tot seit Stunde {a.gestorben} ({a.todesursache})"
        idee = a.idee.get("name", "-") if a.idee else "-"
        zeilen.append(f"  {a.id} (Gen. {a.generation}): {euro(a.guthaben)}, {zustand}, Idee: {idee}, "
                      f"eingenommen {euro(a.eingenommen)}, an dich {euro(a.an_besitzer)}")
    return "\n".join(zeilen)
