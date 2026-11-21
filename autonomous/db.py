# -*- coding: utf-8 -*-
"""SQLite-Datenhaltung mit nummerierten Migrationen.

- Jede Migration läuft genau einmal (Tabelle schema_version).
- Buchungen (Wallet und reale Finanzen) sind per Trigger unveränderbar:
  Korrekturen nur durch Gegenbuchung.
- WAL-Modus: nach Absturz oder Neustart bleibt der letzte bestätigte Stand erhalten.
"""

import datetime
import json
import sqlite3
import threading
import uuid

from . import konfig

MIGRATIONEN = [
    # 1 – Grundgerüst
    """
    CREATE TABLE system (schluessel TEXT PRIMARY KEY, wert TEXT NOT NULL);

    CREATE TABLE einstellungen (schluessel TEXT PRIMARY KEY, wert TEXT NOT NULL,
        geaendert TEXT NOT NULL);

    CREATE TABLE protokoll (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        zeit TEXT NOT NULL,
        ebene TEXT NOT NULL CHECK (ebene IN ('info','warnung','fehler','kritisch','audit')),
        quelle TEXT NOT NULL,
        ereignis TEXT NOT NULL,
        details TEXT
    );
    CREATE INDEX protokoll_zeit ON protokoll(zeit);

    CREATE TABLE agenten_rollen (
        rolle TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        beschreibung TEXT NOT NULL,
        handler TEXT NOT NULL,
        aktiv INTEGER NOT NULL DEFAULT 1,
        erlaubte_aktionen TEXT NOT NULL,
        aufgabentypen TEXT NOT NULL,
        erstellt TEXT NOT NULL
    );

    CREATE TABLE aufgaben (
        id TEXT PRIMARY KEY,
        titel TEXT NOT NULL,
        typ TEXT NOT NULL,
        ersteller TEXT NOT NULL,
        verantwortlich TEXT NOT NULL,
        status TEXT NOT NULL CHECK (status IN ('geplant','bereit','laufend','wartet_auf_freigabe',
                                               'abgeschlossen','fehlgeschlagen','abgebrochen')),
        prioritaet INTEGER NOT NULL DEFAULT 3 CHECK (prioritaet BETWEEN 1 AND 5),
        erstellt TEXT NOT NULL,
        aktualisiert TEXT NOT NULL,
        gestartet TEXT,
        beendet TEXT,
        eingabe TEXT NOT NULL DEFAULT '{}',
        ergebnis TEXT,
        fehler TEXT,
        versuche INTEGER NOT NULL DEFAULT 0,
        max_versuche INTEGER NOT NULL DEFAULT 3,
        naechster_versuch TEXT,
        eltern_id TEXT,
        freigabe_id TEXT
    );
    CREATE INDEX aufgaben_status ON aufgaben(status, prioritaet, erstellt);

    CREATE TABLE aufgaben_verlauf (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        aufgabe_id TEXT NOT NULL,
        zeit TEXT NOT NULL,
        von_status TEXT,
        nach_status TEXT NOT NULL,
        akteur TEXT NOT NULL,
        notiz TEXT
    );

    CREATE TABLE freigaben (
        id TEXT PRIMARY KEY,
        zeit TEXT NOT NULL,
        agent TEXT NOT NULL,
        aktion TEXT NOT NULL,
        ziel TEXT NOT NULL,
        kosten_cent INTEGER NOT NULL DEFAULT 0,
        datenumfang TEXT NOT NULL,
        folgen TEXT NOT NULL,
        risiko TEXT NOT NULL,
        fingerabdruck TEXT NOT NULL,
        status TEXT NOT NULL CHECK (status IN ('offen','erteilt','abgelehnt','verbraucht')),
        entschieden_zeit TEXT,
        entschieden_von TEXT,
        notiz TEXT,
        nutzlast TEXT NOT NULL DEFAULT '{}',
        aufgabe_id TEXT
    );
    CREATE INDEX freigaben_fp ON freigaben(fingerabdruck, status);

    CREATE TABLE wallet_buchungen (
        id TEXT PRIMARY KEY,
        nr INTEGER NOT NULL UNIQUE,
        zeit TEXT NOT NULL,
        betrag_cent INTEGER NOT NULL,
        waehrung TEXT NOT NULL DEFAULT 'EUR' CHECK (waehrung = 'EUR'),
        kategorie TEXT NOT NULL,
        art TEXT NOT NULL CHECK (art IN ('startwert','einnahme','ausgabe','reservierung',
                                         'reservierung_aufloesen','gebuehr','gegenbuchung')),
        status TEXT NOT NULL DEFAULT 'gebucht',
        begruendung TEXT NOT NULL,
        gegenbuchung_zu TEXT,
        simulation INTEGER NOT NULL DEFAULT 1 CHECK (simulation = 1),
        akteur TEXT NOT NULL
    );
    CREATE TRIGGER wallet_kein_update BEFORE UPDATE ON wallet_buchungen
        BEGIN SELECT RAISE(ABORT, 'Wallet-Buchungen sind unveränderbar - bitte Gegenbuchung'); END;
    CREATE TRIGGER wallet_kein_delete BEFORE DELETE ON wallet_buchungen
        BEGIN SELECT RAISE(ABORT, 'Wallet-Buchungen sind unveränderbar - bitte Gegenbuchung'); END;

    CREATE TABLE real_buchungen (
        id TEXT PRIMARY KEY,
        nr INTEGER NOT NULL UNIQUE,
        zeit TEXT NOT NULL,
        datum TEXT NOT NULL,
        art TEXT NOT NULL CHECK (art IN ('einnahme','ausgabe','gegenbuchung')),
        betrag_cent INTEGER NOT NULL,
        waehrung TEXT NOT NULL DEFAULT 'EUR' CHECK (waehrung = 'EUR'),
        kategorie TEXT NOT NULL,
        gegenpartei TEXT NOT NULL,
        beleg TEXT,
        zahlungsnachweis TEXT,
        verifiziert_von TEXT,
        forderung_id TEXT,
        gegenbuchung_zu TEXT,
        begruendung TEXT NOT NULL,
        simulation INTEGER NOT NULL DEFAULT 0 CHECK (simulation = 0),
        akteur TEXT NOT NULL,
        CHECK (art != 'einnahme' OR (zahlungsnachweis IS NOT NULL AND length(trim(zahlungsnachweis)) > 0
                                      AND verifiziert_von IS NOT NULL))
    );
    CREATE TRIGGER real_kein_update BEFORE UPDATE ON real_buchungen
        BEGIN SELECT RAISE(ABORT, 'Reale Buchungen sind unveränderbar - bitte Gegenbuchung'); END;
    CREATE TRIGGER real_kein_delete BEFORE DELETE ON real_buchungen
        BEGIN SELECT RAISE(ABORT, 'Reale Buchungen sind unveränderbar - bitte Gegenbuchung'); END;

    CREATE TABLE forderungen (
        id TEXT PRIMARY KEY,
        erstellt TEXT NOT NULL,
        kunde TEXT NOT NULL,
        betrag_cent INTEGER NOT NULL CHECK (betrag_cent > 0),
        faellig TEXT,
        rechnung_ref TEXT,
        status TEXT NOT NULL CHECK (status IN ('offen','bezahlt','storniert')),
        buchung_id TEXT,
        notiz TEXT
    );

    CREATE TABLE budgets (
        id TEXT PRIMARY KEY,
        bereich TEXT NOT NULL CHECK (bereich IN ('wallet','real')),
        kategorie TEXT NOT NULL,
        limit_cent INTEGER NOT NULL CHECK (limit_cent >= 0),
        zeitraum TEXT NOT NULL CHECK (zeitraum IN ('monat','gesamt')),
        erstellt TEXT NOT NULL,
        UNIQUE (bereich, kategorie, zeitraum)
    );

    CREATE TABLE gedaechtnis (
        id TEXT PRIMARY KEY,
        zeit TEXT NOT NULL,
        art TEXT NOT NULL CHECK (art IN ('fakt','entscheidung','hypothese','vorschlag')),
        thema TEXT NOT NULL,
        inhalt TEXT NOT NULL,
        quelle TEXT NOT NULL,
        autor TEXT NOT NULL,
        aufgabe_id TEXT
    );

    CREATE TABLE ziele (
        id TEXT PRIMARY KEY,
        titel TEXT NOT NULL,
        beschreibung TEXT NOT NULL DEFAULT '',
        prioritaet INTEGER NOT NULL DEFAULT 3 CHECK (prioritaet BETWEEN 1 AND 5),
        status TEXT NOT NULL DEFAULT 'aktiv' CHECK (status IN ('aktiv','erreicht','verworfen')),
        erstellt TEXT NOT NULL,
        aktualisiert TEXT NOT NULL
    );

    CREATE TABLE modellaufrufe (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        zeit TEXT NOT NULL,
        anbieter TEXT NOT NULL,
        modell TEXT NOT NULL,
        agent TEXT NOT NULL,
        aufgabe_id TEXT,
        zeichen_ein INTEGER NOT NULL DEFAULT 0,
        zeichen_aus INTEGER NOT NULL DEFAULT 0,
        kosten_cent INTEGER NOT NULL DEFAULT 0,
        ergebnis TEXT NOT NULL
    );

    CREATE TABLE kontakte (
        id TEXT PRIMARY KEY,
        firma TEXT NOT NULL,
        ansprechpartner TEXT,
        branche TEXT,
        ort TEXT,
        quelle TEXT NOT NULL,
        einwilligung TEXT NOT NULL DEFAULT 'keine' CHECK (einwilligung IN ('keine','ja')),
        einwilligung_nachweis TEXT,
        status TEXT NOT NULL DEFAULT 'neu' CHECK (status IN ('neu','kontaktiert','interessiert',
                                                             'angebot','gewonnen','verloren')),
        naechster_schritt TEXT,
        notizen TEXT,
        erstellt TEXT NOT NULL,
        aktualisiert TEXT NOT NULL
    );

    CREATE TABLE angebote (
        id TEXT PRIMARY KEY,
        kontakt_id TEXT,
        produkt_id TEXT,
        titel TEXT NOT NULL,
        betrag_cent INTEGER NOT NULL CHECK (betrag_cent >= 0),
        status TEXT NOT NULL DEFAULT 'entwurf' CHECK (status IN ('entwurf','geprueft','versendet',
                                                                'angenommen','abgelehnt')),
        inhalt TEXT NOT NULL,
        datei TEXT,
        erstellt TEXT NOT NULL,
        aktualisiert TEXT NOT NULL
    );

    CREATE TABLE produkte (
        id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        typ TEXT NOT NULL,
        status TEXT NOT NULL CHECK (status IN ('entwurf','qualitaet_ok','qualitaet_mangel','beispiel')),
        ordner TEXT NOT NULL,
        dateien TEXT NOT NULL DEFAULT '[]',
        qualitaet TEXT NOT NULL DEFAULT '{}',
        einschraenkungen TEXT NOT NULL DEFAULT '[]',
        aufgabe_id TEXT,
        erstellt TEXT NOT NULL
    );
    """,
    # 2 – Auftragssuche: öffentliche Ausschreibungen und Suchläufe
    """
    CREATE TABLE ausschreibungen (
        id TEXT PRIMARY KEY,
        quelle TEXT NOT NULL CHECK (quelle IN ('ted','service_bund','evergabe_nrw')),
        extern_id TEXT NOT NULL,
        titel TEXT NOT NULL,
        vergabestelle TEXT,
        ort TEXT,
        plz TEXT,
        region TEXT,
        frist TEXT,
        veroeffentlicht TEXT,
        verfahren TEXT,
        link TEXT NOT NULL,
        cpv TEXT NOT NULL DEFAULT '[]',
        punkte INTEGER NOT NULL DEFAULT 0 CHECK (punkte BETWEEN 0 AND 100),
        begruendung TEXT NOT NULL DEFAULT '[]',
        status TEXT NOT NULL DEFAULT 'neu' CHECK (status IN ('neu','interessant','abgelehnt','vorbereitet',
                                                            'abgegeben','gewonnen','verloren')),
        notiz TEXT,
        unterlagen TEXT,
        gefunden TEXT NOT NULL,
        aktualisiert TEXT NOT NULL,
        UNIQUE (quelle, extern_id)
    );
    CREATE INDEX ausschreibungen_frist ON ausschreibungen(status, frist);

    CREATE TABLE suchlaeufe (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        zeit TEXT NOT NULL,
        quelle TEXT NOT NULL,
        ergebnis TEXT NOT NULL CHECK (ergebnis IN ('ok','fehler','gesperrt')),
        gefunden INTEGER NOT NULL DEFAULT 0,
        neu INTEGER NOT NULL DEFAULT 0,
        passend INTEGER NOT NULL DEFAULT 0,
        meldung TEXT,
        aufgabe_id TEXT
    );
    """,
    # 3 – Rückmeldungen echter Interessenten (PDF 2.3: „Miss Reaktionen und verbessere das Angebot“)
    """
    CREATE TABLE rueckmeldungen (
        id TEXT PRIMARY KEY,
        zeit TEXT NOT NULL,
        kontakt_id TEXT,
        angebot_id TEXT,
        angebot_art TEXT NOT NULL CHECK (angebot_art IN ('google_profil','webseite','reinigung','sonstiges')),
        kanal TEXT NOT NULL CHECK (kanal IN ('gespraech','telefon','brief','email','vor_ort','sonstiges')),
        reaktion TEXT NOT NULL CHECK (reaktion IN ('interessiert','neutral','abgelehnt','keine_antwort')),
        grund TEXT CHECK (grund IS NULL OR grund IN ('preis','kein_bedarf','spaeter','hat_anbieter','vertrauen',
                                                     'leistung_unklar','sonstiges')),
        notiz TEXT CHECK (notiz IS NULL OR length(notiz) <= 2000),
        erfasst_von TEXT NOT NULL,
        CHECK (grund IS NULL OR reaktion IN ('abgelehnt','neutral'))
    );
    CREATE INDEX rueckmeldungen_art ON rueckmeldungen(angebot_art, zeit);
    """,
]


