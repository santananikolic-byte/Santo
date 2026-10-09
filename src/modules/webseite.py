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
<meta name="theme-color" content="#08090B">
<link rel="icon" href="/symbol.svg" type="image/svg+xml">
<title>Jarvis</title>
<style>
:root{
  --grund:#08090B; --tief:#0A0D14; --panel:#0F1113; --rand:#1C1F23;
  --rand-hell:#2A3036; --akzent:#E8622C; --kupfer:#F0A882; --text:#F2EFEA;
  --gedaempft:#A0A6AC; --grau:#7E858C; --gruen:#4CC38A; --rot:#E5484D;
  --sans:-apple-system,BlinkMacSystemFont,"Helvetica Neue",Arial,sans-serif;
  --mono:ui-monospace,"SF Mono",Menlo,monospace;
}
*{box-sizing:border-box;margin:0;padding:0}
html,body{height:100%;overflow:hidden}
body{
  background:radial-gradient(ellipse 120% 80% at 50% 120%,#0E1220 0%,var(--grund) 62%);
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
  background:linear-gradient(90deg,rgba(232,98,44,.13),transparent 68%);
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
  background:radial-gradient(circle at 34% 30%,#F3B593,#D9764B 46%,#A34F2C);
  box-shadow:0 0 40px -6px rgba(232,98,44,.5);transition:transform .35s,box-shadow .35s;
}
.kugel .welle{position:absolute;inset:0;border-radius:50%;border:1px solid var(--akzent);
              opacity:0;pointer-events:none}

/* Zustände */
body[data-zustand="schlaeft"] .kugel .kern{transform:scale(.82);
  box-shadow:0 0 26px -10px rgba(232,98,44,.4);filter:saturate(.55)}
body[data-zustand="wach"] .ring{border-color:rgba(232,98,44,.55)}
body[data-zustand="wach"] .kugel .kern{transform:scale(1.08);
  box-shadow:0 0 70px -4px rgba(232,98,44,.75)}
body[data-zustand="wach"] .welle{animation:welle 1.7s ease-out infinite}
body[data-zustand="wach"] .welle.w2{animation-delay:.55s}
body[data-zustand="wach"] .welle.w3{animation-delay:1.1s}
@keyframes welle{0%{opacity:.55;transform:scale(.55)}100%{opacity:0;transform:scale(1.05)}}
body[data-zustand="denkt"] .ring{border-color:rgba(232,98,44,.45);
  border-top-color:var(--akzent);animation:dreh 1.1s linear infinite}
body[data-zustand="denkt"] .ring2{animation:dreh 1.6s linear infinite reverse}
body[data-zustand="denkt"] .ring3{animation:dreh 2.2s linear infinite}
@keyframes dreh{to{transform:rotate(360deg)}}
body[data-zustand="spricht"] .kugel .kern{animation:reden .5s ease-in-out infinite alternate}
@keyframes reden{from{transform:scale(1)}to{transform:scale(1.16)}}
body[data-zustand="aus"] .kugel .kern{filter:grayscale(.85) saturate(.3);transform:scale(.75)}

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
.tippen button{background:var(--akzent);color:#1A0E08;border-radius:11px;
               padding:12px 20px;font-weight:700}

/* ---- Freigabe ---- */
.schleier{position:fixed;inset:0;background:rgba(4,5,6,.9);display:none;
          place-items:center;padding:20px;z-index:60;backdrop-filter:blur(4px)}
.schleier.zeigen{display:grid}
.frage{background:var(--panel);border:1px solid var(--akzent);border-radius:16px;
       max-width:620px;width:100%;overflow:hidden;
       box-shadow:0 30px 90px -24px rgba(232,98,44,.5)}
.frage .kopf{display:flex;align-items:center;gap:12px;padding:13px 20px;
             background:rgba(232,98,44,.12);border-bottom:1px solid var(--rand)}
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
.frage .ja{background:var(--akzent);color:#1A0E08}
.frage .nein{background:var(--tief);border:1px solid var(--rand-hell);color:var(--text)}
.frage{max-height:92vh;overflow-y:auto}
.frage input{width:100%;padding:13px 14px;border-radius:9px;font:14px var(--mono);
  background:var(--tief);border:1px solid var(--rand-hell);color:var(--text);
  user-select:text;-webkit-user-select:text}
.frage .meldung{padding:0 20px 4px;font-size:13px;min-height:20px;color:var(--gedaempft)}
.frage .meldung.fehler{color:var(--rot)}

@media(max-width:640px){
  .ticker{gap:12px;padding:8px 12px;font-size:10px}
  .ticker .rechts{width:100%;margin-left:0;justify-content:flex-start}
  .zahl{padding:9px 10px}.zahl .wert{font-size:15px}
  main{gap:18px;padding:14px}
}
</style>
</head>
<body data-zustand="aus">

<div class="ticker">
  <span class="pkt" id="pkt"></span>
  <span id="lage">Stand wird geholt …</span>
  <span class="rechts">
    <button class="mini" id="tippenAn" title="Notweg, falls das Mikrofon streikt">Tippen</button>
    <a href="/protokoll" data-seite target="_blank" rel="noopener">Protokoll</a>
    <a href="/dashboard" data-seite target="_blank" rel="noopener">Cockpit</a>
    <a href="/sales" data-seite target="_blank" rel="noopener">Sales</a>
  </span>
</div>

<main>
  <div class="kugel" id="kugel" role="button" tabindex="0"
       title="Antippen weckt Jarvis auch ohne Weckwort">
    <span class="ring"></span><span class="ring ring2"></span><span class="ring ring3"></span>
    <span class="welle"></span><span class="welle w2"></span><span class="welle w3"></span>
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
    <div class="kopf"><h2>Anthropic-Schlüssel</h2></div>
    <div class="inhalt" style="border-bottom:1px solid var(--rand)">
      <p class="sagen" style="padding:0 0 10px;text-align:left">
        <b>Mit deinem Claude-Abo, ohne Extra-Kosten:</b> Ist Claude Code auf
        diesem Rechner installiert und angemeldet, denkt Jarvis darüber. Es gilt
        das Limit deines Abos, und Antworten brauchen ein paar Sekunden.</p>
      <div class="meldung" id="ccMeldung" style="padding:0 0 8px"></div>
      <div class="knoepfe" style="padding:0"><button class="ja" id="ccSpeichern">
        Claude Code nutzen</button></div>
    </div>
    <div class="inhalt">
      <div class="aktion">Ein Schritt fehlt</div>
      <p class="sagen" style="padding:0 0 12px;text-align:left">
        Ohne Schlüssel kann ich nicht denken. Hol ihn auf
        <b>console.anthropic.com</b> unter Settings &rarr; API Keys, kopiere ihn
        und füge ihn hier ein. Er bleibt auf diesem Rechner.</p>
      <input id="schluesselFeld" type="password" placeholder="sk-ant-…"
             autocomplete="off" spellcheck="false">
    </div>
    <p class="meldung" id="schluesselMeldung"></p>
    <div class="knoepfe">
      <button class="ja" id="schluesselSpeichern">Speichern</button>
    </div>
    <div class="inhalt" style="border-top:1px solid var(--rand)">
      <p class="sagen" style="padding:0 0 10px;text-align:left">
        <b>Kein Schlüssel, keine Kosten?</b> Dann denkt Jarvis mit einem
        Modell auf diesem Rechner (Ollama, ollama.com). Das ist kostenlos und
        ohne Limit, aber langsamer und schwächer als Claude.</p>
      <input id="lokalFeld" type="text" value="qwen2.5:3b" autocomplete="off"
             spellcheck="false">
    </div>
    <p class="meldung" id="lokalMeldung"></p>
    <div class="knoepfe">
      <button class="nein" id="lokalSpeichern">Lokales Modell nutzen</button>
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
    holen("/api/reden", { text: text }).then(function (a) {
      var antwort = a.antwort || a.fehler || "Ich habe keine Antwort bekommen.";
      el("antwort").textContent = antwort;
      el("antwort").className = "antwort" + (a.ok ? "" : " fehler");
      laeuft = false;
      sprich(antwort, function () { setzeZustand("schlaeft"); });
      lageHolen(); zahlenHolen();
    }).catch(function (f) {
      el("antwort").textContent = "Ich erreiche den Server nicht: " + f.message;
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
  function zustandHolen() {
    holen("/api/zustand").then(function (a) {
      el("pkt").className = "pkt " + (a.einsatzbereit ? "an" : "aus");
      el("pkt").title = a.einsatzbereit ? a.werkzeuge + " Werkzeuge bereit"
                                        : "Kein Anthropic-Schlüssel";
      if (!a.einsatzbereit) {
        el("schluesselDialog").classList.add("zeigen");
        el("antwort").textContent = "Es ist kein Anthropic-Schlüssel hinterlegt. " +
          "Ohne ihn kann ich nicht denken.";
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
  function ccSpeichern() {
    var meldung = el("ccMeldung");
    meldung.className = "meldung"; meldung.textContent = "Ich frage Claude Code, das dauert kurz …";
    el("ccSpeichern").disabled = true;
    holen("/api/claudecode", {}).then(function (a) {
      el("ccSpeichern").disabled = false;
      meldung.textContent = a.text || "";
      if (a.ok) {
        el("schluesselDialog").classList.remove("zeigen");
        el("antwort").textContent = ""; el("antwort").className = "antwort";
        zustandHolen();
      } else { meldung.className = "meldung fehler"; }
    }).catch(function () {
      el("ccSpeichern").disabled = false;
      meldung.className = "meldung fehler";
      meldung.textContent = "Der Server antwortet nicht.";
    });
  }
  el("ccSpeichern").addEventListener("click", ccSpeichern);
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
<meta name="theme-color" content="#08090B">
<link rel="icon" href="/symbol.svg" type="image/svg+xml">
<title>Jarvis Protokoll</title>
<style>
:root{--grund:#08090B;--panel:#0F1113;--rand:#1C1F23;--akzent:#E8622C;
  --kupfer:#F0A882;--text:#F2EFEA;--gedaempft:#A0A6AC;--grau:#7E858C;
  --gruen:#4CC38A;--rot:#E5484D;
  --sans:-apple-system,BlinkMacSystemFont,"Helvetica Neue",Arial,sans-serif;
  --mono:ui-monospace,"SF Mono",Menlo,monospace}
*{box-sizing:border-box;margin:0;padding:0}
body{background:var(--grund);color:var(--text);font-family:var(--sans);
  -webkit-font-smoothing:antialiased;padding:0 0 60px}
header{padding:18px 20px;border-bottom:1px solid var(--rand);
  background:linear-gradient(90deg,rgba(232,98,44,.13),transparent 68%)}
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
