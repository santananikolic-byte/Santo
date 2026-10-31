# -*- coding: utf-8 -*-
"""Provider Manager - welche KI darf JARVIS nutzen, und ist sie bereit?

Regel: nur offizielle Wege über vorhandene Konten, nie ein kostenpflichtiger
Ersatz. Konkret:

* **Claude Code** wird genutzt, aber nur, wenn es mit dem Claude-Abo
  (Anmeldeart ``claude.ai``) angemeldet ist. Ist es über einen API-Schlüssel
  angemeldet, nutzt JARVIS es nicht - das würde pro Anfrage kosten.
  Umgebungsvariablen, die Claude Code auf eine bezahlte Abrechnung umlenken
  würden (API-Schlüssel, Bedrock, Vertex), werden für den Aufruf entfernt.
* Andere Anbieter (Codex, Gemini CLI) nutzt JARVIS bewusst nicht - der Nutzer
  will nur Claude Code.

Das Modell ist einstellbar (``modell`` in config.json): "opus" ist das
klügste, "sonnet" das schnellere mit mehr Spielraum im Abo-Limit. Wie gründlich
nachgedacht wird, regelt Claude Code bei diesen Modellen selbst.

Claude Code läuft mit ``claude -p`` (Modus ohne Bildschirm) und in Phase 3
ganz ohne Werkzeuge: Es antwortet nur, es liest keine Dateien und führt
nichts aus. Werkzeuge kommen mit der Berechtigungsschicht.
"""

import datetime
import json
import os
import re
import shutil
import subprocess
import threading

# Diese Variablen würden Claude Code auf eine kostenpflichtige Abrechnung lenken.
BEZAHL_VARIABLEN = ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "CLAUDE_CODE_USE_BEDROCK",
                    "CLAUDE_CODE_USE_VERTEX", "CLAUDE_CODE_USE_FOUNDRY")
CLAUDE_ORTE = ("~/.local/bin/claude", "~/.claude/local/claude", "/opt/homebrew/bin/claude",
               "/usr/local/bin/claude")
ABO_ANMELDUNG = "claude.ai"


class ProviderFehler(Exception):
    """``art`` ist eine von: nicht_installiert, nicht_angemeldet, nicht_erlaubt, limit,
    beschaeftigt, zeitueberschreitung, fehler, kein_provider."""

    def __init__(self, art, meldung):
        super().__init__(meldung)
        self.art = art


def saubere_umgebung():
    umgebung = dict(os.environ)
    for name in BEZAHL_VARIABLEN:
        umgebung.pop(name, None)
    return umgebung


def _json_aus(ausgabe):
    ausgabe = (ausgabe or "").strip()
    for kandidat in (ausgabe, ausgabe.splitlines()[-1] if ausgabe else ""):
        try:
            return json.loads(kandidat)
        except ValueError:
            continue
    return None