def _migration_gegenbuchung_einmal(con):
    """4 – Jede Buchung darf höchstens EINMAL gegengebucht werden (Sicherheitsprüfung, Befund 7).

    Ein eindeutiger Teil-Index lässt die Datenbank selbst eine zweite Gegenbuchung ablehnen. Hat eine ältere
    Datenbank durch den früheren Wettlauf schon Dubletten, lässt sich der Index nicht anlegen – und die Buchungen
    sind unveränderbar. Dann bricht die Migration NICHT ab (sonst startet das System nicht), sondern meldet die
    Dubletten im Protokoll; neue Dubletten verhindert weiterhin die Prüfung im Code (in derselben Transaktion)."""
    for tabelle, index in (("real_buchungen", "real_gegen_einmal"), ("wallet_buchungen", "wallet_gegen_einmal")):
        dubletten = [z[0] for z in con.execute(
            "SELECT gegenbuchung_zu FROM %s WHERE gegenbuchung_zu IS NOT NULL GROUP BY gegenbuchung_zu "
            "HAVING COUNT(*) > 1" % tabelle).fetchall()]
        if dubletten:
            con.execute("INSERT INTO protokoll (zeit, ebene, quelle, ereignis, details) VALUES (?,?,?,?,?)",
                        (jetzt(), "warnung", "migration",
                         "Doppelte Gegenbuchungen in %s gefunden – Schutz-Index nicht angelegt, die Prüfung im "
                         "Code verhindert weitere Dubletten" % tabelle,
                         json.dumps({"tabelle": tabelle, "gegenbuchung_zu": dubletten[:50]}, ensure_ascii=False)))
            continue
        con.execute("CREATE UNIQUE INDEX IF NOT EXISTS %s ON %s(gegenbuchung_zu) WHERE gegenbuchung_zu IS NOT NULL"
                    % (index, tabelle))


