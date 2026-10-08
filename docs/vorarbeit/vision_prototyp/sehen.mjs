// Prototyp fuer die Seite /sehen - nur zur Syntaxpruefung.
import { FilesetResolver, GestureRecognizer, HandLandmarker }
  from "https://cdn.jsdelivr.net/npm/@mediapipe/tasks-vision@0.10.35/vision_bundle.mjs";

const MP = "https://cdn.jsdelivr.net/npm/@mediapipe/tasks-vision@0.10.35/wasm";
const MODELL = "https://storage.googleapis.com/mediapipe-models/gesture_recognizer/gesture_recognizer/float16/1/gesture_recognizer.task";
const VERBINDUNGEN = HandLandmarker.HAND_CONNECTIONS; // [{start,end}] x21

let erkenner = null, video = null, leinwand = null, g = null, letzteZeit = -1;

export async function starten(videoEl, canvasEl, meldung) {
  video = videoEl; leinwand = canvasEl; g = leinwand.getContext("2d");
  if (!window.isSecureContext || !navigator.mediaDevices) {
    return meldung("Die Kamera geht nur direkt am Mac (http://localhost:8765), nicht übers WLAN.");
  }
  let strom;
  try {
    strom = await navigator.mediaDevices.getUserMedia({
      audio: false,
      video: { width: { ideal: 1280 }, height: { ideal: 720 }, frameRate: { ideal: 60 }, facingMode: "user" },
    });
  } catch (f) {
    const grund = {
      NotAllowedError: "Kamera nicht erlaubt - im Browser oder in Systemeinstellungen > Datenschutz > Kamera freigeben.",
      NotFoundError: "Keine Kamera gefunden.",
      NotReadableError: "Die Kamera ist belegt (FaceTime, Zoom, Fotoaufnahme?).",
      OverconstrainedError: "Die Kamera kann dieses Format nicht.",
      SecurityError: "Unsichere Adresse - bitte über localhost öffnen.",
    }[f && f.name] || ("Kamera-Fehler: " + (f && f.message));
    return meldung(grund);
  }
  video.srcObject = strom; video.muted = true; video.playsInline = true;
  await video.play();
  const fileset = await FilesetResolver.forVisionTasks(MP);
  const optionen = (delegate) => ({
    baseOptions: { modelAssetPath: MODELL, delegate },
    runningMode: "VIDEO", numHands: 1,
    minHandDetectionConfidence: 0.6, minHandPresenceConfidence: 0.6, minTrackingConfidence: 0.6,
  });
  try { erkenner = await GestureRecognizer.createFromOptions(fileset, optionen("GPU")); }
  catch (_) { erkenner = await GestureRecognizer.createFromOptions(fileset, optionen("CPU")); }
  // Kamera aus, sobald das Fenster verdeckt ist oder geschlossen wird.
  document.addEventListener("visibilitychange", () => { if (document.hidden) stoppen(); });
  addEventListener("pagehide", stoppen);
  naechstesBild();
}

export function stoppen() {
  const s = video && video.srcObject;
  if (s) { s.getTracks().forEach((t) => t.stop()); video.srcObject = null; }
  if (erkenner) { erkenner.close(); erkenner = null; }
}

function naechstesBild() {
  if (!video || !video.srcObject) return;
  if ("requestVideoFrameCallback" in video) video.requestVideoFrameCallback(bild);
  else requestAnimationFrame(() => bild(performance.now(), null));
}

let letztesVideoZeit = -1;
function bild(jetzt, meta) {
  if (!erkenner) return;
  // Ohne requestVideoFrameCallback kann dasselbe Bild zweimal kommen.
  if (!meta) { if (video.currentTime === letztesVideoZeit) { naechstesBild(); return; }
               letztesVideoZeit = video.currentTime; }
  // MediaPipe verlangt streng steigende Zeitstempel (ms) - eine einzige Zeitbasis.
  const tErkennung = Math.max(performance.now(), letzteZeit + 1);
  letzteZeit = tErkennung;
  // Fuer die Tremor-Zeitreihe: Aufnahmezeit der Kamera, wenn der Browser sie liefert
  // (gleiche Basis wie performance.now), sonst Zeitpunkt des Rueckrufs.
  const t = (meta && meta.captureTime) || jetzt;
  const r = erkenner.recognizeForVideo(video, tErkennung);
  zeichnen(r);
  const hand = r.landmarks && r.landmarks[0];
  const geste = r.gestures && r.gestures[0] && r.gestures[0][0];
  tremorAufnehmen(t / 1000, hand, video.videoWidth, video.videoHeight);
  daumenPruefen(t, hand, geste);
  naechstesBild();
}

