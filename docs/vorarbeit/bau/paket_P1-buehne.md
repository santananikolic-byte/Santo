# P1-buehne Bühne: Anzeige-Vertrag, Zentrale mit Themenwechsel und Regionen-Globus, Märkte-/Kennzahlen-/Anruf-/Sicht-/Untertitel-/Boot-Ansichten, Partikel-Orb, Kamera-Seite /sehen

Anwendungsfaelle: ['1 (Boot-Animation)', '3 (Anzeige-Layouts)', '8 (Untertitel)', '9', '10', '11 (Kamera, 21 Punkte, Handruhe, Orb im Browser)', '12 (Telefon-HUD)', 'Video 1', 'Video 2', 'Video 3']
Neue Dateien: ['src/modules/anzeige.py', 'src/modules/weltkarte.py', 'src/modules/sehen.py', 'tools/landmaske_bauen.py']
Geaenderte Dateien: ['src/modules/ansicht.py (owner)', 'src/modules/webseite.py (owner)', 'src/modules/webapp.py (routes, header helpers)', 'src/modules/tools.py (anzeige instance + tool anzeige_zeigen)', 'src/agent.py (system prompt line)', 'src/config.py (ANZEIGE_DAUER)', 'config/.env.beispiel', 'build_single.py (BAULISTE)', 'tests/abnahme.py (pruefung_buehne + main)']
Abhaengig von: []

## Spezifikation
Implements the anzeige_vertrag exactly. Every page uses inline CSS and JS only, and contains no http:// or https:// except the SVG namespace.

A. src/modules/anzeige.py
- Imports: stdlib json, threading, time; import config.

class Anzeige
- __init__(self, uhr=None) sets:
  - self._uhr = uhr or time.time
  - self._bed = threading.Condition()
  - self._k = {k: {'version':0,'daten':{},'seit':0.0,'bis':0.0} for k in KANAELE}
  - self._letzte = {}
  - self.start = self._uhr()

melden
- Validate the channel, then isinstance(daten, dict).
- roh = json.dumps(daten, ensure_ascii=False, default=str). Catch TypeError/ValueError → -1.
- If len(roh.encode('utf-8')) > 65536 → -1.
- Store json.loads(roh) as a deep copy.
- version += 1, then notify_all.

zeigen
- See the contract.

warten(nach, timeout)
- deadline = uhr() + timeout. Under the lock, loop:
  - geaendert = {k: self._stand(k) for k in nach if k in self._k and self._k[k]['version'] != nach[k]}
  - If geaendert is non-empty, or the remaining time ≤ 0, return it.
  - Otherwise self._bed.wait(remaining).
- The test injects a fake clock (uhr) but uses real waits.

kurz
- See the contract.

Module functions
- anzeige_nach_lesen(text)
- diskret_filtern(kanal, daten) per contract section 5.
- Names must be unique project-wide; every top-level name in this module is.

B. ansicht.py

1. status_daten adds 'anzeige': tools.anzeige.kurz() if getattr(tools, 'anzeige', None) else {}.

2. New kennzahlen_kacheln(tools) -> list, built from zentrale_daten(tools). A tile is added only when its value is a real number:
- 'Ergebnis Monat' (€): ziel = bedarf.gewinn if bedarf is berechenbar; farbe 'gut' if ≥ 0, else 'schlecht'; text '41 % vom Bedarf'.
- 'Einnahmen Monat' (€).
- 'Ausgaben Monat' (€).
- 'Zahllast' (€).
- 'Belegquote' (%, ziel 100).
- 'Pipeline gewichtet' (€).
- 'Gesichert je Monat' (€).
- 'Nötiger Umsatz' (€, only if bedarf is berechenbar).

3. SEITE_ZENTRALE
Stage structure:
- The middle column becomes <div class='buehne' id='buehne' data-modus='uebersicht'>.
- Inside it: the existing #globus canvas, plus one <section class='lage' data-lage='X'> per non-globe modus.
- CSS crossfade: opacity transition 0.4 s, removed under prefers-reduced-motion.
- In modes other than uebersicht, globus and a globus step of folge, the canvas fades to 25 % as background.

