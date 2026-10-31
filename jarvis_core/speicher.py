# -*- coding: utf-8 -*-
"""Speicher - das dauerhafte Gedächtnis von JARVIS (SQLite, nur Bordmittel).

Alles liegt in einer Datei (``~/.jarvis/jarvis.db``) und übersteht Neustart des
Programms, des Macs und Modellwechsel. Gespeichert wird nur, was zählt:
bestätigte Fakten, Aufgaben, Aufträge samt Ergebnissen, Freigaben und das
Audit - nicht jedes Gespräch wahllos in die Wissensbasis.

Die Daten gehören zu einem **Bereich** (zum Beispiel ``geschaeft`` oder
``privat``). ``allgemein`` (Regeln, Vorlieben) und ``technik`` (Wissen über den
Mac) gelten für alle. Welcher Bereich ins Modell gelangt, entscheidet
``gedaechtnis.py`` - hier wird nur sauber gespeichert.

Zeiten stehen in UTC (siehe ``zeit.py``).
"""

import datetime
import json
import os
import sqlite3
import threading
import uuid

from . import textsuche, zeit

SCHEMA_VERSION = 1

SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (schluessel TEXT PRIMARY KEY, wert TEXT);

CREATE TABLE IF NOT EXISTS fakten (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  bereich TEXT NOT NULL DEFAULT 'allgemein',
  art TEXT NOT NULL DEFAULT 'fakt',
  text TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'bestaetigt',
  wichtig INTEGER NOT NULL DEFAULT 0,
  quelle TEXT NOT NULL DEFAULT 'nutzer',
  erstellt TEXT NOT NULL,
  geaendert TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_fakten ON fakten(status, bereich);

CREATE TABLE IF NOT EXISTS aufgaben (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  bereich TEXT NOT NULL,
  titel TEXT NOT NULL,
  beschreibung TEXT NOT NULL DEFAULT '',
  status TEXT NOT NULL DEFAULT 'offen',
  prioritaet TEXT NOT NULL DEFAULT 'normal',
  faellig TEXT,
  quelle TEXT NOT NULL DEFAULT 'nutzer',
  erstellt TEXT NOT NULL,
  geaendert TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS erinnerungen (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  bereich TEXT NOT NULL,
  text TEXT NOT NULL,
  faellig TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'offen',
  erstellt TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS gespraeche (
  kennung TEXT PRIMARY KEY,
  bereich TEXT NOT NULL,
  titel TEXT NOT NULL DEFAULT '',
  erstellt TEXT NOT NULL,
  geaendert TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS nachrichten (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  gespraech TEXT NOT NULL,
  rolle TEXT NOT NULL,
  text TEXT NOT NULL,
  meta TEXT,
  zeit TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_nachrichten ON nachrichten(gespraech, id);

CREATE TABLE IF NOT EXISTS anfragen (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  zeit TEXT NOT NULL,
  art TEXT NOT NULL,
  modell TEXT,
  dauer_ms INTEGER,
  ok INTEGER NOT NULL,
  fehler_art TEXT,
  tokens_ein INTEGER,
  tokens_aus INTEGER,
  auftrag_id INTEGER
);

CREATE TABLE IF NOT EXISTS auftraege (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  bereich TEXT NOT NULL,
  titel TEXT NOT NULL,
  ziel TEXT NOT NULL,
  status TEXT NOT NULL,
  rueckfragen TEXT,
  ergebnis TEXT,
  fehler TEXT,
  aufrufe INTEGER NOT NULL DEFAULT 0,
  erstellt TEXT NOT NULL,
  geplant_fuer TEXT,
  gestartet TEXT,
  beendet TEXT,
  gespraech TEXT
);

CREATE TABLE IF NOT EXISTS schritte (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  auftrag_id INTEGER NOT NULL,
  nr INTEGER NOT NULL,
  rolle TEXT NOT NULL,
  titel TEXT NOT NULL,
  anweisung TEXT NOT NULL,
  kriterium TEXT NOT NULL,
  datei TEXT,
  abhaengig_von TEXT NOT NULL DEFAULT '[]',
  status TEXT NOT NULL DEFAULT 'offen',
  ergebnis TEXT,
  pruefung TEXT,
  versuche INTEGER NOT NULL DEFAULT 0,
  extern INTEGER NOT NULL DEFAULT 0,
  gestartet TEXT,
  beendet TEXT,
  dauer_ms INTEGER
);
CREATE INDEX IF NOT EXISTS idx_schritte ON schritte(auftrag_id, nr);

CREATE TABLE IF NOT EXISTS freigaben (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  zeit TEXT NOT NULL,
  werkzeug TEXT NOT NULL,
  parameter TEXT NOT NULL,
  vorschau TEXT NOT NULL,
  risiko TEXT NOT NULL DEFAULT '',
  stufe INTEGER NOT NULL,
  bereich TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'offen',
  auftrag_id INTEGER,
  gespraech TEXT,
  liefert_daten INTEGER NOT NULL DEFAULT 0,
  beantwortet TEXT,
  ergebnis TEXT
);

CREATE TABLE IF NOT EXISTS audit (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  zeit TEXT NOT NULL,
  art TEXT NOT NULL,
  werkzeug TEXT,
  stufe INTEGER,
  bereich TEXT,
  details TEXT,
  ergebnis TEXT,
  auftrag_id INTEGER,
  freigabe_id INTEGER
);
"""

TABELLEN = ("fakten", "aufgaben", "erinnerungen", "gespraeche", "nachrichten", "anfragen",
            "auftraege", "schritte", "freigaben", "audit")

JSON_FELDER = {
    "nachrichten": ("meta",),
    "auftraege": ("rueckfragen",),
    "schritte": ("abhaengig_von", "pruefung"),
    "freigaben": ("parameter",),
    "audit": ("details",),
}

# Diese Felder dürfen die *_setzen-Methoden ändern. Alles andere wird abgelehnt.
ERLAUBT = {
    "fakten": {"text", "bereich", "art", "status", "wichtig", "quelle"},
    "aufgaben": {"titel", "beschreibung", "status", "prioritaet", "faellig", "bereich"},
    "erinnerungen": {"text", "faellig", "status", "bereich"},
    "gespraeche": {"titel", "bereich"},
    "auftraege": {"titel", "status", "rueckfragen", "ergebnis", "fehler", "aufrufe", "geplant_fuer",
                  "gestartet", "beendet", "bereich"},
    "schritte": {"status", "ergebnis", "pruefung", "versuche", "extern", "gestartet", "beendet", "dauer_ms"},
    "freigaben": {"status", "beantwortet", "ergebnis"},
}
MIT_GEAENDERT = ("fakten", "aufgaben", "gespraeche")

MAX_FAKT = 700


class Speicher:
    def __init__(self, pfad):
        self.pfad = pfad
        os.makedirs(os.path.dirname(os.path.abspath(pfad)), exist_ok=True)
        self._sperre = threading.RLock()
        self._db = sqlite3.connect(pfad, check_same_thread=False, timeout=30)
        self._db.row_factory = sqlite3.Row
        with self._sperre:
            self._db.execute("PRAGMA journal_mode=WAL")
            self._db.execute("PRAGMA synchronous=NORMAL")
            self._db.executescript(SCHEMA)
        if self.meta("schema_version") is None:
            self.meta_setzen("schema_version", str(SCHEMA_VERSION))

    # --------------------------------------------------------- Grundlagen ---

    def _lesen(self, sql, params=()):
        with self._sperre:
            return [dict(zeile) for zeile in self._db.execute(sql, params).fetchall()]

    def _eins(self, sql, params=()):
        zeilen = self._lesen(sql, params)
        return zeilen[0] if zeilen else None

    def _schreiben(self, sql, params=()):
        with self._sperre, self._db:
            return self._db.execute(sql, params)

    @staticmethod
    def _dekodieren(tabelle, zeile):
        if zeile is None:
            return None
        for feld in JSON_FELDER.get(tabelle, ()):
            wert = zeile.get(feld)
            if isinstance(wert, str):
                try:
                    zeile[feld] = json.loads(wert)
                except ValueError:
                    zeile[feld] = None
        return zeile

    def _liste(self, tabelle, sql, params=()):
        return [self._dekodieren(tabelle, z) for z in self._lesen(sql, params)]

    def _aendern(self, tabelle, zeile_id, felder):
        unbekannt = set(felder) - ERLAUBT[tabelle]
        if unbekannt:
            raise ValueError("Unbekannte Felder für %s: %s" % (tabelle, ", ".join(sorted(unbekannt))))
        if not felder:
            return False
        teile, werte = [], []
        for name, wert in felder.items():
            if name in JSON_FELDER.get(tabelle, ()) and wert is not None:
                wert = json.dumps(wert, ensure_ascii=False)
            teile.append("%s=?" % name)
            werte.append(wert)
        if tabelle in MIT_GEAENDERT:
            teile.append("geaendert=?")
            werte.append(zeit.jetzt())
        werte.append(zeile_id)
        # Tabelle und Spalten stammen ausschließlich aus den festen Listen oben (ERLAUBT) - nie aus Eingaben.
        sql = "UPDATE %s SET %s WHERE %s=?" % (  # noqa: S608
            tabelle, ", ".join(teile), "kennung" if tabelle == "gespraeche" else "id")
        cur = self._schreiben(sql, werte)
        return cur.rowcount > 0

    def meta(self, schluessel, standard=None):
        zeile = self._eins("SELECT wert FROM meta WHERE schluessel=?", (schluessel,))
        return zeile["wert"] if zeile else standard

    def meta_setzen(self, schluessel, wert):
        self._schreiben("INSERT INTO meta (schluessel, wert) VALUES (?, ?) "
                        "ON CONFLICT(schluessel) DO UPDATE SET wert=excluded.wert", (schluessel, wert))

    def meta_loeschen(self, schluessel):
        self._schreiben("DELETE FROM meta WHERE schluessel=?", (schluessel,))

    # -------------------------------------------------------------- Fakten ---

    def fakt_hinzufuegen(self, text, bereich="allgemein", art="fakt", status="bestaetigt", quelle="nutzer", wichtig=0):
        """Legt einen Eintrag an. Gibt (id, neu) zurück; ein Duplikat im selben Bereich wird nicht doppelt gespeichert."""
        text = " ".join((text or "").split())[:MAX_FAKT]
        if not text:
            raise ValueError("Der Eintrag ist leer.")
        with self._sperre:
            for vorhanden in self._lesen("SELECT id, text, status FROM fakten WHERE bereich=?", (bereich,)):
                if textsuche.ist_duplikat(vorhanden["text"], text):
                    if vorhanden["status"] == "verworfen" and status == "bestaetigt":
                        self._aendern("fakten", vorhanden["id"], {"status": "bestaetigt", "quelle": quelle})
                        return vorhanden["id"], True
                    return vorhanden["id"], False
            jetzt = zeit.jetzt()
            cur = self._schreiben(
                "INSERT INTO fakten (bereich, art, text, status, wichtig, quelle, erstellt, geaendert) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)", (bereich, art, text, status, int(bool(wichtig)), quelle, jetzt, jetzt))
            return cur.lastrowid, True

    def fakten(self, status="bestaetigt", bereiche=None, art=None):
        sql, params = "SELECT * FROM fakten WHERE 1=1", []
        if status:
            stati = [status] if isinstance(status, str) else list(status)
            sql += " AND status IN (%s)" % ",".join("?" * len(stati))
            params += stati
        if bereiche:
            sql += " AND bereich IN (%s)" % ",".join("?" * len(bereiche))
            params += list(bereiche)
        if art:
            sql += " AND art=?"
            params.append(art)
        return self._liste("fakten", sql + " ORDER BY wichtig DESC, id", params)

    def fakt(self, fakt_id):
        return self._eins("SELECT * FROM fakten WHERE id=?", (fakt_id,))

    def fakt_setzen(self, fakt_id, **felder):
        if "text" in felder:
            felder["text"] = " ".join(str(felder["text"]).split())[:MAX_FAKT]
            if not felder["text"]:
                raise ValueError("Der Eintrag ist leer.")
            felder.setdefault("quelle", "nutzer")  # vom Nutzer bearbeitet: ein neuer Import überschreibt das nicht
        return self._aendern("fakten", fakt_id, felder)

    def fakt_loeschen(self, fakt_id):
        return self._schreiben("DELETE FROM fakten WHERE id=?", (fakt_id,)).rowcount > 0

    def fakten_loeschen_quelle(self, quelle):
        return self._schreiben("DELETE FROM fakten WHERE quelle=?", (quelle,)).rowcount

    # ------------------------------------------------------------ Aufgaben ---

    def todo_anlegen(self, titel, bereich, beschreibung="", prioritaet="normal", faellig=None, quelle="jarvis"):
        titel = " ".join((titel or "").split())[:200]
        if not titel:
            raise ValueError("Der Titel fehlt.")
        jetzt = zeit.jetzt()
        cur = self._schreiben(
            "INSERT INTO aufgaben (bereich, titel, beschreibung, prioritaet, faellig, quelle, erstellt, geaendert) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (bereich, titel, (beschreibung or "")[:2000], prioritaet, faellig, quelle, jetzt, jetzt))
        return cur.lastrowid

    def todos(self, bereich=None, status=None, limit=200):
        sql, params = "SELECT * FROM aufgaben WHERE 1=1", []
        if bereich:
            sql += " AND bereich=?"
            params.append(bereich)
        if status:
            sql += " AND status=?"
            params.append(status)
        sql += (" ORDER BY CASE status WHEN 'offen' THEN 0 ELSE 1 END, "
                "CASE prioritaet WHEN 'hoch' THEN 0 WHEN 'normal' THEN 1 ELSE 2 END, "
                "COALESCE(faellig, '9999'), id LIMIT ?")
        return self._lesen(sql, params + [limit])

    def todo(self, todo_id):
        return self._eins("SELECT * FROM aufgaben WHERE id=?", (todo_id,))

    def todo_setzen(self, todo_id, **felder):
        return self._aendern("aufgaben", todo_id, felder)

    def todo_loeschen(self, todo_id):
        return self._schreiben("DELETE FROM aufgaben WHERE id=?", (todo_id,)).rowcount > 0

    # --------------------------------------------------------- Erinnerungen ---

    def erinnerung_anlegen(self, text, faellig_utc, bereich):
        text = " ".join((text or "").split())[:300]
        if not text:
            raise ValueError("Der Text fehlt.")
        cur = self._schreiben("INSERT INTO erinnerungen (bereich, text, faellig, erstellt) VALUES (?, ?, ?, ?)",
                              (bereich, text, faellig_utc, zeit.jetzt()))
        return cur.lastrowid

    def erinnerungen(self, bereich=None, stati=("offen", "faellig")):
        sql, params = "SELECT * FROM erinnerungen WHERE 1=1", []
        if bereich:
            sql += " AND bereich=?"
            params.append(bereich)
        if stati:
            sql += " AND status IN (%s)" % ",".join("?" * len(stati))
            params += list(stati)
        return self._lesen(sql + " ORDER BY faellig, id", params)

    def erinnerungen_faellig_markieren(self, jetzt):
        """Setzt alle erreichten Erinnerungen auf "faellig" und gibt sie zurück (jede nur einmal)."""
        with self._sperre:
            zeilen = self._lesen("SELECT * FROM erinnerungen WHERE status='offen' AND faellig<=? ORDER BY faellig", (jetzt,))
            for z in zeilen:
                self._schreiben("UPDATE erinnerungen SET status='faellig' WHERE id=? AND status='offen'", (z["id"],))
            return zeilen

    def erinnerung_setzen(self, erinnerung_id, **felder):
        return self._aendern("erinnerungen", erinnerung_id, felder)

    def erinnerung_loeschen(self, erinnerung_id):
        return self._schreiben("DELETE FROM erinnerungen WHERE id=?", (erinnerung_id,)).rowcount > 0

    # ------------------------------------------------- Gespräche, Nachrichten ---

    def gespraech_anlegen(self, bereich, titel=""):
        kennung = uuid.uuid4().hex[:16]
        jetzt = zeit.jetzt()
        self._schreiben("INSERT INTO gespraeche (kennung, bereich, titel, erstellt, geaendert) VALUES (?, ?, ?, ?, ?)",
                        (kennung, bereich, titel[:80], jetzt, jetzt))
        return kennung

    def gespraech(self, kennung):
        return self._eins("SELECT * FROM gespraeche WHERE kennung=?", (kennung,))

    def letztes_gespraech(self, bereich=None):
        if bereich:
            return self._eins("SELECT * FROM gespraeche WHERE bereich=? ORDER BY geaendert DESC, rowid DESC LIMIT 1", (bereich,))
        return self._eins("SELECT * FROM gespraeche ORDER BY geaendert DESC, rowid DESC LIMIT 1")

    def gespraech_setzen(self, kennung, **felder):
        return self._aendern("gespraeche", kennung, felder)

    def nachricht_hinzufuegen(self, kennung, rolle, text, meta=None):
        jetzt = zeit.jetzt()
        with self._sperre:
            cur = self._schreiben("INSERT INTO nachrichten (gespraech, rolle, text, meta, zeit) VALUES (?, ?, ?, ?, ?)",
                                  (kennung, rolle, text, json.dumps(meta, ensure_ascii=False) if meta else None, jetzt))
            self._schreiben("UPDATE gespraeche SET geaendert=? WHERE kennung=?", (jetzt, kennung))
            return cur.lastrowid

    def nachrichten(self, kennung, limit=60):
        return self._liste("nachrichten", "SELECT * FROM (SELECT * FROM nachrichten WHERE gespraech=? "
                           "ORDER BY id DESC LIMIT ?) ORDER BY id", (kennung, limit))

    # ------------------------------------------------------------- Anfragen ---

    def anfrage_erfassen(self, art, modell, dauer_ms, ok, fehler_art=None, tokens_ein=None, tokens_aus=None,
                         auftrag_id=None):
        self._schreiben("INSERT INTO anfragen (zeit, art, modell, dauer_ms, ok, fehler_art, tokens_ein, tokens_aus, "
                        "auftrag_id) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                        (zeit.jetzt(), art, modell, dauer_ms, 1 if ok else 0, fehler_art, tokens_ein, tokens_aus, auftrag_id))

    def anfragen_stunden(self, stunden=24):
        """Anfragen je Stunde der letzten ``stunden`` Stunden, älteste zuerst (für das Diagramm)."""
        ende = datetime.datetime.now(datetime.timezone.utc).replace(minute=0, second=0, microsecond=0)
        start = ende - datetime.timedelta(hours=stunden - 1)
        zeilen = self._lesen(
            "SELECT substr(zeit, 1, 13) AS h, COUNT(*) AS n, SUM(CASE WHEN ok=0 THEN 1 ELSE 0 END) AS f "
            "FROM anfragen WHERE zeit>=? GROUP BY h", (start.strftime(zeit.FORMAT),))
        je_stunde = {z["h"]: z for z in zeilen}
        ergebnis = []
        for i in range(stunden):
            t = start + datetime.timedelta(hours=i)
            z = je_stunde.get(t.strftime("%Y-%m-%dT%H"))
            ergebnis.append({"von": t.strftime(zeit.FORMAT), "anzahl": z["n"] if z else 0,
                             "fehler": (z["f"] or 0) if z else 0})
        return ergebnis

    def antwortzeiten(self, anzahl=30):
        zeilen = self._lesen("SELECT dauer_ms FROM anfragen WHERE ok=1 AND dauer_ms IS NOT NULL ORDER BY id DESC LIMIT ?",
                             (anzahl,))
        return [z["dauer_ms"] for z in reversed(zeilen)]

    def verbrauch_heute(self):
        z = self._eins("SELECT COUNT(*) AS n, COALESCE(SUM(tokens_ein), 0) AS ein, COALESCE(SUM(tokens_aus), 0) AS aus, "
                       "SUM(CASE WHEN ok=0 THEN 1 ELSE 0 END) AS fehler FROM anfragen WHERE zeit>=?",
                       (zeit.lokaler_tagesbeginn(),))
        return {"anfragen": z["n"], "tokens_ein": z["ein"], "tokens_aus": z["aus"], "fehler": z["fehler"] or 0}

    # ------------------------------------------------------ Aufträge, Schritte ---

    def auftrag_anlegen(self, titel, ziel, bereich, status="entwurf", gespraech=None, geplant_fuer=None, rueckfragen=None):
        cur = self._schreiben(
            "INSERT INTO auftraege (bereich, titel, ziel, status, rueckfragen, erstellt, geplant_fuer, gespraech) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (bereich, titel[:200], ziel[:4000], status, json.dumps(rueckfragen, ensure_ascii=False) if rueckfragen else None,
             zeit.jetzt(), geplant_fuer, gespraech))
        return cur.lastrowid

    def auftrag(self, auftrag_id):
        return self._dekodieren("auftraege", self._eins("SELECT * FROM auftraege WHERE id=?", (auftrag_id,)))

    def auftraege(self, bereich=None, stati=None, limit=30):
        sql, params = "SELECT * FROM auftraege WHERE 1=1", []
        if bereich:
            sql += " AND bereich=?"
            params.append(bereich)
        if stati:
            sql += " AND status IN (%s)" % ",".join("?" * len(stati))
            params += list(stati)
        return self._liste("auftraege", sql + " ORDER BY id DESC LIMIT ?", params + [limit])

    def auftrag_setzen(self, auftrag_id, **felder):
        return self._aendern("auftraege", auftrag_id, felder)

    def auftrag_aufruf_zaehlen(self, auftrag_id):
        with self._sperre:
            self._schreiben("UPDATE auftraege SET aufrufe=aufrufe+1 WHERE id=?", (auftrag_id,))
            zeile = self._eins("SELECT aufrufe FROM auftraege WHERE id=?", (auftrag_id,))
            return zeile["aufrufe"] if zeile else 0

    def auftrag_uebernehmen(self):
        """Nimmt den ältesten wartenden Auftrag und setzt ihn auf "laeuft". Gibt die Nummer zurück oder None."""
        with self._sperre, self._db:
            zeile = self._db.execute("SELECT id FROM auftraege WHERE status='wartend' ORDER BY id LIMIT 1").fetchone()
            if not zeile:
                return None
            cur = self._db.execute("UPDATE auftraege SET status='laeuft', gestartet=COALESCE(gestartet, ?) "
                                   "WHERE id=? AND status='wartend'", (zeit.jetzt(), zeile[0]))
            return zeile[0] if cur.rowcount else None

    def auftraege_unterbrechen(self):
        """Nach einem Neustart: was lief, ist "unterbrochen". Gibt die Nummern zurück."""
        with self._sperre:
            ids = [z["id"] for z in self._lesen("SELECT id FROM auftraege WHERE status IN ('laeuft', 'wartet_auf_freigabe')")]
            for auftrag_id in ids:
                self._schreiben("UPDATE auftraege SET status='unterbrochen' WHERE id=?", (auftrag_id,))
                self._schreiben("UPDATE schritte SET status='offen' WHERE auftrag_id=? AND status='laeuft'", (auftrag_id,))
            return ids

    def geplante_auftraege_faellig(self, jetzt):
        with self._sperre:
            ids = [z["id"] for z in self._lesen(
                "SELECT id FROM auftraege WHERE status='geplant' AND geplant_fuer<=? ORDER BY id", (jetzt,))]
            for auftrag_id in ids:
                self._schreiben("UPDATE auftraege SET status='wartend' WHERE id=? AND status='geplant'", (auftrag_id,))
            return ids

    def auftrag_loeschen(self, auftrag_id):
        with self._sperre:
            self._schreiben("DELETE FROM schritte WHERE auftrag_id=?", (auftrag_id,))
            return self._schreiben("DELETE FROM auftraege WHERE id=?", (auftrag_id,)).rowcount > 0

    def schritt_anlegen(self, auftrag_id, nr, rolle, titel, anweisung, kriterium, datei=None, abhaengig_von=None):
        cur = self._schreiben(
            "INSERT INTO schritte (auftrag_id, nr, rolle, titel, anweisung, kriterium, datei, abhaengig_von) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (auftrag_id, nr, rolle, titel[:200], anweisung[:4000], kriterium[:1000], datei,
             json.dumps(abhaengig_von or [])))
        return cur.lastrowid

    def schritte(self, auftrag_id):
        return self._liste("schritte", "SELECT * FROM schritte WHERE auftrag_id=? ORDER BY nr", (auftrag_id,))

    def schritt(self, schritt_id):
        return self._dekodieren("schritte", self._eins("SELECT * FROM schritte WHERE id=?", (schritt_id,)))

    def schritt_setzen(self, schritt_id, **felder):
        return self._aendern("schritte", schritt_id, felder)

    def schritte_aktiv(self):
        return self._liste("schritte", "SELECT s.*, a.titel AS auftrag_titel FROM schritte s "
                           "JOIN auftraege a ON a.id = s.auftrag_id WHERE s.status='laeuft' ORDER BY s.id")

    def schritte_zuletzt(self, anzahl=12):
        return self._liste("schritte", "SELECT s.*, a.titel AS auftrag_titel FROM schritte s "
                           "JOIN auftraege a ON a.id = s.auftrag_id "
                           "WHERE s.status IN ('fertig', 'fehlgeschlagen', 'blockiert') ORDER BY s.id DESC LIMIT ?", (anzahl,))

    # ------------------------------------------------------------ Freigaben ---

    def freigabe_anlegen(self, werkzeug, parameter, vorschau, risiko, stufe, bereich, auftrag_id=None, gespraech=None,
                         liefert_daten=False):
        cur = self._schreiben(
            "INSERT INTO freigaben (zeit, werkzeug, parameter, vorschau, risiko, stufe, bereich, auftrag_id, gespraech, "
            "liefert_daten) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (zeit.jetzt(), werkzeug, json.dumps(parameter, ensure_ascii=False), vorschau[:60000], risiko, stufe, bereich,
             auftrag_id, gespraech, 1 if liefert_daten else 0))
        return cur.lastrowid

    def freigabe(self, freigabe_id):
        return self._dekodieren("freigaben", self._eins("SELECT * FROM freigaben WHERE id=?", (freigabe_id,)))

    def freigaben(self, status=None, limit=50):
        if status:
            return self._liste("freigaben", "SELECT * FROM freigaben WHERE status=? ORDER BY id DESC LIMIT ?", (status, limit))
        return self._liste("freigaben", "SELECT * FROM freigaben ORDER BY id DESC LIMIT ?", (limit,))

    def freigabe_entscheiden(self, freigabe_id, neuer_status, ergebnis=None):
        """Setzt eine OFFENE Freigabe auf ihren Endstand. Gibt False zurück, wenn sie schon entschieden war."""
        cur = self._schreiben("UPDATE freigaben SET status=?, beantwortet=?, ergebnis=? WHERE id=? AND status='offen'",
                              (neuer_status, zeit.jetzt(), ergebnis, freigabe_id))
        return cur.rowcount == 1

    def freigabe_ergebnis_setzen(self, freigabe_id, ergebnis, status=None):
        felder = {"ergebnis": ergebnis}
        if status:
            felder["status"] = status
        return self._aendern("freigaben", freigabe_id, felder)

    def freigaben_ablaufen(self, grenze):
        """Offene Freigaben, die älter als ``grenze`` sind, werden "abgelaufen". Gibt ihre Nummern zurück."""
        with self._sperre:
            ids = [z["id"] for z in self._lesen("SELECT id FROM freigaben WHERE status='offen' AND zeit<?", (grenze,))]
            for freigabe_id in ids:
                self._schreiben("UPDATE freigaben SET status='abgelaufen', beantwortet=? WHERE id=? AND status='offen'",
                                (zeit.jetzt(), freigabe_id))
            return ids

    # ---------------------------------------------------------------- Audit ---

    def audit_schreiben(self, art, werkzeug=None, stufe=None, bereich=None, details=None, ergebnis=None,
                        auftrag_id=None, freigabe_id=None):
        self._schreiben(
            "INSERT INTO audit (zeit, art, werkzeug, stufe, bereich, details, ergebnis, auftrag_id, freigabe_id) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (zeit.jetzt(), art, werkzeug, stufe, bereich,
             json.dumps(details, ensure_ascii=False)[:8000] if details is not None else None,
             (ergebnis or "")[:2000] or None, auftrag_id, freigabe_id))

    def audit_liste(self, limit=100, art=None):
        if art:
            return self._liste("audit", "SELECT * FROM audit WHERE art=? ORDER BY id DESC LIMIT ?", (art, limit))
        return self._liste("audit", "SELECT * FROM audit ORDER BY id DESC LIMIT ?", (limit,))

    # ------------------------------------------- Überblick, Export, Sicherung ---

    def zaehler(self):
        def n(sql, params=()):
            return self._eins(sql, params)["n"]
        auftraege = {z["status"]: z["n"] for z in self._lesen("SELECT status, COUNT(*) AS n FROM auftraege GROUP BY status")}
        return {
            "fakten": n("SELECT COUNT(*) AS n FROM fakten WHERE status='bestaetigt'"),
            "vorschlaege": n("SELECT COUNT(*) AS n FROM fakten WHERE status='vorschlag'"),
            "todos_offen": n("SELECT COUNT(*) AS n FROM aufgaben WHERE status='offen'"),
            "todos_erledigt": n("SELECT COUNT(*) AS n FROM aufgaben WHERE status='erledigt'"),
            "auftraege": auftraege,
            "freigaben_offen": n("SELECT COUNT(*) AS n FROM freigaben WHERE status='offen'"),
            "erinnerungen_faellig": n("SELECT COUNT(*) AS n FROM erinnerungen WHERE status='faellig'"),
        }

    def exportieren(self):
        daten = {"exportiert": zeit.jetzt(), "schema": SCHEMA_VERSION}
        for tabelle in TABELLEN:
            daten[tabelle] = self._liste(tabelle, "SELECT * FROM %s ORDER BY 1" % tabelle)  # noqa: S608 - feste Namen
        return daten

    def alles_loeschen(self):
        """Löscht ALLE gespeicherten Inhalte (nicht die Datei, nicht die Werkstatt)."""
        with self._sperre, self._db:
            for tabelle in TABELLEN:
                self._db.execute("DELETE FROM %s" % tabelle)  # noqa: S608 - feste Namen
            self._db.execute("DELETE FROM meta WHERE schluessel != 'schema_version'")
            self._db.execute("DELETE FROM sqlite_sequence")

    def sichern(self, ziel):
        """Konsistente Kopie der Datenbank (auch während des Betriebs)."""
        os.makedirs(os.path.dirname(os.path.abspath(ziel)), exist_ok=True)
        with self._sperre:
            kopie = sqlite3.connect(ziel)
            try:
                self._db.backup(kopie)
            finally:
                kopie.close()

    def integritaet(self):
        zeile = self._eins("PRAGMA integrity_check")
        return next(iter(zeile.values())) if zeile else "unbekannt"

    def schliessen(self):
        with self._sperre:
            try:
                self._db.close()
            except sqlite3.Error:
                pass
