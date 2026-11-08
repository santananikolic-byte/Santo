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

import time
from dataclasses import dataclass, field, asdict

from .regeln import AKTIONEN, STANDARD, STUNDEN_PRO_WOCHE, Entscheidung, Regeln, euro

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
    letzte_runde: int = -1        # Echtzeit: in welcher Stunde er zuletzt gehandelt hat (einmal pro Stunde)

    @property
    def lebt(self):
        return self.gestorben < 0

    def als_dict(self):
        return asdict(self)


class RegelVerstoss(Exception):
    """Eine Aktion verstößt gegen die Regeln (z. B. Kopie ohne genug Geld). Nichts wurde gebucht."""


class BuchFehler(AssertionError):
    """Die Buchhaltung stimmt nicht. Wird ausdrücklich geworfen - wirkt also auch unter ``python3 -O``."""


class LadeFehler(ValueError):
    """Die gespeicherten Daten sind kaputt oder passen nicht zusammen."""


ERLAUBTE_DETAILS = {"schritt": 600, "plattform": 100, "preis": 50, "betrag": 0, "neu": 0, "idee": 0}


class Kolonie:
    def __init__(self, regeln: Regeln = STANDARD, echt=False):
        self.regeln = regeln.pruefen()
        self._regeln_dict = self.regeln.als_dict()
        self.echt = bool(echt)
        self.stunde = 0
        self.agenten = {}             # id -> Agent
        self.journal = []             # Buchungen
        self.freigaben = []           # nur Echt-Modus: wartende Aktionen nach außen
        self.ereignisse = []          # lesbares Protokoll
        self._naechste_id = 1
        self._naechste_freigabe = 1
        self.start_zeit = None        # Echtzeit: Sekunden seit 1970 bei der Gründung. None = Rundenzeit.

    @property
    def echtzeit(self):
        return self.start_zeit is not None

    # ------------------------------------------------------------------ Grundlagen ---

    def lebende(self):
        return [a for a in self.agenten.values() if a.lebt]

    def summe(self, konto):
        return sum(b["betrag"] for b in self.journal if b["an"] == konto) - \
            sum(b["betrag"] for b in self.journal if b["von"] == konto)

    @property
    def besitzer_bekommen(self):
        return self.salden().get(BESITZER, 0)

    def _log(self, agent_id, text, eigen=False):
        """``eigen=True``: der Text stammt vom Gehirn (Claude) und wird ihm nicht wieder vorgelegt."""
        eintrag = {"stunde": self.stunde, "agent": agent_id, "text": text}
        if eigen:
            eintrag["eigen"] = True
        self.ereignisse.append(eintrag)

    def _buchen(self, von, an, betrag, art, text=""):
        """Bucht ``betrag`` Cent von ``von`` nach ``an``. Konten: Agent-IDs, 'besitzer', 'betrieb', 'aussen'."""
        betrag = int(betrag)
        if betrag <= 0:
            return
        for konto, vz in ((von, -1), (an, +1)):
            if konto in self.agenten:
                self.agenten[konto].guthaben += vz * betrag
        self.journal.append({"stunde": self.stunde, "von": von, "an": an, "betrag": betrag, "art": art, "text": text})

    def _belasten(self, agent, an, betrag, art, text=""):
        """Kosten abbuchen - aber nie mehr, als da ist. Ein Konto geht nie ins Minus; fehlt Geld, stirbt der Agent."""
        gedeckt = min(int(betrag), max(agent.guthaben, 0))
        self._buchen(agent.id, an, gedeckt, art, text)
        if gedeckt < betrag:
            self._log(agent.id, f"konnte {euro(betrag)} ({art}) nicht voll bezahlen, nur {euro(gedeckt)}.")
        return gedeckt

    def _todescheck(self, agent, ursache):
        if agent.lebt and agent.guthaben <= 0:
            agent.gestorben = self.stunde
            agent.todesursache = ursache
            self._log(agent.id, f"ist tot ({ursache}). Guthaben {euro(agent.guthaben)}.")
            for f in self.freigaben:
                if f["agent"] == agent.id and f["status"] == "offen":
                    f["status"] = "verfallen"
            return True
        return False

    # ---------------------------------------------------------------- Leben & Tod ---

    def gruenden(self, jetzt=None, echtzeit=False):
        """Erster Agent. Das Startbudget kommt von außen (vom Besitzer gestellt).

        ``echtzeit=True``: die Uhr läuft in echten Stunden ab ``jetzt`` - Kosten und Miete laufen auch,
        wenn niemand das Programm öffnet."""
        if self.agenten:
            raise RegelVerstoss("Die Kolonie hat schon einen Agenten.")
        if echtzeit:
            self.start_zeit = float(time.time() if jetzt is None else jetzt)
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
        """Tagesmiete (alle 24 Stunden der Kolonie-Uhr) und Wochenmiete (alle 168 Stunden ab Geburt des Agenten)."""
        r = self.regeln
        for a in self.lebende():
            if r.miete_pro_tag and self.stunde % 24 == 0:
                a.an_besitzer += self._belasten(a, BESITZER, r.miete_pro_tag, "miete", f"Miete Tag {self.stunde // 24}")
                self._todescheck(a, "Miete nicht bezahlbar")
            alter = self.stunde - a.geboren
            if a.lebt and r.miete_pro_woche and alter > 0 and alter % STUNDEN_PRO_WOCHE == 0:
                woche = alter // STUNDEN_PRO_WOCHE
                a.an_besitzer += self._belasten(a, BESITZER, r.miete_pro_woche, "miete", f"Wochenmiete Woche {woche}")
                self._todescheck(a, f"Wochenmiete {euro(r.miete_pro_woche)} nicht bezahlt")

    def zeit_nachziehen(self, jetzt=None):
        """Echtzeit: für jede vergangene volle Stunde die Stundenkosten abbuchen und fällige Miete einziehen.

        Läuft bei jedem Öffnen. Die Zeit vergeht also auch, wenn das Programm nicht läuft - wie im echten Leben."""
        if not self.echtzeit:
            return 0
        jetzt = time.time() if jetzt is None else float(jetzt)
        ziel = int((jetzt - self.start_zeit) // 3600)
        vorher = self.stunde
        while self.stunde < ziel and self.lebende():
            self.stunde += 1
            for a in self.lebende():
                self._belasten(a, BETRIEB, self.regeln.kosten_pro_schritt, "stunde", "Lebenszeit")
                self._todescheck(a, f"Geld aufgebraucht ({euro(self.regeln.kosten_pro_schritt)} pro Stunde)")
            self._miete()
        if not self.lebende():
            self.stunde = max(self.stunde, ziel)
        return self.stunde - vorher

    def naechste_wochenmiete(self, agent):
        """In wie vielen Stunden die nächste Wochenmiete dieses Agenten fällig ist."""
        alter = self.stunde - agent.geboren
        return STUNDEN_PRO_WOCHE - (alter % STUNDEN_PRO_WOCHE)

    # ------------------------------------------------------------------- Runden ---

    def runde(self, gehirn, welt):
        """Eine Stunde (ein Schritt) für alle lebenden Agenten. Gibt die Liste der Entscheidungen zurück.

        Echtzeit: die Uhr rückt hier NICHT vor (das macht ``zeit_nachziehen``), und jeder Agent handelt höchstens
        einmal pro echter Stunde. Die Kosten laufen über die Zeit, nicht über die Aktion."""
        r = self.regeln
        if not self.echtzeit:
            self.stunde += r.stunden_pro_schritt
        ergebnisse = []
        for agent in list(self.lebende()):
            if self.echtzeit:
                if agent.letzte_runde == self.stunde:
                    continue  # hat in dieser echten Stunde schon gehandelt
            elif agent.geboren == self.stunde:
                continue  # in dieser Stunde erst geboren: handelt ab der nächsten
            e = gehirn.entscheiden(self.sicht(agent))
            if not isinstance(e, Entscheidung) or e.aktion not in AKTIONEN:
                e = Entscheidung("warten", "ungültige Entscheidung")
            ergebnisse.append((agent.id, e))
            if e.ausfall:
                self._log(agent.id, f"konnte nicht denken ({e.begruendung[:120]}). Die Stunde wird nicht berechnet.",
                          eigen=True)
                continue
            agent.letzte_runde = self.stunde
            self._ausfuehren(agent, e, welt)
        if not self.echtzeit:
            self._miete()
        return ergebnisse

    def _ausfuehren(self, agent, e, welt):
        agent.schritte += 1
        try:
            if e.aktion == "warten":
                self._log(agent.id, "wartet.")
            elif self.echt and AKTIONEN[e.aktion]["nach_aussen"]:
                self._freigabe_anlegen(agent, e)
            elif e.aktion == "kopieren":
                self._kopieren(agent)
            elif e.aktion == "auszahlen":
                self._auszahlen(agent, e.details.get("betrag", 0))
            else:
                welt.handeln(self, agent, e)
        except RegelVerstoss as fehler:
            self._log(agent.id, f"wollte '{e.aktion}', geht nicht: {fehler}")
        if self.echtzeit:
            return  # in Echtzeit kostet die Zeit, nicht die Aktion (siehe zeit_nachziehen)
        # Jede Stunde kostet - auch Warten, auch wenn die Aktion nicht geklappt hat.
        self._belasten(agent, BETRIEB, self.regeln.kosten_pro_schritt, "schritt", e.aktion)
        self._todescheck(agent, "Geld für den nächsten Schritt aufgebraucht")

    # --------------------------------------------------------- Echt-Modus: Freigaben ---

    def _freigabe_anlegen(self, agent, e):
        if e.aktion == "kopieren":
            grund = self.kopie_moeglich(agent)
            if grund:
                raise RegelVerstoss(grund)
        offen = [x for x in self.offene_freigaben() if x["agent"] == agent.id]
        if offen:
            raise RegelVerstoss(f"Freigabe #{offen[0]['id']} ist noch offen. Erst wenn du entschieden hast, kommt die nächste.")
        f = {"id": self._naechste_freigabe, "agent": agent.id, "aktion": e.aktion,
             "begruendung": str(e.begruendung)[:500], "details": details_saeubern(e.details),
             "status": "offen", "stunde": self.stunde}
        self._naechste_freigabe += 1
        self.freigaben.append(f)
        self._log(agent.id, f"bittet um Freigabe #{f['id']} ({e.aktion}).")

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
        try:
            if f["aktion"] == "kopieren":
                f["ergebnis"] = self._kopieren(agent).id
            elif f["aktion"] == "auszahlen":
                f["ergebnis"] = self._auszahlen(agent, f["details"].get("betrag", 0))
        except RegelVerstoss:
            f["status"] = "verfallen"  # geht nach den Regeln nicht (mehr) - damit der Agent nicht ewig darauf wartet
            self._log(agent.id, f"Freigabe #{nr} verfallen: nach den Regeln nicht mehr möglich.")
            raise
        if f["aktion"] not in ("kopieren", "auszahlen"):  # verkaufen: der Besitzer führt es selbst aus; Einnahmen bucht er später mit "einnahme"
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
            "stunden_bis_miete": bis_miete, "stunden_bis_wochenmiete": self.naechste_wochenmiete(agent),
            "echtzeit": self.echtzeit, "idee": dict(agent.idee), "fortschritt": agent.fortschritt,
            "eingenommen": agent.eingenommen, "lebende_agenten": len(self.lebende()),
            "kopie_moeglich": not self.kopie_moeglich(agent), "echt": self.echt,
            "offene_freigaben": len([f for f in self.offene_freigaben() if f["agent"] == agent.id]),
            "regeln": dict(self._regeln_dict),
            "letzte_ereignisse": self._letzte_ereignisse(agent.id),
        }

    def salden(self):
        """Alle Kontostände aus dem Journal, in einem Durchgang."""
        salden = {}
        for b in self.journal:
            salden[b["von"]] = salden.get(b["von"], 0) - b["betrag"]
            salden[b["an"]] = salden.get(b["an"], 0) + b["betrag"]
        return salden

    def _letzte_ereignisse(self, agent_id, anzahl=8):
        """Die letzten Ereignisse eines Agenten - von hinten gesucht, damit lange Leben nicht immer langsamer werden."""
        gefunden = []
        for x in reversed(self.ereignisse):
            if x["agent"] == agent_id and not x.get("eigen"):
                gefunden.append(x["text"])
                if len(gefunden) == anzahl:
                    break
        return gefunden[::-1]

    def pruefen(self):
        """Buchhaltung stimmt? Wirft BuchFehler, wenn nicht."""
        salden = self.salden()
        for b in self.journal:
            if not isinstance(b.get("betrag"), int) or isinstance(b["betrag"], bool) or b["betrag"] <= 0:
                raise BuchFehler(f"Ungültige Buchung: {b}")
            for konto in (b["von"], b["an"]):
                a = self.agenten.get(konto)
                if a is not None and not a.lebt and b["stunde"] > a.gestorben:
                    raise BuchFehler(f"{konto} hat nach dem Tod noch gebucht: {b}")
        for a in self.agenten.values():
            if not isinstance(a.guthaben, int) or a.guthaben != salden.get(a.id, 0):
                raise BuchFehler(f"{a.id}: Guthaben {a.guthaben!r} passt nicht zum Journal ({salden.get(a.id, 0)})")
            if a.guthaben < 0:
                raise BuchFehler(f"{a.id} steht im Minus: {a.guthaben}")
        if sum(salden.values()) != 0:
            raise BuchFehler(f"Journal nicht ausgeglichen: {sum(salden.values())}")
        return True

    # ------------------------------------------------------------- Speichern/Laden ---

    def als_dict(self):
        return {"version": 1, "regeln": self.regeln.als_dict(), "echt": self.echt, "stunde": self.stunde,
                "agenten": [a.als_dict() for a in self.agenten.values()], "journal": self.journal,
                "freigaben": self.freigaben, "ereignisse": self.ereignisse[-500:],
                "naechste_id": self._naechste_id, "naechste_freigabe": self._naechste_freigabe,
                "start_zeit": self.start_zeit}

    @classmethod
    def aus_dict(cls, d):
        """Lädt und prüft alles. Kaputte Daten -> LadeFehler mit verständlicher Meldung."""
        try:
            if not isinstance(d, dict):
                raise LadeFehler("Die Datei enthält keinen gültigen Zustand.")
            if d.get("version") != 1:
                raise LadeFehler(f"Unbekannte Version {d.get('version')!r} - diese Datei stammt nicht von diesem Programm.")
            # Fehlt die Angabe, gilt sicherheitshalber der Echt-Modus (mit Freigaben).
            k = cls(Regeln.aus_dict(d.get("regeln")), echt=d.get("echt", True) is not False)
            k.stunde = int(d.get("stunde", 0))
            if d.get("start_zeit") is not None:
                k.start_zeit = float(d["start_zeit"])
            for ad in d.get("agenten", []):
                a = Agent(**{n: ad[n] for n in Agent.__dataclass_fields__ if n in ad})
                if a.id in k.agenten:
                    raise LadeFehler(f"Agent {a.id} steht doppelt in der Datei.")
                k.agenten[a.id] = a
            k.journal = list(d.get("journal", []))
            k.freigaben = list(d.get("freigaben", []))
            k.ereignisse = list(d.get("ereignisse", []))
            ids = [f["id"] for f in k.freigaben]
            if len(ids) != len(set(ids)):
                raise LadeFehler("Freigabe-Nummern stehen doppelt in der Datei.")
            for f in k.freigaben:
                if f.get("aktion") not in AKTIONEN or f.get("agent") not in k.agenten or not isinstance(f["id"], int):
                    raise LadeFehler(f"Freigabe {f.get('id')!r} ist ungültig.")
                f["details"] = details_saeubern(f.get("details"))
            nummern = [int(i[1:]) for i in k.agenten if i[:1] == "A" and i[1:].isdigit()]
            k._naechste_id = max([int(d.get("naechste_id", 1))] + [n + 1 for n in nummern])
            k._naechste_freigabe = max([int(d.get("naechste_freigabe", 1))] + [i + 1 for i in ids])
            k.pruefen()
            return k
        except LadeFehler:
            raise
        except (BuchFehler, KeyError, TypeError, ValueError, AttributeError) as fehler:
            raise LadeFehler(f"Gespeicherter Stand ist beschädigt: {fehler}") from fehler


def details_saeubern(details):
    """Nur bekannte Felder, Texte gekürzt - damit kein Riesentext oder Unsinn in Freigaben landet."""
    if not isinstance(details, dict):
        return {}
    sauber = {}
    for name, laenge in ERLAUBTE_DETAILS.items():
        if name not in details:
            continue
        wert = details[name]
        if name == "betrag":
            try:
                sauber[name] = max(0, int(wert))
            except (TypeError, ValueError):
                sauber[name] = 0
        elif name == "neu":
            sauber[name] = bool(wert)
        elif name == "idee":
            if isinstance(wert, dict):
                sauber[name] = {k: str(v)[:300] for k, v in wert.items() if k in ("name", "zielgruppe", "angebot", "preis")}
        else:
            sauber[name] = str(wert)[:laenge]
    return sauber
