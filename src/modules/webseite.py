#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Die Oberfläche der Web-App als eine einzige Seite.

Bewusst ohne Baukasten und ohne Nachladen aus dem Netz: Der Server liefert
genau diese Datei aus, und sie läuft. Kein Build, keine Abhängigkeit, die in
zwei Jahren nicht mehr da ist.

Das Mikrofon läuft über die Spracherkennung des Browsers. Safari und Chrome
können Deutsch, Firefox nicht - das sagt die Seite dann auch, statt einen
Knopf zu zeigen, der nichts tut.
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
:root {
  --grund:#08090B; --panel:#0F1113; --erhoben:#14171A; --rand:#1C1F23;
  --rand-hell:#2A3036; --akzent:#E8622C; --kupfer:#F0A882; --text:#F2EFEA;
  --gedaempft:#A0A6AC; --grau:#7E858C; --gruen:#4CC38A; --rot:#E5484D;
  --gelb:#E8A33C;
  --sans:-apple-system,BlinkMacSystemFont,"Helvetica Neue",Arial,sans-serif;
  --mono:ui-monospace,"SF Mono",Menlo,monospace;
}
*{box-sizing:border-box;margin:0;padding:0}
html,body{height:100%}
body{
  background:var(--grund);color:var(--text);font-family:var(--sans);
  font-size:16px;line-height:1.55;-webkit-font-smoothing:antialiased;
  display:flex;flex-direction:column;overflow:hidden;
}
button{font-family:inherit;cursor:pointer;border:none;background:none;color:inherit}
:focus-visible{outline:2px solid var(--akzent);outline-offset:2px;border-radius:6px}

/* Kopf */
header{
  display:flex;align-items:center;gap:14px;padding:11px 18px;
  border-bottom:1px solid var(--rand);background:var(--panel);flex:none;
}
.marke{font-size:13px;font-weight:700;letter-spacing:.2em;text-transform:uppercase}
.marke span{color:var(--akzent)}
.ampel{width:8px;height:8px;border-radius:50%;background:var(--grau);flex:none}
.ampel.an{background:var(--gruen);box-shadow:0 0 8px var(--gruen)}
.ampel.aus{background:var(--rot);box-shadow:0 0 8px var(--rot)}
header nav{margin-left:auto;display:flex;gap:7px}
header nav a,header nav button{
  font-size:11px;letter-spacing:.1em;text-transform:uppercase;color:var(--grau);
  border:1px solid var(--rand-hell);border-radius:6px;padding:6px 11px;
  text-decoration:none;
}
header nav a:hover,header nav button:hover{color:var(--kupfer);border-color:var(--akzent)}

/* Lageleiste */
.lage{
  padding:9px 18px;font-size:13px;color:var(--gedaempft);
  border-bottom:1px solid var(--rand);
  background:linear-gradient(90deg,rgba(232,98,44,.10),transparent 70%);
  flex:none;
}
.lage b{color:var(--kupfer);font-weight:600}

/* Hauptbereich */
main{flex:1;display:grid;grid-template-columns:1fr 320px;min-height:0}

.gespraech{display:flex;flex-direction:column;min-height:0}
.verlauf{flex:1;overflow-y:auto;padding:20px 18px 8px;display:flex;
         flex-direction:column;gap:12px}
.blase{max-width:min(78%,640px);padding:11px 15px;border-radius:14px;
       font-size:15px;line-height:1.6;white-space:pre-wrap;word-wrap:break-word}
.blase.du{align-self:flex-end;background:var(--erhoben);
          border:1px solid var(--rand-hell);border-bottom-right-radius:5px}
.blase.jarvis{align-self:flex-start;background:var(--panel);
              border:1px solid var(--rand);border-bottom-left-radius:5px}
