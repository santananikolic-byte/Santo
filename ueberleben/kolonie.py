# -*- coding: utf-8 -*-
"""Kasse, Agenten und Kolonie - die eigentliche Spielmechanik.

Eine *Kolonie* ist der Besitzer mit allen seinen Agenten (dem ersten und allen Kopien). Sie hat eine Uhr in Stunden.
Eine *Runde* ist ein Schritt: jeder lebende Agent entscheidet einmal, was er in dieser Stunde tut. Alle 24 Stunden
wird die Miete fällig.

Jede Geldbewegung steht im Journal (nur anhängen, nie ändern). Das Guthaben eines Agenten ist immer gleich der Summe
seiner Buchungen - das prüft ``pruefen()``. So kann kein Geld aus dem Nichts entstehen oder verschwinden.

Welt und Gehirn sind austauschbar:
- Die *Welt* sagt, was eine Aktion bringt (Simulation: Zufall nach Annahmen; echt: nichts, bis der Besitzer bucht).
- Das *Gehirn* entscheidet (Simulation: feste Regeln; echt: Claude).
"""

from dataclasses import dataclass, field, asdict

from .regeln import AKTIONEN, STANDARD, Entscheidung, Regeln, euro

BESITZER = "besitzer"
BETRIEB = "betrieb"  # wohin die Schrittkosten gehen (Rechenzeit). Im Echt-Modus zahlt die der Besitzer über sein Abo.


@dataclass
class Agent:
    id: str
    eltern: str = ""
    generation: int = 0
    geboren: int = 0              # Stunde der Kolonie-Uhr
    gestorben: int = -1           # -1 = lebt
    todesursache: str = ""
    guthaben: int = 0             # Cent
    schritte: int = 0
    eingenommen: int = 0          # Summe aller Einnahmen (brutto)
    an_besitzer: int = 0          # Miete + Anteil + Auszahlungen
    idee: dict = field(default_factory=dict)
    fortschritt: int = 0          # Schritte, die in die aktuelle Idee geflossen sind
    kinder: list = field(default_factory=list)

    @property
    def lebt(self):
        return self.gestorben < 0

    def als_dict(self):
        return asdict(self)


class RegelVerstoss(Exception):
    """Eine Aktion verstößt gegen die Regeln (z. B. Kopie ohne genug Geld). Nichts wurde gebucht."""


