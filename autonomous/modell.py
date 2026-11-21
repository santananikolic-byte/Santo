# -*- coding: utf-8 -*-
"""Austauschbare Modellschicht (PDF Abschnitt 3 und 4, Protokoll Punkt 2).

- Standard: KEIN Modell. Alle Kernfunktionen (Verwaltung, Buchhaltung, Planung, Status) arbeiten
  deterministisch und brauchen kein Modell.
- Optional: Ollama auf diesem Rechner (kostenlos, nur 127.0.0.1/localhost erlaubt) – siehe ki/anbieter.py.
- Kostenpflichtige oder externe Anbieter sind NICHT angebunden (keine automatischen Rückfälle).
- Jeder Modellaufruf wird protokolliert; das Tageslimit wird VOR dem Aufruf geprüft.
- Modellausgabe ist nicht vertrauenswürdig: gesäubert, gekürzt, gekennzeichnet – sie löst nie etwas aus.
"""

from .db import jetzt
from .ki import anbieter as ki_anbieter
from .ki import ausgabe

ANBIETER = {
    "keiner": {"name": "Kein Modell", "kosten": "0 €", "status": "aktiv – Kernfunktionen laufen deterministisch"},
    "ollama": {"name": "Ollama (lokal auf diesem Rechner)", "kosten": "0 € (eigene Hardware, Strom)",
               "status": "optional – muss auf dem Mac separat installiert sein; mit echtem Modell NICHT VERIFIZIERT"},
    "extern_kostenpflichtig": {"name": "Externe Cloud-Modelle (z. B. Anthropic API, OpenAI)",
                               "kosten": "nutzungsabhängig, kostenpflichtig",
                               "status": "NICHT ANGEBUNDEN – nur nach ausdrücklicher Zustimmung, mit Preisangabe"},
}


class ModellNichtVerfuegbar(Exception):
    pass


class Modellschicht:
    def __init__(self, db, protokoll, einstellungen):
        self.db = db
        self.protokoll = protokoll
        self.einstellungen = einstellungen

    def aufrufe_heute(self):
        return int(self.db.wert("SELECT COUNT(*) FROM modellaufrufe WHERE substr(zeit,1,10)=? "
                                "AND ergebnis IN ('ok','fehler')", (jetzt()[:10],)))

    def _anbieter(self, e=None):
        try:
            return ki_anbieter.anbieter_fuer(e or self.einstellungen.alle())
        except ki_anbieter.AnbieterFehler as f:
            raise ModellNichtVerfuegbar(str(f))

    def status(self):
        """Schneller Status aus den Einstellungen – ohne Netzzugriff (wird ständig abgefragt)."""
        e = self.einstellungen.alle()
        return {
            "anbieter": e["modell_anbieter"],
            "modell": e["ollama_modell"] if e["modell_anbieter"] == "ollama" else None,
            "adresse": e["ollama_adresse"] if e["modell_anbieter"] == "ollama" else None,
            "anbieter_info": ANBIETER.get(e["modell_anbieter"]),
            "alle_anbieter": ANBIETER,
            "aufrufe_heute": self.aufrufe_heute(),
            "limit_tag": e["modell_max_aufrufe_tag"],
            "verfuegbar": e["modell_anbieter"] != "keiner",
        }

    def pruefen(self):
        """Echter Status: Ist das Modell erreichbar und installiert? Kostenlos, kein Modellaufruf."""
        e = self.einstellungen.alle()
        try:
            st = self._anbieter(e).status()
        except ModellNichtVerfuegbar as f:
            st = {"erreichbar": False, "modell_vorhanden": False, "installierte_modelle": [], "hinweis": str(f)}
        return dict(st, anbieter=e["modell_anbieter"],
                    modell=e["ollama_modell"] if e["modell_anbieter"] == "ollama" else None,
                    aufrufe_heute=self.aufrufe_heute(), limit_tag=e["modell_max_aufrufe_tag"])

    def verfuegbar(self):
        return self.einstellungen.hole("modell_anbieter") != "keiner"

    def _erzeugen(self, system, nutzer, agent, aufgabe_id, max_zeichen, zeitlimit):
        e = self.einstellungen.alle()
        if e["modell_anbieter"] == "keiner":
            raise ModellNichtVerfuegbar("Kein Modell eingestellt.")
        anbieter = self._anbieter(e)
        modellname = anbieter.modell or "-"
        laenge_ein = len(system or "") + len(nutzer or "")
        if self.aufrufe_heute() >= e["modell_max_aufrufe_tag"]:
            self._log(anbieter.name, modellname, agent, aufgabe_id, laenge_ein, 0, "limit")
            raise ModellNichtVerfuegbar("Tageslimit für Modellaufrufe erreicht.")
        try:
            roh = anbieter.erzeugen(str(system or "")[:20000], str(nutzer or "")[:20000], max_zeichen, zeitlimit)
        except ki_anbieter.AnbieterFehler as f:
            self._log(anbieter.name, modellname, agent, aufgabe_id, laenge_ein, 0, "fehler")
            self.protokoll.warnung("modell", "Lokales Modell nicht nutzbar", str(f))
            meldung = str(f)
            if "nicht erreichbar" not in meldung and "Fehler" not in meldung:
                meldung = "Lokales Modell nicht nutzbar: " + meldung
            raise ModellNichtVerfuegbar(meldung)
        text = ausgabe.saeubern(roh, max_zeichen)
        self._log(anbieter.name, modellname, agent, aufgabe_id, laenge_ein, len(text), "ok")
        return text, modellname

    def frage(self, prompt, agent, aufgabe_id=None, max_zeichen=4000, zeitlimit=60, system=""):
        """Fragt das eingestellte Modell und gibt gesäuberten Text zurück. Wirft ModellNichtVerfuegbar,
        wenn keins da ist – Aufrufer müssen dann deterministisch weiterarbeiten."""
        return self._erzeugen(system, prompt, agent, aufgabe_id, max_zeichen, zeitlimit)[0]

    def frage_gekennzeichnet(self, system, nutzer, agent, aufgabe_id=None, max_zeichen=2000, zeitlimit=120):
        """Wie frage(), aber mit Kennzeichnung „KI-Entwurf – ungeprüft, lokales Modell …“."""
        text, modellname = self._erzeugen(system, nutzer, agent, aufgabe_id, max_zeichen, zeitlimit)
        return ausgabe.kennzeichnen(text, modellname)

    def _log(self, anbieter, modell, agent, aufgabe_id, ein, aus, ergebnis):
        self.db.ausfuehren("INSERT INTO modellaufrufe (zeit, anbieter, modell, agent, aufgabe_id, zeichen_ein,"
                           " zeichen_aus, kosten_cent, ergebnis) VALUES (?,?,?,?,?,?,?,0,?)",
                           (jetzt(), anbieter, modell, agent, aufgabe_id, ein, aus, ergebnis))

    def protokoll_liste(self, grenze=100):
        return self.db.alle("SELECT * FROM modellaufrufe ORDER BY id DESC LIMIT ?", (grenze,))