MIGRATIONEN.append(_migration_gegenbuchung_einmal)


def jetzt():
    return datetime.datetime.now().astimezone().isoformat(timespec="seconds")


def neue_id(praefix=""):
    return praefix + uuid.uuid4().hex[:12]


class Datenbank:
    """Dünne Hülle um sqlite3, threadsicher über eine Sperre für Schreibvorgänge."""

    def __init__(self, pfad=None):
        self.pfad = pfad or konfig.db_pfad()
        self._sperre = threading.RLock()
        self._con = sqlite3.connect(self.pfad, check_same_thread=False, isolation_level=None,
                                    timeout=30)
        self._con.row_factory = sqlite3.Row
        self._con.execute("PRAGMA journal_mode=WAL")
        self._con.execute("PRAGMA foreign_keys=ON")
        self._con.execute("PRAGMA synchronous=NORMAL")
        self.migrieren()

    # ---- Migrationen -------------------------------------------------
    def schema_version(self):
        self._con.execute("CREATE TABLE IF NOT EXISTS schema_version (version INTEGER PRIMARY KEY,"
                          " angewendet TEXT NOT NULL)")
        zeile = self._con.execute("SELECT MAX(version) FROM schema_version").fetchone()
        return zeile[0] or 0

    def migrieren(self):
        with self._sperre:
            aktuell = self.schema_version()
            for nummer, sql in enumerate(MIGRATIONEN, start=1):
                if nummer <= aktuell:
                    continue
                self._con.execute("BEGIN IMMEDIATE")
                try:
                    if callable(sql):  # Migration mit Bedingungen (Python-Schritt)
                        sql(self._con)
                    else:
                        for befehl in _teile_sql(sql):
                            self._con.execute(befehl)
                    self._con.execute("INSERT INTO schema_version VALUES (?, ?)", (nummer, jetzt()))
                    self._con.execute("COMMIT")
                except Exception:
                    self._con.execute("ROLLBACK")
                    raise

    # ---- Zugriff -----------------------------------------------------
    def alle(self, sql, parameter=()):
        with self._sperre:
            return [dict(z) for z in self._con.execute(sql, parameter).fetchall()]

    def eins(self, sql, parameter=()):
        with self._sperre:
            zeile = self._con.execute(sql, parameter).fetchone()
            return dict(zeile) if zeile else None

    def wert(self, sql, parameter=()):
        with self._sperre:
            zeile = self._con.execute(sql, parameter).fetchone()
            return zeile[0] if zeile else None

    def ausfuehren(self, sql, parameter=()):
        with self._sperre:
            return self._con.execute(sql, parameter).rowcount

    def transaktion(self):
        return _Transaktion(self)

    def integritaet(self):
        return self.wert("PRAGMA integrity_check") == "ok"

    def sichern_nach(self, ziel):
        with self._sperre:
            ziel_con = sqlite3.connect(ziel)
            try:
                self._con.backup(ziel_con)
            finally:
                ziel_con.close()

    def schliessen(self):
        with self._sperre:
            self._con.close()


class _Transaktion:
    def __init__(self, db):
        self.db = db

    def __enter__(self):
        self.db._sperre.acquire()
        self.db._con.execute("BEGIN IMMEDIATE")
        return self.db._con

    def __exit__(self, typ, wert, tb):
        try:
            self.db._con.execute("ROLLBACK" if typ else "COMMIT")
        finally:
            self.db._sperre.release()
        return False


def _teile_sql(skript):
    """Teilt ein Migrationsskript in Einzelbefehle; Trigger (BEGIN ... END;) bleiben ganz."""
    befehle, puffer = [], []
    for zeile in skript.splitlines():
        puffer.append(zeile)
        text = "\n".join(puffer).strip()
        if not text:
            puffer = []
            continue
        if sqlite3.complete_statement(text):
            befehle.append(text)
            puffer = []
    rest = "\n".join(puffer).strip()
    if rest:
        befehle.append(rest)
    return befehle
