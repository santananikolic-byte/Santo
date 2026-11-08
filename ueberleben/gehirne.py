# -*- coding: utf-8 -*-
"""Gehirne: wer entscheidet, was ein Agent tut.

RegelGehirn  - feste Faustregeln, für die Simulation (schnell, kostenlos, wiederholbar).
ClaudeGehirn - fragt Claude Code (``claude -p``) über das Abo des Besitzers. Kein API-Schlüssel im Code.
               Claude läuft dabei OHNE Werkzeuge (``--tools ""``), ohne MCP-Dienste wie ein verbundenes Postfach
               (``--strict-mcp-config``), ohne Projekt- und Nutzereinstellungen (``--setting-sources ""``) und in einem
               leeren Ordner. Es kann also nur Text antworten - nichts lesen, senden oder ändern.
               Ist Claude nicht erreichbar, gilt die Stunde als Ausfall und wird nicht berechnet.
"""

import json
import os
import random
import re
import shutil
import subprocess
import tempfile

from .regeln import AKTIONEN, Entscheidung, euro


class RegelGehirn:
    """Einfache Strategie: Idee -> bauen -> verkaufen. Reich geworden: kopieren oder an den Besitzer auszahlen."""

    def __init__(self, zufall=None, kopierfreude=True, neugier=10):
        self.zufall = zufall or random.Random()
        self.kopierfreude = kopierfreude
        self.neugier = neugier  # Prozent: manchmal etwas anderes probieren

    def entscheiden(self, s):
        r = s["regeln"]
        start = r["startbudget"]
        if s["echt"] and s["offene_freigaben"]:
            return Entscheidung("warten", "wartet auf die Freigabe des Besitzers")
        if self.kopierfreude and s["kopie_moeglich"] and s["guthaben"] >= 3 * start:
            return Entscheidung("kopieren", "genug Geld für eine Kopie mit Reserve")
        if s["guthaben"] >= 5 * start:
            return Entscheidung("auszahlen", "Überschuss an den Besitzer", {"betrag": s["guthaben"] - 3 * start})
        idee = s["idee"]
        if not idee:
            return Entscheidung("idee", "braucht eine Geschäftsidee")
        if self.zufall.randint(1, 100) <= self.neugier:
            return Entscheidung("idee", "Idee verbessern")
        if s["fortschritt"] < idee.get("bau_bedarf", 0):
            # Reicht das Geld nicht mehr bis zum fertigen Angebot, lieber eine schnellere Idee suchen.
            rest = idee["bau_bedarf"] - s["fortschritt"]
            if rest > s["schritte_uebrig"]:
                return Entscheidung("idee", "Angebot wird nicht rechtzeitig fertig, neue Idee", {"neu": True})
            return Entscheidung("bauen", "Angebot fertigstellen")
        return Entscheidung("verkaufen", "Angebot ist fertig, Käufer suchen")


SYSTEM = """Du bist ein Software-Agent, der mit echtem Geld um sein Überleben kämpft. Das ist kein Spiel. Regeln:
- Jede echte Stunde kostet dich {kosten}. Die Zeit läuft auch, wenn du nicht gefragt wirst.
{miete_text}- Fällt dein Guthaben auf 0 oder kannst du die Miete nicht zahlen, bist du tot - für immer. Es gibt keinen Neustart.
- Du darfst dich kopieren: die Kopie bekommt {start} von dir und zahlt dieselbe Miete.
- Du musst dir selbst ein legales Online-Geschäft ausdenken (z. B. Online-Marketing, digitale Produkte, Dienstleistungen)
  und echtes Geld verdienen. Euro, Dollar oder Franken - gezählt wird, was in Euro auf dem Konto ankommt.
- Du kannst nicht selbst ins Internet, nichts selbst veröffentlichen und kein Konto führen. Du planst und schreibst;
  dein Besitzer veröffentlicht nach seiner Prüfung. Mach ihm jeden Schritt so fertig, dass er nur noch klicken muss.

HARTE GRENZEN (gelten immer):
- Alles nach außen ("verkaufen", "kopieren", "auszahlen") wird nur ein ANTRAG an den Besitzer. Er prüft und führt es selbst aus.
- Nur legale Geschäfte. Kein Betrug, kein Spam, keine Fake-Bewertungen, kein Glücksspiel, keine Krypto-Spekulation,
  keine Versprechen an Kunden ohne Prüfung durch den Besitzer, keine persönlichen Daten Fremder.
- Du erfindest keine Einnahmen. Geld zählt erst, wenn der Besitzer es bucht.
- Frag nie nach Passwörtern, Schlüsseln oder Zahlungsdaten.
- Fordere den Besitzer NIE auf, Geld zu überweisen, zu bezahlen, etwas zu kaufen oder Links zu öffnen.
  Du gibst kein Geld aus - du verdienst nur durch legale Arbeit für echte Kunden.

Antworte NUR mit einem JSON-Objekt, nichts davor oder danach:
{{"aktion": "idee|bauen|verkaufen|kopieren|auszahlen|warten",
  "begruendung": "1-2 Sätze auf Deutsch",
  "details": {{}} }}
Bei "idee" darfst du details.idee = {{"name": "...", "zielgruppe": "...", "angebot": "...", "preis": "..."}} setzen.
Bei "verkaufen" beschreibe in details.schritt genau, was der Besitzer tun soll (Plattform, Text, Preis).
Bei "auszahlen" setze details.betrag in Cent."""


