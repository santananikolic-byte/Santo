# Use case 11 research: hand tracking, tremor, thumbs-up approval and speech orb (Jarvis, plain HTML/JS, no build step)

## Main decisions
1. **Pin `@mediapipe/tasks-vision@0.10.35`, not the latest `1.1.0`.** The latest version was published 2026-10-06, one day ago. Every 1.x release (from 1.0.0 on) sends usage metrics to Google at `https://odml.pa.googleapis.com/v1/log`. 0.10.35 (2026-04-27) has no such code in its bundle or wasm loader. The HandLandmarker and GestureRecognizer APIs are the same in both (I compared the `.d.ts` files).
2. **Use `GestureRecognizer` instead of `HandLandmarker`.** It returns the same 21 landmarks and also a built-in `Thumb_Up` / `Thumb_Down` class. One model then covers the overlay, the tremor measurement and the gesture.
3. **A webcam can only measure visible hand unsteadiness, not normal physiological tremor.** Present it as "Handruhe" compared with the user's own baseline, never as a diagnosis.
4. **Thumbs-up approval:** a geometric rule and the model's `Thumb_Up` class must both agree, the thumb is held for 1.5 s, and the thresholds use hysteresis. It is armed only while exactly one approval is open, and only after 0.5 s without a thumb.
5. **Orb:** compute the loudness curve of the real audio on the Mac with stdlib `wave`. Publish it with the start time over a long-poll on `/api/stimme`. The browser plays it back against its own clock (same machine, same clock). When the browser speaks with speechSynthesis, use an event-driven animation and label it as such.

---

## (a) MediaPipe HandLandmarker / GestureRecognizer in the browser

**Checked from the sandbox with curl.** All URLs below return HTTP 200 with `access-control-allow-origin: *`.

| Item | URL | Size / note |
|---|---|---|
| ES module (pinned) | `https://cdn.jsdelivr.net/npm/@mediapipe/tasks-vision@0.10.35/vision_bundle.mjs` | 136,993 B; SRI `sha384-Ll1OFMb+0geb9fpvYvxFbnpB/UjqBeQ2iVta6EtAGmIW2s0Oed/AhFDe+32PXnKs` |
| Wasm base path for `FilesetResolver` | `https://cdn.jsdelivr.net/npm/@mediapipe/tasks-vision@0.10.35/wasm` | loads `vision_wasm_internal.js/.wasm` (11,153,617 B), or the `_nosimd_` files if SIMD is missing; `cache-control: immutable, 1 year` |
| Hand model | `https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker/float16/1/hand_landmarker.task` | 7,819,105 B, sha256 `fbc2a30080c3c557093b5ddfc334698132eb341044ccee322ccf8bcf3607cde1`, cached only 1 h |
| Gesture model (recommended) | `https://storage.googleapis.com/mediapipe-models/gesture_recognizer/gesture_recognizer/float16/1/gesture_recognizer.task` | 8,373,440 B, sha256 `97952348cf6a6a4915c2ea1496b4b37ebabc50cbbf80571435643c455f2b0482` |
| 1.1.0, if you upgrade later | `…@1.1.0/vision_bundle.mjs`, `…@1.1.0/wasm` | wasm 12,997,248 B; SRI `sha384-K9SZSZsVUHJTcMp4orEz7jVOD7Ro/2+0a1VxJvrOorWMtdXCO/rYlF17bw+iomf4` |

**Core code (checked with `node --check`):**
```js
import { FilesetResolver, GestureRecognizer, HandLandmarker }
  from "https://cdn.jsdelivr.net/npm/@mediapipe/tasks-vision@0.10.35/vision_bundle.mjs";
const fileset = await FilesetResolver.forVisionTasks(
  "https://cdn.jsdelivr.net/npm/@mediapipe/tasks-vision@0.10.35/wasm");   // SAME version as the import!
const opt = d => ({ baseOptions: { modelAssetPath: MODELL, delegate: d }, runningMode: "VIDEO",
  numHands: 1, minHandDetectionConfidence: .6, minHandPresenceConfidence: .6, minTrackingConfidence: .6 });
let erkenner; try { erkenner = await GestureRecognizer.createFromOptions(fileset, opt("GPU")); }
             catch { erkenner = await GestureRecognizer.createFromOptions(fileset, opt("CPU")); }
// per frame, via video.requestVideoFrameCallback (fallback: requestAnimationFrame + currentTime check):
const tErkennung = Math.max(performance.now(), letzteZeit + 1); letzteZeit = tErkennung; // strictly increasing ms
const r = erkenner.recognizeForVideo(video, tErkennung);
// r.landmarks[0][0..20] {x,y in 0..1, z relative}, r.worldLandmarks (meters), r.handedness, r.gestures[0][0] {categoryName, score}
```
(`HandLandmarker` works the same way with `detectForVideo(video, ts)`.)

