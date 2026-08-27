#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Werkzeugkatalog - alles, was Claude tatsächlich tun kann.

Zwei Sicherheitsentscheidungen stecken in diesem Modul, und sie sind nicht
verhandelbar.

**Keine freie Kommandozeile.** Eine Blockliste gefährlicher Befehle wäre
wertlos: ``rm -rf`` lässt sich als ``rm  -rf`` oder ``rm -fr`` schreiben und
rutscht durch. Stattdessen gibt es eine *Allowlist* registrierter Aktionen mit
festen Argumenten. Was nicht registriert ist, läuft nicht. Jeder Aufruf geht über
``subprocess.run([...])`` mit abgeschalteter Shell - eine Shell wird im ganzen
Projekt an keiner Stelle eingeschaltet.

**Kein Vollzug ohne klares Ja.** Alles mit Wirkung nach außen fragt vorher nach.
Timeout oder ausbleibende Antwort gelten als Ablehnung.
"""

import json
import os
import re
import subprocess

import config
from modules.akquise import Akquise, SONDERLEISTUNGEN, STUFEN
from modules.bookkeeping import Bookkeeping, KATEGORIEN
from modules.calendar_mod import Kalender
from modules.call_analysis import CallAnalysis
from modules.camera import Kamera
from modules.computer_use import Bildschirm
from modules.dashboard import Dashboard
from modules.mail import Mail
from modules.mcp_client import MCPClient
from modules.memory import Memory, heute_datum
from modules.privat import BEREICHE, Privat, WIEDERHOLUNGEN, RHYTHMEN
from modules.messenger import Messenger
from modules.recall import Recall
from modules.routines import Routines
from modules.team import ROLLEN, Team
from modules.telegram_mod import Telegram
from modules.werkstatt import Werkstatt
from modules.world import Welt

# Zeichen, die in eingesetzten Parametern nichts zu suchen haben. Weil überall
# ``shell=False`` gilt, wären sie ohnehin harmlos - abgelehnt werden sie
# trotzdem, damit ein späterer Umbau nicht plötzlich eine Lücke aufreißt.
GEFAEHRLICHE_ZEICHEN = set(";|&$`\n<>")

# Registrierte Aktionen ohne Parameter. Der Name ist der einzige Schlüssel -
# alles andere steht fest im Code.
SYSTEM_AKTIONEN = {
    "datum": (["date", "+%A, %d.%m.%Y, %H:%M"], "Datum und Uhrzeit"),
    "speicherplatz": (["df", "-h", "/"], "freier Speicherplatz"),
    "rechnername": (["hostname"], "Name des Rechners"),
    "laufzeit": (["uptime"], "wie lange der Rechner läuft"),
    "arbeitsspeicher": (["vm_stat"], "Arbeitsspeicher"),
    "batterie": (["pmset", "-g", "batt"], "Ladezustand des Akkus"),
    "netzwerk": (["ifconfig", "en0"], "Netzwerkverbindung"),
    "wlan": (["networksetup", "-getairportnetwork", "en0"], "verbundenes WLAN"),
    "programme": (["ps", "-A", "-o", "comm"], "laufende Programme"),
    "lautstaerke": (["osascript", "-e", "output volume of (get volume settings)"],
                    "Lautstärke"),
}

# Registrierte Aktionen mit genau einem geprüften Parameter.
PARAMETER_AKTIONEN = {
    "ordner_zeigen": (["ls", "-la", "{pfad}"], "pfad", "Inhalt eines Ordners"),
    "programm_oeffnen": (["open", "-a", "{programm}"], "programm", "Programm starten"),
    "datei_oeffnen": (["open", "{pfad}"], "pfad", "Datei öffnen"),
}

# Alles hier drin fragt vor der Ausführung nach einer Freigabe.
FREIGABE_PFLICHTIG = {"mail_senden", "termin_anlegen", "bildschirm_bedienen",
                      "nachricht_senden", "skript_ausfuehren"}


def parameter_pruefen(wert: str):
    """Prüft einen eingesetzten Parameter. Gibt ``(ok, meldung)`` zurück."""
    text = str(wert if wert is not None else "")
    if not text.strip():
        return False, "Der Wert ist leer."
    if len(text) > 500:
        return False, "Der Wert ist zu lang."
    treffer = sorted({z for z in text if z in GEFAEHRLICHE_ZEICHEN})
    if treffer:
        sichtbar = ", ".join(repr(z) for z in treffer)
        return False, ("Der Wert enthält die Zeichen %s. Solche Werte führe ich "
                       "grundsätzlich nicht aus." % sichtbar)
    return True, ""


class Werkzeuge:
    """Der Katalog: Beschreibungen für Claude und die Ausführung dahinter."""

    def __init__(self, agent=None, db_pfad: str = None):
        self.agent = agent
        self.memory = Memory(db_pfad)
        self.recall = Recall(self.memory)
        self.bookkeeping = Bookkeeping(self.memory)
        self.call_analysis = CallAnalysis(self.memory)
        self.akquise = Akquise(self.memory, config.STANDARD_MWST)
        self.werkstatt = Werkstatt(self.memory)
        self.privat = Privat(self.memory, config.STEUER_RUECKLAGE)
        self.routines = Routines(self.memory)
        self.mail = Mail()
        self.kalender = Kalender()
        self.telegram = Telegram()
        self.kamera = Kamera()
        self.mcp = MCPClient()
        self.welt = Welt(self.mcp)
        self.bildschirm = Bildschirm(agent)
        self.messenger = Messenger(self.telegram, self.mail, self.mcp, None)
        self.team = Team(agent, self.memory)
        self.dashboard = Dashboard(memory=self.memory, bookkeeping=self.bookkeeping,
                                   call_analysis=self.call_analysis, recall=self.recall,
                                   kalender=self.kalender, mail=self.mail,
                                   routines=self.routines, mcp=self.mcp,
                                   akquise=self.akquise, team=self.team,
                                   privat=self.privat)
        self.stimme = None
        # Ein anderer Weg, Freigaben einzuholen - die Web-App setzt sich hier ein.
        self.freigabe_kanal = None

    def freigabe_kanal_setzen(self, kanal):
        """Setzt einen anderen Freigabeweg, etwa den Browser.

        Der Kanal braucht nur eine Methode ``anfordern(aktion, details)``, die
        ein Wörterbuch mit ``erlaubt`` zurückgibt. Ohne Kanal bleibt es bei
        Telegram beziehungsweise dem Terminal.
        """
        self.freigabe_kanal = kanal

    def stimme_setzen(self, stimme):
        """Reicht die Sprachausgabe durch - für Sprachnachrichten."""
        self.stimme = stimme
        self.messenger.stimme = stimme

    def agent_setzen(self, agent):
        """Verknüpft den Katalog mit dem Agenten, damit Werkzeuge Claude nutzen können."""
        self.agent = agent
        self.bildschirm.agent = agent
        self.team.agent = agent

    # -- Katalog für Claude -------------------------------------------------

    def katalog(self) -> list:
        """Alle Werkzeuge im Format der Claude-Schnittstelle."""
        def werkzeug(name, beschreibung, eigenschaften=None, pflicht=None):
            return {"name": name, "description": beschreibung,
                    "input_schema": {"type": "object",
                                     "properties": eigenschaften or {},
                                     "required": pflicht or []}}

        text = {"type": "string"}
        zahl = {"type": "number"}
        ganz = {"type": "integer"}
        wahr = {"type": "boolean"}

        eigene = [
            # -- Gedächtnis --
            werkzeug("notiz_speichern",
                     "Hält etwas Wichtiges fest, das er nebenbei erwähnt: eine "
                     "Kundeninformation, eine Entscheidung, eine Zahl.",
                     {"text": text, "kategorie": text}, ["text"]),
            werkzeug("notizen_suchen", "Sucht in gespeicherten Notizen.",
                     {"begriff": text}, ["begriff"]),
            werkzeug("kontakt_anlegen",
                     "Legt einen Kunden oder Lieferanten an oder ergänzt ihn.",
                     {"name": text, "firma": text, "telefon": text, "email": text,
                      "adresse": text, "notiz": text}, ["name"]),
            werkzeug("kontakt_suchen", "Sucht einen Kontakt.",
                     {"begriff": text}, ["begriff"]),
            werkzeug("punkt_anlegen",
                     "Merkt sich etwas, das noch zu erledigen ist.",
                     {"text": text, "faellig": text}, ["text"]),
            werkzeug("punkte_offen", "Zeigt, was noch offen ist.", {}),
            werkzeug("punkt_erledigen", "Hakt einen offenen Punkt ab.",
                     {"id": ganz}, ["id"]),
            werkzeug("kennzahl_setzen", "Hält eine Kennzahl mit Datum fest.",
                     {"name": text, "wert": zahl, "einheit": text}, ["name", "wert"]),
            werkzeug("gedaechtnis_durchsuchen",
                     "Sucht in Notizen, Kontakten, Tagesberichten und früheren "
                     "Gesprächen nach einem Thema.",
                     {"frage": text}, ["frage"]),
            werkzeug("tagesbericht_speichern",
                     "Legt die Zusammenfassung eines Tages ab.",
                     {"zusammenfassung": text, "entscheidungen": text, "offen": text,
                      "datum": text}, ["zusammenfassung"]),
            werkzeug("rueckblick", "Gibt die Tagesberichte der letzten Tage zurück.",
                     {"tage": ganz}),

            # -- Buchhaltung --
            werkzeug("buchung_eintragen",
                     "Trägt eine Einnahme oder Ausgabe ein. Beträge nie schätzen - "
                     "ist etwas unklar, vorher nachfragen.",
                     {"art": {"type": "string", "enum": ["einnahme", "ausgabe"]},
                      "datum": text, "betrag": zahl, "haendler": text,
                      "kategorie": {"type": "string", "enum": KATEGORIEN},
                      "mwst_satz": zahl, "mwst_betrag": zahl, "zahlungsart": text,
                      "notiz": text},
                     ["art", "datum", "betrag"]),
            werkzeug("beleg_erfassen",
                     "Liest einen Beleg von einem Foto und trägt ihn ein.",
                     {"bildpfad": text}, ["bildpfad"]),
            werkzeug("auswertung",
                     "Einnahmen, Ausgaben, Ergebnis, Vorsteuer, Umsatzsteuer und "
                     "Zahllast für einen Zeitraum.",
                     {"von": text, "bis": text}),
            werkzeug("fehlende_belege",
                     "Zeigt Ausgaben ohne hinterlegtes Belegfoto - genau die fehlen "
                     "beim Steuerberater.", {"von": text, "bis": text}),
            werkzeug("csv_export", "Exportiert die Buchungen als CSV für den Steuerberater.",
                     {"von": text, "bis": text}),

            # -- Kundengespräche --
            werkzeug("gespraech_festhalten",
                     "Bewertet ein Kundengespräch und legt es ab. Nutze das immer "
                     "ungefragt, wenn er von einem Kundentermin erzählt.",
                     {"bericht": text, "kunde": text}, ["bericht"]),
            werkzeug("offene_leads", "Zeigt offene Leads samt offenem Volumen.", {}),
            werkzeug("verkaufsmuster",
                     "Abschlussquote, Durchschnittspunktzahl und wiederkehrende Einwände.",
                     {"tage": ganz}),

            # -- Routinen --
            werkzeug("routine_anlegen",
                     "Legt einen gespeicherten Ablauf an. Mit Uhrzeit läuft er täglich "
                     "von selbst.",
                     {"name": text, "anweisung": text, "uhrzeit": text},
                     ["name", "anweisung"]),
            werkzeug("routine_ausfuehren", "Führt eine gespeicherte Routine aus.",
                     {"name": text}, ["name"]),
            werkzeug("routinen_liste", "Zeigt alle gespeicherten Routinen.", {}),

            # -- Akquise --
            werkzeug("lead_anlegen",
                     "Nimmt einen Interessenten in die Pipeline auf.",
                     {"firma": text, "ansprechpartner": text, "telefon": text,
                      "email": text, "adresse": text, "quelle": text,
                      "objekt_qm": zahl, "bodenbelag": text,
                      "intervall_pro_woche": zahl, "notiz": text,
                      "naechster_schritt": text}, ["firma"]),
            werkzeug("lead_weiterstufen",
                     "Setzt einen Interessenten auf eine neue Stufe.",
                     {"name": text,
                      "stufe": {"type": "string", "enum": STUFEN},
                      "notiz": text, "naechster_schritt": text,
                      "wert_monat": zahl}, ["name", "stufe"]),
            werkzeug("angebot_kalkulieren",
                     "Rechnet aus Fläche, Bodenbelag und Reinigungsintervall einen "
                     "Monatspreis über Leistungswerte. Ohne Quadratmeter und "
                     "Intervall wird nichts gerechnet - dann nachfragen.",
                     {"qm": zahl, "bodenbelag": text, "intervall_pro_woche": zahl,
                      "stundensatz": zahl,
                      "sonderleistungen": {
                          "type": "object",
                          "description": "Mengen je Leistung: %s"
                                         % ", ".join(SONDERLEISTUNGEN)}},
                     ["qm", "intervall_pro_woche"]),
            werkzeug("angebot_ablegen",
                     "Legt ein kalkuliertes Angebot beim Interessenten ab und "
                     "setzt ihn auf die Stufe Angebot.",
                     {"name": text, "qm": zahl, "bodenbelag": text,
                      "intervall_pro_woche": zahl, "stundensatz": zahl,
                      "notiz": text}, ["name", "qm", "intervall_pro_woche"]),
            werkzeug("nachfassliste",
                     "Wer heute zum Nachfassen fällig ist und warum.", {}),
            werkzeug("pipeline",
                     "Alle Interessenten nach Stufen, mit Werten.", {}),
            werkzeug("cashflow_prognose",
                     "Was in den nächsten Monaten hereinkommt: gesichert aus "
                     "Aufträgen, gewichtet aus der Pipeline, abzüglich Kosten.",
                     {"monate": ganz}),

            werkzeug("leads_finden",
                     "Sucht über den Such-Dienst Betriebe in einem Ort, die "
                     "Reinigung brauchen könnten, und nimmt sie als neue "
                     "Interessenten auf. Sie stehen auf Wert null, bis "
                     "angerufen wurde.",
                     {"ort": text, "branche": text, "anzahl": ganz}, ["ort"]),

            # -- Privat --
            werkzeug("fixkosten_anlegen",
                     "Trägt eine wiederkehrende Verpflichtung ein - privat oder "
                     "betrieblich. Im Zweifel nachfragen, welches von beiden.",
                     {"name": text, "betrag": zahl,
                      "rhythmus": {"type": "string",
                                   "enum": sorted(set(RHYTHMEN))},
                      "bereich": {"type": "string", "enum": list(BEREICHE)},
                      "kategorie": text, "faellig_am": text, "notiz": text},
                     ["name", "betrag"]),
            werkzeug("fixkosten_liste",
                     "Alle laufenden Verpflichtungen, auf den Monat gerechnet.",
                     {"bereich": {"type": "string", "enum": list(BEREICHE)}}),
            werkzeug("fixkosten_streichen", "Setzt eine Verpflichtung auf inaktiv.",
                     {"name": text,
                      "bereich": {"type": "string", "enum": list(BEREICHE)}},
                     ["name"]),
            werkzeug("bedarfsrechnung",
                     "Wie viel Umsatz der Betrieb im Monat braucht, damit nach "
                     "Kosten und Steuerrücklage das Private gedeckt ist. Die "
                     "wichtigste Zahl für einen Einzelunternehmer.", {}),
            werkzeug("erinnerung_anlegen",
                     "Merkt sich etwas mit Datum, auch jährlich wiederkehrend.",
                     {"was": text, "datum": text,
                      "wiederholung": {"type": "string",
                                       "enum": list(WIEDERHOLUNGEN)},
                      "bereich": {"type": "string", "enum": list(BEREICHE)},
                      "notiz": text}, ["was", "datum"]),
            werkzeug("erinnerungen_faellig",
                     "Was in den nächsten Tagen ansteht.", {"tage": ganz}),
            werkzeug("erinnerung_erledigen", "Hakt eine Erinnerung ab.",
                     {"id": ganz}, ["id"]),

            # -- Team --
            werkzeug("mitarbeiter_beauftragen",
                     "Gibt einen mehrschrittigen Auftrag an eine Fachkraft: %s. "
                     "Sie arbeitet ihn mit ihren eigenen Werkzeugen ab und "
                     "berichtet zurück." % ", ".join(ROLLEN),
                     {"rolle": {"type": "string", "enum": sorted(ROLLEN)},
                      "auftrag": text}, ["rolle", "auftrag"]),
            werkzeug("team_liste", "Zeigt, welche Fachkräfte es gibt.", {}),
            werkzeug("lagebericht",
                     "Der vollständige aktuelle Stand des Betriebs: Kasse, "
                     "Aufträge, Cashflow, Termine, Post, Offenes.", {}),

            # -- Werkstatt --
            werkzeug("skript_schreiben",
                     "Schreibt ein Python-Skript in die Werkstatt. Ausgeführt "
                     "wird dabei nichts.",
                     {"name": text, "code": text, "zweck": text},
                     ["name", "code"]),
            werkzeug("skript_zeigen", "Zeigt den Code eines abgelegten Skripts.",
                     {"name": text}, ["name"]),
            werkzeug("skript_ausfuehren",
                     "Führt ein Skript aus der Werkstatt aus. Braucht eine "
                     "Freigabe, und der Code wird dabei vollständig angezeigt.",
                     {"name": text, "argumente": {"type": "array",
                                                  "items": {"type": "string"}}},
                     ["name"]),
            werkzeug("werkstatt_liste", "Zeigt alle abgelegten Skripte.", {}),

            # -- Kommunikation --
            werkzeug("mails_lesen",
                     "Holt ungelesene Mails und sortiert sie vor.", {"limit": ganz}),
            werkzeug("mail_senden",
                     "Verschickt eine E-Mail. Braucht eine Freigabe.",
                     {"an": text, "betreff": text, "text": text},
                     ["an", "betreff", "text"]),
            werkzeug("nachricht_senden",
                     "Verschickt eine Nachricht über telegram, mail, imessage oder "
                     "whatsapp. Braucht eine Freigabe.",
                     {"kanal": {"type": "string",
                                "enum": ["telegram", "mail", "imessage", "whatsapp"]},
                      "an": text, "text": text, "als_sprache": wahr, "betreff": text},
                     ["kanal", "text"]),

            # -- Kalender --
            werkzeug("termine_lesen",
                     "Termine der nächsten Tage samt Überschneidungen.", {"tage": ganz}),
            werkzeug("termin_anlegen",
                     "Trägt einen Termin ein. Braucht eine Freigabe.",
                     {"titel": text, "beginn": text, "dauer_minuten": ganz,
                      "ort": text, "beschreibung": text}, ["titel", "beginn"]),

            # -- Welt --
            werkzeug("wetter", "Aktuelles Wetter und Vorhersage für einen Ort.",
                     {"ort": text}),
            werkzeug("recherche", "Sucht etwas im Internet.", {"frage": text}, ["frage"]),
            werkzeug("flug_suchen",
                     "Sucht Flugverbindungen und nennt sie. Bucht nichts.",
                     {"von": text, "nach": text, "wann": text}, ["von", "nach"]),
            werkzeug("umschauen",
                     "Nimmt ein Einzelbild der Kamera auf und beschreibt, was zu sehen "
                     "ist. Kein Dauervideo.",
                     {"frage": text, "behalten": wahr}),

            # -- Bildschirm --
            werkzeug("bildschirm_bedienen",
                     "Bedient den Mac über Screenshots, Schritt für Schritt. Braucht "
                     "eine Freigabe und bestätigt jeden Schritt einzeln.",
                     {"ziel": text}, ["ziel"]),

            # -- System --
            werkzeug("systeminfo",
                     "Fragt eine registrierte Systeminformation ab. Erlaubt sind "
                     "ausschließlich: %s." % ", ".join(sorted(SYSTEM_AKTIONEN)),
                     {"was": {"type": "string", "enum": sorted(SYSTEM_AKTIONEN)}},
                     ["was"]),
            werkzeug("ordner_zeigen", "Listet den Inhalt eines Ordners auf.",
                     {"pfad": text}, ["pfad"]),
            werkzeug("programm_oeffnen", "Startet ein Programm auf dem Mac.",
                     {"programm": text}, ["programm"]),
            werkzeug("dashboard_bauen", "Baut das Command Center neu.", {}),
        ]
        return eigene + self.mcp.alle_werkzeuge()

    def namen(self) -> list:
        """Alle Werkzeugnamen."""
        return [w["name"] for w in self.katalog()]

    # -- Freigabe -----------------------------------------------------------

    def braucht_freigabe(self, name: str) -> bool:
        """Muss vor diesem Werkzeug gefragt werden?"""
        if self.mcp.ist_mcp_werkzeug(name):
            return self.mcp.braucht_freigabe(name)
        return name in FREIGABE_PFLICHTIG

    def _freigabe(self, name: str, argumente: dict) -> dict:
        """Holt die Freigabe ein. Ohne klares Ja wird nichts ausgeführt."""
        if name == "skript_ausfuehren":
            # Beim Ausführen von Code muss der Code selbst in der Frage stehen.
            # Über einen blossen Dateinamen kann niemand entscheiden.
            details = self.werkstatt.freigabetext(argumente.get("name", ""))
        else:
            try:
                details = json.dumps(argumente or {}, ensure_ascii=False)[:600]
            except (TypeError, ValueError):
                details = str(argumente)[:600]
        if self.freigabe_kanal is not None:
            return self.freigabe_kanal.anfordern(name, details)
        return self.telegram.freigabe_einholen(name, details)

    # -- Ausführung ---------------------------------------------------------

    def run(self, name: str, argumente: dict = None) -> dict:
        """Führt ein Werkzeug aus - mit Freigabeprüfung und Protokoll."""
        argumente = argumente or {}
        if name not in self.namen():
            ergebnis = {"ok": False,
                        "fehler": "Das Werkzeug '%s' gibt es nicht." % name}
            self.memory.aktion_protokollieren(name, argumente, ergebnis["fehler"],
                                              "unbekannt")
            return ergebnis

        if self.braucht_freigabe(name):
            entscheidung = self._freigabe(name, argumente)
            if not entscheidung.get("erlaubt"):
                ergebnis = {"ok": False, "abgebrochen": True,
                            "text": "Abgebrochen. %s" % entscheidung.get("grund", "")}
                self.memory.aktion_protokollieren(
                    name, argumente, "Abgebrochen: %s" % entscheidung.get("grund", ""),
                    "abgelehnt")
                return ergebnis

        try:
            ergebnis = self._ausfuehren(name, argumente)
        except Exception as fehler:
            ergebnis = {"ok": False,
                        "fehler": "Das Werkzeug %s ist fehlgeschlagen: %s" % (name, fehler)}

        if not isinstance(ergebnis, dict):
            ergebnis = {"ok": True, "text": str(ergebnis)}
        kurz = str(ergebnis.get("text") or ergebnis.get("fehler") or "")[:400]
        self.memory.aktion_protokollieren(
            name, argumente, kurz, "ok" if ergebnis.get("ok") else "fehler")
        return ergebnis

    def _ausfuehren(self, name: str, a: dict) -> dict:
        """Die eigentliche Zuordnung von Namen zu Funktionen."""
        if self.mcp.ist_mcp_werkzeug(name):
            return self.mcp.aufrufen(name, a)

        # -- Gedächtnis --
        if name == "notiz_speichern":
            return self.memory.notiz_speichern(a.get("text"), a.get("kategorie", "allgemein"))
        if name == "notizen_suchen":
            treffer = self.memory.notizen_suchen(a.get("begriff"))
            return {"ok": True, "anzahl": len(treffer),
                    "notizen": [{"id": n["id"], "text": n["text"],
                                 "datum": n["angelegt"][:10]} for n in treffer],
                    "text": ("%d Notizen gefunden." % len(treffer)) if treffer
                            else "Dazu habe ich nichts gespeichert."}
        if name == "kontakt_anlegen":
            return self.memory.kontakt_anlegen(
                a.get("name"), a.get("firma", ""), a.get("telefon", ""),
                a.get("email", ""), a.get("adresse", ""), a.get("notiz", ""))
        if name == "kontakt_suchen":
            treffer = self.memory.kontakt_suchen(a.get("begriff"))
            return {"ok": True, "anzahl": len(treffer),
                    "kontakte": [{k: z[k] for k in ("id", "name", "firma", "telefon",
                                                    "email", "notiz")} for z in treffer],
                    "text": ("%d Kontakte gefunden." % len(treffer)) if treffer
                            else "Den Kontakt kenne ich nicht."}
        if name == "punkt_anlegen":
            return self.memory.punkt_anlegen(a.get("text"), a.get("faellig", ""))
        if name == "punkte_offen":
            punkte = self.memory.punkte_offen()
            return {"ok": True, "anzahl": len(punkte),
                    "punkte": [{"id": p["id"], "text": p["text"],
                                "faellig": p["faellig"]} for p in punkte],
                    "text": ("%d Punkte offen." % len(punkte)) if punkte
                            else "Es ist nichts offen."}
        if name == "punkt_erledigen":
            erledigt = self.memory.punkt_erledigen(a.get("id"))
            return {"ok": erledigt,
                    "text": "Erledigt." if erledigt
                            else "Einen offenen Punkt mit dieser Nummer gibt es nicht."}
        if name == "kennzahl_setzen":
            return self.memory.kennzahl_setzen(a.get("name"), a.get("wert"),
                                               a.get("einheit", ""))
        if name == "gedaechtnis_durchsuchen":
            treffer = self.recall.nachschlagen(a.get("frage", ""))
            anzahl = sum(len(treffer[s]) for s in
                         ("notizen", "kontakte", "berichte", "aeusserungen"))
            return {"ok": True, "treffer": {
                        "notizen": [n["text"] for n in treffer["notizen"]],
                        "kontakte": [k["name"] for k in treffer["kontakte"]],
                        "berichte": [("%s: %s" % (b["datum"], b["zusammenfassung"]))
                                     for b in treffer["berichte"]],
                        "aeusserungen": [z["text"][:200] for z in treffer["aeusserungen"]]},
                    "text": ("%d Treffer im Gedächtnis." % anzahl) if anzahl
                            else "Dazu finde ich nichts."}
        if name == "tagesbericht_speichern":
            return self.recall.tagesbericht_speichern(
                a.get("zusammenfassung"), a.get("entscheidungen", ""),
                a.get("offen", ""), a.get("datum", ""))
        if name == "rueckblick":
            return {"ok": True, "text": self.recall.rueckblick(int(a.get("tage") or 7))}

        # -- Buchhaltung --
        if name == "buchung_eintragen":
            return self.bookkeeping.buchung_eintragen(
                a.get("art"), a.get("datum"), a.get("betrag"), a.get("haendler", ""),
                a.get("kategorie", "Sonstiges"), a.get("mwst_satz"),
                a.get("mwst_betrag"), a.get("zahlungsart", ""), None, "",
                a.get("notiz", ""))
        if name == "beleg_erfassen":
            return self.bookkeeping.beleg_erfassen(a.get("bildpfad"), self.agent)
        if name == "auswertung":
            return self.bookkeeping.auswertung(a.get("von", ""), a.get("bis", ""))
        if name == "fehlende_belege":
            return self.bookkeeping.fehlende_belege(a.get("von", ""), a.get("bis", ""))
        if name == "csv_export":
            return self.bookkeeping.csv_export(a.get("von", ""), a.get("bis", ""))

        # -- Kundengespräche --
        if name == "gespraech_festhalten":
            return self.call_analysis.gespraech_festhalten(
                a.get("bericht"), self.agent, a.get("kunde", ""))
        if name == "offene_leads":
            return self.call_analysis.offene_leads()
        if name == "verkaufsmuster":
            return self.call_analysis.verkaufsmuster(int(a.get("tage") or 90))

        # -- Routinen --
        if name == "routine_anlegen":
            return self.routines.routine_anlegen(a.get("name"), a.get("anweisung"),
                                                 a.get("uhrzeit", ""))
        if name == "routine_ausfuehren":
            return self.routines.routine_ausfuehren(a.get("name"), self.agent)
        if name == "routinen_liste":
            liste = self.routines.routinen_liste()
            return {"ok": True, "anzahl": len(liste),
                    "routinen": [{"name": z["name"], "uhrzeit": z["uhrzeit"],
                                  "anweisung": z["anweisung"][:200]} for z in liste],
                    "text": ("Gespeicherte Routinen: %s."
                             % ", ".join(z["name"] for z in liste)) if liste
                            else "Es ist noch keine Routine angelegt."}

        # -- Akquise --
        if name == "lead_anlegen":
            return self.akquise.lead_anlegen(
                a.get("firma"), a.get("ansprechpartner", ""), a.get("telefon", ""),
                a.get("email", ""), a.get("adresse", ""), a.get("quelle", ""),
                a.get("objekt_qm", 0), a.get("bodenbelag", ""),
                a.get("intervall_pro_woche", 0), a.get("notiz", ""),
                a.get("naechster_schritt", ""))
        if name == "lead_weiterstufen":
            return self.akquise.lead_weiterstufen(
                a.get("name"), a.get("stufe"), a.get("notiz", ""),
                a.get("naechster_schritt", ""), a.get("wert_monat"))
        if name == "angebot_kalkulieren":
            return self.akquise.angebot_kalkulieren(
                a.get("qm"), a.get("bodenbelag", ""), a.get("intervall_pro_woche"),
                a.get("stundensatz"), a.get("sonderleistungen"))
        if name == "angebot_ablegen":
            kalkulation = self.akquise.angebot_kalkulieren(
                a.get("qm"), a.get("bodenbelag", ""), a.get("intervall_pro_woche"),
                a.get("stundensatz"))
            if not kalkulation.get("ok"):
                return kalkulation
            ergebnis = self.akquise.angebot_ablegen(a.get("name"), kalkulation,
                                                    a.get("notiz", ""))
            ergebnis["angebotstext"] = self.akquise.angebotstext(
                kalkulation, a.get("name", ""))
            return ergebnis
        if name == "nachfassliste":
            return self.akquise.nachfassliste()
        if name == "pipeline":
            return self.akquise.pipeline()
        if name == "cashflow_prognose":
            return self.akquise.cashflow_prognose(int(a.get("monate") or 6),
                                                  self.bookkeeping)

        if name == "leads_finden":
            return self.akquise.leads_finden(
                a.get("ort"), a.get("branche", ""), int(a.get("anzahl") or 8),
                self.welt, self.agent)

        # -- Privat --
        if name == "fixkosten_anlegen":
            return self.privat.fixkosten_anlegen(
                a.get("name"), a.get("betrag"), a.get("rhythmus", "monatlich"),
                a.get("bereich", "privat"), a.get("kategorie", ""),
                a.get("faellig_am", ""), a.get("notiz", ""))
        if name == "fixkosten_liste":
            return self.privat.fixkosten(a.get("bereich", ""))
        if name == "fixkosten_streichen":
            return self.privat.fixkosten_streichen(a.get("name"),
                                                   a.get("bereich", ""))
        if name == "bedarfsrechnung":
            return self.privat.bedarfsrechnung(self.akquise)
        if name == "erinnerung_anlegen":
            return self.privat.erinnerung_anlegen(
                a.get("was"), a.get("datum"), a.get("wiederholung", "einmalig"),
                a.get("bereich", "privat"), a.get("notiz", ""))
        if name == "erinnerungen_faellig":
            return self.privat.erinnerungen_faellig(int(a.get("tage") or 14))
        if name == "erinnerung_erledigen":
            return self.privat.erinnerung_erledigen(a.get("id"))

        # -- Team --
        if name == "mitarbeiter_beauftragen":
            return self.team.beauftragen(a.get("rolle"), a.get("auftrag"))
        if name == "team_liste":
            liste = self.team.rollen_liste()
            return {"ok": True, "team": liste,
                    "text": "Im Team sind: %s."
                            % ", ".join("%s (%s)" % (e["name"], e["rolle"])
                                        for e in liste)}
        if name == "lagebericht":
            return self.team.lagebericht(self)

        # -- Werkstatt --
        if name == "skript_schreiben":
            return self.werkstatt.skript_schreiben(a.get("name"), a.get("code"),
                                                   a.get("zweck", ""))
        if name == "skript_zeigen":
            return self.werkstatt.skript_zeigen(a.get("name"))
        if name == "skript_ausfuehren":
            return self.werkstatt.skript_ausfuehren(a.get("name"),
                                                    a.get("argumente"))
        if name == "werkstatt_liste":
            return self.werkstatt.werkstatt_liste()

        # -- Kommunikation --
        if name == "mails_lesen":
            return self.mail.ungelesene(int(a.get("limit") or 15))
        if name == "mail_senden":
            return self.mail.senden(a.get("an"), a.get("betreff"), a.get("text"))
        if name == "nachricht_senden":
            return self.messenger.nachricht_senden(
                a.get("kanal"), a.get("an", ""), a.get("text"),
                bool(a.get("als_sprache")), a.get("betreff", ""))

        # -- Kalender --
        if name == "termine_lesen":
            return self.kalender.termine(int(a.get("tage") or 7))
        if name == "termin_anlegen":
            return self.kalender.termin_anlegen(
                a.get("titel"), a.get("beginn"), int(a.get("dauer_minuten") or 60),
                a.get("ort", ""), a.get("beschreibung", ""))

        # -- Welt --
        if name == "wetter":
            return self.welt.wetter(a.get("ort", ""))
        if name == "recherche":
            return self.welt.recherche(a.get("frage"))
        if name == "flug_suchen":
            return self.welt.flug_suchen(a.get("von"), a.get("nach"), a.get("wann", ""))
        if name == "umschauen":
            return self.kamera.umschauen(a.get("frage", ""), self.agent,
                                         bool(a.get("behalten")))

        # -- Bildschirm --
        if name == "bildschirm_bedienen":
            return self.bildschirm.bedienen(a.get("ziel", ""))

        # -- System --
        if name == "systeminfo":
            return self.systeminfo(a.get("was", ""))
        if name in PARAMETER_AKTIONEN:
            return self.parameter_aktion(name, a)
        if name == "dashboard_bauen":
            return self.dashboard.bauen(mit_netz=True)

        return {"ok": False, "fehler": "Für '%s' fehlt die Umsetzung." % name}

    # -- Die Allowlist ------------------------------------------------------

    def systeminfo(self, was: str) -> dict:
        """Führt eine registrierte Systemabfrage aus.

        Nur die Namen aus :data:`SYSTEM_AKTIONEN` sind zulässig. Ein übergebener
        Befehlstext wird nie ausgeführt - er ist schlicht kein gültiger Name.
        """
        schluessel = str(was or "").strip().lower()
        if schluessel not in SYSTEM_AKTIONEN:
            return {"ok": False,
                    "fehler": "'%s' ist keine registrierte Abfrage. Ich führe nur "
                              "diese aus: %s." % (was, ", ".join(sorted(SYSTEM_AKTIONEN)))}
        befehl, beschreibung = SYSTEM_AKTIONEN[schluessel]
        return self._befehl_ausfuehren(befehl, beschreibung)

    def parameter_aktion(self, name: str, argumente: dict) -> dict:
        """Führt eine registrierte Aktion mit genau einem geprüften Parameter aus."""
        vorlage, parametername, beschreibung = PARAMETER_AKTIONEN[name]
        wert = argumente.get(parametername, "")
        ok, meldung = parameter_pruefen(wert)
        if not ok:
            return {"ok": False,
                    "fehler": "Der Wert für %s ist nicht zulässig. %s"
                              % (parametername, meldung)}
        if parametername == "pfad":
            wert = os.path.expanduser(str(wert))
        befehl = [teil.replace("{%s}" % parametername, str(wert)) for teil in vorlage]
        return self._befehl_ausfuehren(befehl, beschreibung)

    @staticmethod
    def _befehl_ausfuehren(befehl: list, beschreibung: str) -> dict:
        """Führt einen fest registrierten Befehl aus - immer ohne Shell."""
        try:
            ergebnis = subprocess.run(befehl, capture_output=True, text=True,
                                      timeout=25, shell=False)
        except FileNotFoundError:
            return {"ok": False,
                    "fehler": "Das Programm '%s' gibt es auf diesem Rechner nicht. "
                              "Diese Abfrage funktioniert nur auf einem Mac." % befehl[0]}
        except (OSError, subprocess.SubprocessError) as fehler:
            return {"ok": False, "fehler": "Die Abfrage ist fehlgeschlagen: %s" % fehler}
        ausgabe = (ergebnis.stdout or ergebnis.stderr or "").strip()
        if ergebnis.returncode != 0 and not ergebnis.stdout:
            return {"ok": False,
                    "fehler": "Die Abfrage '%s' hat nicht funktioniert: %s"
                              % (beschreibung, ausgabe[:300])}
        return {"ok": True, "was": beschreibung, "text": ausgabe[:3000]}

    # -- Übersicht ----------------------------------------------------------

    def zustand(self) -> dict:
        """Was ist einsatzbereit - für den Selbsttest und das Dashboard."""
        return {
            "werkzeuge": len(self.namen()),
            "mcp_werkzeuge": len(self.mcp.alle_werkzeuge()),
            "freigabepflichtig": sorted(FREIGABE_PFLICHTIG),
            "systemaktionen": sorted(SYSTEM_AKTIONEN),
            "mail": self.mail.zustand(),
            "kalender": self.kalender.zustand(),
            "telegram": self.telegram.verfuegbar(),
            "kamera": self.kamera.zustand(),
            "bildschirm": self.bildschirm.zustand(),
            "versand": self.messenger.zustand(),
        }