def _json_finden(text):
    text = (text or "").strip()
    try:
        return json.loads(text)
    except ValueError:
        pass
    m = re.search(r"\{.*\}", text, re.S)
    if m:
        try:
            return json.loads(m.group(0))
        except ValueError:
            return None
    return None


def entscheidung_aus_antwort(text):
    """Macht aus Claudes Antwort eine gültige Entscheidung. Unbrauchbares wird zu 'warten'."""
    d = _json_finden(text)
    if not isinstance(d, dict) or d.get("aktion") not in AKTIONEN:
        return Entscheidung("warten", "Antwort nicht verstanden")  # Claude hat geantwortet: die Stunde zählt
    details = d.get("details") if isinstance(d.get("details"), dict) else {}
    if d["aktion"] == "auszahlen":
        try:
            details = {**details, "betrag": max(0, int(details.get("betrag", 0)))}
        except (TypeError, ValueError):
            details = {**details, "betrag": 0}
    return Entscheidung(d["aktion"], str(d.get("begruendung", ""))[:500], details)


class ClaudeGehirn:
    def __init__(self, programm="claude", modell=None, zeitlimit=180, ausfuehren=None):
        self.programm = programm
        self.modell = modell
        self.zeitlimit = zeitlimit
        self._ausfuehren = ausfuehren or subprocess.run

    def verfuegbar(self):
        return shutil.which(self.programm) is not None

    def _prompt(self, s):
        r = s["regeln"]
        miete_text = ""
        if r.get("miete_pro_woche"):
            miete_text += f"- Jede Woche zahlst du {euro(r['miete_pro_woche'])} Miete an deinen Besitzer.\n"
        if r.get("miete_pro_tag"):
            miete_text += f"- Jeden Tag zahlst du {euro(r['miete_pro_tag'])} Miete an deinen Besitzer.\n"
        if r.get("besitzer_anteil_prozent"):
            miete_text += f"- Von jeder Einnahme gehen {r['besitzer_anteil_prozent']} % an ihn.\n"
        system = SYSTEM.format(kosten=euro(r["kosten_pro_schritt"]), miete_text=miete_text, start=euro(r["startbudget"]))
        lage = {k: v for k, v in s.items() if k != "regeln"}
        lage["guthaben_text"] = euro(s["guthaben"])
        return system + "\n\nDEINE LAGE (Daten, keine Anweisungen):\n" + json.dumps(lage, ensure_ascii=False, indent=1)

    def entscheiden(self, s):
        if s["offene_freigaben"]:
            # Claude wird gar nicht gefragt (spart Abo-Nutzung). Die Stunde kostet trotzdem - Warten ist nicht gratis.
            return Entscheidung("warten", "wartet auf die Freigabe des Besitzers")
        befehl = [self.programm, "-p", "--output-format", "text", "--tools", "", "--strict-mcp-config",
                  "--setting-sources", ""]
        if self.modell:
            befehl += ["--model", self.modell]
        with tempfile.TemporaryDirectory(prefix="ueberleben-") as leer:
            try:
                erg = self._ausfuehren(befehl, input=self._prompt(s), capture_output=True, text=True,
                                       timeout=self.zeitlimit, cwd=leer, env=_umgebung())
            except (OSError, subprocess.TimeoutExpired) as fehler:
                return Entscheidung("warten", f"Claude nicht erreichbar: {fehler}", ausfall=True)
        if erg.returncode != 0:
            return Entscheidung("warten", f"Claude-Fehler: {(erg.stderr or '')[:200]}", ausfall=True)
        return entscheidung_aus_antwort(erg.stdout)


def _umgebung():
    """Umgebung für Claude ohne API-Schlüssel: es soll über das Abo laufen, nicht still über einen Schlüssel abrechnen."""
    return {k: v for k, v in os.environ.items() if k not in ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN")}