function zeichnen(r) {
  const b = leinwand.width = video.videoWidth, h = leinwand.height = video.videoHeight;
  g.clearRect(0, 0, b, h);
  for (const hand of r.landmarks || []) {
    g.strokeStyle = "rgba(232,98,44,.9)"; g.lineWidth = 3;
    for (const { start, end } of VERBINDUNGEN) {
      g.beginPath(); g.moveTo(hand[start].x * b, hand[start].y * h);
      g.lineTo(hand[end].x * b, hand[end].y * h); g.stroke();
    }
    g.fillStyle = "#fff";
    for (const p of hand) { g.beginPath(); g.arc(p.x * b, p.y * h, 4, 0, 6.2832); g.fill(); }
  }
}

// ---------- Handruhe (Mikrobewegung) ----------
const FS = 30, FENSTER_S = 8, SPITZEN = [4, 8, 12, 16, 20];
const puffer = [];   // {t, x, y} in Handgroessen-Einheiten

function handgroesse(hand, b, h) {
  // Handgelenk (0) bis Mittelfinger-Grundgelenk (9), in Pixeln
  return Math.hypot((hand[9].x - hand[0].x) * b, (hand[9].y - hand[0].y) * h);
}

function tremorAufnehmen(t, hand, b, h) {
  if (!hand) { puffer.length = 0; return; }      // Luecke = neu anfangen
  const s = handgroesse(hand, b, h);
  if (s < 0.08 * h) { puffer.length = 0; return; } // Hand zu klein/weit weg
  // Mittel der fuenf Fingerspitzen, in Pixeln, geteilt durch die Handgroesse
  let x = 0, y = 0;
  for (const i of SPITZEN) { x += hand[i].x * b; y += hand[i].y * h; }
  puffer.push({ t, x: x / SPITZEN.length / s, y: y / SPITZEN.length / s });
  while (puffer.length && puffer[0].t < t - FENSTER_S - 0.5) puffer.shift();
}

// Liefert null, solange zu wenig oder zu ungleichmaessige Daten da sind.
export function handruhe(handLaengeMm = 95) {
  if (puffer.length < 2) return null;
  const dauer = puffer[puffer.length - 1].t - puffer[0].t;
  const fpsEcht = (puffer.length - 1) / Math.max(dauer, 1e-6);
  if (dauer < FENSTER_S || fpsEcht < 25) return { gueltig: false, fps: fpsEcht };
  const n = FENSTER_S * FS, t0 = puffer[puffer.length - 1].t - FENSTER_S;
  const ergebnis = { gueltig: true, fps: fpsEcht };
  for (const achse of ["x", "y"]) {
    // 1) gleichmaessiges 30-Hz-Raster (lineare Interpolation ueber echte Bildzeiten)
    const roh = new Float64Array(n); let j = 0;
    for (let i = 0; i < n; i++) {
      const tz = t0 + i / FS;
      while (j < puffer.length - 2 && puffer[j + 1].t < tz) j++;
      const a = Math.min(1, Math.max(0, (tz - puffer[j].t) / (puffer[j + 1].t - puffer[j].t || 1)));
      roh[i] = puffer[j][achse] * (1 - a) + puffer[j + 1][achse] * a;
    }
    // 2) Hochpass: gleitender Mittelwert ueber 9 Bilder (0,3 s) abziehen
    const k = 4, hp = [];
    for (let i = k; i < n - k; i++) {
      let m = 0; for (let q = -k; q <= k; q++) m += roh[i + q];
      hp.push(roh[i] - m / (2 * k + 1));
    }
    // 3) RMS in Handgroessen -> mm-Schaetzung
    const rms = Math.sqrt(hp.reduce((s, v) => s + v * v, 0) / hp.length);
    // 4) Hann-Fenster + kleine DFT 3..14 Hz
    const m = hp.length, spek = [];
    for (let f = 3; f <= 14.001; f += 0.25) {
      let re = 0, im = 0;
      for (let i = 0; i < m; i++) {
        const w = 0.5 - 0.5 * Math.cos(2 * Math.PI * i / (m - 1));
        re += hp[i] * w * Math.cos(2 * Math.PI * f * i / FS);
        im += hp[i] * w * Math.sin(2 * Math.PI * f * i / FS);
      }
      spek.push([f, re * re + im * im]);
    }
    const sortiert = spek.map((e) => e[1]).sort((a, b) => a - b);
    const median = sortiert[sortiert.length >> 1] || 1e-12;
    const spitze = spek.reduce((a, e) => (e[1] > a[1] ? e : a));
    ergebnis[achse] = {
      rmsMm: rms * handLaengeMm,
      rhythmusHz: spitze[1] / median > 20 ? spitze[0] : null, // sonst: kein deutlicher Rhythmus
    };
  }
  return ergebnis;
}

