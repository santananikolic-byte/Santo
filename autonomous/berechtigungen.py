# -*- coding: utf-8 -*-
"""Zentrales Berechtigungs- und Freigabesystem (Abschnitt 8 des Auftrags).

Jede Agentenaktion hat eine Risikoklasse:
- AUTO      – automatisch erlaubt (lokal, intern, Tests)
- FREIGABE  – nur nach ausdrücklichem Ja des Eigentümers; ein Ja gilt für genau eine Ausführung
- VERBOTEN  – wird immer blockiert

Unbekannte Aktionen gelten als VERBOTEN (sichere Grundeinstellung).
Abgelehnte Freigaben sind bindend: Dieselbe Aktion (gleicher Fingerabdruck – unabhängig vom
anfragenden Agenten) wird danach sofort blockiert, ohne den Eigentümer erneut zu fragen.
Agenten können ihre Rechte nicht erweitern: Rollenrechte stehen im Code, die Prüfung
schneidet sie mit dem Aktionskatalog.
"""

import hashlib
import json
import os

from . import konfig
from .db import jetzt, neue_id

AUTO, FREIGABE, VERBOTEN = "auto", "freigabe", "verboten"

AKTIONEN = {
    # automatisch erlaubt
    "lokale_recherche": (AUTO, "Lokale Daten und Vorlagen auswerten"),
    "interne_planung": (AUTO, "Pläne, Aufgaben und Prioritäten intern anlegen"),
    "datei_erstellen": (AUTO, "Datei im freigegebenen Projektbereich erzeugen"),
    "test_ausfuehren": (AUTO, "Interne Prüfungen und Tests ausführen"),
    "interne_auswertung": (AUTO, "Kennzahlen und Auswertungen berechnen"),
    "gedaechtnis_vorschlag": (AUTO, "Hypothese oder Vorschlag im Gedächtnis ablegen"),
    "wallet_simulation": (AUTO, "Simulierte Buchung im internen Wallet"),
    "entwurf_erstellen": (AUTO, "Entwurf (Nachricht, Angebot) lokal erstellen – wird nicht versendet"),
    "lokales_modell": (AUTO, "Lokales, kostenloses Modell abfragen (im Tageslimit)"),
    # Freigabe erforderlich
    "externe_nachricht": (FREIGABE, "Nachricht an Externe senden (E-Mail, Brief, Messenger)"),
    "veroeffentlichung": (FREIGABE, "Inhalt veröffentlichen"),
    "kundenkontakt": (FREIGABE, "Kunden oder Interessenten kontaktieren"),
    "personenbezogene_daten": (FREIGABE, "Personenbezogene Daten verwenden oder weitergeben"),
    "kostenpflichtiger_dienst": (FREIGABE, "Kostenpflichtigen Dienst nutzen"),
    "echte_zahlung": (FREIGABE, "Echtes Geld bewegen"),
    "vertrag_annehmen": (FREIGABE, "Vertrag oder bindende Erklärung abgeben"),
    "irreversibel": (FREIGABE, "Nicht umkehrbare Aktion"),
    "web_abruf": (FREIGABE, "Externe Webseite abrufen"),
    # verboten
    "sicherheit_umgehen": (VERBOTEN, "Sicherheitsmechanismen umgehen"),
    "unautorisierter_zugriff": (VERBOTEN, "Unautorisierter Zugriff"),
    "taeuschung": (VERBOTEN, "Täuschung"),
    "spam": (VERBOTEN, "Massenhafte unerwünschte Werbung"),
    "datenverkauf": (VERBOTEN, "Daten ohne Rechtsgrundlage verkaufen"),
    "fremdes_konto": (VERBOTEN, "Zugriff auf fremde Konten"),
    "rechte_aendern": (VERBOTEN, "Eigene oder fremde Agentenrechte ändern"),
}


def risikoklasse(aktion):
    return AKTIONEN.get(aktion, (VERBOTEN, "Unbekannte Aktion"))[0]


