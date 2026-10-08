#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Der Dolmetscher mit Untertiteln.

Du sprichst Deutsch, der Gast seine Sprache; Jarvis übersetzt hin und her, liest die
Übersetzung vor und zeigt beide Sprachen als Untertitel – auf der Seite ``/dolmetscher``
und auf der Zentrale (Kanal ``untertitel`` der Anzeige).

**Rundenweise, nicht gleichzeitig.** Die Spracherkennung des Browsers liefert einen
Satz erst nach einer kurzen Pause; dann wird übersetzt, dann vorgelesen. Das dauert
pro Satz grob 1,5 bis 3 Sekunden (Schätzung – die Seite zeigt die gemessene Zeit).
Wirklich gleichzeitiges Übersetzen wäre ein anderes Verfahren und ist hier nicht gebaut.

**Wer übersetzt.** Gemini, wenn ein Schlüssel da ist (schnell, im Free Tier gratis),
sonst Claude über ``text_anfrage`` mit niedriger Denktiefe – das zählt zum Monatslimit.
``DOLMETSCHER_GEHIRN`` legt es fest.

**Datenschutz.** Die Seite speichert nichts auf dem Server; der Verlauf lebt nur im
Fenster. Der erkannte Text geht zum Übersetzen an Gemini oder Claude, der Ton der
Spracherkennung an den Hersteller des Browsers (siehe Hinweis auf der Seite).
"""

import json
import re
import shutil
import subprocess
import time
from datetime import datetime

import config
from modules.ansicht import BASIS_STIL
from modules.router import gemini_fragen
from modules.sprechtext import sprechstuecke, sprechstuecke_fremd

# Kürzel -> (Name auf Deutsch, Sprachkennung des Browsers)
SPRACHEN = {
    "de": ("Deutsch", "de-DE"),
    "en": ("Englisch", "en-GB"),
    "tr": ("Türkisch", "tr-TR"),
    "hr": ("Kroatisch", "hr-HR"),
    "sr": ("Serbisch", "sr-RS"),
    "bs": ("Bosnisch", "bs-BA"),
    "sq": ("Albanisch", "sq-AL"),
    "pl": ("Polnisch", "pl-PL"),
    "ro": ("Rumänisch", "ro-RO"),
    "hu": ("Ungarisch", "hu-HU"),
    "sk": ("Slowakisch", "sk-SK"),
    "cs": ("Tschechisch", "cs-CZ"),
    "bg": ("Bulgarisch", "bg-BG"),
    "uk": ("Ukrainisch", "uk-UA"),
    "ru": ("Russisch", "ru-RU"),
    "ar": ("Arabisch", "ar-SA"),
    "fa": ("Persisch", "fa-IR"),
    "it": ("Italienisch", "it-IT"),
    "fr": ("Französisch", "fr-FR"),
    "es": ("Spanisch", "es-ES"),
}

UEBERSETZER_SYSTEM = (
    "Du bist Dolmetscher zwischen {von_name} und {nach_name}. Übersetze nur die letzte "
    "Äußerung. Gib ausschließlich die Übersetzung aus – ohne Anführungszeichen, ohne "
    "Erklärung. Fachbegriffe der Gebäudereinigung (Unterhaltsreinigung, Grundreinigung, "
    "Baureinigung, Bauendreinigung, Glasreinigung, Leistungsverzeichnis) korrekt "
    "übertragen. Namen, Zahlen, Uhrzeiten und Beträge unverändert.")

# So lang darf eine Äußerung sein, und so viele Zeichen der Vorgeschichte sind erlaubt.
DOLMETSCHER_MAX_ZEICHEN = 1500
MAX_KONTEXT_ZEICHEN = 300
KONTEXT_RUNDEN = 4
# Antwortgrenze für die Übersetzung (das Denken zählt bei Gemini mit).
UEBERSETZEN_MAX_TOKENS = 3000
# Der Untertitel steht fünf Minuten auf der Zentrale.
UNTERTITEL_DAUER_S = 300

DOLMETSCHER_NUR_WEBAPP = ("Der Dolmetscher läuft in der Web-App – öffne Jarvis über das "
                    "Dock-Symbol.")


def sprachen_aktiv() -> list:
    """Die Gastsprachen, die der Dolmetscher anbietet (``DOLMETSCHER_SPRACHEN``), ohne Deutsch."""
    gesehen = []
    for teil in str(config.DOLMETSCHER_SPRACHEN or "").split(","):
        code = teil.strip().lower()
        if code in SPRACHEN and code != "de" and code not in gesehen:
            gesehen.append(code)
    return gesehen or [c for c in SPRACHEN if c != "de"]


def _unbekannte_sprache(code: str) -> str:
    moeglich = ", ".join("%s (%s)" % (name, kuerzel) for kuerzel, (name, _) in SPRACHEN.items())
    return "Die Sprache '%s' kenne ich nicht. Möglich: %s." % (str(code)[:12], moeglich)


def _kontext(verlauf) -> str:
    """Die letzten Äußerungen als Zeilen – nur zum Verständnis des Zusammenhangs."""
    zeilen = []
    for eintrag in list(verlauf or [])[-KONTEXT_RUNDEN:]:
        if isinstance(eintrag, dict):
            original = eintrag.get("original") or eintrag.get("text") or ""
            uebersetzung = eintrag.get("uebersetzung") or ""
        else:
            original, uebersetzung = eintrag, ""
        original = " ".join(str(original).split())[:MAX_KONTEXT_ZEICHEN]
        uebersetzung = " ".join(str(uebersetzung).split())[:MAX_KONTEXT_ZEICHEN]
        if original:
            zeilen.append("- %s%s" % (original, " → %s" % uebersetzung if uebersetzung else ""))
    return "\n".join(zeilen)


def _bereinigen(text: str) -> str:
    """Nimmt Anführungszeichen weg, die das Modell trotz Anweisung um die Übersetzung setzt."""
    text = str(text or "").strip()
    paare = (("\"", "\""), ("„", "“"), ("“", "”"), ("»", "«"), ("«", "»"), ("'", "'"))
    for auf, zu in paare:
        if len(text) > 1 and text.startswith(auf) and text.endswith(zu) \
                and auf not in text[1:-1] and zu not in text[1:-1]:
            return text[1:-1].strip()
    return text


def _gehirne(gehirn: str, agent) -> list:
    """Welche Übersetzer in welcher Reihenfolge in Frage kommen."""
    gehirn = (gehirn or "auto").strip().lower()
    gemini = bool(config.GEMINI_API_KEY)
    claude = False
    if agent is not None:
        einsatzbereit = getattr(agent, "einsatzbereit", None)
        claude = bool(einsatzbereit()) if callable(einsatzbereit) else bool(config.ANTHROPIC_API_KEY)
    if gehirn == "gemini":
        reihe = ["gemini"]
    elif gehirn == "claude":
        reihe = ["claude"]
    else:
        reihe = ["gemini", "claude"]
    return [g for g in reihe if (g == "gemini" and gemini) or (g == "claude" and claude)]


def uebersetzen(text: str, von: str, nach: str, verlauf=None, agent=None) -> dict:
    """Übersetzt eine Äußerung von einer Sprache in eine andere.

    ``verlauf`` sind die letzten Äußerungen (Zeichenketten oder Wörterbücher mit
    ``original`` und ``uebersetzung``); sie helfen bei Bezügen wie "das" oder "dort".
    Ergebnis: ``{"ok", "uebersetzung", "von", "nach", "sprechstuecke", "zeit"}`` oder
    ``{"ok": False, "fehler"}``. Gemini zuerst, sonst Claude (``text_anfrage``, niedrige
    Denktiefe – zählt zum Monatslimit).
    """
    von = str(von or "").strip().lower()
    nach = str(nach or "").strip().lower()
    for code in (von, nach):
        if code not in SPRACHEN:
            return {"ok": False, "fehler": _unbekannte_sprache(code)}
    if von == nach:
        return {"ok": False, "fehler": "Ausgangs- und Zielsprache sind gleich – es gibt nichts zu übersetzen."}
    text = str(text or "").strip()
    if not text:
        return {"ok": False, "fehler": "Es kam kein Text an."}
    if len(text) > DOLMETSCHER_MAX_ZEICHEN:
        return {"ok": False, "fehler": "Der Text ist zu lang (höchstens %d Zeichen)." % DOLMETSCHER_MAX_ZEICHEN}

    gehirne = _gehirne(config.DOLMETSCHER_GEHIRN, agent)
    if not gehirne:
        return {"ok": False, "fehler": "Zum Übersetzen brauche ich Gemini oder Claude – "
                                       "es ist kein Schlüssel hinterlegt."}
    system = UEBERSETZER_SYSTEM.format(von_name=SPRACHEN[von][0], nach_name=SPRACHEN[nach][0])
    kontext = _kontext(verlauf)
    beginn = time.time()
    fehler = ""
    antwort = ""
    benutzt = ""
    for gehirn in gehirne:
        try:
            if gehirn == "gemini":
                hinweis = ("\n\nLetzte Äußerungen (nur zum Verständnis des Zusammenhangs, nicht "
                           "übersetzen):\n%s" % kontext) if kontext else ""
                ergebnis = gemini_fragen(text, system + hinweis, verlauf=[],
                                         max_tokens=UEBERSETZEN_MAX_TOKENS)
            else:
                auftrag = system
                if kontext:
                    auftrag += "\n\nLetzte Äußerungen:\n%s" % kontext
                auftrag += "\n\nZu übersetzen:\n%s" % text
                ergebnis = agent.text_anfrage(auftrag, effort="low", max_tokens=2000)
        except Exception as ausnahme:
            ergebnis = {"ok": False, "fehler": str(ausnahme)}
        if isinstance(ergebnis, dict) and ergebnis.get("ok") and str(ergebnis.get("text") or "").strip():
            antwort = _bereinigen(ergebnis["text"])
            benutzt = gehirn
            break
        fehler = (ergebnis or {}).get("fehler") if isinstance(ergebnis, dict) else ""
        fehler = fehler or "Die Übersetzung ist leer geblieben."
    if not antwort:
        return {"ok": False, "fehler": "Die Übersetzung hat nicht geklappt: %s" % fehler}
    stuecke = sprechstuecke(antwort) if nach == "de" else sprechstuecke_fremd(antwort)
    return {"ok": True, "uebersetzung": antwort, "von": von, "nach": nach,
            "sprechstuecke": stuecke, "gehirn": benutzt,
            "dauer_ms": int((time.time() - beginn) * 1000),
            "zeit": datetime.now().isoformat(timespec="seconds")}


def untertitel_veroeffentlichen(tools, original: str, ergebnis: dict, sprecher: str = "gast",
                                von: str = "", nach: str = "") -> bool:
    """Schreibt die Runde in den Kanal 'untertitel' und schaltet die Zentrale darauf um.

    ``von`` und ``nach`` gelten, wenn das Ergebnis sie nicht selbst nennt. Nie eine
    Ausnahme: die Anzeige darf das Übersetzen nicht kaputt machen. Gibt zurück, ob der
    Untertitel angenommen wurde.
    """
    try:
        sprecher = sprecher if sprecher in ("ich", "gast") else "gast"
        version = tools.anzeige.melden("untertitel", {
            "von": str(ergebnis.get("von") or von), "nach": str(ergebnis.get("nach") or nach),
            "original": str(original or "")[:DOLMETSCHER_MAX_ZEICHEN],
            "uebersetzung": str(ergebnis.get("uebersetzung") or ""),
            "sprecher": sprecher,
            "zeit": str(ergebnis.get("zeit") or datetime.now().isoformat(timespec="seconds"))})
        tools.anzeige.zeigen("untertitel", {}, UNTERTITEL_DAUER_S, quelle="dolmetscher")
        return version is not None and version >= 0
    except Exception as fehler:
        print("[dolmetscher] Untertitel: %s" % fehler)
        return False


# -- Werkzeug dolmetscher_starten ---------------------------------------------------------

def _mac_oeffnen(adresse: str):
    """Öffnet eine Adresse im Standardbrowser des Macs. ``None``, wenn es hier kein ``open`` gibt."""
    if not shutil.which("open"):
        return None
    try:
        lauf = subprocess.run(["open", adresse], shell=False, timeout=15,
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except (OSError, subprocess.SubprocessError):
        return False
    return lauf.returncode == 0


def dolmetscher_adresse(web, nach: str) -> str:
    """Die Adresse der Dolmetscher-Seite der laufenden Web-App, mit Schlüssel falls nötig."""
    kopf, _, anhang = str(web.adresse()).partition("?")
    adresse = kopf.rstrip("/") + "/dolmetscher?nach=" + nach
    return adresse + ("&" + anhang if anhang else "")


def dolmetscher_starten(nach: str, web=None, oeffnen=None) -> dict:
    """Öffnet die Dolmetscher-Seite – nur möglich, wenn die Web-App läuft.

    ``web`` ist die laufende Web-App (``JarvisWeb``), ``oeffnen(adresse)`` der Öffner
    (Standard: ``open`` auf dem Mac; Prüfungen speisen einen Fälscher ein und öffnen nie
    ein Fenster). Im Dienst gibt es die Seite nicht – das wird ehrlich gesagt.
    """
    nach = str(nach or "").strip().lower()
    if nach not in SPRACHEN or nach == "de":
        return {"ok": False, "fehler": _unbekannte_sprache(nach)}
    if web is None or getattr(web, "server", None) is None:
        return {"ok": False, "fehler": DOLMETSCHER_NUR_WEBAPP}
    name = SPRACHEN[nach][0]
    adresse = dolmetscher_adresse(web, nach)
    ohne_schluessel = adresse.partition("&schluessel=")[0]
    try:
        geoeffnet = (oeffnen or _mac_oeffnen)(adresse)
    except Exception as fehler:
        return {"ok": False, "fehler": "Ich konnte die Seite nicht öffnen: %s" % fehler}
    if geoeffnet is None:
        return {"ok": True, "adresse": ohne_schluessel,
                "text": "Öffne diese Adresse im Browser: %s (Du sprichst Deutsch, der Gast %s.)"
                        % (ohne_schluessel, name)}
    if not geoeffnet:
        return {"ok": False, "fehler": "Der Browser ließ sich nicht öffnen. Adresse: %s" % ohne_schluessel}
    return {"ok": True, "adresse": ohne_schluessel,
            "text": "Der Dolmetscher ist offen: Du sprichst Deutsch, der Gast %s." % name}


# -- Die Seite ------------------------------------------------------------------------------

SEITE_DOLMETSCHER = r"""<!DOCTYPE html>
<html lang="de"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<link rel="icon" href="/symbol.svg" type="image/svg+xml">
<title>Jarvis – Dolmetscher</title>
<style>
""" + BASIS_STIL + r"""
html,body{height:auto;min-height:100%;overflow:auto}
body{display:flex;flex-direction:column;
 background:radial-gradient(ellipse 120% 70% at 50% 120%,#1a0d07 0%,var(--grund) 62%)}
button,select,input{font:inherit;color:inherit}
button{cursor:pointer}
:focus-visible{outline:2px solid var(--orange);outline-offset:3px;border-radius:8px}
.kopf{flex:none;display:flex;align-items:center;justify-content:space-between;gap:16px;flex-wrap:wrap;
 padding:16px max(16px,env(safe-area-inset-left)) 12px}
.kopf h1{font:600 13px var(--mono);letter-spacing:.42em;color:var(--glut);text-transform:uppercase}
.status{display:flex;align-items:center;gap:10px;font:500 12px var(--mono);letter-spacing:.2em;
 color:var(--hell);text-transform:uppercase}
.status i{width:9px;height:9px;border-radius:50%;background:var(--leise)}
.status[data-z="hoert"] i{background:var(--gruen);box-shadow:0 0 14px var(--gruen);animation:atmen 1.1s ease-in-out infinite}
.status[data-z="uebersetzt"] i{background:#fff;box-shadow:0 0 16px #fff;animation:atmen .6s ease-in-out infinite}
.status[data-z="spricht"] i{background:var(--orange);box-shadow:0 0 14px var(--orange);animation:atmen .8s ease-in-out infinite}
.status[data-z="fehler"] i{background:var(--rot);box-shadow:0 0 14px var(--rot)}
@keyframes atmen{50%{transform:scale(1.6);opacity:.5}}
main{flex:1;width:100%;max-width:1100px;margin:0 auto;display:flex;flex-direction:column;gap:18px;
 padding:6px max(16px,env(safe-area-inset-left)) 24px}
.wahl{display:grid;grid-template-columns:1fr 1fr;gap:14px}
.gross{display:flex;flex-direction:column;align-items:flex-start;justify-content:center;gap:6px;min-height:110px;
 padding:18px 22px;border-radius:16px;border:2px solid var(--linie);background:rgba(255,255,255,.03);text-align:left}
.gross b{font:600 clamp(20px,3.4vw,30px) var(--sans)}
.gross small{font:500 12px var(--mono);letter-spacing:.14em;color:var(--leise);text-transform:uppercase}
.gross:hover{border-color:var(--glut)}
.gross[data-an="true"]{border-color:var(--orange);background:rgba(255,106,31,.14);box-shadow:0 0 28px rgba(255,106,31,.18)}
.gast{gap:10px;cursor:default}
.gast button.sprecher{display:flex;flex-direction:column;align-items:flex-start;gap:4px;width:100%;
 background:none;border:none;padding:0;text-align:left}
.gast select{width:100%;padding:10px 12px;border-radius:10px;border:1px solid var(--linie);
 background:var(--tief);font-size:17px}
.steuer{display:flex;flex-wrap:wrap;gap:14px;align-items:center}
.steuer label{display:flex;gap:8px;align-items:center;font:500 13px var(--mono);letter-spacing:.1em;color:var(--hell)}
.knopf{padding:9px 16px;border-radius:10px;border:1px solid var(--linie);background:rgba(255,255,255,.04);
 font:500 12px var(--mono);letter-spacing:.14em;text-transform:uppercase}
.knopf:hover{border-color:var(--glut)}
.untertitel{border:1px solid var(--linie);border-radius:16px;padding:20px 22px;min-height:230px;
 background:rgba(13,7,5,.7);display:flex;flex-direction:column;gap:14px}
.vorlaeufig{min-height:1.3em;font:400 15px var(--sans);color:var(--leise);font-style:italic}
.zeile{display:flex;flex-direction:column;gap:4px}
.etikett{font:500 11px var(--mono);letter-spacing:.24em;color:var(--leise);text-transform:uppercase}
.alt .text{font:400 clamp(16px,2.2vw,20px) var(--sans);color:var(--text);opacity:.8}
.neu .text{font:600 clamp(26px,5vw,50px)/1.18 var(--sans);color:var(--hell)}
.takt{font:500 12px var(--mono);letter-spacing:.1em;color:var(--leise)}
.tippen{display:flex;gap:10px}
.tippen input{flex:1;min-width:0;padding:11px 14px;border-radius:10px;border:1px solid var(--linie);
 background:var(--tief);font-size:16px}
.verlauf h2{font:600 11px var(--mono);letter-spacing:.3em;color:var(--leise);text-transform:uppercase;margin:6px 0 10px}
.verlauf ol{list-style:none;display:flex;flex-direction:column;gap:10px}
.verlauf li{border-left:3px solid var(--linie);padding:2px 0 2px 12px}
.verlauf li[data-sprecher="ich"]{border-left-color:var(--orange)}
.verlauf li small{display:block;font:500 11px var(--mono);letter-spacing:.14em;color:var(--leise);text-transform:uppercase}
.verlauf li span{display:block}
.verlauf li .u{font-weight:600;color:var(--hell)}
.leer{font:400 14px var(--sans);color:var(--leise)}
.hinweise{flex:none;max-width:1100px;width:100%;margin:0 auto;padding:6px max(16px,env(safe-area-inset-left)) 28px;
 font:400 12.5px/1.55 var(--sans);color:var(--leise);display:flex;flex-direction:column;gap:6px}
.nur-leser{position:absolute;width:1px;height:1px;overflow:hidden;clip:rect(0 0 0 0);white-space:nowrap}
@media (max-width:700px){.wahl{grid-template-columns:1fr}.gross{min-height:92px}}
@media (prefers-reduced-motion:reduce){.status i{animation:none!important}*{scroll-behavior:auto!important}}
</style></head><body>
<header class="kopf">
 <h1>Dolmetscher</h1>
 <div class="status" id="status" data-z="bereit" role="status" aria-live="polite"><i></i><span id="statustext">bereit</span></div>
</header>
<main>
 <section class="wahl" aria-label="Wer spricht gerade">
  <button type="button" class="gross" id="knopfIch" aria-pressed="false" data-an="false">
   <b>Ich spreche Deutsch</b><small id="richtungIch">Deutsch → Türkisch</small>
  </button>
  <div class="gross gast" id="kartGast" data-an="false">
   <button type="button" class="sprecher" id="knopfGast" aria-pressed="false">
    <b>Gast spricht</b><small id="richtungGast">Türkisch → Deutsch</small>
   </button>
   <label><span class="nur-leser">Sprache des Gastes</span><select id="gastSprache"></select></label>
  </div>
 </section>
 <section class="steuer" aria-label="Einstellungen">
  <label><input type="checkbox" id="abwechselnd" checked> abwechselnd</label>
  <button type="button" class="knopf" id="knopfAus">Mikrofon aus</button>
  <button type="button" class="knopf" id="knopfLeeren">Verlauf leeren</button>
 </section>
 <section class="untertitel" id="untertitel" aria-live="polite" aria-label="Untertitel">
  <p class="vorlaeufig" id="vorlaeufig"></p>
  <div class="zeile alt"><span class="etikett" id="etiOriginal">Gesagt</span><span class="text" id="textOriginal"></span></div>
  <div class="zeile neu"><span class="etikett" id="etiUebersetzung">Übersetzung</span><span class="text" id="textUebersetzung">Wähle oben, wer spricht – dann geht es los.</span></div>
  <p class="takt" id="takt"></p>
 </section>
 <form class="tippen" id="tippform" autocomplete="off">
  <label class="nur-leser" for="tippfeld">Text eintippen</label>
  <input id="tippfeld" type="text" maxlength="1500" placeholder="Oder hier tippen – für den, der gerade dran ist">
  <button type="submit" class="knopf">Übersetzen</button>
 </form>
 <section class="verlauf" aria-label="Letzte Gespräche">
  <h2>Letzte Runden (nur in diesem Fenster)</h2>
  <ol id="verlauf"></ol>
  <p class="leer" id="verlaufLeer">Noch nichts gesagt.</p>
 </section>
</main>
<footer class="hinweise">
 <span><b>Rundenweise, nicht gleichzeitig:</b> Erst wird ein Satz erkannt, dann übersetzt, dann vorgelesen. Das dauert pro Satz
 grob 1,5 bis 3 Sekunden (Schätzung – die gemessene Zeit steht über dem Verlauf). Während Jarvis spricht, hört das Mikrofon nicht zu.</span>
 <span>Die Spracherkennung des Browsers schickt den Ton an den Hersteller des Browsers (Google bei Chrome, Apple bei Safari).
 Zum Übersetzen geht der erkannte Text an Gemini oder Claude, je nach Einstellung von Jarvis.</span>
 <span>Der Verlauf bleibt in diesem Fenster und wird nicht gespeichert. Der letzte Untertitel liegt bis zum Beenden von Jarvis
 im Arbeitsspeicher der Zentrale.</span>
</footer>
<audio id="ton" hidden></audio>
<script>
window.addEventListener('error',function(e){document.documentElement.setAttribute('data-fehler',String(e.message||e).slice(0,200))});
(function(){
"use strict";
var SCHLUESSEL="{{SCHLUESSEL}}";
var SPRACHEN=""" + json.dumps({k: [v[0], v[1]] for k, v in SPRACHEN.items()}) + r""";
// Wenn der Browser für eine Sprache keine Stimme hat, versucht er eine nahe verwandte.
var NAHE={bs:["bs","hr","sr"],sr:["sr","hr","bs"],hr:["hr","sr","bs"],sk:["sk","cs"],cs:["cs","sk"],uk:["uk","ru"],fa:["fa","ar"]};
var aktivCodes=Object.keys(SPRACHEN).filter(function(c){return c!=="de"});
var serverStimme=false;
var aktiv="ich";            // wer gerade dran ist: "ich" (Deutsch) oder "gast"
var willHoeren=false, belegt=false, erkLaeuft=false, fehlerZaehler=0, rundenNr=0;
var verlauf=[];
var el=function(id){return document.getElementById(id)};

function url(p){return p+(SCHLUESSEL?(p.indexOf("?")<0?"?":"&")+"schluessel="+encodeURIComponent(SCHLUESSEL):"")}
function holenJson(p,k){
 var o={headers:{"Content-Type":"application/json"}};
 if(k!==undefined){o.method="POST";o.body=JSON.stringify(k)}
 return fetch(url(p),o).then(function(r){return r.json()});
}
function name(c){return SPRACHEN[c]?SPRACHEN[c][0]:c}
function tag(c){return SPRACHEN[c]?SPRACHEN[c][1]:c}
function gast(){return el("gastSprache").value||aktivCodes[0]||"en"}
function code(wer){return wer==="ich"?"de":gast()}
function status(z,t){el("status").dataset.z=z;el("statustext").textContent=t}
function sek(ms){return (ms/1000).toFixed(1).replace(".",",")+" s"}

/* ---------- Sprachwahl ---------- */
function auswahlFuellen(vorgabe){
 var feld=el("gastSprache"),alt=vorgabe||feld.value;
 if(alt&&aktivCodes.indexOf(alt)<0&&SPRACHEN[alt]&&alt!=="de"){aktivCodes.push(alt)}
 feld.textContent="";
 aktivCodes.forEach(function(c){var o=document.createElement("option");o.value=c;o.textContent=name(c);feld.appendChild(o)});
 if(alt&&aktivCodes.indexOf(alt)>=0){feld.value=alt}
 beschriften();
}
function beschriften(){
 el("richtungIch").textContent="Deutsch → "+name(gast());
 el("richtungGast").textContent=name(gast())+" → Deutsch";
 var ich=aktiv==="ich";
 el("knopfIch").setAttribute("aria-pressed",String(willHoeren&&ich));
 el("knopfIch").dataset.an=String(willHoeren&&ich);
 el("knopfGast").setAttribute("aria-pressed",String(willHoeren&&!ich));
 el("kartGast").dataset.an=String(willHoeren&&!ich);
}
var vorgabeNach=(new URLSearchParams(location.search).get("nach")||"").toLowerCase();
if(!SPRACHEN[vorgabeNach]||vorgabeNach==="de"){vorgabeNach=""}
auswahlFuellen(vorgabeNach);
holenJson("/api/zustand").then(function(z){
 if(z&&z.dolmetscher_sprachen&&z.dolmetscher_sprachen.length){
  aktivCodes=z.dolmetscher_sprachen.filter(function(c){return SPRACHEN[c]&&c!=="de"});
 }
 serverStimme=!!(z&&z.stimme_im_browser);
 auswahlFuellen(vorgabeNach||el("gastSprache").value);
}).catch(function(){});
el("gastSprache").addEventListener("change",function(){beschriften();if(willHoeren&&aktiv==="gast"){wechsle()}});

/* ---------- Erkennung ---------- */
var Erk=window.SpeechRecognition||window.webkitSpeechRecognition;
var erk=null;
function erkStart(){
 if(!erk||erkLaeuft||!willHoeren||belegt){return}
 erk.lang=tag(code(aktiv));
 try{erk.start();erkLaeuft=true;status("hoert","hört zu: "+name(code(aktiv)))}catch(f){erkLaeuft=false}
}
function erkStopp(){if(erk&&erkLaeuft){try{erk.stop()}catch(f){}}}
function wechsle(){
 beschriften();
 if(!willHoeren){return}
 if(erkLaeuft){erkStopp()}else{erkStart()}   // onend startet mit der neuen Sprache neu
}
if(!Erk){
 status("fehler","keine Spracherkennung");
 el("textUebersetzung").textContent="Dieser Browser kann keine Spracherkennung. Nimm Safari oder Chrome – oder tipp unten.";
}else{
 erk=new Erk();
 erk.continuous=true;
 erk.interimResults=true;
 erk.onend=function(){erkLaeuft=false;if(willHoeren&&!belegt){setTimeout(erkStart,250)}};
 erk.onerror=function(e){
  erkLaeuft=false;
  var art=e&&e.error;
  if(art==="not-allowed"||art==="service-not-allowed"){
   willHoeren=false;beschriften();status("fehler","Mikrofon nicht erlaubt");
   el("textUebersetzung").textContent="Der Browser lässt mich nicht ans Mikrofon. Erlaub es in der Adressleiste und lad die Seite neu.";
  }else if(art==="network"||art==="audio-capture"){
   fehlerZaehler++;
   if(fehlerZaehler>=3){
    willHoeren=false;beschriften();status("fehler","Spracherkennung nicht erreichbar");
    el("textUebersetzung").textContent="Die Spracherkennung des Browsers ist gerade nicht erreichbar. Tipp unten oder versuch es später noch einmal.";
   }
  }
 };
 erk.onresult=function(e){
  if(belegt){return}
  fehlerZaehler=0;
  var fertig="",vorl="";
  for(var i=e.resultIndex;i<e.results.length;i++){
   if(e.results[i].isFinal){fertig+=e.results[i][0].transcript}else{vorl+=e.results[i][0].transcript}
  }
  if(vorl){el("vorlaeufig").textContent=vorl}
  if(fertig.trim()){runde(fertig.trim())}
 };
}
function starte(wer){
 aktiv=wer;willHoeren=true;fehlerZaehler=0;
 if(!Erk){beschriften();el("tippfeld").focus();return}
 wechsle();
}
el("knopfIch").addEventListener("click",function(){starte("ich")});
el("knopfGast").addEventListener("click",function(){starte("gast")});
el("knopfAus").addEventListener("click",function(){
 willHoeren=false;erkStopp();if(window.speechSynthesis){window.speechSynthesis.cancel()}
 el("ton").pause();belegt=false;rundenNr++;beschriften();status("bereit","Mikrofon aus");
});

/* ---------- Eine Runde ---------- */
function runde(text){
 var von=code(aktiv),nach=code(aktiv==="ich"?"gast":"ich"),wer=aktiv,nr=++rundenNr;
 belegt=true;erkStopp();
 el("vorlaeufig").textContent="";
 el("etiOriginal").textContent="Gesagt – "+name(von);
 el("textOriginal").textContent=text;
 el("etiUebersetzung").textContent="Übersetzung – "+name(nach);
 el("textUebersetzung").textContent="…";
 el("takt").textContent="";
 status("uebersetzt","übersetzt …");
 var t0=performance.now();
 var kontext=verlauf.slice(-4).map(function(v){return {von:v.von,original:v.original,uebersetzung:v.uebersetzung}});
 holenJson("/api/uebersetzen",{text:text,von:von,nach:nach,verlauf:kontext,sprecher:wer}).then(function(a){
  if(nr!==rundenNr){return}
  var dauer=performance.now()-t0;
  if(!a||!a.ok){
   el("textUebersetzung").textContent=(a&&a.fehler)||"Das Übersetzen hat nicht geklappt.";
   status("fehler","Fehler");
   fertigRunde(true);return;
  }
  el("textUebersetzung").textContent=a.uebersetzung;
  el("takt").textContent="Übersetzt in "+sek(dauer)+(a.gehirn?" ("+(a.gehirn==="gemini"?"Gemini":"Claude")+")":"");
  verlauf.push({von:von,nach:nach,sprecher:wer,original:text,uebersetzung:a.uebersetzung,dauer:dauer});
  if(verlauf.length>10){verlauf.shift()}
  verlaufZeigen();
  status("spricht","spricht: "+name(nach));
  sprich(a.sprechstuecke&&a.sprechstuecke.length?a.sprechstuecke:[a.uebersetzung],nach,function(){
   if(nr===rundenNr){fertigRunde(false)}
  });
 }).catch(function(f){
  if(nr!==rundenNr){return}
  el("textUebersetzung").textContent="Ich erreiche Jarvis nicht: "+f.message;
  status("fehler","Fehler");
  fertigRunde(true);
 });
}
function fertigRunde(mitFehler){
 belegt=false;
 if(!mitFehler&&el("abwechselnd").checked){aktiv=(aktiv==="ich"?"gast":"ich")}
 beschriften();
 if(willHoeren){erkStart()}else{status("bereit","bereit")}
}
el("tippform").addEventListener("submit",function(e){
 e.preventDefault();
 var t=el("tippfeld").value.trim();
 if(!t||belegt){return}
 el("tippfeld").value="";
 runde(t);
});
function verlaufZeigen(){
 var liste=el("verlauf");liste.textContent="";
 verlauf.slice().reverse().forEach(function(v){
  var li=document.createElement("li");li.dataset.sprecher=v.sprecher;
  var kopf=document.createElement("small");kopf.textContent=(v.sprecher==="ich"?"Ich":"Gast")+" · "+name(v.von)+" → "+name(v.nach)+" · "+sek(v.dauer);
  var o=document.createElement("span");o.textContent=v.original;
  var u=document.createElement("span");u.className="u";u.textContent=v.uebersetzung;
  li.appendChild(kopf);li.appendChild(o);li.appendChild(u);liste.appendChild(li);
 });
 el("verlaufLeer").style.display=verlauf.length?"none":"";
}
el("knopfLeeren").addEventListener("click",function(){
 verlauf=[];verlaufZeigen();
 el("textOriginal").textContent="";el("textUebersetzung").textContent="";el("takt").textContent="";
 el("etiOriginal").textContent="Gesagt";el("etiUebersetzung").textContent="Übersetzung";
});

/* ---------- Sprechen ---------- */
function sprachCode(l){return String(l||"").toLowerCase().replace("_","-").split("-")[0]}
function alleStimmen(){return window.speechSynthesis?window.speechSynthesis.getVoices():[]}
if(window.speechSynthesis){window.speechSynthesis.onvoiceschanged=alleStimmen}
// Die natürlichste Stimme für eine Sprache: erst hochwertige (Premium, Enhanced, Natural,
// Neural), dann Google, dann irgendeine. Gibt es keine, eine nahe verwandte Sprache.
function besteStimme(c){
 var liste=alleStimmen(),kette=NAHE[c]||[c];
 for(var k=0;k<kette.length;k++){
  var passend=liste.filter(function(s){return sprachCode(s.lang)===kette[k]});
  if(!passend.length){continue}
  var stufen=[/premium|enhanced|natural|neural|online/i,/google/i];
  for(var i=0;i<stufen.length;i++){
   var t=passend.filter(function(s){return stufen[i].test(s.name)});
   if(t.length){return {stimme:t[0],sprache:kette[k]}}
  }
  return {stimme:passend[0],sprache:kette[k]};
 }
 return null;
}
function sprich(stuecke,c,danach){
 if(serverStimme){spielServer(stuecke,c,danach)}else{spielBrowser(stuecke,c,danach)}
}
function spielBrowser(stuecke,c,danach){
 var wahl=besteStimme(c);
 if(!window.speechSynthesis||!wahl){
  el("takt").textContent+=(el("takt").textContent?" · ":"")+"Dein Browser hat keine Stimme für "+name(c)+" – nur Text.";
  danach();return;
 }
 if(wahl.sprache!==c){el("takt").textContent+=" · Stimme: "+name(wahl.sprache)+" (für "+name(c)+" gibt es keine)"}
 window.speechSynthesis.cancel();
 var i=0,fertig=false;
 function ende(){if(fertig){return}fertig=true;danach()}
 function weiter(){
  if(fertig){return}
  if(i>=stuecke.length){ende();return}
  var u=new SpeechSynthesisUtterance(stuecke[i++]);
  u.lang=wahl.stimme.lang||tag(wahl.sprache);u.voice=wahl.stimme;u.rate=1;
  u.onend=weiter;
  u.onerror=function(e){if(e&&(e.error==="canceled"||e.error==="interrupted")){ende()}else{weiter()}};
  window.speechSynthesis.speak(u);
 }
 weiter();
 // Sicherheitsnetz: manche Browser melden das Ende nicht.
 setTimeout(function(){if(!fertig){window.speechSynthesis.cancel();ende()}},Math.min(120000,4000+stuecke.join(" ").length*90));
}
function spielServer(stuecke,c,danach){
 var ton=el("ton"),i=0,vorab=null;
 function holeStueck(t){
  return fetch(url("/api/sprache"),{method:"POST",headers:{"Content-Type":"application/json"},
   body:JSON.stringify({text:t,sprache:c})}).then(function(r){
    if(!r.ok){throw new Error("Serverstimme: "+r.status)}
    return r.blob();
  }).then(function(b){return URL.createObjectURL(b)});
 }
 function zurueck(rest){
  // Die Serverstimme geht nicht (kein Guthaben, kein Netz): mit der Browserstimme weiter.
  serverStimme=false;
  el("takt").textContent+=(el("takt").textContent?" · ":"")+"Serverstimme nicht verfügbar – Browserstimme";
  spielBrowser(rest,c,danach);
 }
 function weiter(){
  if(i>=stuecke.length){danach();return}
  var jetzt=i;
  var p=vorab||holeStueck(stuecke[i]);
  i++;
  vorab=i<stuecke.length?holeStueck(stuecke[i]):null;
  if(vorab){vorab.catch(function(){})}
  p.then(function(u){
   ton.onended=function(){URL.revokeObjectURL(u);weiter()};
   ton.onerror=function(){zurueck(stuecke.slice(jetzt))};
   ton.src=u;
   return ton.play();
  }).catch(function(){zurueck(stuecke.slice(jetzt))});
 }
 weiter();
}
verlaufZeigen();
beschriften();
})();
</script></body></html>
"""
