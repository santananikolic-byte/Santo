#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Die Kamera-Seite ``/sehen``: Webcam, 21 Punkte der Hand, Handruhe, Daumen hoch, Orb.

Alles läuft im Browser. **Das Bild verlässt die Seite nie** - es wird weder hochgeladen
noch aufgezeichnet noch zwischengespeichert; an Jarvis gehen nur Messzahlen. Die
Seite darf dafür gar nichts nach außen: Ihr Sicherheitskopf (``SEHEN_CSP``) erlaubt
Verbindungen nur zu Jarvis selbst, und die Erkennung (MediaPipe) wird von Jarvis
ausgeliefert, nicht von jsDelivr oder Google (siehe ``sicht.py``).

**Was die Seite kann**

* Startfeld mit der ersten Meldung, die zutrifft: Kamera aus (``SICHT_AN``), Dateien
  nicht geladen, keine sichere Adresse - sonst der Knopf "Kamera einschalten".
* Webcam mit den 21 Punkten der Hand, Bildrate und Rechenzeit; ein deutliches
  "Kamera an" mit "Aus"-Knopf. Bei ``pagehide`` oder unsichtbarer Seite geht die
  Kamera aus.
* **Handruhe** (``handruhe``): acht Sekunden Fingerspitzen messen, mit der Handlänge
  in Millimeter schätzen, nach dem Rhythmus suchen. Unter 25 Bildern pro Sekunde
  wird abgelehnt ("Mehr Licht, bitte"), weil sich ein schnelles Zittern sonst auf
  eine falsche Frequenz faltet. Ehrlich: Selbstbeobachtung gegen die eigenen
  Werte, kein Medizinprodukt, eine Webcam sieht nur Bewegungen ab etwa einem
  halben Millimeter.
* **Daumen hoch** beantwortet genau eine offene Freigabe oder den jüngsten
  Vorschlag - bewusst schwer auszulösen (``istDaumenHoch``, ``daumenSchritt``):
  Geometrie und Modell müssen sich einig sein, 1,5 Sekunden halten, erst scharf
  nach einer halben Sekunde ohne Daumen, danach drei Sekunden Sperre. Daumen
  runter (0,8 Sekunden) heißt Nein.
* Der Orb (``/gehirn?eingebettet=1&form=kugel``) bekommt Pegel und Sprechen per
  ``postMessage`` von dieser Seite weitergereicht.

**Zwei Betriebsarten.** In der Web-App (Anschluss 8765) geht alles. Auf der
Anzeige des Dienstes (8766, nur lesen) laufen Kamera, Punkte und Handruhe live,
aber Speichern und Gesten gehen nicht - die Seite sagt das und schickt dort keine
POST-Anfragen.

