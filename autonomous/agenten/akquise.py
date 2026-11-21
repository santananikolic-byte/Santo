# -*- coding: utf-8 -*-
"""Akquise-Agent: findet öffentliche Ausschreibungen, bewertet sie und bereitet Bewerbungs-Mappen vor.

- Liest NUR die freigegebenen öffentlichen Quellen (TED, service.bund.de, Vergabemarktplatz NRW),
  und nur, wenn der Eigentümer die Internet-Recherche eingeschaltet hat (Recht ``web_lesen``).
- Fällt eine Quelle aus, laufen die anderen weiter – das Ergebnis sagt ehrlich, was fehlte.
- Den Status, den der Eigentümer gesetzt hat, überschreibt er nie.
- Er registriert sich nirgends, lädt keine Vergabeunterlagen herunter und gibt NIE ein Angebot ab.
"""

import json
import os

from . import Agent, Blockiert
from .. import auftraege, konfig, netz
from ..auftraege import PASSEND_AB, QUELLEN_NAMEN, STUFEN, datum_deutsch, mappe, quellen, tage_bis
from ..auftraege.bewertung import bewerten
from ..db import jetzt, neue_id
from ..produkte import datei_schreiben, sicherer_pfad

QUELLEN = ("ted", "service_bund", "evergabe_nrw")


class _Gesperrt(Exception):
    pass