def fingerabdruck(aktion, ziel, nutzlast=None):
    """Identität einer Aktion – bewusst ohne Agentennamen, damit ein anderer Agent eine
    Ablehnung nicht umgehen kann."""
    roh = json.dumps({"a": aktion, "z": str(ziel).strip().lower(), "n": nutzlast or {}},
                     sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(roh.encode("utf-8")).hexdigest()[:32]


class Entscheidung:
    def __init__(self, ergebnis, grund, freigabe_id=None):
        self.ergebnis = ergebnis  # erlaubt | freigabe_noetig | wartet | verboten
        self.grund = grund
        self.freigabe_id = freigabe_id

    @property
    def erlaubt(self):
        return self.ergebnis == "erlaubt"

    def als_dict(self):
        return {"ergebnis": self.ergebnis, "grund": self.grund, "freigabe_id": self.freigabe_id}


class Supervisor:
    """Prüft Berechtigungen, Kostenlimits und externe Aktionen; protokolliert jede Entscheidung."""

    def __init__(self, db, protokoll, einstellungen, rollen_rechte):
        self.db = db
        self.protokoll = protokoll
        self.einstellungen = einstellungen
        self._rollen_rechte = rollen_rechte  # Funktion rolle -> set(aktionen), aus dem Code

    # ---- Kernprüfung -------------------------------------------------
    def pruefe(self, agent, aktion, ziel, *, kosten_cent=0, datenumfang="keine personenbezogenen Daten",
               folgen="", nutzlast=None, aufgabe_id=None, datei_pfad=None):
        klasse = risikoklasse(aktion)
        rechte = self._rollen_rechte(agent)
        details = {"agent": agent, "aktion": aktion, "ziel": str(ziel)[:200], "kosten_cent": kosten_cent}

        if klasse == VERBOTEN:
            return self._blockiert(details, "Aktion ist verboten" if aktion in AKTIONEN else "Unbekannte Aktion")
        if aktion not in rechte:
            return self._blockiert(details, "Rolle %s hat das Recht '%s' nicht" % (agent, aktion))
        if datei_pfad is not None and not pfad_erlaubt(datei_pfad):
            return self._blockiert(details, "Dateipfad außerhalb des freigegebenen Bereichs")
        if kosten_cent and kosten_cent > 0 and not self.einstellungen.hole("kostenpflichtig_erlaubt"):
            return self._blockiert(details, "Kostenpflichtige Aktionen sind gesperrt (Einstellungen)")

        fp = fingerabdruck(aktion, ziel, nutzlast)
        # Alles Weitere in EINER Transaktion: parallel arbeitende Agenten können ein Ja nicht doppelt
        # verbrauchen und keine doppelten Anfragen erzeugen.
        with self.db.transaktion() as con:
            abgelehnt = con.execute("SELECT id FROM freigaben WHERE fingerabdruck=? AND status='abgelehnt'",
                                    (fp,)).fetchone()
            if abgelehnt:
                ergebnis = ("blockiert", abgelehnt["id"])
            elif klasse == AUTO and not kosten_cent:
                ergebnis = ("auto", None)
            else:
                erteilt = con.execute("SELECT id FROM freigaben WHERE fingerabdruck=? AND status='erteilt' "
                                      "ORDER BY zeit LIMIT 1", (fp,)).fetchone()
                offen = con.execute("SELECT id FROM freigaben WHERE fingerabdruck=? AND status='offen'",
                                    (fp,)).fetchone()
                if erteilt and con.execute("UPDATE freigaben SET status='verbraucht' WHERE id=? AND "
                                           "status='erteilt'", (erteilt["id"],)).rowcount == 1:
                    ergebnis = ("verbraucht", erteilt["id"])  # ein Ja gilt für genau eine Ausführung
                elif offen:
                    ergebnis = ("wartet", offen["id"])
                else:
                    fid = neue_id("f_")
                    con.execute(
                        "INSERT INTO freigaben (id, zeit, agent, aktion, ziel, kosten_cent, datenumfang, folgen, risiko,"
                        " fingerabdruck, status, nutzlast, aufgabe_id) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                        (fid, jetzt(), agent, aktion, str(ziel)[:500], int(kosten_cent or 0), str(datenumfang)[:500],
                         str(folgen or AKTIONEN[aktion][1])[:1000], klasse, fp, "offen",
                         json.dumps(nutzlast or {}, ensure_ascii=False, default=str)[:20000], aufgabe_id))
                    ergebnis = ("angefragt", fid)

        art, fid = ergebnis
        if art == "blockiert":
            return self._blockiert(details, "Eigentümer hat genau diese Aktion abgelehnt (%s)" % fid, fid)
        if art == "auto":
            return Entscheidung("erlaubt", "automatisch erlaubt")
        if art == "verbraucht":
            self.protokoll.audit("supervisor", "Freigabe verbraucht", dict(details, freigabe=fid))
            return Entscheidung("erlaubt", "Freigabe des Eigentümers liegt vor", fid)
        if art == "wartet":
            return Entscheidung("wartet", "Freigabe angefragt, Entscheidung steht aus", fid)
        self.protokoll.audit("supervisor", "Freigabe angefragt", dict(details, freigabe=fid))
        return Entscheidung("freigabe_noetig", "Ausdrückliche Freigabe des Eigentümers nötig", fid)

    def _blockiert(self, details, grund, freigabe_id=None):
        self.protokoll.audit("supervisor", "Aktion blockiert: " + grund, details)
        return Entscheidung("verboten", grund, freigabe_id)

    # ---- Entscheidungen des Eigentümers --------------------------------
    def entscheiden(self, freigabe_id, ja, akteur, notiz=""):
        if akteur != "eigentuemer":
            self.protokoll.audit("supervisor", "Freigabe durch Nicht-Eigentümer blockiert",
                                 {"akteur": akteur, "freigabe": freigabe_id})
            raise PermissionError("Nur der Eigentümer kann Freigaben erteilen oder ablehnen.")
        f = self.db.eins("SELECT * FROM freigaben WHERE id=?", (freigabe_id,))
        if not f:
            raise KeyError("Freigabe nicht gefunden.")
        if f["status"] != "offen":
            raise ValueError("Freigabe ist bereits entschieden (%s)." % f["status"])
        neu = "erteilt" if ja else "abgelehnt"
        self.db.ausfuehren("UPDATE freigaben SET status=?, entschieden_zeit=?, entschieden_von=?, notiz=? "
                           "WHERE id=? AND status='offen'", (neu, jetzt(), akteur, str(notiz)[:500], freigabe_id))
        self.protokoll.audit("supervisor", "Freigabe " + neu, {"freigabe": freigabe_id, "aktion": f["aktion"],
                                                               "ziel": f["ziel"]})
        return neu

    def liste(self, status=None):
        if status:
            return self.db.alle("SELECT * FROM freigaben WHERE status=? ORDER BY zeit DESC", (status,))
        return self.db.alle("SELECT * FROM freigaben ORDER BY zeit DESC LIMIT 300")

    # ---- Ergebniskontrolle ---------------------------------------------
    def ergebnis_pruefen(self, agent, ergebnis):
        """Prüft ein Agentenergebnis, bevor es gespeichert wird. Gibt Liste von Mängeln zurück."""
        maengel = []
        try:
            text = json.dumps(ergebnis, ensure_ascii=False, default=str)
        except (TypeError, ValueError):
            return ["Ergebnis ist nicht speicherbar"]
        if len(text) > 500_000:
            maengel.append("Ergebnis zu groß")
        if not isinstance(ergebnis, dict):
            maengel.append("Ergebnis muss ein Objekt sein")
            return maengel
        for pfad in ergebnis.get("dateien", []) or []:
            if not pfad_erlaubt(pfad):
                maengel.append("Datei außerhalb des freigegebenen Bereichs: %s" % pfad)
        # Behauptungen über externe Wirkungen sind nur mit Beleg zulässig
        for schluessel in ("gesendet", "bezahlt", "veroeffentlicht", "einnahme_verbucht"):
            if ergebnis.get(schluessel) and not ergebnis.get("beleg"):
                maengel.append("Behauptung '%s' ohne Beleg" % schluessel)
        from .protokoll import sieht_nach_geheimnis_aus
        if sieht_nach_geheimnis_aus(text):
            maengel.append("Ergebnis enthält vermutlich ein Geheimnis (Passwort/Schlüssel/Seed)")
        return maengel


def erlaubte_wurzeln():
    return [os.path.realpath(konfig.datenordner())]


def pfad_erlaubt(pfad):
    """Dateizugriffe nur innerhalb des Datenordners (Symlinks werden aufgelöst)."""
    try:
        echt = os.path.realpath(pfad)
    except (TypeError, ValueError):
        return False
    return any(echt == w or echt.startswith(w + os.sep) for w in erlaubte_wurzeln())
