# -*- coding: utf-8 -*-
"""Persistente Aufgabenverwaltung (Abschnitt 9).

Status: geplant, bereit, laufend, wartet_auf_freigabe, abgeschlossen, fehlgeschlagen, abgebrochen.
Jeder Statuswechsel wird im Verlauf gespeichert. Wiederholungen sind begrenzt (max_versuche),
mit wachsender Wartezeit – keine Endlosschleifen. Nach einem Neustart werden Aufgaben, die mitten
im Lauf unterbrochen wurden, wieder auf ``bereit`` gesetzt (oder als fehlgeschlagen markiert,
wenn die Versuche aufgebraucht sind).
"""

import datetime
import json

from .db import jetzt, neue_id

STATUS = ("geplant", "bereit", "laufend", "wartet_auf_freigabe", "abgeschlossen", "fehlgeschlagen", "abgebrochen")
ENDSTATUS = ("abgeschlossen", "fehlgeschlagen", "abgebrochen")
UEBERGAENGE = {
    "geplant": {"bereit", "abgebrochen"},
    "bereit": {"laufend", "abgebrochen", "geplant"},
    "laufend": {"abgeschlossen", "fehlgeschlagen", "bereit", "wartet_auf_freigabe", "abgebrochen"},
    "wartet_auf_freigabe": {"bereit", "abgebrochen"},
    "abgeschlossen": set(),
    "fehlgeschlagen": {"bereit"},   # nur manuell durch den Eigentümer erneut anstoßen
    "abgebrochen": set(),
}
MAX_EINGABE = 200_000


def _json(wert):
    return json.dumps(wert, ensure_ascii=False, default=str)


