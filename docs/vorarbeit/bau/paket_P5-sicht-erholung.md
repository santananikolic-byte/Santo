# P5-sicht-erholung Sicht & Erholung: MediaPipe-Dateien laden und lokal ausliefern, Handruhe speichern und vergleichen, Erholung aus Apple Health / Oura / Whoop / Hand, Zusammenhang mit Abschlussquote, proaktive Entlastung

Anwendungsfaelle: ['11', '13 (Empfehlung aus Kalender, Erholung, Abschlussquote)', "Video 2 (Server-Seite: Wearables, Korrelation, Vorschlag 'Soll ich morgen zwei Termine streichen?')"]
Neue Dateien: ['src/modules/sicht.py', 'src/modules/erholung.py', 'src/modules/leistung.py']
Geaenderte Dateien: ['src/modules/tools.py (7 tools, __init__, umschauen description)', 'src/modules/webapp.py (6 routes, ANZEIGE_PFADE, prefix rule)', 'src/modules/camera.py (docstring principle)', 'src/modules/scheduler.py (standardjobs_anlegen: belastung)', 'src/agent.py (_bausteine_sammeln recovery line)', 'src/run.py (CLI: sicht laden/an/aus, gesundheit, zugang oura/whoop)', 'src/config.py (+ MODELL_VERZEICHNIS path)', 'config/.env.beispiel', 'build_single.py', 'tests/abnahme.py (pruefung_sicht_erholung + main)']
Abhaengig von: ['P1-buehne', 'P4-buero']

## Spezifikation
Owner of sicht.py, erholung.py, leistung.py and the camera principle text. Build on scratchpad/health_parse.py and vision_prototyp/.

A. sicht.py

SICHT_VERSION = '0.10.35'
SICHT_DATEIEN: name → (url, pinned hash or None, content type)
- vision_bundle.mjs: https://cdn.jsdelivr.net/npm/@mediapipe/tasks-vision@0.10.35/vision_bundle.mjs, 'sha384-Ll1OFMb+0geb9fpvYvxFbnpB/UjqBeQ2iVta6EtAGmIW2s0Oed/AhFDe+32PXnKs', text/javascript
- vision_wasm_internal.js: …@0.10.35/wasm/vision_wasm_internal.js, None, text/javascript
- vision_wasm_internal.wasm: …/wasm/vision_wasm_internal.wasm, None, application/wasm
- vision_wasm_nosimd_internal.js: …/wasm/vision_wasm_nosimd_internal.js, None, text/javascript
- vision_wasm_nosimd_internal.wasm: …/wasm/vision_wasm_nosimd_internal.wasm, None, application/wasm
- gesture_recognizer.task: https://storage.googleapis.com/mediapipe-models/gesture_recognizer/gesture_recognizer/float16/1/gesture_recognizer.task, 'sha256-97952348cf6a6a4915c2ea1496b4b37ebabc50cbbf80571435643c455f2b0482', application/octet-stream

sicht_ordner() -> Path
- config.MODELL_VERZEICHNIS / ('sicht-' + SICHT_VERSION)

sicht_laden(holen=None, melden=print) -> dict
For each file:
1. Download to a temp file; timeout 120 s; maximum 40 MB.
2. Verify the pinned hash: the sha384 SRI form is base64 of the digest, the sha256 form is hex. On mismatch, delete the file and report 'Die Datei X stimmt nicht mit der erwarteten Prüfsumme überein – nichts gespeichert.'
3. Files without a pinned hash: record their sha256 in pruefsummen.json (trust on first use). On a later download, compare against it.
4. Move into place atomically.
Returns {'ok', 'dateien', 'text': 'Die Handerkennung ist geladen (20,3 MB).'}

sicht_bereit() -> bool

sicht_datei(name) -> (bytes, typ) or (None, fehler)
- Whitelist only: no '/' and no '..'.
- Checks the stored sha256 once per process.
- Missing file: 'Die Handerkennung ist noch nicht geladen. Im Terminal: python3 jarvis.py sicht laden'

SCHEMA_HANDRUHE
- handruhe(id INTEGER PRIMARY KEY AUTOINCREMENT, tag TEXT, zeit TEXT, art TEXT, mm REAL, rauschen_mm REAL, rhythmus_hz REAL, spitze REAL, fps REAL, dauer_s REAL, bilder INTEGER, handlaenge_mm REAL)

class Handruhe(memory, anzeige=None)