**The 21 landmarks:**
- 0 wrist
- Thumb: 1 CMC, 2 MCP, 3 IP, 4 TIP
- Index: 5 MCP, 6 PIP, 7 DIP, 8 TIP
- Middle: 9 MCP … 12 TIP
- Ring: 13 … 16
- Pinky: 17 … 20

**Connections** (taken from the bundle; also available as `HandLandmarker.HAND_CONNECTIONS`, as `{start, end}` objects):
`[0,1],[1,2],[2,3],[3,4],[0,5],[5,6],[6,7],[7,8],[5,9],[9,10],[10,11],[11,12],[9,13],[13,14],[14,15],[15,16],[13,17],[0,17],[17,18],[18,19],[19,20]`

For drawing, multiply `x` by `videoWidth` and `y` by `videoHeight`. If you mirror the selfie view, mirror the video and the overlay canvas with the same CSS `scaleX(-1)` and keep the landmark maths unmirrored.

**Gesture classes** (`cannedGesturesClassifierOptions`): `None, Closed_Fist, Open_Palm, Pointing_Up, Thumb_Down, Thumb_Up, Victory, ILoveYou`.

**Pitfalls (found in the bundle code):**
- If the wasm path is unversioned (`…/tasks-vision/wasm`), it resolves to the latest 1.1.0 and no longer matches the pinned 0.10.35 JS.
- The loader adds a `<script>` to `document.body`, so the page needs a `<body>`.
- In VIDEO mode, timestamps must be strictly increasing. Use one time base only. The prototype first mixed `mediaTime` and `performance.now()`, which stops detection, so it now uses `performance.now()` for the detector.
- The model is fetched with `fetch()`.

**Performance:** Google publishes Pixel 6 figures only: HandLandmarker (full) 17.12 ms on CPU, 12.27 ms on GPU. In VIDEO mode the palm detector only runs again when tracking is lost. On an Apple Silicon iMac with the GPU (WebGL2) delegate this should fit easily into the 33 ms frame budget, but I could not measure it on a Mac.
- Time `recognizeForVideo` with `performance.now()` and show the result in a debug line.
- Expect about 20 MB to download on first use (wasm and model).
- Optionally, Jarvis can download the model once with urllib into its data folder (check the sha256) and serve it itself. That removes the storage.googleapis.com dependency.

**If you ever upgrade to 1.x, block the metrics upload.** Send this header only for the vision page:
```
Content-Security-Policy: connect-src 'self' https://cdn.jsdelivr.net https://storage.googleapis.com
```
The metrics sender wraps `fetch` in try/catch, so a blocked request just switches the logger off; the page keeps working. The header is also worth sending with 0.10.35: the browser then technically cannot send anything to a third-party host.

## (b) Measuring finger micro-tremor honestly

**What the webcam limits are:**
- At 30 fps the Nyquist limit is 15 Hz, so 8–12 Hz is in principle below it.
- Anything above 15 Hz folds back into the band. In the simulation, 18 Hz showed up at 11.75 Hz.
- In low light, Mac cameras often drop to about 15 fps. A real 10 Hz signal then shows up as 5 Hz (simulated). So **compute the real fps from the frame timestamps and refuse the measurement below 25 fps** ("Mehr Licht, bitte").
- Motion blur from a 33 ms exposure weakens 10 Hz by roughly 17% (sinc factor). That is minor.
- The landmarks are predicted on a crop of about 224×224 px around the hand. Positional precision is therefore limited to roughly mm order, almost regardless of camera resolution.
- Normal physiological tremor is invisible to the eye and probably well below that noise floor. I could not confirm µm figures from a source. One search result attributes to Elble that enhanced physiological tremor is 5–20 times normal amplitude.
- In short: the webcam detects visible or enhanced unsteadiness, not normal tremor.

