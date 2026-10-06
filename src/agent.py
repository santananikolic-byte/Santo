#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Der Kern - Claude denkt, die Werkzeuge handeln.

Ablauf pro Eingabe:

1. Erinnerung nachschlagen und dem Systemprompt beilegen
2. Anfrage an die Claude-Schnittstelle mit dem gesamten Werkzeugkatalog
   (eigene Werkzeuge **plus** alle von MCP-Servern)
3. Fordert Claude ein Werkzeug an: ausführen, Ergebnis zurückgeben, wiederholen
4. Höchstens acht Runden, dann Abbruch mit klarer Meldung
"""

import json
import socket
import threading
import time
import urllib.error
import urllib.request
from datetime import datetime

import config
from modules.memory import heute_datum
from modules.recall import Recall
from modules.router import (Gedankenlog, claude_kosten, gehirn_waehlen,
                            gemini_fragen)
from modules.tools import Werkzeuge

API_URL = "https://api.anthropic.com/v1/messages"
API_VERSION = "2023-06-01"
# Lehnt das Modell eine Frage aus Sicherheitsgründen ab, springt ein anderes Claude-Modell
# ein (serverseitig, "default" wählt passend zum Grund). Nur diese Modelle kennen das.
AUSWEICH_BETA = "server-side-fallback-2026-07-01"
AUSWEICH_MODELLE = ("claude-opus-5-5", "claude-opus-5", "claude-fable-5-1", "claude-fable-5",
                    "claude-sonnet-5-5")
# Ältere kleine Modelle kennen keine Denktiefe.
OHNE_EFFORT = ("claude-haiku", "claude-sonnet-4-5", "claude-3")


def anfrage_ergaenzen(koerper: dict, effort: str = "", zwischenspeicher: bool = True) -> dict:
    """Ergänzt eine Anfrage um Denktiefe, Ausweichmodell und Zwischenspeicher.

    Der Zwischenspeicher (Prompt-Caching) spart in den Werkzeugrunden einer
    Frage den größten Teil der Eingabekosten: Die zweite Runde liest Werkzeuge,
    Systemprompt und Gespräch für einen Bruchteil. Die Werkzeugliste hat einen
    eigenen Haltepunkt und hält über Fragen hinweg. Einzelanfragen
    (``zwischenspeicher=False``) werden nie wieder gelesen - dort wäre das
    Speichern nur ein Aufschlag.
    """
    modell = str(koerper.get("model") or "")
    effort = effort or config.CLAUDE_EFFORT
    if effort and not modell.startswith(OHNE_EFFORT):
        koerper.setdefault("output_config", {})["effort"] = effort
    if modell in AUSWEICH_MODELLE:
        koerper["fallbacks"] = "default"
    if zwischenspeicher:
        koerper.setdefault("cache_control", {"type": "ephemeral"})
    werkzeuge = koerper.get("tools")
    if werkzeuge:
        # Die Werkzeugliste ändert sich nie - ein eigener Haltepunkt hält sie über Fragen hinweg.
        koerper["tools"] = list(werkzeuge[:-1]) + [dict(werkzeuge[-1], cache_control={"type": "ephemeral"})]
    return koerper


def ausweichen_bereinigen(inhalt: list) -> list:
    """Nach einem Wechsel des Modells mitten in der Antwort: was davor lag, geht nicht zurück.

    Denkblöcke und Werkzeugaufrufe des ablehnenden Modells vor dem letzten
    Wechselzeichen bleiben weg; Text und alles danach bleiben.
    """
    inhalt = list(inhalt or [])
    marken = [i for i, b in enumerate(inhalt) if isinstance(b, dict) and b.get("type") == "fallback"]
    if not marken:
        return inhalt
    grenze = marken[-1]
    return [b for i, b in enumerate(inhalt)
            if i > grenze or (b.get("type") not in ("thinking", "redacted_thinking", "tool_use", "fallback"))]


def denkspuren_entfernen(verlauf: list) -> list:
    """Entfernt Denkblöcke aus früheren Runden.

    Denkblöcke gehören zu genau dem Gespräch, in dem sie entstanden. Weil alte
    Runden vorn wegfallen und sich der Systemprompt mit dem Tag ändert, würde
    die Schnittstelle alte Denkblöcke ablehnen. Text, Werkzeugaufrufe und
    Ergebnisse bleiben.
    """
    neu = []
    for nachricht in verlauf:
        inhalt = nachricht.get("content")
        if nachricht.get("role") == "assistant" and isinstance(inhalt, list):
            inhalt = [b for b in inhalt if not (isinstance(b, dict) and b.get("type") in
                                                 ("thinking", "redacted_thinking", "fallback"))]
            if not inhalt:
                continue
            nachricht = dict(nachricht, content=inhalt)
        neu.append(nachricht)
    return neu


DENKTIEFEN = ("low", "medium", "high", "xhigh", "max")


def denktiefe() -> str:
    """Die eingestellte Denktiefe - ein Tippfehler in der Konfiguration wird zu "high"."""
    wert = str(config.CLAUDE_EFFORT or "").strip().lower()
    return wert if wert in DENKTIEFEN else "high"


def nutzung_addieren(summe: dict, nachricht: dict) -> None:
    """Zählt die Tokens einer Antwort zur Summe (ein, aus, gelesen, geschrieben)."""
    nutzung = (nachricht or {}).get("usage") or {}
    for schluessel, feld in (("ein", "input_tokens"), ("aus", "output_tokens"),
                             ("gelesen", "cache_read_input_tokens"),
                             ("geschrieben", "cache_creation_input_tokens")):
        summe[schluessel] = summe.get(schluessel, 0) + int(nutzung.get(feld, 0) or 0)


def summe_kosten(summe: dict) -> float:
    return claude_kosten(summe.get("ein", 0), summe.get("aus", 0),
                         summe.get("gelesen", 0), summe.get("geschrieben", 0))


MAX_RUNDEN = 8
MAX_VERLAUF = 24
# Schneidet die Grenze eine Antwort ab, versucht er es einmal mit weniger Nachdenken.
WENIGER_DENKEN = {"max": "medium", "xhigh": "medium", "high": "medium", "medium": "low"}
ABGESCHNITTEN = ("Meine Antwort ist zu lang geworden und wurde abgeschnitten. Ich habe "
                 "nichts davon ausgeführt. Teil die Aufgabe bitte in kleinere Schritte.")

WOCHENTAGE_DE = ["Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag",
                 "Samstag", "Sonntag"]
MONATE_DE = ["Januar", "Februar", "März", "April", "Mai", "Juni", "Juli",
             "August", "September", "Oktober", "November", "Dezember"]

SYSTEMPROMPT = """Du bist Jarvis, der persönliche Assistent von {name}.
{name} führt einen Betrieb als Einzelunternehmer. Branche: {branche}.

