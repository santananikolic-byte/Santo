# -*- coding: utf-8 -*-
"""Programmieren - JARVIS gibt Programmier-Aufträge an Claude Code, abgeschottet in einem Projektordner.

So ist es abgesichert (die Startoptionen folgen der Dokumentation von Claude Code):

* Jeder Auftrag läuft in Werkstatt/projekte/<name>. Lesen und Schreiben außerhalb ist gesperrt
  (``blockReadsOutsideWorkingDirectories`` / ``blockWritesOutsideWorkingDirectories``), kein Internet
  (WebFetch/WebSearch verboten). Alles, was eine Rückfrage bräuchte, wird abgelehnt (``--permission-mode dontAsk``).
* Ohne Tests: keine Kommandozeile - nur Dateien lesen, anlegen, ändern.
* Mit Tests: Kommandozeile nur in der Sandbox (``sandbox.enabled``): kein Netz, unsandboxed Wiederholungen aus.
  Ist die Sandbox nicht verfügbar, bricht Claude Code ab (``failIfUnavailable``), statt ungeschützt zu laufen.
* Steuerdateien für Claude Code (``.claude/``, ``.mcp.json``, ``CLAUDE.md``) darf ein Auftrag nicht schreiben, und
  Einstellungen aus dem Projektordner werden gar nicht geladen (``--setting-sources user``): Ein Auftrag kann sich so
  keine Rechte für den nächsten Lauf geben. Keine fremden MCP-Dienste (``--strict-mcp-config``).
* Abo, nie API-Schlüssel (Umgebung wie beim Denken bereinigt); ``--bare`` wird nie benutzt (schaltet das Abo ab).
* Vor jedem Auftrag wird das Projekt gesichert (Werkstatt/.papierkorb/projekte) - nichts geht verloren.
* Jeder Auftrag braucht die Freigabe des Nutzers, läuft im Hintergrund und meldet sich am Ende. Notstopp bricht ab.
"""

import atexit
import datetime
import json
import os
import re
import shutil
import signal
import subprocess
import threading
import time

from . import zeit
from .provider import saubere_umgebung

PROJEKTNAME = re.compile(r"^[a-z0-9][a-z0-9_-]{1,39}$")
STEUERDATEIEN = (".claude", ".mcp.json", "CLAUDE.md", "CLAUDE.local.md")
UEBERSPRINGEN = (".git", "node_modules", ".venv", "venv", "__pycache__", ".pytest_cache", ".mypy_cache")
MAX_SICHERUNG = 100 * 1024 * 1024
MAX_SCHRITTE = 40
MAX_AUFTRAG = 8000
# Nebenoptionen, auf die ein Lauf verzichten kann, falls eine neuere Version von Claude Code sie nicht mehr kennt
VERZICHTBAR = ("--max-turns", "--disable-slash-commands", "--no-session-persistence")

RAHMEN = """Du programmierst für JARVIS, den Assistenten eines kleinen Bau- und Reinigungsbetriebs, im aktuellen Ordner \
(dem Projektordner). Regeln:
- Arbeite nur in diesem Ordner. Lies und schreibe nichts außerhalb.
- Kein Internet und keine Installation von Paketen. Am liebsten Python 3.8 ohne Zusatzpakete oder eine einzelne \
HTML-Datei - beides läuft auf jedem Mac ohne Installation.
- Keine Passwörter, Zugangsdaten oder API-Schlüssel in Dateien; wo etwas nötig wäre, ein klar benannter Platzhalter.
- Lösche nichts, was du nicht in diesem Auftrag selbst angelegt hast.
- %(tests)s
- Zum Schluss auf Deutsch und kurz: was gebaut wurde, wie man es startet (Doppelklick oder ein Befehl), was getestet \
ist und was noch fehlt. Erfinde keine Testergebnisse.

AUFTRAG DES NUTZERS:
%(auftrag)s"""
MIT_TESTS = "Schreib Tests und führe sie aus. Die Kommandozeile läuft in einer Sandbox ohne Internet."
OHNE_TESTS = ("Du kannst nichts ausführen (keine Kommandozeile). Prüf deinen Code durch sorgfältiges Lesen und sag "
              "am Ende ehrlich, dass er nicht ausgeführt wurde.")