**Method** (in the prototype `handruhe()`, tested with synthetic data):
1. Each frame: average of the fingertips 4, 8, 12, 16, 20 in pixels (convert `x`·W and `y`·H separately), divided by the palm length |0→9| in pixels. This makes it independent of distance.
   - Discard the frame if the hand is lost or the palm length is under 8% of the image height.
   - Ignore `z`.
   - Use `meta.captureTime` from `requestVideoFrameCallback` if available, otherwise the callback time.
2. Resample linearly onto an even 30 Hz grid over an 8 s window.
3. High-pass by subtracting a 9-frame moving average (0.3 s). This passes 10 Hz fully and is about −6 dB at 2 Hz, so voluntary drift is removed.
4. Amplitude: RMS of the high-passed signal × the assumed palm length (default 95 mm, user-adjustable) gives a mm estimate.
5. Rhythm: Hann window, then a small DFT from 3 to 14 Hz in 0.25 Hz steps. Report a peak only if peak power divided by the spectrum median is above 20; otherwise say "kein deutlicher Rhythmus".
   - Zero crossings are too sensitive to noise, so don't use them.
   - In the noise-only simulation the 98% quantile of this ratio was 15 (8 s window) and 22 (4 s window).

**Simulation results** (landmark noise 0.4 mm per frame, 8 s window):
- 10 Hz at 0.3 mm amplitude: detected 29 of 30 times.
- 0.2 mm: 6 of 30.
- 0.1 mm: 1 of 30.
- So the detection threshold is about 0.75× the per-frame noise. The real noise level on the Mac is unknown, so the user measures it:
  - **Ruhemessung:** hand flat on the desk for 8 s gives the noise floor R0.
  - **Haltemessung:** arm stretched out for 8 s gives R1.
  - Report R1/R0 and compare with the median of the user's last 14 measurements.

**Presentation, without medical claims:**
- Example wording: "Handruhe heute: 0,6 mm (Schätzung) – unruhiger als dein 14-Tage-Mittel. Kein deutlicher Rhythmus."
- Always show the fps, the noise floor and the sample size.
- Never use the words Diagnose, Stress, Parkinson or Gesundheit.
- Fixed footnote: "Selbstbeobachtung, kein Medizinprodukt. Eine Webcam sieht nur Bewegungen ab etwa einem halben Millimeter."
- This positioning also keeps it away from EU MDR Rule 11.
- When correlating with sales results, always show n ("3 Tage – zu wenig für eine Aussage") and say "Zusammenhang, keine Ursache".
- Store only the numbers, never any image.

## (c) Thumbs-up confirmation that cannot fire by accident

This is implemented and tested in the prototype (synthetic hand: not fired after 1.4 s, fired after 1.7 s). y grows downwards; P = palm length |0→9|.

**Conditions for "thumb up":**
- Thumb extended: |2→4| > 0.55·P.
- Thumb pointing up: y4 < y3 < y2, and the angle of 2→4 from vertical is under 35° to enter, under 50° to stay.
- Thumb tip is the highest point: y4 < every other y − 0.15·P to enter, − 0.05·P to stay.
- Four fingers curled: for (6,8), (10,12), (14,16), (18,20), the distance tip→wrist is less than PIP→wrist (to stay: less than 1.1× PIP→wrist).
- The model also says `Thumb_Up` with a score above 0.7 (to stay: above 0.5).

**Timing:**
- Hold for 1.5 s continuously; gaps of up to 120 ms are tolerated.
- After firing: 3 s lockout.
- Arm only after 0.5 s *without* a thumb, so a thumb that was already up when the question appeared does not count.
- Show a progress ring while holding.

**How it ties into approvals:**
- The page gets `/api/freigaben`. Only if exactly one approval is open does it show that approval's text and arm the gesture. It then sends `POST /api/freigabe {id, ja:true}`, which is the same as clicking "Ja".
- With several approvals open, the gesture is disabled.
- `Thumb_Down` held for 0.8 s can mean "Nein", because declining is always safe.
- The existing rule that a timeout counts as "Nein" stays as it is.
- **Note:** in `nur_anzeige` (Dienst) mode, POSTs are blocked. Gesture approval therefore only works in web mode, unless an exception is deliberately added.

## (d) Camera on localhost, permissions UX and privacy

