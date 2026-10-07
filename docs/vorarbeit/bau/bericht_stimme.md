Research for use cases 1, 3 and 8 and the voice output, Jarvis repo (`/home/user/Santo`, branch claude/new-session-o54yqu)

Short version: Fish Audio can go in next to ElevenLabs as one more fetch function, using only urllib. Lights, scenes and Focus are best driven through named Shortcuts in a "Jarvis" folder. The boot check can be built from stdlib calls and built-in macOS commands, but the temperature in degrees cannot be read without sudo. For translation there are two tiers: one that works today with the existing pieces, and a truly real-time one that uses an outbound WebSocket and needs no ingress. Three problems turned up in the existing code; they are listed at the end.

## (a) Fish Audio TTS: what it is and how it fits into `src/modules/voice.py`

**API** ([TTS reference](https://docs.fish.audio/api-reference/endpoint/openapi-v1/text-to-speech))
- **Endpoint:** `POST https://api.fish.audio/v1/tts`.
- **Headers:** `Authorization: Bearer <key>`, `Content-Type: application/json`, and `model: <id>`. The model goes in a header, not the body. Allowed values are `s2.1-pro` (the default and the recommended one), `s2.1-pro-free` (free developer tier), `s2-pro`, `s1` and `drama-3-preview`. An unknown value silently falls back to `s2.1-pro`.
- **Request body:**
  - `text` (required)
  - `reference_id`: the voice model ID
  - `format`: `mp3` (default), `wav`, `pcm` or `opus`
  - `mp3_bitrate`: 64, 128 (default) or 192
  - `sample_rate`
  - `latency`: `"normal"` (best quality, default), `"balanced"` (less latency) or `"low"` (lowest)
  - `chunk_length`: 100–300, default 300
  - `normalize`: default true, but it only normalises English and Chinese
  - `prosody`: `{speed 0.5–2.0, volume in dB, normalize_loudness}`
  - `temperature` and `top_p`: both 0.7 by default
  - `condition_on_previous_chunks`: default true
- **Response:** the audio arrives as a chunked HTTP stream, so `urllib`'s `read(n)` yields bytes as they come in. Errors are 401 (bad key), 402 (payment required) and 503 (overloaded).
- **WebSocket alternative:** `wss://api.fish.audio/v1/tts/live` exists, but it uses MessagePack, which the stdlib cannot speak ([WebSocket docs](https://docs.fish.audio/api-reference/endpoint/websocket/tts-live.md)). The REST endpoint is the right choice.
- **Finding German voices:** `GET https://api.fish.audio/model?language=de&sort_by=score&page_size=20`. With `self=true` the same call lists your own voices and doubles as a cheap key check in the setup wizard ([list models](https://docs.fish.audio/api-reference/endpoint/model/list-models.md)).
- **Emotion tags:** S2 accepts free-text tags such as `[whisper]` or `[professional broadcast tone]` ([S2 page](https://fish.audio/s2/)). Keep them out of Claude's answers, because `say` and ElevenLabs would read them aloud. If you want a tone, add it as an optional prefix setting used on the Fish path only.

**German quality**
- German is a "Tier 2" language in S2, together with Korean, Spanish, French, Russian and others. Tier 1 is Japanese, English and Chinese ([fish.audio/s2](https://fish.audio/s2/), [models overview](https://docs.fish.audio/developer-guide/models-pricing/models-overview.md)).
- Because `normalize` does nothing for German, keep the existing `sprechtext()` step: it already spells out numbers, amounts and dates in German.
- Fish states about 100 ms time-to-first-audio for S2-Pro, measured on their own GPU. That excludes the network, and they give no guarantee for the free model.
- I could not find an independent German quality test. A side-by-side test with the same text against `eleven_multilingual_v2` is worth doing before switching.

**Pricing and limits** ([pricing and rate limits](https://docs.fish.audio/developer-guide/models-pricing/pricing-and-rate-limits.md))
- `s2.1-pro`, `s2-pro` and `s1` cost $15 per million UTF-8 bytes. `s2.1-pro-free` costs $0 under "fair use".
- Umlauts take 2 bytes each, so a typical 400-character Jarvis answer is about 420 bytes, roughly $0.006.
- Concurrency depends on total spend: 5 parallel requests below $100, 15 from $100, 50 from $1,000. No requests-per-minute limit is documented. Jarvis prefetches at most two requests at once, which is fine.

**Where it slots in**
- Today `sprich()` goes ElevenLabs first, then `say`. The fetch loop (`_elevenlabs_sprechen`: a queue, a prefetch thread, `afplay`) does not depend on the provider.
  - Turn it into a generic `_anbieter_sprechen(stuecke, holen)`.
  - Add `_fish_holen(text) -> bytes|None`.
  - Make the order configurable with `STIMME_ANBIETER=auto|fish|elevenlabs|mac`. `auto` means the first provider that has a key. The fallback to `say` stays exactly as it is.
- Request sketch, mirroring `_elevenlabs_holen` (lines 235–276):
  ```python
  urllib.request.Request("https://api.fish.audio/v1/tts", method="POST",
      data=json.dumps({"text": text, "reference_id": config.FISH_STIMME_ID, "format": "mp3",
                       "latency": config.FISH_LATENZ, "normalize": False}).encode("utf-8"),
      headers={"Authorization": "Bearer %s" % config.FISH_API_KEY,
               "Content-Type": "application/json", "model": config.FISH_MODELL})
  ```
- **Config** in `src/config.py`: `FISH_API_KEY`, `FISH_STIMME_ID`, `FISH_MODELL` (default `s2.1-pro`; `s2.1-pro-free` for testing) and `FISH_LATENZ` (default `balanced`). Add Fish to `konfig_uebersicht()`, and add `"fish": bool(config.FISH_API_KEY)` to `Stimme.zustand()`.
- **Continuity between chunks:** Fish has no equivalent of ElevenLabs' `previous_text` or `previous_request_ids`. To keep the intonation flowing, send larger pieces (`sprechstuecke(text, ziel=300)`) and let `condition_on_previous_chunks` work inside each request.
- **Telegram voice notes:** `sprachdatei_erzeugen` and `_elevenlabs_datei` should use the same provider chain.

**Browser playback and the reacting orb (needed for video 2)**
- `webseite.py` currently speaks with `speechSynthesis`. Its audio cannot be fed into Web Audio: no spec offers a way to capture `speechSynthesis` output ([soledadpenades.com](https://soledadpenades.com/posts/2023/web-speech-to-web-audio/), [WPT issue](https://github.com/w3c/web-platform-tests/issues/8795)). So an orb that reacts to Jarvis' voice needs the server-side voice.
- Proposed flow:
  - `/api/reden` returns an audio ID.
  - `GET /api/stimme/<id>` proxies the Fish or ElevenLabs MP3 stream. The key stays on the server.
  - The page plays it in an `<audio>` element, then `createMediaElementSource`, then an `AnalyserNode`, then `getByteFrequencyData` drives the orb ([MDN AnalyserNode](https://developer.mozilla.org/en-US/docs/Web/API/AnalyserNode)).
  - Same origin, so there is no CORS problem.
- The server runs `protocol_version = "HTTP/1.1"` (`webapp.py:194`). Streaming therefore needs either manual chunked framing or `Connection: close` with no Content-Length.
- `speechSynthesis` stays as the fallback when there is no key.

## (b) Controlling the Mac without extra packages

**The `shortcuts` command line** ([Apple guide](https://support.apple.com/guide/shortcuts-mac/apd455c82f02/mac))
- `shortcuts list`, `shortcuts list -f <Ordner>`, `shortcuts list --folders`, `shortcuts run "Name"`. It exits 0 on success and 1 on error.
- `-i` only accepts file paths. Text input goes in through stdin (`shortcuts run "X" <<< "50"`), so in Python: `subprocess.run(["shortcuts","run",name], input=text, ...)` ([Six Colors](https://sixcolors.com/post/2022/01/shortcuts-applescript-terminal-working-around-automation-roadblocks/)).
- Avoid file input and output. Since Ventura 13.2, non-sandboxed callers that use `-i`/`-o` files need Full Disk Access, and without it the shortcut fails silently ([Apple forum](https://developer.apple.com/forums/thread/724134)).
- A shortcut must not show dialogs or ask for input, otherwise the process hangs. Run each one once by hand to answer its first-run prompts ([flaviocopes](https://flaviocopes.com/courses/automate-macos/run-shortcuts-from-terminal/)).

**Lights, scenes and Focus through Shortcuts**
- Lights and scenes: the user builds named shortcuts in a folder called "Jarvis" ("Licht Büro an", "Szene Feierabend", "Fokus Arbeit") using the Home actions (run a scene, set accessories) and "Set Focus". Shortcuts can set HomeKit scenes, but the Home app has richer control ([MacStories, from the iOS era](https://macstories.net/stories/ios-12-the-macstories-review/10)).
- Focus: macOS has no command-line tool for Focus, so the "Set Focus" action plus `shortcuts run` is the way ([heyfocus](https://heyfocus.com/blog/how-to-turn-on-mac-focus-mode-from-the-terminal/)). Do not read the Focus database; that needs Full Disk Access and goes against hard constraint 2.

**Proposed tools for `tools.py`**
- `kurzbefehle_liste`: runs `shortcuts list -f Jarvis`.
- `kurzbefehl_ausfuehren(name, eingabe)`:
  - The name must appear in the live list. No shell is used, and `parameter_pruefen` checks the input.
  - Shortcuts from the "Jarvis" folder run without approval, since they are local lights and scenes.
  - Any other shortcut goes in `FREIGABE_PFLICHTIG`, because it could send messages.
  - Neither tool is offered to the autopilot.

**App launch and window layouts**
- `open -a "App"` needs no permission (it already exists as `programm_oeffnen`).
- Display geometry with no permission needed: `osascript -l JavaScript` with `ObjC.import("AppKit")` reads `$.NSScreen.screens` and the frame of each screen. NSScreen measures from the bottom-left, AppleScript `bounds` from the top-left, so y must be converted. Test this on the iMac.
- Scriptable apps (Chrome, Safari, Finder, Mail): `tell application "Google Chrome" to set bounds of front window to {x1,y1,x2,y2}`. This needs the Automation permission per target app. Error -1743 means it was denied (`messenger.py` already checks for that).
- Apps that are not scriptable: `System Events` → `set position/size of window 1 of process "X"`. This needs Accessibility (error -1719). `setup_wizard.recht_bedienhilfen()` already tests it.
- Jarvis pages on the second display:
  - `open -na "Google Chrome" --args --user-data-dir=<eigenes Profil> --app=http://127.0.0.1:8765/zentrale --window-position=X,Y --window-size=W,H`
  - With its own profile Chrome starts as a separate process and honours the flags. Without one, the flags go to the already-running Chrome, which may ignore the position. `macapp.py:63` already uses `--app` and `--window-size`.
  - Correct the position afterwards with AppleScript `bounds`.
- Layouts should be fixed definitions in config (for example `zentrale`, `arbeiten`, `praesentation`), run through a `fenster_anordnen(layout)` tool. Claude should not write AppleScript freely.
- Extras with no outward effect:
  - Volume: `osascript -e "set volume output volume 30"`
  - Dark mode: `tell application "System Events" to tell appearance preferences to set dark mode to true`. This needs the Automation permission for System Events.

**Which macOS permissions get asked for** ([Apple: app privacy access settings](https://support.apple.com/guide/platform-support/supae21a43c8))

| Action | Permission |
|---|---|
| `open -a`, `shortcuts list` | none |
| Running a shortcut for the first time | that shortcut's own privacy prompts |
| AppleScript `tell application "X"` | Automation, asked once per target app, credited to the process that started Jarvis (Terminal, Jarvis.app, or python under launchd) |
| System Events window and keyboard control | Accessibility |
| Camera / microphone | Camera / Microphone |
| Screenshots | Screen Recording |
| Shortcut file input/output | Full Disk Access (avoid) |

Under the launchd service, prompts may not appear on screen, so approve everything once interactively first. The wizard already has deep links for these settings (`setup_wizard.py:40-50`).

## (c) Hardware check for the boot report

**What exists today:** `tools.py:57-69` defines `SYSTEM_AKTIONEN`, and `systeminfo()` passes the raw command output through: `df -h /`, `uptime`, `vm_stat`, `pmset -g batt`, `ifconfig en0`, `networksetup -getairportnetwork en0`. Nothing is parsed, there is no network or CPU value, and nothing is structured for a display. I suggest a new function, `hardware_bericht() -> dict`, that runs each probe in its own thread with a timeout of about 2 s and marks every value as either "gemessen" or "nicht verfügbar, weil …".

| Value | Source (stdlib or built into macOS) | Note |
|---|---|---|
| CPU load | `os.getloadavg()` / `os.cpu_count()` | Load per core is a better measure than percent |
| Model and chip | `sysctl -n hw.model`, `sysctl -n machdep.cpu.brand_string`, `platform.mac_ver()[0]` | |
| Total RAM | `sysctl -n hw.memsize` | |
| RAM in use | Parse `vm_stat`: page size from the header line "page size of N bytes" (16384 on Apple Silicon); add active, wired and compressor pages | [man vm_stat](https://leancrew.com/all-this/man/man1/vm_stat.html) |
| Memory pressure | Last line of `memory_pressure`: "System-wide memory free percentage: N%" | [flaviocopes](https://flaviocopes.com/courses/macos-internals-troubleshooting/interpret-memory-pressure/). Alternative `sysctl kern.memorystatus_vm_pressure_level`, not checked on the iMac yet |
| Disk | `shutil.disk_usage(os.path.expanduser("~"))` (the data volume) | Finder's "available" also counts purgeable space, so its figure will be higher |
| Battery | `pmset -g batt` | An iMac has no "InternalBattery" line. Report "Netzbetrieb" and show no battery tile |
| Network | `socket.create_connection(("api.anthropic.com", 443), 3)`, timed; same check only for services that have a key; `route -n get default` | Outbound only, no key sent |
| Wi-Fi name | `system_profiler SPAirPortDataType` (slow, so cache it) | `networksetup -getairportnetwork` returns "not associated" on macOS 15+ even when connected ([Apple Community](https://discussions.apple.com/thread/255778674), [Jamf](https://community.jamf.com/general-discussions-2/macos-sequoia-bugg-34594)) |
| Temperature | Not possible without sudo: `powermetrics` needs root, and SMC reads need undocumented IOKit | Say so honestly |
| Thermal load (substitute) | `notifyutil -g com.apple.system.thermalpressurelevel` → 0 normal, 1 moderate, 2 heavy, 3 trapping, 4 sleeping; no sudo | [stanislas.blog](https://stanislas.blog/2025/12/macos-thermal-throttling-app/), which also notes `pmset -g therm` reports nothing useful on Apple Silicon |
| Uptime | `sysctl -n kern.boottime` → regex `sec = (\d+)`, then now minus that | [macpaw](https://macpaw.tech/research/mac-startup-time) |
| Displays / camera / microphone present | `system_profiler SPDisplaysDataType SPCameraDataType SPAudioDataType -json`, once at startup and cached | Only lists hardware. The real camera test stays in `camera.py` |

**Boot flow (use case 1)**
1. On the first page load of the day (a flag file), `GET /api/hochfahren` returns `hardware_bericht()` plus the morning facts from `agent._bausteine_sammeln(morgens=True)`.
2. The page plays the check as lines ticking in.
3. Claude speaks a greeting of four to six sentences: hardware in one sentence, then the day.
4. Without a key it falls back to `_briefing_ohne_claude` with the raw facts.

## (d) Real-time translation mode (use case 8)

**Tier A: works today with existing pieces. Estimated 1.5–3 s per utterance (not measured).**
- **Speech in:**
  - The browser's SpeechRecognition cannot detect the language by itself; `lang` has to be set ([MDN](https://developer.mozilla.org/en-US/docs/Web/API/SpeechRecognition)).
  - Mode: two large buttons, "Ich (DE)" and "Gast (TR/EN/…)", with automatic alternation after each final result.
  - A new `lang` only takes effect after `erk.stop()` and the next `start()` (the existing `onend` restart handles that).
  - Chrome sends the audio to Google's servers. Newer browsers offer on-device recognition through `processLocally` / `SpeechRecognition.available()` / `install()`; check whether it exists before using it.
- **Translation:**
  - A new endpoint `POST /api/uebersetzen {text, von, nach}` that bypasses the agent's tool loop: a short system prompt ("Gib nur die Übersetzung aus") plus the last 4 turns for context.
  - Fastest option is Gemini, which already has a key and code (`router.gemini_fragen`).
  - Fallback is `agent.text_anfrage` with Claude Opus 5.5 at effort `"low"`. Thinking cannot be turned off on Opus 5.5; low effort is the speed control.
  - Haiku 4.5 (`claude-haiku-4-5`, $1/$5 per million tokens) would be faster and cheaper, but that is the user's choice.
- **Voice out:**
  - `speechSynthesis`: generalise `besteStimme(lang)` and set `utterance.lang` and `voice` per language ([MDN](https://developer.mozilla.org/en-US/docs/Web/API/SpeechSynthesisUtterance/lang)). macOS Premium voices must be downloaded per language.
  - Or ElevenLabs `eleven_flash_v2_5` (about 75 ms model latency, 32 languages, half the price of multilingual) through `/v1/text-to-speech/{voice}/stream` with `language_code` ([models](https://elevenlabs.io/docs/models), [stream](https://elevenlabs.io/docs/api-reference/text-to-speech/stream)).
  - Or Fish `s2.1-pro`. ElevenLabs and Fish keep the same voice across languages.
- **Important:** `sprechstuecke()` turns digits into German words. For any non-German output, skip `schreiben_zu_sprechen` and use only `abschnitte()` and `schleifen_entfernen()`.
- Pausing the microphone while Jarvis speaks (`hoerenPause`) is mandatory, otherwise Jarvis translates himself.
- **Rough latency budget (estimates):** Chrome's end-of-speech detection about 0.5–1 s, translation 0.4–1.5 s, voice start 0.1–0.6 s.

**Tier B: true real-time, with no ingress needed**
- Gemini 3.5 Live Translate (`gemini-3.5-live-translate-preview`, preview since June 2026) does speech-to-speech translation in 70+ languages including German ([docs](https://ai.google.dev/gemini-api/docs/live-api/live-translate)).
- **Connection:** the browser opens an **outbound** WebSocket to `BidiGenerateContent` with `generationConfig.translationConfig.targetLanguageCode` and `echoTargetLanguage`, plus input and output transcripts.
- **Audio:**
  - In: 16 kHz 16-bit mono PCM in 100 ms chunks, captured with `getUserMedia` and an inline AudioWorklet.
  - Out: 24 kHz PCM, scheduled as `AudioBufferSourceNode`s. The same path can drive the AnalyserNode, so the orb reacts to it too.
  - Text input is not supported.
- **Key stays on the server:**
  - Python mints an ephemeral token with `POST https://generativelanguage.googleapis.com/v1beta/auth_tokens` using `uses: 1`, a short `expireTime` and `liveConnectConstraints` that pin the model. The response's `name` field is the token.
  - The browser passes it as `access_token`. Check the exact constrained WebSocket path in the docs when building ([ephemeral tokens](https://ai.google.dev/gemini-api/docs/ephemeral-tokens)).
- **Both directions:** run two parallel sessions on the same microphone stream. One targets `de` (foreign → German, German is silenced with `echoTargetLanguage: false`), the other targets `tr` (German → Turkish).
- **Cost:** about $0.037 per minute per session, free tier available ([pricing](https://ai.google.dev/gemini-api/docs/pricing)).
- **Limits Google names:** the voice can change after pauses, and language detection struggles with heavy accents.
- **Constraints:** it fits hard constraints 1, 3 and 4 (outbound only, key never in the browser, explain what is missing when there is no key).
- `getUserMedia` only works in a secure context, so it works on `127.0.0.1` but not in `--offen` mode over plain http on the LAN.

## Problems found in the existing code
1. `src/modules/tools.py:64-65`: `networksetup -getairportnetwork en0` reports "not associated" on macOS 15+ even when connected. Also, `en0` is not reliably the Wi-Fi interface on an iMac; map the device with `networksetup -listallhardwareports`. As a result Jarvis may wrongly say there is no Wi-Fi.
2. `src/modules/webseite.py` speaks only with `speechSynthesis`. That output cannot be analysed, so an orb reacting to the voice (video 2) needs the server-side audio path from (a).
3. `src/modules/sprechtext.py:321-327`: `sprechstuecke()` is German-only (numbers become German words). Any multilingual or translation output needs a version without that step.

Relevant files: `/home/user/Santo/src/modules/voice.py`, `/home/user/Santo/src/config.py`, `/home/user/Santo/src/modules/tools.py`, `/home/user/Santo/src/modules/webseite.py`, `/home/user/Santo/src/modules/webapp.py`, `/home/user/Santo/src/modules/sprechtext.py`, `/home/user/Santo/src/modules/router.py`, `/home/user/Santo/src/agent.py`, `/home/user/Santo/src/modules/setup_wizard.py`, `/home/user/Santo/src/modules/macapp.py`, `/home/user/Santo/src/modules/messenger.py`.