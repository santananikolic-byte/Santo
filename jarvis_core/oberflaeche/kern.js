/* Der leuchtende Kern: ein Knäuel aus Drähten auf einer Kugel.
 * Er ist rein optisch und zeigt nur den Zustand von JARVIS (bereit, hört zu, denkt, spricht, gesperrt).
 * Er erfindet keine Messwerte. */
(function () {
  "use strict";

  var ZUSTAENDE = {
    bereit:   { drehen: 0.16, unruhe: 0.012, hell: 0.85, puls: 0.012, fluss: 0, ring: 0, farbe: [255, 138, 31] },
    hoert:    { drehen: 0.30, unruhe: 0.030, hell: 1.05, puls: 0.020, fluss: 0, ring: 1, farbe: [255, 172, 72] },
    denkt:    { drehen: 0.95, unruhe: 0.045, hell: 1.15, puls: 0.025, fluss: 1, ring: 0, farbe: [255, 192, 104] },
    spricht:  { drehen: 0.36, unruhe: 0.070, hell: 1.25, puls: 0.085, fluss: 0.3, ring: 0, farbe: [255, 160, 55] },
    gesperrt: { drehen: 0.02, unruhe: 0, hell: 0.5, puls: 0, fluss: 0, ring: 0, farbe: [255, 80, 65] },
    offline:  { drehen: 0.05, unruhe: 0, hell: 0.35, puls: 0, fluss: 0, ring: 0, farbe: [140, 130, 120] }
  };
  var DRAEHTE = 44;
  var PUNKTE = 150;

  function zufallsfolge(start) {
    var s = start | 0;
    return function () {
      s = (s + 0x6D2B79F5) | 0;
      var t = Math.imul(s ^ (s >>> 15), 1 | s);
      t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
      return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
    };
  }
  function norm(v) { var l = Math.sqrt(v[0] * v[0] + v[1] * v[1] + v[2] * v[2]) || 1; return [v[0] / l, v[1] / l, v[2] / l]; }
  function kreuz(a, b) { return [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]]; }

  /* Ein Draht ist ein Zufallsweg auf der Kugel mit sanften Richtungswechseln. */
  function draht(zufall) {
    var p = norm([zufall() * 2 - 1, zufall() * 2 - 1, zufall() * 2 - 1]);
    var r = norm(kreuz(p, [zufall() * 2 - 1, zufall() * 2 - 1, zufall() * 2 - 1]));
    var schritt = 0.05 + zufall() * 0.04;
    var drall = (zufall() - 0.5) * 0.5;
    var punkte = new Float32Array(PUNKTE * 3);
    for (var i = 0; i < PUNKTE; i++) {
      punkte[i * 3] = p[0]; punkte[i * 3 + 1] = p[1]; punkte[i * 3 + 2] = p[2];
      drall += (zufall() - 0.5) * 0.18;
      drall = Math.max(-0.45, Math.min(0.45, drall));
      var n = kreuz(p, r), c = Math.cos(drall), s = Math.sin(drall);
      r = norm([r[0] * c + n[0] * s, r[1] * c + n[1] * s, r[2] * c + n[2] * s]);
      var cs = Math.cos(schritt), ss = Math.sin(schritt);
      var np = norm([p[0] * cs + r[0] * ss, p[1] * cs + r[1] * ss, p[2] * cs + r[2] * ss]);
      var nr = norm([r[0] * cs - p[0] * ss, r[1] * cs - p[1] * ss, r[2] * cs - p[2] * ss]);
      p = np; r = nr;
    }
    return punkte;
  }

  function start(leinwand) {
    var ctx = leinwand.getContext("2d");
    var ruhig = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    var zufall = zufallsfolge(20261031);
    var draehte = [];
    for (var d = 0; d < DRAEHTE; d++) draehte.push(draht(zufall));
    var puffer = [0, 1, 2, 3, 4].map(function () { return new Float32Array(DRAEHTE * PUNKTE * 4); });
    var anzahl = [0, 0, 0, 0, 0];

    var ziel = ZUSTAENDE.bereit;
    var akt = { drehen: ziel.drehen, unruhe: ziel.unruhe, hell: ziel.hell, puls: ziel.puls, fluss: ziel.fluss, ring: ziel.ring, farbe: ziel.farbe.slice() };
    var breite = 0, hoehe = 0, dpr = 1;
    var sichtbar = true;
    var gierung = 0, neigung = 0.35, zeit = 0, letzte = 0;

    function groesse() {
      var rect = leinwand.getBoundingClientRect();
      dpr = Math.min(window.devicePixelRatio || 1, 2);
      breite = Math.max(1, Math.round(rect.width * dpr));
      hoehe = Math.max(1, Math.round(rect.height * dpr));
      if (leinwand.width !== breite || leinwand.height !== hoehe) { leinwand.width = breite; leinwand.height = hoehe; }
    }
    if (window.ResizeObserver) new ResizeObserver(groesse).observe(leinwand); else window.addEventListener("resize", groesse);
    if (window.IntersectionObserver) new IntersectionObserver(function (e) { sichtbar = e[0].isIntersecting; }).observe(leinwand);
    groesse();

    function weich(a, b, k) { return a + (b - a) * k; }

    function zeichnen(jetzt) {
      window.requestAnimationFrame(zeichnen);
      if (!sichtbar || document.hidden) { letzte = jetzt; return; }
      var dt = Math.min(0.05, (jetzt - (letzte || jetzt)) / 1000);
      letzte = jetzt;
      if (ruhig && dt > 0 && (jetzt % 100) > 16) return; // bei "weniger Bewegung": selten und langsam
      zeit += dt;
      var k = 1 - Math.exp(-dt * 4);
      akt.drehen = weich(akt.drehen, ziel.drehen * (ruhig ? 0.2 : 1), k);
      akt.unruhe = weich(akt.unruhe, ruhig ? 0 : ziel.unruhe, k);
      akt.hell = weich(akt.hell, ziel.hell, k);
      akt.puls = weich(akt.puls, ruhig ? 0 : ziel.puls, k);
      akt.fluss = weich(akt.fluss, ruhig ? 0 : ziel.fluss, k);
      akt.ring = weich(akt.ring, ruhig ? 0 : ziel.ring, k);
      for (var c = 0; c < 3; c++) akt.farbe[c] = weich(akt.farbe[c], ziel.farbe[c], k);
      gierung += akt.drehen * dt;
      neigung = 0.35 + Math.sin(zeit * 0.2) * 0.12;

      var cx = breite / 2, cy = hoehe / 2;
      var radius = Math.min(breite, hoehe) * 0.33;
      var f = akt.farbe, fs = Math.round(f[0]) + "," + Math.round(f[1]) + "," + Math.round(f[2]);
      var sprechen = 1 + akt.puls * (Math.sin(zeit * 9.1) * 0.5 + Math.sin(zeit * 14.3 + 1) * 0.3 + Math.sin(zeit * 5.2 + 2) * 0.4);
      var R = radius * sprechen;

      ctx.setTransform(1, 0, 0, 1, 0, 0);
      ctx.clearRect(0, 0, breite, hoehe);
      ctx.globalCompositeOperation = "source-over";
      var glut = ctx.createRadialGradient(cx, cy, R * 0.15, cx, cy, R * 1.65);
      glut.addColorStop(0, "rgba(" + fs + "," + (0.34 * akt.hell) + ")");
      glut.addColorStop(0.45, "rgba(" + fs + "," + (0.13 * akt.hell) + ")");
      glut.addColorStop(1, "rgba(" + fs + ",0)");
      ctx.fillStyle = glut;
      ctx.fillRect(0, 0, breite, hoehe);
      var innen = ctx.createRadialGradient(cx, cy, 0, cx, cy, R);
      innen.addColorStop(0, "rgba(" + fs + "," + (0.16 * akt.hell) + ")");
      innen.addColorStop(1, "rgba(" + fs + "," + (0.03 * akt.hell) + ")");
      ctx.fillStyle = innen;
      ctx.beginPath(); ctx.arc(cx, cy, R, 0, Math.PI * 2); ctx.fill();

      /* HUD-Ring mit Strichen */
      ctx.lineWidth = Math.max(1, dpr);
      ctx.strokeStyle = "rgba(" + fs + "," + (0.28 * akt.hell) + ")";
      ctx.setLineDash([2 * dpr, 7 * dpr]);
      ctx.beginPath(); ctx.arc(cx, cy, radius * 1.3, zeit * 0.05, zeit * 0.05 + Math.PI * 2); ctx.stroke();
      ctx.setLineDash([]);
      ctx.beginPath();
      for (var t = 0; t < 72; t++) {
        var w = t * Math.PI / 36 - zeit * 0.08, lang = t % 6 === 0 ? 0.075 : 0.035;
        ctx.moveTo(cx + Math.cos(w) * radius * 1.22, cy + Math.sin(w) * radius * 1.22);
        ctx.lineTo(cx + Math.cos(w) * radius * (1.22 + lang), cy + Math.sin(w) * radius * (1.22 + lang));
      }
      ctx.stroke();

      /* Drähte: drehen, projizieren, nach Tiefe sortieren */
      var cg = Math.cos(gierung), sg = Math.sin(gierung), cn = Math.cos(neigung), sn = Math.sin(neigung);
      anzahl[0] = anzahl[1] = anzahl[2] = anzahl[3] = anzahl[4] = 0;
      var kopfbreite = 0.07;
      for (var di = 0; di < DRAEHTE; di++) {
        var punkte = draehte[di];
        var kopf = ((zeit * 0.35 + di * 0.137) % 1);
        var vx = 0, vy = 0, vz = 0, hat = false;
        for (var i = 0; i < PUNKTE; i++) {
          var x = punkte[i * 3], y = punkte[i * 3 + 1], z = punkte[i * 3 + 2];
          var rauschen = 1 + akt.unruhe * Math.sin(zeit * 3.1 + i * 0.37 + di * 1.7) + (sprechen - 1) * 0.35 * Math.sin(i * 0.5 + di);
          x *= rauschen; y *= rauschen; z *= rauschen;
          var x1 = x * cg + z * sg, z1 = -x * sg + z * cg;
          var y1 = y * cn - z1 * sn, z2 = y * sn + z1 * cn;
          var persp = 1 + z2 * 0.14;
          var px = cx + x1 * R * persp, py = cy + y1 * R * persp;
          if (hat) {
            var zm = (z2 + vz) * 0.5;
            var b = zm > 0.5 ? 3 : zm > 0 ? 2 : zm > -0.5 ? 1 : 0;
            var feld = puffer[b], n = anzahl[b];
            feld[n] = vx; feld[n + 1] = vy; feld[n + 2] = px; feld[n + 3] = py; anzahl[b] = n + 4;
            if (akt.fluss > 0.05) {
              var abstand = Math.abs(i / PUNKTE - kopf);
              if (abstand > 0.5) abstand = 1 - abstand;
              if (abstand < kopfbreite) { var h = puffer[4], m = anzahl[4]; h[m] = vx; h[m + 1] = vy; h[m + 2] = px; h[m + 3] = py; anzahl[4] = m + 4; }
            }
          }
          vx = px; vy = py; vz = z2; hat = true;
        }
      }
      ctx.globalCompositeOperation = "lighter";
      ctx.lineCap = "round";
      var alphas = [0.11, 0.21, 0.38, 0.66];
      for (var bu = 0; bu < 4; bu++) {
        ctx.strokeStyle = "rgba(" + fs + "," + Math.min(1, alphas[bu] * akt.hell) + ")";
        ctx.lineWidth = (0.8 + bu * 0.3) * dpr;
        ctx.beginPath();
        var feld2 = puffer[bu], ende = anzahl[bu];
        for (var q = 0; q < ende; q += 4) { ctx.moveTo(feld2[q], feld2[q + 1]); ctx.lineTo(feld2[q + 2], feld2[q + 3]); }
        ctx.stroke();
      }
      for (var gl = 2; gl < 4; gl++) { // weicher Schein um die vorderen Drähte
        ctx.strokeStyle = "rgba(" + fs + "," + Math.min(1, 0.07 * akt.hell) + ")";
        ctx.lineWidth = (2.6 + gl) * dpr;
        ctx.beginPath();
        var feld3 = puffer[gl], ende3 = anzahl[gl];
        for (var q3 = 0; q3 < ende3; q3 += 4) { ctx.moveTo(feld3[q3], feld3[q3 + 1]); ctx.lineTo(feld3[q3 + 2], feld3[q3 + 3]); }
        ctx.stroke();
      }
      if (anzahl[4] > 0) {
        ctx.strokeStyle = "rgba(255,236,200," + Math.min(1, 0.85 * akt.fluss) + ")";
        ctx.lineWidth = 1.8 * dpr;
        ctx.beginPath();
        var hf = puffer[4];
        for (var q2 = 0; q2 < anzahl[4]; q2 += 4) { ctx.moveTo(hf[q2], hf[q2 + 1]); ctx.lineTo(hf[q2 + 2], hf[q2 + 3]); }
        ctx.stroke();
      }

      /* Ringe beim Zuhören */
      if (akt.ring > 0.03) {
        for (var rr = 0; rr < 3; rr++) {
          var ph = ((zeit * 0.55 + rr / 3) % 1);
          ctx.strokeStyle = "rgba(" + fs + "," + ((1 - ph) * 0.4 * akt.ring) + ")";
          ctx.lineWidth = 1.5 * dpr;
          ctx.beginPath(); ctx.arc(cx, cy, radius * (1.02 + ph * 0.5), 0, Math.PI * 2); ctx.stroke();
        }
      }
      ctx.globalCompositeOperation = "source-over";
    }
    window.requestAnimationFrame(zeichnen);

    return {
      zustand: function (name) { ziel = ZUSTAENDE[name] || ZUSTAENDE.bereit; }
    };
  }

  window.JarvisKern = { start: start };
})();