**Secure context:**
- `http://localhost` and `http://127.0.0.1` count as secure contexts in Chrome, including `--app` windows, and in Firefox.
- Safari has allowed getUserMedia on localhost and loopback since WebKit r220805 (Aug 2017, bug 173457).
- The WLAN mode (`offen=True`, `http://192.168.x.y`) is **not** secure: `navigator.mediaDevices` is undefined there. Check `isSecureContext` and show "Kamera nur direkt am Mac".
- Never use `--unsafely-treat-insecure-origin-as-secure` or `--use-fake-ui-for-media-stream`.
- `localhost` and `127.0.0.1` are separate origins with separate permissions. Use `localhost` everywhere, as `macapp.py` already does.

**Permissions UX:**
- The first start needs a button ("Kamera einschalten" plus a one-sentence purpose). Later starts can be automatic if the permission is already granted.
- Chrome remembers the decision per origin and also offers a one-time allow.
- In Safari, the user can set Settings > Websites > Kamera to "Erlauben" for localhost; otherwise it keeps asking.
- macOS also asks once per browser (TCC). If that is refused, the error is `NotAllowedError`, fixed under Systemeinstellungen > Datenschutz & Sicherheit > Kamera.
- Map error names to German messages (in the prototype):
  - `NotAllowedError`: permission refused
  - `NotFoundError`: no camera
  - `NotReadableError`: camera in use by another app
  - `OverconstrainedError`: format not supported
  - `SecurityError`: insecure address
- Constraints: `{width:{ideal:1280}, height:{ideal:720}, frameRate:{ideal:60}}`, then read the real value from `track.getSettings()`.

**Privacy:**
- Frames stay in the browser: no `toDataURL`, `toBlob` or `MediaRecorder`, nothing sent to `camera.py`/imagesnap.
- Only numbers are POSTed. The server should validate them strictly (floats only, small body).
- `visibilitychange`/`pagehide` stop all tracks and call `close()` on the model. Show a visible "Kamera an" indicator and an "Aus" button.
- The CSP above enforces this technically.
- Disclosure: loading the files reveals the IP address to jsdelivr and Google Storage, but no images are sent.

## (e) Driving the orb from real speech amplitude

**Recommendation: compute the loudness curve on the Mac, publish it with its start time, and let the browser animate locally.**

Why this option:
- In Dienst mode the voice plays only through `afplay`/`say` on the Mac.
- `Date.now()` in the browser and `time.time()` in Python read the same clock, so sync only needs a constant `afplay` start delay. I estimate about 50 ms; measure it and make it configurable.
- Computing the curve takes about 1.1 ms per second of audio (measured here).

**Getting audio the stdlib can read:**
- **ElevenLabs:** request `?output_format=pcm_22050` (checked in their OpenAPI spec; 44.1 kHz PCM/WAV needs the Pro plan). Wrap the result with `wave` into a WAV and play it with `afplay`.
  - Remove `Accept: audio/mpeg`.
  - Add a format parameter to `_elevenlabs_holen` so the Telegram voice messages stay MP3.
  - Standard-library Python cannot decode MP3, so the current MP3 path cannot give a curve.
- **say:** run `say -o x.wav --data-format=LEI16@22050 …`.
  - Without `--data-format`, `say` fails with "Opening output file failed: fmt?" (confirmed).
  - The confirmed working variant is `LEF32@22050`, but Python's `wave` cannot read float WAV, hence `LEI16`. I could not test `LEI16` without a Mac.
  - Fallback: `say -o x.aiff` then `afconvert -f WAVE -d LEI16@22050 x.aiff x.wav`.
  - Then play with `afplay`, one chunk at a time. Side benefit: `stoppen()` can then interrupt the system voice too; today `subprocess.run(say)` cannot be stopped.
- **Do not use `audioop` or `aifc`.** Both were removed in Python 3.13.

**Loudness curve** (stdlib only; tested in `pegel.py`):
```python
with wave.open(pfad, "rb") as w: rate, n = w.getframerate(), w.getnframes(); roh = w.readframes(n)
werte = array.array("h"); werte.frombytes(roh)            # byteswap() on big-endian machines
je = rate * 20 // 1000                                    # 20 ms frames -> 50 values/s
pegel = [max(0, min(255, int((20*math.log10(max(1e-6, math.sqrt(sum(v*v for v in werte[i:i+je])/len(werte[i:i+je]))/32768))+50)/50*255)))
         for i in range(0, len(werte), je)]
```