messung_pruefen(daten) -> (dict or None, fehler)
Strict:
- Only the contract keys are read.
- art is 'ruhe' or 'halten'.
- Numbers must be finite, real float or int; strings and booleans are rejected.
- Ranges: mm 0..20; rauschen_mm null or 0..20; rhythmus_hz null or 3..14; spitze_verhaeltnis null or 0..1e6; fps 10..120; dauer_s 4..30; bilder 40..4000; handlaenge_mm 60..130.
- fps < 25: 'Mehr Licht, bitte – die Messung braucht mindestens 25 Bilder pro Sekunde.'

speichern(daten) -> dict
Text examples:
- 'Handruhe heute: 0,6 mm (Schätzung) – unruhiger als dein 14-Tage-Mittel von 0,4 mm. Kein deutlicher Rhythmus.'
- With a rhythm: 'Rhythmus um 8,5 Hz.'
- With a resting measurement today: 'Verhältnis zur Ruhemessung 1,8.'
- With fewer than 5 earlier halten measurements: 'Für einen Vergleich brauche ich noch ein paar Messungen.'
- Always ends with 'Selbstbeobachtung, kein Medizinprodukt.'
- Never uses the words Diagnose, Stress, Parkinson or Gesundheit.
Also:
- anzeige.melden('sicht', …) and anzeige.zeigen('sicht', {}, 120).
- One daily index via memory.kennzahl_setzen('handruhe_mm', mm, 'mm').

verlauf(tage=14)
stand() -> the contract shape of /api/sicht/stand

B. erholung.py

SCHEMA_ERHOLUNG
- erholung_tage(tag TEXT, quelle TEXT, wert REAL, hrv REAL, ruhepuls REAL, schlaf_h REAL, roh TEXT DEFAULT '{}', geholt TEXT, PRIMARY KEY(tag, quelle))

Apple Health constants
- HK_HRV = 'HKQuantityTypeIdentifierHeartRateVariabilitySDNN'
- HK_RUHEPULS = 'HKQuantityTypeIdentifierRestingHeartRate'
- HK_SCHLAF = 'HKCategoryTypeIdentifierSleepAnalysis'
- SCHLAF_WERTE = the five values Asleep, AsleepUnspecified, AsleepCore, AsleepDeep, AsleepREM. Awake and InBed are excluded.

apple_export_lesen(pfad, ab_tag) -> {tag: {'hrv': [...], 'ruhepuls': [...], 'schlaf': [(start, ende)]}}
- Accepts a .zip (reads apple_health_export/export.xml directly, without unpacking) or a .xml.
- ET.iterparse with events ('start', 'end'). Take the root from the first start event. After each Record: el.clear() and root.clear().
- Dates: strptime with '%Y-%m-%d %H:%M:%S %z'.
- HRV counts only for samples starting between 00:00 and 08:00 local time.
- A night belongs to the day of its endDate.
- Python 3.9-safe.

schlaf_stunden(intervalle)
- Merges overlapping intervals, so several sources are counted once.

erholung_schaetzen(tag, hrv_tage, puls_tage, schlaf_tage, basis_tage=30, ziel_schlaf=7.5) -> dict or None
- Baseline: the previous 30 days, excluding the day itself.
- Return None if there are fewer than 14 baseline days of HRV or of resting pulse, or no HRV that day.
- z_hrv on ln(HRV); z_puls = −(pulse − mean)/sd.
- Each part = clamp(50 + 20z, 0, 100).
- Sleep part = clamp(100·h/7.5, 0, 100).
- Score = 0.45 hrv + 0.30 pulse + 0.25 sleep. Without sleep data: 0.6 hrv + 0.4 pulse.
- band(wert): ≥ 67 gruen, 34..66 gelb, < 34 rot.
- Standard deviations are computed by hand.

class Erholung(memory, holen=None, uhr=None)

importieren(pfad)
- realpath must be inside the home folder and end in .zip or .xml, else 'Diese Datei lese ich nicht.'
- Larger than 300 MB: run in a background thread and report the result via ausgabe.
- Stores per day: quelle 'Apple Health (eigene Schätzung)'.

oura_holen(tage=14)
- Refresh the token: POST https://api.ouraring.com/oauth/token as form data, grant_type=refresh_token with refresh_token, client_id, client_secret.
- Store the new refresh token immediately via config.env_setzen('OURA_REFRESH_TOKEN', …).
- GET https://api.ouraring.com/v2/usercollection/daily_readiness?start_date=…&end_date=… → score.
- Also daily_sleep and sleep (average_hrv, total_sleep_duration/3600).
- quelle 'Oura (Readiness)'.
- On 429: honour Retry-After and fail softly.