JS: lauschen()
- One long-poll: /api/anzeige?nach=<all six channels>&warten=20 plus ANHANG.
- Versions start at -1. If start changes, reset them.
- Compute offset from jetzt.
- On error, retry after 3 s.
- Expiry: if a stand has bis > 0, return to uebersicht at bis on the server clock (via offset).

Globe camera
- Pure functions go in a block delimited by '// <rechnen-zentrale>' and '// </rechnen-zentrale>' (extracted by node in the tests):
  - lonWeg(a, b): signed shortest longitude delta in (-180, 180].
  - easeInOut(p): cubic.
  - flugZoom(z0, z1, winkelGrad, p) = 2^(lerp(log2 z0, log2 z1, p) - 0.9*sin(PI*p)*min(1, winkelGrad/90)), clamped to 1..6.
  - kugelLerp(a, b, p): slerp over unit vectors from lat/lon.
- A fly-to lasts 1800 ms; under reduced motion it jumps.
- In uebersicht mode the globe behaves exactly as today: home focus and customer markers from d.orte.

Land dots
- Fetch /api/weltkarte once and decode the RLE into a Uint8Array of 1440×720.
- Build three point sets at steps of 4, 2 and 1 cells (1°, 0.5°, 0.25°). Each is a Float32Array of [sinLat, cosLat, lonRad], grouped by row with row-start offsets.
- Choose the set by zoom: below 1.6 → step 4; below 3 → step 2; otherwise step 1.
- Per frame, iterate only the rows within fokusLat ± (deg(asin(min(1, hypot(GW,GH)/(2R)))) + 3).
- Cull points where sicht < 0.02 or that fall off screen.
- Dot size: clamp(R/300 * step, 1.2, 3.6).
- If /api/weltkarte fails or rle is empty, use the old LAND/MEER polygons.

Globe HUD (globus mode)
- Corner brackets and crosshair at the focus.
- Coordinate line '32,4° N · 53,7° O · ZOOM 3,6×'.
- titel at top-left, stand at bottom-left.
- 'liste' as a right-hand overlay: 'HH:MM · quelle · titel'.
- News marker: diamond with a pulsing cyan ring (#9fe7ff) and a label of up to 42 characters with ellipsis. Labels avoid overlaps.
- boegen: dashed great circles, 32 slerp segments, animated dash offset, only visible segments drawn.

maerkte layer
- Grid of cards: grid-template-columns repeat(auto-fill, minmax(200px, 1fr)).
- Each card: name; wert as de-DE with 2 decimals, or 0 decimals if ≥ 1000, or 4 for eurusd; einheit; change with sign, green if ≥ 0, red if < 0, '–' if null; SVG sparkline (area plus line, as in verlauf()); HH:MM.
- Footer: stand, plus 'Nicht abrufbar: …' for anything in fehlend.
- Empty kurse → 'Kursdaten gerade nicht verfügbar'.

kennzahlen layer
- ring() when the tile has a ziel, otherwise a large number.
- Colour by farbe.
- Without kacheln, build them from the last zentrale data.

anruf layer: phone HUD
- Left side: ziel; nummer; phase chip.
  - waehlt: 3 expanding rings.
  - klingelt: 1 Hz pulse.
  - verbunden: green dot plus an mm:ss timer from beginn (via offset).
  - beendet / fehler: grey.
- Right side: transcript bubbles. jarvis on the right in orange, gegenueber on the left in white. Auto-scroll.
- If not mitschrift_live and phase is verbunden: 'Die Mitschrift kommt bei diesem Anbieter erst nach dem Gespräch.'
- After the end with mitschrift_live false, the transcript header reads 'Mitschrift nach Gesprächsende'.
- Result card:
  - Success: '✓ Reserviert: Do, 09.10. · 19:30 · 2 Personen · auf <Name>'.
  - Otherwise: '✕ Nicht reserviert', plus the gegenvorschlag.
  - Also shows grund_ende and '≈ 0,42 $'.

sicht layer
- Erholung: ring with band colour, quelle, tag.
- Handruhe: mm with 1 decimal, vergleich, small fps and noise line.
- Zusammenhang: table stufe / tage / termine / abschlussquote (or '–'), n, text.
- Footnote hinweis. A missing part shows 'Noch keine Daten'.

Other layers
- untertitel: original small with the language code, uebersetzung very large; keep the last 4 locally.
- hochfahren: steps appear one per 250 ms with ✓/✕/–, then the greeting is typed at 30 characters/s (all at once under reduced motion).
- recherche: titel, absaetze, liste, quellen. Sources show as text with the host only, no links.
- inhalte: table datum · plattform · titel · status.
- folge: per the contract.

Performance
- Target ≥ 50 fps at zoom 6 on the iMac.
- ?debug=1 shows fps and the point count.

4. SEITE_GEHIRN

?form=kugel
- Replaces the brain cloud with a Fibonacci sphere of 2600 particles, using the same glutBild, drehen and abbilden.
- No knowledge nodes; labels hidden.

Level P (0..1)
- Smoothing per frame: rise ×0.5, fall ×0.12.
- Sources, in priority order:
  a) postMessage {pegel} seen within the last 300 ms. Label 'Pegel: echt'.
  b) stimme channel envelope through its own long-poll. Only when not embedded, or when a) has been silent for 5 s. Label 'Pegel: echt'.
  c) postMessage {sprechen}: base 0.25 while speaking; each 'wort' adds an impulse of +0.6 that decays with τ = 120 ms. Label 'Pegel: nachempfunden'.
  d) zustand 'spricht' → 0.3 + 0.15·sin(2π·2.2·t). Label 'Pegel: nachempfunden'.
