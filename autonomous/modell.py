# -*- coding: utf-8 -*-
"""Austauschbare Modellschicht (Abschnitt 3).

- Standard: KEIN Modell. Alle Kernfunktionen (Verwaltung, Buchhaltung, Planung, Status) arbeiten
  deterministisch und brauchen kein Modell.
- Optional: Ollama auf diesem Rechner (kostenlos, nur 127.0.0.1/localhost erlaubt).
- Kostenpflichtige Anbieter sind in Version 1 NICHT angebunden (keine automatischen Fallbacks).
- Jeder Aufruf wird protokolliert; Tageslimit wird vor dem Aufruf geprüft.
"""

import json
import urllib.error
import urllib.request

from .db import jetzt

ANBIETER = {
    "keiner": {"name": "Kein Modell", "kosten": "0 €", "status": "aktiv – Kernfunktionen laufen deterministisch"},
    "ollama": {"name": "Ollama (lokal auf diesem Rechner)", "kosten": "0 € (eigene Hardware, Strom)",
               "status": "optional – auf dem Mac nicht verifiziert, muss separat installiert sein"},
    "extern_kostenpflichtig": {"name": "Externe Cloud-Modelle (z. B. Anthropic API, OpenAI)",
                               "kosten": "nutzungsabhängig, kostenpflichtig",
                               "status": "NICHT ANGEBUNDEN – nur nach ausdrücklicher Zustimmung, mit Preisangabe"},
}
OLLAMA_URL = "http://127.0.0.1:11434/api/generate"


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

    def status(self):
        e = self.einstellungen.alle()
        return {
            "anbieter": e["modell_anbieter"],
            "anbieter_info": ANBIETER.get(e["modell_anbieter"]),
            "alle_anbieter": ANBIETER,
            "aufrufe_heute": self.aufrufe_heute(),
            "limit_tag": e["modell_max_aufrufe_tag"],
            "verfuegbar": e["modell_anbieter"] != "keiner",
        }

    def verfuegbar(self):
        return self.einstellungen.hole("modell_anbieter") != "keiner"

    def frage(self, prompt, agent, aufgabe_id=None, max_zeichen=4000, zeitlimit=60):
        """Fragt das eingestellte Modell. Wirft ModellNichtVerfuegbar, wenn keins da ist –
        Aufrufer müssen dann deterministisch weiterarbeiten."""
        e = self.einstellungen.alle()
        anbieter = e["modell_anbieter"]
        if anbieter == "keiner":
            raise ModellNichtVerfuegbar("Kein Modell eingestellt.")
        if self.aufrufe_heute() >= e["modell_max_aufrufe_tag"]:
            self._log(anbieter, "-", agent, aufgabe_id, len(prompt), 0, "limit")
            raise ModellNichtVerfuegbar("Tageslimit für Modellaufrufe erreicht.")
        if anbieter != "ollama":
            raise ModellNichtVerfuegbar("Anbieter nicht angebunden.")
        prompt = str(prompt)[:20000]
        daten = json.dumps({"model": e["ollama_modell"], "prompt": prompt, "stream": False,
                            "options": {"num_predict": max(64, max_zeichen // 3)}}).encode()
        anfrage = urllib.request.Request(OLLAMA_URL, data=daten, headers={"Content-Type": "application/json"})
        try:
            # Proxy bewusst umgehen: nur lokale Adresse
            oeffner = urllib.request.build_opener(urllib.request.ProxyHandler({}))
            with oeffner.open(anfrage, timeout=zeitlimit) as antwort:
                text = json.loads(antwort.read(2_000_000).decode("utf-8")).get("response", "")
        except (urllib.error.URLError, OSError, ValueError) as fehler:
            self._log(anbieter, e["ollama_modell"], agent, aufgabe_id, len(prompt), 0, "fehler")
            self.protokoll.warnung("modell", "Lokales Modell nicht erreichbar", str(fehler))
            raise ModellNichtVerfuegbar("Lokales Modell nicht erreichbar: %s" % fehler)
        text = text[:max_zeichen]
        self._log(anbieter, e["ollama_modell"], agent, aufgabe_id, len(prompt), len(text), "ok")
        return text

    def _log(self, anbieter, modell, agent, aufgabe_id, ein, aus, ergebnis):
        self.db.ausfuehren("INSERT INTO modellaufrufe (zeit, anbieter, modell, agent, aufgabe_id, zeichen_ein,"
                           " zeichen_aus, kosten_cent, ergebnis) VALUES (?,?,?,?,?,?,?,0,?)",
                           (jetzt(), anbieter, modell, agent, aufgabe_id, ein, aus, ergebnis))

    def protokoll_liste(self, grenze=100):
        return self.db.alle("SELECT * FROM modellaufrufe ORDER BY id DESC LIMIT ?", (grenze,))
