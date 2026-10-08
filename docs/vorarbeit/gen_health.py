# erzeugt eine synthetische export.zip im Format des Apple-Health-Exports (nur Test)
import random, zipfile, datetime, sys
out = sys.argv[1]
random.seed(1)
kopf = '''<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE HealthData [
<!-- HealthKit Export Version: 14 -->
<!ELEMENT HealthData (ExportDate,Me,(Record|Correlation|Workout|ActivitySummary|ClinicalRecord|Audiogram|VisionPrescription)*)>
<!ATTLIST HealthData locale CDATA #REQUIRED>
<!ELEMENT ExportDate EMPTY>
<!ATTLIST ExportDate value CDATA #REQUIRED>
<!ELEMENT Me EMPTY>
<!ATTLIST Me HKCharacteristicTypeIdentifierDateOfBirth CDATA #REQUIRED>
<!ELEMENT Record ((MetadataEntry|HeartRateVariabilityMetadataList)*)>
<!ATTLIST Record type CDATA #REQUIRED unit CDATA #IMPLIED value CDATA #IMPLIED sourceName CDATA #REQUIRED sourceVersion CDATA #IMPLIED device CDATA #IMPLIED creationDate CDATA #IMPLIED startDate CDATA #REQUIRED endDate CDATA #REQUIRED>
<!ELEMENT MetadataEntry EMPTY>
<!ATTLIST MetadataEntry key CDATA #REQUIRED value CDATA #REQUIRED>
<!ELEMENT HeartRateVariabilityMetadataList (InstantaneousBeatsPerMinute*)>
<!ELEMENT InstantaneousBeatsPerMinute EMPTY>
<!ATTLIST InstantaneousBeatsPerMinute bpm CDATA #REQUIRED time CDATA #REQUIRED>
]>
<HealthData locale="de_DE">
 <ExportDate value="2026-10-07 07:00:00 +0200"/>
 <Me HKCharacteristicTypeIdentifierDateOfBirth="1985-01-01"/>
'''
f = lambda d: d.strftime('%Y-%m-%d %H:%M:%S +0200')
zeilen = [kopf]
start = datetime.datetime(2026, 8, 1)
for t in range(68):
    tag = start + datetime.timedelta(days=t)
    for _ in range(300):  # Puls-Ballast wie im echten Export
        z = tag + datetime.timedelta(minutes=random.randint(0, 1439))
        zeilen.append(f' <Record type="HKQuantityTypeIdentifierHeartRate" sourceName="Apple Watch" unit="count/min" creationDate="{f(z)}" startDate="{f(z)}" endDate="{f(z)}" value="{random.randint(55,110)}"/>\n')
    for h in (2, 5, 14):
        z = tag + datetime.timedelta(hours=h)
        zeilen.append(f' <Record type="HKQuantityTypeIdentifierHeartRateVariabilitySDNN" sourceName="Apple Watch" unit="ms" creationDate="{f(z)}" startDate="{f(z)}" endDate="{f(z+datetime.timedelta(minutes=1))}" value="{random.gauss(48 if t<60 else 35, 8):.4f}">\n  <HeartRateVariabilityMetadataList>\n   <InstantaneousBeatsPerMinute bpm="58" time="2:01:02,51 AM"/>\n  </HeartRateVariabilityMetadataList>\n </Record>\n')
    z = tag + datetime.timedelta(hours=9)
    zeilen.append(f' <Record type="HKQuantityTypeIdentifierRestingHeartRate" sourceName="Apple Watch" unit="count/min" creationDate="{f(z)}" startDate="{f(tag)}" endDate="{f(z)}" value="{round(random.gauss(56 if t<60 else 62, 2))}"/>\n')
    s = tag - datetime.timedelta(hours=1) + datetime.timedelta(minutes=random.randint(-30, 30))
    zeilen.append(f' <Record type="HKCategoryTypeIdentifierSleepAnalysis" sourceName="Apple Watch" creationDate="{f(s)}" startDate="{f(s)}" endDate="{f(s+datetime.timedelta(hours=8))}" value="HKCategoryValueSleepAnalysisInBed"/>\n')
    phasen = ['HKCategoryValueSleepAnalysisAsleepCore','HKCategoryValueSleepAnalysisAsleepDeep','HKCategoryValueSleepAnalysisAsleepREM','HKCategoryValueSleepAnalysisAwake']
    p = s
    ende = s + datetime.timedelta(hours=random.uniform(6.8, 7.8) if t < 60 else random.uniform(5.0, 6.0))
    while p < ende:
        d = datetime.timedelta(minutes=random.randint(10, 50)); ph = random.choice(phasen)
        zeilen.append(f' <Record type="HKCategoryTypeIdentifierSleepAnalysis" sourceName="Apple Watch" creationDate="{f(p+d)}" startDate="{f(p)}" endDate="{f(min(p+d, ende))}" value="{ph}">\n  <MetadataEntry key="HKTimeZone" value="Europe/Berlin"/>\n </Record>\n')
        p += d
zeilen.append('</HealthData>\n')
with zipfile.ZipFile(out, 'w', zipfile.ZIP_DEFLATED) as z:
    z.writestr('apple_health_export/export.xml', ''.join(zeilen))