class ProgrammierFehler(Exception):
    """Fehler, den der Nutzer verstehen soll."""


def _nachkommen(pid):
    """Alle Kind- und Enkelprozesse (z. B. Tests, die Claude Code startet) - über ``ps``, ohne Zusatzpakete."""
    try:
        ausgabe = subprocess.run(["ps", "-A", "-o", "pid=,ppid="], capture_output=True, text=True,  # noqa: S603, S607
                                 timeout=5).stdout
    except (OSError, subprocess.SubprocessError):
        return []
    kinder = {}
    for zeile in ausgabe.splitlines():
        teile = zeile.split()
        if len(teile) == 2 and teile[0].isdigit() and teile[1].isdigit():
            kinder.setdefault(int(teile[1]), []).append(int(teile[0]))
    gefunden, offen = [], [pid]
    while offen and len(gefunden) < 500:
        for kind in kinder.get(offen.pop(), []):
            if kind not in gefunden:
                gefunden.append(kind)
                offen.append(kind)
    return gefunden


def beenden(proc):
    """Beendet Claude Code samt allem, was es gestartet hat. Ohne die Kinder liefe z. B. eine Endlosschleife in einem
    Test nach einem Notstopp weiter."""
    if proc.poll() is not None:
        return
    for pid in reversed(_nachkommen(proc.pid)):
        try:
            os.kill(pid, signal.SIGKILL)
        except OSError:
            pass
    try:
        proc.kill()
    except OSError:
        pass


_LAUFENDE = set()


@atexit.register
def _beim_beenden():
    """Beendet JARVIS, endet auch ein laufender Programmier-Auftrag (sonst arbeitet er unbeaufsichtigt weiter)."""
    for proc in list(_LAUFENDE):
        beenden(proc)


def projekt_pfad(konfig, name):
    """ "Kunden Chatbot" -> ("kunden-chatbot", Werkstatt/projekte/kunden-chatbot). Wirft ProgrammierFehler."""
    name = re.sub(r"\s+", "-", (name or "").strip().lower())
    if not PROJEKTNAME.match(name):
        raise ProgrammierFehler("Projektname: 2 bis 40 Zeichen, nur a-z, 0-9, - und _ (zum Beispiel kunden-chatbot).")
    return name, os.path.join(os.path.realpath(konfig.werkstatt_pfad), "projekte", name)


def befehl(programm, modell, mit_tests, max_schritte=MAX_SCHRITTE, ohne=()):
    """Die Startoptionen für einen Programmier-Lauf - an einer Stelle, damit sie geprüft werden können.

    ``ohne``: Nebenoptionen aus VERZICHTBAR, die diese Version von Claude Code nicht kennt."""
    erlaubt = ["Read", "Edit", "Write", "Glob", "Grep"]
    verboten = ["WebFetch", "WebSearch"]
    for datei in (".claude/**", ".mcp.json", "CLAUDE.md", "CLAUDE.local.md"):
        verboten += ["Edit(%s)" % datei, "Write(%s)" % datei]
    einstellungen = {"permissions": {"blockReadsOutsideWorkingDirectories": True,
                                     "blockWritesOutsideWorkingDirectories": True}}
    if mit_tests:
        erlaubt.append("Bash")
        einstellungen["sandbox"] = {"enabled": True, "failIfUnavailable": True, "allowUnsandboxedCommands": False,
                                    "network": {"allowedDomains": []}}
    else:
        verboten.append("Bash")
    return [programm, "-p", "--output-format", "json", "--model", modell or "opus", "--permission-mode", "dontAsk",
            "--allowedTools", ",".join(erlaubt), "--disallowedTools", ",".join(verboten),
            "--settings", json.dumps(einstellungen), "--setting-sources", "user",
            "--strict-mcp-config", "--mcp-config", json.dumps({"mcpServers": {}})] + [
                teil for name, teile in (("--disable-slash-commands", ["--disable-slash-commands"]),
                                         ("--no-session-persistence", ["--no-session-persistence"]),
                                         ("--max-turns", ["--max-turns", str(max_schritte)]))
                if name not in ohne for teil in teile]


