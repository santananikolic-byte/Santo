# -*- coding: utf-8 -*-
"""Berechtigungsschicht - entscheidet in der Software, ob eine Aktion laufen darf.

Reihenfolge der Prüfung für jede Aktion des Modells:

1. Notstopp aktiv?                           -> verweigert
2. Werkzeug einzeln abgeschaltet?            -> verweigert ("Rechte widerrufen")
3. Rolle erlaubt dieses Werkzeug nicht?      -> verweigert
4. Werkzeug nur für das Gespräch gedacht?    -> in Aufträgen verweigert
5. Stufe bestimmen (1 frei, 2 Meldung, 3 Freigabe); im Bereich "privat" brauchen
   Aktionen nach außen immer Stufe 3
6. War schon Außenwelt im Spiel (Websuche)?  -> Stufe 2 wird zu Stufe 3
   (Webinhalte könnten Anweisungen enthalten; sie bekommen nie selbst Rechte)

Eine Freigabe gilt nur für die eine gezeigte Aktion mit genau diesen Parametern.
Sie läuft nach ``freigabe_minuten`` ab, wird beim Erteilen erneut gegen Notstopp
und Sperren geprüft, und Dateien dürfen sich zwischen Anfrage und Erteilung nicht
geändert haben. Alles wird im Audit festgehalten.
"""

import json
import threading
import time
from collections import namedtuple

from . import rollen, zeit
from .werkzeuge import FREI, FREIGABE, MELDUNG, Kontext

Entscheidung = namedtuple("Entscheidung", "art stufe grund")  # art: ausfuehren | freigabe | verweigert

PRIVAT = "privat"


