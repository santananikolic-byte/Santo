#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Betriebsarten - was passiert, wenn Jarvis gestartet wird.

Ohne Angabe startet die Web-App: Jarvis läuft dann im Browser, das Mikrofon
kommt vom Browser, und vom Handy im selben WLAN geht es auch. Wer lieber im
Terminal spricht, nimmt ``hoeren``.

    python3 jarvis.py             Web-App im Browser - der Normalfall
    python3 jarvis.py web --offen auch vom Handy im eigenen WLAN
    python3 jarvis.py hoeren      im Terminal zuhören, ohne Browser
    python3 jarvis.py chat        tippen statt sprechen
    python3 jarvis.py telegram    vom Handy aus
    python3 jarvis.py status      voller Stand des Betriebs
    python3 jarvis.py briefing    Briefing sofort
    python3 jarvis.py abend       Abendrückblick sofort
    python3 jarvis.py dashboard   Dashboard bauen
    python3 jarvis.py export      Buchhaltung als CSV
    python3 jarvis.py stimme      Stimmprofil einlernen
    python3 jarvis.py stimmen     ElevenLabs-Stimme aussuchen
    python3 jarvis.py test        Selbsttest
    python3 jarvis.py einrichten  geführte Ersteinrichtung
    python3 jarvis.py hardware    den Mac prüfen: Last, Speicher, Platte, Netz, Wärme
    python3 jarvis.py zugang      einen Schlüssel eintragen oder ersetzen
    python3 jarvis.py zugang mail Gmail oder ein anderes Postfach verbinden
    python3 jarvis.py zugang telegram  Handy verbinden: schreiben und sprechen von unterwegs
    python3 jarvis.py macapp      Jarvis als Programm: Symbol im Dock und im Programme-Ordner
    python3 jarvis.py autopilot   Postfach des Autopiloten (an / aus zum Schalten)
    python3 jarvis.py daemon      dauerhaft, nur Stimme, ohne Fenster (der iMac als Kopf)
    python3 jarvis.py dienst      installieren | entfernen | status | neustart | hinweise
    python3 jarvis.py anzeige     Zentrale und Gehirn auf den Bildschirmen öffnen
"""

import json
import os
import sys
import threading
import time
import urllib.error
import urllib.request

import config
from agent import JarvisAgent
from modules.bookkeeping import mwst_aus_brutto
from modules.memory import Memory
from modules.mcp_client import MCPClient, MCPServer, vorlage_schreiben
from modules.scheduler import Scheduler, ist_faellig
from modules.dienst import (Ansager, HINWEISE, Herzschlag, SprachFreigabe, dienst_status,
                            entfernen, installieren, logdatei_drehen, neustarten)
from modules.setup_wizard import einrichtung_starten, zugang_eintragen
from modules.speaker import Sprecherprofil
from modules.telegram_mod import TelegramFreigabe
from modules.voice import Stimme, weckwort_pruefen
from modules.macapp import app_bauen
from modules.webapp import JarvisWeb, STANDARD_PORT
# Importe der Pakete.
# [P1 Bühne] Anfang
# [P1 Bühne] Ende
# [P2 Weltlage] Anfang
# [P2 Weltlage] Ende
# [P3 Telefon] Anfang
# [P3 Telefon] Ende
# [P4 Büro] Anfang
# [P4 Büro] Ende
# [P5 Sicht] Anfang
# [P5 Sicht] Ende
# [P6 Stimme] Anfang
# [P6 Stimme] Ende
# [P7 Start] Anfang
from modules.hardware import hardware_bericht, hardware_text, hochfahren
# [P7 Start] Ende

# Die Anzeige des Dienstes hat ihren eigenen Anschluss - so kann die Web-App per
# Doppelklick trotzdem starten, während der Dienst läuft.
ANZEIGE_PORT = STANDARD_PORT + 1

BANNER = r"""
   _   _   ___  _   _ ___ ___
  | | /_\ | _ \| | | |_ _/ __|   Persönlicher Assistent
  | |/ _ \|   /| |_| || |\__ \   Gebäudereinigung
 _/ /_/ \_\_|_\ \___/|___|___/   alles lokal auf diesem Rechner