# Bekannte Meldungen von Claude Code, verständlich auf Deutsch (der Originaltext bleibt dahinter stehen)
ERKLAERUNGEN = (
    ("sandbox required but unavailable", "Die Sandbox für Tests ist auf diesem Rechner nicht verfügbar - deshalb ist "
     "Claude Code gar nicht erst gestartet (der Schutz hat gegriffen). Ohne Tests (mit_tests=nein) geht es trotzdem."),
    ("usage limit", "Das Nutzungslimit deines Claude-Abos ist gerade erreicht. Später noch einmal versuchen."),
    ("unknown option", "Diese Version von Claude Code kennt eine Startoption nicht. Bitte im Terminal: claude update"),
    ("not logged in", "Claude Code ist nicht angemeldet. Im Terminal: claude auth login"),
    ("please run /login", "Claude Code ist nicht angemeldet. Im Terminal: claude auth login"),
)


def fehler_erklaeren(text):
    klein = (text or "").lower()
    for muster, erklaerung in ERKLAERUNGEN:
        if muster in klein:
            return "%s (Claude Code: %s)" % (erklaerung, " ".join(text.split())[:300])
    return text


def bestand(ordner):
    """{relativer Pfad: (Größe, Änderungszeit in ms)} - ohne Abhängigkeiten wie node_modules."""
    ergebnis = {}
    for wurzel, unter, dateien in os.walk(ordner):
        unter[:] = [u for u in unter if u not in UEBERSPRINGEN]
        for name in dateien:
            pfad = os.path.join(wurzel, name)
            try:
                st = os.lstat(pfad)
            except OSError:
                continue
            ergebnis[os.path.relpath(pfad, ordner)] = (st.st_size, int(st.st_mtime * 1000))
    return ergebnis


def unterschied(vorher, nachher):
    neu = sorted(set(nachher) - set(vorher))
    weg = sorted(set(vorher) - set(nachher))
    geaendert = sorted(p for p in set(vorher) & set(nachher) if vorher[p] != nachher[p])
    return neu, geaendert, weg


def steuerdateien(ordner):
    return [n for n in STEUERDATEIEN if os.path.lexists(os.path.join(ordner, n))]


def ordner_pruefen(pfad):
    """Der Projektordner selbst darf keine Verknüpfung sein, und keine Verknüpfung darin darf nach außen zeigen -
    sonst schriebe Claude Code über den Umweg doch außerhalb (z. B. in Dokumente)."""
    eltern = os.path.dirname(pfad)
    if os.path.islink(pfad) or os.path.realpath(pfad) != os.path.join(os.path.realpath(eltern), os.path.basename(pfad)):
        raise ProgrammierFehler("Der Projektordner ist eine Verknüpfung - das ist aus Sicherheitsgründen nicht erlaubt.")
    if not os.path.isdir(pfad):
        return
    echt = os.path.realpath(pfad)
    nach_aussen = []
    for wurzel, unter, dateien in os.walk(pfad):
        unter[:] = [u for u in unter if u not in UEBERSPRINGEN]
        for name in unter + dateien:
            voll = os.path.join(wurzel, name)
            if os.path.islink(voll):
                ziel = os.path.realpath(voll)
                if ziel != echt and not ziel.startswith(echt + os.sep):
                    nach_aussen.append(os.path.relpath(voll, pfad))
    if nach_aussen:
        raise ProgrammierFehler("Im Projekt liegen Verknüpfungen nach außerhalb (%s). Bitte erst entfernen."
                                % ", ".join(sorted(nach_aussen)[:5]))