whoop_holen(tage=14)
- Token endpoint: https://api.prod.whoop.com/oauth/oauth2/token
- GET https://api.prod.whoop.com/developer/v2/recovery?start=…&end=…&limit=25 → records[].score.recovery_score, resting_heart_rate, hrv_rmssd_milli.
- quelle 'Whoop (Recovery)'.
- Field names and pagination are marked 'zu prüfen'.

oauth_start(dienst, port=8765) -> {'url', 'zustand'}
- zustand: 24 random characters for Oura; exactly 8 for Whoop.
- Valid 10 minutes, single use.
- Oura authorize URL: https://cloud.ouraring.com/oauth/authorize?response_type=code&client_id=…&redirect_uri=http://localhost:8765/oura/rueckruf&scope=daily%20heartrate%20personal&state=…
- Whoop authorize URL: https://api.prod.whoop.com/oauth/oauth2/auth?…&scope=read:recovery%20read:sleep%20offline

oauth_abschluss(dienst, code, zustand)
- Wrong or used state: 'Die Anmeldung passt nicht zu der, die ich gestartet habe. Bitte noch einmal: python3 jarvis.py zugang oura'

oauth_im_terminal(dienst)
- Prints the URL, asks for the address the browser landed on, and parses code and state from it. This is the fallback when the provider rejects a localhost redirect.

manuell(tag, wert)

heute() -> {'ok', 'tag', 'wert', 'band', 'quelle', 'text'}
- Source order: Oura, Whoop, Apple Health, manual.
- Nothing found: {'ok': False, 'fehler': 'Es ist keine Erholungsquelle verbunden. Möglich: Apple-Health-Export (python3 jarvis.py gesundheit <Datei>), Oura oder Whoop (python3 jarvis.py zugang oura), oder du sagst mir den Wert.'}

vergessen()
- Deletes the rows of erholung_tage and handruhe.
- Used by the CLI 'gesundheit vergessen' after a yes typed in the terminal.

C. leistung.py

pearson(xs, ys) -> float or None
- Hand-written. None if n < 3 or a variance is 0.

verkaufstermin(titel, stichwoerter, firmen) -> bool

class Leistung(memory, kalender, erholung, call_analysis, vorschlaege=None, anzeige=None)

tage_zusammenstellen(tage=60) -> list of {tag, erholung, termine, verkaufstermine, gespraeche, gewonnen, quote}
- Calendar: kalender.termine(tage, ab=today − tage). Past days are allowed.
- Conversations: the gespraeche table, grouped by datum. quote = gewonnen / gespraeche, or None.

zusammenhang(tage=60) -> dict
- Buckets by band rot / gelb / gruen.
- Each bucket: tage, average termine, gespraeche, abschlussquote.
- r = pearson(erholung, quote) over days with at least 1 conversation.
- Text, always naming n: e.g. 'An 6 Tagen mit niedriger Erholung hast du 0 von 9 Gesprächen abgeschlossen, an 11 guten Tagen 6 von 14. Zusammenhang, keine Ursache.'
- Fewer than 10 days with both values, or any bucket with fewer than 3 days: '%d Tage – zu wenig für eine Aussage.'
- Display: sicht channel zusammenhang plus zeigen('sicht').

belastung_pruefen(heute=None) -> str
A proposal is made only when ALL of these hold:
- today's erholung wert < config.BELASTUNG_SCHWELLE;
- tomorrow has ≥ config.BELASTUNG_MIN_TERMINE appointments;
- the zusammenhang has at least 5 days each in the rot and gruen buckets, and the rot close rate is lower than the gruen close rate by at least 0.15.
Then it calls vorschlaege.einbringen('belastung:' + tag, text, 'erholung').
Text: 'Deine Erholung liegt heute bei 28 von 100. Morgen hast du 5 Termine, davon 3 Verkaufstermine. An Tagen mit so niedriger Erholung hast du bisher 0 von 9 Gesprächen abgeschlossen. Soll ich morgen zwei Termine verschieben oder absagen? Welche, sage ich dir vorher.'
Returns the text, or '' when there is nothing to propose. Never acts on its own.

D. Tools (catalog section '# -- Erholung und Sicht --'). None needs approval.

erholung_lesen
- Description: 'Erholungswert heute und der letzten Tage aus dem verbundenen Wearable oder dem Apple-Health-Export, mit Quelle. Zeigt ihn auf der Zentrale. Kein Medizinprodukt.'
- Schema: {'tage': ganz}

erholung_eintragen
- Description: 'Trägt einen Erholungswert (0 bis 100) von Hand ein, etwa aus der Oura- oder Whoop-App.'
- Schema: {'wert': zahl, 'tag': text}; required wert.