// ---------- Daumen hoch = Ja (bewusst schwer auszuloesen) ----------
const HALTEN_MS = 1500, LUECKE_MS = 120, SPERRE_MS = 3000;
let daumen = { scharf: false, seit: 0, zuletzt: 0, gesperrtBis: 0, ohneSeit: 0 };
let beiJa = null;   // nur gesetzt, solange genau eine Freigabe offen ist
export function daumenScharfFuer(rueckruf) { beiJa = rueckruf; daumen.scharf = false; daumen.seit = 0; daumen.ohneSeit = 0; }

function winkelZuSenkrecht(a, b) {           // 0 Grad = zeigt nach oben
  return Math.abs(Math.atan2(b.x - a.x, -(b.y - a.y)) * 180 / Math.PI);
}
function abst(a, b) { return Math.hypot(a.x - b.x, a.y - b.y); }

function istDaumenHoch(hand, geste, streng) {
  if (!hand) return false;
  const toleranz = streng ? 35 : 50;          // Hysterese: rein schwer, raus leicht
  const palme = abst(hand[0], hand[9]);
  const daumenLang = abst(hand[2], hand[4]) > 0.55 * palme;
  const daumenOben = hand[4].y < hand[3].y && hand[3].y < hand[2].y
    && winkelZuSenkrecht(hand[2], hand[4]) < toleranz;
  // Spitze des Daumens ist der hoechste Punkt der ganzen Hand
  const hoechster = hand.every((p, i) => i === 4 || hand[4].y < p.y - (streng ? 0.15 : 0.05) * palme);
  // Die vier Finger sind eingerollt: Spitze naeher am Handgelenk als das Mittelgelenk
  const eingerollt = [[6, 8], [10, 12], [14, 16], [18, 20]]
    .every(([mittel, spitze]) => abst(hand[spitze], hand[0]) < abst(hand[mittel], hand[0]) * (streng ? 1.0 : 1.1));
  const modell = !geste || (geste.categoryName === "Thumb_Up" && geste.score > (streng ? 0.7 : 0.5));
  return daumenLang && daumenOben && hoechster && eingerollt && modell;
}

function daumenPruefen(t, hand, geste) {
  const d = daumen;
  if (!beiJa || t < d.gesperrtBis) { d.scharf = false; d.seit = 0; return; }
  const jetzt = istDaumenHoch(hand, geste, !d.seit);   // strenge Regeln nur zum Einstieg
  if (!d.scharf) {                    // erst scharf, wenn 0,5 s KEIN Daumen zu sehen war
    if (!jetzt) { d.ohneSeit = d.ohneSeit || t; if (t - d.ohneSeit > 500) d.scharf = true; }
    else d.ohneSeit = 0;
    return;
  }
  if (jetzt) { d.zuletzt = t; if (!d.seit) d.seit = t; }
  else if (d.seit && t - d.zuletzt > LUECKE_MS) { d.seit = 0; }   // kurze Aussetzer verzeihen
  const fortschritt = d.seit ? Math.min(1, (t - d.seit) / HALTEN_MS) : 0;
  if (fortschritt >= 1) {
    const ja = beiJa; beiJa = null;
    Object.assign(d, { scharf: false, seit: 0, ohneSeit: 0, gesperrtBis: t + SPERRE_MS });
    ja();
  }
}
