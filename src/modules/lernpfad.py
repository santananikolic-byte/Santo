#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Der Lernpfad - sieben Welten, in denen Jarvis Stück für Stück wächst.

Jeder Haken hier wird **aus dem echten Stand** gerechnet: Schlüssel in der
Konfiguration, Einträge im Gedächtnis, Zeilen im Gedankenlog. Niemand hakt
von Hand etwas ab, das nicht stimmt - steht ein Haken da, ist es wahr.

Eine Welt öffnet sich, sobald in der davor alle **Pflicht-Level** erledigt
sind. Freiwillige Level (Telegram, Kalender, Kamera ...) zählen mit, sperren
aber nichts: wer sie nicht braucht, soll nicht daran hängen bleiben.
"""

import importlib.util
import sys

import config
from modules.router import Gedankenlog


def _modul_da(name: str) -> bool:
    try:
        return importlib.util.find_spec(name) is not None
    except (ImportError, ValueError):
        return False


# Jedes Level: (kennung, Titel, Beschreibung, Pflicht?, Wie es sich erledigt)
WELTEN = [
    {"nummer": 1, "name": "Das Fundament",
     "text": "Jarvis läuft auf deinem Rechner und kennt dich.",
     "level": [
         ("einrichtung", "Die Einrichtung", "Einmal durchlaufen, damit alles angelegt ist.", True,
          "Hier steht dein Anthropic-Schlüssel und die Einrichtung ist durch."),
         ("name", "Dein Name", "Damit er dich ansprechen kann.", True,
          "Dein Name steht in der Konfiguration."),
     ]},
    {"nummer": 2, "name": "Der Verstand",
     "text": "Seine Zugänge: gründliches Denken, schnelles Denken, Stimme, Ohren. "
             "Alles sind deine eigenen Konten.",
     "level": [
         ("claude", "Sein Gehirn", "Claude für die gründliche Arbeit.", True,
          "Ein Anthropic-Schlüssel ist hinterlegt."),
         ("gemini", "Sein schnelles Denken", "Gemini für Gespräch und einfache Fragen.", True,
          "Ein Gemini-Schlüssel ist hinterlegt."),
         ("stimme", "Seine Stimme", "ElevenLabs, oder unter macOS die eingebaute.", False,
          "ElevenLabs ist eingerichtet oder du bist auf einem Mac."),
         ("ohren", "Seine Ohren", "Spracherkennung, lokal oder über OpenAI.", False,
          "Whisper ist installiert oder ein OpenAI-Schlüssel steht da."),
     ]},
    {"nummer": 3, "name": "Das Zuhause",
     "text": "Wo du ihn siehst und von unterwegs erreichst.",
     "level": [
         ("webapp", "Die Web-App", "Du schaust gerade hinein.", True,
          "Die Seite wird ausgeliefert - also läuft sie."),
         ("dashboard", "Das Cockpit", "Kennzahlen auf einen Blick.", True,
          "Das Command Center wurde schon einmal gebaut."),
         ("telegram", "Telegram", "Jarvis in der Hosentasche.", False,
          "Bot-Token und deine Chat-Nummer sind eingetragen."),
     ]},
    {"nummer": 4, "name": "Das Gedächtnis",
     "text": "Ohne Gedächtnis ist er ein gewöhnlicher Chatbot.",
     "level": [
         ("notiz", "Die erste Notiz", "Sag ihm, er soll sich etwas merken.", True,
          "Mindestens eine Notiz liegt im Gedächtnis."),
         ("kontakt", "Der erste Kontakt", "Ein Kunde, den er kennt.", True,
          "Mindestens ein Kontakt ist angelegt."),
         ("gespraech", "Zehn Sätze", "Er soll dich im Gespräch kennenlernen.", True,
          "Zehn Gesprächszeilen sind gespeichert."),
     ]},
    {"nummer": 5, "name": "Die Sinne",
     "text": "Was er von der Welt mitbekommt.",
     "level": [
         ("kalender", "Der Kalender", "Termine kennen und anlegen.", False,
          "Ein Kalender ist verbunden."),
         ("mail", "Das Postfach", "Mails lesen und Entwürfe schreiben.", False,
          "Postfach-Zugang ist eingetragen."),
         ("kamera", "Die Augen", "Sehen, was vor der Kamera liegt.", False,
          "Eine Kamera ist ansprechbar."),
     ]},
    {"nummer": 6, "name": "Der Zuruf",
     "text": "Du sprichst, er antwortet - ohne Knopf.",
     "level": [
         ("erstes_wort", "Das erste Wort", "Du sagst etwas, er antwortet.", True,
          "Es gibt mindestens eine Antwort von ihm."),
         ("freigabe", "Die erste Freigabe", "Er tut etwas - und hat vorher gefragt.", True,
          "Mindestens eine Aktion steht im Protokoll."),
     ]},
    {"nummer": 7, "name": "Master",
     "text": "Er wählt selbst das richtige Gehirn und achtet auf dein Geld.",
     "level": [
         ("router", "Beide Gehirne im Einsatz", "Eine Frage ging an Gemini, eine an Claude.", True,
          "Im Gedankenlog stehen Einträge von beiden."),
         ("limit", "Das Monatslimit", "Eine Grenze, damit nichts ausufert.", True,
          "Ein Limit über null ist gesetzt."),
         ("monitor", "Der Kostenblick", "Du siehst im Cockpit, was das Denken kostet.", False,
          "Es gibt Einträge im Gedankenlog."),
         ("autopilot", "Der Autopilot", "Er arbeitet im Hintergrund und legt Entwürfe ins Postfach.", False,
          "Der Autopilot ist eingeschaltet."),
     ]},
]


def _erledigt(kennung: str, werkzeuge, dashboard_gebaut: bool, statistik: dict,
              logzeilen: list) -> bool:
    if kennung == "einrichtung":
        return bool(config.ANTHROPIC_API_KEY and config.EINRICHTUNG_FERTIG)
    if kennung == "name":
        return bool(config.NUTZER_NAME and config.NUTZER_NAME != "Chef")
    if kennung == "claude":
        return bool(config.ANTHROPIC_API_KEY)
    if kennung == "gemini":
        return bool(config.GEMINI_API_KEY)
    if kennung == "stimme":
        return bool(config.ELEVENLABS_API_KEY) or sys.platform == "darwin"
    if kennung == "ohren":
        return (bool(config.OPENAI_API_KEY) or _modul_da("faster_whisper")
                or _modul_da("whisper"))
    if kennung == "webapp":
        return True
    if kennung == "dashboard":
        return dashboard_gebaut
    if kennung == "telegram":
        return bool(config.TELEGRAM_BOT_TOKEN and config.TELEGRAM_CHAT_ID)
    if kennung == "notiz":
        return statistik.get("notizen", 0) >= 1
    if kennung == "kontakt":
        return statistik.get("kontakte", 0) >= 1
    if kennung == "gespraech":
        return statistik.get("verlauf", 0) >= 10
    if kennung == "kalender":
        return bool(config.CALDAV_URL and config.CALDAV_USER)
    if kennung == "mail":
        return bool(config.IMAP_HOST and config.IMAP_USER)
    if kennung == "kamera":
        try:
            return bool(werkzeuge.kamera.verfuegbar())
        except Exception:
            return False
    if kennung == "erstes_wort":
        return statistik.get("verlauf", 0) >= 2
    if kennung == "freigabe":
        return statistik.get("aktionen", 0) >= 1
    if kennung == "router":
        gehirne = {z.get("gehirn") for z in logzeilen}
        return {"gemini", "claude"} <= gehirne
    if kennung == "limit":
        return config.MONATSLIMIT_EURO > 0
    if kennung == "autopilot":
        return bool(config.AUTOPILOT_AN)
    if kennung == "monitor":
        return bool(logzeilen)
    return False


def lernpfad_stand(werkzeuge) -> dict:
    """Rechnet den Lernpfad aus dem echten Stand von Jarvis."""
    try:
        statistik = werkzeuge.memory.statistik()
    except Exception:
        statistik = {}
    try:
        logzeilen = Gedankenlog().zeilen()
    except Exception:
        logzeilen = []
    dashboard_gebaut = (config.DASHBOARD_VERZEICHNIS / "dashboard.html").exists()

    welten, vorige_offen = [], False
    gesamt = erledigt_gesamt = 0
    for vorlage in WELTEN:
        level, pflicht_offen = [], 0
        for nummer, (kennung, titel, text, pflicht, haken) in enumerate(
                vorlage["level"], start=1):
            fertig = _erledigt(kennung, werkzeuge, dashboard_gebaut, statistik, logzeilen)
            level.append({"nummer": nummer, "kennung": kennung, "titel": titel,
                          "text": text, "pflicht": pflicht, "haken": haken,
                          "erledigt": fertig})
            gesamt += 1
            erledigt_gesamt += 1 if fertig else 0
            if pflicht and not fertig:
                pflicht_offen += 1
        erledigt = sum(1 for l in level if l["erledigt"])
        welten.append({"nummer": vorlage["nummer"], "name": vorlage["name"],
                       "text": vorlage["text"], "level": level,
                       "gesperrt": vorige_offen, "erledigt": erledigt,
                       "gesamt": len(level),
                       "abgeschlossen": pflicht_offen == 0 and erledigt > 0
                                        and not vorige_offen})
        vorige_offen = vorige_offen or pflicht_offen > 0
    return {"ok": True, "welten": welten, "erledigt": erledigt_gesamt, "gesamt": gesamt}


SEITE_PFAD = r"""<!DOCTYPE html>
<html lang="de"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<link rel="icon" href="/symbol.svg" type="image/svg+xml">
<title>Jarvis – Der Pfad</title>
<style>
:root{--grund:#F4F1F6;--karte:#fff;--text:#1B1B1F;--leise:#8A8790;--kupfer:#B8694B;
 --kupfer-hell:#F0DDD3;--gruen:#4E8A3E;--gruen-hell:#E4F2DE;--rand:#ECE8EE;
 --sans:-apple-system,BlinkMacSystemFont,"Helvetica Neue",Arial,sans-serif}
