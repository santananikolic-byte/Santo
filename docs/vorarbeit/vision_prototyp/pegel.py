# Huellkurve (Lautstaerke je 20 ms) aus einer WAV-Datei - nur Standardbibliothek.
# Kein audioop/aifc: beide sind ab Python 3.13 entfernt.
import array, math, sys, wave

def huellkurve(pfad: str, rahmen_ms: int = 20) -> dict:
    with wave.open(pfad, "rb") as w:
        kanaele, breite, rate, n = w.getnchannels(), w.getsampwidth(), w.getframerate(), w.getnframes()
        if breite != 2:
            return {"ok": False, "fehler": "nur 16-Bit-PCM"}
        roh = w.readframes(n)
    werte = array.array("h"); werte.frombytes(roh)
    if sys.byteorder == "big":
        werte.byteswap()                      # WAV ist immer Little Endian
    je_rahmen = max(1, rate * rahmen_ms // 1000) * kanaele
    pegel = []
    for start in range(0, len(werte), je_rahmen):
        stueck = werte[start:start + je_rahmen]
        rms = math.sqrt(sum(v * v for v in stueck) / len(stueck)) / 32768.0
        # dB-Skala, -50 dB .. 0 dB -> 0..255; so sieht leise Sprache nicht tot aus
        db = 20 * math.log10(rms) if rms > 1e-6 else -120.0
        pegel.append(max(0, min(255, int((db + 50) / 50 * 255))))
    return {"ok": True, "rahmen_ms": rahmen_ms, "dauer_ms": int(n * 1000 / rate), "pegel": pegel}

if __name__ == "__main__":
    # Selbsttest: 1 s Ton mit an- und abschwellender Lautstaerke
    pfad = sys.argv[1]
    with wave.open(pfad, "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(22050)
        daten = array.array("h", (int(20000 * abs(math.sin(math.pi * i / 22050)) * math.sin(2 * math.pi * 220 * i / 22050)) for i in range(22050)))
        w.writeframes(daten.tobytes())
    import time; t = time.perf_counter(); e = huellkurve(pfad); d = time.perf_counter() - t
    print(len(e["pegel"]), "Rahmen", e["dauer_ms"], "ms, Rechenzeit %.1f ms" % (d * 1000), e["pegel"][::5])
