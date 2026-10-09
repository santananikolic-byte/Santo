#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Die Oberfläche - Sprache, sonst nichts.

Kein Textfeld als Hauptweg, kein Knopf zum Drücken. Die Seite hört dauerhaft
zu, wartet auf das Weckwort und antwortet laut. Tippen geht nur als Notweg,
wenn das Mikrofon streikt.

Die Spracherkennung läuft im Browser. Wichtig dabei: Während Jarvis spricht,
wird die Erkennung angehalten - sonst hört er sich selbst zu und antwortet
auf seine eigene Stimme.
"""

SEITE_HTML = r"""<!DOCTYPE html>
<html lang="de">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<meta name="theme-color" content="#03080F">
<link rel="icon" href="/symbol.svg" type="image/svg+xml">
<title>Jarvis</title>
<style>
:root{
  --grund:#03080F; --tief:#050D16; --panel:#071420; --rand:#0E2A3C;
  --rand-hell:#16425C; --akzent:#3AD1FF; --kupfer:#A6ECFF; --text:#E4F7FF;
  --gedaempft:#8DB4C6; --grau:#5D8799; --gruen:#4CC38A; --rot:#E5484D;
  --sans:-apple-system,BlinkMacSystemFont,"Helvetica Neue",Arial,sans-serif;
  --mono:ui-monospace,"SF Mono",Menlo,monospace;
}
*{box-sizing:border-box;margin:0;padding:0}
html,body{height:100%;overflow:hidden}
body{
  background:
    radial-gradient(ellipse 70% 55% at 50% 45%,rgba(58,209,255,.10) 0%,transparent 70%),
    repeating-linear-gradient(0deg,rgba(58,209,255,.035) 0 1px,transparent 1px 44px),
    repeating-linear-gradient(90deg,rgba(58,209,255,.035) 0 1px,transparent 1px 44px),
    radial-gradient(ellipse 120% 80% at 50% 120%,#062238 0%,var(--grund) 62%);
  color:var(--text);font-family:var(--sans);-webkit-font-smoothing:antialiased;
  display:flex;flex-direction:column;user-select:none;
}
button{font-family:inherit;cursor:pointer;border:none;background:none;color:inherit}
:focus-visible{outline:2px solid var(--akzent);outline-offset:3px;border-radius:6px}

/* ---- Ticker ---- */
.ticker{
  flex:none;display:flex;gap:22px;flex-wrap:wrap;align-items:center;
  padding:10px 20px;font-size:11px;letter-spacing:.11em;text-transform:uppercase;
  color:var(--grau);border-bottom:1px solid var(--rand);
  background:linear-gradient(90deg,rgba(58,209,255,.13),transparent 68%);
}
.ticker b{color:var(--akzent);font-weight:600}
.ticker b.rot{color:var(--rot)}
.ticker .pkt{width:7px;height:7px;border-radius:50%;background:var(--grau);
             box-shadow:0 0 8px transparent}
.ticker .pkt.an{background:var(--gruen);box-shadow:0 0 9px var(--gruen)}
.ticker .pkt.aus{background:var(--rot);box-shadow:0 0 9px var(--rot)}
.ticker .rechts{margin-left:auto;display:flex;gap:14px;align-items:center}
.ticker a,.ticker .mini{color:var(--grau);text-decoration:none;font-size:10px;
                        letter-spacing:.12em}
.ticker a:hover,.ticker .mini:hover{color:var(--kupfer)}
.ticker .mini{text-transform:uppercase}
#lage{flex:1;min-width:0;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.ticker .mini:disabled{opacity:.45;cursor:default}
.ticker .mini.aktiv{color:var(--akzent);text-shadow:0 0 8px rgba(58,209,255,.6)}
.blitz{position:fixed;inset:0;background:rgba(166,236,255,.18);pointer-events:none;
       opacity:0;transition:opacity .25s;z-index:50}
.blitz.an{opacity:1}

/* ---- Bühne ---- */
main{flex:1;display:flex;flex-direction:column;align-items:center;
     justify-content:center;gap:26px;padding:20px;min-height:0;position:relative}

.kugel{position:relative;width:min(46vmin,260px);height:min(46vmin,260px);
       flex:none;display:grid;place-items:center;cursor:pointer}
.kugel .ring{position:absolute;inset:0;border-radius:50%;
             border:1px solid var(--rand-hell);transition:border-color .4s}
.kugel .ring2{inset:9%;opacity:.6}
.kugel .ring3{inset:19%;opacity:.35}
.kugel .kern{
  width:42%;height:42%;border-radius:50%;
  background:radial-gradient(circle,#F4FDFF 0%,#A6ECFF 20%,#3AD1FF 42%,#0B6E99 62%,
             rgba(6,40,64,.9) 70%);
  border:2px solid rgba(166,236,255,.55);
  box-shadow:0 0 40px -2px rgba(58,209,255,.65),inset 0 0 22px rgba(255,255,255,.35);
  transition:transform .35s,box-shadow .35s;
}
.kugel .welle{position:absolute;inset:0;border-radius:50%;border:1px solid var(--akzent);
              opacity:0;pointer-events:none}

/* Zustände */
body[data-zustand="schlaeft"] .kugel .kern{transform:scale(.82);
  box-shadow:0 0 26px -10px rgba(58,209,255,.4);filter:saturate(.55)}
body[data-zustand="wach"] .ring{border-color:rgba(58,209,255,.55)}
body[data-zustand="wach"] .kugel .kern{transform:scale(1.08);
  box-shadow:0 0 70px -4px rgba(58,209,255,.75)}
body[data-zustand="wach"] .welle{animation:welle 1.7s ease-out infinite}
body[data-zustand="wach"] .welle.w2{animation-delay:.55s}
body[data-zustand="wach"] .welle.w3{animation-delay:1.1s}
@keyframes welle{0%{opacity:.55;transform:scale(.55)}100%{opacity:0;transform:scale(1.05)}}
body[data-zustand="denkt"] .ring{border-color:rgba(58,209,255,.45);
  border-top-color:var(--akzent);animation:dreh 1.1s linear infinite}
body[data-zustand="denkt"] .ring2{animation:dreh 1.6s linear infinite reverse}
body[data-zustand="denkt"] .ring3{animation:dreh 2.2s linear infinite}
@keyframes dreh{to{transform:rotate(360deg)}}
body[data-zustand="spricht"] .kugel .kern{animation:reden .5s ease-in-out infinite alternate}
@keyframes reden{from{transform:scale(1)}to{transform:scale(1.16)}}
body[data-zustand="aus"] .kugel .kern{filter:grayscale(.85) saturate(.3);transform:scale(.75)}

/* HUD: drehende Ringe um den Kern */
.kugel .hud{position:absolute;inset:-9%;width:118%;height:118%;color:var(--akzent);
            pointer-events:none;filter:drop-shadow(0 0 6px rgba(58,209,255,.45))}
.kugel .hud1{animation:dreh 60s linear infinite}
.kugel .hud2{animation:dreh 34s linear infinite reverse}
body[data-zustand="denkt"] .kugel .hud1{animation-duration:5s}
body[data-zustand="denkt"] .kugel .hud2{animation-duration:3.4s}
body[data-zustand="aus"] .kugel .hud{opacity:.35;filter:none}
.ring{border-style:dashed}
.hud-ecke{position:absolute;top:22px;font-family:var(--mono);color:var(--gedaempft);
          text-transform:uppercase;letter-spacing:.16em;font-size:10px;line-height:1.7}
.hud-ecke.links{left:26px}
.hud-ecke.rechts{right:26px;text-align:right}
.hud-ecke .hud-wert{font-size:30px;letter-spacing:.04em;color:var(--akzent);
                    text-shadow:0 0 14px rgba(58,209,255,.55);font-weight:300}
.hud-ecke::before{content:"";display:block;width:42px;height:1px;background:var(--akzent);
                  margin-bottom:8px;box-shadow:0 0 8px var(--akzent)}
.hud-ecke.rechts::before{margin-left:auto}
.hud-ecke a{color:inherit;text-decoration:none}
.hud-ecke a:hover{color:var(--kupfer)}
.zustandstext{font-size:12px;letter-spacing:.22em;text-transform:uppercase;
              color:var(--grau);text-align:center;min-height:16px}
body[data-zustand="wach"] .zustandstext{color:var(--akzent)}

/* ---- Text ---- */
.buehne{width:min(100%,780px);text-align:center;display:flex;flex-direction:column;
        gap:14px;min-height:0}
.gesagt{font-size:clamp(15px,2.1vw,19px);color:var(--gedaempft);min-height:26px;
        font-style:italic}
.gesagt.vorlaeufig{opacity:.55}
.antwort{font-size:clamp(19px,3.1vw,30px);line-height:1.42;font-weight:500;
         letter-spacing:-.01em;max-height:38vh;overflow-y:auto;padding:0 4px}
.antwort.fehler{color:#F3B0B2}
.antwort::-webkit-scrollbar{width:5px}
.antwort::-webkit-scrollbar-thumb{background:var(--rand-hell);border-radius:3px}

.hinweis{font-size:13px;color:var(--grau);line-height:1.6;max-width:440px;
         margin:0 auto}
.hinweis b{color:var(--kupfer);font-weight:600}

/* ---- Zahlenleiste unten ---- */
.zahlen{flex:none;display:flex;gap:1px;background:var(--rand);
        border-top:1px solid var(--rand)}
.zahl{flex:1;background:var(--panel);padding:11px 14px;min-width:0}
.zahl .wert{font-size:17px;font-weight:700;font-variant-numeric:tabular-nums;
            white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.zahl .wert.gut{color:var(--gruen)} .zahl .wert.schlecht{color:var(--rot)}
.zahl .wert.akzent{color:var(--akzent)}
.zahl .name{font-size:9.5px;letter-spacing:.12em;text-transform:uppercase;
            color:var(--grau);margin-top:3px;white-space:nowrap;overflow:hidden;
            text-overflow:ellipsis}

/* ---- Notweg Tippen ---- */
.tippen{position:fixed;left:50%;transform:translateX(-50%);bottom:88px;
        width:min(92vw,620px);display:none;gap:9px}
.tippen.zeigen{display:flex}
.tippen input{flex:1;background:var(--panel);border:1px solid var(--rand-hell);
              border-radius:11px;padding:12px 15px;color:var(--text);
              font-family:inherit;font-size:15px}
.tippen button{background:var(--akzent);color:#02121C;border-radius:11px;
               padding:12px 20px;font-weight:700}

/* ---- Freigabe ---- */
.schleier{position:fixed;inset:0;background:rgba(4,5,6,.9);display:none;
          place-items:center;padding:20px;z-index:60;backdrop-filter:blur(4px)}
.schleier.zeigen{display:grid}
.frage{background:var(--panel);border:1px solid var(--akzent);border-radius:16px;
       max-width:620px;width:100%;overflow:hidden;
       box-shadow:0 30px 90px -24px rgba(58,209,255,.5)}
.frage .kopf{display:flex;align-items:center;gap:12px;padding:13px 20px;
             background:rgba(58,209,255,.12);border-bottom:1px solid var(--rand)}
.frage .kopf h2{font-size:12px;letter-spacing:.18em;text-transform:uppercase;
                color:var(--akzent);font-weight:700}
.frage .rest{margin-left:auto;font-family:var(--mono);font-size:12px;color:var(--grau)}
.frage .inhalt{padding:20px}
.frage .aktion{font-size:24px;font-weight:700;margin-bottom:12px}
.frage pre{background:var(--tief);border:1px solid var(--rand);border-radius:9px;
           padding:13px 15px;font-family:var(--mono);font-size:12.5px;line-height:1.65;
           color:var(--kupfer);max-height:230px;overflow:auto;white-space:pre-wrap;
           word-break:break-word}
.frage .sagen{padding:0 20px 8px;font-size:14px;color:var(--gedaempft);text-align:center}
.frage .sagen b{color:var(--akzent)}
.frage .knoepfe{display:flex;gap:11px;padding:12px 20px 20px}
.frage .knoepfe button{flex:1;padding:15px;border-radius:10px;font-weight:700;font-size:16px}
.frage .ja{background:var(--akzent);color:#02121C}
.frage .nein{background:var(--tief);border:1px solid var(--rand-hell);color:var(--text)}
.frage{max-height:92vh;overflow-y:auto}
.frage input{width:100%;padding:13px 14px;border-radius:9px;font:14px var(--mono);
  background:var(--tief);border:1px solid var(--rand-hell);color:var(--text);
  user-select:text;-webkit-user-select:text}
.frage .meldung{padding:0 20px 4px;font-size:13px;min-height:20px;color:var(--gedaempft)}
.frage .meldung.fehler{color:var(--rot)}

@media(max-width:640px){
  .hud-ecke{display:none}
  .ticker{gap:12px;padding:8px 12px;font-size:10px}
  .ticker .rechts{width:100%;margin-left:0;justify-content:flex-start}
  .zahl{padding:9px 10px}.zahl .wert{font-size:15px}
  main{gap:18px;padding:14px}
}
</style>
</head>
<body data-zustand="aus">
<div class="blitz" id="blitz"></div>

<div class="ticker">
  <span class="pkt" id="pkt"></span>
  <span id="lage">Stand wird geholt …</span>
  <span class="rechts">
    <button class="mini" id="kameraKnopf" title="Bei 'schau mal' macht Jarvis ein Foto mit der Kamera">Kamera an</button>
    <button class="mini" id="schirmKnopf" title="Jarvis sieht deinen Bildschirm, solange du teilst">Bildschirm teilen</button>
    <button class="mini" id="tippenAn" title="Notweg, falls das Mikrofon streikt">Tippen</button>
    <a href="/autopilot" data-seite target="_blank" rel="noopener" id="zuTunLink">Heute zu tun</a>
    <a href="/protokoll" data-seite target="_blank" rel="noopener">Protokoll</a>
    <a href="/dashboard" data-seite target="_blank" rel="noopener">Cockpit</a>
    <a href="/sales" data-seite target="_blank" rel="noopener">Sales</a>
  </span>
</div>

<main>
  <div class="hud-ecke links">
    <div class="hud-wert" id="uhr">--:--</div>
    <div id="datum"></div>
    <div id="hudGehirn"></div>
  </div>
  <div class="hud-ecke rechts">
    <div class="hud-wert"><a href="/autopilot" data-seite target="_blank" rel="noopener"
         id="hudAufgaben">–</a></div>
    <div>Heute zu tun</div>
    <div id="hudSystem">Online</div>
  </div>
  <div class="kugel" id="kugel" role="button" tabindex="0"
       title="Antippen weckt Jarvis auch ohne Weckwort">
    <span class="ring"></span><span class="ring ring2"></span><span class="ring ring3"></span>
    <span class="welle"></span><span class="welle w2"></span><span class="welle w3"></span>
    <svg class="hud hud1" viewBox="0 0 200 200" aria-hidden="true">
      <circle cx="100" cy="100" r="97" fill="none" stroke="currentColor" stroke-width="1"
              stroke-dasharray="1 5"/>
      <circle cx="100" cy="100" r="90" fill="none" stroke="currentColor" stroke-width="3"
              stroke-dasharray="46 14" opacity=".55"/>
    </svg>
    <svg class="hud hud2" viewBox="0 0 200 200" aria-hidden="true">
      <circle cx="100" cy="100" r="81" fill="none" stroke="currentColor" stroke-width="1.6"
              stroke-dasharray="120 40 20 40" opacity=".75"/>
      <circle cx="100" cy="100" r="73" fill="none" stroke="currentColor" stroke-width=".8"
              stroke-dasharray="2 3" opacity=".5"/>
    </svg>
    <span class="kern"></span>
  </div>
  <div class="zustandstext" id="zustandstext">Mikrofon wird gefragt …</div>

  <div class="buehne">
    <div class="gesagt" id="gesagt"></div>
    <div class="antwort" id="antwort"></div>
    <div class="hinweis" id="hinweis">
      Sag <b>„Hey Jarvis“</b> und dann, was du brauchst.
    </div>
  </div>
</main>

<div class="tippen" id="tippen">
  <input id="feld" placeholder="Notweg: hier tippen und Enter" autocomplete="off">
  <button id="senden">Senden</button>
</div>

<div class="zahlen">
  <div class="zahl"><div class="wert" id="z1">–</div><div class="name" id="n1">Kasse</div></div>
  <div class="zahl"><div class="wert" id="z2">–</div><div class="name" id="n2">Fehlt je Monat</div></div>
  <div class="zahl"><div class="wert" id="z3">–</div><div class="name" id="n3">Nachfassen</div></div>
  <div class="zahl"><div class="wert" id="z4">–</div><div class="name" id="n4">Gesichert</div></div>
</div>

<div class="schleier" id="schleier">
  <div class="frage">
    <div class="kopf"><h2>Freigabe</h2><span class="rest" id="rest"></span></div>
    <div class="inhalt">
      <div class="aktion" id="fAktion"></div>
      <pre id="fDetails"></pre>
    </div>
    <p class="sagen">Sag <b>ja</b> oder <b>nein</b>.</p>
    <div class="knoepfe">
      <button class="nein" id="fNein">Nein</button>
      <button class="ja" id="fJa">Ja, mach</button>
    </div>
  </div>
</div>

<div class="schleier" id="schluesselDialog">
  <div class="frage">
    <div class="kopf"><h2>Womit soll Jarvis denken?</h2></div>
    <div class="inhalt">
      <div class="aktion">Kostenlos mit einem Gratis-Schlüssel</div>
      <p class="sagen" style="padding:0 0 10px;text-align:left">
        Der schnellste Weg ohne Kosten und ohne Anthropic: Hol dir bei einem
        Dienst mit Gratis-Kontingent einen Schlüssel (ohne Karte, ohne Guthaben).
        <b>Groq:</b> console.groq.com/keys &middot; <b>Google:</b>
        aistudio.google.com/apikey. Grenzen pro Minute und Tag gelten, und das
        Gespräch geht an diesen Anbieter.</p>
      <select id="dienstWahl" style="width:100%;padding:11px;margin-bottom:8px;
        border-radius:9px;background:var(--tief);border:1px solid var(--rand-hell);
        color:var(--text);font-size:14px">
        <option value="groq" data-modell="llama-3.3-70b-versatile">Groq</option>
        <option value="gemini" data-modell="gemini-flash-lite-latest,gemini-3.5-flash-lite,gemini-3.1-flash-lite,gemini-flash-latest,gemini-3.8-flash">Google Gemini</option>
        <option value="openrouter" data-modell="meta-llama/llama-3.3-70b-instruct:free">OpenRouter</option>
      </select>
      <input id="dienstModell" type="text" value="llama-3.3-70b-versatile"
             autocomplete="off" spellcheck="false" style="margin-bottom:8px"
             title="Modellnamen, durch Komma getrennt. Ist eines aufgebraucht, nimmt Jarvis das nächste.">
      <input id="dienstSchluessel" type="password" placeholder="Schlüssel einfügen"
             autocomplete="off" spellcheck="false">
    </div>
    <p class="meldung" id="dienstMeldung"></p>
    <div class="knoepfe">
      <button class="ja" id="dienstSpeichern">Gratis-Dienst nutzen</button>
    </div>
    <div class="inhalt" style="border-top:1px solid var(--rand)">
      <div class="aktion">Oder auf diesem Rechner (Ollama)</div>
      <p class="sagen" style="padding:0 0 10px;text-align:left">
        Jarvis denkt mit einem Modell, das auf diesem Rechner läuft (Ollama,
        <b>ollama.com</b>). Kein Konto, kein Guthaben, kein Limit. Dafür ist es
        langsamer und schwächer als Claude. Ollama muss installiert und
        geöffnet sein.</p>
      <input id="lokalFeld" type="text" value="qwen2.5:3b" autocomplete="off"
             spellcheck="false">
    </div>
    <p class="meldung" id="lokalMeldung"></p>
    <div class="knoepfe">
      <button class="nein" id="lokalSpeichern">Lokales Modell nutzen</button>
    </div>
    <div class="inhalt" style="border-top:1px solid var(--rand)">
      <p class="sagen" style="padding:0 0 10px;text-align:left">
        <b>Nur wenn du willst:</b> Mit einem Anthropic-Schlüssel antwortet
        Claude, schneller und klüger. Das kostet Guthaben auf
        console.anthropic.com. Das brauchst du für den Weg oben nicht.</p>
      <input id="schluesselFeld" type="password" placeholder="sk-ant-…"
             autocomplete="off" spellcheck="false">
    </div>
    <p class="meldung" id="schluesselMeldung"></p>
    <div class="knoepfe">
      <button class="nein" id="schluesselSpeichern">Schlüssel speichern</button>
    </div>
  </div>
</div>

<script>
(function () {
  "use strict";
  var SCHLUESSEL = "{{SCHLUESSEL}}";
  var WECKWOERTER = ["hey jarvis","hey javis","hey dscharvis","hey charvis",
                     "hey travis","hey jervis","hey service","hey chavis",
                     "jarvis","javis"];
  var JA = ["ja","jo","jup","okay","ok","passt","mach","machen","los","sicher",
            "einverstanden","erlaubt","freigabe","yes"];
  var NEIN = ["nein","ne","nee","no","stop","stopp","abbrechen","abbruch",
              "lass","nicht","niemals","nope"];

  var el = function (id) { return document.getElementById(id); };
  var zustand = "aus", wachBis = 0, laeuft = false;
  var freigabe = null, sprichtGerade = false;

  function setzeZustand(neu, text) {
    zustand = neu;
    document.body.dataset.zustand = neu;
    el("zustandstext").textContent = text || {
      aus: "Mikrofon aus", schlaeft: "Sag Hey Jarvis",
      wach: "Ich höre", denkt: "Ich arbeite", spricht: "…"
    }[neu];
  }

  /* ---------- Netz ---------- */
  function url(p) {
    return p + (SCHLUESSEL ? (p.indexOf("?") < 0 ? "?" : "&") +
      "schluessel=" + encodeURIComponent(SCHLUESSEL) : "");
  }
  /* Seitenlinks tragen den Schlüssel mit, sonst sperrt der Server sie aus. */
  Array.prototype.forEach.call(document.querySelectorAll("a[data-seite]"),
    function (a) { a.setAttribute("href", url(a.getAttribute("href"))); });
  function holen(p, k) {
    var o = { headers: { "Content-Type": "application/json" } };
    if (k !== undefined) { o.method = "POST"; o.body = JSON.stringify(k); }
    return fetch(url(p), o).then(function (a) { return a.json(); });
  }
  function euro(n) {
    if (typeof n !== "number") { return "–"; }
    return n.toLocaleString("de-DE", { minimumFractionDigits: 0,
      maximumFractionDigits: 0 }) + " €";
  }

  /* ---------- Sprechen ---------- */
  var stimmen = [];
  function stimmenLaden() {
    stimmen = window.speechSynthesis ? window.speechSynthesis.getVoices() : [];
  }
  if (window.speechSynthesis) {
    stimmenLaden();
    window.speechSynthesis.onvoiceschanged = stimmenLaden;
  }
  function sprich(text, danach) {
    if (!window.speechSynthesis || !text) { if (danach) { danach(); } return; }
    // Erkennung anhalten, sonst hört Jarvis sich selbst zu.
    hoerenPause();
    sprichtGerade = true;
    setzeZustand("spricht");
    window.speechSynthesis.cancel();
    var satz = new SpeechSynthesisUtterance(text);
    satz.lang = "de-DE"; satz.rate = 1.06;
    var de = stimmen.filter(function (s) { return /^de/i.test(s.lang); });
    var gut = de.filter(function (s) {
      return /markus|yannick|petra|anna|viktor|google/i.test(s.name); });
    if (gut.length) { satz.voice = gut[0]; } else if (de.length) { satz.voice = de[0]; }
    satz.onend = satz.onerror = function () {
      sprichtGerade = false;
      hoerenWeiter();
      if (danach) { danach(); }
    };
    window.speechSynthesis.speak(satz);
    // Sicherheitsnetz: manche Browser feuern onend nicht.
    setTimeout(function () {
      if (sprichtGerade) { sprichtGerade = false; hoerenWeiter(); }
    }, Math.min(45000, 2500 + text.length * 90));
  }

  /* ---------- Sehen: Kamera und Bildschirm über den Browser ---------- */
  // Kein Homebrew, kein Zusatzprogramm: Der Browser darf an Kamera und
  // Bildschirm, und das Gehirn bekommt das Bild direkt mit der Frage.
  // Nur eindeutige Seh-Aufforderungen - "schau mal in meinen Kalender" oder
  // "Fotovoltaik" machen kein Foto.
  var SEHEN = /((schau|guck)\w* (mal |doch |dir )*(her\b|hier\b|das an|was ich)|was siehst du|was halte ich|in der hand|mach (mal )?ein foto|was ist das hier|lies (mir )?(das|den zettel|den beleg|die rechnung) (hier )?vor|diesen beleg|den beleg hier|die rechnung hier)/i;
  var SCHIRM = /(auf (meinem|dem) (bildschirm|schirm|monitor)|was ist (hier|gerade|da) offen|was hab ich (hier |gerade |da )?offen|was siehst du auf)/i;
  var ADRESSE = /(https?:|www\.|\.(at|de|com|ch|eu|net|org)\b)/i;
  var kannKamera = !!(navigator.mediaDevices && navigator.mediaDevices.getUserMedia);
  var kannSchirm = !!(navigator.mediaDevices && navigator.mediaDevices.getDisplayMedia);
  var kameraAn = false, schirmStrom = null, schirmUhr = null;
  try { kameraAn = kannKamera && localStorage.getItem("jarvis-kamera") === "an"; } catch (e) {}

  function knoepfeZeigen() {
    el("kameraKnopf").textContent = !kannKamera ? "Kamera nicht verfügbar"
                                  : (kameraAn ? "Kamera an" : "Kamera aus");
    el("kameraKnopf").classList.toggle("aktiv", kameraAn);
    el("kameraKnopf").disabled = !kannKamera;
    el("schirmKnopf").textContent = !kannSchirm ? "Bildschirm nicht verfügbar"
                                  : (schirmStrom ? "Bildschirm geteilt" : "Bildschirm teilen");
    el("schirmKnopf").classList.toggle("aktiv", !!schirmStrom);
    el("schirmKnopf").disabled = !kannSchirm;
  }
  function bildAus(strom) {
    // Mit Zeitlimit: Liefert die Quelle kein Bild (Tab im Hintergrund, Fenster
    // minimiert), hängt Jarvis sonst für immer bei "Ich arbeite".
    var v = document.createElement("video");
    function aufraeumen() { try { v.pause(); } catch (e) {} v.srcObject = null; }
    var aufnahme = new Promise(function (fertig, fehler) {
      v.muted = true; v.playsInline = true; v.srcObject = strom;
      v.onloadeddata = function () {
        setTimeout(function () {
          try {
            var breite = Math.min(1280, v.videoWidth || 1280);
            var hoehe = Math.round(breite * (v.videoHeight || 720) / (v.videoWidth || 1280));
            var c = document.createElement("canvas"); c.width = breite; c.height = hoehe;
            c.getContext("2d").drawImage(v, 0, 0, breite, hoehe);
            fertig(c.toDataURL("image/jpeg", 0.72).split(",")[1]);
          } catch (e) { fehler(e); }
        }, 350);  // kurz warten: die Kamera regelt erst die Helligkeit nach
      };
      v.onerror = function () { fehler(new Error("Kein Bild von der Quelle")); };
      v.play().catch(fehler);
    });
    var zeitlimit = new Promise(function (_, fehler) {
      setTimeout(function () { fehler(new Error("Zeitlimit")); }, 5000);
    });
    return Promise.race([aufnahme, zeitlimit]).then(
      function (b) { aufraeumen(); return b; },
      function (e) { aufraeumen(); throw e; });
  }
  function blitzen() {
    el("blitz").classList.add("an");
    setTimeout(function () { el("blitz").classList.remove("an"); }, 260);
  }
  function kameraBild() {
    var anfrage = navigator.mediaDevices.getUserMedia({ video: { width: 1280 } });
    var zeitlimit = new Promise(function (_, fehler) {
      setTimeout(function () { fehler(new Error("Zeitlimit")); }, 8000);
    });
    return Promise.race([anfrage, zeitlimit]).then(function (strom) {
      function aus() { strom.getTracks().forEach(function (t) { t.stop(); }); }
      return bildAus(strom).then(
        function (b) { aus(); blitzen(); return { daten: b, quelle: "kamera" }; },
        function (e) { aus(); throw e; });  // Kamera in jedem Fall wieder aus
    });
  }
  function hinweisZeigen(text) {
    el("hinweis").style.display = "block";
    el("hinweis").textContent = text;
  }
  function bildFuer(text) {
    if (schirmStrom && SCHIRM.test(text)) {
      return bildAus(schirmStrom).then(function (b) {
        return { daten: b, quelle: "bildschirm" };
      }).catch(function () {
        hinweisZeigen("Vom geteilten Bildschirm kam kein Bild - ich antworte ohne.");
        return null;
      });
    }
    if (SEHEN.test(text) && !ADRESSE.test(text)) {
      if (!kannKamera) {
        hinweisZeigen("Hier gibt es keine Kamera (nur am Mac über localhost).");
        return Promise.resolve(null);
      }
      if (!kameraAn) {
        hinweisZeigen("Damit ich sehen kann, schalte oben die Kamera an.");
        return Promise.resolve(null);
      }
      return kameraBild().catch(function (e) {
        hinweisZeigen(e && e.name === "NotAllowedError"
          ? "Die Kamera ist im Browser nicht erlaubt - erlaube sie über das Symbol in der Adressleiste."
          : (e && e.name === "NotReadableError"
             ? "Die Kamera wird gerade von einem anderen Programm benutzt."
             : "Von der Kamera kam kein Bild - ich antworte ohne."));
        return null;
      });
    }
    return Promise.resolve(null);
  }
  function schirmBeenden() {
    if (schirmStrom) { schirmStrom.getTracks().forEach(function (t) { t.stop(); }); }
    schirmStrom = null; clearTimeout(schirmUhr); knoepfeZeigen();
  }
  el("kameraKnopf").addEventListener("click", function () {
    kameraAn = !kameraAn;
    try { localStorage.setItem("jarvis-kamera", kameraAn ? "an" : "aus"); } catch (e) {}
    knoepfeZeigen();
  });
  el("schirmKnopf").addEventListener("click", function () {
    if (schirmStrom) { schirmBeenden(); return; }
    if (!kannSchirm) { return; }
    navigator.mediaDevices.getDisplayMedia({ video: true }).then(function (strom) {
      schirmStrom = strom;
      strom.getVideoTracks()[0].addEventListener("ended", schirmBeenden);
      // Vergessenes Teilen endet von selbst - sonst sieht Jarvis Stunden später
      // noch das Online-Banking.
      schirmUhr = setTimeout(schirmBeenden, 15 * 60 * 1000);
      knoepfeZeigen();
    }).catch(function () {});
  });
  knoepfeZeigen();

  /* ---------- Reden ---------- */
  function fragen(text) {
    text = (text || "").trim();
    if (!text || laeuft) { return; }
    laeuft = true;
    wachBis = 0;
    el("gesagt").textContent = "„" + text + "“";
    el("gesagt").className = "gesagt";
    el("hinweis").style.display = "none";
    setzeZustand("denkt");
    bildFuer(text).then(function (bild) {
      var k = { text: text };
      if (bild && bild.daten) {
        k.bild = bild.daten; k.quelle = bild.quelle;
        el("gesagt").textContent = "„" + text + "“ · mit " +
          (bild.quelle === "bildschirm" ? "Bildschirmbild" : "Foto");
      }
      return holen("/api/reden", k);
    }).then(function (a) {
      var antwort = a.antwort || a.fehler || "Ich habe keine Antwort bekommen.";
      el("antwort").textContent = antwort;
      el("antwort").className = "antwort" + (a.ok ? "" : " fehler");
      laeuft = false;
      sprich(antwort, function () { setzeZustand("schlaeft"); });
      lageHolen(); zahlenHolen();
    }).catch(function (f) {
      el("antwort").textContent = "Ich erreiche den Server nicht: " +
        ((f && f.message) || String(f));
      el("antwort").className = "antwort fehler";
      laeuft = false;
      setzeZustand("schlaeft");
    });
  }

  /* ---------- Zuhören ---------- */
  var Erk = window.SpeechRecognition || window.webkitSpeechRecognition;
  var erk = null, laeuftErk = false, willHoeren = false;

  function hoerenStart() {
    if (!erk || laeuftErk || !willHoeren || sprichtGerade) { return; }
    try { erk.start(); laeuftErk = true; } catch (f) { laeuftErk = false; }
  }
  function hoerenPause() {
    willHoeren = false;
    if (erk && laeuftErk) { try { erk.stop(); } catch (f) {} }
  }
  function hoerenWeiter() {
    willHoeren = true;
    setTimeout(hoerenStart, 320);
    if (zustand === "spricht") { setzeZustand("schlaeft"); }
  }

  function saeubern(t) {
    return (t || "").toLowerCase().replace(/[^a-zäöüß0-9 ]+/g, " ")
      .replace(/\s+/g, " ").trim();
  }
  function weckwortAb(text) {
    var k = saeubern(text);
    for (var i = 0; i < WECKWOERTER.length; i++) {
      var w = WECKWOERTER[i];
      if (k === w) { return { wach: true, rest: "" }; }
      if (k.indexOf(w + " ") === 0) {
        return { wach: true, rest: text.substr(text.length - (k.length - w.length - 1)).trim() };
      }
    }
    return { wach: false, rest: "" };
  }

  if (!Erk) {
    setzeZustand("aus", "Browser ohne Spracherkennung");
    el("hinweis").innerHTML = "Dieser Browser kann keine Spracherkennung. " +
      "Nimm <b>Safari</b> oder <b>Chrome</b> — oder tipp oben rechts.";
    el("tippen").classList.add("zeigen");
  } else {
    erk = new Erk();
    erk.lang = "de-DE";
    erk.continuous = true;
    erk.interimResults = true;

    erk.onstart = function () {
      laeuftErk = true;
      if (zustand === "aus") { setzeZustand("schlaeft"); }
    };
    erk.onend = function () {
      laeuftErk = false;
      if (willHoeren) { setTimeout(hoerenStart, 300); }
    };
    erk.onerror = function (e) {
      laeuftErk = false;
      if (e.error === "not-allowed" || e.error === "service-not-allowed") {
        willHoeren = false;
        setzeZustand("aus", "Mikrofon nicht erlaubt");
        el("hinweis").innerHTML = "Der Browser lässt mich nicht ans Mikrofon. " +
          "Erlaub es in der Adressleiste und lad die Seite neu.";
        el("hinweis").style.display = "";
        el("tippen").classList.add("zeigen");
      }
    };

    erk.onresult = function (e) {
      var fertig = "", vorlaeufig = "";
      for (var i = e.resultIndex; i < e.results.length; i++) {
        if (e.results[i].isFinal) { fertig += e.results[i][0].transcript; }
        else { vorlaeufig += e.results[i][0].transcript; }
      }

      if (vorlaeufig && !laeuft) {
        el("gesagt").textContent = vorlaeufig;
        el("gesagt").className = "gesagt vorlaeufig";
      }
      if (!fertig) { return; }
      var text = fertig.trim();
      var k = saeubern(text);
      if (!k) { return; }

      // Bei offener Freigabe zählt nur ja oder nein.
      if (freigabe) {
        var wort = k.split(" ").filter(function (w) {
          return JA.indexOf(w) >= 0 || NEIN.indexOf(w) >= 0; })[0];
        if (wort) { antworten(JA.indexOf(wort) >= 0); }
        return;
      }
      if (laeuft || sprichtGerade) { return; }

      var probe = weckwortAb(text);
      if (probe.wach) {
        if (probe.rest) { fragen(probe.rest); }
        else {
          wachBis = Date.now() + 9000;
          setzeZustand("wach");
          el("gesagt").textContent = "";
        }
        return;
      }
      if (Date.now() < wachBis) { fragen(text); }
    };

    willHoeren = true;
    hoerenStart();
    setzeZustand("schlaeft");

    // Wach werden ohne Weckwort: Kugel antippen.
    el("kugel").addEventListener("click", function () {
      if (laeuft || freigabe) { return; }
      if (window.speechSynthesis) { window.speechSynthesis.cancel(); }
      wachBis = Date.now() + 9000;
      setzeZustand("wach");
      hoerenWeiter();
    });
    el("kugel").addEventListener("keydown", function (e) {
      if (e.key === "Enter" || e.key === " ") { e.preventDefault(); this.click(); }
    });

    // Wachfenster läuft ab
    setInterval(function () {
      if (zustand === "wach" && wachBis && Date.now() > wachBis) {
        wachBis = 0;
        setzeZustand("schlaeft");
      }
    }, 500);
  }

  /* ---------- Notweg Tippen ---------- */
  el("tippenAn").addEventListener("click", function () {
    el("tippen").classList.toggle("zeigen");
    if (el("tippen").classList.contains("zeigen")) { el("feld").focus(); }
  });
  el("senden").addEventListener("click", function () {
    fragen(el("feld").value); el("feld").value = "";
  });
  el("feld").addEventListener("keydown", function (e) {
    if (e.key === "Enter") { fragen(this.value); this.value = ""; }
  });

  /* ---------- Freigaben ---------- */
  function freigabenHolen() {
    holen("/api/freigaben").then(function (a) {
      var offen = (a.offen || [])[0];
      if (!offen) { if (freigabe) { schliessen(); } return; }
      if (freigabe && freigabe.id === offen.id) {
        el("rest").textContent = offen.rest + " s"; return;
      }
      freigabe = offen;
      el("fAktion").textContent = offen.aktion;
      el("fDetails").textContent = offen.details || "(ohne Angaben)";
      el("rest").textContent = offen.rest + " s";
      el("schleier").classList.add("zeigen");
      sprich("Ich brauche eine Freigabe für " + offen.aktion + ". Ja oder nein?");
    }).catch(function () {});
  }
  function schliessen() {
    freigabe = null;
    el("schleier").classList.remove("zeigen");
  }
  function antworten(ja) {
    if (!freigabe) { return; }
    var id = freigabe.id;
    schliessen();
    if (window.speechSynthesis) { window.speechSynthesis.cancel(); }
    sprichtGerade = false; hoerenWeiter();
    holen("/api/freigabe", { id: id, ja: ja }).then(function () { lageHolen(); });
  }
  el("fJa").addEventListener("click", function () { antworten(true); });
  el("fNein").addEventListener("click", function () { antworten(false); });
  document.addEventListener("keydown", function (e) {
    if (freigabe && e.key === "Escape") { antworten(false); }
  });

  /* ---------- Was Jarvis von selbst sagt ---------- */
  function meldungenHolen() {
    if (laeuft || sprichtGerade || freigabe) { return; }
    holen("/api/meldungen").then(function (a) {
      var m = (a.meldungen || [])[0];
      if (!m) { return; }
      el("gesagt").textContent = "";
      el("antwort").textContent = m.text;
      el("antwort").className = "antwort";
      el("hinweis").style.display = "none";
      sprich(m.text, function () { setzeZustand("schlaeft"); });
      lageHolen(); zahlenHolen();
    }).catch(function () {});
  }

  /* ---------- Stand ---------- */
  function lageHolen() {
    holen("/api/lage").then(function (a) {
      el("lage").textContent = a.text || "Kein Stand abrufbar.";
    }).catch(function () { el("lage").textContent = "Server antwortet nicht."; });
  }
  function uhrStellen() {
    var jetzt = new Date();
    el("uhr").textContent = ("0" + jetzt.getHours()).slice(-2) + ":" +
                            ("0" + jetzt.getMinutes()).slice(-2);
    el("datum").textContent = jetzt.toLocaleDateString("de-AT", {
      weekday: "long", day: "numeric", month: "long"});
  }
  uhrStellen();
  setInterval(uhrStellen, 15000);

  function zustandHolen() {
    holen("/api/zustand").then(function (a) {
      el("pkt").className = "pkt " + (a.einsatzbereit ? "an" : "aus");
      if (a.aufgaben) { el("zuTunLink").textContent = "Heute zu tun (" + a.aufgaben + ")"; }
      el("hudAufgaben").textContent = String(a.aufgaben || 0);
      var gehirn = Object.keys(a.dienste || {}).filter(function (k) {
        return a.dienste[k] && ["Claude", "Gratis-Dienst", "Lokales Modell"].indexOf(k) >= 0;
      })[0];
      el("hudGehirn").textContent = "Gehirn: " + (gehirn || "fehlt");
      el("pkt").title = a.einsatzbereit ? a.werkzeuge + " Werkzeuge bereit"
                                        : "Kein Anthropic-Schlüssel";
      if (!a.einsatzbereit) {
        el("schluesselDialog").classList.add("zeigen");
        el("antwort").textContent = "Ich habe noch kein Gehirn. Trag im Fenster einen Gratis-Schlüssel ein, " +
          "dann denke ich mit.";
        el("antwort").className = "antwort fehler";
      }
    }).catch(function () {});
  }
  function schluesselSpeichern() {
    var feld = el("schluesselFeld"), meldung = el("schluesselMeldung");
    if (!feld.value.trim()) { return; }
    meldung.className = "meldung"; meldung.textContent = "Ich probiere den Schlüssel aus …";
    el("schluesselSpeichern").disabled = true;
    holen("/api/schluessel", { schluessel: feld.value }).then(function (a) {
      el("schluesselSpeichern").disabled = false;
      meldung.textContent = a.text || "";
      if (a.ok) {
        feld.value = "";
        el("schluesselDialog").classList.remove("zeigen");
        el("antwort").textContent = ""; el("antwort").className = "antwort";
        zustandHolen();
      } else { meldung.className = "meldung fehler"; }
    }).catch(function () {
      el("schluesselSpeichern").disabled = false;
      meldung.className = "meldung fehler";
      meldung.textContent = "Der Server antwortet nicht.";
    });
  }
  function lokalSpeichern() {
    var meldung = el("lokalMeldung");
    meldung.className = "meldung"; meldung.textContent = "Ich schaue nach Ollama …";
    el("lokalSpeichern").disabled = true;
    holen("/api/lokal", { modell: el("lokalFeld").value }).then(function (a) {
      el("lokalSpeichern").disabled = false;
      meldung.textContent = a.text || "";
      if (a.ok) {
        el("schluesselDialog").classList.remove("zeigen");
        el("antwort").textContent = ""; el("antwort").className = "antwort";
        zustandHolen();
      } else { meldung.className = "meldung fehler"; }
    }).catch(function () {
      el("lokalSpeichern").disabled = false;
      meldung.className = "meldung fehler";
      meldung.textContent = "Der Server antwortet nicht.";
    });
  }
  function dienstSpeichern() {
    var meldung = el("dienstMeldung");
    if (!el("dienstSchluessel").value.trim()) { return; }
    meldung.className = "meldung"; meldung.textContent = "Ich probiere den Dienst aus …";
    el("dienstSpeichern").disabled = true;
    holen("/api/dienst", { dienst: el("dienstWahl").value,
                           modell: el("dienstModell").value,
                           schluessel: el("dienstSchluessel").value }).then(function (a) {
      el("dienstSpeichern").disabled = false;
      meldung.textContent = a.text || "";
      if (a.ok) {
        el("dienstSchluessel").value = "";
        el("schluesselDialog").classList.remove("zeigen");
        el("antwort").textContent = ""; el("antwort").className = "antwort";
        zustandHolen();
      } else { meldung.className = "meldung fehler"; }
    }).catch(function () {
      el("dienstSpeichern").disabled = false;
      meldung.className = "meldung fehler";
      meldung.textContent = "Der Server antwortet nicht.";
    });
  }
  el("dienstSpeichern").addEventListener("click", dienstSpeichern);
  el("dienstWahl").addEventListener("change", function () {
    var o = el("dienstWahl").options[el("dienstWahl").selectedIndex];
    el("dienstModell").value = o.getAttribute("data-modell") || "";
  });
  el("lokalSpeichern").addEventListener("click", lokalSpeichern);
  el("schluesselSpeichern").addEventListener("click", schluesselSpeichern);
  el("schluesselFeld").addEventListener("keydown", function (e) {
    if (e.key === "Enter") { schluesselSpeichern(); }
  });
  function setzeZahl(nr, wert, name, klasse) {
    el("z" + nr).textContent = wert;
    el("z" + nr).className = "wert" + (klasse ? " " + klasse : "");
    el("n" + nr).textContent = name;
  }
  function zahlenHolen() {
    holen("/api/kasse").then(function (a) {
      setzeZahl(1, euro(a.ergebnis), "Ergebnis Monat",
                a.ergebnis >= 0 ? "gut" : "schlecht");
    }).catch(function () {});
    holen("/api/bedarf").then(function (a) {
      if (a.berechenbar && typeof a.luecke === "number" && a.luecke > 0) {
        setzeZahl(2, euro(a.luecke), "fehlt je Monat", "schlecht");
      } else if (a.berechenbar) {
        setzeZahl(2, euro(a.noetiger_umsatz), "nötig je Monat", "gut");
      } else { setzeZahl(2, "–", "Fixkosten fehlen"); }
    }).catch(function () {});
    holen("/api/nachfassen").then(function (a) {
      setzeZahl(3, String(a.anzahl || 0), a.anzahl ? "heute nachfassen" : "nichts fällig",
                a.anzahl ? "akzent" : "");
    }).catch(function () {});
    holen("/api/pipeline").then(function (a) {
      setzeZahl(4, euro(a.laufender_umsatz_monat), "gesichert je Monat", "gut");
    }).catch(function () {});
  }

  zustandHolen(); lageHolen(); zahlenHolen();
  setInterval(freigabenHolen, 1200);
  setInterval(meldungenHolen, 4000);
  setInterval(lageHolen, 45000);
  setInterval(zahlenHolen, 60000);
})();
</script>
</body>
</html>
"""


PROTOKOLL_HTML = r"""<!DOCTYPE html>
<html lang="de">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<meta name="theme-color" content="#03080F">
<link rel="icon" href="/symbol.svg" type="image/svg+xml">
<title>Jarvis Protokoll</title>
<style>
:root{--grund:#03080F;--panel:#071420;--rand:#0E2A3C;--akzent:#3AD1FF;
  --kupfer:#A6ECFF;--text:#E4F7FF;--gedaempft:#8DB4C6;--grau:#5D8799;
  --gruen:#4CC38A;--rot:#E5484D;
  --sans:-apple-system,BlinkMacSystemFont,"Helvetica Neue",Arial,sans-serif;
  --mono:ui-monospace,"SF Mono",Menlo,monospace}
*{box-sizing:border-box;margin:0;padding:0}
body{background:var(--grund);color:var(--text);font-family:var(--sans);
  -webkit-font-smoothing:antialiased;padding:0 0 60px}
header{padding:18px 20px;border-bottom:1px solid var(--rand);
  background:linear-gradient(90deg,rgba(58,209,255,.13),transparent 68%)}
header h1{font-size:18px;font-weight:600}
header p{font-size:12px;color:var(--grau);margin-top:4px;letter-spacing:.06em}
.leiste{display:flex;gap:8px;flex-wrap:wrap;padding:14px 20px;align-items:center}
.leiste button,.leiste input{font:inherit;font-size:13px;color:var(--text);
  background:var(--panel);border:1px solid var(--rand);border-radius:8px;
  padding:8px 12px}
.leiste button{cursor:pointer}
.leiste button.an{border-color:var(--akzent);color:var(--kupfer)}
.leiste input{min-width:0;flex:1 1 160px}
:focus-visible{outline:2px solid var(--akzent);outline-offset:2px}
main{max-width:860px;margin:0 auto;padding:0 20px}
.fazit{background:var(--panel);border:1px solid var(--rand);border-left:3px solid var(--akzent);
  border-radius:8px;padding:14px 16px;font-size:14px;line-height:1.5;margin-bottom:18px}
h2{font-size:11px;letter-spacing:.14em;text-transform:uppercase;color:var(--grau);
  margin:22px 0 8px;font-weight:600}
.zeile{display:flex;gap:12px;padding:9px 0;border-bottom:1px solid var(--rand);
  font-size:14px;line-height:1.45}
.zeit{flex:none;width:62px;font:11px var(--mono);color:var(--grau);padding-top:3px}
.wer{flex:none;width:54px;font-size:11px;letter-spacing:.08em;text-transform:uppercase;
  padding-top:3px;color:var(--grau)}
.wer.user{color:var(--kupfer)}
.text{flex:1;min-width:0;white-space:pre-wrap;word-wrap:break-word}
.fehler{color:var(--rot)}
.leer{color:var(--grau);font-size:13px;padding:10px 0}
</style>
</head>
<body>
<header>
  <h1 id="titel"></h1>
  <p id="unter"></p>
</header>
<div class="leiste">
  <button data-tag="heute" class="an">Heute</button>
  <button data-tag="gestern">Gestern</button>
  <button data-tag="vorgestern">Vorgestern</button>
  <button data-tage="7">7 Tage</button>
  <input id="thema" type="search" placeholder="Thema filtern" autocomplete="off">
</div>
<main>
  <div class="fazit" id="fazit">Wird geholt …</div>
  <h2>Gespräche</h2><div id="gespraeche"></div>
  <h2>Aktionen</h2><div id="aktionen"></div>
  <h2>Offen</h2><div id="offen"></div>
</main>
<script>
(function () {
  "use strict";
  var SCHLUESSEL = {{SCHLUESSEL_JSON}};
  var NUTZER = {{NUTZER_JSON}}, FIRMA = {{FIRMA_JSON}};
  var tag = "heute", tage = 1, wartet = null;
  var el = function (id) { return document.getElementById(id); };

  document.getElementById("titel").textContent = "Protokoll von " + NUTZER;
  document.getElementById("unter").textContent =
    FIRMA + " · läuft auf deinem iMac, nur für dich";

  function zeile(links, mitte, text, klasse) {
    var z = document.createElement("div"); z.className = "zeile";
    var a = document.createElement("div"); a.className = "zeit"; a.textContent = links;
    var b = document.createElement("div"); b.className = "wer " + (klasse || "");
    b.textContent = mitte;
    var c = document.createElement("div"); c.className = "text"; c.textContent = text;
    z.appendChild(a); z.appendChild(b); z.appendChild(c);
    return z;
  }
  function fuellen(id, zeilen, leerText) {
    var k = el(id); k.textContent = "";
    if (!zeilen.length) {
      var l = document.createElement("div"); l.className = "leer"; l.textContent = leerText;
      k.appendChild(l); return;
    }
    zeilen.forEach(function (z) { k.appendChild(z); });
  }
  function uhr(zeit) { return (zeit || "").slice(tage > 1 ? 5 : 11, 16); }

  function holen() {
    var q = "tag=" + encodeURIComponent(tag) + "&tage=" + tage +
      "&thema=" + encodeURIComponent(el("thema").value.trim());
    if (SCHLUESSEL) q += "&schluessel=" + encodeURIComponent(SCHLUESSEL);
    fetch("/api/protokoll?" + q).then(function (r) { return r.json(); }).then(function (d) {
      var f = el("fazit"); f.textContent = d.text || d.fehler || "Keine Antwort.";
      f.classList.toggle("fehler", !d.ok);
      if (!d.ok) return;
      fuellen("gespraeche", d.gespraeche.map(function (g) {
        return zeile(uhr(g.zeit), g.rolle === "user" ? NUTZER : "Jarvis", g.text, g.rolle);
      }), "Keine Gespräche.");
      fuellen("aktionen", d.aktionen.map(function (a) {
        return zeile(uhr(a.zeit), a.status, a.werkzeug + (a.ergebnis ? " – " + a.ergebnis : ""));
      }), "Keine Aktionen.");
      fuellen("offen", d.offene_punkte.map(function (p) {
        return zeile(p.faellig || "", "#" + p.id, p.text);
      }), "Nichts offen.");
    }).catch(function () {
      var f = el("fazit"); f.textContent = "Der iMac antwortet nicht."; f.classList.add("fehler");
    });
  }

  Array.prototype.forEach.call(document.querySelectorAll(".leiste button"), function (b) {
    b.addEventListener("click", function () {
      Array.prototype.forEach.call(document.querySelectorAll(".leiste button"),
        function (x) { x.classList.remove("an"); });
      b.classList.add("an");
      tag = b.dataset.tag || "heute"; tage = parseInt(b.dataset.tage || "1", 10);
      holen();
    });
  });
  el("thema").addEventListener("input", function () {
    clearTimeout(wartet); wartet = setTimeout(holen, 300);
  });
  holen();
})();
</script>
</body>
</html>
"""


AUTOPILOT_HTML = r"""<!DOCTYPE html>
<html lang="de">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<meta name="theme-color" content="#03080F">
<link rel="icon" href="/symbol.svg" type="image/svg+xml">
<title>Heute zu tun</title>
<style>
:root{--grund:#03080F;--panel:#071420;--tief:#050D16;--rand:#0E2A3C;--rand-hell:#16425C;
  --akzent:#3AD1FF;--kupfer:#A6ECFF;--text:#E4F7FF;--gedaempft:#8DB4C6;--grau:#5D8799;
  --gruen:#4CC38A;--rot:#E5484D;
  --sans:-apple-system,BlinkMacSystemFont,"Helvetica Neue",Arial,sans-serif;
  --mono:ui-monospace,"SF Mono",Menlo,monospace}
*{box-sizing:border-box;margin:0;padding:0}
body{background:var(--grund);color:var(--text);font-family:var(--sans);
  -webkit-font-smoothing:antialiased;padding:0 0 60px}
header{padding:18px 20px;border-bottom:1px solid var(--rand);
  background:linear-gradient(90deg,rgba(58,209,255,.13),transparent 68%)}
header h1{font-size:18px;font-weight:600}
header p{font-size:12px;color:var(--grau);margin-top:4px;letter-spacing:.04em}
main{max-width:860px;margin:0 auto;padding:16px 20px}
.karte{background:var(--panel);border:1px solid var(--rand);border-radius:10px;
  padding:14px 16px;margin-bottom:12px}
.karte.lauf{border-left:3px solid var(--akzent)}
h2{font-size:11px;letter-spacing:.14em;text-transform:uppercase;color:var(--grau);
  margin:20px 0 8px;font-weight:600}
label{font-size:13px;color:var(--gedaempft)}
input[type=text],textarea{width:100%;font:14px var(--sans);color:var(--text);
  background:var(--tief);border:1px solid var(--rand-hell);border-radius:8px;padding:9px 11px}
textarea{font:13px/1.5 var(--sans);min-height:120px;resize:vertical;margin-top:8px}
.branchen{display:flex;flex-wrap:wrap;gap:6px 14px;margin:10px 0}
.branchen label{display:flex;gap:6px;align-items:center}
button,.knopf{font:inherit;font-size:13px;cursor:pointer;border-radius:8px;padding:8px 14px;
  border:1px solid var(--rand-hell);background:var(--tief);color:var(--text);
  text-decoration:none;display:inline-block}
button.haupt{background:var(--akzent);border-color:var(--akzent);color:#02121C;font-weight:700}
button:disabled{opacity:.5;cursor:default}
.reihe{display:flex;gap:8px;flex-wrap:wrap;margin-top:10px;align-items:center}
.art{font-size:10px;letter-spacing:.12em;text-transform:uppercase;color:var(--kupfer)}
.titel{font-size:16px;font-weight:600;margin:3px 0}
.grund{font-size:12px;color:var(--grau)}
.meldung{font-size:13px;color:var(--gedaempft);min-height:18px;margin-top:8px}
.meldung.fehler{color:var(--rot)}
.karte .meldung:empty{display:none}
.leer{color:var(--grau);font-size:14px;padding:8px 0}
.betrag{font-family:var(--mono);font-size:14px;color:var(--kupfer)}
.rot{color:var(--rot)}
.zeile{display:flex;gap:10px;align-items:center;flex-wrap:wrap;padding:8px 0;
  border-top:1px solid var(--rand);font-size:13px}
.zeile:first-child{border-top:0}
.zeile .wer{flex:1;min-width:160px}
.zeile a{color:var(--akzent)}
:focus-visible{outline:2px solid var(--akzent);outline-offset:2px}
</style>
</head>
<body>
<header>
  <h1 id="titel">Heute zu tun</h1>
  <p id="unter"></p>
</header>
<main>
  <div class="karte lauf">
    <div id="laufText">Wird geholt …</div>
    <div class="reihe">
      <button class="haupt" id="jetzt">Jetzt arbeiten</button>
      <span class="meldung" id="laufMeldung"></span>
    </div>
  </div>

  <h2>Offene Punkte</h2>
  <div id="punkte"></div>

  <h2>Vom Autopilot</h2>
  <div id="liste"></div>

  <h2>Rechnungen</h2>
  <div class="karte">
    <div id="rechnungText">Wird geholt …</div>
    <p class="grund" style="margin-top:6px">Neue Rechnung? Sag Jarvis zum Beispiel:
      „Rechnung an Praxis Huber: Unterhaltsreinigung Oktober, 13 Einsätze zu 65 Euro“.
      Angebote genauso: „Angebot für Kanzlei Berger, 220 Quadratmeter, 3-mal die Woche“.</p>
  </div>
  <div id="rechnungen"></div>
  <div class="karte" id="letzteKarte" hidden>
    <div class="art" style="margin-bottom:4px">Zuletzt geschrieben</div>
    <div id="letzte"></div>
  </div>

  <h2>Einstellungen</h2>
  <div class="karte">
    <label for="name">Dein Name (so stellt Jarvis dich in Skripten vor)</label>
    <input id="name" type="text" autocomplete="off" style="margin-bottom:10px">
    <label for="firma">Name deiner Firma</label>
    <input id="firma" type="text" autocomplete="off" style="margin-bottom:10px">
    <details style="margin:4px 0 12px"><summary style="cursor:pointer;color:var(--kupfer);font-size:13px">
      Firmendaten für Rechnungen und Angebote</summary>
      <div style="display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-top:10px" id="firmendaten">
        <input type="text" data-feld="FIRMA_ADRESSE" placeholder="Adresse (Straße Nr, PLZ Ort)" style="grid-column:1/3">
        <input type="text" data-feld="FIRMA_UID" placeholder="UID (ATU12345678)">
        <input type="text" data-feld="FIRMA_TELEFON" placeholder="Telefon">
        <input type="text" data-feld="FIRMA_IBAN" placeholder="IBAN">
        <input type="text" data-feld="FIRMA_BIC" placeholder="BIC">
        <input type="text" data-feld="FIRMA_EMAIL" placeholder="E-Mail" style="grid-column:1/3">
        <input type="text" data-feld="RECHNUNG_START" style="grid-column:1/3"
          placeholder="Nächste Rechnungsnummer, falls du schon Rechnungen hast (z.B. 2026-046)">
        <label style="grid-column:1/3"><input type="checkbox" data-feld="KLEINUNTERNEHMER">
          Kleinunternehmer (keine Umsatzsteuer auf Rechnungen)</label>
      </div>
    </details>
    <label for="ort">In welchem Ort oder Bezirk suchst du Kunden?</label>
    <input id="ort" type="text" placeholder="zum Beispiel Linz oder Wien" autocomplete="off">
    <div class="branchen" id="branchen"></div>
    <label><input type="checkbox" id="an"> Von selbst arbeiten (<span id="uhrzeiten"></span>)</label>
    <div class="reihe">
      <button id="speichern">Speichern</button>
      <span class="meldung" id="einstMeldung"></span>
    </div>
  </div>
  <p class="grund" style="margin-top:14px">
    Jarvis schickt Mails nie von selbst: Gesendet wird erst, wenn du auf
    „Senden“ klickst. Neue Betriebe bekommen ein Anruf-Skript statt einer Mail,
    weil Werbemails ohne Einwilligung in der Regel nicht erlaubt sind.
  </p>
</main>
<script>
(function () {
  "use strict";
  var SCHLUESSEL = {{SCHLUESSEL_JSON}};
  var NUTZER = {{NUTZER_JSON}}, FIRMA = {{FIRMA_JSON}};
  var ARTEN = {anruf: "Anrufen", nachfassen: "Nachfassen", antwort: "Mail beantworten",
               hinweis: "Hinweis"};
  var el = function (id) { return document.getElementById(id); };
  var warten = null;

  el("titel").textContent = "Heute zu tun · " + NUTZER;
  el("unter").textContent = FIRMA + " · Jarvis arbeitet auf deinem iMac und legt hier alles ab";

  function url(p) {
    return p + (SCHLUESSEL ? (p.indexOf("?") < 0 ? "?" : "&") +
      "schluessel=" + encodeURIComponent(SCHLUESSEL) : "");
  }
  function holen(p, k) {
    var o = { headers: { "Content-Type": "application/json" } };
    if (k !== undefined) { o.method = "POST"; o.body = JSON.stringify(k); }
    return fetch(url(p), o).then(function (a) { return a.json(); });
  }
  function knopf(text, klasse, aktion) {
    var b = document.createElement("button");
    b.textContent = text; if (klasse) { b.className = klasse; }
    b.addEventListener("click", aktion); return b;
  }

  function karte(a) {
    var k = document.createElement("div"); k.className = "karte";
    var art = document.createElement("div"); art.className = "art";
    art.textContent = ARTEN[a.art] || a.art;
    var titel = document.createElement("div"); titel.className = "titel"; titel.textContent = a.titel;
    var grund = document.createElement("div"); grund.className = "grund"; grund.textContent = a.grund || "";
    k.appendChild(art); k.appendChild(titel); k.appendChild(grund);
    var betreff = null;
    if (a.art === "antwort") {
      betreff = document.createElement("input"); betreff.type = "text";
      betreff.value = a.betreff || ""; betreff.style.marginTop = "8px";
      k.appendChild(betreff);
    }
    var text = document.createElement("textarea"); text.value = a.text || "";
    k.appendChild(text);
    var meldung = document.createElement("div"); meldung.className = "meldung";
    var reihe = document.createElement("div"); reihe.className = "reihe";
    function machen(aktion) {
      return function () {
        meldung.className = "meldung"; meldung.textContent = "…";
        holen("/api/autopilot/aktion", {id: a.id, aktion: aktion, text: text.value,
                                        betreff: betreff ? betreff.value : undefined})
          .then(function (r) {
            meldung.textContent = r.text || "";
            if (r.ok) { k.style.opacity = ".45"; setTimeout(laden, 700); }
            else { meldung.className = "meldung fehler"; }
          }).catch(function () { meldung.className = "meldung fehler";
                                 meldung.textContent = "Der iMac antwortet nicht."; });
      };
    }
    if (a.art === "antwort") {
      reihe.appendChild(knopf("Senden an " + a.an, "haupt", machen("senden")));
    }
    if ((a.art === "anruf" || a.art === "nachfassen") && a.an) {
      var tel = document.createElement("a"); tel.className = "knopf";
      tel.href = "tel:" + a.an.replace(/[^+0-9]/g, ""); tel.textContent = "Anrufen " + a.an;
      reihe.appendChild(tel);
    }
    if (a.art !== "antwort") { reihe.appendChild(knopf("Erledigt", "", machen("erledigt"))); }
    reihe.appendChild(knopf("Verwerfen", "", machen("verwerfen")));
    k.appendChild(reihe); k.appendChild(meldung);
    return k;
  }

  function euro(x) {
    return Number(x || 0).toLocaleString("de-AT", {style: "currency", currency: "EUR"});
  }
  function datum(iso) {
    var t = String(iso || "").slice(0, 10).split("-");
    return t.length === 3 ? t[2] + "." + t[1] + "." + t[0] : String(iso || "");
  }
  function pdfLink(datei, text) {
    var a = document.createElement("a"); a.className = "knopf";
    a.href = url("/rechnung/" + encodeURIComponent(datei)); a.target = "_blank";
    a.rel = "noopener"; a.textContent = text; return a;
  }
  var STUFEN = ["", "Zahlungserinnerung", "1. Mahnung", "2. Mahnung"];
  var ARTNAMEN = {rechnung: "Rechnung", angebot: "Angebot", storno: "Storno"};

  function rechnungAktion(r, aktion, frage, meldung, karte) {
    return function () {
      if (frage && !window.confirm(frage)) { return; }
      meldung.className = "meldung"; meldung.textContent = "…";
      holen("/api/rechnung/aktion", {nummer: r.nummer, aktion: aktion}).then(function (x) {
        meldung.textContent = x.text || x.fehler || "";
        if (x.ok) { if (karte) { karte.style.opacity = ".45"; } setTimeout(rechnungenLaden, 900); }
        else { meldung.className = "meldung fehler"; }
      }).catch(function () { meldung.className = "meldung fehler";
                             meldung.textContent = "Der iMac antwortet nicht."; });
    };
  }

  function rechnungKarte(r) {
    var k = document.createElement("div"); k.className = "karte";
    var art = document.createElement("div"); art.className = "art";
    art.textContent = "Rechnung " + r.nummer + (r.mahnstufe ? " · " + STUFEN[r.mahnstufe] +
      " am " + datum(r.gemahnt_am) : "");
    var reihe0 = document.createElement("div"); reihe0.className = "reihe"; reihe0.style.marginTop = "2px";
    var titel = document.createElement("div"); titel.className = "titel"; titel.style.flex = "1";
    titel.textContent = r.kunde;
    var betrag = document.createElement("span"); betrag.className = "betrag"; betrag.textContent = euro(r.brutto);
    reihe0.appendChild(titel); reihe0.appendChild(betrag);
    var grund = document.createElement("div"); grund.className = "grund";
    grund.textContent = "vom " + datum(r.datum) + " · zahlbar bis " + datum(r.faellig);
    if (r.ueberfaellig_tage > 0) {
      var rot = document.createElement("span"); rot.className = "rot";
      rot.textContent = " · seit " + r.ueberfaellig_tage + (r.ueberfaellig_tage === 1 ? " Tag" : " Tagen") + " überfällig";
      grund.appendChild(rot);
    }
    var meldung = document.createElement("div"); meldung.className = "meldung";
    var reihe = document.createElement("div"); reihe.className = "reihe";
    if (r.datei) { reihe.appendChild(pdfLink(r.datei, "PDF ansehen")); }
    reihe.appendChild(knopf("Bezahlt", "haupt", rechnungAktion(r, "bezahlt",
      "Ist Rechnung " + r.nummer + " über " + euro(r.brutto) + " bezahlt? Jarvis bucht dann die Einnahme.",
      meldung, k)));
    if (r.ueberfaellig_tage > 0 && r.mahnstufe < 3) {
      reihe.appendChild(knopf(STUFEN[r.mahnstufe + 1] + " schreiben", "",
        rechnungAktion(r, "mahnen", "", meldung, null)));
    }
    if (r.mahn_datei) { reihe.appendChild(pdfLink(r.mahn_datei, STUFEN[r.mahnstufe] + " ansehen")); }
    if (r.email) {
      reihe.appendChild(knopf(r.mahn_datei ? "Mahnung senden" : "Senden", "",
        rechnungAktion(r, r.mahn_datei ? "mahnung_senden" : "senden",
          (r.mahn_datei ? STUFEN[r.mahnstufe] : "Rechnung " + r.nummer) + " jetzt an " + r.email + " schicken?",
          meldung, null)));
    }
    k.appendChild(art); k.appendChild(reihe0); k.appendChild(grund);
    k.appendChild(reihe); k.appendChild(meldung);
    return k;
  }

  function letzteZeile(r) {
    var z = document.createElement("div"); z.className = "zeile";
    var wer = document.createElement("span"); wer.className = "wer";
    wer.textContent = (ARTNAMEN[r.art] || r.art) + " " + r.nummer + " · " + r.kunde;
    var b = document.createElement("span"); b.className = "betrag"; b.textContent = euro(r.brutto);
    var st = document.createElement("span"); st.className = "grund"; st.textContent = r.status;
    z.appendChild(wer); z.appendChild(b); z.appendChild(st);
    if (r.datei) {
      var a = document.createElement("a"); a.href = url("/rechnung/" + encodeURIComponent(r.datei));
      a.target = "_blank"; a.rel = "noopener"; a.textContent = "PDF"; z.appendChild(a);
    }
    if (r.art === "angebot" && r.status === "offen") {
      var m = document.createElement("span"); m.className = "meldung"; m.style.marginTop = "0";
      z.appendChild(knopf("Angenommen", "", rechnungAktion(r, "angenommen", "", m, null)));
      z.appendChild(knopf("Abgelehnt", "", rechnungAktion(r, "abgelehnt", "", m, null)));
      z.appendChild(m);
    }
    return z;
  }

  function rechnungenLaden() {
    holen("/api/rechnungen").then(function (d) {
      el("rechnungText").textContent = d.text || "";
      var kasten = el("rechnungen"); kasten.textContent = "";
      d.offen.forEach(function (r) { kasten.appendChild(rechnungKarte(r)); });
      var letzte = el("letzte"); letzte.textContent = "";
      var andere = d.letzte.filter(function (r) { return !(r.art === "rechnung" && r.status === "offen"); });
      andere.slice(0, 12).forEach(function (r) { letzte.appendChild(letzteZeile(r)); });
      el("letzteKarte").hidden = !andere.length;
    }).catch(function () { el("rechnungText").textContent = "Rechnungen sind gerade nicht abrufbar."; });
  }

  function laden() {
    rechnungenLaden();
    holen("/api/autopilot").then(function (d) {
      var liste = el("liste"); liste.textContent = "";
      if (!d.aufgaben.length) {
        var l = document.createElement("div"); l.className = "leer";
        l.textContent = "Nichts vom Autopilot. Klick auf „Jetzt arbeiten“, dann sucht Jarvis neue Arbeit.";
        liste.appendChild(l);
      }
      d.aufgaben.forEach(function (a) { liste.appendChild(karte(a)); });
      var punkte = el("punkte"); punkte.textContent = "";
      if (!d.punkte.length) {
        var lp = document.createElement("div"); lp.className = "leer";
        lp.textContent = "Keine offenen Punkte. Sag zum Beispiel: „Leg einen Punkt an: Freitag Berger anrufen“.";
        punkte.appendChild(lp);
      }
      d.punkte.forEach(function (p) {
        var k = document.createElement("div"); k.className = "karte";
        var reihe = document.createElement("div"); reihe.className = "reihe"; reihe.style.marginTop = "0";
        var t = document.createElement("div"); t.className = "titel"; t.style.flex = "1";
        t.textContent = p.text;
        var f = document.createElement("span"); f.className = "grund";
        f.textContent = p.faellig ? "fällig " + p.faellig_text : "";
        reihe.appendChild(t); reihe.appendChild(f);
        reihe.appendChild(knopf("Erledigt", "", function () {
          holen("/api/autopilot/punkt", {id: p.id}).then(function () {
            k.style.opacity = ".45"; setTimeout(laden, 500);
          });
        }));
        k.appendChild(reihe); punkte.appendChild(k);
      });
      var e = d.einstellungen;
      ["ort", "name", "firma"].forEach(function (f) {
        if (document.activeElement !== el(f)) { el(f).value = e[f] || ""; }
      });
      Array.prototype.forEach.call(document.querySelectorAll("#firmendaten [data-feld]"), function (f) {
        var wert = (e.firmendaten || {})[f.getAttribute("data-feld")];
        if (f.type === "checkbox") { f.checked = !!wert; }
        else if (document.activeElement !== f) { f.value = wert || ""; }
      });
      el("an").checked = !!e.an; el("uhrzeiten").textContent = e.uhrzeiten;
      var kasten = el("branchen");
      if (!kasten.childNodes.length) {
        e.alle_branchen.forEach(function (b) {
          var lab = document.createElement("label"); var c = document.createElement("input");
          c.type = "checkbox"; c.value = b; c.checked = e.branchen.indexOf(b) >= 0;
          lab.appendChild(c); lab.appendChild(document.createTextNode(b)); kasten.appendChild(lab);
        });
      }
      var lauf = d.letzter_lauf || {};
      el("laufText").textContent = d.laeuft ? "Jarvis arbeitet gerade …" :
        (lauf.ergebnis ? "Zuletzt (" + (lauf.ende || lauf.start || "").slice(0, 16) + "): " +
         lauf.ergebnis : "Jarvis hat noch nicht gearbeitet.");
      el("jetzt").disabled = !!d.laeuft;
      clearTimeout(warten);
      if (d.laeuft) { warten = setTimeout(laden, 4000); }
    }).catch(function () { el("laufText").textContent = "Der iMac antwortet nicht."; });
  }

  el("jetzt").addEventListener("click", function () {
    el("jetzt").disabled = true;
    holen("/api/autopilot/laufen", {}).then(function (r) {
      el("laufMeldung").textContent = r.text || ""; setTimeout(laden, 1500);
    });
  });
  function firmendatenLesen() {
    var daten = {};
    Array.prototype.forEach.call(document.querySelectorAll("#firmendaten [data-feld]"), function (f) {
      daten[f.getAttribute("data-feld")] = f.type === "checkbox" ? f.checked : f.value;
    });
    return daten;
  }
  el("speichern").addEventListener("click", function () {
    var gewaehlt = Array.prototype.filter.call(
      document.querySelectorAll("#branchen input"), function (c) { return c.checked; })
      .map(function (c) { return c.value; });
    holen("/api/autopilot/einstellungen", {ort: el("ort").value, branchen: gewaehlt,
                                           an: el("an").checked, name: el("name").value,
                                           firma: el("firma").value,
                                           firmendaten: firmendatenLesen()}).then(function (r) {
      el("einstMeldung").textContent = r.text || ""; laden();
    });
  });
  laden();
})();
</script>
</body>
</html>
"""