class Kolonie:
    def __init__(self, regeln: Regeln = STANDARD, echt=False):
        self.regeln = regeln.pruefen()
        self.echt = bool(echt)
        self.stunde = 0
        self.agenten = {}             # id -> Agent
        self.journal = []             # Buchungen
        self.freigaben = []           # nur Echt-Modus: wartende Aktionen nach außen
        self.ereignisse = []          # lesbares Protokoll
        self._naechste_id = 1
        self._naechste_freigabe = 1

    # ------------------------------------------------------------------ Grundlagen ---

    def lebende(self):
        return [a for a in self.agenten.values() if a.lebt]

    def summe(self, konto):
        return sum(b["betrag"] for b in self.journal if b["an"] == konto) - \
            sum(b["betrag"] for b in self.journal if b["von"] == konto)

    @property
    def besitzer_bekommen(self):
        return self.summe(BESITZER)

    def _log(self, agent_id, text):
        self.ereignisse.append({"stunde": self.stunde, "agent": agent_id, "text": text})

    def _buchen(self, von, an, betrag, art, text=""):
        """Bucht ``betrag`` Cent von ``von`` nach ``an``. Konten: Agent-IDs, 'besitzer', 'betrieb', 'aussen'."""
        betrag = int(betrag)
        if betrag <= 0:
            return
        for konto, vz in ((von, -1), (an, +1)):
            if konto in self.agenten:
                self.agenten[konto].guthaben += vz * betrag
        self.journal.append({"stunde": self.stunde, "von": von, "an": an, "betrag": betrag, "art": art, "text": text})

    def _todescheck(self, agent, ursache):
        if agent.lebt and agent.guthaben <= 0:
            agent.gestorben = self.stunde
            agent.todesursache = ursache
            self._log(agent.id, f"ist tot ({ursache}). Guthaben {euro(agent.guthaben)}.")
            return True
        return False

    # ---------------------------------------------------------------- Leben & Tod ---

    def gruenden(self):
        """Erster Agent. Das Startbudget kommt von außen (vom Besitzer gestellt)."""
        if self.agenten:
            raise RegelVerstoss("Die Kolonie hat schon einen Agenten.")
        a = self._neuer_agent(eltern="", generation=0)
        self._buchen("aussen", a.id, self.regeln.startbudget, "start", "Startbudget vom Besitzer")
        self._log(a.id, f"wurde gegründet mit {euro(self.regeln.startbudget)}.")
        return a

    def _neuer_agent(self, eltern, generation):
        a = Agent(id=f"A{self._naechste_id}", eltern=eltern, generation=generation, geboren=self.stunde)
        self._naechste_id += 1
        self.agenten[a.id] = a
        return a

    def kopie_moeglich(self, agent):
        """Warum eine Kopie gerade nicht geht - oder '' wenn sie geht."""
        r = self.regeln
        if not agent.lebt:
            return "Tote Agenten können sich nicht kopieren."
        if len(self.lebende()) >= r.max_agenten:
            return f"Höchstzahl von {r.max_agenten} lebenden Agenten erreicht."
        if agent.generation + 1 > r.max_generation:
            return f"Höchstens {r.max_generation} Generationen."
        noetig = r.startbudget + r.kosten_pro_schritt + r.kopie_reserve
        if agent.guthaben < noetig:
            return f"Zu wenig Geld: nötig {euro(noetig)} (Startbudget + Schritt + Reserve), da sind {euro(agent.guthaben)}."
        return ""

    def _kopieren(self, agent):
        grund = self.kopie_moeglich(agent)
        if grund:
            raise RegelVerstoss(grund)
        kind = self._neuer_agent(eltern=agent.id, generation=agent.generation + 1)
        kind.idee = dict(agent.idee)  # die Kopie erbt das Wissen, aber nicht den Fortschritt
        agent.kinder.append(kind.id)
        self._buchen(agent.id, kind.id, self.regeln.startbudget, "kopie", f"Startbudget für {kind.id}")
        self._log(agent.id, f"hat sich kopiert: {kind.id} startet mit {euro(self.regeln.startbudget)}.")
        return kind

    def einnahme(self, agent, betrag, text):
        """Echte oder simulierte Einnahme. Der Besitzer-Anteil geht sofort ab."""
        if not agent.lebt:
            raise RegelVerstoss(f"{agent.id} ist tot und kann nichts mehr einnehmen.")
        self._buchen("aussen", agent.id, betrag, "einnahme", text)
        agent.eingenommen += betrag
        anteil = betrag * self.regeln.besitzer_anteil_prozent // 100
        if anteil:
            self._buchen(agent.id, BESITZER, anteil, "anteil", f"{self.regeln.besitzer_anteil_prozent} % von {euro(betrag)}")
            agent.an_besitzer += anteil
        self._log(agent.id, f"hat {euro(betrag)} eingenommen ({text}). Anteil Besitzer {euro(anteil)}.")

    def _auszahlen(self, agent, betrag):
        betrag = min(int(betrag), agent.guthaben - self.regeln.kosten_pro_schritt - 1)
        if betrag <= 0:
            raise RegelVerstoss("Nach der Auszahlung bliebe nichts übrig - der Agent würde sterben.")
        self._buchen(agent.id, BESITZER, betrag, "auszahlung", "freiwillige Auszahlung")
        agent.an_besitzer += betrag
        self._log(agent.id, f"zahlt dem Besitzer {euro(betrag)} aus.")
        return betrag

    def _miete(self):
        for a in self.lebende():
            betrag = self.regeln.miete_pro_tag
            self._buchen(a.id, BESITZER, betrag, "miete", f"Miete Tag {self.stunde // 24}")
            a.an_besitzer += betrag
            self._todescheck(a, "Miete nicht bezahlbar")

    # ------------------------------------------------------------------- Runden ---

    def runde(self, gehirn, welt):
        """Eine Stunde (ein Schritt) für alle lebenden Agenten. Gibt die Liste der Entscheidungen zurück."""
        r = self.regeln
        self.stunde += r.stunden_pro_schritt
        ergebnisse = []
        for agent in list(self.lebende()):
            if agent.geboren == self.stunde:
                continue  # in dieser Stunde erst geboren: handelt ab der nächsten
            e = gehirn.entscheiden(self.sicht(agent))
            if not isinstance(e, Entscheidung) or e.aktion not in AKTIONEN:
                e = Entscheidung("warten", "ungültige Entscheidung")
            ergebnisse.append((agent.id, e))
            self._ausfuehren(agent, e, welt)
        if self.stunde % 24 == 0:
            self._miete()
        return ergebnisse

    def _ausfuehren(self, agent, e, welt):
        if e.aktion == "warten":
            self._log(agent.id, "wartet.")
            return
        agent.schritte += 1
        try:
            if self.echt and AKTIONEN[e.aktion]["nach_aussen"]:
                self._freigabe_anlegen(agent, e)
            elif e.aktion == "kopieren":
                self._kopieren(agent)
            elif e.aktion == "auszahlen":
                self._auszahlen(agent, e.details.get("betrag", 0))
            else:
                welt.handeln(self, agent, e)
        except RegelVerstoss as fehler:
            self._log(agent.id, f"wollte '{e.aktion}', geht nicht: {fehler}")
        # Die Stunde Arbeit kostet in jedem Fall - auch wenn die Aktion nicht geklappt hat.
        self._buchen(agent.id, BETRIEB, self.regeln.kosten_pro_schritt, "schritt", e.aktion)
        self._todescheck(agent, "Geld für den nächsten Schritt aufgebraucht")

    # --------------------------------------------------------- Echt-Modus: Freigaben ---

    def _freigabe_anlegen(self, agent, e):
        if e.aktion == "kopieren":
            grund = self.kopie_moeglich(agent)
            if grund:
                raise RegelVerstoss(grund)
        f = {"id": self._naechste_freigabe, "agent": agent.id, "aktion": e.aktion, "begruendung": e.begruendung,
             "details": e.details, "status": "offen", "stunde": self.stunde}
        self._naechste_freigabe += 1
        self.freigaben.append(f)
        self._log(agent.id, f"bittet um Freigabe #{f['id']}: {e.aktion} - {e.begruendung}")

    def offene_freigaben(self):
        return [f for f in self.freigaben if f["status"] == "offen"]

    def freigabe_entscheiden(self, nr, ja):
        """Der Besitzer sagt Ja oder Nein. Nur bei Ja passiert etwas - und nur diese eine Aktion."""
        f = next((x for x in self.freigaben if x["id"] == nr), None)
        if f is None:
            raise RegelVerstoss(f"Freigabe #{nr} gibt es nicht.")
        if f["status"] != "offen":
            raise RegelVerstoss(f"Freigabe #{nr} ist schon entschieden ({f['status']}).")
        agent = self.agenten[f["agent"]]
        if not ja:
            f["status"] = "abgelehnt"
            self._log(agent.id, f"Freigabe #{nr} abgelehnt.")
            return f
        if not agent.lebt:
            f["status"] = "verfallen"
            raise RegelVerstoss(f"{agent.id} ist inzwischen tot. Freigabe #{nr} verfällt.")
        if f["aktion"] == "kopieren":
            kind = self._kopieren(agent)
            f["ergebnis"] = kind.id
        elif f["aktion"] == "auszahlen":
            f["ergebnis"] = self._auszahlen(agent, f["details"].get("betrag", 0))
        else:  # verkaufen: der Besitzer führt es selbst aus; Einnahmen bucht er später mit "einnahme"
            f["ergebnis"] = "vom Besitzer auszuführen"
        f["status"] = "freigegeben"
        self._log(agent.id, f"Freigabe #{nr} erteilt.")
        return f

    # --------------------------------------------------------------- Sicht & Prüfung ---

    def sicht(self, agent):
        """Was ein Agent über sich und die Lage weiß - die Grundlage jeder Entscheidung."""
        r = self.regeln
        bis_miete = 24 - (self.stunde % 24) if self.stunde % 24 else 24
        return {
            "id": agent.id, "generation": agent.generation, "stunde": self.stunde,
            "guthaben": agent.guthaben, "schritte_uebrig": max(0, (agent.guthaben - 1) // r.kosten_pro_schritt),
            "stunden_bis_miete": bis_miete, "idee": dict(agent.idee), "fortschritt": agent.fortschritt,
            "eingenommen": agent.eingenommen, "lebende_agenten": len(self.lebende()),
            "kopie_moeglich": not self.kopie_moeglich(agent), "echt": self.echt,
            "offene_freigaben": len([f for f in self.offene_freigaben() if f["agent"] == agent.id]),
            "regeln": r.als_dict(),
            "letzte_ereignisse": [x["text"] for x in self.ereignisse if x["agent"] == agent.id][-8:],
        }

    def pruefen(self):
        """Buchhaltung stimmt? Wirft AssertionError, wenn nicht."""
        for a in self.agenten.values():
            assert a.guthaben == self.summe(a.id), f"{a.id}: Guthaben {a.guthaben} != Journal {self.summe(a.id)}"
        gesamt = sum(self.summe(k) for k in {b["von"] for b in self.journal} | {b["an"] for b in self.journal})
        assert gesamt == 0, f"Journal nicht ausgeglichen: {gesamt}"
        for a in self.agenten.values():
            if not a.lebt:
                spaeter = [b for b in self.journal if b["stunde"] > a.gestorben and a.id in (b["von"], b["an"])]
                assert not spaeter, f"{a.id} hat nach dem Tod noch gebucht: {spaeter[:1]}"
        return True

    # ------------------------------------------------------------- Speichern/Laden ---

    def als_dict(self):
        return {"version": 1, "regeln": self.regeln.als_dict(), "echt": self.echt, "stunde": self.stunde,
                "agenten": [a.als_dict() for a in self.agenten.values()], "journal": self.journal,
                "freigaben": self.freigaben, "ereignisse": self.ereignisse[-500:],
                "naechste_id": self._naechste_id, "naechste_freigabe": self._naechste_freigabe}

    @classmethod
    def aus_dict(cls, d):
        k = cls(Regeln.aus_dict(d.get("regeln")), echt=d.get("echt", False))
        k.stunde = int(d.get("stunde", 0))
        for ad in d.get("agenten", []):
            felder = {n: ad[n] for n in Agent.__dataclass_fields__ if n in ad}
            a = Agent(**felder)
            k.agenten[a.id] = a
        k.journal = list(d.get("journal", []))
        k.freigaben = list(d.get("freigaben", []))
        k.ereignisse = list(d.get("ereignisse", []))
        k._naechste_id = int(d.get("naechste_id", len(k.agenten) + 1))
        k._naechste_freigabe = int(d.get("naechste_freigabe", len(k.freigaben) + 1))
        k.pruefen()
        return k