So sprichst du:
- Kurz und gesprochen. Deine Antworten werden vorgelesen — keine
  Aufzählungszeichen, keine Sternchen, keine Überschriften. Ganze Sätze.
- Zwei bis vier Sätze reichen fast immer.
- Du duzt ihn. Sachlich und ruhig, nicht kumpelhaft.

So arbeitest du:
- Du nutzt deine Werkzeuge selbstständig, ohne zu fragen, wenn die Absicht klar ist.
- Du hast ein Team: Buchhalter, Verkäufer, Terminplaner, Postbearbeiter,
  Kundenberater, Rechercheur, Controller und Programmierer. Für eine Aufgabe,
  die klar zu einem von ihnen gehört und mehrere Schritte braucht, beauftragst
  du ihn mit mitarbeiter_beauftragen und gibst danach seinen Bericht weiter.
  Kleine Handgriffe machst du selbst - dafür brauchst du niemanden.
- Erzählt er von einem Kundentermin, bewertest du ihn und hältst ihn fest —
  ungefragt. Ehrlich, nicht schmeichelnd: ein nettes Gespräch ohne Abschluss
  war kein gutes Gespräch, und das sagst du auch.
- Nennt er nebenbei etwas Wichtiges über einen Kunden oder eine Entscheidung,
  merkst du es dir.
- Bei Geld bist du genau. Beträge schätzt du nie. Ist etwas unklar, fragst du nach.
- Du hast ein Gedächtnis über frühere Tage. Nutze es beiläufig, ohne es
  anzukündigen. Sag nie "laut meinem Gedächtnis".
- Ging etwas schief, sagst du es. Du erfindest keine Ergebnisse.
- Steht vor seiner Nachricht ein Abschnitt <erinnerung>, sind das Treffer aus
  deinem Gedächtnis zu dieser Frage. Er hat sie nicht gesagt - nutze sie still.

Die Buchhaltung führst du vor — die fachliche Prüfung macht sein Steuerberater.

Heute ist {wochentag}, der {datum}.

