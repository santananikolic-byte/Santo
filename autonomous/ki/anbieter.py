# -*- coding: utf-8 -*-
"""Austauschbare Modell-Anbieter.

Jeder Anbieter erfüllt dieselbe kleine Schnittstelle (status, erzeugen). Ein späterer Austausch des
Modells heißt: neuen Anbieter hier ergänzen – Agentenlogik, Gedächtnis und Werkzeuge bleiben unverändert.
"""

import json
import re
import urllib.error
import urllib.request
from urllib.parse import urlsplit

from . import modelfile, vorlagen

LOKALE_HOSTS = ("127.0.0.1", "localhost", "::1")
MAX_ANTWORT_BYTES = 2_000_000
STATUS_ZEITLIMIT = 3
TEMPERATUR = 0.2
SEED = 42  # fester Startwert: gleiche Anfrage → meist gleiche Antwort (nicht garantiert, siehe docs/KI.md)


class AnbieterFehler(Exception):
    pass


class _KeineUmleitung(urllib.request.HTTPRedirectHandler):
    """Ollama leitet nie um. Eine Umleitung würde Anfragen (mit Marktdaten) an einen anderen Ort schicken –
    darum wird sie nicht befolgt, sondern als Fehler behandelt."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def lokale_adresse_ok(adresse):
    """Nur http://127.0.0.1|localhost|[::1]:PORT – ohne Pfad, Anfrage, Benutzer oder Passwort."""
    if not isinstance(adresse, str) or len(adresse) > 60:
        return False
    try:
        t = urlsplit(adresse)
        port = t.port
    except ValueError:
        return False
    return (t.scheme == "http" and (t.hostname or "").lower() in LOKALE_HOSTS and port is not None
            and 1 <= port <= 65535 and t.path in ("", "/") and not t.query and not t.fragment
            and t.username is None and t.password is None)


class Anbieter:
    """Schnittstelle. name: Kennung; modell: Modellname (oder None)."""
    name = "basis"
    modell = None

    def status(self):
        raise NotImplementedError

    def erzeugen(self, system, nutzer, max_zeichen, zeitlimit):
        raise NotImplementedError


class KeinAnbieter(Anbieter):
    name = "keiner"

    def status(self):
        return {"erreichbar": False, "modell_vorhanden": False, "installierte_modelle": [],
                "hinweis": "Kein Modell eingestellt – alle Kernfunktionen laufen ohne Modell."}

    def erzeugen(self, system, nutzer, max_zeichen, zeitlimit):
        raise AnbieterFehler("Kein Modell eingestellt.")