class AkquiseAgent(Agent):
    rolle = "akquise"
    name = "Akquise-Agent"
    beschreibung = ("Sucht öffentliche Ausschreibungen (TED, service.bund.de, Vergabemarktplatz NRW), bewertet sie "
                    "nachvollziehbar und bereitet Bewerbungs-Mappen vor. Gibt nie selbst ein Angebot ab.")
    rechte = frozenset({"web_lesen", "lokale_recherche", "interne_auswertung", "gedaechtnis_vorschlag",
                        "datei_erstellen", "interne_planung"})
    aufgabentypen = {
        "ausschreibungen_suchen": "Öffentliche Ausschreibungen aus allen freigegebenen Quellen holen und bewerten",
        "ausschreibung_vorbereiten": "Bewerbungs-Mappe zu einer Ausschreibung erstellen (Eingabe: ausschreibung_id)",
        "auswertung": "Ausschreibungen nach Status und Quelle zählen, nächste Fristen nennen",
    }

    # ------------------------------------------------------------------ Suchen
    def aufgabe_ausschreibungen_suchen(self, aufgabe, k):
        if not k.einstellungen.hole("internet_recherche_erlaubt"):
            # Klar blockiert – der Orchestrator bricht die Aufgabe ab, es gibt keine Wiederholung
            raise Blockiert("Internet-Recherche ist ausgeschaltet (Einstellungen → einmal einschalten)")
        einstellungen = k.einstellungen.alle()
        self.darf(k, "interne_planung", "ausschreibungen", aufgabe)
        bericht, neu_passend, fehlende = {}, [], []
        for quelle in QUELLEN:
            name = QUELLEN_NAMEN[quelle]

            def pruefen(url, _quelle=quelle):
                e = k.supervisor.pruefe(self.rolle, "web_lesen", _quelle, url=url, aufgabe_id=aufgabe["id"])
                if not e.erlaubt:
                    raise _Gesperrt(e.grund)
            try:
                eintraege = quellen.holen(quelle, einstellungen, netz.abrufen, pruefen)
            except _Gesperrt as g:
                self._lauf(k, quelle, "gesperrt", 0, 0, 0, str(g), aufgabe)
                bericht[name] = {"ergebnis": "gesperrt", "meldung": str(g)}
                fehlende.append(name)
                continue
            except (netz.NetzFehler, quellen.QuellenFehler) as f:
                self._lauf(k, quelle, "fehler", 0, 0, 0, str(f), aufgabe)
                bericht[name] = {"ergebnis": "fehler", "meldung": str(f)}
                fehlende.append(name)
                continue
            gefunden, neu, passend = len(eintraege), 0, 0
            for e in eintraege:
                punkte, gruende, ist_passend = bewerten(e, einstellungen)
                passend += ist_passend
                aid, ist_neu = self._speichern(k, e, punkte, gruende)
                neu += ist_neu
                if ist_neu and ist_passend and (tage_bis(e["frist"]) is None or tage_bis(e["frist"]) >= 0):
                    neu_passend.append({"id": aid, "titel": e["titel"], "quelle": name, "ort": e.get("ort") or
                                        e.get("region"), "frist": e.get("frist"), "punkte": punkte})
            self._lauf(k, quelle, "ok", gefunden, neu, passend, None, aufgabe)
            bericht[name] = {"ergebnis": "ok", "gefunden": gefunden, "neu": neu, "passend": passend}
        neu_passend.sort(key=lambda x: (-x["punkte"], x["frist"] or "9999"))
        if neu_passend:
            self.darf(k, "gedaechtnis_vorschlag", "ausschreibungen", aufgabe)
            k.gedaechtnis.merken("vorschlag", "Neue passende Ausschreibungen",
                                 "\n".join("%d Punkte · Frist %s · %s (%s)" % (
                                     x["punkte"], datum_deutsch(x["frist"]), x["titel"][:120], x["quelle"])
                                     for x in neu_passend[:10]),
                                 "akquise:ausschreibungen_suchen", self.rolle, aufgabe["id"])
        return {
            "quellen": bericht,
            "fehlende_quellen": fehlende,
            "neu_passend": neu_passend[:10],
            "neu_passend_gesamt": len(neu_passend),
            "hinweis": ("Gefunden und bewertet – nichts abgegeben, nichts angemeldet. Passend heißt: mindestens %d "
                        "Punkte nach nachvollziehbaren Regeln, keine Erfolgsgarantie." % PASSEND_AB)
                       + (" Nicht erreichbar: %s." % ", ".join(fehlende) if fehlende else ""),
        }

    def _speichern(self, k, e, punkte, gruende):
        """Neu anlegen oder aktualisieren. Status, Notiz und Unterlagen des Eigentümers bleiben unberührt."""
        z = jetzt()
        felder = (e["titel"], e.get("vergabestelle"), e.get("ort"), e.get("plz"), e.get("region"), e.get("frist"),
                  e.get("veroeffentlicht"), e.get("verfahren"), e["link"], json.dumps(e.get("cpv") or []),
                  int(punkte), json.dumps(gruende, ensure_ascii=False))
        with k.db.transaktion() as con:
            vorhanden = con.execute("SELECT id FROM ausschreibungen WHERE quelle=? AND extern_id=?",
                                    (e["quelle"], e["extern_id"])).fetchone()
            if vorhanden:
                con.execute("UPDATE ausschreibungen SET titel=?, vergabestelle=?, ort=?, plz=?, region=?, frist=?, "
                            "veroeffentlicht=?, verfahren=?, link=?, cpv=?, punkte=?, begruendung=?, aktualisiert=? "
                            "WHERE id=?", felder + (z, vorhanden["id"]))
                return vorhanden["id"], False
            aid = neue_id("as_")
            con.execute("INSERT INTO ausschreibungen (id, quelle, extern_id, titel, vergabestelle, ort, plz, region, "
                        "frist, veroeffentlicht, verfahren, link, cpv, punkte, begruendung, status, gefunden, "
                        "aktualisiert) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                        (aid, e["quelle"], e["extern_id"]) + felder + ("neu", z, z))
            return aid, True

    @staticmethod
    def _lauf(k, quelle, ergebnis, gefunden, neu, passend, meldung, aufgabe):
        k.db.ausfuehren("INSERT INTO suchlaeufe (zeit, quelle, ergebnis, gefunden, neu, passend, meldung, aufgabe_id) "
                        "VALUES (?,?,?,?,?,?,?,?)", (jetzt(), quelle, ergebnis, gefunden, neu, passend,
                                                     (meldung or "")[:500] or None, aufgabe["id"]))
        if ergebnis != "ok":
            k.protokoll.warnung("akquise", "Quelle %s: %s" % (quelle, ergebnis), meldung)

    # ------------------------------------------------------------------ Vorbereiten
    def aufgabe_ausschreibung_vorbereiten(self, aufgabe, k):
        aid = aufgabe["eingabe"].get("ausschreibung_id")
        a = k.db.eins("SELECT * FROM ausschreibungen WHERE id=?", (aid,)) if isinstance(aid, str) else None
        if not a:
            raise KeyError("Ausschreibung nicht gefunden.")
        if a["status"] in ("abgelehnt", "gewonnen", "verloren"):
            raise ValueError("Ausschreibung hat den Status „%s“ – keine Mappe nötig." % a["status"])
        pfad = sicherer_pfad("ausschreibungen", a["id"], "mappe.html")
        self.darf(k, "datei_erstellen", "mappe:%s" % a["id"], aufgabe, datei_pfad=pfad)
        try:
            datei_schreiben(pfad, mappe.erzeugen(a, k.einstellungen.alle(), jetzt()))
        except FileExistsError:
            raise ValueError("Für diese Ausschreibung gibt es schon eine Mappe.")
        relativ = "ausschreibungen/%s/mappe.html" % a["id"]
        neuer_status = "vorbereitet" if a["status"] in ("neu", "interessant") else a["status"]
        k.db.ausfuehren("UPDATE ausschreibungen SET unterlagen=?, status=?, aktualisiert=? WHERE id=?",
                        (relativ, neuer_status, jetzt(), a["id"]))
        tage = tage_bis(a["frist"])
        return {"ausschreibung_id": a["id"], "titel": a["titel"], "status": neuer_status,
                "frist": a["frist"], "tage_bis_frist": tage, "dateien": [pfad],
                "unterlagen_url": "/produkte/" + relativ,
                "hinweis": "Mappe erstellt. Registrierung, Vergabeunterlagen und Abgabe macht nur der Inhaber."
                           + (" Achtung: Frist sehr knapp." if tage is not None and 0 <= tage < 7 else "")}

    # ------------------------------------------------------------------ Auswertung
    def aufgabe_auswertung(self, aufgabe, k):
        self.darf(k, "interne_auswertung", "ausschreibungen", aufgabe)
        heute = auftraege.heute().isoformat()
        nach_status = {s: 0 for s in STUFEN}
        for z in k.db.alle("SELECT status, COUNT(*) n FROM ausschreibungen GROUP BY status"):
            nach_status[z["status"]] = z["n"]
        nach_quelle = {QUELLEN_NAMEN.get(z["quelle"], z["quelle"]): z["n"] for z in k.db.alle(
            "SELECT quelle, COUNT(*) n FROM ausschreibungen GROUP BY quelle")}
        fristen = k.db.alle("SELECT id, titel, frist, status, punkte FROM ausschreibungen WHERE frist >= ? AND "
                            "status IN ('neu','interessant','vorbereitet') AND punkte >= ? ORDER BY frist LIMIT 10",
                            (heute, PASSEND_AB))
        return {"nach_status": nach_status, "nach_quelle": nach_quelle,
                "naechste_fristen": [dict(f, tage_bis_frist=tage_bis(f["frist"])) for f in fristen],
                "hinweis": "Alle Zahlen aus der Datenbank gezählt."}


def mappe_vorhanden(relativ):
    if not relativ:
        return False
    return os.path.isfile(os.path.join(konfig.unterordner("produkte"), relativ))