{gedaechtnis}"""


def datum_deutsch(zeitpunkt: datetime = None) -> tuple:
    """Gibt Wochentag und ausgeschriebenes Datum auf Deutsch zurück."""
    zeitpunkt = zeitpunkt or datetime.now()
    return (WOCHENTAGE_DE[zeitpunkt.weekday()],
            "%d. %s %d" % (zeitpunkt.day, MONATE_DE[zeitpunkt.month - 1], zeitpunkt.year))


def json_aus_text(rohtext: str):
    """Holt ein JSON-Objekt aus einer Antwort, auch wenn Code-Zäune drumherum stehen."""
    if not rohtext:
        return None
    text = str(rohtext).strip()
    if text.startswith("```"):
        text = text.split("```")[1] if "```" in text[3:] else text[3:]
        if text.lstrip().lower().startswith("json"):
            text = text.lstrip()[4:]
    text = text.strip().strip("`").strip()
    try:
        return json.loads(text)
    except ValueError:
        pass
    # Notfalls das äußerste geschweifte Klammerpaar herausschneiden.
    beginn, ende = text.find("{"), text.rfind("}")
    if beginn >= 0 and ende > beginn:
        try:
            return json.loads(text[beginn:ende + 1])
        except ValueError:
            return None
    return None


class JarvisAgent:
    """Die Denkschleife: fragt Claude, führt Werkzeuge aus, antwortet gesprochen."""

    def __init__(self, db_pfad: str = None, stimme=None):
        self.tools = Werkzeuge(agent=None, db_pfad=db_pfad)
        self.tools.agent_setzen(self)
        self.memory = self.tools.memory
        self.recall = self.tools.recall
        self.stimme = stimme
        if stimme is not None:
            self.tools.stimme_setzen(stimme)
        self.verlauf = []
        # Stimme, Telegram, Web und Zeitplan teilen sich den Verlauf - einer nach dem anderen.
        self._denk_sperre = threading.RLock()
        self.letzter_fehler = ""
        self.gedankenlog = Gedankenlog()
        self.letztes_gehirn = ""
        # Was Jarvis gerade tut - die Anzeige (Gehirn, Zentrale) liest das mit.
        self.status = {"zustand": "bereit", "seit": time.time(), "satz": ""}

    # -- Grundlagen ---------------------------------------------------------

    def einsatzbereit(self) -> bool:
        """Ist ein Anthropic-Schlüssel hinterlegt?"""
        return bool(config.ANTHROPIC_API_KEY)

    def stimme_setzen(self, stimme):
        """Hängt die Sprachausgabe ein."""
        self.stimme = stimme
        self.tools.stimme_setzen(stimme)

    def dienste_starten(self) -> dict:
        """Startet die eingeschalteten MCP-Dienste."""
        return self.tools.mcp.starten()

    def systemprompt(self, frage: str = "") -> str:
        """Baut den Systemprompt samt passendem Gedächtnisauszug."""
        wochentag, datum = datum_deutsch()
        try:
            gedaechtnis = self.recall.gedaechtnis_block(frage)
        except Exception as fehler:
            gedaechtnis = ""
            print("[agent] Gedächtnis nicht lesbar: %s" % fehler)
        persoenlich = ""
        if config.JARVIS_PROFIL:
            persoenlich += "Das solltest du über %s wissen: %s\n" % (
                config.NUTZER_NAME, config.JARVIS_PROFIL)
        if config.JARVIS_STIL:
            persoenlich += "So möchte %s, dass du klingst: %s\n" % (
                config.NUTZER_NAME, config.JARVIS_STIL)
        return SYSTEMPROMPT.format(
            name=config.NUTZER_NAME, branche=config.BRANCHE, wochentag=wochentag,
            datum=datum, gedaechtnis=(persoenlich + "\n" if persoenlich else "") + gedaechtnis)

    # -- Schnittstelle ------------------------------------------------------

    def _anfrage(self, koerper: dict, timeout: int = 600) -> dict:
        """Schickt eine Anfrage an die Claude-Schnittstelle.

        Fehler kommen auf Deutsch zurück und benennen den nächsten Schritt.
        Läuft die Wartezeit ab, ist die Anfrage schon angekommen und wird
        berechnet - dann wird nicht noch einmal geschickt.
        """
        if not self.einsatzbereit():
            return {"ok": False,
                    "fehler": "Es ist kein Anthropic-Schlüssel hinterlegt. Starte die "
                              "Einrichtung mit: python3 jarvis.py einrichten"}
        daten = json.dumps(koerper).encode("utf-8")
        kopf = {
            "x-api-key": config.ANTHROPIC_API_KEY,
            "anthropic-version": API_VERSION,
            "content-type": "application/json",
        }
        if koerper.get("fallbacks"):
            kopf["anthropic-beta"] = AUSWEICH_BETA
        anfrage = urllib.request.Request(API_URL, data=daten, method="POST", headers=kopf)
        for versuch in range(3):
            try:
                with urllib.request.urlopen(anfrage, timeout=timeout) as antwort:
                    return {"ok": True,
                            "daten": json.loads(antwort.read().decode("utf-8"))}
            except urllib.error.HTTPError as fehler:
                try:
                    inhalt = fehler.read().decode("utf-8")
                    meldung = (json.loads(inhalt).get("error") or {}).get("message", inhalt)
                except (ValueError, OSError):
                    meldung = str(fehler)
                if fehler.code == 401:
                    return {"ok": False,
                            "fehler": "Der Schlüssel wird abgelehnt - bitte neu kopieren "
                                      "und die Einrichtung noch einmal starten."}
                if fehler.code == 400 and "credit" in meldung.lower():
                    return {"ok": False,
                            "fehler": "Auf dem Anthropic-Konto ist kein Guthaben mehr. "
                                      "Bitte unter console.anthropic.com aufladen."}
                if fehler.code in (429, 529) and versuch < 2:
                    time.sleep(3 * (versuch + 1))
                    continue
                if fehler.code == 429:
                    return {"ok": False,
                            "fehler": "Zu viele Anfragen in kurzer Zeit. Bitte in einer "
                                      "Minute noch einmal."}
                return {"ok": False,
                        "fehler": "Claude meldet einen Fehler (%d): %s"
                                  % (fehler.code, meldung[:300])}
            except socket.timeout:
                # Die Anfrage ist angekommen und Claude arbeitet noch - nicht doppelt bezahlen.
                return {"ok": False,
                        "fehler": "Claude hat länger als %d Sekunden gebraucht. Teil die "
                                  "Aufgabe bitte in kleinere Schritte." % timeout}
            except (urllib.error.URLError, OSError) as fehler:
                if versuch < 2:
                    time.sleep(2 * (versuch + 1))
                    continue
                return {"ok": False,
                        "fehler": "Keine Verbindung zu Claude: %s. Ist das Internet da?"
                                  % fehler}
            except ValueError as fehler:
                return {"ok": False, "fehler": "Die Antwort war unlesbar: %s" % fehler}
        return {"ok": False, "fehler": "Claude hat nicht geantwortet."}

    def _claude_runde(self, koerper: dict, summe: dict, effort: str = "",
                      zwischenspeicher: bool = True) -> dict:
        """Eine Anfrage; schneidet die Grenze sie ab, einmal mit weniger Nachdenken.

        Das Denken zählt zu den Tokens. Reicht die Grenze nicht, war es meist
        zu viel Denken - ein zweiter Versuch eine Stufe flacher passt dann.
        Die Tokens beider Versuche landen in ``summe``.
        """
        effort = effort or denktiefe()
        modell = str(koerper.get("model") or "")
        for versuch in range(2):
            antwort = self._anfrage(anfrage_ergaenzen(dict(koerper), effort, zwischenspeicher))
            if not antwort.get("ok"):
                return antwort
            nutzung_addieren(summe, antwort["daten"])
            weniger = WENIGER_DENKEN.get(effort)
            if antwort["daten"].get("stop_reason") != "max_tokens" or versuch or not weniger \
                    or modell.startswith(OHNE_EFFORT):
                return antwort
            print("[agent] Antwort abgeschnitten - noch einmal mit Denktiefe %s" % weniger)
            effort = weniger
        return antwort

    @staticmethod
    def _inhalt_bauen(auftrag: str, bild_base64: str = "", bild_typ: str = "image/jpeg"):
        """Baut den Inhaltsblock einer Nachricht, wahlweise mit Bild."""
        if not bild_base64:
            return auftrag
        return [
            {"type": "image", "source": {"type": "base64", "media_type": bild_typ,
                                         "data": bild_base64}},
            {"type": "text", "text": auftrag},
        ]

    def text_anfrage(self, auftrag: str, bild_base64: str = "",
                     bild_typ: str = "image/jpeg", max_tokens: int = 8000) -> dict:
        """Eine einzelne Anfrage ohne Werkzeuge - gibt reinen Text zurück.

        Zählt wie jede Claude-Runde zum Monatslimit und landet im Gedankenlog.
        """
        if self.gedankenlog.limit_erreicht():
            return {"ok": False, "fehler": self._limit_meldung()}
        beginn = time.time()
        summe = {}
        antwort = self._claude_runde({
            "model": config.CLAUDE_MODEL,
            "max_tokens": max(int(max_tokens or 0), 8000),
            "messages": [{"role": "user",
                          "content": self._inhalt_bauen(auftrag, bild_base64, bild_typ)}],
        }, summe, effort="medium", zwischenspeicher=False)
        if summe:
            self.gedankenlog.eintragen(auftrag, "claude", "Einzelauftrag", time.time() - beginn,
                                       summe.get("ein", 0), summe.get("aus", 0), summe_kosten(summe))
        if not antwort.get("ok"):
            return antwort
        if antwort["daten"].get("stop_reason") == "refusal":
            return {"ok": False, "fehler": "Diesen Auftrag lehnt Claude ab."}
        teile = [block.get("text", "") for block in antwort["daten"].get("content", [])
                 if block.get("type") == "text"]
        text = "\n".join(teile).strip()
        if antwort["daten"].get("stop_reason") == "max_tokens" and not text:
            return {"ok": False, "fehler": "Die Antwort war zu lang und wurde abgeschnitten."}
        return {"ok": True, "text": text}

    def json_anfrage(self, auftrag: str, bild_base64: str = "",
                     bild_typ: str = "image/jpeg", max_tokens: int = 8000) -> dict:
        """Eine Anfrage, deren Antwort als JSON erwartet wird."""
        antwort = self.text_anfrage(auftrag, bild_base64, bild_typ, max_tokens)
        if not antwort.get("ok"):
            return antwort
        daten = json_aus_text(antwort["text"])
        if daten is None:
            return {"ok": False,
                    "fehler": "Die Antwort war kein auswertbares JSON.",
                    "rohtext": antwort["text"][:500]}
        return {"ok": True, "daten": daten}

    @staticmethod
    def _limit_meldung() -> str:
        return ("Das Monatslimit von %.2f Euro für Claude ist erreicht. Das Limit hebst "
                "du mit MONATSLIMIT_EURO in der Konfiguration an." % config.MONATSLIMIT_EURO)

    # -- Verlauf ------------------------------------------------------------

    def _verlauf_kuerzen(self):
        """Kürzt den Verlauf - immer beginnend bei einer Nutzerfrage.

        Ist er länger als 24 Nachrichten, bleibt auf einen Schlag nur die
        jüngere Hälfte. So ändert sich der Anfang selten, und der
        Zwischenspeicher trägt über viele Fragen. Beginnt der Verlauf mit einer
        Antwort oder einem Werkzeugergebnis, weist die Schnittstelle die ganze
        Anfrage ab - deshalb wird vorne bis zur nächsten echten Nutzerfrage
        abgeschnitten.
        """
        if len(self.verlauf) <= MAX_VERLAUF:
            return
        rest = self.verlauf[-(MAX_VERLAUF // 2):]
        while rest and not self._ist_echte_nutzerfrage(rest[0]):
            rest.pop(0)
        if not rest:
            rest = self.verlauf[-1:]
        self.verlauf = rest

    @staticmethod
    def _ist_echte_nutzerfrage(nachricht: dict) -> bool:
        """Ist das eine Nutzernachricht, die nicht bloß ein Werkzeugergebnis ist?"""
        if nachricht.get("role") != "user":
            return False
        inhalt = nachricht.get("content")
        if isinstance(inhalt, str):
            return True
        for block in inhalt or []:
            if isinstance(block, dict) and block.get("type") == "tool_result":
                return False
        return True

    def verlauf_leeren(self):
        """Beginnt ein neues Gespräch."""
        with self._denk_sperre:
            self.verlauf = []

    def _claude_zuvor(self):
        """Was Claude direkt vor der neuen Frage gesagt hat - ``None``, wenn nicht Claude.

        Gemini-Antworten stehen als reiner Text im Verlauf, Claude-Antworten als
        Blöcke. Stand davor ein Werkzeugergebnis, lief gerade eine Aufgabe.
        """
        if len(self.verlauf) < 2:
            return None
        vorige = self.verlauf[-2]
        inhalt = vorige.get("content")
        if not isinstance(inhalt, list):
            return None
        if vorige.get("role") != "assistant":
            return "?"
        return " ".join(b.get("text", "") for b in inhalt
                        if isinstance(b, dict) and b.get("type") == "text").strip()

    # -- Zustand ------------------------------------------------------------

    def zustand_setzen(self, zustand: str, satz: str = ""):
        """bereit, hoert, denkt oder spricht - für die Anzeige."""
        self.status = {"zustand": zustand, "seit": time.time(), "satz": satz}

    # -- Denkschleife -------------------------------------------------------

    def denken(self, eingabe: str, protokollieren: bool = True, anzeigen: bool = True) -> str:
        """Die Hauptschleife, mit Zustand für die Anzeige.

        Hintergrundarbeit (Briefing) läuft mit ``anzeigen=False``: Sie soll der
        Anzeige nicht mitten im Gespräch "bereit" melden. Wer gleichzeitig
        fragt, wartet - der Verlauf verträgt nur einen Schreiber.
        """
        with self._denk_sperre:
            if not anzeigen:
                return self._denken(eingabe, protokollieren)
            self.zustand_setzen("denkt")
            try:
                return self._denken(eingabe, protokollieren)
            finally:
                self.zustand_setzen("bereit")

    def _gemini_antwort(self, eingabe: str, systemtext: str, grund: str,
                        protokollieren: bool):
        """Fragt Gemini und hängt die Antwort an. ``None``, wenn Gemini nicht kann."""
        beginn = time.time()
        gemini = gemini_fragen(eingabe, systemtext, self.verlauf)
        if not gemini.get("ok"):
            return None, gemini.get("fehler", "")
        text = gemini["text"]
        self.verlauf.append({"role": "assistant", "content": text})
        if protokollieren:
            self.memory.verlauf_anhaengen("assistant", text)
        self.gedankenlog.eintragen(eingabe, "gemini", grund, time.time() - beginn,
                                   gemini["tokens_ein"], gemini["tokens_aus"])
        self.letztes_gehirn = "gemini"
        return text, ""

    def _denken(self, eingabe: str, protokollieren: bool = True) -> str:
        """Die Hauptschleife: fragen, Werkzeuge ausführen, antworten."""
        eingabe = (eingabe or "").strip()
        if not eingabe:
            return ""
        if not self.einsatzbereit():
            return ("Es ist kein Anthropic-Schlüssel hinterlegt. Starte einmal die "
                    "Einrichtung, dann kann ich dir antworten.")
        # Ein neuer Gedankengang: Fremdes ist noch nicht gelesen worden.
        self.tools.lauf_beginnen(hintergrund=False)

        # Der Systemprompt bleibt von Frage zu Frage gleich - dann liest der
        # Zwischenspeicher ihn samt Gespräch. Was zur Frage passt, kommt in die
        # Nachricht selbst. Erst nachschlagen, dann die Frage speichern - sonst
        # findet er seine eigene Frage.
        systemtext = self.systemprompt("")
        try:
            treffer = self.recall.treffer_block(eingabe)
        except Exception as fehler:
            treffer = ""
            print("[agent] Gedächtnis nicht lesbar: %s" % fehler)
        inhalt = ("<erinnerung>\n%s\n</erinnerung>\n\n%s" % (treffer, eingabe)
                  if treffer else eingabe)
        if protokollieren:
            self.memory.verlauf_anhaengen("user", eingabe)
        self.verlauf.append({"role": "user", "content": inhalt})
        self._verlauf_kuerzen()
        self.verlauf = denkspuren_entfernen(self.verlauf)
        beginn_runde = len(self.verlauf) - 1  # hier beginnt diese Frage
        katalog = self.tools.katalog()

        gehirn, grund = gehirn_waehlen(eingabe, vorher=self._claude_zuvor())
        ausgewichen = False
        gemini_system = systemtext + ("\n\n" + treffer if treffer else "")
        if gehirn == "gemini":
            text, fehler = self._gemini_antwort(eingabe, gemini_system, grund, protokollieren)
            if text is not None:
                return text
            # Limit oder Ausfall: Claude übernimmt, der Nutzer merkt nichts.
            ausgewichen = True
            grund = "Gemini ausgefallen: %s" % fehler

        if self.gedankenlog.limit_erreicht():
            if config.GEMINI_API_KEY and not ausgewichen:
                text, _ = self._gemini_antwort(eingabe, gemini_system + (
                    "\n\nHINWEIS: Das Claude-Monatslimit ist erreicht. Du hast gerade KEINE "
                    "Werkzeuge. Behaupte nie, etwas erledigt zu haben. Braucht die Bitte "
                    "Werkzeuge, sag, dass das erst wieder geht, wenn das Monatslimit "
                    "(MONATSLIMIT_EURO) angehoben ist."), "Monatslimit erreicht", protokollieren)
                if text is not None:
                    return text
            del self.verlauf[beginn_runde:]  # die unbeantwortete Frage nicht im Verlauf lassen
            self.letzter_fehler = self._limit_meldung()
            return self.letzter_fehler

        beginn = time.time()
        summe = {}

        def _protokoll():
            self.letztes_gehirn = "claude"
            self.gedankenlog.eintragen(
                eingabe, "claude", grund, time.time() - beginn, summe.get("ein", 0),
                summe.get("aus", 0), summe_kosten(summe), ausgewichen)

        for runde in range(MAX_RUNDEN):
            antwort = self._claude_runde({
                "model": config.CLAUDE_MODEL,
                "max_tokens": config.CLAUDE_MAX_TOKENS,
                "system": systemtext,
                "tools": katalog,
                "messages": self.verlauf,
            }, summe)
            if not antwort.get("ok"):
                self.letzter_fehler = antwort.get("fehler", "")
                _protokoll()
                return self.letzter_fehler

            nachricht = antwort["daten"]
            if nachricht.get("stop_reason") == "refusal":
                # Die abgelehnte Frage samt halber Werkzeugrunde nicht wieder mitschicken.
                del self.verlauf[beginn_runde:]
                _protokoll()
                return ("Dabei kann ich nicht helfen. Wenn du es anders meinst, sag es "
                        "mir mit anderen Worten.")
            inhalt = ausweichen_bereinigen(nachricht.get("content", []))
            text = "\n".join(b.get("text", "") for b in inhalt
                             if b.get("type") == "text").strip()
            werkzeugaufrufe = [b for b in inhalt if b.get("type") == "tool_use"]

            if nachricht.get("stop_reason") == "max_tokens":
                # Abgeschnitten: kein halber Werkzeugaufruf wird ausgeführt.
                if text and not werkzeugaufrufe:
                    text += " ... (Hier ist meine Antwort abgeschnitten.)"
                else:
                    text = ABGESCHNITTEN
                self.verlauf.append({"role": "assistant",
                                     "content": [{"type": "text", "text": text}]})
                _protokoll()
                if protokollieren:
                    self.memory.verlauf_anhaengen("assistant", text)
                return text

            self.verlauf.append({"role": "assistant", "content": inhalt})
            if not werkzeugaufrufe:
                _protokoll()
                if protokollieren and text:
                    self.memory.verlauf_anhaengen("assistant", text)
                return text or "Dazu habe ich nichts zu sagen."

            ergebnisse = []
            for aufruf in werkzeugaufrufe:
                name = aufruf.get("name", "")
                argumente = aufruf.get("input") or {}
                print("[werkzeug] %s %s" % (name, json.dumps(argumente,
                                                             ensure_ascii=False)[:200]))
                ergebnis = self.tools.run(name, argumente)
                try:
                    text = json.dumps(ergebnis, ensure_ascii=False, default=str)[:6000]
                except (TypeError, ValueError):
                    text = str(ergebnis)[:6000]
                ergebnisse.append({"type": "tool_result", "tool_use_id": aufruf.get("id"),
                                   "content": text,
                                   "is_error": not bool(ergebnis.get("ok"))})
            self.verlauf.append({"role": "user", "content": ergebnisse})

        _protokoll()
        return ("Ich habe es %d Mal versucht und komme nicht weiter. Sag mir bitte "
                "genauer, was du brauchst." % MAX_RUNDEN)

    def arbeiten(self, systemtext: str, auftrag: str, werkzeugnamen: list = None,
                 max_runden: int = 6, grund: str = "Team", hintergrund: bool = False) -> str:
        """Wie ``_arbeiten``, mit dem Hintergrund-Merker für den Werkzeugkatalog.

        Ohne Sperre: Die Schleife hat ihre eigene Nachrichtenliste, und der
        Autopilot soll niemanden warten lassen, der gerade mit Jarvis spricht.
        """
        vorher = self.tools.im_hintergrund()
        self.tools.hintergrund_setzen(vorher or hintergrund)
        try:
            return self._arbeiten(systemtext, auftrag, werkzeugnamen, max_runden, grund)
        finally:
            self.tools.hintergrund_setzen(vorher)

    def _arbeiten(self, systemtext: str, auftrag: str, werkzeugnamen: list = None,
                  max_runden: int = 6, grund: str = "Team") -> str:
        """Eine abgeschlossene Arbeitsschleife ohne eigenen Gesprächsverlauf.

        Damit arbeitet eine Fachkraft ihren Auftrag ab: eigener Systemprompt,
        eigener Werkzeugsatz, eigenes Ende. Der Verlauf des Hauptgesprächs
        bleibt davon unberührt - sonst würde jeder Zwischenschritt einer
        Fachkraft den Kontext des Chefs zumüllen.
        """
        if not self.einsatzbereit():
            return ("Es ist kein Anthropic-Schlüssel hinterlegt.")
        if self.gedankenlog.limit_erreicht():
            return self._limit_meldung()

        katalog = self.tools.katalog()
        erlaubt = None
        if werkzeugnamen:
            erlaubt = set(werkzeugnamen)
            katalog = [w for w in katalog if w["name"] in erlaubt]
            if not katalog:
                return "Für diesen Auftrag stehen keine Werkzeuge bereit."

        nachrichten = [{"role": "user", "content": auftrag}]
        beginn = time.time()
        summe = {}

        def protokoll():
            self.gedankenlog.eintragen(
                auftrag, "claude", grund, time.time() - beginn, summe.get("ein", 0),
                summe.get("aus", 0), summe_kosten(summe))

        for _ in range(max(1, int(max_runden))):
            antwort = self._claude_runde({
                "model": config.CLAUDE_MODEL,
                "max_tokens": config.CLAUDE_MAX_TOKENS,
                "system": systemtext,
                "tools": katalog,
                "messages": nachrichten,
            }, summe)
            if not antwort.get("ok"):
                protokoll()
                return antwort.get("fehler", "Der Auftrag ist fehlgeschlagen.")

            if antwort["daten"].get("stop_reason") == "refusal":
                protokoll()
                return "Diesen Auftrag lehnt Claude ab. Formuliere ihn bitte anders."
            inhalt = ausweichen_bereinigen(antwort["daten"].get("content", []))
            text = "\n".join(b.get("text", "") for b in inhalt
                             if b.get("type") == "text").strip()
            aufrufe = [b for b in inhalt if b.get("type") == "tool_use"]
            if antwort["daten"].get("stop_reason") == "max_tokens":
                protokoll()
                if text and not aufrufe:
                    return text + " ... (Hier ist die Antwort abgeschnitten.)"
                return ABGESCHNITTEN
            nachrichten.append({"role": "assistant", "content": inhalt})
            if not aufrufe:
                protokoll()
                return text

            ergebnisse = []
            for aufruf in aufrufe:
                name = aufruf.get("name", "")
                print("[fachkraft] %s" % name)
                if erlaubt is not None and name not in erlaubt:
                    # Die Liste der Rolle ist die Sperre, nicht nur das Angebot.
                    ergebnis = {"ok": False, "fehler": "Das Werkzeug %s gehört nicht zu dieser Rolle." % name}
                    self.memory.aktion_protokollieren(name, aufruf.get("input") or {},
                                                      ergebnis["fehler"], "abgelehnt")
                else:
                    ergebnis = self.tools.run(name, aufruf.get("input") or {})
                try:
                    text = json.dumps(ergebnis, ensure_ascii=False,
                                      default=str)[:6000]
                except (TypeError, ValueError):
                    text = str(ergebnis)[:6000]
                ergebnisse.append({"type": "tool_result",
                                   "tool_use_id": aufruf.get("id"),
                                   "content": text,
                                   "is_error": not bool(ergebnis.get("ok"))})
            nachrichten.append({"role": "user", "content": ergebnisse})

        protokoll()
        return ("Ich bin nach %d Schritten nicht fertig geworden und höre auf."
                % max_runden)

    def antworten(self, eingabe: str) -> str:
        """Denken und die Antwort aussprechen."""
        antwort = self.denken(eingabe)
        if antwort and self.stimme is not None:
            self.zustand_setzen("spricht")
            try:
                self.stimme.sprich(antwort)
            finally:
                self.zustand_setzen("bereit")
        elif antwort:
            print("Jarvis: %s" % antwort)
        return antwort

    # -- Briefings ----------------------------------------------------------

    def briefing_morgens(self) -> str:
        """Das Morgenbriefing - Termine, Post, Offenes, Wetter."""
        bausteine = self._bausteine_sammeln(morgens=True)
        if not self.einsatzbereit():
            return self._briefing_ohne_claude(bausteine, morgens=True)
        auftrag = ("Sprich jetzt dein Morgenbriefing. Vier bis sechs Sätze, gesprochen, "
                   "ohne Aufzählungen. Beginne mit einer kurzen Begrüßung. Nenne die "
                   "Termine, das Wichtigste aus der Post und was offen ist. Wenn etwas "
                   "davon nicht abrufbar war, sag es kurz und erfinde nichts.\n\n"
                   "Das sind die Daten:\n%s" % bausteine)
        antwort = self.denken(auftrag, protokollieren=False, anzeigen=False)
        return antwort

    def briefing_abends(self) -> str:
        """Der Abendrückblick - Zahlen, Leads, offene Punkte, Tagesbericht."""
        try:
            self.recall.tag_zusammenfassen(self)
        except Exception as fehler:
            print("[agent] Tagesbericht fehlgeschlagen: %s" % fehler)
        bausteine = self._bausteine_sammeln(morgens=False)
        if not self.einsatzbereit():
            return self._briefing_ohne_claude(bausteine, morgens=False)
        auftrag = ("Sprich jetzt deinen Abendrückblick. Vier bis sechs Sätze, gesprochen, "
                   "ohne Aufzählungen. Wie der Tag lief, was er morgen anpacken sollte, "
                   "und wenn ein Lead liegen bleibt, sag das deutlich.\n\n"
                   "Das sind die Daten:\n%s" % bausteine)
        return self.denken(auftrag, protokollieren=False, anzeigen=False)

    def _bausteine_sammeln(self, morgens: bool) -> str:
        """Sammelt die Fakten für ein Briefing - jeder Fehler bleibt sichtbar."""
        teile = []

        if morgens and self.tools.kalender.verfuegbar():
            teile.append("Kalender: %s" % self.tools.kalender.zusammenfassung(1))
        if morgens and self.tools.mail.lesen_moeglich():
            teile.append("Posteingang: %s" % self.tools.mail.zusammenfassung(10))
        if morgens and config.WETTER_ORT:
            wetter = self.tools.welt.wetter(config.WETTER_ORT)
            teile.append("Wetter: %s" % (wetter.get("text") or wetter.get("fehler")))

        if morgens:
            try:
                postfach = self.tools.autopilot.postfach(10)
                if postfach:
                    teile.append("Im Postfach des Autopiloten: %s"
                                 % self.tools.autopilot.postfach_text())
            except Exception:
                pass

        punkte = self.memory.punkte_offen()
        teile.append("Offene Punkte: %s"
                     % ("; ".join(p["text"] for p in punkte[:8]) if punkte else "keine"))

        leads = self.tools.call_analysis.offene_leads()
        teile.append("Leads: %s" % leads.get("text", ""))

        if not morgens:
            auswertung = self.tools.bookkeeping.auswertung()
            teile.append("Zahlen des Monats: %s" % auswertung.get("text", ""))
            belege = self.tools.bookkeeping.fehlende_belege()
            teile.append("Belege: %s" % belege.get("text", ""))
            muster = self.tools.call_analysis.verkaufsmuster(30)
            teile.append("Vertrieb: %s" % muster.get("text", ""))

        return "\n".join(teile)

    @staticmethod
    def _briefing_ohne_claude(bausteine: str, morgens: bool) -> str:
        """Rückfallebene ohne Schlüssel: die nackten Fakten, nichts Erfundenes."""
        kopf = ("Guten Morgen. Ohne Anthropic-Schlüssel kann ich nur die nackten Zahlen "
                "vorlesen." if morgens else
                "Feierabend. Ohne Anthropic-Schlüssel kann ich nur die nackten Zahlen "
                "vorlesen.")
        return "%s\n%s" % (kopf, bausteine)

    # -- Übersicht ----------------------------------------------------------

    def zustand(self) -> dict:
        """Was ist bereit - für den Selbsttest."""
        return {"schluessel": self.einsatzbereit(), "modell": config.CLAUDE_MODEL,
                "verlauf": len(self.verlauf), "werkzeuge": len(self.tools.namen()),
                "gedaechtnis": self.memory.statistik()}