erholung_abrufen
- Description: 'Holt die neuesten Werte von Oura oder Whoop.'
- Schema: {'dienst': {'type': 'string', 'enum': ['oura', 'whoop']}}; required.
- Fixed URLs, so it is not NETZ_SENDEND.

gesundheit_importieren
- Description: 'Liest einen Apple-Health-Export (export.zip oder export.xml) aus dem Benutzerordner und berechnet die Erholung je Tag.'
- Schema: {'pfad': text}; required.

handruhe_verlauf
- Description: 'Die gespeicherten Handruhe-Messungen der letzten Tage. Selbstbeobachtung, kein Medizinprodukt.'
- Schema: {'tage': ganz}

leistung_zusammenhang
- Description: 'Wie Erholung, Terminlast und Abschlussquote zusammenhängen, mit Fallzahlen. Zusammenhang, keine Ursache.'
- Schema: {'tage': ganz}

belastung_pruefen
- Description: 'Prüft jetzt, ob der morgige Tag bei der heutigen Erholung zu voll ist, und schlägt gegebenenfalls Entlastung vor. Ändert selbst nichts.'
- Schema: {}

__init__
- self.erholung = Erholung(self.memory)
- self.handruhe = Handruhe(self.memory, anzeige=self.anzeige)
- self.leistung = Leistung(self.memory, self.kalender, self.erholung, self.call_analysis, vorschlaege=getattr(self, 'vorschlaege', None), anzeige=self.anzeige)

umschauen description
- 'Nimmt ein Einzelbild der Kamera auf und beschreibt, was zu sehen ist. Kein Dauervideo auf dem Server; das Live-Bild gibt es nur auf der Seite Sicht im Browser.'

E. webapp.py

ANZEIGE_PFADE
- Add '/api/sicht/stand' and '/api/sicht/verlauf'.

New constant
- ANZEIGE_PRAEFIXE = ('/sicht/dateien/',)
- _behandeln lets a path through on the display server when it is in ANZEIGE_PFADE or starts with an ANZEIGE_PRAEFIXE entry.

GET /sicht/dateien/<name>
- sicht_datei(name) → bytes with its content type and zusatz {'Cache-Control': 'max-age=31536000, immutable'}.
- Error → 404 with the JSON fehler.

GET /api/sicht/stand
GET /api/sicht/verlauf?tage=14

POST /api/sicht/messung
- Content-Length > 2048 → 400 'Zu viele Daten.'
- messung_pruefen; error → 400 {'fehler'}.
- Success → 200 speichern(...).

GET /oura/rueckruf?code&state and GET /whoop/rueckruf?code&state
- These are the only GET routes that change state. They are protected by the single-use state.
- Response: an HTML page 'Oura ist verbunden. Du kannst dieses Fenster schließen.', or the error text.
- Not in ANZEIGE_PFADE.

F. Other shared edits

camera.py docstring, replacing lines 7-9
- 'Der Server nimmt nur Einzelbilder auf (umschauen, Belege). Ein Live-Bild gibt es nur im Browser auf der Seite Sicht, nur nach Einschalten (SICHT_AN), es verlässt den Browser nie und wird nicht aufgezeichnet; gespeichert werden nur Messzahlen.'

scheduler.py, standardjobs_anlegen
- if config.BELASTUNG_PRUEFEN_UM and getattr(getattr(self.agent, 'tools', None), 'leistung', None): self.job_anlegen('belastung', config.BELASTUNG_PRUEFEN_UM, lambda: self.agent.tools.leistung.belastung_pruefen(), 'Belastung für morgen prüfen')
- An empty return means the scheduler stays silent. This must be checked against Scheduler._ausfuehren: an empty string must not be sent to the ausgabe.

agent.py, _bausteine_sammeln, morning only
- e = self.tools.erholung.heute()
- if e.get('ok'): teile.append('Erholung: %s' % e['text'])

run.py CLI
- 'sicht laden' → sicht_laden()
- 'sicht an' / 'sicht aus' → config.env_setzen('SICHT_AN', 'ja' / 'nein')
- 'gesundheit <pfad>' → importieren
- 'gesundheit vergessen' → asks 'Alle Erholungs- und Handruhe-Werte löschen? (ja/nein)', then vergessen()
- 'zugang oura' / 'zugang whoop' → erholung.oauth_im_terminal(dienst), handled before zugang_eintragen.

