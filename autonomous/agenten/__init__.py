# -*- coding: utf-8 -*-
"""Agenten-Grundgerüst und Rollenregister (Abschnitt 5).

Ein Agent ist eine Rolle mit festen Aufgabentypen und festen Rechten (im Code, nicht änderbar
durch Agenten). Mehrere logische Rollen können dieselbe Implementierung nutzen – so lassen sich
später bis zu 500 Rollen registrieren, ohne 500 Prozesse zu starten. Abgearbeitet wird über die
Warteschlange mit begrenzter Parallelität (siehe orchestrator.py).
"""

import json

from ..db import jetzt

MAX_ROLLEN = 500


class FreigabeNoetig(Exception):
    def __init__(self, entscheidung):
        super().__init__(entscheidung.grund)
        self.entscheidung = entscheidung


class Blockiert(Exception):
    pass


class Agent:
    rolle = "basis"
    name = "Basis"
    beschreibung = ""
    rechte = frozenset()
    aufgabentypen = {}  # typ -> Beschreibung; Methode heißt aufgabe_<typ>

    def bearbeite(self, aufgabe, kern):
        methode = getattr(self, "aufgabe_" + aufgabe["typ"], None)
        if methode is None or aufgabe["typ"] not in self.aufgabentypen:
            raise ValueError("Rolle %s kennt den Aufgabentyp '%s' nicht." % (self.rolle, aufgabe["typ"]))
        return methode(aufgabe, kern)

    # Hilfe: jede relevante Aktion läuft über den Supervisor
    def darf(self, kern, aktion, ziel, aufgabe=None, **kw):
        e = kern.supervisor.pruefe(self.rolle, aktion, ziel, aufgabe_id=aufgabe and aufgabe["id"], **kw)
        if e.ergebnis == "erlaubt":
            return e
        if e.ergebnis in ("freigabe_noetig", "wartet"):
            raise FreigabeNoetig(e)
        raise Blockiert(e.grund)


class Register:
    def __init__(self):
        self._agenten = {}

    def registrieren(self, agent):
        if len(self._agenten) >= MAX_ROLLEN and agent.rolle not in self._agenten:
            raise ValueError("Maximal %d Rollen." % MAX_ROLLEN)
        self._agenten[agent.rolle] = agent

    def hole(self, rolle):
        return self._agenten.get(rolle)

    def rollen(self):
        return list(self._agenten)

    def rechte(self, rolle):
        a = self._agenten.get(rolle)
        return set(a.rechte) if a else set()

    def alle(self):
        return list(self._agenten.values())

    def in_db_spiegeln(self, db):
        """Spiegelt die Rollen in die Datenbank (nur zur Anzeige). Rechte kommen IMMER aus dem Code."""
        for a in self._agenten.values():
            db.ausfuehren(
                "INSERT INTO agenten_rollen VALUES (?,?,?,?,1,?,?,?) ON CONFLICT(rolle) DO UPDATE SET "
                "name=excluded.name, beschreibung=excluded.beschreibung, handler=excluded.handler, "
                "erlaubte_aktionen=excluded.erlaubte_aktionen, aufgabentypen=excluded.aufgabentypen",
                (a.rolle, a.name, a.beschreibung, type(a).__module__ + "." + type(a).__name__,
                 json.dumps(sorted(a.rechte)), json.dumps(a.aufgabentypen, ensure_ascii=False), jetzt()))


def standard_register():
    from .ceo import CeoAgent
    from .research import ResearchAgent
    from .product import ProductAgent
    from .sales import SalesAgent
    from .finance import FinanceAgent
    from .learning import LearningAgent

    r = Register()
    for klasse in (CeoAgent, ResearchAgent, ProductAgent, SalesAgent, FinanceAgent, LearningAgent):
        r.registrieren(klasse())
    return r