- Effects on the sphere: radius ×(1 + 0.22P), particle jitter ×(1 + 3P), glow alpha 0.35 + 0.6P.
- The brain form also uses P: scale ×(1 + 0.06P).
- postMessage is accepted only from location.origin, and only the keys zustand, pegel and sprechen with valid types.
- The label is shown only when not embedded.

5. webseite.py (main page)

Header
- Ticker links to /sehen ('Sicht') and /dolmetscher ('Dolmetscher'), passed through url().

Server voice
- If /api/zustand.stimme_im_browser is true, use sprichServer(liste, danach):
  - Per chunk: POST /api/sprache {text: chunk, sprache: 'de'} → blob → objectURL. Prefetch the next chunk while the current one plays.
  - One <audio id='ton'>. The AudioContext is created on the first click, keydown or touch.
  - createMediaElementSource once → AnalyserNode (fftSize 512) → destination.
  - A rAF loop computes the RMS of getFloatTimeDomainData, pegel = min(1, rms·4), posted to the hirn iframe.
- On any non-200, fetch error or play() NotAllowedError, the remaining chunks fall back to the existing speechSynthesis path.
- On NotAllowedError, show the 'Ton einschalten' button once.
- Keep hoerenPause, hoerenWeiter and the safety timeout.

speechSynthesis path
- onstart → postMessage {sprechen: 'start'}; onboundary → 'wort'; end → 'ende'.

Both paths
- At the start of every chunk, fire-and-forget POST /api/anzeige/satz {text: chunk}.

Approval dialog
- Three rows: Was / Warum / Wie, falling back to details.
- details sits in a collapsible <details>.
- Spoken prompt: 'Ich brauche eine Freigabe. ' + was + '. Grund: ' + warum + '. Ja oder nein?'
- Buttons send kanal 'klick'; a voice yes/no sends kanal 'sprache'.

Boot
- POST /api/hochfahren {} once per page load.
- If neu: overlay #hochfahren ticks the steps in, then speaks the greeting (via sprechstuecke).
- 404 → do nothing.