config.py
- MODELL_VERZEICHNIS = BASIS / 'modelle' (a path constant)
- SICHT_AN = _wahrheit('SICHT_AN', False)
- HANDLAENGE_MM = _zahl('HANDLAENGE_MM', 95)
- OURA_CLIENT_ID, OURA_CLIENT_SECRET, OURA_REFRESH_TOKEN: _text
- WHOOP_CLIENT_ID, WHOOP_CLIENT_SECRET, WHOOP_REFRESH_TOKEN: _text
- VERKAUFS_STICHWOERTER = _text('VERKAUFS_STICHWOERTER', 'besichtigung,angebot,erstgespräch,beratung,vor ort,akquise,objektbegehung')
- BELASTUNG_SCHWELLE = _ganzzahl('BELASTUNG_SCHWELLE', 34)
- BELASTUNG_MIN_TERMINE = _ganzzahl('BELASTUNG_MIN_TERMINE', 4)
- BELASTUNG_PRUEFEN_UM = _text('BELASTUNG_PRUEFEN_UM', '18:25')
- konfig_uebersicht gets 'Wearable': bool(OURA_REFRESH_TOKEN or WHOOP_REFRESH_TOKEN)

build_single.py
- 'modules/erholung', 'modules/sicht', 'modules/leistung' directly after 'modules/camera'.

## Tests
New function pruefung_sicht_erholung(agent). All files go to ARBEITSVERZEICHNIS. config.env_setzen is monkeypatched so the real config/.env is never written.

Apple Health import
1. A synthetic export.zip is built in the test with zipfile, holding apple_health_export/export.xml with a <!DOCTYPE HealthData [...]> block and:
   - HRV samples at 03:00 and at 14:00 (only 03:00 counts);
   - resting heart rate;
   - sleep records from two sources overlapping 23:00-06:30 (merged to 7.5 h, counted on the wake day);
   - Awake and InBed records (excluded).
   apple_export_lesen returns the expected per-day values.

erholung_schaetzen
2. 10 baseline days → None.
3. 30 normal days → 50 ± 15.
4. A day with low HRV, pulse +8 and 4 h sleep → < 34, band 'rot'.

Oura
5. With a fake holen: the token endpoint returns a new refresh_token → the monkeypatched env_setzen is called with OURA_REFRESH_TOKEN. The daily_readiness JSON in the sandbox shape (data: [{day, score: 80}]) is stored with quelle 'Oura (Readiness)'.

OAuth state
6. oauth_abschluss with the wrong state → ok False, with 'passt nicht'.
7. A reused state → rejected.
8. An expired state (fake clock +11 min) → rejected.
9. Web route /oura/rueckruf on nur_anzeige → 404.

Handruhe.messung_pruefen
10. Rejects: mm '0.5' (a string), mm NaN, mm 50, fps 5, bilder true, a missing art.
11. Ignores extra keys and accepts a valid payload.
12. speichern text contains 'Schätzung' and 'kein Medizinprodukt', and none of Diagnose, Stress, Parkinson.
13. After 5 earlier measurements the text contains '14-Tage-Mittel'.
14. The fake anzeige receives the sicht channel.

HTTP
15. POST /api/sicht/messung with a 3 KB body → 400; with a valid body → 200.
16. GET /api/sicht/stand works on the nur_anzeige server (200).

sicht_datei
17. sicht_datei('../config/.env') → None.
18. A missing file → the message contains 'python3 jarvis.py sicht laden'.
19. GET /sicht/dateien/vision_bundle.mjs on the display server, when the file exists in a temp MODELL_VERZEICHNIS → 200 with Content-Type text/javascript.

sicht_laden with a fake holen
20. Model bytes with the wrong sha256 → refused, and no file written.
21. The correct bytes are written. The test computes the pinned hash for its fake bytes by monkeypatching SICHT_DATEIEN.
22. The SRI sha384 check works.
23. Unpinned files are recorded in pruefsummen.json, and a changed second download is refused.

Leistung
24. pearson([1,2,3],[2,4,6]) == 1.0; n < 3 → None; constant input → None.
25. zusammenhang on a monkeypatched tage_zusammenstellen:
   - 4 days → text contains 'zu wenig';
   - 30 days → buckets with tage counts, and the text contains 'keine Ursache'.
26. belastung_pruefen with a fake erholung (28), a fake kalender (5 appointments tomorrow, 3 with 'Besichtigung') and a fake zusammenhang (rot 0/9 over 6 days, gruen 6/14 over 11 days) → the text contains 'Soll ich' and vorschlaege.einbringen was called once.
27. A second call the same day → no new proposal.
28. No erholung data → '' and no proposal.

Other
29. The umschauen description contains 'Kein Dauervideo auf dem Server'.
30. erholung.heute() without any data → the fehler names 'Apple-Health-Export' and 'Oura'.
