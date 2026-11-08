# -*- coding: utf-8 -*-
"""Programmieren - JARVIS gibt Programmier-Aufträge an Claude Code, abgeschottet in einem Projektordner.

So ist es abgesichert (die Startoptionen folgen der Dokumentation von Claude Code):

* Jeder Auftrag läuft in Werkstatt/projekte/<name>. Lesen und Schreiben außerhalb ist gesperrt
  (``blockReadsOutsideWorkingDirectories`` / ``blockWritesOutsideWorkingDirectories``), kein Internet
  (WebFetch/WebSearch verboten). Alles, was eine Rückfrage bräuchte, wird abgelehnt (``--permission-mode dontAsk``).
* Ohne Tests: keine Kommandozeile - nur Dateien lesen, anlegen, ändern.
* Mit Tests: Kommandozeile nur in der Sandbox (``sandbox.enabled``): kein Netz, unsandboxed Wiederholungen aus.
  Ist die Sandbox nicht verfügbar, bricht Claude Code ab (``failIfUnavailable``), statt ungeschützt zu laufen.
* Keine fremden Einstellungen: ``--setting-sources ""`` lädt weder Einstellungen (auch nicht die eigenen des Nutzers
  mit Hooks, Plugins oder erweiterten Rechten) noch eine ``CLAUDE.md`` - mit echtem Claude Code geprüft. Steuerdateien
  (``.claude/``, ``.mcp.json``, ``CLAUDE.md``) darf ein Auftrag zudem nicht schreiben: Er kann sich so keine Rechte für
  den nächsten Lauf geben. Keine fremden MCP-Dienste (``--strict-mcp-config``).
* Abo, nie API-Schlüssel. Claude Code bekommt nur die nötigsten Umgebungsvariablen (Positivliste) - keine
  Zugangsschlüssel anderer Programme, die ein Test sonst auslesen könnte. ``--bare`` wird nie benutzt (schaltet das
  Abo ab).
* Claude Code läuft in einer eigenen Prozessgruppe: Abbrechen, Notstopp, Zeitlimit und das Beenden von JARVIS beenden
  alles, was der Auftrag gestartet hat - auch Programme, die Claude Code selbst überleben.
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
import stat
import subprocess
import threading
import time

from . import zeit

PROJEKTNAME = re.compile(r"^[a-z0-9][a-z0-9_-]{1,39}$")
STEUERDATEIEN = (".claude", ".mcp.json", "CLAUDE.md", "CLAUDE.local.md")
UEBERSPRINGEN = (".git", "node_modules", ".venv", "venv", "__pycache__", ".pytest_cache", ".mypy_cache")
MAX_SICHERUNG = 100 * 1024 * 1024
MAX_SCHRITTE = 40
MAX_AUFTRAG = 8000
# Nebenoptionen, auf die ein Lauf verzichten kann, falls eine neuere Version von Claude Code sie nicht mehr kennt
VERZICHTBAR = ("--max-turns", "--disable-slash-commands", "--no-session-persistence")
LESEN_WARTEN = 10  # Sekunden, die nach dem Ende von Claude Code höchstens noch auf offene Ausgaben gewartet wird

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
    """Beendet Claude Code samt allem, was es gestartet hat - auch dann, wenn Claude Code selbst schon beendet ist, ein
    Kind (z. B. ein Testserver) aber weiterläuft und die Ausgabe offen hält. Ohne das liefe etwa eine Endlosschleife in
    einem Test nach einem Notstopp weiter. Claude Code läuft dafür in einer eigenen Prozessgruppe."""
    nachkommen = _nachkommen(proc.pid) if proc.poll() is None else []
    try:
        os.killpg(proc.pid, signal.SIGKILL)  # die ganze Gruppe - nie die von JARVIS (eigene Sitzung beim Start)
    except (OSError, AttributeError):
        pass
    for pid in reversed(nachkommen):  # wer sich eine eigene Gruppe aufgemacht hat
        try:
            os.kill(pid, signal.SIGKILL)
        except OSError:
            pass
    if proc.poll() is None:
        try:
            proc.kill()
        except OSError:
            pass


def _lesen(rohr, ziel):
    """Liest eine Ausgabe bis zum Ende (eigener Faden - so blockiert ein offen gehaltenes Rohr nie den Lauf) und
    schließt sie danach selbst, auch wenn der Lauf längst nicht mehr auf ihn wartet."""
    try:
        while True:
            stueck = rohr.read(65536)
            if not stueck:
                return
            ziel.append(stueck)
    except (OSError, ValueError):
        return
    finally:
        try:
            rohr.close()
        except (OSError, ValueError):
            pass


# Nur diese Umgebungsvariablen bekommt Claude Code beim Programmieren. Alles andere (z. B. GITHUB_TOKEN oder
# Zugangsdaten anderer Programme) könnte ein Test sonst auslesen. FAKE_* gibt es nur für die Ersatzprogramme der Tests.
UMGEBUNG_ERLAUBT = ("PATH", "HOME", "USER", "LOGNAME", "SHELL", "TMPDIR", "TERM", "TZ", "LANG",
                    "HTTPS_PROXY", "HTTP_PROXY", "NO_PROXY", "ALL_PROXY", "https_proxy", "http_proxy", "no_proxy",
                    "all_proxy", "NODE_EXTRA_CA_CERTS", "SSL_CERT_FILE", "SSL_CERT_DIR", "CLAUDE_CONFIG_DIR")


def umgebung(mit_tests):
    """Positivliste. Die Abo-Anmeldung per Umgebungsvariable (claude setup-token) nur ohne Kommandozeile - mit Tests
    könnte ein Programm sie sonst lesen. Die übliche Anmeldung (claude auth login) liegt ohnehin im Schlüsselbund."""
    erlaubt = UMGEBUNG_ERLAUBT + (() if mit_tests else ("CLAUDE_CODE_OAUTH_TOKEN",))
    return {k: v for k, v in os.environ.items() if k in erlaubt or k.startswith(("LC_", "FAKE_"))}


# Lesen gesperrt - auch für Programme, die ein Auftrag mit Tests startet (Sandbox-Regeln laut Dokumentation von
# Claude Code, auf dem Mac nicht nachgeprüft). Ausgelassen wird, was den Projektordner selbst enthält.
GESPERRT_LESEN = ("~/.jarvis", "~/.ssh", "~/.aws", "~/.gnupg", "~/.config", "~/.claude", "~/Library", "~/Documents",
                  "~/Desktop", "~/Downloads", "~/Pictures", "~/Movies", "~/Music")


def lesesperren(projekt=None):
    heim = os.path.realpath(os.path.expanduser("~"))
    echt = os.path.realpath(projekt) if projekt else ""
    regeln = []
    for ort in GESPERRT_LESEN:
        voll = os.path.join(heim, ort[2:])
        if echt and (echt == voll or echt.startswith(voll + os.sep)):
            continue
        regeln.append("Read(%s/**)" % ort)
    return regeln


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


def befehl(programm, modell, mit_tests, max_schritte=MAX_SCHRITTE, ohne=(), projekt=None):
    """Die Startoptionen für einen Programmier-Lauf - an einer Stelle, damit sie geprüft werden können.

    ``ohne``: Nebenoptionen aus VERZICHTBAR, die diese Version von Claude Code nicht kennt."""
    erlaubt = ["Read", "Edit", "Write", "Glob", "Grep"]
    verboten = ["WebFetch", "WebSearch"]
    for datei in (".claude/**", ".mcp.json", "CLAUDE.md", "CLAUDE.local.md"):
        verboten += ["Edit(%s)" % datei, "Write(%s)" % datei]
    verboten += lesesperren(projekt)
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
            "--settings", json.dumps(einstellungen), "--setting-sources", "",
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
    """Der Projektordner selbst darf keine Verknüpfung sein, und nichts darin darf nach außen zeigen - weder eine
    Verknüpfung noch eine harte Verknüpfung (zweiter Name einer Datei von außerhalb). Sonst läse oder schriebe Claude
    Code über den Umweg doch außerhalb (z. B. in Dokumente). Geprüft wird alles, auch .git und node_modules."""
    eltern = os.path.dirname(pfad)
    if os.path.islink(pfad) or os.path.realpath(pfad) != os.path.join(os.path.realpath(eltern), os.path.basename(pfad)):
        raise ProgrammierFehler("Der Projektordner ist eine Verknüpfung - das ist aus Sicherheitsgründen nicht erlaubt.")
    if not os.path.isdir(pfad):
        return
    echt = os.path.realpath(pfad)
    nach_aussen, mehrfach = [], []
    for wurzel, unter, dateien in os.walk(pfad):
        for name in unter + dateien:
            voll = os.path.join(wurzel, name)
            try:
                st = os.lstat(voll)
            except OSError:
                continue
            if stat.S_ISLNK(st.st_mode):
                ziel = os.path.realpath(voll)
                if ziel != echt and not ziel.startswith(echt + os.sep):
                    nach_aussen.append(os.path.relpath(voll, pfad))
            elif stat.S_ISREG(st.st_mode) and st.st_nlink > 1:
                mehrfach.append(os.path.relpath(voll, pfad))
    if nach_aussen:
        raise ProgrammierFehler("Im Projekt liegen Verknüpfungen nach außerhalb (%s). Bitte erst entfernen."
                                % ", ".join(sorted(nach_aussen)[:5]))
    if mehrfach:
        raise ProgrammierFehler("Im Projekt liegen Dateien, die noch an anderer Stelle stehen (harte Verknüpfung: %s). "
                                "Bitte erst entfernen oder durch eine Kopie ersetzen." % ", ".join(sorted(mehrfach)[:5]))


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
        return self.laufend is not None or (self._faden is not None and self._faden.is_alive())

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
        if laufend is not None:
            raise ProgrammierFehler("Es läuft schon ein Programmier-Auftrag (Projekt %s). Bitte warten, bis er fertig "
                                    "ist, oder abbrechen." % laufend["projekt"])

    def _notstopp_pruefen(self):
        if self.agent.gesperrt.is_set():
            raise ProgrammierFehler("Notstopp ist aktiv - es startet kein Programmier-Auftrag.")

    def starten(self, ctx, name, auftrag, mit_tests):
        """Platz reservieren (unter der Sperre), dann prüfen und sichern (ohne Sperre - ein Notstopp muss nicht auf das
        Kopieren warten), dann unter der Sperre starten, nur wenn inzwischen weder Abbruch noch Notstopp kam."""
        name, pfad = projekt_pfad(self.agent.konfig, name)
        with self._sperre:
            self._notstopp_pruefen()
            self.frei_pruefen()
            info = {"projekt": name, "pfad": pfad, "start": zeit.jetzt(), "mit_tests": bool(mit_tests),
                    "gespraech": ctx.gespraech, "bereich": ctx.bereich, "sicherung": None}
            self.laufend = info
            self._abgebrochen.clear()
        try:
            programm = self.claude_pruefen()
            ordner_pruefen(pfad)
            os.makedirs(pfad, exist_ok=True)
            info["sicherung"] = self._sichern(name, pfad)
            with self._sperre:
                self._notstopp_pruefen()
                if self._abgebrochen.is_set():
                    raise ProgrammierFehler("Abgebrochen, bevor der Auftrag begann. Es wurde nichts verändert.")
                self._faden = threading.Thread(target=self._laufen, args=(info, programm, auftrag), daemon=True,
                                               name="jarvis-programmieren")
                self._faden.start()
        except BaseException:
            with self._sperre:
                if self.laufend is info:
                    self.laufend = None
            raise
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

    def stoppen(self, warten=15):
        """Beim Beenden von JARVIS: laufenden Auftrag abbrechen und kurz warten, bis seine Meldung geschrieben ist."""
        if self.abbrechen():
            faden = self._faden
            if faden is not None:
                faden.join(warten)

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
                    befehl(programm, k.modell_fuer("arbeit"), info["mit_tests"], ohne=ohne, projekt=info["pfad"]),
                    eingabe, info["pfad"], k.programmier_minuten * 60, umgebung(info["mit_tests"]))
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

    def _prozess(self, argumente, eingabe, ordner, timeout, env):
        """Ein Aufruf von Claude Code. Gibt (Rückgabewert, Ausgabe, Fehlerausgabe, Zeit überschritten?) zurück.

        Gewartet wird auf das Ende von Claude Code, nicht auf das Ende der Ausgabe: Hält ein übrig gebliebenes Kind die
        Ausgabe offen, wird es beendet; wer sich auch dem entzieht, wird nach 10 s nicht weiter abgewartet."""
        proc = subprocess.Popen(argumente, stdin=subprocess.PIPE, stdout=subprocess.PIPE,  # noqa: S603
                                stderr=subprocess.PIPE, text=True, cwd=ordner, env=env, start_new_session=True)
        with self._sperre:
            self._proc = proc
            _LAUFENDE.add(proc)
            if self._abgebrochen.is_set() or self.agent.gesperrt.is_set():
                self._abgebrochen.set()
                beenden(proc)
        ausgabe, fehler = [], []
        leser = [threading.Thread(target=_lesen, args=(proc.stdout, ausgabe), daemon=True, name="jarvis-prog-aus"),
                 threading.Thread(target=_lesen, args=(proc.stderr, fehler), daemon=True, name="jarvis-prog-fehler")]
        for faden in leser:
            faden.start()
        zu_lange = False
        try:
            try:
                proc.stdin.write(eingabe)
                proc.stdin.close()
            except (OSError, ValueError):
                pass  # Claude Code hat schon aufgehört (z. B. unbekannte Option) - die Meldung steht in der Ausgabe
            try:
                proc.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                zu_lange = True
            beenden(proc)  # auch, was Claude Code überlebt hat
            for faden in leser:
                faden.join(LESEN_WARTEN)  # die Fäden schließen ihre Rohre selbst, sobald sie fertig sind
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                pass
        finally:
            with self._sperre:
                _LAUFENDE.discard(proc)
                self._proc = None
        return proc.returncode, "".join(ausgabe), "".join(fehler), zu_lange

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