Call overlay
- Long-poll anruf only.
- While the phase is waehlt, klingelt or verbunden, a compact overlay shows ziel, phase, timer and the last 3 transcript lines, plus a button 'Auflegen' → POST /api/werkzeug {name: 'anruf_beenden'}.
- After the end, show the result for 20 s.

6. src/modules/sehen.py
Constants
- SEITE_SEHEN with a {{SCHLUESSEL}} placeholder. Imports BASIS_STIL from modules.ansicht.
- SEHEN_CSP = "default-src 'self'; script-src 'self' 'unsafe-inline' 'wasm-unsafe-eval'; connect-src 'self'; img-src 'self' data: blob:; media-src 'self' blob: mediastream:; worker-src 'self' blob:; style-src 'self' 'unsafe-inline'; frame-src 'self'; object-src 'none'; base-uri 'none'"
- SEHEN_ERLAUBNIS = 'camera=(self), microphone=()'

Start panel
- GET /api/sicht/stand, then show the first message that applies:
  - not an → 'Die Live-Kamera ist ausgeschaltet. Einschalten: python3 jarvis.py sicht an'
  - not dateien_da → 'Die Handerkennung ist noch nicht geladen. Einmal im Terminal: python3 jarvis.py sicht laden (etwa 20 MB, von jsDelivr und Google).'
  - not isSecureContext, or no navigator.mediaDevices → 'Die Kamera geht nur direkt am Mac (localhost), nicht über das WLAN.'
  - otherwise: button 'Kamera einschalten' and the sentence 'Das Bild bleibt in diesem Browser. Gespeichert werden nur Messzahlen, nie ein Bild.'

getUserMedia
- Constraints: {video: {width: {ideal: 1280}, height: {ideal: 720}, frameRate: {ideal: 60}}, audio: false}.
- Error messages:
  - NotAllowedError: 'Der Browser oder macOS lässt mich nicht an die Kamera (Systemeinstellungen > Datenschutz & Sicherheit > Kamera).'
  - NotFoundError: 'Ich finde keine Kamera.'
  - NotReadableError: 'Die Kamera wird gerade von einem anderen Programm benutzt.'
  - OverconstrainedError: 'Die Kamera kann dieses Format nicht.'
  - SecurityError: 'Diese Adresse ist nicht sicher genug für die Kamera.'

Model
- const {FilesetResolver, GestureRecognizer} = await import('/sicht/dateien/vision_bundle.mjs')
- FilesetResolver.forVisionTasks(location.origin + '/sicht/dateien')
- Options: runningMode 'VIDEO'; numHands 1; minHandDetectionConfidence, minHandPresenceConfidence and minTrackingConfidence all 0.6; baseOptions {modelAssetPath: '/sicht/dateien/gesture_recognizer.task', delegate: 'GPU'}, falling back to 'CPU'.
- On a 'securitypolicyviolation' event: 'Der Sicherheitskopf blockiert die Handerkennung (' + violatedDirective + ').'

Frame loop
- requestVideoFrameCallback, falling back to rAF with a currentTime check.
- Detector timestamp = max(performance.now(), last + 1).
- HUD: fps from frame times, processing time in ms, 'HAND ERKANNT · 21 PUNKTE'.

Overlay
- Mirrored with scaleX(-1), the same as the video.
- 21 points; connections [[0,1],[1,2],[2,3],[3,4],[0,5],[5,6],[6,7],[7,8],[5,9],[9,10],[10,11],[11,12],[9,13],[13,14],[14,15],[15,16],[13,17],[0,17],[17,18],[18,19],[19,20]].
- Fingertips 4, 8, 12, 16, 20 glow larger.

