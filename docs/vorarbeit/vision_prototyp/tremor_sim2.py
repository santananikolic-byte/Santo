import importlib.util, sys, random
spec = importlib.util.spec_from_file_location("s", sys.argv[1]); s = importlib.util.module_from_spec(spec)
import io, contextlib
with contextlib.redirect_stdout(io.StringIO()): spec.loader.exec_module(s)
random.seed(7)
for dauer in (4.0, 8.0):
    leer = sorted(s.lauf(0.0, 10.0, 0.4, dauer=dauer)[2] for _ in range(60))
    schwelle = leer[int(0.98 * len(leer))]
    print("Fenster %.0f s: Rauschen-only SNR 98%%-Quantil %.1f" % (dauer, schwelle))
    for amp in (0.1, 0.2, 0.3, 0.4):
        erg = [s.lauf(amp, 10.0, 0.4, dauer=dauer) for _ in range(30)]
        tr = sum(1 for r, f, snr in erg if snr > max(schwelle, 12) and abs(f - 10) <= 0.75)
        print("   Amp %.1f mm: erkannt %2d/30" % (amp, tr))