class Programmierer:
    """Ein Programmier-Auftrag zur Zeit, im Hintergrund. Ergebnis als Ereignis im Gespräch und als Mitteilung."""

    def __init__(self, agent):
        self.agent = agent
        self._sperre = threading.Lock()
        self._proc = None
        self._faden = None
        self._abgebrochen = threading.Event()
        self.laufend = None

    @property
    def stand_ordner(self):
        return os.path.join(self.agent.konfig.daten_ordner, "programmieren")

    def beschaeftigt(self):
        return self._faden is not None and self._faden.is_alive()

    def claude_pruefen(self):
        provider = self.agent.provider
        programm = provider.claude.finden()
        zustand = provider.status().get("claude_code", {})
        if programm and not zustand.get("nutzbar"):
            zustand = provider.pruefen().get("claude_code", {})
        if not programm or not zustand.get("nutzbar"):
            raise ProgrammierFehler("Programmieren braucht Claude Code, angemeldet mit deinem Abo: %s"
                                    % (zustand.get("hinweis") or "nicht installiert"))
        return programm

    def _sichern(self, name, pfad):
        if not os.listdir(pfad):
            return None
        groesse = sum(g for g, _ in bestand(pfad).values())
        if groesse > MAX_SICHERUNG:
            return "keine (Projekt größer als 100 MB)"
        ziel = os.path.join(os.path.realpath(self.agent.konfig.werkstatt_pfad), ".papierkorb", "projekte",
                            "%s-%s" % (name, datetime.datetime.now().strftime("%Y%m%d-%H%M%S")))
        shutil.copytree(pfad, ziel, symlinks=True, ignore=shutil.ignore_patterns(*UEBERSPRINGEN))
        return os.path.relpath(ziel, os.path.realpath(self.agent.konfig.werkstatt_pfad))

    def frei_pruefen(self):
        laufend = self.laufend
        if self.beschaeftigt() and laufend:
            raise ProgrammierFehler("Es läuft schon ein Programmier-Auftrag (Projekt %s). Bitte warten, bis er fertig "
                                    "ist, oder abbrechen." % laufend["projekt"])

    def starten(self, ctx, name, auftrag, mit_tests):
        with self._sperre:
            self.frei_pruefen()
            programm = self.claude_pruefen()
            name, pfad = projekt_pfad(self.agent.konfig, name)
            ordner_pruefen(pfad)
            os.makedirs(pfad, exist_ok=True)
            info = {"projekt": name, "pfad": pfad, "start": zeit.jetzt(), "mit_tests": bool(mit_tests),
                    "gespraech": ctx.gespraech, "bereich": ctx.bereich, "sicherung": self._sichern(name, pfad)}
            self.laufend = info
            self._abgebrochen.clear()
            self._faden = threading.Thread(target=self._laufen, args=(info, programm, auftrag), daemon=True,
                                           name="jarvis-programmieren")
            self._faden.start()
        return info

    def abbrechen(self):
        """Beendet einen laufenden Auftrag (Notstopp). Gibt True zurück, wenn einer lief.

        Auch kurz vor dem Start (Prozess noch nicht da) greift der Abbruch: der Lauf prüft die Marke direkt nach dem Start."""
        with self._sperre:
            if self.laufend is None or self.laufend.get("beendet"):
                return False
            self._abgebrochen.set()
            if self._proc is not None:
                beenden(self._proc)
            return True

    def _laufen(self, info, programm, auftrag):
        """Im Hintergrund: Claude Code starten, warten, Ergebnis melden. Was auch passiert - am Ende ist der Platz frei."""
        try:
            ergebnis = self._ausfuehren(info, programm, auftrag)
            self._melden(info, ergebnis)
        except Exception as problem:  # noqa: BLE001 - ein Fehler im Hintergrund darf JARVIS nicht blockieren
            self.agent.log.ereignis("programmieren_fehler", "ERROR", projekt=info["projekt"], fehler=repr(problem)[:300])
        finally:
            with self._sperre:
                self.laufend = None

    def _ausfuehren(self, info, programm, auftrag):
        k = self.agent.konfig
        vorher = bestand(info["pfad"])
        start = time.time()
        ergebnis = {"projekt": info["projekt"], "start": info["start"], "mit_tests": info["mit_tests"],
                    "sicherung": info["sicherung"], "status": "fehler", "text": "", "verweigert": []}
        eingabe = RAHMEN % {"tests": MIT_TESTS if info["mit_tests"] else OHNE_TESTS, "auftrag": auftrag}
        ohne = []
        try:
            for _ in range(len(VERZICHTBAR) + 1):
                rc, ausgabe, fehler, zu_lange = self._prozess(
                    befehl(programm, k.modell_fuer("arbeit"), info["mit_tests"], ohne=ohne), eingabe, info["pfad"],
                    k.programmier_minuten * 60)
                # Kennt eine neuere Version von Claude Code eine Nebenoption nicht mehr: ohne sie noch einmal.
                # Schutzoptionen (Rechte, Einstellungen, Sandbox) fallen nie weg - ohne sie startet kein Lauf.
                text = ((fehler or "") + (ausgabe or "")).lower()
                unbekannt = [f for f in VERZICHTBAR if f not in ohne and "unknown option '%s'" % f in text]
                if rc != 0 and unbekannt and not self._abgebrochen.is_set():
                    ohne += unbekannt
                    continue
                break
            daten = {}
            for zeile in reversed((ausgabe or "").strip().splitlines()):
                try:
                    daten = json.loads(zeile)
                    break
                except ValueError:
                    continue
            if not isinstance(daten, dict):
                daten = {}
            roh = str(daten.get("result") or (fehler or ausgabe or "").strip()[-600:])
            ergebnis["verweigert"] = [str(d.get("tool_name", "?"))[:40] for d in (daten.get("permission_denials") or [])
                                      if isinstance(d, dict)]
            ergebnis["schritte"] = daten.get("num_turns")
            if self._abgebrochen.is_set():
                ergebnis["status"] = "abgebrochen"
            elif zu_lange:
                ergebnis["status"] = "zeitueberschreitung"
            else:
                ergebnis["status"] = "fertig" if rc == 0 and not daten.get("is_error") else "fehler"
            # Erklärt wird nur ein Fehlschlag - ein fertiger Bericht über eine Seite "/login" ist kein Anmeldeproblem
            ergebnis["text"] = (roh if ergebnis["status"] == "fertig" else fehler_erklaeren(roh))[:4000]
        except OSError as problem:
            ergebnis["text"] = "Claude Code ließ sich nicht starten: %s" % problem
        finally:
            with self._sperre:
                info["beendet"] = True
        neu, geaendert, weg = unterschied(vorher, bestand(info["pfad"]))
        ergebnis.update({"neu": neu[:100], "geaendert": geaendert[:100], "entfernt": weg[:100],
                         "dauer_s": int(time.time() - start), "ende": zeit.jetzt()})
        return ergebnis

    def _prozess(self, argumente, eingabe, ordner, timeout):
        """Ein Aufruf von Claude Code. Gibt (Rückgabewert, Ausgabe, Fehlerausgabe, Zeit überschritten?) zurück."""
        proc = subprocess.Popen(argumente, stdin=subprocess.PIPE, stdout=subprocess.PIPE,  # noqa: S603
                                stderr=subprocess.PIPE, text=True, cwd=ordner, env=saubere_umgebung())
        with self._sperre:
            self._proc = proc
            _LAUFENDE.add(proc)
            if self._abgebrochen.is_set():
                beenden(proc)
        zu_lange = False
        try:
            try:
                ausgabe, fehler = proc.communicate(input=eingabe, timeout=timeout)
            except subprocess.TimeoutExpired:
                zu_lange = True
                beenden(proc)
                ausgabe, fehler = proc.communicate()
        finally:
            with self._sperre:
                _LAUFENDE.discard(proc)
                self._proc = None
        return proc.returncode, ausgabe, fehler, zu_lange

    def _melden(self, info, e):
        os.makedirs(self.stand_ordner, mode=0o700, exist_ok=True)
        with open(os.path.join(self.stand_ordner, "%s.json" % info["projekt"]), "w", encoding="utf-8") as f:
            json.dump(e, f, ensure_ascii=False, indent=1)
        text = bericht(e)
        a = self.agent
        if info.get("gespraech"):
            a.speicher.nachricht_hinzufuegen(info["gespraech"], "ereignis", text,
                                             meta={"programmieren": info["projekt"], "status": e["status"]})
        a.speicher.audit_schreiben("programmieren", bereich=info.get("bereich"), details={
            "projekt": info["projekt"], "status": e["status"], "neu": len(e["neu"]), "geaendert": len(e["geaendert"]),
            "entfernt": len(e["entfernt"]), "verweigert": e["verweigert"][:10], "mit_tests": e["mit_tests"]})
        a.log.ereignis("programmieren", projekt=info["projekt"], status=e["status"], dauer_s=e["dauer_s"])
        titel = {"fertig": "fertig", "abgebrochen": "abgebrochen", "zeitueberschreitung": "zu lange"}.get(e["status"], "mit Fehler")
        a.benachrichtigen("JARVIS - Programmieren %s" % titel, "Projekt %s: %d neu, %d geändert" % (
            info["projekt"], len(e["neu"]), len(e["geaendert"])), sprechen=True)

    def stand(self, name=""):
        laufend = self.laufend
        if laufend and (not name or projekt_pfad(self.agent.konfig, name)[0] == laufend["projekt"]):
            return dict(laufend, laeuft=True)
        try:
            namen = [name] if name else sorted((n[:-5] for n in os.listdir(self.stand_ordner) if n.endswith(".json")),
                                               key=lambda n: os.path.getmtime(os.path.join(self.stand_ordner, n + ".json")),
                                               reverse=True)[:1]
            if namen:
                with open(os.path.join(self.stand_ordner, "%s.json" % projekt_pfad(self.agent.konfig, namen[0])[0]),
                          encoding="utf-8") as f:
                    return dict(json.load(f), laeuft=False)
        except (OSError, ValueError):
            pass
        return None