@media (prefers-color-scheme:dark){:root{--grund:#14121A;--karte:#1E1B25;--text:#F2EFEA;
 --leise:#9B97A3;--kupfer:#E19272;--kupfer-hell:#3A2A24;--gruen:#7CC36B;
 --gruen-hell:#223220;--rand:#2B2733}}
*{box-sizing:border-box;margin:0;padding:0}
body{background:var(--grund);color:var(--text);font-family:var(--sans);
 -webkit-font-smoothing:antialiased;padding:0 16px 40px;max-width:560px;margin:0 auto}
a{color:var(--kupfer);text-decoration:none;font-weight:600}
.kopf{padding:22px 0 8px}.kopf h1{font-size:26px;margin-top:10px}
.kopf p{color:var(--leise);margin-top:6px;font-size:15px;line-height:1.5}
.balken{height:8px;border-radius:8px;background:var(--rand);margin:16px 0 4px;overflow:hidden}
.balken i{display:block;height:100%;background:var(--kupfer);border-radius:8px}
.stand{color:var(--leise);font-size:13px}
.welt{display:flex;flex-direction:column;align-items:center;margin:34px 0 0}
.planet{width:112px;height:112px;border-radius:50%;position:relative;
 background:radial-gradient(circle at 34% 30%,#fff 0,#D9D4D2 38%,#A8A29F 100%);
 box-shadow:0 0 0 12px rgba(184,105,75,.10),0 12px 26px rgba(0,0,0,.14)}
.planet.offen{background:radial-gradient(circle at 34% 30%,#FFE9DC 0,#DCA487 45%,#B8694B 100%)}
.planet.fertig{background:radial-gradient(circle at 34% 30%,#fff 0,#B7DDA8 45%,#4E8A3E 100%)}
.planet.zu{filter:grayscale(.6);opacity:.75}
.planet b{position:absolute;right:-4px;bottom:18px;width:34px;height:34px;border-radius:50%;
 background:#6B6A72;color:#fff;display:grid;place-items:center;font-size:15px;
 border:3px solid var(--grund)}
.planet.fertig b{background:var(--gruen)}
.schild{background:var(--karte);border-radius:20px;padding:14px 22px;margin-top:-14px;
 text-align:center;box-shadow:0 6px 20px rgba(0,0,0,.07);min-width:220px;position:relative}
.schild small{letter-spacing:.16em;font-size:11px;color:var(--leise);font-weight:700}
.schild h2{font-size:19px;margin:3px 0}
.schild span{font-size:13px;color:var(--leise)}
.schild.zu h2{color:var(--leise)}
.level{background:var(--karte);border-radius:18px;padding:14px 16px;margin-top:10px;
 width:100%;display:flex;gap:12px;align-items:flex-start;border:1px solid var(--rand)}
.level .zahl{flex:none;width:30px;height:30px;border-radius:50%;background:var(--kupfer-hell);
 color:var(--kupfer);font-weight:700;display:grid;place-items:center}
.level.fertig .zahl{background:var(--gruen-hell);color:var(--gruen)}
.level>div:nth-child(2){min-width:0;flex:1}.level h3{font-size:16px}.level p{font-size:13px;color:var(--leise);margin-top:3px;line-height:1.45}
.level em{font-style:normal;font-size:11px;color:var(--leise);border:1px solid var(--rand);
 border-radius:9px;padding:1px 7px;margin-left:6px;vertical-align:middle}
.level .mark{margin-left:auto;white-space:nowrap;flex:none;font-size:13px;font-weight:700;color:var(--leise)}
.level.fertig .mark{color:var(--gruen)}
.liste{width:100%;margin-top:6px}
.fuss{margin-top:44px;color:var(--leise);font-size:12px;text-align:center;line-height:1.6}
</style></head><body>
<div class="kopf"><a href="/" id="zurueck">‹ Zurück zu Jarvis</a>
<h1>Der Pfad</h1>
<p>Sieben Welten, in denen dein Jarvis wächst. Jeder Haken ist echt: er steht
nur da, wenn es wirklich eingerichtet ist.</p>
<div class="balken"><i id="gesamt" style="width:0"></i></div>
<div class="stand" id="stand">Stand wird geholt …</div></div>
<div id="welten"></div>
<div class="fuss">Alles läuft lokal auf diesem Rechner.<br>
Schlüssel trägst du nur im Terminal ein (<b>jarvis.py zugang</b>), nie in einem Chat.</div>
<script>
const SCHLUESSEL="{{SCHLUESSEL}}";
function esc(t){return String(t).replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]))}
const ANHANG=SCHLUESSEL?"?schluessel="+encodeURIComponent(SCHLUESSEL):"";
document.getElementById("zurueck").href="/"+ANHANG;
fetch("/api/pfad"+ANHANG)
 .then(r=>r.json()).then(d=>{
  document.getElementById("gesamt").style.width=(100*d.erledigt/Math.max(d.gesamt,1))+"%";
  document.getElementById("stand").textContent=d.erledigt+" von "+d.gesamt+" Haken";
  document.getElementById("welten").innerHTML=d.welten.map(w=>{
   const klasse=w.gesperrt?"zu":(w.abgeschlossen?"fertig":"offen");
   const zeichen=w.gesperrt?"🔒":(w.abgeschlossen?"✓":w.erledigt+"/"+w.gesamt);
   const status=w.gesperrt?"Gesperrt":(w.abgeschlossen?"Abgeschlossen":w.erledigt+" von "+w.gesamt+" Haken");
   const level=w.gesperrt?"":'<div class="liste">'+w.level.map(l=>
    '<div class="level '+(l.erledigt?"fertig":"")+'"><div class="zahl">'+l.nummer+'</div><div>'+
    '<h3>'+esc(l.titel)+(l.pflicht?"":"<em>freiwillig</em>")+'</h3><p>'+esc(l.erledigt?l.haken:l.text)+
    '</p></div><div class="mark">'+(l.erledigt?"✓ Erledigt":"Offen")+'</div></div>').join("")+"</div>";
   return '<div class="welt"><div class="planet '+klasse+'"><b>'+zeichen+'</b></div>'+
    '<div class="schild '+(w.gesperrt?"zu":"")+'"><small>WELT '+w.nummer+'</small><h2>'+esc(w.name)+
    '</h2><span>'+(w.gesperrt?"🔒 ":"")+status+'</span></div>'+
    (w.gesperrt?"":'<p class="stand" style="margin-top:10px;text-align:center">'+esc(w.text)+'</p>')+level+'</div>'}).join("");
 }).catch(()=>{document.getElementById("stand").textContent="Der Stand ist nicht erreichbar."});
</script></body></html>
"""