class Aufgaben:
    def __init__(self, db, protokoll):
        self.db = db
        self.protokoll = protokoll

    def anlegen(self, titel, typ, verantwortlich, ersteller, eingabe=None, prioritaet=3, sofort_bereit=True,
                max_versuche=3, eltern_id=None):
        if not str(titel).strip():
            raise ValueError("Titel fehlt.")
        if not 1 <= int(prioritaet) <= 5:
            raise ValueError("Priorität 1 (hoch) bis 5 (niedrig).")
        if not 1 <= int(max_versuche) <= 10:
            raise ValueError("max_versuche 1 bis 10.")
        eingabe_text = _json(eingabe or {})
        if len(eingabe_text) > MAX_EINGABE:
            raise ValueError("Eingabe zu groß.")
        aid = neue_id("a_")
        z = jetzt()
        status = "bereit" if sofort_bereit else "geplant"
        self.db.ausfuehren(
            "INSERT INTO aufgaben (id, titel, typ, ersteller, verantwortlich, status, prioritaet, erstellt,"
            " aktualisiert, eingabe, max_versuche, eltern_id) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (aid, str(titel).strip()[:200], typ, ersteller, verantwortlich, status, int(prioritaet), z, z,
             eingabe_text, int(max_versuche), eltern_id))
        self._verlauf(aid, None, status, ersteller, "angelegt")
        return aid

    def hole(self, aid):
        a = self.db.eins("SELECT * FROM aufgaben WHERE id=?", (aid,))
        if a:
            a["eingabe"] = json.loads(a["eingabe"] or "{}")
            a["ergebnis"] = json.loads(a["ergebnis"]) if a["ergebnis"] else None
        return a

    def liste(self, status=None, verantwortlich=None, grenze=300):
        sql, p = "SELECT * FROM aufgaben WHERE 1=1", []
        if status:
            sql += " AND status=?"
            p.append(status)
        if verantwortlich:
            sql += " AND verantwortlich=?"
            p.append(verantwortlich)
        sql += " ORDER BY CASE WHEN status IN ('abgeschlossen','fehlgeschlagen','abgebrochen') THEN 1 ELSE 0 END," \
               " prioritaet, erstellt DESC LIMIT ?"
        p.append(grenze)
        ergebnis = self.db.alle(sql, p)
        for a in ergebnis:
            a["eingabe"] = json.loads(a["eingabe"] or "{}")
            a["ergebnis"] = json.loads(a["ergebnis"]) if a["ergebnis"] else None
        return ergebnis

    def verlauf(self, aid):
        return self.db.alle("SELECT * FROM aufgaben_verlauf WHERE aufgabe_id=? ORDER BY id", (aid,))

    def _verlauf(self, aid, von, nach, akteur, notiz=None):
        self.db.ausfuehren("INSERT INTO aufgaben_verlauf (aufgabe_id, zeit, von_status, nach_status, akteur, notiz)"
                           " VALUES (?,?,?,?,?,?)", (aid, jetzt(), von, nach, akteur, (notiz or "")[:1000]))

    def _wechsel(self, aid, nach, akteur, notiz=None, **felder):
        a = self.db.eins("SELECT status FROM aufgaben WHERE id=?", (aid,))
        if not a:
            raise KeyError("Aufgabe nicht gefunden.")
        von = a["status"]
        if nach not in UEBERGAENGE[von]:
            raise ValueError("Statuswechsel %s → %s nicht erlaubt." % (von, nach))
        setz = ["status=?", "aktualisiert=?"]
        werte = [nach, jetzt()]
        for k, v in felder.items():
            setz.append("%s=?" % k)
            werte.append(v)
        werte += [aid, von]
        n = self.db.ausfuehren("UPDATE aufgaben SET %s WHERE id=? AND status=?" % ", ".join(setz), werte)
        if n != 1:
            raise ValueError("Aufgabe wurde parallel verändert.")
        self._verlauf(aid, von, nach, akteur, notiz)

    # ---- Ablauf ------------------------------------------------------
    def naechste_beanspruchen(self, rollen):
        """Holt atomar die wichtigste bereite Aufgabe für eine der Rollen und setzt sie auf laufend."""
        if not rollen:
            return None
        platz = ",".join("?" * len(rollen))
        with self.db.transaktion() as con:
            zeile = con.execute(
                "SELECT id FROM aufgaben WHERE status='bereit' AND verantwortlich IN (%s) "
                "AND (naechster_versuch IS NULL OR naechster_versuch<=?) ORDER BY prioritaet, erstellt LIMIT 1"
                % platz, (*rollen, jetzt())).fetchone()
            if not zeile:
                return None
            z = jetzt()
            con.execute("UPDATE aufgaben SET status='laufend', gestartet=?, aktualisiert=?, versuche=versuche+1 "
                        "WHERE id=? AND status='bereit'", (z, z, zeile["id"]))
            con.execute("INSERT INTO aufgaben_verlauf (aufgabe_id, zeit, von_status, nach_status, akteur, notiz)"
                        " VALUES (?,?,?,?,?,?)", (zeile["id"], z, "bereit", "laufend", "orchestrator", "gestartet"))
        return self.hole(zeile["id"])

    def abschliessen(self, aid, ergebnis, akteur):
        self._wechsel(aid, "abgeschlossen", akteur, "fertig", ergebnis=_json(ergebnis), beendet=jetzt(), fehler=None)

    def fehlschlag(self, aid, fehler, akteur):
        """Fehler speichern; erneut versuchen, solange Versuche übrig sind (mit Wartezeit)."""
        a = self.db.eins("SELECT versuche, max_versuche FROM aufgaben WHERE id=?", (aid,))
        fehler = str(fehler)[:2000]
        if a["versuche"] < a["max_versuche"]:
            warte = 30 * (2 ** (a["versuche"] - 1))
            naechster = (datetime.datetime.now().astimezone() + datetime.timedelta(seconds=warte)).isoformat(
                timespec="seconds")
            self._wechsel(aid, "bereit", akteur, "Fehler, neuer Versuch in %ss: %s" % (warte, fehler),
                          fehler=fehler, naechster_versuch=naechster)
            return "erneut"
        self._wechsel(aid, "fehlgeschlagen", akteur, fehler, fehler=fehler, beendet=jetzt())
        self.protokoll.fehler("aufgaben", "Aufgabe endgültig fehlgeschlagen", {"id": aid, "fehler": fehler})
        return "fehlgeschlagen"

    def warten_auf_freigabe(self, aid, freigabe_id, akteur, notiz=""):
        self._wechsel(aid, "wartet_auf_freigabe", akteur, notiz or "wartet auf Freigabe %s" % freigabe_id,
                      freigabe_id=freigabe_id)

    def freigabe_entschieden(self, freigabe_id, erteilt):
        """Weckt Aufgaben auf, die auf diese Freigabe warten (oder bricht sie bei Ablehnung ab)."""
        for a in self.db.alle("SELECT id FROM aufgaben WHERE freigabe_id=? AND status='wartet_auf_freigabe'",
                              (freigabe_id,)):
            if erteilt:
                # Der Versuch, der auf die Freigabe stieß, zählt nicht als Fehlversuch
                self.db.ausfuehren("UPDATE aufgaben SET versuche=MAX(versuche-1,0) WHERE id=?", (a["id"],))
                self._wechsel(a["id"], "bereit", "eigentuemer", "Freigabe erteilt")
            else:
                self._wechsel(a["id"], "abgebrochen", "eigentuemer", "Freigabe abgelehnt", beendet=jetzt())

    def abbrechen(self, aid, akteur, grund=""):
        a = self.db.eins("SELECT status FROM aufgaben WHERE id=?", (aid,))
        if not a:
            raise KeyError("Aufgabe nicht gefunden.")
        if a["status"] in ENDSTATUS:
            raise ValueError("Aufgabe ist bereits beendet.")
        self._wechsel(aid, "abgebrochen", akteur, grund or "abgebrochen", beendet=jetzt())

    def freigeben(self, aid, akteur):
        """geplant → bereit, oder fehlgeschlagen → bereit (neuer Anlauf durch den Eigentümer)."""
        a = self.db.eins("SELECT status FROM aufgaben WHERE id=?", (aid,))
        if not a:
            raise KeyError("Aufgabe nicht gefunden.")
        if a["status"] == "fehlgeschlagen":
            if akteur != "eigentuemer":
                raise PermissionError("Nur der Eigentümer stößt fehlgeschlagene Aufgaben neu an.")
            self._wechsel(aid, "bereit", akteur, "neu angestoßen", versuche=0, naechster_versuch=None, beendet=None)
        else:
            self._wechsel(aid, "bereit", akteur, "freigegeben")

    def wiederherstellen(self):
        """Beim Start: unterbrochene 'laufend'-Aufgaben in einen konsistenten Zustand bringen."""
        ergebnis = {"zurueckgesetzt": 0, "fehlgeschlagen": 0}
        for a in self.db.alle("SELECT id, versuche, max_versuche FROM aufgaben WHERE status='laufend'"):
            if a["versuche"] < a["max_versuche"]:
                self._wechsel(a["id"], "bereit", "system", "nach Neustart wieder bereit (Lauf war unterbrochen)")
                ergebnis["zurueckgesetzt"] += 1
            else:
                self._wechsel(a["id"], "fehlgeschlagen", "system", "nach Neustart: Versuche aufgebraucht",
                              fehler="Lauf durch Neustart unterbrochen", beendet=jetzt())
                ergebnis["fehlgeschlagen"] += 1
        if any(ergebnis.values()):
            self.protokoll.warnung("aufgaben", "Wiederherstellung nach Neustart", ergebnis)
        return ergebnis

    def zaehlen(self):
        zahlen = {s: 0 for s in STATUS}
        for z in self.db.alle("SELECT status, COUNT(*) AS n FROM aufgaben GROUP BY status"):
            zahlen[z["status"]] = z["n"]
        return zahlen