**Publishing the curve:**
- A `Sprechpegel` object with a `threading.Condition`.
- `melden(pegel, start_ms = time.time()*1000 + VORLAUF_MS)` is called right before `Popen(afplay)`. `stoppen()` publishes an empty curve.
- `GET /api/stimme?nach=<nr>` waits up to 20 s with `wait_for`, then returns `{ok, nr, start_ms, rahmen_ms:20, pegel:[…], jetzt_ms}`.
- Add the route to `ANZEIGE_PFADE` (GET only, read-only). The `ThreadingHTTPServer` already uses daemon threads.
- Keep it to at most about 3 open long-polls: Chrome allows only 6 connections per host.

**Browser side** (`kugel.mjs`):
- Frame index = floor((Date.now() − start_ms) / 20) gives the target level.
- Rise fast, fall slowly (×0.5 up, ×0.12 down); this drives radius, glow and particle spread on `/gehirn` and on the new page.

**When the browser speaks (speechSynthesis):** the browser gives no access to the audio data.
- The conversation page sends `postMessage({sprechen:"start"|"wort"|"ende"})` from `onstart`, `onboundary` and `onend`. It already posts its state to the `/gehirn` iframe.
- The orb then pulses, and the UI calls this "spricht", not a level meter. I believe Chrome's remote Google voices often don't fire boundary events; I did not verify this.
- Last fallback: animate only from `zustand=="spricht"` in `/api/status`.

**Why not play the audio in the browser** (AnalyserNode with `createMediaElementSource` and `getFloatTimeDomainData`):
- No browser is open in Dienst mode.
- Audio could play twice (Mac and browser).
- `AudioContext` needs a user click before it can play.
- Launch flags like `--autoplay-policy` don't reliably apply when Chrome is already running.
- Stop/barge-in logic would have to move into the browser.
- It is only worth adding later as an option for web-only mode.

## Integration into Jarvis
- New `src/modules/sehen.py` with `SEITE_SEHEN`: webcam with the 21-point overlay, Handruhe panel, gesture ring, and the orb next to it.
- `webapp.py`:
  - route `/sehen` with the CSP header (extend `_kopf_setzen` with optional extra headers)
  - `/api/stimme`
  - `POST /api/sehen/messung` (numbers only)
  - add `/sehen` and `/api/stimme` to `ANZEIGE_PFADE`
- `voice.py`: PCM output, `say` to WAV, publishing the loudness curve.
- `build_single.py`: add the new module to `BAULISTE`.
- Suggested `abnahme.py` checks:
  - import version equals wasm version
  - the page contains no `toDataURL` or `MediaRecorder`
  - the CSP header is present
  - the loudness curve from a generated WAV is correct
  - `/api/stimme` times out cleanly
  - the page handles a missing camera or insecure context with a German message

## Files
All in `/tmp/claude-0/-home-user-Santo/960d1cbb-e7e7-5f3d-ab4f-b540bef2bbee/scratchpad/vision_prototyp/`:
- `sehen.mjs`: camera, model, overlay, `handruhe()`, thumbs-up logic (passes `node --check`)
- `kugel.mjs`: orb client
- `pegel.py`: loudness curve
- `tremor_sim.py`, `tremor_sim2.py`: noise and aliasing simulation
- `logik.mjs`, `logik2.mjs`: gesture and tremor tests

## Sources
- jsDelivr API: https://data.jsdelivr.com/v1/packages/npm/@mediapipe/tasks-vision
- npm registry: https://registry.npmjs.org/@mediapipe/tasks-vision
- Package README and `vision.d.ts` from jsDelivr
- MediaPipe Hand Landmarker docs: https://developers.google.com/edge/mediapipe/solutions/vision/hand_landmarker
- WebKit localhost getUserMedia: https://bugs.webkit.org/show_bug.cgi?id=173457
- ElevenLabs OpenAPI: https://api.elevenlabs.io/openapi.json
- `say` WAV error: https://www.markhneedham.com/blog/2011/04/07/unix-getting-the-sound-from-say-as-a-wav-file/
- `say` LEF32 workaround: https://scrapbox.io/nikkie-memos/macOSのsayコマンドでwavファイルを保存したい
- Elble (search snippet only): https://smithengineering.queensu.ca/mme/faculty/deluzio/jam/files/Elble.pdf