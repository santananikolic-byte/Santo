# Simuliert Fingerspitzen-Zeitreihe bei ~30 fps mit Jitter, prueft Hochpass + DFT-Spitzensuche.
import math, random
random.seed(1)
FS = 30.0
def messen(t, x, fenster_s=4.0):
    # 1) auf gleichmaessiges 30-Hz-Raster interpolieren
    t0, t1 = t[-1] - fenster_s, t[-1]
    n = int(fenster_s * FS)
    grid = [t0 + i / FS for i in range(n)]
    j = 0; y = []
    for g in grid:
        while j < len(t) - 2 and t[j + 1] < g: j += 1
        a = (g - t[j]) / max(1e-9, t[j + 1] - t[j]); a = min(1, max(0, a))
        y.append(x[j] * (1 - a) + x[j + 1] * a)
    # 2) Hochpass: gleitenden Mittelwert (0.3 s) abziehen -> Grenze ~3 Hz
    k = 9; h = k // 2
    hp = []
    for i in range(n):
        lo, hi = max(0, i - h), min(n, i + h + 1)
        hp.append(y[i] - sum(y[lo:hi]) / (hi - lo))
    hp = hp[h:n - h]
    m = len(hp)
    rms = math.sqrt(sum(v * v for v in hp) / m)
    # 3) Hann + DFT 3..14 Hz in 0.25-Hz-Schritten
    w = [0.5 - 0.5 * math.cos(2 * math.pi * i / (m - 1)) for i in range(m)]
    spek = []
    f = 3.0
    while f <= 14.0001:
        re = sum(hp[i] * w[i] * math.cos(2 * math.pi * f * i / FS) for i in range(m))
        im = sum(hp[i] * w[i] * math.sin(2 * math.pi * f * i / FS) for i in range(m))
        spek.append((f, re * re + im * im)); f += 0.25
    spek_s = sorted(p for _, p in spek)
    median = spek_s[len(spek_s) // 2]
    fpk, ppk = max(spek, key=lambda e: e[1])
    return rms, fpk, ppk / median

def lauf(amp_mm, f_hz, rausch_mm, fps=30.0, jitter_ms=4.0, dauer=4.0):
    t = []; x = []; tt = 0.0
    while tt < dauer + 0.5:
        t.append(tt)
        x.append(amp_mm * math.sin(2 * math.pi * f_hz * tt) + random.gauss(0, rausch_mm) + 2.0 * math.sin(2 * math.pi * 0.3 * tt))
        tt += 1 / fps + random.gauss(0, jitter_ms / 1000)
    return messen(t, x, dauer)

for amp in (0.0, 0.05, 0.1, 0.2, 0.4, 1.0):
    erg = [lauf(amp, 10.0, 0.4) for _ in range(30)]
    treffer = sum(1 for r, f, snr in erg if snr > 8 and abs(f - 10) <= 0.75)
    print("Amp %.2f mm @10Hz, Rauschen 0.4 mm: Treffer %2d/30, RMS-Mittel %.3f mm, SNR-Median %.1f" % (
        amp, treffer, sum(e[0] for e in erg) / 30, sorted(e[2] for e in erg)[15]))
# Aliasing: 15-fps-Kamera (Dunkelheit), 10-Hz-Tremor
r, f, snr = lauf(1.0, 10.0, 0.1, fps=15.0)
print("15 fps, echte 10 Hz -> gefunden %.2f Hz (Faltung auf 5 Hz zu erwarten), SNR %.1f" % (f, snr))
r, f, snr = lauf(1.0, 18.0, 0.1)
print("30 fps, echte 18 Hz -> gefunden %.2f Hz (Faltung auf 12 Hz)" % f)