Handruhe: pure function handruhe(proben, handlaengeMm)
- Lives in a block delimited by '// <rechnen>' and '// </rechnen>'.
- proben: [{t (ms), x, y, ok}]. x and y are the mean of tips 4, 8, 12, 16, 20 in px, divided by the palm length |0→9| in px.
- Frames where the hand is missing, or the palm is shorter than 8 % of the video height, have ok = false.
- Reject when fewer than 85 % of frames are valid, or when fps < 25: {ok: false, grund: 'Mehr Licht, bitte – die Kamera liefert nur N Bilder pro Sekunde.'}
- Steps:
  1. Resample linearly to 30 Hz.
  2. High-pass: subtract a 9-sample moving average on each axis.
  3. rms = sqrt(mean(dx² + dy²)); mm = rms · handlaengeMm.
  4. Apply a Hann window, then a DFT from 3 to 14 Hz in 0.25 Hz steps.
  5. verhaeltnis = peak power / median power; rhythmus_hz = the peak frequency if verhaeltnis > 20, else null.
- Returns {ok, mm, rhythmus_hz, spitze_verhaeltnis, fps, bilder, dauer_s}.
- Buttons: 'Ruhemessung (Hand flach auf den Tisch, 8 s)' and 'Haltemessung (Arm ausgestreckt, 8 s)'.
- POST /api/sicht/messung and show the text that comes back.
- 14-day chart from /api/sicht/verlauf.

Thumbs-up: in the same rechnen block, istDaumenHoch(hand, geste, streng) and daumenSchritt(zustand, t, hand, geste)
P = palm length |0→9|. Thresholds give an enter value and a looser stay value:
- Thumb extended: |2→4| > 0.55P.
- Thumb ordered upward: y4 < y3 < y2.
- Angle of 2→4 from vertical: < 35° to enter, < 50° to stay.
- Thumb tip highest: y4 < min(other y) − 0.15P to enter, − 0.05P to stay.
- Four fingers curled, for (6,8), (10,12), (14,16), (18,20): dist(tip, wrist) < dist(pip, wrist) to enter, < 1.1× to stay.
- Model says Thumb_Up: score > 0.7 to enter, > 0.5 to stay.
Timing:
- Hold 1500 ms continuously; gaps of up to 120 ms are tolerated.
- Armed only after 500 ms without a thumb.
- 3000 ms lockout after firing.
- Thumb_Down with score > 0.7, held 800 ms, means no.
When it is active:
- Only if GET /api/freigaben (polled every 1 s) returns exactly ONE entry with geste_erlaubt true,
- and that entry's card (was / warum / wie / rest) is rendered,
- and document.visibilityState is 'visible'.
Action:
- POST /api/freigabe {id, ja, kanal: 'geste'} and show the server text.
- A progress ring while holding.

Orb and privacy
- Orb iframe: url('/gehirn?eingebettet=1&form=kugel').
- No toDataURL, toBlob, MediaRecorder, getImageData or captureStream anywhere.
- On pagehide, or visibilitychange to hidden: stop all tracks and call erkenner.close().
- Red indicator '● Kamera an' with an 'Aus' button.
- Footnote: 'Selbstbeobachtung, kein Medizinprodukt. Eine Webcam sieht nur Bewegungen ab etwa einem halben Millimeter.'

7. src/modules/weltkarte.py
- LANDMASKE_BREITE = 1440, LANDMASKE_HOEHE = 720.
- LANDMASKE_QUELLE = 'Natural Earth 110m (world-atlas@2 land-110m.json, gemeinfrei)'.
- LANDMASKE_RLE: rows run north to south (row i centre latitude = 90 − (i + 0.5)·0.25). Columns run west to east (column j centre longitude = −180 + (j + 0.5)·0.25). Each row is base-36 run lengths separated by commas, starting with water. Rows are joined with ';'.
- def landmaske_dekodieren(rle) -> bytearray.

8. tools/landmaske_bauen.py
- Not in BAULISTE. Stdlib only. Run once; commit the output.
- Input: https://cdn.jsdelivr.net/npm/world-atlas@2/land-110m.json, or a local path argument.
- Decode the TopoJSON:
  - transform scale and translate;
  - delta-decoded arcs;
  - a negative arc index means ~i, reversed;
  - the objects.land MultiPolygon.
- Rasterise each row with scanline even-odd crossings at cell centres.
- Write src/modules/weltkarte.py. Target size ≤ 120 KB.

