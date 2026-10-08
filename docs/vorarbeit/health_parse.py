import zipfile, datetime, math, statistics, sys, time
import xml.etree.ElementTree as ET

HRV = "HKQuantityTypeIdentifierHeartRateVariabilitySDNN"
RUHEPULS = "HKQuantityTypeIdentifierRestingHeartRate"
SCHLAF = "HKCategoryTypeIdentifierSleepAnalysis"
SCHLAF_WERTE = {"HKCategoryValueSleepAnalysisAsleep", "HKCategoryValueSleepAnalysisAsleepUnspecified",
                "HKCategoryValueSleepAnalysisAsleepCore", "HKCategoryValueSleepAnalysisAsleepDeep",
                "HKCategoryValueSleepAnalysisAsleepREM"}

def _zeit(s):  # "2026-10-07 07:12:33 +0200"
    return datetime.datetime.strptime(s, "%Y-%m-%d %H:%M:%S %z")

def lese_export(pfad, ab_tag):
    hrv, puls, schlaf = {}, {}, {}
    zf = zipfile.ZipFile(pfad)
    name = next(n for n in zf.namelist() if n.endswith("/export.xml") or n == "export.xml")
    with zf.open(name) as f:
        for ev, el in ET.iterparse(f, events=("end",)):
            if el.tag != "Record":
                if el.tag in ("Workout", "ActivitySummary", "Correlation"):
                    el.clear()
                continue
            typ = el.get("type")
            if typ in (HRV, RUHEPULS, SCHLAF):
                ende = _zeit(el.get("endDate"))
                tag = ende.date()
                if tag >= ab_tag:
                    if typ == HRV:
                        start = _zeit(el.get("startDate"))
                        if start.hour < 8:  # naechtliche/morgendliche Messungen
                            hrv.setdefault(tag, []).append(float(el.get("value")))
                    elif typ == RUHEPULS:
                        puls[tag] = float(el.get("value"))
                    elif el.get("value") in SCHLAF_WERTE:
                        start = _zeit(el.get("startDate"))
                        schlaf.setdefault(tag, []).append((start, ende))
            el.clear()
    # ueberlappende Schlafintervalle (Uhr + iPhone) zusammenfuehren
    stunden = {}
    for tag, iv in schlaf.items():
        iv.sort(); summe = 0.0; a, b = iv[0]
        for s, e in iv[1:]:
            if s <= b: b = max(b, e)
            else: summe += (b - a).total_seconds(); a, b = s, e
        summe += (b - a).total_seconds()
        stunden[tag] = summe / 3600
    return {t: statistics.median(v) for t, v in hrv.items()}, puls, stunden

def erholung(tag, hrv, puls, schlaf, basis_tage=30, ziel_schlaf=7.5):
    basis = [tag - datetime.timedelta(days=i) for i in range(1, basis_tage + 1)]
    lh = [math.log(hrv[t]) for t in basis if t in hrv]
    rp = [puls[t] for t in basis if t in puls]
    if len(lh) < 14 or len(rp) < 14 or tag not in hrv:
        return None  # zu wenig Daten -> ehrlich sagen
    sd_h = statistics.stdev(lh) or 0.05
    sd_p = statistics.stdev(rp) or 1.0
    z_hrv = (math.log(hrv[tag]) - statistics.mean(lh)) / sd_h
    z_puls = -((puls.get(tag, statistics.mean(rp)) - statistics.mean(rp)) / sd_p)
    k = lambda x: max(0.0, min(100.0, x))
    teil_hrv = k(50 + 20 * z_hrv)
    teil_puls = k(50 + 20 * z_puls)
    teil_schlaf = k(100 * schlaf.get(tag, 0) / ziel_schlaf) if tag in schlaf else None
    if teil_schlaf is None:
        wert = 0.6 * teil_hrv + 0.4 * teil_puls
    else:
        wert = 0.45 * teil_hrv + 0.30 * teil_puls + 0.25 * teil_schlaf
    return round(wert), {"hrv": round(teil_hrv), "puls": round(teil_puls), "schlaf": None if teil_schlaf is None else round(teil_schlaf)}

t0 = time.time()
hrv, puls, schlaf = lese_export(sys.argv[1], datetime.date(2026, 7, 1))
print("Dauer", round(time.time() - t0, 2), "s; Tage hrv/puls/schlaf", len(hrv), len(puls), len(schlaf))
for tag in sorted(hrv)[-12:]:
    print(tag, "HRV", round(hrv[tag], 1), "RHR", puls.get(tag), "Schlaf", round(schlaf.get(tag, 0), 2), "->", erholung(tag, hrv, puls, schlaf))