class OllamaAnbieter(Anbieter):
    """Ollama auf diesem Rechner (https://docs.ollama.com/api/chat, /api/tags). Proxy wird umgangen."""
    name = "ollama"

    def __init__(self, adresse, modell):
        if not lokale_adresse_ok(adresse):
            raise AnbieterFehler("Ollama-Adresse ist nicht lokal – nur 127.0.0.1, localhost oder [::1] erlaubt.")
        self.adresse = adresse.rstrip("/")
        self.modell = modell

    @staticmethod
    def _oeffner():
        # Kein Proxy und keine Umleitung: das Modell läuft auf diesem Rechner, Daten verlassen ihn nicht
        return urllib.request.build_opener(urllib.request.ProxyHandler({}), _KeineUmleitung())

    def _lesen(self, anfrage, zeitlimit):
        with self._oeffner().open(anfrage, timeout=zeitlimit) as a:
            roh = a.read(MAX_ANTWORT_BYTES + 1)
        if len(roh) > MAX_ANTWORT_BYTES:
            raise AnbieterFehler("Antwort des Modells zu groß.")
        try:
            return json.loads(roh.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            raise AnbieterFehler("Antwort des Modells ist kein gültiges JSON.")

    def status(self):
        try:
            d = self._lesen(urllib.request.Request(self.adresse + "/api/tags"), STATUS_ZEITLIMIT)
        except (AnbieterFehler, urllib.error.URLError, OSError, ValueError):
            return {"erreichbar": False, "modell_vorhanden": False, "installierte_modelle": [],
                    "hinweis": "Ollama nicht erreichbar unter %s – auf dem Mac Ollama starten "
                               "(Programm „Ollama“ öffnen)." % self.adresse}
        modelle = []
        for m in (d.get("models") if isinstance(d, dict) else None) or []:
            if isinstance(m, dict) and isinstance(m.get("name"), str):
                modelle.append(re.sub(r"[^\w.:\-/]", "", m["name"])[:60])
        vorhanden = self.modell in modelle or (":" not in self.modell and self.modell + ":latest" in modelle)
        hinweis = "Ollama erreichbar, Modell %s vorhanden." % self.modell if vorhanden else (
            "Ollama erreichbar, aber Modell %s ist nicht installiert – auf dem Mac im Terminal: "
            "ollama pull %s" % (self.modell, self.modell))
        st = {"erreichbar": True, "modell_vorhanden": vorhanden, "installierte_modelle": modelle[:20],
              "hinweis": hinweis}
        if vorhanden and modelfile.ist_eigenes_modell(self.modell):
            st["eigene_regeln"] = self._regeln_eingebaut()
            st["hinweis"] += (" Eigenes Modell mit %s." % modelfile.KENNUNG if st["eigene_regeln"] else
                              " Im Modell fehlen die aktuellen AUTONOMOUS-Regeln – bitte autonomous-ki-einrichten.sh "
                              "erneut ausführen.")
        return st

    def _regeln_eingebaut(self):
        """Steckt der aktuelle AUTONOMOUS-Systemtext im Modell? (POST /api/show liefert das Feld „system“)"""
        anfrage = urllib.request.Request(self.adresse + "/api/show", data=json.dumps({"model": self.modell}).encode(
            "utf-8"), headers={"Content-Type": "application/json"})
        try:
            d = self._lesen(anfrage, STATUS_ZEITLIMIT)
        except (AnbieterFehler, urllib.error.URLError, OSError, ValueError):
            return False
        system = d.get("system") if isinstance(d, dict) else None
        return isinstance(system, str) and modelfile.KENNUNG in system

    def nachrichten(self, system, nutzer):
        """Das eigene Modell bringt die Grundregeln fest eingebaut mit. Eine System-Nachricht würde sie samt
        Firmenwissen ERSETZEN (gemessen mit Ollama 0.40.17) – darum geht sie dort nicht mit. Besondere Regeln (jeder
        andere Systemtext) gehen immer mit; eine leere System-Nachricht nie."""
        system = system or ""
        weglassen = not system.strip() or (modelfile.ist_eigenes_modell(self.modell)
                                           and system.strip() == vorlagen.GRUNDREGELN)
        return ([] if weglassen else [{"role": "system", "content": system}]) + [{"role": "user", "content": nutzer}]

    def erzeugen(self, system, nutzer, max_zeichen, zeitlimit):
        koerper = {"model": self.modell, "stream": False, "messages": self.nachrichten(system, nutzer),
                   "options": {"num_predict": max(32, int(max_zeichen) // 3), "temperature": TEMPERATUR,
                               "seed": SEED}}
        anfrage = urllib.request.Request(self.adresse + "/api/chat", data=json.dumps(koerper).encode("utf-8"),
                                         headers={"Content-Type": "application/json"})
        try:
            d = self._lesen(anfrage, zeitlimit)
        except urllib.error.HTTPError as f:
            raise AnbieterFehler("Modell antwortet mit Fehler %s." % f.code)
        except (urllib.error.URLError, OSError) as f:
            raise AnbieterFehler("Lokales Modell nicht erreichbar: %s" % getattr(f, "reason", f))
        nachricht = d.get("message") if isinstance(d, dict) else None
        inhalt = nachricht.get("content") if isinstance(nachricht, dict) else None
        if not isinstance(inhalt, str):
            raise AnbieterFehler("Antwort des Modells hat ein unerwartetes Format.")
        return inhalt


def anbieter_fuer(einstellungen):
    """Anbieter laut Einstellungen. Unbekannt → KeinAnbieter (nie ein externer Dienst als Rückfall)."""
    if einstellungen.get("modell_anbieter") == "ollama":
        return OllamaAnbieter(einstellungen.get("ollama_adresse") or "http://127.0.0.1:11434",
                              einstellungen.get("ollama_modell") or "gemma3:4b")
    return KeinAnbieter()