Rechenteile (``// <rechnen>``) sind reine Funktionen ohne Seitenzugriff; die
Prüfungen führen sie mit node aus.
"""

from modules.ansicht import BASIS_STIL, FEHLERFANG
from modules.sicht import SICHT_VERSION

# Was die Seite darf: nur zu sich selbst sprechen. 'unsafe-inline' für das eine Skript der
# Seite, 'wasm-unsafe-eval' damit der Browser die Erkennung (WASM) übersetzen darf.
SEHEN_CSP = ("default-src 'self'; script-src 'self' 'unsafe-inline' 'wasm-unsafe-eval'; "
             "connect-src 'self'; img-src 'self' data: blob:; media-src 'self' blob: mediastream:; "
             "worker-src 'self' blob:; style-src 'self' 'unsafe-inline'; frame-src 'self'; "
             "object-src 'none'; base-uri 'none'")
# Kamera nur für diese Seite selbst, Mikrofon nie.
SEHEN_ERLAUBNIS = "camera=(self), microphone=()"
# Solange die Live-Kamera ausgeschaltet ist (SICHT_AN), gibt der Browser die Kamera gar nicht her.
SEHEN_ERLAUBNIS_AUS = "camera=(), microphone=()"

_SEITE_KOPF = r"""<!DOCTYPE html>
<html lang="de"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<link rel="icon" href="/symbol.svg" type="image/svg+xml">
<title>Jarvis – Sicht</title>
<style>
""" + BASIS_STIL + r"""
html,body{overflow:auto;height:auto;min-height:100%}
body{padding:0 16px 32px}
a{color:var(--glut)}
.kopf{display:flex;align-items:center;gap:18px;padding:14px 0;min-height:64px;flex-wrap:wrap;max-width:1280px;margin:0 auto}
.kopf h1{font:600 13px var(--mono);letter-spacing:.42em;color:var(--glut);text-transform:uppercase}
.kopf .zurueck{font:500 11px var(--mono);letter-spacing:.2em;color:var(--leise);text-transform:uppercase;text-decoration:none}
.kopf .zurueck:hover{color:var(--hell)}
.an{display:flex;align-items:center;gap:10px;margin-left:auto;padding:5px 6px 5px 12px;border:1px solid var(--rot);
 border-radius:6px;background:rgba(255,90,77,.16);color:#fff;font:600 12px var(--mono);letter-spacing:.16em;text-transform:uppercase}
.an[hidden]{display:none}
.an i{width:10px;height:10px;border-radius:50%;background:var(--rot);box-shadow:0 0 12px var(--rot);animation:atmen 1.4s ease-in-out infinite}
@keyframes atmen{50%{transform:scale(1.5);opacity:.5}}
.knopf{font:600 13px var(--sans);min-height:40px;padding:8px 14px;border-radius:6px;border:1px solid var(--orange);
 background:rgba(255,106,31,.14);color:var(--hell);cursor:pointer}
.knopf:hover:not(:disabled){background:rgba(255,106,31,.28)}
.knopf:disabled{opacity:.45;cursor:not-allowed}
.knopf.klein{min-height:30px;padding:3px 10px;font-size:12px}
.knopf:focus-visible,input:focus-visible,a:focus-visible{outline:2px solid var(--hell);outline-offset:2px}
.raster{display:grid;grid-template-columns:minmax(0,1.6fr) minmax(280px,1fr);gap:18px;max-width:1280px;margin:0 auto;align-items:start}
@media (max-width:900px){.raster{grid-template-columns:minmax(0,1fr)}}
.bild{position:relative;aspect-ratio:16/9;background:#000;border:1px solid var(--linie);border-radius:8px;overflow:hidden}
.bild video,.bild canvas{position:absolute;inset:0;width:100%;height:100%;object-fit:contain;transform:scaleX(-1)}
.hud{position:absolute;left:10px;right:10px;top:8px;display:flex;justify-content:space-between;gap:10px;pointer-events:none;
 font:500 11px var(--mono);letter-spacing:.14em;color:var(--hell);text-transform:uppercase;text-shadow:0 1px 3px #000}
.hud b{color:var(--gruen);font-weight:600}
.hud span:last-child{text-align:right;white-space:nowrap}
@media (max-width:600px){.hud{flex-direction:column;gap:2px;font-size:10px;letter-spacing:.08em}.hud span:last-child{text-align:left}}
.start{position:absolute;inset:0;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:12px;padding:18px;
 text-align:center;background:rgba(7,4,3,.82)}
.start[hidden]{display:none}
.start p{max-width:46ch;line-height:1.45}
.klein{font-size:12px;color:var(--leise)}
.ring{position:absolute;left:50%;bottom:14px;width:64px;height:64px;transform:translateX(-50%) rotate(-90deg);display:none}
.ring.sichtbar{display:block}
.ring circle{fill:rgba(7,4,3,.6);stroke-width:4}
.ring .spur{stroke:rgba(255,255,255,.18)}
.ring .fuell{stroke:var(--gruen);fill:none;stroke-linecap:round}
.ring.nein .fuell{stroke:var(--rot)}
.hinweisbox{margin:10px 0 0;padding:9px 12px;border:1px solid var(--linie);border-radius:6px;background:rgba(255,154,82,.08);
 color:var(--hell);line-height:1.45;font-size:13px}
.hinweisbox[hidden]{display:none}
.seite{display:flex;flex-direction:column;gap:14px;min-width:0}
.karte{border:1px solid var(--linie);border-radius:8px;padding:14px;background:rgba(13,7,5,.7);min-width:0}
.karte h2{font:600 11px var(--mono);letter-spacing:.3em;color:var(--glut);text-transform:uppercase;margin-bottom:10px}
.orb{padding:0;overflow:hidden}
.orb iframe{display:block;width:100%;height:230px;border:0;background:transparent}
.orb .etikett{padding:6px 12px 8px;font:500 10px var(--mono);letter-spacing:.2em;color:var(--leise);text-transform:uppercase}
.karte dl{display:grid;grid-template-columns:auto 1fr;gap:4px 12px;font-size:13px;line-height:1.4}
.karte dt{font:500 10px var(--mono);letter-spacing:.2em;color:var(--leise);text-transform:uppercase;padding-top:2px}
.karte dd{overflow-wrap:anywhere}
.zeile{display:flex;flex-wrap:wrap;gap:8px;align-items:center;margin:6px 0}
.zeile label{font-size:12px;color:var(--leise);display:flex;align-items:center;gap:8px}
input[type=number]{width:72px;padding:6px 8px;border-radius:6px;border:1px solid var(--linie);background:#120b08;color:var(--text);font:500 13px var(--mono)}
.balken{height:6px;border-radius:3px;background:rgba(255,255,255,.12);overflow:hidden;margin:8px 0}
.balken[hidden]{display:none}
.balken i{display:block;height:100%;width:0;background:var(--orange)}
.ergebnis{margin-top:8px;line-height:1.45;font-size:13px}
.ergebnis.gut{color:var(--hell)}
.ergebnis.schlecht{color:var(--rot)}
.statuszeile{font-size:12px;color:var(--leise);min-height:1.4em}
.verlauf svg{display:block;width:100%;height:auto;margin-top:8px}
.verlauf text{font:10px var(--mono);fill:var(--leise)}
.fuss{max-width:1280px;margin:18px auto 0;font-size:12px;color:var(--leise);line-height:1.5}
@media (prefers-reduced-motion: reduce){.an i{animation:none}}
</style></head><body>
<header class="kopf">
<a class="zurueck" id="zurueck" href="/">Jarvis</a>
<h1>Sicht</h1>
<div class="an" id="kameraan" role="status" hidden><i></i><span>Kamera an</span>
<button class="knopf klein" id="aus" type="button">Aus</button></div>
</header>
<main class="raster">
<section aria-label="Kamerabild">
<div class="bild" id="bild">
<video id="video" playsinline muted></video>
<canvas id="leinwand"></canvas>
<div class="hud"><span id="hudhand"></span><span id="hudfps"></span></div>
<svg class="ring" id="ring" viewBox="0 0 44 44" aria-hidden="true"><circle class="spur" cx="22" cy="22" r="18"/><circle class="fuell" id="ringfuell" cx="22" cy="22" r="18"/></svg>
<div class="start" id="start"><p id="startmeldung">Einen Moment …</p>
<button class="knopf" id="startknopf" type="button" hidden>Kamera einschalten</button>
<p class="klein" id="startdatenschutz" hidden>Das Bild bleibt in diesem Browser. Gespeichert werden nur Messzahlen, nie ein Bild.</p></div>
</div>
<p class="hinweisbox" id="modushinweis" hidden></p>
</section>
<aside class="seite">
<section class="karte orb" aria-label="Orb"><iframe id="orb" title="Orb, der mitspricht" tabindex="-1"></iframe>
<div class="etikett" id="orbetikett">Orb · ruhig</div></section>
<section class="karte" id="gestenkarte" aria-live="polite"><h2 id="gestenkopf">Geste</h2>
<dl id="gestenzeilen"></dl>
<p class="statuszeile" id="gestenstatus"></p>
<p class="ergebnis" id="gestentext"></p></section>
<section class="karte" aria-label="Handruhe"><h2>Handruhe</h2>
<div class="zeile">
<button class="knopf" id="mruhe" type="button" disabled>Ruhemessung (Hand flach auf den Tisch, 8 s)</button>
<button class="knopf" id="mhalten" type="button" disabled>Haltemessung (Arm ausgestreckt, 8 s)</button></div>
<div class="zeile"><label for="handlaenge">Handlänge Handgelenk bis Mittelfingerwurzel, mm
<input id="handlaenge" type="number" min="60" max="130" step="1" value="95"></label></div>
<p class="klein">Ruhemessung: Hand flach auf den Tisch - das ist das Grundrauschen von Kamera und Licht. Haltemessung: Arm ausstrecken und die Hand ruhig halten. Verglichen wird nur mit deinen eigenen letzten 14 Tagen.</p>
<div class="balken" id="balken" hidden><i id="balkenfuell"></i></div>
<p class="statuszeile" id="erholungszeile"></p>
<p class="statuszeile" id="messstatus"></p>
<p class="ergebnis" id="messergebnis" aria-live="polite"></p>
<div class="verlauf" id="verlauf"></div>
</section>
</aside>
</main>
<p class="fuss">Selbstbeobachtung, kein Medizinprodukt. Eine Webcam sieht nur Bewegungen ab etwa einem halben Millimeter.
Das Bild bleibt in diesem Browser: Es wird weder hochgeladen noch aufgezeichnet. Gespeichert werden nur Messzahlen.</p>
<script>
"""

_SEITE_RECHNEN = r"""
// <rechnen>
// Reine Funktionen: kein Seitenzugriff, damit sie sich mit node prüfen lassen.
var SPITZEN=[4,8,12,16,20];
var MIN_FPS=25;

// Eine Probe für die Handruhe aus einer erkannten Hand. hand: 21 Punkte mit x, y in 0..1;
// b, h: Breite und Höhe des Bildes in Pixeln. x und y sind der Mittelpunkt der fünf
// Fingerspitzen in Pixeln, geteilt durch die Handflächenlänge |0 -> 9| - so zählt der Abstand
// zur Kamera nicht. Fehlt die Hand oder ist die Handfläche kürzer als 8 % der Bildhöhe: ok=false.
function handProbe(hand,t,b,h){
 if(!hand||hand.length<21)return {t:t,x:0,y:0,ok:false};
 var p=Math.hypot((hand[9].x-hand[0].x)*b,(hand[9].y-hand[0].y)*h);
 if(!(p>=0.08*h))return {t:t,x:0,y:0,ok:false};
 var x=0,y=0;
 for(var i=0;i<SPITZEN.length;i++){x+=hand[SPITZEN[i]].x*b;y+=hand[SPITZEN[i]].y*h}
 return {t:t,x:x/SPITZEN.length/p,y:y/SPITZEN.length/p,ok:true};
}

// Die Hand in Pixel umrechnen, damit Längen und Winkel in x und y gleich zählen.
function handPixel(hand,b,h){
 var aus=[];
 for(var i=0;i<hand.length;i++)aus.push({x:hand[i].x*b,y:hand[i].y*h});
 return aus;
}

// Wie ruhig ist die Hand? proben: [{t (ms), x, y, ok}] über etwa acht Sekunden.
function handruhe(proben,handlaengeMm){
 var n=proben?proben.length:0;
 if(n<2)return {ok:false,grund:"Zu wenige Bilder für eine Messung."};
 var dauerS=(proben[n-1].t-proben[0].t)/1000;
 var fps=(n-1)/Math.max(dauerS,1e-6);
 if(!(fps>=MIN_FPS))return {ok:false,fps:fps,bilder:n,dauer_s:dauerS,
  grund:"Mehr Licht, bitte – die Kamera liefert nur "+Math.round(fps)+" Bilder pro Sekunde."};
 var gut=[];
 for(var i=0;i<n;i++)if(proben[i].ok)gut.push(proben[i]);
 if(gut.length<0.85*n)return {ok:false,fps:fps,bilder:n,dauer_s:dauerS,
  grund:"Die Hand war nur in "+Math.round(100*gut.length/n)+" % der Bilder zu sehen. Bitte die Hand ruhig und ganz ins Bild halten."};
 // 1) Auf ein gleichmäßiges 30-Hz-Raster bringen (linear, nur aus gültigen Proben)
 var FS=30,t0=gut[0].t,t1=gut[gut.length-1].t;
 var m=Math.floor((t1-t0)/1000*FS)+1;
 if(m<32)return {ok:false,fps:fps,bilder:n,dauer_s:dauerS,grund:"Zu wenige gültige Bilder für eine Messung."};
 var xs=new Float64Array(m),ys=new Float64Array(m),j=0;
 for(var i=0;i<m;i++){
  var tz=t0+i*1000/FS;
  while(j<gut.length-2&&gut[j+1].t<tz)j++;
  var a=gut[j].t,e=gut[j+1].t;
  var w=e>a?Math.min(1,Math.max(0,(tz-a)/(e-a))):0;
  xs[i]=gut[j].x*(1-w)+gut[j+1].x*w;
  ys[i]=gut[j].y*(1-w)+gut[j+1].y*w;
 }
 // 2) Hochpass: den gleitenden Mittelwert über 9 Bilder (0,3 s) abziehen - das nimmt das langsame Treiben weg
 var K=4,hx=[],hy=[];
 for(var i=K;i<m-K;i++){
  var sx=0,sy=0;
  for(var q=-K;q<=K;q++){sx+=xs[i+q];sy+=ys[i+q]}
  hx.push(xs[i]-sx/(2*K+1));hy.push(ys[i]-sy/(2*K+1));
 }
 // 3) Stärke: Effektivwert in Handlängen, mit der Handlänge in Millimeter
 var L=hx.length,quad=0;
 for(var i=0;i<L;i++)quad+=hx[i]*hx[i]+hy[i]*hy[i];
 var mm=Math.sqrt(quad/L)*handlaengeMm;
 // 4) Rhythmus: Hann-Fenster, kleine DFT von 3 bis 14 Hz in 0,25-Hz-Schritten
 var freq=[],leist=[];
 for(var f=3;f<=14.0001;f+=0.25){
  var rx=0,ix=0,ry=0,iy=0;
  for(var i=0;i<L;i++){
   var fen=0.5-0.5*Math.cos(2*Math.PI*i/(L-1)),ph=2*Math.PI*f*i/FS,c=Math.cos(ph),s=Math.sin(ph);
   rx+=hx[i]*fen*c;ix+=hx[i]*fen*s;ry+=hy[i]*fen*c;iy+=hy[i]*fen*s;
  }
  freq.push(f);leist.push(rx*rx+ix*ix+ry*ry+iy*iy);
 }
 var sortiert=leist.slice().sort(function(u,v){return u-v});
 var median=Math.max(sortiert[sortiert.length>>1],1e-18);
 var top=0;
 for(var i=1;i<leist.length;i++)if(leist[i]>leist[top])top=i;
 var verhaeltnis=Math.min(1e6,leist[top]/median);
 return {ok:true,mm:mm,rhythmus_hz:verhaeltnis>20?freq[top]:null,spitze_verhaeltnis:verhaeltnis,
  fps:fps,bilder:n,dauer_s:dauerS};
}

function abst(p,q){return Math.hypot(p.x-q.x,p.y-q.y)}
// Winkel der Strecke p -> q zur Senkrechten in Grad (0 = zeigt nach oben; y wächst nach unten)
function winkelSenkrecht(p,q){return Math.abs(Math.atan2(q.x-p.x,-(q.y-p.y))*180/Math.PI)}

// Zeigt die Hand "Daumen hoch"? hand: 21 Punkte in Pixeln, geste: {categoryName, score} des Modells.
// streng=true gilt zum Einstieg, streng=false zum Dabeibleiben (Hysterese).
function istDaumenHoch(hand,geste,streng){
 if(!hand||hand.length<21)return false;
 var P=abst(hand[0],hand[9]);
 if(!(P>0))return false;
 var lang=abst(hand[2],hand[4])>0.55*P;
 var oben=hand[4].y<hand[3].y&&hand[3].y<hand[2].y&&winkelSenkrecht(hand[2],hand[4])<(streng?35:50);
 var abstand=(streng?0.15:0.05)*P,hoechster=true;
 for(var i=0;i<21;i++)if(i!==4&&!(hand[4].y<hand[i].y-abstand))hoechster=false;
 var spitzen=[[6,8],[10,12],[14,16],[18,20]],eingerollt=true;
 for(var i=0;i<4;i++)if(!(abst(hand[spitzen[i][1]],hand[0])<abst(hand[spitzen[i][0]],hand[0])*(streng?1:1.1)))eingerollt=false;
 var modell=!!geste&&geste.categoryName==="Thumb_Up"&&geste.score>(streng?0.7:0.5);
 return lang&&oben&&hoechster&&eingerollt&&modell;
}
function istDaumenRunter(geste){return !!geste&&geste.categoryName==="Thumb_Down"&&geste.score>0.7}

var DAUMEN_HALTEN_MS=1500,DAUMEN_NEIN_MS=800,DAUMEN_LUECKE_MS=120,DAUMEN_FREI_MS=500,DAUMEN_SPERRE_MS=3000;
// Der Zustand der Geste. -1 heißt: läuft nicht.
function daumenNeu(){return {scharf:false,ohneSeit:-1,seit:-1,zuletzt:-1,runterSeit:-1,runterZuletzt:-1,gesperrtBis:-1}}

// Ein Bild weiter. t: Zeit in ms, hand: 21 Punkte in Pixeln oder null, geste: Modellergebnis oder null.
// Gibt {aktion: "" | "ja" | "nein", fortschritt: 0..1, scharf, art: "" | "ja" | "nein"} zurück und
// verändert z. Scharf wird die Geste erst, wenn eine halbe Sekunde lang kein Daumen zu sehen war -
// ein Daumen, der schon oben war, als die Frage kam, zählt nicht.
function daumenSchritt(z,t,hand,geste){
 var erg={aktion:"",fortschritt:0,scharf:!!z.scharf,art:""};
 if(z.gesperrtBis>=0&&t<z.gesperrtBis){
  z.scharf=false;z.ohneSeit=-1;z.seit=-1;z.runterSeit=-1;erg.scharf=false;return erg;
 }
 var runter=istDaumenRunter(geste);
 if(!z.scharf){
  if(istDaumenHoch(hand,geste,false)||runter)z.ohneSeit=-1;
  else{
   if(z.ohneSeit<0)z.ohneSeit=t;
   if(t-z.ohneSeit>=DAUMEN_FREI_MS)z.scharf=true;
  }
  erg.scharf=z.scharf;
  return erg;
 }
 var hoch=istDaumenHoch(hand,geste,z.seit<0);   // streng nur zum Einstieg
 if(hoch){z.zuletzt=t;if(z.seit<0)z.seit=t;z.runterSeit=-1}
 else if(z.seit>=0&&t-z.zuletzt>DAUMEN_LUECKE_MS)z.seit=-1;
 if(runter&&!hoch){z.runterZuletzt=t;if(z.runterSeit<0)z.runterSeit=t;z.seit=-1}
 else if(z.runterSeit>=0&&t-z.runterZuletzt>DAUMEN_LUECKE_MS)z.runterSeit=-1;
 var fh=z.seit>=0?Math.min(1,(t-z.seit)/DAUMEN_HALTEN_MS):0;
 var fn=z.runterSeit>=0?Math.min(1,(t-z.runterSeit)/DAUMEN_NEIN_MS):0;
 if(fh>=1||fn>=1){
  erg.aktion=fh>=1?"ja":"nein";
  z.scharf=false;z.ohneSeit=-1;z.seit=-1;z.runterSeit=-1;z.gesperrtBis=t+DAUMEN_SPERRE_MS;
  erg.scharf=false;erg.fortschritt=1;erg.art=erg.aktion;
  return erg;
 }
 erg.fortschritt=Math.max(fh,fn);erg.art=fh>=fn?(fh>0?"ja":""):"nein";
 return erg;
}
// </rechnen>
"""

_SEITE_SKRIPT = r"""
var SCHLUESSEL="{{SCHLUESSEL}}";
function url(p){return SCHLUESSEL?p+(p.indexOf("?")<0?"?":"&")+"schluessel="+encodeURIComponent(SCHLUESSEL):p}
function $(s){return document.querySelector(s)}
var REDUZIERT=matchMedia("(prefers-reduced-motion: reduce)").matches;
var SVGNS="http://www.w3.org/2000/svg";
function el(tag,attr,text){var e=document.createElement(tag);if(attr)for(var k in attr)e.setAttribute(k,attr[k]);if(text!=null)e.textContent=text;return e}
function svg(tag,attr){var e=document.createElementNS(SVGNS,tag);if(attr)for(var k in attr)e.setAttribute(k,attr[k]);return e}
function leeren(e){while(e.firstChild)e.removeChild(e.firstChild)}
function komma(x,n){return Number(x).toFixed(n==null?1:n).replace(".",",")}
async function holenJson(pfad,koerper){
 var opt={cache:"no-store"};
 if(koerper!==undefined){opt.method="POST";opt.headers={"Content-Type":"application/json"};opt.body=JSON.stringify(koerper)}
 var r=await fetch(url(pfad),opt),d={};
 try{d=await r.json()}catch(f){}
 return {status:r.status,daten:d};
}

var VERBINDUNGEN=[[0,1],[1,2],[2,3],[3,4],[0,5],[5,6],[6,7],[7,8],[5,9],[9,10],[10,11],[11,12],[9,13],[13,14],[14,15],[15,16],[13,17],[0,17],[17,18],[18,19],[19,20]];
var MESSDAUER=8000;
var VIDEO=$("#video"),LEINWAND=$("#leinwand"),G=LEINWAND.getContext("2d");
var STAND=null,SCHREIBEN=true,AN=false,STARTET=false,SITZUNG=0,ERKENNER=null;
var LETZTE_ZEIT=-1,LETZTES_VIDEO=-1,FEHLERZAHL=0,ZEITEN=[],RECHENMS=0;
var MESS=null,RUHE_MM=null;
var FREIGABEN=[],VORSCHLAG=null,AKTIV=null,GESTE=daumenNeu(),GESTENZEILE="";

// ---- Startfeld ------------------------------------------------------------------------------
function startZeigen(text,knopf){
 $("#startmeldung").textContent=text;$("#startknopf").hidden=!knopf;$("#startdatenschutz").hidden=!knopf;$("#start").hidden=false;
}
function modusHinweis(){
 var b=$("#modushinweis");
 if(SCHREIBEN){b.hidden=true;return}
 b.textContent="Das ist die Anzeige des Dienstes: Kamera, Punkte und Handruhe laufen live, aber Speichern und Gesten gehen nur in der Web-App.";
 b.hidden=false;
}
async function standHolen(){
 try{
  var r=await holenJson("/api/sicht/stand");
  if(r.status===200&&r.daten&&r.daten.ok){STAND=r.daten;SCHREIBEN=r.daten.schreiben!==false;VORSCHLAG=r.daten.vorschlag||null;erholungZeigen();return true}
 }catch(f){}
 return false;
}
function erholungZeigen(){
 var e=STAND&&STAND.erholung,z=$("#erholungszeile");
 z.textContent=e&&typeof e.wert==="number"?"Erholung heute: "+Math.round(e.wert)+" von 100"+(e.quelle?" ("+e.quelle+")":"")+" - Schätzung, kein Medizinprodukt.":"";
}
async function startPruefen(vorspann){
 var ok=await standHolen();
 var pre=vorspann?vorspann+" ":"";
 if(!ok){startZeigen(pre+"Ich erreiche Jarvis gerade nicht. Bitte die Seite neu laden.",false);return}
 modusHinweis();
 if(!STAND.an){startZeigen(pre+"Die Live-Kamera ist ausgeschaltet. Einschalten: python3 jarvis.py sicht an – danach Jarvis einmal neu starten.",false);return}
 if(!STAND.dateien_da){startZeigen(pre+"Die Handerkennung ist noch nicht geladen. Einmal im Terminal: python3 jarvis.py sicht laden (etwa 31 MB, von jsDelivr und Google).",false);return}
 if(!window.isSecureContext||!navigator.mediaDevices){startZeigen(pre+"Die Kamera geht nur direkt am Mac (localhost), nicht über das WLAN.",false);return}
 var h=Number(STAND.handlaenge_mm);
 if(!handlaengeGesetzt&&h>=60&&h<=130)$("#handlaenge").value=String(Math.round(h));
 startZeigen(vorspann?vorspann:"Die Kamera ist aus.",true);
}
var handlaengeGesetzt=false;
try{var gespeichert=Number(localStorage.getItem("sicht_handlaenge"));if(gespeichert>=60&&gespeichert<=130){$("#handlaenge").value=String(gespeichert);handlaengeGesetzt=true}}catch(f){}
function handlaenge(){var v=Number($("#handlaenge").value);return v>=60&&v<=130?v:95}
$("#handlaenge").addEventListener("change",function(){handlaengeGesetzt=true;try{localStorage.setItem("sicht_handlaenge",String(handlaenge()))}catch(f){}});

// ---- Kamera ----------------------------------------------------------------------------------
function kameraFehler(f){
 var n=f&&f.name;
 if(n==="NotAllowedError")return "Der Browser oder macOS lässt mich nicht an die Kamera (Systemeinstellungen > Datenschutz & Sicherheit > Kamera).";
 if(n==="NotFoundError")return "Ich finde keine Kamera.";
 if(n==="NotReadableError")return "Die Kamera wird gerade von einem anderen Programm benutzt.";
 if(n==="OverconstrainedError")return "Die Kamera kann dieses Format nicht.";
 if(n==="SecurityError")return "Diese Adresse ist nicht sicher genug für die Kamera.";
 return "Die Kamera ging nicht an"+(f&&f.message?" ("+f.message+")":"")+".";
}
document.addEventListener("securitypolicyviolation",function(e){
 meldungOben("Der Sicherheitskopf blockiert die Handerkennung ("+e.violatedDirective+").");
});
function meldungOben(text){$("#hudhand").textContent=text}

async function modellLaden(){
 var m=await import("/sicht/dateien/{{SICHT_VERSION}}/vision_bundle.mjs");
 var fileset=await m.FilesetResolver.forVisionTasks(location.origin+"/sicht/dateien/{{SICHT_VERSION}}");
 var opt=function(d){return {baseOptions:{modelAssetPath:"/sicht/dateien/{{SICHT_VERSION}}/gesture_recognizer.task",delegate:d},
  runningMode:"VIDEO",numHands:1,minHandDetectionConfidence:0.6,minHandPresenceConfidence:0.6,minTrackingConfidence:0.6}};
 try{return await m.GestureRecognizer.createFromOptions(fileset,opt("GPU"))}
 catch(f){return await m.GestureRecognizer.createFromOptions(fileset,opt("CPU"))}
}

async function kameraAn(){
 if(AN||STARTET)return;
 STARTET=true;var meine=++SITZUNG;
 startZeigen("Die Kamera wird gestartet …",false);
 var strom=null;
 try{strom=await navigator.mediaDevices.getUserMedia({video:{width:{ideal:1280},height:{ideal:720},frameRate:{ideal:60}},audio:false})}
 catch(f){STARTET=false;startZeigen(kameraFehler(f),true);return}
 if(meine!==SITZUNG){strom.getTracks().forEach(function(t){t.stop()});return}
 VIDEO.srcObject=strom;AN=true;
 var spur=strom.getVideoTracks()[0];
 if(spur)spur.addEventListener("ended",function(){if(meine===SITZUNG&&AN)kameraAus("Die Kamera wurde getrennt oder der Zugriff entzogen.")});
 $("#kameraan").hidden=false;$("#start").hidden=true;
 meldungOben("Handerkennung wird geladen …");
 try{await VIDEO.play()}catch(f){}
 var erk=null;
 try{erk=await modellLaden()}
 catch(f){
  if(meine===SITZUNG){kameraAus("Die Handerkennung ließ sich nicht starten ("+(f&&f.message?f.message:f)+").")}
  return;
 }
 if(meine!==SITZUNG){try{erk.close()}catch(f){}return}
 ERKENNER=erk;STARTET=false;FEHLERZAHL=0;LETZTE_ZEIT=-1;LETZTES_VIDEO=-1;ZEITEN=[];
 knoepfeSetzen();
 naechstesBild();
}

function kameraAus(grund){
 SITZUNG++;STARTET=false;
 var s=VIDEO.srcObject;
 if(s&&s.getTracks)s.getTracks().forEach(function(t){t.stop()});
 VIDEO.srcObject=null;
 if(ERKENNER){try{ERKENNER.close()}catch(f){}ERKENNER=null}
 AN=false;MESS=null;GESTE=daumenNeu();
 G.clearRect(0,0,LEINWAND.width,LEINWAND.height);
 meldungOben("");$("#hudfps").textContent="";$("#kameraan").hidden=true;$("#balken").hidden=true;
 ringSetzen(0,"");knoepfeSetzen();
 if(grund)startPruefen(grund);else startPruefen("");
}

function naechstesBild(){
 if(!AN||!VIDEO.srcObject)return;
 if("requestVideoFrameCallback" in VIDEO)VIDEO.requestVideoFrameCallback(bildSchritt);
 else requestAnimationFrame(function(t){bildSchritt(t,null)});
}

function bildSchritt(jetzt,meta){
 if(!AN||!ERKENNER)return;
 // Ohne requestVideoFrameCallback kann dasselbe Bild zweimal kommen.
 if(!meta){if(VIDEO.currentTime===LETZTES_VIDEO){naechstesBild();return}LETZTES_VIDEO=VIDEO.currentTime}
 var b=VIDEO.videoWidth,h=VIDEO.videoHeight;
 if(!b||!h){naechstesBild();return}
 // MediaPipe verlangt streng steigende Zeitstempel - eine einzige Zeitbasis.
 var tErk=Math.max(performance.now(),LETZTE_ZEIT+1);LETZTE_ZEIT=tErk;
 var t=(meta&&typeof meta.captureTime==="number"&&meta.captureTime>0)?meta.captureTime:jetzt;
 var r=null;
 try{var a0=performance.now();r=ERKENNER.recognizeForVideo(VIDEO,tErk);RECHENMS=RECHENMS*0.9+(performance.now()-a0)*0.1}
 catch(f){FEHLERZAHL++;if(FEHLERZAHL>30){kameraAus("Die Handerkennung ist ausgestiegen ("+(f&&f.message?f.message:f)+").");return}}
 var hand=r&&r.landmarks&&r.landmarks[0]?r.landmarks[0]:null;
 var geste=r&&r.gestures&&r.gestures[0]&&r.gestures[0][0]?r.gestures[0][0]:null;
 zeichnen(hand,b,h);
 hudSetzen(t,!!hand);
 if(MESS)messungSchritt(handProbe(hand,t,b,h),t);
 if(AKTIV&&document.visibilityState==="visible")gesteSchritt(t,hand?handPixel(hand,b,h):null,geste);
 naechstesBild();
}

function zeichnen(hand,b,h){
 if(LEINWAND.width!==b||LEINWAND.height!==h){LEINWAND.width=b;LEINWAND.height=h;$("#bild").style.aspectRatio=b+" / "+h}
 G.clearRect(0,0,b,h);
 if(!hand)return;
 var d=Math.max(2,b/320);
 G.lineWidth=d;G.strokeStyle="rgba(255,106,31,.92)";G.lineCap="round";
 for(var i=0;i<VERBINDUNGEN.length;i++){
  var v=VERBINDUNGEN[i];G.beginPath();G.moveTo(hand[v[0]].x*b,hand[v[0]].y*h);G.lineTo(hand[v[1]].x*b,hand[v[1]].y*h);G.stroke();
 }
 for(var i=0;i<hand.length;i++){
  var spitze=SPITZEN.indexOf(i)>=0;
  G.shadowColor=spitze?"rgba(255,154,82,.95)":"transparent";G.shadowBlur=spitze?d*5:0;
  G.fillStyle=spitze?"#ffd9b8":"#ffffff";
  G.beginPath();G.arc(hand[i].x*b,hand[i].y*h,spitze?d*2.2:d*1.4,0,6.2832);G.fill();
 }
 G.shadowBlur=0;
}
function hudSetzen(t,hand){
 ZEITEN.push(t);if(ZEITEN.length>30)ZEITEN.shift();
 var fps=ZEITEN.length>1?(ZEITEN.length-1)*1000/(ZEITEN[ZEITEN.length-1]-ZEITEN[0]):0;
 $("#hudhand").textContent=hand?"HAND ERKANNT · 21 PUNKTE":"KEINE HAND";
 $("#hudfps").textContent=Math.round(fps)+" Bilder/s · "+RECHENMS.toFixed(0)+" ms";
}

addEventListener("pagehide",function(){if(AN||STARTET)kameraAus("")});
document.addEventListener("visibilitychange",function(){
 if(document.visibilityState==="hidden"&&(AN||STARTET))kameraAus("Die Kamera ist aus, weil die Seite nicht mehr zu sehen war.");
});
$("#startknopf").addEventListener("click",kameraAn);
$("#aus").addEventListener("click",function(){kameraAus("Die Kamera ist aus.")});

// ---- Handruhe messen ---------------------------------------------------------------------------
function knoepfeSetzen(){
 var frei=AN&&!!ERKENNER&&!MESS;
 $("#mruhe").disabled=!frei;$("#mhalten").disabled=!frei;
}
function ergebnisSetzen(text,gut){var e=$("#messergebnis");e.textContent=text;e.className="ergebnis "+(gut?"gut":"schlecht")}
function messungStarten(art){
 if(!AN||!ERKENNER||MESS)return;
 MESS={art:art,proben:[],t0:null};
 $("#messergebnis").textContent="";$("#balken").hidden=false;$("#balkenfuell").style.width="0%";
 $("#messstatus").textContent="Messung läuft – Hand ruhig ins Bild halten.";
 knoepfeSetzen();
}
function messungSchritt(probe,t){
 if(MESS.t0===null)MESS.t0=t;
 MESS.proben.push(probe);
 var vorbei=t-MESS.t0;
 $("#balkenfuell").style.width=Math.min(100,100*vorbei/MESSDAUER)+"%";
 $("#messstatus").textContent="Messung läuft – noch "+Math.max(0,Math.ceil((MESSDAUER-vorbei)/1000))+" s. Hand ruhig im Bild halten.";
 if(vorbei>=MESSDAUER)messungBeenden();
}
async function messungBeenden(){
 var m=MESS;MESS=null;knoepfeSetzen();
 $("#balken").hidden=true;$("#messstatus").textContent="";
 var laenge=handlaenge(),e=handruhe(m.proben,laenge);
 if(!e.ok){ergebnisSetzen(e.grund||"Die Messung hat nicht geklappt.",false);return}
 if(m.art==="ruhe")RUHE_MM=e.mm;
 var koerper={art:m.art,mm:e.mm,rauschen_mm:(m.art==="halten"&&RUHE_MM!==null)?RUHE_MM:null,rhythmus_hz:e.rhythmus_hz,
  spitze_verhaeltnis:e.spitze_verhaeltnis,fps:e.fps,dauer_s:e.dauer_s,bilder:e.bilder,handlaenge_mm:laenge};
 if(!SCHREIBEN){
  ergebnisSetzen(komma(e.mm)+" mm (Schätzung)"+(e.rhythmus_hz!==null?", Rhythmus um "+komma(e.rhythmus_hz)+" Hz":", kein deutlicher Rhythmus")+
   ". Nicht gespeichert: Speichern geht nur in der Web-App. Selbstbeobachtung, kein Medizinprodukt.",true);
  return;
 }
 try{
  var r=await holenJson("/api/sicht/messung",koerper);
  if(r.status===200&&r.daten&&r.daten.ok){ergebnisSetzen(r.daten.text,true);verlaufLaden()}
  else ergebnisSetzen((r.daten&&(r.daten.fehler||r.daten.text))||("Das Speichern hat nicht geklappt ("+r.status+")."),false);
 }catch(f){ergebnisSetzen("Ich erreiche Jarvis gerade nicht – die Messung ist nicht gespeichert.",false)}
}
$("#mruhe").addEventListener("click",function(){messungStarten("ruhe")});
$("#mhalten").addEventListener("click",function(){messungStarten("halten")});

// Die letzten 14 Tage: je Tag der letzte Wert der Haltemessung (Punkte) und der Ruhemessung (Ring).
async function verlaufLaden(){
 var box=$("#verlauf");
 try{
  var r=await holenJson("/api/sicht/verlauf?tage=14");
  var tage=(r.status===200&&r.daten&&r.daten.tageswerte)||[];
  leeren(box);
  if(!tage.length){box.appendChild(el("p","","Noch keine Messungen."));box.lastChild.className="statuszeile";return}
  var B=320,H=120,L=26,R=8,O=14,U=22,max=0.5;
  tage.forEach(function(t){max=Math.max(max,t.halten_mm||0,t.ruhe_mm||0)});
  max=max*1.15;
  var s=svg("svg",{viewBox:"0 0 "+B+" "+H,role:"img","aria-label":"Handruhe der letzten Tage in Millimeter"});
  var x=function(i){return tage.length===1?(L+(B-L-R)/2):L+(B-L-R)*i/(tage.length-1)};
  var y=function(v){return H-U-(H-U-O)*v/max};
  s.appendChild(svg("line",{x1:L,y1:y(0),x2:B-R,y2:y(0),stroke:"rgba(255,255,255,.2)"}));
  var t1=svg("text",{x:2,y:y(max)+4});t1.textContent=komma(max,1);s.appendChild(t1);
  var t0=svg("text",{x:2,y:y(0)+4});t0.textContent="0";s.appendChild(t0);
  var pfad="";
  tage.forEach(function(t,i){if(t.halten_mm!=null)pfad+=(pfad?"L":"M")+x(i).toFixed(1)+" "+y(t.halten_mm).toFixed(1)});
  if(pfad)s.appendChild(svg("path",{d:pfad,fill:"none",stroke:"#ff6a1f","stroke-width":2}));
  tage.forEach(function(t,i){
   if(t.ruhe_mm!=null)s.appendChild(svg("circle",{cx:x(i),cy:y(t.ruhe_mm),r:3.5,fill:"none",stroke:"#9a8678","stroke-width":1.5}));
   if(t.halten_mm!=null)s.appendChild(svg("circle",{cx:x(i),cy:y(t.halten_mm),r:3.5,fill:"#ffd9b8"}));
   if(i===0||i===tage.length-1||tage.length<=7){var tx=svg("text",{x:x(i),y:H-6,"text-anchor":"middle"});tx.textContent=t.tag.slice(8,10)+"."+t.tag.slice(5,7)+".";s.appendChild(tx)}
  });
  box.appendChild(s);
  var legende=el("p","","Punkt: Haltemessung, Ring: Ruhemessung (Grundrauschen) – je Tag der letzte Wert, in Millimeter (Schätzung).");
  legende.className="statuszeile";box.appendChild(legende);
 }catch(f){}
}

// ---- Daumen hoch / runter -----------------------------------------------------------------------
function ringSetzen(anteil,art){
 var r=$("#ring"),umfang=2*Math.PI*18;
 if(!(anteil>0)){r.classList.remove("sichtbar");return}
 r.classList.add("sichtbar");r.classList.toggle("nein",art==="nein");
 var f=$("#ringfuell");f.setAttribute("stroke-dasharray",umfang.toFixed(1));f.setAttribute("stroke-dashoffset",(umfang*(1-anteil)).toFixed(1));
}
function gesteSchritt(t,handPx,geste){
 var s=daumenSchritt(GESTE,t,handPx,geste);
 ringSetzen(s.fortschritt,s.art);
 var zeile=s.scharf?"Bereit: Daumen hoch 1,5 Sekunden halten heißt Ja, Daumen runter heißt Nein.":
  "Noch nicht scharf: Hand erst einen Moment aus dem Bild nehmen.";
 if(zeile!==GESTENZEILE){GESTENZEILE=zeile;$("#gestenstatus").textContent=zeile}
 if(s.aktion)gesteSenden(s.aktion);
}
async function gesteSenden(aktion){
 var a=AKTIV;if(!a)return;
 AKTIV=null;ringSetzen(0,"");
 var ja=aktion==="ja";
 try{
  var r=a.art==="freigabe"?await holenJson("/api/freigabe",{id:a.id,ja:ja,kanal:'geste'}):await holenJson("/api/vorschlag/geste",{id:a.id,ja:ja});
  $("#gestentext").textContent=(r.daten&&(r.daten.text||r.daten.fehler))||"Keine Antwort von Jarvis.";
 }catch(f){$("#gestentext").textContent="Ich erreiche Jarvis gerade nicht."}
 FREIGABEN=[];VORSCHLAG=null;karteSetzen();
}
function karteSetzen(){
 GESTENZEILE="";
 var kopf="Geste",zeilen=[],hinweis="",neu=null;
 if(!SCHREIBEN){hinweis="Gesten gehen nur in der Web-App."}
 else if(FREIGABEN.length>1){kopf="Freigabe";hinweis="Mehrere Fragen sind offen, deshalb ist die Geste aus. Bitte auf der Hauptseite per Klick oder Stimme antworten."}
 else if(FREIGABEN.length===1){
  var f=FREIGABEN[0];kopf="Freigabe";
  zeilen=[["Was",f.was],["Warum",f.warum],["Wie",f.wie]].filter(function(z){return z[1]});
  if(f.rest!=null)zeilen.push(["Noch",f.rest+" s"]);
  if(f.geste_erlaubt)neu={art:"freigabe",id:f.id};
  else hinweis=STAND&&!STAND.geste?"Die Gesten-Freigabe ist ausgeschaltet (GESTEN_FREIGABE=ja in der .env).":"Diese Frage gibt nur ein Klick oder die Stimme frei.";
 }
 else if(VORSCHLAG&&STAND&&STAND.geste){kopf="Vorschlag";zeilen=[["Jarvis schlägt vor",VORSCHLAG.text]];neu={art:"vorschlag",id:VORSCHLAG.id}}
 else hinweis=STAND&&!STAND.geste?"Die Gesten-Freigabe ist ausgeschaltet (GESTEN_FREIGABE=ja in der .env).":"Gerade ist nichts offen, worauf eine Geste antworten könnte.";
 var gleich=AKTIV&&neu&&AKTIV.art===neu.art&&AKTIV.id===neu.id;
 if(!gleich){GESTE=daumenNeu();ringSetzen(0,"")}
 AKTIV=neu;
 $("#gestenkopf").textContent=kopf;
 var dl=$("#gestenzeilen");leeren(dl);
 zeilen.forEach(function(z){dl.appendChild(el("dt","",z[0]));dl.appendChild(el("dd","",z[1]))});
 if(neu){
  $("#gestenstatus").textContent=AN?"Daumen hoch zeigen heißt Ja, Daumen runter heißt Nein. Oder auf der Hauptseite antworten.":
   "Die Kamera ist aus – mit eingeschalteter Kamera geht Daumen hoch als Ja. Oder auf der Hauptseite antworten.";
 }else $("#gestenstatus").textContent=hinweis;
}
async function freigabenSchleife(){
 for(;;){
  if(SCHREIBEN&&document.visibilityState==="visible"){
   try{
    var r=await holenJson("/api/freigaben");
    if(r.status===200&&r.daten&&Array.isArray(r.daten.offen)){FREIGABEN=r.daten.offen;karteSetzen()}
   }catch(f){}
  }
  await new Promise(function(ok){setTimeout(ok,1000)});
 }
}
async function vorschlagSchleife(){
 for(;;){
  await new Promise(function(ok){setTimeout(ok,3000)});
  if(SCHREIBEN&&STAND&&STAND.geste&&document.visibilityState==="visible"){
   var davor=VORSCHLAG&&VORSCHLAG.id;
   if(await standHolen()&&(VORSCHLAG&&VORSCHLAG.id)!==davor)karteSetzen();
  }
 }
}

// ---- Orb ----------------------------------------------------------------------------------------
var ORB=$("#orb"),SPUR=null,SATZ=null,STIMME_V=-1,ANZ_START=0,VERSATZ=0,ORB_ZUSTAND="",ORB_LAEUFT=false;
function orbSenden(nachricht){try{ORB.contentWindow.postMessage(nachricht,location.origin)}catch(f){}}
var ORBTEXT="";
function orbEtikett(text){if(text!==ORBTEXT){ORBTEXT=text;$("#orbetikett").textContent="Orb · "+text}}
function stimmeAnwenden(d){
 if(!d||typeof d!=="object")return;
 if(d.art==="pegel"&&Array.isArray(d.pegel)&&d.pegel.length){SPUR={start:Number(d.start_ms)||0,rahmen:Number(d.rahmen_ms)||20,pegel:d.pegel};SATZ=null;orbSchleife()}
 else if(d.art==="satz"&&typeof d.text==="string"){
  SPUR=null;var worte=d.text.trim().split(/\s+/).slice(0,80);
  SATZ={t0:Date.now(),worte:worte.length,geschickt:0,gestartet:false};orbSchleife();
 }
 else if(d.art==="aus"){SPUR=null;SATZ=null;orbSenden({pegel:0});orbSenden({sprechen:"ende"});orbEtikett("ruhig")}
}
function orbSchleife(){
 if(ORB_LAEUFT)return;
 ORB_LAEUFT=true;
 var schritt=function(){
  var jetzt=Date.now();
  if(SPUR){
   var i=Math.floor((jetzt+VERSATZ-SPUR.start)/SPUR.rahmen);
   if(i>=SPUR.pegel.length+5){SPUR=null;orbSenden({pegel:0});orbEtikett("ruhig")}
   else if(i>=0){orbSenden({pegel:Math.max(0,Math.min(1,Number(SPUR.pegel[Math.min(i,SPUR.pegel.length-1)])/255))});orbEtikett("Pegel echt")}
  }else if(SATZ){
   // Der Browser spricht selbst: kein Pegel zu haben, nur Wörter. Darum "nachempfunden".
   var vergangen=jetzt-SATZ.t0,soll=Math.floor(vergangen/380);
   if(!SATZ.gestartet){SATZ.gestartet=true;orbSenden({sprechen:"start"})}
   while(SATZ.geschickt<Math.min(soll,SATZ.worte)){SATZ.geschickt++;orbSenden({sprechen:"wort"})}
   orbEtikett("Pegel nachempfunden");
   if(vergangen>SATZ.worte*380+400){SATZ=null;orbSenden({sprechen:"ende"});orbEtikett("ruhig")}
  }
  if(SPUR||SATZ)(REDUZIERT?setTimeout(schritt,100):requestAnimationFrame(schritt));else ORB_LAEUFT=false;
 };
 requestAnimationFrame(schritt);
}
async function stimmeSchleife(){
 for(;;){
  try{
   var r=await holenJson("/api/anzeige?nach=stimme:"+STIMME_V+"&warten=20");
   if(r.status!==200||!r.daten||!r.daten.ok)throw new Error("Antwort");
   if(r.daten.start!==ANZ_START){ANZ_START=r.daten.start;STIMME_V=-1}
   VERSATZ=r.daten.jetzt*1000-Date.now();
   var k=r.daten.kanaele&&r.daten.kanaele.stimme;
   if(k){STIMME_V=k.version;if(k.daten&&k.daten.art)stimmeAnwenden(k.daten)}
  }catch(f){await new Promise(function(ok){setTimeout(ok,3000)})}
 }
}
async function zustandSchleife(){
 for(;;){
  try{
   var r=await holenJson("/api/status");
   var z=r.status===200&&r.daten&&r.daten.zustand;
   if(typeof z==="string"&&/^(bereit|hoert|denkt|spricht)$/.test(z)&&z!==ORB_ZUSTAND){ORB_ZUSTAND=z;orbSenden({zustand:z})}
  }catch(f){}
  await new Promise(function(ok){setTimeout(ok,2000)});
 }
}

// ---- Start --------------------------------------------------------------------------------------
$("#zurueck").setAttribute("href",url("/"));
ORB.addEventListener("load",function(){if(ORB_ZUSTAND)orbSenden({zustand:ORB_ZUSTAND})});
ORB.setAttribute("src",url("/gehirn?eingebettet=1&form=kugel"));
startPruefen("").then(function(){karteSetzen();verlaufLaden()});
freigabenSchleife();vorschlagSchleife();stimmeSchleife();zustandSchleife();
"""

SEITE_SEHEN = (_SEITE_KOPF + FEHLERFANG + _SEITE_RECHNEN + _SEITE_SKRIPT
               + "\n</script></body></html>\n").replace("{{SICHT_VERSION}}", SICHT_VERSION)