9. webapp.py (exact edits)
Imports
- from modules.anzeige import anzeige_nach_lesen
- from modules.sehen import SEITE_SEHEN, SEHEN_CSP, SEHEN_ERLAUBNIS
- from modules.weltkarte import LANDMASKE_BREITE, LANDMASKE_HOEHE, LANDMASKE_RLE

ANZEIGE_PFADE
- Add '/api/anzeige', '/api/weltkarte', '/sehen'.

Helpers
- _kopf_setzen(behandler, code, typ, laenge, zusatz=None): zusatz may override Cache-Control and add headers.
- _html(self, behandler, text, zusatz=None).

_get
- Starts with frage = parse_qs(urlparse(behandler.path).query).
- '/api/anzeige': warten = clamp(float(frage.get('warten', ['20'])[0]), 0, 25), falling back to 20 on ValueError. Response {'ok': True, 'jetzt': time.time(), 'start': werkzeuge.anzeige.start, 'kanaele': werkzeuge.anzeige.warten(anzeige_nach_lesen(frage.get('nach', [''])[0]), warten)}.
- '/api/weltkarte': as in the contract, with zusatz {'Cache-Control': 'max-age=86400'}.
- '/sehen': SEITE_SEHEN with the key replaced, zusatz {'Content-Security-Policy': SEHEN_CSP, 'Permissions-Policy': SEHEN_ERLAUBNIS}.

_post
- '/api/anzeige/satz': as in the contract.

10. tools.py
Imports
- from modules.anzeige import Anzeige
- from modules.ansicht import kennzahlen_kacheln

__init__
- self.anzeige = Anzeige() directly after self.memory = Memory(db_pfad).

Catalog
- Append section '# -- Anzeige --' at the end of eigene, before MCP:
  werkzeug('anzeige_zeigen', 'Schaltet die große Anzeige (Zentrale) um: uebersicht (Betrieb), kennzahlen (Kacheln aus Kasse, Bedarf, Pipeline, Belegquote), globus (Erde) oder zurück zu einer zuletzt gezeigten Ansicht (maerkte, anruf, sicht, untertitel, recherche, inhalte). Ändert nur die Anzeige.', {'modus': {'type': 'string', 'enum': ['uebersicht', 'kennzahlen', 'globus', 'maerkte', 'anruf', 'sicht', 'untertitel', 'recherche', 'inhalte']}, 'sekunden': ganz}, ['modus'])

Dispatch
- if name == 'anzeige_zeigen': return self.anzeige_umschalten(a.get('modus', ''), a.get('sekunden'))

New method anzeige_umschalten
- Clamp sekunden to 10..1800.
- kennzahlen → zeigen('kennzahlen', {'titel': 'Betrieb', 'kacheln': kennzahlen_kacheln(self)}).
- uebersicht or globus → zeigen(modus, {}).
- Any other mode → re-show letzte(modus). If there is none: {'ok': False, 'fehler': 'Dazu habe ich noch nichts gezeigt. Frag mich zuerst danach, dann kann ich es zurückholen.'}
- Success text: 'Die Zentrale zeigt jetzt <Name>.'
- The tool is in none of the three sets.

11. agent.py
- SYSTEMPROMPT gets a new line after '- Ging etwas schief, sagst du es. Du erfindest keine Ergebnisse.':
  '- Die große Anzeige folgt deinen Werkzeugen: weltlage zeigt den Globus, maerkte die Kurse, ein Anruf das Telefon. Mit anzeige_zeigen schaltest du um, etwa auf die Kennzahlen. Sag nie, dass etwas angezeigt wird, wenn das Werkzeug einen Fehler gemeldet hat.'

12. config.py
- ANZEIGE_DAUER = _ganzzahl('ANZEIGE_DAUER', 180)
- Plus a line in config/.env.beispiel.

13. build_single.py
- 'modules/anzeige' directly after 'modules/sprechtext'.
- 'modules/weltkarte' directly before 'modules/ansicht'.
- 'modules/sehen' directly after 'modules/webseite'.

