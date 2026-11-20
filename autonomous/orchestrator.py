# -*- coding: utf-8 -*-
"""Orchestrierung: Warteschlange mit begrenzter Parallelität (Abschnitt 5.8).

Es laufen höchstens ``max_parallel`` Arbeiter (Threads). Jeder holt atomar die nächste bereite
Aufgabe, gibt sie der verantwortlichen Rolle, lässt das Ergebnis vom Supervisor prüfen und
speichert es. Folgeaufgaben, die ein Agent vorschlägt, werden als neue Aufgaben angelegt.
"""

import threading
import traceback

from .agenten import Blockiert, FreigabeNoetig


class Orchestrator:
    def __init__(self, kern, takt=1.0):
        self.kern = kern
        self.takt = takt
        self._stopp = threading.Event()
        self._threads = []
        self._aktiv = 0
        self._sperre = threading.Lock()
        self.bearbeitet = 0

    def status(self):
        return {"laeuft": any(t.is_alive() for t in self._threads), "arbeiter": len(self._threads),
                "beschaeftigt": self._aktiv, "bearbeitet_seit_start": self.bearbeitet}

    def starten(self):
        n = self.kern.einstellungen.hole("max_parallel")
        self._stopp.clear()
        for i in range(n):
            t = threading.Thread(target=self._schleife, name="arbeiter-%d" % i, daemon=True)
            t.start()
            self._threads.append(t)
        self.kern.orchestrator = self

    def stoppen(self, warten=5):
        self._stopp.set()
        for t in self._threads:
            t.join(timeout=warten)
        self._threads = []

    def _schleife(self):
        while not self._stopp.is_set():
            try:
                if not self.einmal():
                    self._stopp.wait(self.takt)
            except Exception:  # Arbeiter darf nie sterben
                self.kern.protokoll.fehler("orchestrator", "Unerwarteter Fehler im Arbeiter", traceback.format_exc())
                self._stopp.wait(self.takt)

    def einmal(self):
        """Bearbeitet höchstens eine Aufgabe. Gibt True zurück, wenn etwas bearbeitet wurde."""
        aufgabe = self.kern.aufgaben.naechste_beanspruchen(self.kern.register.rollen())
        if not aufgabe:
            return False
        with self._sperre:
            self._aktiv += 1
        try:
            self._bearbeiten(aufgabe)
        finally:
            with self._sperre:
                self._aktiv -= 1
                self.bearbeitet += 1
        return True

    def alle_abarbeiten(self, maximal=100):
        """Für Tests und die Kommandozeile: synchron abarbeiten, bis nichts mehr bereit ist."""
        n = 0
        while n < maximal and self.einmal():
            n += 1
        return n

    def _bearbeiten(self, aufgabe):
        try:
            self._bearbeiten_intern(aufgabe)
        except ValueError:
            # Wurde die Aufgabe während der Bearbeitung vom Eigentümer abgebrochen, ist der letzte
            # Statuswechsel nicht mehr erlaubt. Das ist kein Fehler: Ergebnis verwerfen, sauber protokollieren.
            status = self.kern.db.wert("SELECT status FROM aufgaben WHERE id=?", (aufgabe["id"],))
            if status == "laufend":
                raise
            self.kern.protokoll.info("orchestrator", "Aufgabe wurde während der Bearbeitung beendet – Ergebnis "
                                     "verworfen, keine Folgeaufgaben", {"aufgabe": aufgabe["id"], "status": status})

    def _bearbeiten_intern(self, aufgabe):
        k = self.kern
        agent = k.register.hole(aufgabe["verantwortlich"])
        aid = aufgabe["id"]
        try:
            ergebnis = agent.bearbeite(aufgabe, k)
        except FreigabeNoetig as f:
            k.aufgaben.warten_auf_freigabe(aid, f.entscheidung.freigabe_id, agent.rolle, f.entscheidung.grund)
            return
        except Blockiert as b:
            k.aufgaben.abbrechen(aid, "supervisor", "Blockiert: %s" % b)
            return
        except (ValueError, KeyError, PermissionError) as fehler:
            # Fachliche Fehler: nicht sinnlos wiederholen
            k.db.ausfuehren("UPDATE aufgaben SET max_versuche=versuche WHERE id=?", (aid,))
            k.aufgaben.fehlschlag(aid, "%s: %s" % (type(fehler).__name__, fehler), agent.rolle)
            return
        except Exception as fehler:
            k.protokoll.fehler("orchestrator", "Agentenfehler", {"aufgabe": aid, "fehler": traceback.format_exc()})
            k.aufgaben.fehlschlag(aid, "%s: %s" % (type(fehler).__name__, fehler), agent.rolle)
            return

        ergebnis = ergebnis or {}
        folge = ergebnis.pop("folgeaufgaben", []) if isinstance(ergebnis, dict) else []
        maengel = k.supervisor.ergebnis_pruefen(agent.rolle, ergebnis)
        if maengel:
            k.protokoll.warnung("supervisor", "Ergebnis abgelehnt", {"aufgabe": aid, "maengel": maengel})
            k.db.ausfuehren("UPDATE aufgaben SET max_versuche=versuche WHERE id=?", (aid,))
            k.aufgaben.fehlschlag(aid, "Supervisor: " + "; ".join(maengel), "supervisor")
            return
        k.aufgaben.abschliessen(aid, ergebnis, agent.rolle)
        for f in folge[:10]:  # Agenten können keine Aufgabenlawine auslösen
            if k.register.hole(f.get("verantwortlich")) is None:
                continue
            k.aufgaben.anlegen(f["titel"], f["typ"], f["verantwortlich"], agent.rolle, f.get("eingabe"),
                               f.get("prioritaet", 3), eltern_id=aid)
