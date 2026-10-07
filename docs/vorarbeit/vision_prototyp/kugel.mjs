// Kugel-Pegel: echte Huellkurve vom Mac (afplay) oder Ersatzanimation (speechSynthesis).
let spur = null;            // {nr, start_ms, rahmen_ms, pegel:[0..255]}
let ersatzBis = 0, wortImpuls = 0, glatt = 0;
const SCHLUESSEL = "";      // {{SCHLUESSEL}} wird vom Server ersetzt

async function stimmeLauschen(nach = -1) {
  for (;;) {
    try {
      const r = await fetch("/api/stimme?nach=" + nach + (SCHLUESSEL ? "&schluessel=" + SCHLUESSEL : ""),
                            { cache: "no-store" });
      const d = await r.json();
      if (d && d.ok && d.nr > nach) { spur = d; nach = d.nr; }
    } catch (_) { await new Promise((ok) => setTimeout(ok, 2000)); }
  }
}

// Ersatz, wenn der Browser selbst spricht: keine Audiodaten, nur Ereignisse.
addEventListener("message", (e) => {
  if (e.origin !== location.origin || !e.data) return;
  if (e.data.sprechen === "start") ersatzBis = Date.now() + 15000;
  if (e.data.sprechen === "wort") wortImpuls = 1;
  if (e.data.sprechen === "ende") ersatzBis = 0;
});

export function pegelJetzt() {
  const jetzt = Date.now();             // gleiche Uhr wie time.time() auf dem Mac
  let ziel = 0;
  if (spur) {
    const i = Math.floor((jetzt - spur.start_ms) / spur.rahmen_ms);
    if (i >= 0 && i < spur.pegel.length) ziel = spur.pegel[i] / 255;
  }
  if (!ziel && jetzt < ersatzBis) {     // erkennbar "unechter" Pegel: weicher Puls + Wortimpulse
    ziel = 0.35 + 0.15 * Math.sin(jetzt / 90) + 0.4 * wortImpuls;
    wortImpuls *= 0.85;
  }
  // schnell hoch, langsam runter - wirkt wie ein VU-Meter
  glatt += (ziel - glatt) * (ziel > glatt ? 0.5 : 0.12);
  return glatt;
}
stimmeLauschen();