class Berechtigung:
    def __init__(self, agent):
        self.agent = agent
        self._signale = {}
        self._sperre = threading.Lock()

    # ---------------------------------------------------------- Prüfung ---

    def sichtbar(self, w, rolle):
        """Soll das Werkzeug dem Modell in dieser Rolle überhaupt gezeigt werden?"""
        if w.name in self.agent.konfig.deaktivierte_werkzeuge or not rollen.erlaubt(rolle, w.name):
            return False
        return not (w.nur_chat and rolle != "allgemein")

    def entscheiden(self, w, params, ctx):
        a = self.agent
        if a.gesperrt.is_set():
            return Entscheidung("verweigert", 0, "Notstopp ist aktiv.")
        if w.name in a.konfig.deaktivierte_werkzeuge:
            return Entscheidung("verweigert", 0, "Dieses Werkzeug ist abgeschaltet.")
        if not rollen.erlaubt(ctx.rolle, w.name):
            return Entscheidung("verweigert", 0, "Die Rolle %s darf %s nicht benutzen." % (ctx.rolle, w.name))
        if w.nur_chat and ctx.quelle != "chat":
            return Entscheidung("verweigert", 0, "%s gibt es nur im Gespräch, nicht innerhalb eines Auftrags." % w.name)
        stufe = w.stufe_fuer(ctx, params)
        grund = ""
        if w.privat_freigabe and ctx.bereich == PRIVAT:
            stufe, grund = FREIGABE, "Im privaten Bereich gehen Anfragen nach außen nur nach Freigabe."
        if ctx.extern and stufe == MELDUNG:
            stufe, grund = FREIGABE, "Es war schon Außenwelt im Spiel (Websuche); jetzt entscheidest du."
        return Entscheidung("freigabe" if stufe >= FREIGABE else "ausfuehren", stufe, grund)

    # --------------------------------------------------------- Freigaben ---

    def anfordern(self, w, params, ctx, stufe, grund=""):
        """Speichert die Aktion als offene Freigabe (ausgeführt wird noch nichts). Gibt die Nummer zurück."""
        a = self.agent
        vorschau = w.vorschau(ctx, params) if w.vorschau else "Aufruf: %s\n%s" % (
            w.name, json.dumps({k: v for k, v in params.items() if not k.startswith("_")}, ensure_ascii=False, indent=2))
        risiko = " ".join(t for t in (w.risiko, grund) if t)
        freigabe_id = a.speicher.freigabe_anlegen(w.name, params, vorschau, risiko, stufe, ctx.bereich,
                                                  auftrag_id=ctx.auftrag_id, gespraech=ctx.gespraech,
                                                  liefert_daten=w.liefert_daten)
        if ctx.warten:
            with self._sperre:
                self._signale[freigabe_id] = threading.Event()
        a.speicher.audit_schreiben("freigabe_angefragt", werkzeug=w.name, stufe=stufe, bereich=ctx.bereich,
                                   details={"vorschau": vorschau[:500], "grund": grund}, auftrag_id=ctx.auftrag_id,
                                   freigabe_id=freigabe_id)
        a.log.ereignis("freigabe_angefragt", freigabe=freigabe_id, werkzeug=w.name, berechtigungsstufe=stufe)
        return freigabe_id

    def erteilen(self, freigabe_id):
        """Der Nutzer sagt Ja. Gibt (HTTP-Code, Antwort) zurück; ausgeführt wird genau diese eine Aktion."""
        a = self.agent
        rec = a.speicher.freigabe(freigabe_id)
        if not rec:
            return 404, {"ok": False, "fehler": "Diese Freigabe gibt es nicht."}
        if rec["status"] != "offen":
            return 409, {"ok": False, "fehler": "Diese Freigabe ist schon %s." % rec["status"]}
        if rec["zeit"] < zeit.vor_minuten(a.konfig.freigabe_minuten):
            self._beenden(freigabe_id, "abgelaufen", "Abgelaufen, bevor du geantwortet hast.")
            return 410, {"ok": False, "fehler": "Diese Freigabe ist abgelaufen. Bitte neu anfragen."}
        if a.gesperrt.is_set():
            return 423, {"ok": False, "fehler": "Notstopp ist aktiv. Erst entsperren."}
        w = a.register.get(rec["werkzeug"])
        if w is None or w.name in a.konfig.deaktivierte_werkzeuge:
            self._beenden(freigabe_id, "abgelehnt", "Werkzeug ist inzwischen abgeschaltet.")
            return 403, {"ok": False, "fehler": "Das Werkzeug ist inzwischen abgeschaltet."}
        if not a.speicher.freigabe_entscheiden(freigabe_id, "erteilt"):
            return 409, {"ok": False, "fehler": "Diese Freigabe wurde gerade anderweitig entschieden."}
        a.speicher.audit_schreiben("freigabe_erteilt", werkzeug=w.name, stufe=rec["stufe"], bereich=rec["bereich"],
                                   auftrag_id=rec["auftrag_id"], freigabe_id=freigabe_id)
        ctx = Kontext(a, rec["bereich"], gespraech=rec["gespraech"], auftrag_id=rec["auftrag_id"], quelle="freigabe")
        ergebnis = a.ausfuehren(w, rec["parameter"], ctx, rec["stufe"], freigabe_id=freigabe_id)
        ok = ergebnis["status"] == "ausgefuehrt"
        a.speicher.freigabe_ergebnis_setzen(freigabe_id, ergebnis["text"], status="ausgefuehrt" if ok else "fehlgeschlagen")
        self._signalisieren(freigabe_id)
        return 200, {"ok": ok, "ergebnis": ergebnis, "weiter": bool(ok and w.liefert_daten and rec["gespraech"]),
                     "gespraech": rec["gespraech"]}

    def ablehnen(self, freigabe_id):
        a = self.agent
        rec = a.speicher.freigabe(freigabe_id)
        if not rec:
            return 404, {"ok": False, "fehler": "Diese Freigabe gibt es nicht."}
        if not a.speicher.freigabe_entscheiden(freigabe_id, "abgelehnt", "Vom Nutzer abgelehnt."):
            return 409, {"ok": False, "fehler": "Diese Freigabe ist schon %s." % rec["status"]}
        a.speicher.audit_schreiben("freigabe_abgelehnt", werkzeug=rec["werkzeug"], stufe=rec["stufe"],
                                   bereich=rec["bereich"], auftrag_id=rec["auftrag_id"], freigabe_id=freigabe_id)
        self._signalisieren(freigabe_id)
        return 200, {"ok": True, "status": "abgelehnt"}

    def _beenden(self, freigabe_id, status, text):
        a = self.agent
        if a.speicher.freigabe_entscheiden(freigabe_id, status, text):
            rec = a.speicher.freigabe(freigabe_id)
            a.speicher.audit_schreiben("freigabe_" + status, werkzeug=rec["werkzeug"], stufe=rec["stufe"],
                                       bereich=rec["bereich"], auftrag_id=rec["auftrag_id"], freigabe_id=freigabe_id)
        self._signalisieren(freigabe_id)

    def ablaufen_lassen(self):
        """Wird regelmäßig aufgerufen: alte offene Freigaben verfallen."""
        a = self.agent
        for freigabe_id in a.speicher.freigaben_ablaufen(zeit.vor_minuten(a.konfig.freigabe_minuten)):
            rec = a.speicher.freigabe(freigabe_id)
            a.speicher.audit_schreiben("freigabe_abgelaufen", werkzeug=rec["werkzeug"], stufe=rec["stufe"],
                                       bereich=rec["bereich"], auftrag_id=rec["auftrag_id"], freigabe_id=freigabe_id)
            self._signalisieren(freigabe_id)

    def alle_offenen_ablehnen(self, grund):
        a = self.agent
        for rec in a.speicher.freigaben("offen", limit=500):
            if a.speicher.freigabe_entscheiden(rec["id"], "abgelehnt", grund):
                a.speicher.audit_schreiben("freigabe_abgelehnt", werkzeug=rec["werkzeug"], stufe=rec["stufe"],
                                           bereich=rec["bereich"], details={"grund": grund}, freigabe_id=rec["id"])
            self._signalisieren(rec["id"])

    # ----------------------------------------------------- Warten (Läufer) ---

    def _signalisieren(self, freigabe_id):
        with self._sperre:
            signal = self._signale.get(freigabe_id)
        if signal:
            signal.set()

    def warten(self, freigabe_ids, timeout):
        """Wartet, bis alle genannten Freigaben entschieden sind (oder ``timeout`` abläuft)."""
        ende = time.time() + timeout
        for freigabe_id in freigabe_ids:
            with self._sperre:
                signal = self._signale.get(freigabe_id)
            if signal is not None:
                signal.wait(timeout=max(0.0, ende - time.time()))
            with self._sperre:
                self._signale.pop(freigabe_id, None)

    def werkzeug_sperren(self, name, sperren):
        """Einzelnes Werkzeug abschalten oder wieder erlauben. Offene Freigaben dafür werden beim Abschalten abgelehnt."""
        a = self.agent
        if a.register.get(name) is None:
            return False
        aktuell = set(a.konfig.deaktivierte_werkzeuge)
        (aktuell.add if sperren else aktuell.discard)(name)
        a.konfig.aktualisieren({"deaktivierte_werkzeuge": sorted(aktuell)})
        a.speicher.audit_schreiben("werkzeug_gesperrt" if sperren else "werkzeug_erlaubt", werkzeug=name)
        if sperren:
            for rec in a.speicher.freigaben("offen", limit=500):
                if rec["werkzeug"] == name:
                    self.ablehnen(rec["id"])
        return True


__all__ = ["Berechtigung", "Entscheidung", "FREI", "MELDUNG", "FREIGABE"]