def bericht(e):
    """Der Bericht nach einem Lauf - nur Belegtes: Status, Dateien, Abgelehntes, die Zusammenfassung von Claude Code."""
    kopf = {"fertig": "Programmier-Auftrag fertig", "abgebrochen": "Programmier-Auftrag ABGEBROCHEN",
            "zeitueberschreitung": "Programmier-Auftrag nach Zeitlimit beendet"}.get(e["status"], "Programmier-Auftrag mit FEHLER beendet")
    zeilen = ["%s (Projekt %s, %d s, %s)." % (kopf, e["projekt"], e.get("dauer_s", 0), "mit Tests in der Sandbox"
                                             if e["mit_tests"] else "ohne Ausführen")]
    for wort, liste in (("Neu", e["neu"]), ("Geändert", e["geaendert"]), ("Entfernt", e["entfernt"])):
        if liste:
            zeilen.append("%s: %s%s" % (wort, ", ".join(liste[:15]), " …" if len(liste) > 15 else ""))
    if not (e["neu"] or e["geaendert"] or e["entfernt"]):
        zeilen.append("Keine Datei verändert.")
    if e["verweigert"]:
        zeilen.append("Abgelehnte Zugriffe (Schutz hat gegriffen): %s" % ", ".join(sorted(set(e["verweigert"]))[:10]))
    if e.get("sicherung"):
        zeilen.append("Sicherung vorher: %s" % e["sicherung"])
    if e.get("text"):
        zeilen.append("Bericht von Claude Code: %s" % e["text"][:1500])
    zeilen.append("Die Dateien liegen in Werkstatt/projekte/%s." % e["projekt"])
    return "\n".join(zeilen)