|__/
"""


def agent_aufbauen(mit_stimme: bool = True):
    """Baut Agent, Sprachausgabe und startet die MCP-Dienste."""
    stimme = Stimme() if mit_stimme else None
    agent = JarvisAgent(stimme=stimme)
    bericht = agent.dienste_starten()
    if bericht.get("gestartet"):
        print("[mcp] gestartet: %s" % ", ".join(bericht["gestartet"]))
    if bericht.get("fehlgeschlagen"):
        for eintrag in bericht["fehlgeschlagen"]:
            print("[mcp] nicht gestartet: %s" % eintrag)
    return agent, stimme


# ---------------------------------------------------------------------------
# Dauerbetrieb
# ---------------------------------------------------------------------------

BEENDEN_SAETZE = ("schalte dich ab", "schalt dich ab", "beende dich", "feierabend jarvis",
                  "mach dich aus", "fahr dich runter")


def telegram_lauschen(agent, stimme, sperre, halt, warten: float = 10.0):
    """Nimmt im Dienst Nachrichten vom Handy an - Text oder Sprachnachricht.

    Nur der eingerichtete Chat zählt (das prüft ``nachrichten_holen``). Rückfragen
    zur Freigabe gehen per Telegram ans Handy, nicht laut in den leeren Raum. Wer
    per Sprachnachricht fragt, bekommt die Antwort auch als Sprachnachricht.
    """
    telegram = agent.tools.telegram
    kanal = TelegramFreigabe(telegram)
    while not halt.is_set():
        try:
            nachrichten = telegram.nachrichten_holen(timeout=25)
        except Exception as fehler:
            print("[telegram] %s" % fehler)
            halt.wait(warten)
            continue
        for nachricht in nachrichten:
            text = (nachricht.get("text") or "").strip()
            gesprochen = False
            if not text and nachricht.get("sprachdatei"):
                gesprochen = True
                try:
                    text = stimme.transkribieren(nachricht["sprachdatei"]) or ""
                finally:
                    try:
                        os.remove(nachricht["sprachdatei"])
                    except OSError:
                        pass
            if not text:
                continue
            erkannt, befehl = weckwort_pruefen(text)
            befehl = befehl if erkannt and befehl else text
            print("Du (Telegram): %s" % befehl)
            with sperre:
                agent.tools.anfrage_kanal_setzen(kanal)
                try:
                    antwort = agent.denken(befehl)
                except Exception as fehler:
                    antwort = "Da ist etwas schiefgegangen: %s" % fehler
                finally:
                    agent.tools.anfrage_kanal_setzen(None)
            if gesprochen and hasattr(stimme, "sprachdatei_erzeugen"):
                pfad = stimme.sprachdatei_erzeugen(antwort)
                if pfad:
                    telegram.datei_senden(pfad, "sendVoice", "voice", "")
                    try:
                        os.remove(pfad)
                    except OSError:
                        pass
            telegram.senden(antwort)


def dauerbetrieb(dienst: bool = False):
    """Hört auf das Weckwort und meldet sich zu den eingestellten Zeiten.

    Als ``dienst`` läuft das ohne Fenster und ohne Tippen: Freigaben per Stimme,
    Meldungen über den Ansager, Lebenszeichen für den Neustart bei Stillstand,
    und fehlt das Mikrofon, wird weiter versucht statt zu tippen.
    """
    print(BANNER)
    herz = None
    if dienst:
        logdatei_drehen(config.LOG_VERZEICHNIS / "dienst.log")
        herz = Herzschlag()
        herz.start()
    agent, stimme = agent_aufbauen()
    profil = Sprecherprofil()
    ansager = Ansager(stimme) if dienst else None
    if dienst:
        agent.tools.freigabe_kanal_setzen(SprachFreigabe(stimme, profil))

    zeitplan = Scheduler(agent=agent, routines=agent.tools.routines,
                         ausgabe=ansager.sagen if dienst else stimme.sprich)
    zeitplan.start()
    print("[zeitplan] Morgens %s, abends %s." % (config.BRIEFING_MORGENS,
                                                 config.BRIEFING_ABENDS))
    for eintrag in zeitplan.uebersicht():
        print("           %s  %s" % (eintrag["uhrzeit"], eintrag["beschreibung"]))

    web = None
    if dienst and config.DIENST_ANZEIGE:
        # Die Anzeige für die Bildschirme: nur zum Ansehen, nur auf diesem Rechner.
        try:
            web = JarvisWeb(agent, port=ANZEIGE_PORT, nur_anzeige=True)
            web.starten(blockierend=False)
            print("[anzeige] Zentrale:  %s/zentrale\n[anzeige] Gehirn:    %s/gehirn"
                  % (web.adresse().split("?")[0].rstrip("/"), web.adresse().split("?")[0].rstrip("/")))
        except OSError as fehler:
            web = None
            print("[anzeige] Die Anzeige startet nicht (%s). Läuft Jarvis schon einmal?" % fehler)
        finally:
            # JarvisWeb setzt sich als Freigabeweg ein. Im Dienst bleibt es die Stimme -
            # auch wenn die Anzeige nicht startet, sonst wartet jede Freigabe ins Leere.
            agent.tools.freigabe_kanal_setzen(SprachFreigabe(stimme, profil))

    if dienst:
        agent.tools.autopilot.ausgabe = ansager.leise
        agent.tools.autopilot.start()
        print("[autopilot] %s" % ("an" if config.AUTOPILOT_AN else "aus (python3 jarvis.py autopilot an)"))

    # Agent, Stimme und Ausgabewege stehen - hier verdrahten die Pakete (etwa Ausgaben),
    # bevor die Hauptschleife läuft.
    # [P1 Bühne] Anfang
    # [P1 Bühne] Ende
    # [P2 Weltlage] Anfang
    # [P2 Weltlage] Ende
    # [P3 Telefon] Anfang
    # Das Ende eines Telefonats wird gesagt; der Kalendervorschlag steht dann auch im Gespräch
    # (der Telefonagent merkt ihn über agent.meldung_vormerken vor).
    agent.tools.telefonagent.ausgabe = ansager.sagen if dienst else stimme.sprich
    # [P3 Telefon] Ende
    # [P4 Büro] Anfang
    # [P4 Büro] Ende
    # [P5 Sicht] Anfang
    # [P5 Sicht] Ende
    # [P6 Stimme] Anfang
    # [P6 Stimme] Ende
    # [P7 Start] Anfang
    # [P7 Start] Ende

    if not stimme.mikrofon_bereit() and not dienst:
        print("\n[!] Kein Mikrofonzugriff. Ich wechsle in den Tippbetrieb.")
        stimme.sprich("Ich komme nicht an das Mikrofon. Wir tippen erst einmal.")
        zeitplan.stop()
        return chatbetrieb(agent, stimme)

    if not agent.einsatzbereit():
        stimme.sprich("Es ist kein Anthropic-Schlüssel hinterlegt. Starte bitte einmal "
                      "die Einrichtung.")
        print("Starte die Einrichtung mit: python3 jarvis.py einrichten")

    # Ein Gedanke zur Zeit: Stimme am iMac und Telegram vom Handy teilen sich den Verlauf.
    denk_sperre = threading.Lock()
    telegram_halt = threading.Event()
    if dienst and config.DIENST_TELEGRAM and agent.tools.telegram.verfuegbar():
        threading.Thread(target=telegram_lauschen, args=(agent, stimme, denk_sperre, telegram_halt),
                         daemon=True, name="jarvis-telegram").start()
        print("[telegram] Ich höre auch auf Nachrichten vom Handy.")

    # Beim Hochfahren: den Mac prüfen und mit dem Tag begrüßen (einmal je Tag, sonst "wieder da").
    try:
        gruss = hochfahren(agent, stimme).get("begruessung") or "Ich bin da."
    except Exception as fehler:
        print("[hochfahren] %s" % fehler)
        gruss = "Ich bin da."
    stimme.sprich(gruss + " Sag Hey Jarvis, wenn du etwas brauchst.")
    print("\nIch höre zu. Abbrechen mit Strg und C.\n")
    mikro_gemeldet = 0.0
    mikro_seit = 0.0

    def zustand_wenn_frei(zustand):
        # Denkt gerade Telegram (hält die Sperre), gehört die Anzeige ihm.
        if denk_sperre.acquire(blocking=False):
            try:
                agent.zustand_setzen(zustand)
            finally:
                denk_sperre.release()

    try:
        while True:
            if herz is not None:
                herz.schlagen()
            if ansager is not None and ansager.wartend():
                zustand_wenn_frei("spricht")
                try:
                    ansager.ausliefern()
                finally:
                    zustand_wenn_frei("bereit")
            zustand_wenn_frei("hoert")
            pfad = stimme.aufnehmen_bis_pause(still_signal=True)
            zustand_wenn_frei("bereit")
            if not pfad:
                if dienst and getattr(stimme, "mikro_fehler", ""):
                    # Kein Tippen im Dienst: weiter versuchen, einmal pro Stunde Bescheid sagen,
                    # und nach zehn Minuten ohne Mikrofon neu starten (launchd holt ihn zurück).
                    if not mikro_seit:
                        mikro_seit = time.time()
                    if time.time() - mikro_gemeldet > 3600:
                        mikro_gemeldet = time.time()
                        print("[dienst] Kein Mikrofon. %s" % stimme.mikro_fehler)
                        stimme.sprich("Ich komme gerade nicht an das Mikrofon. "
                                      "Bitte gib es in den Systemeinstellungen frei.")
                    if time.time() - mikro_seit > 600:
                        print("[dienst] Seit zehn Minuten kein Mikrofon - Neustart.")
                        return 4
                    time.sleep(30)
                else:
                    mikro_seit = 0.0
                continue
            mikro_seit = 0.0
            try:
                text = stimme.transkribieren(pfad)
                if not text:
                    continue
                erkannt, befehl = weckwort_pruefen(text)
                if not erkannt:
                    continue

                pruefung = profil.ist_der_nutzer(pfad)
                if not pruefung["erkannt"]:
                    print("[stimme] %s - ich reagiere nicht." % pruefung["grund"])
                    continue
            finally:
                try:
                    os.remove(pfad)
                except OSError:
                    pass

            stimme.signal("verstanden")
            if not befehl:
                stimme.sprich("Ja?")
                zustand_wenn_frei("hoert")
                try:
                    nachtrag = stimme.zuhoeren()
                finally:
                    zustand_wenn_frei("bereit")
                if not nachtrag:
                    continue
                befehl = nachtrag

            print("Du: %s" % befehl)
            if dienst and any(satz in befehl.lower() for satz in BEENDEN_SAETZE):
                stimme.sprich("Alles klar, ich schalte mich ab. Bis später.")
                return 0  # Exit 0: der Dienst startet erst bei der nächsten Anmeldung neu.
            try:
                with denk_sperre:
                    agent.antworten(befehl)
            except Exception as fehler:
                stimme.signal("fehler")
                print("[fehler] %s" % fehler)
                stimme.sprich("Da ist etwas schiefgegangen: %s" % fehler)
            if herz is not None:
                herz.schlagen()
    except KeyboardInterrupt:
        print("\nBis später.")
        stimme.sprich("Bis später.")
    finally:
        telegram_halt.set()
        zeitplan.stop()
        if dienst:
            agent.tools.autopilot.stop()
            herz.stop()
            if web is not None:
                web.stoppen()
        agent.tools.mcp.stoppen()


def _port_belegt(port: int) -> bool:
    import socket
    try:
        with socket.create_connection(("127.0.0.1", int(port)), timeout=0.5):
            return True
    except OSError:
        return False


def macapp_anlegen(argumente=None) -> int:
    """``python3 jarvis.py macapp``: Jarvis als Programm mit Symbol, im Dock und auf dem Schreibtisch."""
    argumente = argumente or []
    if sys.platform != "darwin" and "--ziel" not in argumente:
        print("Die App gibt es nur auf dem Mac.")
        return 1
    ziel = argumente[argumente.index("--ziel") + 1] if "--ziel" in argumente[:-1] else None
    ergebnis = app_bauen(ziel_ordner=ziel, dock="--ohne-dock" not in argumente)
    print(ergebnis.get("text") or ergebnis.get("fehler"))
    if ergebnis.get("ok"):
        print("Starten: Klick auf das Gehirn im Dock, im Programme-Ordner oder auf dem Schreibtisch.")
    return 0 if ergebnis.get("ok") else 1


def anzeige_oeffnen(argumente=None) -> int:
    """Öffnet Gehirn und Zentrale im Browser - je ein Fenster, zum Verschieben auf die Bildschirme."""
    import shutil as _shutil
    import subprocess as _subprocess
    # Läuft der Dienst, zeigt seine Anzeige; sonst die Web-App per Doppelklick.
    if _port_belegt(ANZEIGE_PORT):
        port = ANZEIGE_PORT
    elif _port_belegt(STANDARD_PORT):
        port = STANDARD_PORT
    else:
        print("Die Anzeige läuft gerade nicht. Sie läuft im Dienst mit "
              "(python3 jarvis.py dienst status, sonst dienst installieren; DIENST_ANZEIGE=ja) "
              "oder nach Doppelklick auf JARVIS.")
        return 1
    adressen = ["http://127.0.0.1:%d/zentrale" % port, "http://127.0.0.1:%d/gehirn" % port]
    if not _shutil.which("open"):
        print("Öffne diese Adressen im Browser:\n  " + "\n  ".join(adressen))
        return 0
    for adresse in adressen:
        _subprocess.run(["open", adresse], shell=False, timeout=15,
                        stdout=_subprocess.DEVNULL, stderr=_subprocess.DEVNULL)
    print("Beide Seiten sind offen. Zentrale auf den großen Bildschirm, Gehirn auf den zweiten, "
          "dann in der Seite mit Strg+Cmd+F auf Vollbild.")
    return 0


def dienst_verwalten(argumente=None) -> int:
    """``python3 jarvis.py dienst installieren | entfernen | status | neustart | hinweise``."""
    argumente = [a.lower() for a in (argumente or [])]
    aktion = argumente[0] if argumente else "status"
    trocken = "--trocken" in argumente
    if aktion in ("installieren", "einrichten", "an"):
        ergebnis = installieren(trocken)
    elif aktion in ("entfernen", "aus"):
        ergebnis = entfernen(trocken)
    elif aktion in ("neustart", "neu"):
        ergebnis = neustarten()
    elif aktion in ("hinweise", "hilfe"):
        print(HINWEISE)
        return 0
    else:
        ergebnis = dienst_status()
    print(ergebnis.get("text") or ergebnis.get("fehler", ""))
    return 0 if ergebnis.get("ok") else 1


# ---------------------------------------------------------------------------
# Tippbetrieb
# ---------------------------------------------------------------------------

def chatbetrieb(agent=None, stimme=None):
    """Tippen statt sprechen - der Notfallweg, wenn das Mikrofon streikt."""
    if agent is None:
        print(BANNER)
        agent, stimme = agent_aufbauen(mit_stimme=True)
    print("Tippbetrieb. 'ende' beendet, 'neu' beginnt ein neues Gespräch.\n")
    try:
        while True:
            try:
                eingabe = input("Du: ").strip()
            except (EOFError, KeyboardInterrupt):
                break
            if not eingabe:
                continue
            if eingabe.lower() in ("ende", "exit", "quit", "schluss", "feierabend jarvis"):
                break
            if eingabe.lower() == "neu":
                agent.verlauf_leeren()
                print("Jarvis: Neues Gespräch.")
                continue
            antwort = agent.denken(eingabe)
            print("Jarvis: %s\n" % antwort)
            if stimme is not None:
                stimme.sprich(antwort)
    finally:
        agent.tools.mcp.stoppen()
    print("Bis später.")


# ---------------------------------------------------------------------------
# Telegram-Betrieb
# ---------------------------------------------------------------------------

def telegrambetrieb():
    """Jarvis vom Handy aus bedienen."""
    print(BANNER)
    agent, stimme = agent_aufbauen()
    telegram = agent.tools.telegram
    if not telegram.verfuegbar():
        print("Telegram ist nicht eingerichtet. Starte: python3 jarvis.py einrichten")
        return
    telegram.senden("Ich bin da. Schreib oder sprich einfach.")
    print("Telegram-Betrieb läuft. Abbrechen mit Strg und C.\n")

    zeitplan = Scheduler(agent=agent, routines=agent.tools.routines,
                         ausgabe=lambda text: telegram.senden(text))
    zeitplan.start()
    try:
        while True:
            for nachricht in telegram.nachrichten_holen(timeout=25):
                text = (nachricht.get("text") or "").strip()
                if not text and nachricht.get("sprachdatei"):
                    text = stimme.transkribieren(nachricht["sprachdatei"])
                    try:
                        os.remove(nachricht["sprachdatei"])
                    except OSError:
                        pass
                if not text:
                    continue
                erkannt, befehl = weckwort_pruefen(text)
                befehl = befehl if erkannt and befehl else text
                print("Du: %s" % befehl)
                antwort = agent.denken(befehl)
                telegram.senden(antwort)
                print("Jarvis: %s\n" % antwort)
    except KeyboardInterrupt:
        print("\nBeendet.")
    finally:
        zeitplan.stop()
        agent.tools.mcp.stoppen()


# ---------------------------------------------------------------------------
# Einzelaufgaben
# ---------------------------------------------------------------------------

def briefing_sofort(abends: bool = False):
    """Spricht sofort das Morgen- oder Abendbriefing."""
    agent, stimme = agent_aufbauen()
    try:
        text = agent.briefing_abends() if abends else agent.briefing_morgens()
        stimme.sprich(text)
        print("\n%s" % text)
    finally:
        agent.tools.mcp.stoppen()


def dashboard_bauen():
    """Baut das Command Center."""
    agent, _ = agent_aufbauen(mit_stimme=False)
    try:
        ergebnis = agent.tools.dashboard.bauen(mit_netz=True)
        print(ergebnis.get("text") or ergebnis.get("fehler"))
        if ergebnis.get("ok"):
            import subprocess
            import shutil as _shutil
            if _shutil.which("open"):
                subprocess.run(["open", ergebnis["datei"]], shell=False,
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    finally:
        agent.tools.mcp.stoppen()


def webbetrieb(argumente=None):
    """Startet Jarvis als Web-App im Browser."""
    argumente = argumente or []
    offen = "--offen" in argumente or "offen" in argumente
    # Die Mac-App öffnet ihr eigenes Fenster - dann hier keinen Browser-Tab dazu.
    ohne_browser = "--ohne-browser" in argumente
    port = STANDARD_PORT
    for teil in argumente:
        if teil.isdigit():
            port = int(teil)

    print(BANNER)
    agent, stimme = agent_aufbauen(mit_stimme=False)
    del stimme
    web = JarvisWeb(agent, port=port, offen=offen)
    # Erst den Anschluss belegen, dann den Browser öffnen - sonst landet er bei einem
    # anderen Programm auf demselben Anschluss, und hier folgt ein Absturz.
    try:
        web.starten(blockierend=False)
    except OSError as fehler:
        print("  Der Anschluss %d ist belegt (%s). Läuft Jarvis schon in einem anderen "
              "Fenster? Dann dort weiterreden - oder dieses schließen und neu starten." % (port, fehler))
        agent.tools.mcp.stoppen()
        return 1

    # Der Zeitplan meldet in die Web-App, nicht ins Terminal - dort schaut
    # um 6:45 niemand hin.
    zeitplan = Scheduler(agent=agent, routines=agent.tools.routines,
                         ausgabe=web.melden)
    zeitplan.start()
    print("  Briefings: morgens %s, abends %s"
          % (config.BRIEFING_MORGENS, config.BRIEFING_ABENDS))
    autopilot = agent.tools.autopilot
    autopilot.ausgabe = web.melden
    autopilot.start()
    print("  Autopilot: %s" % ("an, arbeitet im Hintergrund" if config.AUTOPILOT_AN
                               else "aus (einschalten auf der Seite Autopilot)"))

    # Agent, Server und Ausgabewege stehen - hier verdrahten die Pakete (etwa Ausgaben),
    # bevor der Browser aufgeht und die Hauptschleife läuft.
    # [P1 Bühne] Anfang
    # [P1 Bühne] Ende
    # [P2 Weltlage] Anfang
    # [P2 Weltlage] Ende
    # [P3 Telefon] Anfang
    # Das Ende eines Telefonats landet wie ein Briefing in der Web-App.
    agent.tools.telefonagent.ausgabe = web.melden
    # [P3 Telefon] Ende
    # [P4 Büro] Anfang
    # [P4 Büro] Ende
    # [P5 Sicht] Anfang
    # [P5 Sicht] Ende
    # [P6 Stimme] Anfang
    # [P6 Stimme] Ende
    # [P7 Start] Anfang
    # [P7 Start] Ende

    adresse = web.adresse()
    print("  Jarvis läuft jetzt im Browser:")
    print("     %s" % adresse)
    if offen:
        print("\n  Der Zugang ist offen im WLAN - deshalb steht ein Schlüssel in")
        print("  der Adresse. Ohne ihn kommt niemand herein. Gib die Adresse nur")
        print("  weiter, wenn du willst, dass jemand alles darf, was du darfst.")
    else:
        print("     (nur auf diesem Rechner erreichbar)")
    print("\n  Beenden mit Strg und C.\n")

    import shutil as _shutil
    import subprocess as _subprocess
    # Eine Seite für alles: das Gehirn sitzt mitten in der Gesprächsseite.
    if _shutil.which("open") and not ohne_browser:
        try:
            _subprocess.run(["open", adresse], shell=False, timeout=15,
                            stdout=_subprocess.DEVNULL, stderr=_subprocess.DEVNULL)
        except (OSError, _subprocess.SubprocessError):
            pass

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        zeitplan.stop()
        autopilot.stop()
        web.stoppen()
        agent.tools.mcp.stoppen()
    print("\nBeendet.")
    return 0


def autopilot_zeigen(argumente=None):
    """Zeigt das Postfach des Autopiloten - oder schaltet ihn ein und aus."""
    argumente = argumente or []
    agent, stimme = agent_aufbauen(mit_stimme=False)
    del stimme
    ap = agent.tools.autopilot
    if argumente and argumente[0].lower() in ("an", "ein", "aus"):
        print(ap.schalten(argumente[0].lower() != "aus")["text"])
        return 0
    zustand = ap.zustand()
    print("Autopilot: %s%s" % ("an" if zustand["an"] else "aus",
                               " (pausiert: %s)" % zustand["gesperrt"]
                               if zustand["an"] and zustand["gesperrt"] else ""))
    print("Wartet: %d, Postfach: %d" % (len(zustand["warteschlange"]), len(zustand["postfach"])))
    for eintrag in zustand["postfach"]:
        print("\n[%d] %s\n%s" % (eintrag["id"], eintrag["titel"], eintrag["ergebnis"]))
    return 0


def lage_sagen():
    """Sagt den vollständigen aktuellen Stand des Betriebs."""
    agent, stimme = agent_aufbauen()
    try:
        lage = agent.tools.team.lagebericht(agent.tools)
        text = lage.get("text") or lage.get("fehler", "Kein Stand abrufbar.")
        print("\n%s\n" % text)
        for name, bereich in (lage.get("bereiche") or {}).items():
            if isinstance(bereich, dict) and bereich.get("text"):
                print("  %-14s %s" % (name + ":", bereich["text"][:100]))
            elif isinstance(bereich, dict) and not bereich.get("ok", True):
                print("  %-14s nicht abrufbar: %s"
                      % (name + ":", bereich.get("fehler", "")[:70]))
        stimme.sprich(text)
        return 0
    finally:
        agent.tools.mcp.stoppen()


def buchhaltung_exportieren(argumente=None):
    """Schreibt die Buchungen als CSV für den Steuerberater."""
    argumente = argumente or []
    von = argumente[0] if len(argumente) > 0 else ""
    bis = argumente[1] if len(argumente) > 1 else ""
    agent, _ = agent_aufbauen(mit_stimme=False)
    try:
        ergebnis = agent.tools.bookkeeping.csv_export(von, bis)
        print(ergebnis.get("text") or ergebnis.get("fehler"))
        return 0 if ergebnis.get("ok") else 1
    finally:
        agent.tools.mcp.stoppen()


def stimmprofil_einlernen():
    """Lernt die Stimme des Nutzers ein."""
    stimme = Stimme()
    profil = Sprecherprofil()
    ergebnis = profil.einlernen(stimme)
    print(ergebnis.get("text") or ergebnis.get("fehler"))
    if ergebnis.get("ok"):
        config.env_setzen("STIMMPRUEFUNG_AN", "ja")
        stimme.sprich(ergebnis["text"])
    else:
        stimme.sprich(ergebnis.get("fehler", "Das hat nicht geklappt."))


def stimme_aussuchen():
    """Listet die ElevenLabs-Stimmen auf und speichert die gewählte."""
    if not config.ELEVENLABS_API_KEY:
        print("Für ElevenLabs ist kein Schlüssel hinterlegt. Ich benutze die "
              "Systemstimme von macOS - die kostet nichts und ist immer da.")
        stimme = Stimme()
        print("Aktuelle Systemstimme: %s" % (stimme.macos_stimme or "keine deutsche"))
        return
    try:
        anfrage = urllib.request.Request(
            "https://api.elevenlabs.io/v1/voices",
            headers={"xi-api-key": config.ELEVENLABS_API_KEY})
        with urllib.request.urlopen(anfrage, timeout=30) as antwort:
            daten = json.loads(antwort.read().decode("utf-8"))
    except (urllib.error.URLError, OSError, ValueError) as fehler:
        print("Die Stimmenliste ist nicht erreichbar: %s" % fehler)
        return

    stimmen = daten.get("voices", []) or []
    if not stimmen:
        print("Es sind keine Stimmen hinterlegt.")
        return

    def deutsch(eintrag):
        marken = " ".join(str(v) for v in (eintrag.get("labels") or {}).values()).lower()
        return any(w in marken for w in ("german", "deutsch", "austrian", "österreich"))
    # Eine deutsche Muttersprachlerstimme klingt am menschlichsten - die kommen zuerst.
    stimmen.sort(key=lambda e: (not deutsch(e), e.get("name", "")))
    if not any(deutsch(e) for e in stimmen):
        print("In deinem Konto ist noch keine deutsche Stimme. Am natürlichsten klingt eine "
              "deutsche Stimme aus der Voice Library von ElevenLabs (elevenlabs.io/app/voice-library, "
              "Sprache Deutsch). Dort \"Add to my voices\" und danach hier noch einmal wählen.\n")
    for nummer, eintrag in enumerate(stimmen, 1):
        marken = eintrag.get("labels") or {}
        print("%2d. %-22s %s" % (nummer, eintrag.get("name", "?"),
                                 ", ".join("%s: %s" % (k, v) for k, v in marken.items())))
    try:
        wahl = input("\nNummer der Stimme (Enter bricht ab): ").strip()
    except (EOFError, KeyboardInterrupt):
        return
    if not wahl.isdigit() or not (1 <= int(wahl) <= len(stimmen)):
        print("Nichts geändert.")
        return
    gewaehlt = stimmen[int(wahl) - 1]
    config.env_setzen("ELEVENLABS_VOICE_ID", gewaehlt.get("voice_id", ""))
    print("Gespeichert: %s" % gewaehlt.get("name"))
    Stimme().sprich("So klinge ich jetzt.")


# ---------------------------------------------------------------------------
# Selbsttest
# ---------------------------------------------------------------------------

def _marke(zustand: str) -> str:
    return {"ok": "[ok]", "fehlt": "[--]", "fehler": "[!!]"}.get(zustand, "[??]")


def selbsttest() -> int:
    """Geht jeden Baustein durch.

    ``[ok]`` läuft, ``[--]`` läuft ohne diese Funktion weiter, ``[!!]`` ist kaputt.
    """
    print(BANNER)
    print("SELBSTTEST\n" + "=" * 62)
    fehler_gesamt = 0

    def melden(name, zustand, hinweis=""):
        nonlocal fehler_gesamt
        if zustand == "fehler":
            fehler_gesamt += 1
        print("%s %-26s %s" % (_marke(zustand), name, hinweis))

    # -- Konfiguration --
    print("\nGrundlage")
    melden("Konfiguration", "ok", "Basis: %s" % config.BASIS)
    melden("Anthropic-Schlüssel", "ok" if config.ANTHROPIC_API_KEY else "fehlt",
           config.CLAUDE_MODEL if config.ANTHROPIC_API_KEY
           else "ohne ihn kann Jarvis nicht denken")

    # -- Agent und Gedächtnis --
    print("\nGedächtnis")
    try:
        agent = JarvisAgent()
        melden("Agent gestartet", "ok", "%d Werkzeuge" % len(agent.tools.namen()))
    except Exception as fehler:
        melden("Agent gestartet", "fehler", str(fehler))
        return 1

    memory = agent.memory
    try:
        notiz = memory.notiz_speichern("Selbsttest: Kunde Meier will Fensterreinigung",
                                       "test")
        gefunden = memory.notizen_suchen("Selbsttest")
        melden("Notiz speichern und finden", "ok" if gefunden else "fehler",
               "%d Treffer" % len(gefunden))
        memory.notiz_loeschen(notiz.get("id"))
    except Exception as fehler:
        melden("Notiz speichern und finden", "fehler", str(fehler))

    try:
        memory.kontakt_anlegen("Selbsttest Berger", "Berger GmbH")
        treffer = memory.kontakt_suchen("Selbsttest Berger")
        melden("Kontakt anlegen und suchen", "ok" if treffer else "fehler",
               "%d Treffer" % len(treffer))
    except Exception as fehler:
        melden("Kontakt anlegen und suchen", "fehler", str(fehler))

    try:
        block = agent.recall.gedaechtnis_block("Angebot Meier")
        melden("Gedächtnis nachschlagen", "ok", "%d Zeichen Kontext" % len(block))
    except Exception as fehler:
        melden("Gedächtnis nachschlagen", "fehler", str(fehler))

    # -- Buchhaltung --
    print("\nBuchhaltung")
    try:
        vorsteuer = mwst_aus_brutto(130.40, 20)
        melden("MwSt-Rechnung 130,40 bei 20%", "ok" if vorsteuer == 21.73 else "fehler",
               "%.2f Euro (erwartet 21,73)" % vorsteuer)
    except Exception as fehler:
        melden("MwSt-Rechnung", "fehler", str(fehler))

    try:
        auswertung = agent.tools.bookkeeping.auswertung()
        melden("Auswertung", "ok", auswertung["text"][:70])
        belege = agent.tools.bookkeeping.fehlende_belege()
        melden("Fehlende Belege", "ok", belege["text"][:70])
    except Exception as fehler:
        melden("Auswertung", "fehler", str(fehler))

    # -- Vertrieb --
    print("\nVertrieb")
    try:
        leads = agent.tools.call_analysis.offene_leads()
        melden("Offene Leads", "ok", leads["text"][:70])
        muster = agent.tools.call_analysis.verkaufsmuster()
        melden("Verkaufsmuster", "ok", muster["text"][:70])
    except Exception as fehler:
        melden("Vertrieb", "fehler", str(fehler))

    # -- Routinen --
    print("\nRoutinen")
    try:
        routinen = agent.tools.routines
        routinen.routine_anlegen("Selbsttest Tagesbericht", "Zahlen zusammenfassen",
                                 "18 Uhr")
        treffer = routinen.routine_finden("den Selbsttest Tages Bericht")
        melden("Routine mit ungenauem Namen finden",
               "ok" if treffer else "fehler",
               treffer["name"] if treffer else "nicht gefunden")
        geplant = routinen.geplante_routinen()
        melden("Routine im Zeitplan", "ok" if geplant else "fehler",
               "%d mit Uhrzeit" % len(geplant))
        routinen.routine_loeschen("Selbsttest Tagesbericht")
    except Exception as fehler:
        melden("Routinen", "fehler", str(fehler))

    # -- Zeitplan --
    print("\nZeitplan")
    try:
        from datetime import datetime as _dt
        pruefungen = [
            (_dt(2026, 1, 1, 9, 30), True, "9:30 bei 9:00-Job"),
            (_dt(2026, 1, 1, 8, 0), False, "8:00 bei 9:00-Job"),
            (_dt(2026, 1, 1, 14, 0), False, "14:00 bei 9:00-Job (zu spät)"),
        ]
        alle_ok = True
        for zeitpunkt, erwartet, name in pruefungen:
            tatsaechlich = ist_faellig("09:00", zeitpunkt)
            if tatsaechlich != erwartet:
                alle_ok = False
            melden(name, "ok" if tatsaechlich == erwartet else "fehler",
                   "%s (erwartet %s)" % (tatsaechlich, erwartet))
        del alle_ok
    except Exception as fehler:
        melden("Zeitplan", "fehler", str(fehler))

    # -- Sicherheit --
    print("\nSicherheit")
    try:
        abgewiesen = agent.tools.run("systeminfo", {"was": "rm -rf /"})
        melden("systeminfo mit 'rm -rf /' abgewiesen",
               "ok" if not abgewiesen.get("ok") else "fehler",
               abgewiesen.get("fehler", "")[:60])
        abgewiesen = agent.tools.run("ordner_zeigen", {"pfad": ".;rm -rf /"})
        melden("ordner_zeigen mit ';' abgewiesen",
               "ok" if not abgewiesen.get("ok") else "fehler",
               abgewiesen.get("fehler", "")[:60])
        unbekannt = agent.tools.run("beliebiger_befehl", {})
        melden("Unbekanntes Werkzeug abgewiesen",
               "ok" if not unbekannt.get("ok") else "fehler", "")
        pflichtig = sorted(n for n in agent.tools.namen()
                           if agent.tools.braucht_freigabe(n))
        melden("Freigabepflichtige Werkzeuge", "ok", ", ".join(pflichtig))
    except Exception as fehler:
        melden("Sicherheit", "fehler", str(fehler))

    # -- MCP --
    print("\nMCP")
    try:
        vorlage_schreiben()
        client = MCPClient()
        client.konfiguration_lesen()
        eingeschaltet = [name for name, eintrag in
                         (client.konfig.get("server") or {}).items()
                         if isinstance(eintrag, dict) and not eintrag.get("aus", True)]
        melden("Konfiguration", "ok",
               "%d Dienste hinterlegt, %d eingeschaltet"
               % (len(client.konfig.get("server") or {}), len(eingeschaltet)))
        testserver = os.path.join(str(config.BASIS), "tests", "mcp_testserver.py")
        if os.path.exists(testserver):
            probe = MCPClient()
            probe.konfig = {"server": {"test": {
                "aus": False, "befehl": sys.executable, "argumente": [testserver],
                "ohne_rueckfrage": ["liste_lesen"]}}}
            server = MCPServer("test", probe.konfig["server"]["test"])
            if server.starten():
                probe.server_hinzufuegen("test", server)
                werkzeuge = [w["name"] for w in probe.alle_werkzeuge()]
                melden("Testserver Werkzeuge", "ok" if len(werkzeuge) == 2 else "fehler",
                       ", ".join(werkzeuge))
                frei = probe.braucht_freigabe("mcp__test__liste_lesen")
                pflicht = probe.braucht_freigabe("mcp__test__datei_loeschen")
                melden("ohne_rueckfrage läuft durch",
                       "ok" if frei is False else "fehler", "")
                melden("Rest fragt nach", "ok" if pflicht is True else "fehler", "")
                ergebnis = probe.aufrufen("mcp__test__liste_lesen", {"was": "test"})
                melden("Testaufruf", "ok" if ergebnis.get("ok") else "fehler",
                       ergebnis.get("text", ergebnis.get("fehler", ""))[:50])
                server.stoppen()
            else:
                melden("Testserver", "fehler", server.fehler)
        else:
            melden("Testserver", "fehlt", "tests/mcp_testserver.py nicht gefunden")
    except Exception as fehler:
        melden("MCP", "fehler", str(fehler))

    # -- Sprache --
    print("\nSprache")
    try:
        stimme = Stimme()
        zustand = stimme.zustand()
        melden("Sprachausgabe macOS", "ok" if zustand["macos_say"] else "fehlt",
               zustand["macos_stimme"])
        melden("ElevenLabs", "ok" if zustand["elevenlabs"] else "fehlt",
               "optional, die Systemstimme reicht")
        melden("Mikrofon", "ok" if zustand["mikrofon"] else "fehlt",
               zustand.get("mikrofon_grund", ""))
        melden("Spracherkennung lokal", "ok" if zustand["whisper_lokal"] else "fehlt",
               "" if zustand["whisper_lokal"] else "Paket faster-whisper fehlt")
        melden("Spracherkennung API", "ok" if zustand["whisper_api"] else "fehlt",
               "optional")
        erkannt, rest = weckwort_pruefen("Hey Javis, wie sieht mein Tag aus?")
        melden("Weckwort erkennen", "ok" if erkannt else "fehler", "Rest: %s" % rest)
        profil = Sprecherprofil()
        melden("Stimmprofil", "ok" if profil.eingelernt() else "fehlt",
               "entscheidet nur, ob Jarvis zuhört - gibt nie etwas frei")
    except Exception as fehler:
        melden("Sprache", "fehler", str(fehler))

    # -- Außenwelt --
    print("\nAußenwelt")
    try:
        melden("E-Mail lesen", "ok" if agent.tools.mail.lesen_moeglich() else "fehlt", "")
        melden("E-Mail senden", "ok" if agent.tools.mail.senden_moeglich() else "fehlt", "")
        melden("Kalender", "ok" if agent.tools.kalender.verfuegbar() else "fehlt", "")
        melden("Telegram", "ok" if agent.tools.telegram.verfuegbar() else "fehlt",
               "ohne ihn fragt Jarvis im Terminal nach Freigaben")
        kamera = agent.tools.kamera.zustand()
        melden("Kamera", "ok" if kamera["verfuegbar"] else "fehlt",
               kamera["programm"] if kamera["verfuegbar"] else "brew install imagesnap")
        bildschirm = agent.tools.bildschirm.zustand()
        melden("Bildschirmsteuerung",
               "ok" if bildschirm.get("pyautogui") and bildschirm.get("pillow") else "fehlt",
               "Skalierung %s" % bildschirm.get("skalierung"))
        telefon = agent.tools.telefon.zustand()
        melden("Telefon", "ok" if telefon["eingerichtet"] else "fehlt",
               ("eigene Nummer %s" % telefon["eigene_nummer"])
               if telefon["eingerichtet"]
               else "fuer Anrufe und SMS: TWILIO_SID, TWILIO_TOKEN, TWILIO_NUMMER")
        browser = agent.tools.browser.zustand()
        melden("Browser-Steuerung", "ok" if browser["verfuegbar"] else "fehlt",
               browser["hinweis"])
        wetter = agent.tools.welt.wetter(config.WETTER_ORT)
        melden("Wetter", "ok" if wetter.get("ok") else "fehlt",
               (wetter.get("text") or wetter.get("fehler", ""))[:60])
    except Exception as fehler:
        melden("Außenwelt", "fehler", str(fehler))

    # -- Dashboard --
    print("\nDashboard")
    try:
        ergebnis = agent.tools.dashboard.bauen()
        melden("Command Center bauen", "ok" if ergebnis.get("ok") else "fehler",
               ergebnis.get("datei", ergebnis.get("fehler", "")))
    except Exception as fehler:
        melden("Command Center bauen", "fehler", str(fehler))

    agent.tools.mcp.stoppen()

    print("\n" + "=" * 62)
    if fehler_gesamt == 0:
        print("Alles, was eingerichtet ist, funktioniert. [--] heißt nicht kaputt,")
        print("sondern: läuft ohne diese Funktion weiter.")
    else:
        print("%d Prüfungen sind fehlgeschlagen. Details stehen oben bei [!!]."
              % fehler_gesamt)
    print("=" * 62)
    return 0 if fehler_gesamt == 0 else 1


# ---------------------------------------------------------------------------
# Einstieg
# ---------------------------------------------------------------------------

def hauptprogramm(argumente=None) -> int:
    """Wählt die Betriebsart anhand des ersten Arguments."""
    argumente = argumente if argumente is not None else sys.argv[1:]
    modus = (argumente[0].strip().lower() if argumente else "")

    config.verzeichnisse_anlegen()
    vorlage_schreiben()

    if modus in ("", "start", "web", "browser", "app"):
        if not config.EINRICHTUNG_FERTIG and not config.ANTHROPIC_API_KEY:
            print("Jarvis ist noch nicht eingerichtet. Ich starte die Einrichtung.")
            einrichtung_starten()
            return 0
        return webbetrieb(argumente[1:] if argumente else [])
    elif modus in ("hoeren", "hören", "dauerbetrieb", "sprechen"):
        if not config.EINRICHTUNG_FERTIG and not config.ANTHROPIC_API_KEY:
            print("Jarvis ist noch nicht eingerichtet. Ich starte die Einrichtung.")
            einrichtung_starten()
            return 0
        dauerbetrieb()
    elif modus == "chat":
        chatbetrieb()
    elif modus == "telegram":
        telegrambetrieb()
    elif modus == "briefing":
        briefing_sofort(abends=False)
    elif modus in ("abend", "abendrueckblick", "feierabend"):
        briefing_sofort(abends=True)
    elif modus == "dashboard":
        dashboard_bauen()
    elif modus == "export":
        return buchhaltung_exportieren(argumente[1:])
    elif modus in ("status", "lage"):
        return lage_sagen()
    elif modus == "stimme":
        stimmprofil_einlernen()
    elif modus == "stimmen":
        stimme_aussuchen()
    elif modus == "test":
        return selbsttest()
    elif modus in ("einrichten", "setup"):
        einrichtung_starten()
    elif modus in ("daemon", "dienstbetrieb"):
        if not config.EINRICHTUNG_FERTIG and not config.ANTHROPIC_API_KEY:
            print("Jarvis ist noch nicht eingerichtet. Starte: python3 jarvis.py einrichten")
            return 1
        return dauerbetrieb(dienst=True) or 0
    elif modus == "dienst":
        return dienst_verwalten(argumente[1:])
    elif modus == "anzeige":
        return anzeige_oeffnen(argumente[1:])
    elif modus in ("macapp", "mac-app", "programm"):
        return macapp_anlegen(argumente[1:])
    elif modus == "autopilot":
        return autopilot_zeigen(argumente[1:])
    elif modus in ("zugang", "schluessel", "schlüssel"):
        return 0 if zugang_eintragen(argumente[1] if len(argumente) > 1 else "") else 1
    # Neue Betriebsarten der Pakete, je als "elif modus == ...:".
    # [P1 Bühne] Anfang
    # [P1 Bühne] Ende
    # [P2 Weltlage] Anfang
    # [P2 Weltlage] Ende
    # [P3 Telefon] Anfang
    # [P3 Telefon] Ende
    # [P4 Büro] Anfang
    # [P4 Büro] Ende
    # [P5 Sicht] Anfang
    # [P5 Sicht] Ende
    # [P6 Stimme] Anfang
    # [P6 Stimme] Ende
    # [P7 Start] Anfang
    elif modus == "hardware":
        print(hardware_text(hardware_bericht(stimme=Stimme(), tools=JarvisAgent().tools)))
        return 0
    # [P7 Start] Ende
    elif modus in ("hilfe", "--help", "-h", "help"):
        print(__doc__)
    else:
        print("Die Betriebsart '%s' kenne ich nicht.\n" % modus)
        print(__doc__)
        return 2
    return 0
