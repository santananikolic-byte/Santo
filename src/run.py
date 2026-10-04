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
    python3 jarvis.py zugang      einen Schlüssel eintragen oder ersetzen
"""

import json
import os
import sys
import time
import urllib.error
import urllib.request

import config
from agent import JarvisAgent
from modules.bookkeeping import mwst_aus_brutto
from modules.memory import Memory
from modules.mcp_client import MCPClient, MCPServer, vorlage_schreiben
from modules.scheduler import Scheduler, ist_faellig
from modules.setup_wizard import einrichtung_starten, zugang_eintragen
from modules.speaker import Sprecherprofil
from modules.voice import Stimme, weckwort_pruefen
from modules.webapp import JarvisWeb, STANDARD_PORT

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

def dauerbetrieb():
    """Hört auf das Weckwort und meldet sich zu den eingestellten Zeiten."""
    print(BANNER)
    agent, stimme = agent_aufbauen()
    profil = Sprecherprofil()

    zeitplan = Scheduler(agent=agent, routines=agent.tools.routines,
                         ausgabe=stimme.sprich)
    zeitplan.start()
    print("[zeitplan] Morgens %s, abends %s." % (config.BRIEFING_MORGENS,
                                                 config.BRIEFING_ABENDS))
    for eintrag in zeitplan.uebersicht():
        print("           %s  %s" % (eintrag["uhrzeit"], eintrag["beschreibung"]))

    if not stimme.mikrofon_bereit():
        print("\n[!] Kein Mikrofonzugriff. Ich wechsle in den Tippbetrieb.")
        stimme.sprich("Ich komme nicht an das Mikrofon. Wir tippen erst einmal.")
        zeitplan.stop()
        return chatbetrieb(agent, stimme)

    if not agent.einsatzbereit():
        stimme.sprich("Es ist kein Anthropic-Schlüssel hinterlegt. Starte bitte einmal "
                      "die Einrichtung.")
        print("Starte die Einrichtung mit: python3 jarvis.py einrichten")

    stimme.sprich("Ich bin da. Sag Hey Jarvis, wenn du etwas brauchst.")
    print("\nIch höre zu. Abbrechen mit Strg und C.\n")

    try:
        while True:
            pfad = stimme.aufnehmen_bis_pause(still_signal=True)
            if not pfad:
                continue
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
                nachtrag = stimme.zuhoeren()
                if not nachtrag:
                    continue
                befehl = nachtrag

            print("Du: %s" % befehl)
            try:
                agent.antworten(befehl)
            except Exception as fehler:
                stimme.signal("fehler")
                print("[fehler] %s" % fehler)
                stimme.sprich("Da ist etwas schiefgegangen: %s" % fehler)
    except KeyboardInterrupt:
        print("\nBis später.")
        stimme.sprich("Bis später.")
    finally:
        zeitplan.stop()
        agent.tools.mcp.stoppen()


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
    port = STANDARD_PORT
    for teil in argumente:
        if teil.isdigit():
            port = int(teil)

    print(BANNER)
    agent, stimme = agent_aufbauen(mit_stimme=False)
    del stimme
    web = JarvisWeb(agent, port=port, offen=offen)

    # Der Zeitplan meldet in die Web-App, nicht ins Terminal - dort schaut
    # um 6:45 niemand hin.
    zeitplan = Scheduler(agent=agent, routines=agent.tools.routines,
                         ausgabe=web.melden)
    zeitplan.start()
    print("  Briefings: morgens %s, abends %s"
          % (config.BRIEFING_MORGENS, config.BRIEFING_ABENDS))

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
    if _shutil.which("open"):
        try:
            _subprocess.run(["open", adresse], shell=False, timeout=15,
                            stdout=_subprocess.DEVNULL, stderr=_subprocess.DEVNULL)
        except (OSError, _subprocess.SubprocessError):
            pass

    try:
        web.starten(blockierend=True)
    except KeyboardInterrupt:
        pass
    finally:
        zeitplan.stop()
        web.stoppen()
        agent.tools.mcp.stoppen()
    print("\nBeendet.")
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
    elif modus in ("zugang", "schluessel", "schlüssel"):
        return 0 if zugang_eintragen(argumente[1] if len(argumente) > 1 else "") else 1
    elif modus in ("hilfe", "--help", "-h", "help"):
        print(__doc__)
    else:
        print("Die Betriebsart '%s' kenne ich nicht.\n" % modus)
        print(__doc__)
        return 2
    return 0