class ClaudeCode:
    name = "claude_code"
    anzeige = "Claude Code"

    def __init__(self, arbeitsordner, timeout=300, modell=""):
        self.arbeitsordner = arbeitsordner
        self.timeout = timeout
        # Leer = Claude Code wählt selbst. "opus" = klügstes Modell, "sonnet" = schneller.
        self.modell = (modell or "").strip()

    def finden(self):
        fest = os.environ.get("JARVIS_CLAUDE")
        if fest:
            return fest if os.path.isfile(fest) and os.access(fest, os.X_OK) else None
        gefunden = shutil.which("claude")
        if gefunden:
            return gefunden
        for ort in CLAUDE_ORTE:
            pfad = os.path.expanduser(ort)
            if os.path.isfile(pfad) and os.access(pfad, os.X_OK):
                return pfad
        return None

    def _lauf(self, programm, argumente, eingabe=None, timeout=20):
        os.makedirs(self.arbeitsordner, exist_ok=True)
        return subprocess.run([programm] + argumente, input=eingabe, capture_output=True, text=True,
                              timeout=timeout, cwd=self.arbeitsordner, env=saubere_umgebung())

    def pruefen(self):
        """Ist Claude Code installiert und mit dem Abo angemeldet? Verbraucht kein Kontingent."""
        ergebnis = {"name": self.name, "anzeige": self.anzeige, "installiert": False, "version": None,
                    "angemeldet": False, "anmeldeart": None, "plan": None, "nutzbar": False, "hinweis": ""}
        programm = self.finden()
        if not programm:
            ergebnis["hinweis"] = ("nicht installiert – im Terminal: curl -fsSL https://claude.ai/install.sh | bash, "
                                   "danach „claude“ starten und mit dem Claude-Konto anmelden")
            return ergebnis
        ergebnis["installiert"] = True
        try:
            ergebnis["version"] = (self._lauf(programm, ["--version"], timeout=15).stdout or "").strip() or None
            status = _json_aus(self._lauf(programm, ["auth", "status"], timeout=20).stdout)
        except (OSError, subprocess.SubprocessError) as fehler:
            ergebnis["hinweis"] = "lässt sich nicht starten: %s" % fehler
            return ergebnis
        if not isinstance(status, dict):
            ergebnis["hinweis"] = "Anmeldestatus nicht lesbar – im Terminal „claude auth status“ prüfen"
            return ergebnis
        ergebnis["angemeldet"] = bool(status.get("loggedIn"))
        ergebnis["anmeldeart"] = status.get("authMethod")
        ergebnis["plan"] = status.get("subscriptionType")
        if not ergebnis["angemeldet"]:
            ergebnis["hinweis"] = "nicht angemeldet – im Terminal „claude“ starten und mit dem Claude-Konto anmelden"
        elif ergebnis["anmeldeart"] != ABO_ANMELDUNG:
            ergebnis["hinweis"] = ("angemeldet über „%s“ statt über das Claude-Abo – JARVIS nutzt das nicht, "
                                   "weil es pro Anfrage kosten würde" % ergebnis["anmeldeart"])
        else:
            ergebnis["nutzbar"] = True
            ergebnis["hinweis"] = "bereit (Claude-Abo%s, Modell: %s)" % (
                ", " + ergebnis["plan"] if ergebnis["plan"] else "", self.modell or "Standard von Claude Code")
        ergebnis["modell"] = self.modell or None
        return ergebnis

    def fragen(self, text, system, sitzung=None):
        """Eine Anfrage an Claude Code. Gibt Antwort, Sitzungskennung und Dauer zurück."""
        programm = self.finden()
        if not programm:
            raise ProviderFehler("nicht_installiert", "Claude Code ist nicht installiert.")
        argumente = ["-p", "--output-format", "json", "--system-prompt", system, "--tools", ""]
        if self.modell:
            argumente += ["--model", self.modell]
        if sitzung:
            argumente += ["--resume", sitzung]
        try:
            lauf = self._lauf(programm, argumente, eingabe=text, timeout=self.timeout)
        except subprocess.TimeoutExpired:
            raise ProviderFehler("zeitueberschreitung",
                                 "Claude hat länger als %d Sekunden gebraucht." % self.timeout) from None
        except OSError as fehler:
            raise ProviderFehler("fehler", "Claude Code ließ sich nicht starten: %s" % fehler) from None

        daten = _json_aus(lauf.stdout)
        if lauf.returncode == 0 and isinstance(daten, dict) and not daten.get("is_error") and daten.get("result"):
            return {"antwort": str(daten["result"]).strip(), "sitzung": daten.get("session_id") or sitzung,
                    "dauer_ms": daten.get("duration_ms")}

        meldung = str(daten.get("result") or "") if isinstance(daten, dict) else ""
        meldung = (meldung or lauf.stderr or lauf.stdout or "keine Antwort").strip()
        klein = meldung.lower()
        if sitzung and ("no conversation" in klein or "not found" in klein):
            # Gespräch ist auf diesem Mac nicht mehr vorhanden: neu beginnen.
            return self.fragen(text, system, None)
        if "login" in klein or "logged in" in klein or "authenticat" in klein or "api key" in klein:
            raise ProviderFehler("nicht_angemeldet", "Claude Code ist nicht angemeldet. Im Terminal „claude“ "
                                 "starten und mit dem Claude-Konto anmelden.")
        if "limit" in klein:
            zeit = re.search(r"\|(\d{9,})", meldung)
            if zeit:
                uhr = datetime.datetime.fromtimestamp(int(zeit.group(1))).strftime("%H:%M")
                raise ProviderFehler("limit", "Das Claude-Limit ist erreicht. Ab etwa %s Uhr geht es weiter." % uhr)
            raise ProviderFehler("limit", "Das Claude-Limit ist erreicht. " + meldung[:200])
        raise ProviderFehler("fehler", "Claude Code meldet: " + meldung[:300])


class ProviderManager:
    def __init__(self, konfig, protokoll):
        self.log = protokoll
        self.claude = ClaudeCode(konfig.daten_ordner, timeout=konfig.provider_timeout, modell=konfig.modell)
        self.anbieter = [self.claude]
        self._status = {a.name: {"name": a.name, "anzeige": a.anzeige, "nutzbar": False,
                                 "hinweis": "wird geprüft …"} for a in self.anbieter}
        self._status_sperre = threading.Lock()
        # Immer nur eine Anfrage gleichzeitig: schont das Abo-Kontingent und den Mac.
        self._eine_anfrage = threading.Semaphore(1)

    def pruefen(self):
        neu = {}
        for anbieter in self.anbieter:
            neu[anbieter.name] = anbieter.pruefen()
            self.log.ereignis("provider_geprueft", provider=anbieter.name,
                              nutzbar=neu[anbieter.name]["nutzbar"], hinweis=neu[anbieter.name]["hinweis"])
        with self._status_sperre:
            self._status = neu
        return neu

    def status(self):
        with self._status_sperre:
            return {name: dict(werte) for name, werte in self._status.items()}

    def fragen(self, text, system, sitzung=None, warten=120):
        if not self.status()[self.claude.name].get("nutzbar"):
            self.pruefen()  # vielleicht inzwischen angemeldet
        zustand = self.status()[self.claude.name]
        if not zustand.get("nutzbar"):
            raise ProviderFehler("kein_provider", "Kein nutzbarer Anbieter: Claude Code – %s." % zustand["hinweis"])
        if not self._eine_anfrage.acquire(timeout=warten):
            raise ProviderFehler("beschaeftigt", "JARVIS bearbeitet gerade eine andere Anfrage. Bitte gleich nochmal.")
        try:
            ergebnis = self.claude.fragen(text, system, sitzung)
        finally:
            self._eine_anfrage.release()
        ergebnis["provider"] = self.claude.name
        return ergebnis