.blase.jarvis.fehler{border-color:rgba(229,72,77,.5);color:#F3B0B2}
.blase .wer{font-size:10px;letter-spacing:.13em;text-transform:uppercase;
            color:var(--grau);margin-bottom:5px}
.blase.jarvis .wer{color:var(--akzent)}
.leerzustand{margin:auto;text-align:center;color:var(--grau);max-width:400px;padding:20px}
.leerzustand h2{font-size:22px;color:var(--text);margin-bottom:10px;font-weight:700}
.leerzustand p{font-size:14px;line-height:1.7}
.leerzustand code{font-family:var(--mono);font-size:13px;color:var(--kupfer)}

.denkt{align-self:flex-start;display:flex;gap:5px;padding:12px 16px}
.denkt i{width:7px;height:7px;border-radius:50%;background:var(--akzent);
         animation:pulsen 1.2s ease-in-out infinite}
.denkt i:nth-child(2){animation-delay:.18s}
.denkt i:nth-child(3){animation-delay:.36s}
@keyframes pulsen{0%,100%{opacity:.25;transform:translateY(0)}
                  50%{opacity:1;transform:translateY(-3px)}}

/* Eingabe */
.eingabe{flex:none;padding:12px 18px 16px;border-top:1px solid var(--rand);
         background:var(--panel);display:flex;gap:10px;align-items:flex-end}
.eingabe textarea{
  flex:1;resize:none;background:var(--erhoben);color:var(--text);
  border:1px solid var(--rand-hell);border-radius:11px;padding:11px 14px;
  font-family:inherit;font-size:15px;line-height:1.5;max-height:140px;min-height:46px;
}
.eingabe textarea::placeholder{color:var(--grau)}
.knopf{
  width:46px;height:46px;border-radius:50%;flex:none;display:grid;place-items:center;
  background:var(--erhoben);border:1px solid var(--rand-hell);
  transition:background .15s,border-color .15s,transform .1s;
}
.knopf:hover{border-color:var(--akzent)}
.knopf:active{transform:scale(.94)}
.knopf svg{width:20px;height:20px;fill:currentColor}
.knopf.mikro.hoert{background:var(--akzent);border-color:var(--akzent);color:#1A0E08;
                   animation:atmen 1.4s ease-in-out infinite}
@keyframes atmen{0%,100%{box-shadow:0 0 0 0 rgba(232,98,44,.55)}
                 70%{box-shadow:0 0 0 13px rgba(232,98,44,0)}}
.knopf.senden{background:var(--akzent);border-color:var(--akzent);color:#1A0E08}
.knopf[disabled]{opacity:.4;cursor:default}

/* Seitenspalte */
.seite{border-left:1px solid var(--rand);background:var(--panel);overflow-y:auto;
       padding:14px;display:flex;flex-direction:column;gap:11px}
.kachel{background:var(--erhoben);border:1px solid var(--rand);border-radius:10px;
        padding:12px 14px}
.kachel h3{font-size:10px;letter-spacing:.14em;text-transform:uppercase;
           color:var(--grau);margin-bottom:8px;font-weight:600}
.kachel .zahl{font-size:21px;font-weight:700;letter-spacing:-.01em;
              font-variant-numeric:tabular-nums}
.kachel .zahl.gut{color:var(--gruen)} .kachel .zahl.schlecht{color:var(--rot)}
.kachel .zahl.akzent{color:var(--akzent)}
.kachel .neben{font-size:12px;color:var(--grau);margin-top:3px;line-height:1.5}
.kachel ul{list-style:none} .kachel li{font-size:13px;padding:5px 0;
           border-bottom:1px solid var(--rand)}
.kachel li:last-child{border-bottom:none}
.kachel li small{display:block;color:var(--grau);font-size:11.5px}
.leer{color:#4A5157;font-style:italic;font-size:12.5px}
.schnell{display:flex;flex-wrap:wrap;gap:6px}
.schnell button{font-size:12px;border:1px solid var(--rand-hell);border-radius:999px;
                padding:6px 12px;color:var(--gedaempft)}
.schnell button:hover{border-color:var(--akzent);color:var(--kupfer)}

/* Freigabe */
.schleier{position:fixed;inset:0;background:rgba(4,5,6,.86);display:none;
          place-items:center;padding:20px;z-index:50;backdrop-filter:blur(3px)}
.schleier.zeigen{display:grid}
.frage{background:var(--panel);border:1px solid var(--akzent);border-radius:14px;
       max-width:560px;width:100%;overflow:hidden;
       box-shadow:0 24px 70px -20px rgba(232,98,44,.4)}
.frage header{background:rgba(232,98,44,.11);border-bottom:1px solid var(--rand)}
.frage h2{font-size:13px;letter-spacing:.16em;text-transform:uppercase;
          color:var(--akzent);font-weight:700}
.frage .rest{margin-left:auto;font-family:var(--mono);font-size:12px;color:var(--grau)}
.frage .inhalt{padding:16px 18px}
.frage .aktion{font-size:19px;font-weight:700;margin-bottom:9px}
.frage pre{background:var(--erhoben);border:1px solid var(--rand);border-radius:8px;
           padding:11px 13px;font-family:var(--mono);font-size:12.5px;line-height:1.6;
           color:var(--kupfer);max-height:240px;overflow:auto;white-space:pre-wrap;
           word-break:break-word}
.frage .knoepfe{display:flex;gap:10px;padding:0 18px 18px}
.frage .knoepfe button{flex:1;padding:13px;border-radius:9px;font-weight:700;
                       font-size:15px}
.frage .ja{background:var(--akzent);color:#1A0E08}
.frage .nein{background:var(--erhoben);border:1px solid var(--rand-hell);
             color:var(--text)}
.frage .hinweis{padding:0 18px 14px;font-size:12px;color:var(--grau)}

/* Schmale Fenster ganz zum Schluss: gleiche Genauigkeit gewinnt die spaetere
   Regel, deshalb duerfen diese hier nicht weiter oben stehen. */
main,.gespraech,.verlauf,.eingabe,.blase,.kachel{min-width:0}
@media(max-width:900px){
  main{grid-template-columns:1fr}
  .seite{display:none}
  .blase{max-width:88%}
  header{padding:10px 12px;gap:10px}
  header nav a,header nav button{padding:6px 9px;font-size:10px}
  .lage{padding:8px 12px;font-size:12.5px}
  .verlauf{padding:16px 12px 6px}
  .eingabe{padding:10px 12px 14px}
}
@media(max-width:430px){
  .marke{font-size:11px;letter-spacing:.12em}
  #wer{display:none}
  header nav a[href="/sales"]{display:none}
}
</style>
</head>
<body>

<header>
  <span class="ampel" id="ampel"></span>
  <span class="marke">Jarvis <span id="wer"></span></span>
  <nav>
    <button id="sprechenAn" title="Antworten vorlesen">Stimme an</button>
    <button id="neu">Neu</button>
    <a href="/dashboard" target="_blank" rel="noopener">Cockpit</a>
    <a href="/sales" target="_blank" rel="noopener">Sales</a>
  </nav>
</header>

<div class="lage" id="lage">Stand wird geholt …</div>

<main>
  <section class="gespraech">
    <div class="verlauf" id="verlauf">
      <div class="leerzustand" id="leerzustand">
        <h2>Sag etwas.</h2>
        <p>Drück auf das Mikrofon und sprich, oder tippe unten.<br>
           Zum Beispiel: <code>Wie steht es?</code> ·
           <code>Was muss ich heute nachfassen?</code> ·
           <code>Trag 59,90 Tankstelle als Ausgabe ein</code></p>
      </div>
    </div>

    <div class="eingabe">
      <button class="knopf mikro" id="mikro" title="Sprechen" aria-label="Sprechen">
        <svg viewBox="0 0 24 24"><path d="M12 14a3 3 0 0 0 3-3V5a3 3 0 0 0-6 0v6a3 3 0 0 0 3 3zm5-3a5 5 0 0 1-10 0H5a7 7 0 0 0 6 6.92V21h2v-3.08A7 7 0 0 0 19 11z"/></svg>
      </button>
      <textarea id="feld" rows="1" placeholder="Schreib oder sprich …"></textarea>
      <button class="knopf senden" id="senden" title="Senden" aria-label="Senden">
        <svg viewBox="0 0 24 24"><path d="M3 20.5v-6l9-2.5-9-2.5v-6l19 8.5z"/></svg>
      </button>
    </div>
  </section>

  <aside class="seite">
    <div class="kachel">
      <h3>Was der Betrieb tragen muss</h3>
      <div class="zahl" id="bedarfZahl">–</div>
      <div class="neben" id="bedarfText">wird geholt …</div>
    </div>
    <div class="kachel">
      <h3>Kasse diesen Monat</h3>
      <div class="zahl" id="kasseZahl">–</div>
      <div class="neben" id="kasseText">wird geholt …</div>
    </div>
    <div class="kachel">
      <h3>Heute nachfassen</h3>
      <div id="nachfassen"><span class="leer">wird geholt …</span></div>
    </div>
    <div class="kachel">
      <h3>Schnell</h3>
      <div class="schnell" id="schnell"></div>
    </div>
  </aside>
</main>

<div class="schleier" id="schleier">
  <div class="frage">
    <header>
      <h2>Freigabe nötig</h2>
      <span class="rest" id="freigabeRest"></span>
    </header>
    <div class="inhalt">
      <div class="aktion" id="freigabeAktion"></div>
      <pre id="freigabeDetails"></pre>
    </div>
    <p class="hinweis">Ohne dein Ja passiert nichts. Keine Antwort gilt als Nein.</p>
    <div class="knoepfe">
      <button class="nein" id="freigabeNein">Nein</button>
      <button class="ja" id="freigabeJa">Ja, mach</button>
    </div>
  </div>
</div>

<script>
(function () {
  "use strict";
  var SCHLUESSEL = "{{SCHLUESSEL}}";

  var el = function (id) { return document.getElementById(id); };
  var verlauf = el("verlauf"), feld = el("feld");
  var sprechen = true, hoertZu = false, laeuft = false;
  var aktuelleFreigabe = null, restZaehler = null;

  /* ---------- Netz ---------- */
  function url(pfad) {
    return pfad + (SCHLUESSEL ? (pfad.indexOf("?") < 0 ? "?" : "&") +
      "schluessel=" + encodeURIComponent(SCHLUESSEL) : "");
  }
  function holen(pfad, koerper) {
    var einstellungen = { headers: { "Content-Type": "application/json" } };
    if (koerper !== undefined) {
      einstellungen.method = "POST";
      einstellungen.body = JSON.stringify(koerper);
    }
    return fetch(url(pfad), einstellungen).then(function (a) { return a.json(); });
  }
  function euro(n) {
    if (typeof n !== "number") { return "–"; }
    return n.toLocaleString("de-DE", { minimumFractionDigits: 2,
      maximumFractionDigits: 2 }) + " €";
  }

  /* ---------- Gespräch ---------- */
  function blase(wer, text, fehler) {
    var leerzustand = el("leerzustand");
    if (leerzustand) { leerzustand.remove(); }
    var knoten = document.createElement("div");
    knoten.className = "blase " + (wer === "du" ? "du" : "jarvis") +
                       (fehler ? " fehler" : "");
    var kopf = document.createElement("div");
    kopf.className = "wer";
    kopf.textContent = wer === "du" ? "Du" : "Jarvis";
    knoten.appendChild(kopf);
    knoten.appendChild(document.createTextNode(text));
    verlauf.appendChild(knoten);
    verlauf.scrollTop = verlauf.scrollHeight;
    return knoten;
  }
  function denktAn() {
    var k = document.createElement("div");
    k.className = "denkt"; k.id = "denkt";
    k.innerHTML = "<i></i><i></i><i></i>";
    verlauf.appendChild(k);
    verlauf.scrollTop = verlauf.scrollHeight;
  }
  function denktAus() {
    var k = el("denkt");
    if (k) { k.remove(); }
  }

  /* ---------- Stimme ---------- */
  var stimmen = [];
  function stimmenLaden() {
    stimmen = window.speechSynthesis ? window.speechSynthesis.getVoices() : [];
  }
  if (window.speechSynthesis) {
    stimmenLaden();
    window.speechSynthesis.onvoiceschanged = stimmenLaden;
  }
  function sprich(text) {
    if (!sprechen || !window.speechSynthesis || !text) { return; }
    window.speechSynthesis.cancel();
    var satz = new SpeechSynthesisUtterance(text);
    satz.lang = "de-DE";
    satz.rate = 1.05;
    var deutsch = stimmen.filter(function (s) { return /^de/i.test(s.lang); });
    var lieber = deutsch.filter(function (s) {
      return /markus|yannick|petra|anna|viktor|google/i.test(s.name);
    });
    if (lieber.length) { satz.voice = lieber[0]; }
    else if (deutsch.length) { satz.voice = deutsch[0]; }
    window.speechSynthesis.speak(satz);
  }

  /* ---------- Senden ---------- */
  function senden(text) {
    text = (text || feld.value).trim();
    if (!text || laeuft) { return; }
    laeuft = true;
    feld.value = "";
    feld.style.height = "auto";
    blase("du", text);
    denktAn();
    el("senden").disabled = true;
    holen("/api/reden", { text: text }).then(function (a) {
      denktAus();
      var antwort = a.antwort || a.fehler || "Keine Antwort bekommen.";
      blase("jarvis", antwort, !a.ok);
      if (a.ok) { sprich(antwort); }
      lageHolen();
      kachelnHolen();
    }).catch(function (fehler) {
      denktAus();
      blase("jarvis", "Ich erreiche den Server nicht: " + fehler.message, true);
    }).then(function () {
      laeuft = false;
      el("senden").disabled = false;
    });
  }

  el("senden").addEventListener("click", function () { senden(); });
  feld.addEventListener("keydown", function (e) {
    if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); senden(); }
  });
  feld.addEventListener("input", function () {
    feld.style.height = "auto";
    feld.style.height = Math.min(feld.scrollHeight, 140) + "px";
  });

  /* ---------- Mikrofon ---------- */
  var Erkennung = window.SpeechRecognition || window.webkitSpeechRecognition;
  var erkennung = null;
  if (!Erkennung) {
    var mikro = el("mikro");
    mikro.disabled = true;
    mikro.title = "Dieser Browser kann keine Spracherkennung. Safari oder Chrome nehmen.";
  } else {
    erkennung = new Erkennung();
    erkennung.lang = "de-DE";
    erkennung.interimResults = true;
    erkennung.continuous = false;
    erkennung.onresult = function (e) {
      var text = "";
      for (var i = e.resultIndex; i < e.results.length; i++) {
        text += e.results[i][0].transcript;
      }
      feld.value = text;
      if (e.results[e.results.length - 1].isFinal) {
        hoertAuf();
        senden(text);
      }
    };
    erkennung.onerror = function (e) {
      hoertAuf();
      if (e.error === "not-allowed") {
        blase("jarvis", "Der Browser lässt mich nicht ans Mikrofon. Erlaub den " +
          "Zugriff in der Adressleiste, dann geht es.", true);
      } else if (e.error !== "aborted" && e.error !== "no-speech") {
        blase("jarvis", "Mit dem Mikrofon stimmt etwas nicht: " + e.error, true);
      }
    };
    erkennung.onend = function () { hoertAuf(); };
    el("mikro").addEventListener("click", function () {
      if (hoertZu) { erkennung.stop(); hoertAuf(); return; }
      if (window.speechSynthesis) { window.speechSynthesis.cancel(); }
      try { erkennung.start(); hoertZu = true; el("mikro").classList.add("hoert"); }
      catch (fehler) { hoertAuf(); }
    });
  }
  function hoertAuf() {
    hoertZu = false;
    el("mikro").classList.remove("hoert");
  }

  /* ---------- Kopfzeile ---------- */
  el("sprechenAn").addEventListener("click", function () {
    sprechen = !sprechen;
    this.textContent = sprechen ? "Stimme an" : "Stimme aus";
    if (!sprechen && window.speechSynthesis) { window.speechSynthesis.cancel(); }
  });
  el("neu").addEventListener("click", function () {
    holen("/api/verlauf/neu", {}).then(function () {
      verlauf.innerHTML = "";
      blase("jarvis", "Neues Gespräch. Was brauchst du?");
    });
  });

  /* ---------- Stand ---------- */
  function lageHolen() {
    holen("/api/lage").then(function (a) {
      el("lage").textContent = a.text || a.fehler || "Kein Stand abrufbar.";
    }).catch(function () {
      el("lage").textContent = "Der Server antwortet nicht.";
    });
  }
  function zustandHolen() {
    holen("/api/zustand").then(function (a) {
      el("ampel").className = "ampel " + (a.einsatzbereit ? "an" : "aus");
      el("ampel").title = a.einsatzbereit
        ? "Bereit · " + a.werkzeuge + " Werkzeuge"
        : "Kein Anthropic-Schlüssel hinterlegt";
      el("wer").textContent = "// " + (a.firma || "");
      if (!a.einsatzbereit) {
        blase("jarvis", "Es ist kein Anthropic-Schlüssel hinterlegt. Ohne ihn " +
          "kann ich nicht denken. Starte einmal die Einrichtung.", true);
      }
    }).catch(function () {});
  }
  function kachelnHolen() {
    holen("/api/bedarf").then(function (a) {
      if (!a.berechenbar) {
        el("bedarfZahl").textContent = "–";
        el("bedarfText").textContent = "Fixkosten noch nicht erfasst.";
        return;
      }
      if (typeof a.luecke === "number" && a.luecke > 0) {
        el("bedarfZahl").textContent = euro(a.luecke) + " fehlen";
        el("bedarfZahl").className = "zahl schlecht";
        el("bedarfText").textContent = "Nötig " + euro(a.noetiger_umsatz) +
          " je Monat, gesichert " + euro(a.gesichert) + ".";
      } else {
        el("bedarfZahl").textContent = euro(a.noetiger_umsatz);
        el("bedarfZahl").className = "zahl gut";
        el("bedarfText").textContent = "nötig je Monat – gedeckt.";
      }
    }).catch(function () {});

    holen("/api/kasse").then(function (a) {
      el("kasseZahl").textContent = euro(a.ergebnis);
      el("kasseZahl").className = "zahl " + (a.ergebnis >= 0 ? "gut" : "schlecht");
      el("kasseText").textContent = "Ein " + euro(a.einnahmen) + " · Aus " +
        euro(a.ausgaben) + " · Zahllast " + euro(a.zahllast);
    }).catch(function () {});

    holen("/api/nachfassen").then(function (a) {
      var ziel = el("nachfassen");
      if (!a.anzahl) {
        ziel.innerHTML = '<span class="leer">Heute ist niemand fällig.</span>';
        return;
      }
      var liste = document.createElement("ul");
      a.eintraege.slice(0, 5).forEach(function (e) {
        var zeile = document.createElement("li");
        zeile.textContent = e.firma + " · " + euro(e.wert_monat);
        var klein = document.createElement("small");
        klein.textContent = e.schritt +
          (e.seit_tagen > 0 ? " · " + e.seit_tagen + " Tage überfällig" : "");
        zeile.appendChild(klein);
        liste.appendChild(zeile);
      });
      ziel.innerHTML = "";
      ziel.appendChild(liste);
    }).catch(function () {});
  }

  var SCHNELL = ["Wie steht es?", "Was muss ich heute nachfassen?",
                 "Was fehlt mir zum Decken?", "Welche Belege fehlen?",
                 "Was steht an?"];
  SCHNELL.forEach(function (text) {
    var knopf = document.createElement("button");
    knopf.textContent = text;
    knopf.addEventListener("click", function () { senden(text); });
    el("schnell").appendChild(knopf);
  });

  /* ---------- Freigaben ---------- */
  function freigabenHolen() {
    holen("/api/freigaben").then(function (a) {
      var offen = (a.offen || [])[0];
      if (!offen) {
        if (aktuelleFreigabe) { freigabeSchliessen(); }
        return;
      }
      if (aktuelleFreigabe && aktuelleFreigabe.id === offen.id) {
        el("freigabeRest").textContent = offen.rest + " s";
        return;
      }
      aktuelleFreigabe = offen;
      el("freigabeAktion").textContent = offen.aktion;
      el("freigabeDetails").textContent = offen.details || "(ohne Angaben)";
      el("freigabeRest").textContent = offen.rest + " s";
      el("schleier").classList.add("zeigen");
      if (window.speechSynthesis) { window.speechSynthesis.cancel(); }
      sprich("Ich brauche eine Freigabe für " + offen.aktion);
    }).catch(function () {});
  }
  function freigabeSchliessen() {
    aktuelleFreigabe = null;
    el("schleier").classList.remove("zeigen");
    if (restZaehler) { clearInterval(restZaehler); restZaehler = null; }
  }
  function antworten(ja) {
    if (!aktuelleFreigabe) { return; }
    var kennung = aktuelleFreigabe.id;
    freigabeSchliessen();
    holen("/api/freigabe", { id: kennung, ja: ja }).then(function () {
      lageHolen();
    });
  }
  el("freigabeJa").addEventListener("click", function () { antworten(true); });
  el("freigabeNein").addEventListener("click", function () { antworten(false); });
  document.addEventListener("keydown", function (e) {
    if (!aktuelleFreigabe) { return; }
    if (e.key === "Escape") { antworten(false); }
  });

  /* ---------- Start ---------- */
  zustandHolen();
  lageHolen();
  kachelnHolen();
  setInterval(freigabenHolen, 1500);
  setInterval(lageHolen, 45000);
  setInterval(kachelnHolen, 60000);
  feld.focus();
})();
</script>
</body>
</html>
"""