## Tests
New function pruefung_buehne(agent) in tests/abnahme.py, called in main() before pruefung_einzeldatei.

Anzeige store
1. melden returns 1, then 2. stand('buehne')['version'] == 2.
2. warten({'buehne': 0}, 5) returns at once.
3. warten({'buehne': 2}, 0.3) returns {} after ≥ 0.25 s.
4. A thread that calls melden after 0.1 s wakes warten({'buehne': 2}, 5) in under 1 s.
5. zeigen('quatsch') → ok False, with 'gibt es nicht' in fehler.
6. A payload of 70 KB → ok False.
7. A non-dict payload → -1.
8. Expiry with a fake clock: zeigen('globus', {}, dauer_s=10), then advance the clock by 11 → kurz()['modus'] == 'uebersicht'.
9. With config.ANZEIGE_DISKRET = True, melden('anruf', {'nummer': '+43…', 'mitschrift': [{'wer': 'jarvis', 'text': 'x'}]}) → stand shows nummer '' and text ''. Restore the flag afterwards.
10. anzeige_nach_lesen('buehne:7,anruf:x,foo:3') == {'buehne': 7, 'anruf': -1}.

Tool anzeige_zeigen
11. tools.run('anzeige_zeigen', {'modus': 'kennzahlen'}) → ok True, buehne modus 'kennzahlen', every tile's wert is int or float.
12. tools.run('anzeige_zeigen', {'modus': 'maerkte'}) on a fresh Anzeige → ok False, with 'noch nichts gezeigt'.
13. status_daten(...) has the key 'anzeige'.

Pages
14. SEITE_ZENTRALE, SEITE_GEHIRN and SEITE_SEHEN: with the SVG namespace removed, no 'http://' and no 'https://'. Each contains {{SCHLUESSEL}}, requestAnimationFrame and prefers-reduced-motion.
15. SEITE_SEHEN contains none of: toDataURL, toBlob, MediaRecorder, getImageData, captureStream, jsdelivr, googleapis.
16. SEITE_SEHEN contains isSecureContext, NotAllowedError, '/sicht/dateien/gesture_recognizer.task' and "kanal:'geste'" (or the equivalent).
17. The Gehirn page checks e.origin and accepts the pegel and sprechen keys.

Real HTTP on a free port
18. GET /sehen: the Content-Security-Policy header contains "connect-src 'self'" and Permissions-Policy is present.
19. GET /api/anzeige?nach=buehne:-1&warten=0 → kanaele has buehne.
20. GET /api/weltkarte → breite 1440.
21. POST /api/anzeige/satz {'text': 'Iran'} → the stimme version increases.

Dienst display (nur_anzeige=True, via the fake-request pattern from :1604)
22. /api/anzeige, /sehen and /api/weltkarte → 200.
23. POST /api/anzeige/satz → 404.

node checks (only when node is installed)
24. Evaluate the rechnen-zentrale block:
   - lonWeg(170, -170) == 20 and lonWeg(-170, 170) == -20.
   - flugZoom(1, 4, 120, 0.5) < 2.
   - flugZoom stays within 1..6 for 50 random inputs.
25. Evaluate the SEITE_SEHEN rechnen block with synthetic samples (30 fps, 8 s, 10 Hz sine of 0.3 mm with palm 95 mm, plus 0.05 mm noise):
   - ok; rhythmus_hz within 10 ± 0.5; mm between 0.15 and 0.35.
   - Same at 15 fps → ok false, with 'Mehr Licht' in grund.
26. Synthetic thumbs-up hand:
   - not fired after 1400 ms, fired after 1700 ms;
   - not fired when the thumb was already up at arming time.

welt map
27. If LANDMASKE_RLE is not empty, landmaske_dekodieren gives 720 rows that each sum to 1440, and:
   - Wien (48.2, 16.37) = land;
   - (40, −30) Atlantic = water;
   - (0, −150) = water;
   - Moskau (55.76, 37.62) = land.
   If it is empty, the check passes with the hint 'Weltkarte noch nicht gebaut'.
