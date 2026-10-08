# Jarvis gap map: three demo videos and 13 use cases

Branch `claude/new-session-o54yqu`, read-only. Every file:line reference was checked against the code. Nothing was changed and no tests were run, because the tests write into `dashboard/` inside the repo.

---

## 0. Traps in the code a builder will hit first

1. **Pages may not load anything from the network.** Four tests fail if a page contains `http://` or `https://` (only the SVG namespace is allowed):
   - `tests/abnahme.py:1694-1698` for Gehirn and Zentrale. This check also requires `{{SCHLUESSEL}}`, `requestAnimationFrame` and `prefers-reduced-motion` in the page.
   - `:2672-2676` for `SEITE_HTML`, `:2504` for Autopilot, `:2623` for Pfad.
   - So Three.js or MediaPipe from a CDN breaks the tests. Today the only file route is `_datei` (`webapp.py:476-490`), and it is limited to `DASHBOARD_VERZEICHNIS`. There is no route for local static files or assets.
2. **`agent.status` is replaced as a whole.** `zustand_setzen` builds a new dict each time (`agent.py:463-465`), so any extra field is lost on the next state change. `status_daten` passes on only `zustand, satz, seit, jetzt, aktionen` (`ansicht.py:314-317`). `satz` exists but nothing ever fills it or renders it.
3. **Web mode has no server voice.** `webbetrieb` builds the agent with `mit_stimme=False` (`run.py:499`), so the browser speaks through `speechSynthesis` only. ElevenLabs is used only in the `hoeren`/`daemon` modes, which play through `afplay` on the Mac. In web mode the server never sets `hoert` or `spricht`; only the main page tells the Gehirn iframe via postMessage (`webseite.py:279-281`, `ansicht.py:455-457`).
4. **The display in Dienst mode is read-only.** It runs on port 8766 (`run.py:58, 169-183`) with `nur_anzeige=True`: GET only, and only paths in `ANZEIGE_PFADE` (`webapp.py:109-110, 281-283`). Approvals there are voice-only through `SprachFreigabe` (`run.py:159, 183`). A test enforces this (`abnahme.py:1604-1620`). A gesture-yes or a camera-to-server POST is blocked by design.
5. **`jarvis.py` must be rebuilt after every change in `src/`.** A test checks that it is current (`abnahme.py:2912`). New modules must be added to `BAULISTE` (`build_single.py:41-82`), otherwise the build only warns (`:358-377`).
6. **"Stdlib only" applies to the core, not to extras.** Optional packages already exist behind try/except imports:
   - numpy, sounddevice, faster_whisper in `voice.py:33-46`
   - pyautogui, PIL in `computer_use.py:27-36`
   - playwright in `browser.py:23-27`
   - `install.sh:160` installs them; `build_single.py:149-171` moves the import blocks to the top of `jarvis.py`. Adding mediapipe the same way would break the constraint, so that needs a decision.
7. **No minimum Python version is enforced** (`install.sh:54-61`, `JARVIS.command:36`). The Mac's command-line-tools Python can be 3.9. Avoid `statistics.correlation` (3.10+) and `match`. `audioop` and `aifc` are gone in 3.13.
8. **The camera principle conflicts with Video 2.** `camera.py:7-9` says "Kein Dauervideo, keine Überwachung", and so does the tool text (`tools.py:463-466`). A live webcam is a deliberate change of that principle.
9. **The calendar can only read and create.**
   - There is no delete or move. `termine()` throws away href and etag (`calendar_mod.py:189-203`), so a CalDAV DELETE is impossible as things stand.
   - Time handling is wrong in three ways: `ics_zeit_lesen` strips the `Z` and reads UTC as local time (`:36-48`); `TZID` and `RRULE` are ignored (`:67-102`); `termin_anlegen` writes floating times with no timezone (`:272-273`).
   - `CALDAV_KALENDER` is declared (`config.py:189`) but never used.
10. **Approval prompts show what, but not why.** `freigabe_details` dumps the arguments as JSON (`tools.py:546-562`), and `freigabe_ansage` speaks them (`dienst.py:85-124`). Constraint 3 asks for what, why and how, so tools need a reason field, for example a `begruendung` argument.
11. **A "ja" after a proactive message has no context.**
    - `web.melden` writes to the DB history and the browser, not to `agent.verlauf` (`webapp.py:138-157`). This path carries the scheduler and autopilot messages.
    - Briefings, by contrast, run through `agent.denken` and do land in `agent.verlauf` (`agent.py:526, 603`).
12. **`datei_oeffnen` is unreachable.** It is in `PARAMETER_AKTIONEN` (`tools.py:75`) but not in the catalog, and `run()` rejects names that are not in the catalog (`:604-609`).
13. **The phone test fixes the current state.** `abnahme.py:870` asserts `gespraech_moeglich is False`. A phone-agent build has to change this test on purpose.

---

## 1. Integration points

### 1.1 Tools: declaration, dispatch and approvals (`src/modules/tools.py`)

**Declaring a tool**
- Each entry is built by `werkzeug(name, beschreibung, eigenschaften=None, pflicht=None)` and becomes `{"name", "description", "input_schema": {"type": "object", "properties": {...}, "required": [...]}}` (`:188-192`).
- Shorthand types: `text`, `zahl`, `ganz`, `wahr` (`:194-197`). Enums are written inline (e.g. `:236-238`), arrays at `:422-423`, a nested object at `:295-298`.
- The list `eigene` (`:199-515`) is grouped by `# -- Bereich --` comments. MCP tools are appended as `mcp__<server>__<tool>` (`:516`). There are 75 own tools today.

**Dispatch**
- `_ausfuehren` is one long if-chain by name (`:662-951`). A tool must return a dict with `ok` plus `text` or `fehler`; the contract test is `abnahme.py:613-635`.
- The result is sent back to Claude as JSON, cut at 6000 characters (`agent.py:617-623`).

**`run()` step by step** (`:601-660`)
1. Unknown name: rejected and logged.
2. `datei_schreiben`: pre-checked before anything is asked.
3. `braucht_freigabe` (`:538-544`): MCP tools follow their own rule; `NETZ_SENDEND` tools need approval only after something foreign was read; everything in `FREIGABE_PFLICHTIG` always asks.
4. In background mode, any tool that needs approval is refused with the instruction to write a draft instead (`:620-627`).
5. Otherwise `_freigabe` (`:564-575`) calls `kanal.anfordern(name, details)`. The channel is per thread (`anfrage_kanal_setzen`, `:160-170`) or global (`freigabe_kanal_setzen`, `:151-158`), with Telegram and then the terminal as fallback (`telegram_mod.py:170-255`).
6. Scripts get a fingerprint check (`:639-645`).
7. If the tool is in `FREMDE_INHALTE`, the run is marked as having read foreign content (`:647-648`).
8. The tool runs, and every call is logged to the `aktionen` table (`memory.py:263-273`). That log drives the Gehirn flashes and the Zentrale activity feed.

**The three sets**

| Set | Line | Meaning |
|---|---|---|
| `FREIGABE_PFLICHTIG` | `:79-82` | Always asks. A timeout counts as no (`webapp.py:78-86`, `config.FREIGABE_TIMEOUT`). |
| `NETZ_SENDEND` | `:88-89` | Carries free text to the network. Asks only after something foreign was read in the same run; the flag resets each turn (`agent.py:510`). Removed completely for background roles (`team.py:399-403`). |
| `FREMDE_INHALTE` | `:91-93` | The result is third-party text, so it sets the "foreign read" flag. |

**Background mode**
- Controlled by `lauf_beginnen` / `hintergrund_setzen` (`:524-533`) and `agent.arbeiten(..., hintergrund=True)` (`agent.py:630-642`), which the autopilot uses through `team.beauftragen(hintergrund=True)` (`team.py:368-421`).
- A test enforces "no approval tool and no `NETZ_SENDEND` tool in any background role" (`abnahme.py:2365-2378`).
- Design tip: tools with fixed enums (regions, ticker symbols) do not carry free text. They can stay out of `NETZ_SENDEND` and remain usable for briefings and the autopilot, but news results belong in `FREMDE_INHALTE`.

**Checklist for a new tool**
1. Catalog entry and an `_ausfuehren` branch.
2. Membership in the right sets.
3. Add it to the relevant roles in `team.ROLLEN` (`team.py:73-293`). The test at `abnahme.py:529-535` requires every name a role lists to exist.
4. A spoken approval text in `dienst.freigabe_ansage` (`:85-124`).
5. The flash regex on the Gehirn page (`ansicht.py:517-520`).
6. A probe in the tool-contract test.
7. If needed, keywords in `router.HANDLUNGSSTAEMME` (`router.py:40-48`).

Cost note: the whole catalog goes with every Claude round (`agent.py:530, 570`), with a cache breakpoint on the last tool (`:58-61`). More tools mean more tokens, and changing the order invalidates the cache.

### 1.2 How `agent.status` reaches `/api/status`

- **Sources:**
  - `agent.status` (`agent.py:220`), set by `zustand_setzen` (`:463-465`).
  - `denken` sets `denkt` and then `bereit` (`:479/483`); with `anzeigen=False` (used for briefings) it sets nothing.
  - `antworten` sets `spricht` (`:734-738`), but only with the Mac voice.
  - In daemon mode, `run.dauerbetrieb.zustand_wenn_frei` (`run.py:214-220`) sets `hoert`, `bereit` and `spricht` (around the announcer, `:226-234`).
- **Endpoint:** `ansicht.status_daten(tools, agent)` (`:306-317`) copies the fields and adds the last 8 entries from `aktionen`. `webapp._get` serves it at `/api/status` (`:314-315`). `zentrale_daten` also embeds it (`:380`).
- **Consumers:**
  - Gehirn: `/api/status` every 1.5 s and `/api/gehirn` every 30 s (`ansicht.py:575`). A new action id triggers `aktion(name)`, which flashes the matching region (`:566-570, 517-520`).
  - Zentrale: `/api/status` every 2 s, which only updates the status chip (`:787-789`), and `/api/zentrale` every 15 s (`:786`).
- **To push display state** (mode, region, call, speech envelope): keep it in a separate attribute such as `agent.anzeige`, not inside `status`, and add it explicitly to `status_daten`. The 2 s poll is fine for switching topics but too slow for a live transcript or tremor data; those need their own endpoint polled every 0.5-1 s, or long-poll or SSE. SSE would need custom headers, because `_kopf_setzen` always sets `Content-Length` (`webapp.py:453-460`).

### 1.3 The `/zentrale` page (`ansicht.py:581-791`)

**Layout**
- The body is a grid: header, `main`, ticker (`:588`).
- `main` has three columns, `minmax(260px,24%) | 1fr | minmax(280px,27%)` (`:599`); the HTML is at `:635-654`.
  - Left column: Betrieb rings, Denken bars, Nachfassen list.
  - Middle: `.globus` canvas with an absolutely positioned `.briefing` overlay (`:616-621`).
  - Right column: Einnahmen/Ausgaben SVG, Pipeline bars, "Was Jarvis getan hat" feed.
  - Footer: a scrolling ticker.
- Below 1000 px it collapses to one column (`:632`).
- There is no mode switching; the layout is fixed.

**Data**
- `anzeigen(d)` (`:751-784`) renders everything from `zentrale_daten` (`:322-381`), which calls `dashboard.daten_sammeln(False)`. With `False`, the calendar and mailbox are not fetched.
- The briefing lines (`:338-349`) are static facts from the database, not what Jarvis just said.
- `ANZEIGE_DISKRET` blanks names (`:204, 352, 367-376`).
- Reusable widgets: `ring()` (`:666-672`), `balken()` (`:673-674`), the SVG `verlauf()` chart (`:680-688`).

**Globe**
- It is a 2D canvas with an orthographic projection. No WebGL, no Three.js.
- Land: hand-drawn polygons `LAND` minus `MEER` (`:690-709`), sampled into a 0.95° dot grid `PUNKTE = [sin lat, cos lat, lon rad]` (`:712-713`).
- Projection: `proj(lat, lon, R, cx, cy, l0, t)` returns `[x, y, sicht]`, where tilt `t = fokusLat*rad` and `sicht > 0` means visible (`:718-720`). `winkel()` gives the angular distance (`:721`).
- `globus(jetzt)` (`:722-749`):
  - Focus is the home location (`art == "zuhause"`) or, without places, a slowly rotating globe.
  - Zoom is 1.0-1.55, chosen from how far the customer places spread (`:724-726`); radius `R = min(GW*.46, GH*.47)*zoom` (`:727`).
  - Graticule every 10° (`:733-735`), dots drawn in one pass (`:736-738`), city lights loaded once from `/api/lichter` (`:740-741, 788`).
- Markers (`:743-748`): pulsing ring `r = 5+puls*7` plus a 3 px dot; home is white, customers orange; labels avoid overlaps in an 80×16 px box. The data is `d.orte` from `orte_der_kunden` (`:187-215`), which uses the city table `ORTE` (`:35-67`). There are no countries or regions.
- `lon0` and `gz` are declared but unused (`:717`). There is no way to set focus from outside, no smooth transition, and zoom tops out at 1.55.

**Reusable particle engine for an orb** (Gehirn page, `:464-563`)
- `zufall` (`:467`), `drehen` / `abbilden` (`:525-527`) and the radial `glutBild` sprite (`:528-530`).
- Speed follows the state: `bereit .5, hoert 1.4, denkt 5, spricht 3` (`:534`).
- An embedded mode `?eingebettet=1` (`:452-453`) is what the main page uses in its iframe.

### 1.4 Adding routes (`src/modules/webapp.py`)

1. **Page:** an HTML constant with `{{SCHLUESSEL}}`, and only inline CSS and JS. Import it at `:36-40` and serve it in `_get` (`:295-368`) with `self._html(b, SEITE_X.replace("{{SCHLUESSEL}}", self.token))`.
2. **API:** `self._antworten(b, 200, dict)`. POST handlers go in `_post` (`:370-434`); the JSON body is capped at 512 KB (`MAX_KOERPER`, `:43, 439-450`).
3. **Security, applied in `_behandeln`** (`:274-293`):
   - `_erlaubt` (`:235-254`) checks the Host header (localhost, 127.0.0.1, ::1, and the LAN IP when the server is open) and the token, either `?schluessel=` or the `X-Jarvis-Schluessel` header.
   - `_herkunft_ok` (`:256-272`) compares Origin with Host, for POST only. GET has no origin check, so new GET routes must never change anything.
4. **Display mode:** a path must be in `ANZEIGE_PFADE` (`:109-110`) to show on the Dienst display, and it must be GET.
5. **Client side:** fetch with the `ANHANG` token suffix (`ansicht.py:657`) or the `url()` helper (`webseite.py:290-293`).
6. **Other hooks:**
   - `/api/werkzeug` (`:421-427`) runs any tool directly, still through the approval check.
   - `WebFreigabe` (`:54-105`) handles approvals: the browser polls `/api/freigaben` and answers with `POST /api/freigabe {id, ja}`.
   - `melden()` (`:138-157`) queues messages that the browser collects from `/api/meldungen` every 4 s.
7. **Camera access in the browser:** the Mac app opens Chrome or Edge in an app window on `http://localhost:8765/` (`macapp.py:39-62`). Localhost counts as a secure context in Chrome, so `getUserMedia` works; Safari needs checking. There is no CSP or Permissions-Policy header.

### 1.5 How the browser speaks, and where an orb could hook in (`webseite.py`)

- `sprich(text, danach)` (`:340-374`) splits the text into sentences, speaks them one by one as `SpeechSynthesisUtterance` (`lang de-DE`, best German voice from `:323-332`), pauses recognition while speaking (`hoerenPause`), and has a safety timeout. `onboundary` is not used. The Web Speech API exposes no audio samples, so in web mode there is no real amplitude.
- State goes to the brain iframe through `setzeZustand` → `postMessage({zustand})` (`:275-287`), mapped `wach→hoert`, `denkt`, `spricht`.
- The old CSS orb (`.kugel .ring/.kern/.welle`, `:62-98`) is hidden behind the brain (`.kugel.hirn`, `:65-68`).
- **Three options for a speech-reactive orb:**
  - **(a) Web mode, cheap:** drive a fake envelope from `onstart`, `onboundary` and `onend`.
  - **(b) Web mode, real audio:** a new endpoint that serves audio from `Stimme.sprachdatei_erzeugen` / `_elevenlabs_datei` (`voice.py:401-462`), played in the browser through `<audio>` and a WebAudio `AnalyserNode`. This needs a `Stimme` object in web mode, which is `None` today.
  - **(c) Daemon mode** (Mac plays the audio, the display is a separate page): the server computes the envelope itself, for example from `say -o x.wav --data-format=LEI16@22050` read with stdlib `wave`, or from a raw PCM format from ElevenLabs (to verify). It then publishes `{start, huelle[]}` and the display plays it back in sync.
  - Caveat: many code paths call `Stimme.sprich` directly without setting state (the announcer in non-daemon modes, scheduler output).

### 1.6 Scheduler and briefings

- **`Scheduler(agent, routines, ausgabe)`** (`scheduler.py:56-66`): jobs are `{uhrzeit "HH:MM", aufgabe() -> str, beschreibung, zuletzt}`, added with `job_anlegen` (`:68-75`).
  - Standard jobs come from `BRIEFING_MORGENS` / `BRIEFING_ABENDS` (`:82-89`, `config.py:192-193`). Routines with a time are hooked in at `:91-114`.
  - The loop checks every 30 s (`:168-178`), never catches up more than 120 minutes late (`:25, 41-50`), and marks today's past jobs as done at start (`:116-124`).
  - Only one fixed time per day. Interval jobs (market refresh, call-status polling) need their own thread or a Scheduler extension.
- **Where the output goes:** `web.melden` in web mode (`run.py:514-515`), `Ansager.sagen` in daemon mode (`:161-162`; `dienst.py:171-208`, autopilot messages via `leise` respect quiet hours), `stimme.sprich` in `hoeren` mode, `telegram.senden` in Telegram mode.
- **Briefing content:** `agent.briefing_morgens` (`agent.py:745-756`) gathers facts in `_bausteine_sammeln` (`:773-809`: calendar, mailbox, weather, autopilot inbox, open items, leads) and runs `denken(..., protokollieren=False, anzeigen=False)`. Without a key it reads out the bare facts (`:811-818`). New facts such as news, markets, recovery or the day's load go in as extra `teile.append(...)` lines, and every failure must stay visible.

### 1.7 Config keys (`src/config.py`)

- Declare as `NAME = _text("NAME", default)`, `_zahl`, `_ganzzahl` or `_wahrheit` (helpers `:63-92`, keys `:101-239`).
  - Names must be unique across the project, because the build turns `config.NAME` into a bare `NAME`.
  - Read only as `config.NAME`; `getattr(config, …)` aborts the build (`build_single.py:246-262, 421-433`).
- Values are read from `config/.env` first, then the process environment.
- `env_setzen` (`:242-266`) persists a value and updates it live. `konfig_uebersicht` (`:297-310`) feeds the "dienste" list in `/api/zustand`.
- Optional extras: a line in `.env.beispiel`; a terminal flow `jarvis.py zugang <kennung>` via `setup_wizard.ZUGAENGE` (`:497-502`); a Lernpfad level (`lernpfad.py:29-101`).
- One existing exception: MCP tokens live in `config/mcp_servers.json` under `"umgebung"`, not in `.env`. `mac.py` blocks reading that file.

### 1.8 Build (`build_single.py`)

- `BAULISTE` (`:41-82`) lists modules in dependency order; `config` comes first, then `modules/*`, then `agent` and `run`. A new module goes before every module that imports it, for example before `webapp` and `tools`.
- Internal imports (`config`, `agent`, `run`, `modules.*`, `:86`) are removed. Nested internal imports inside functions trigger a warning (`:281-292`) and break in the single file.
- Top-level name collisions are renamed per module to `NAME_modul` through the token stream (`:401-418`). Never import a name that collides (`from modules.x import SCHEMA`), because the importing module will then point at a name that no longer exists. Use unique prefixes.
- The result is syntax-checked with `ast` (`:491-498`). `abnahme` additionally runs `jarvis.py test` (`:2918-2922`).

### 1.9 Tests

- **`tests/abnahme.py`:**
  - `pruefen(name, bedingung, hinweis)` (`:74-81`) and `abschnitt(titel)` (`:84-85`).
  - Each area is a `pruefung_<bereich>(agent)` function that must be added to `main()` by hand (`:2932-2983`).
  - The database and logs go to a temp directory (`:33-38`).
- **Fake patterns already in use:**
  - `types.SimpleNamespace` fake tools and world (`:1552-1556`), and small classes with static methods (`_WeltOhne`, `_AgentJa`, `:426-444`).
  - Monkeypatching agent methods, e.g. `agent.zustand_setzen` (`:1588`) and `agent.arbeiten` (`:2365`), and config flags (`config.ANTHROPIC_API_KEY = "test"`).
  - Injected fetchers (`betriebe_suchen(holen=...)`).
  - A fake request class driven through `JarvisWeb._behandeln` with `_antworten` / `_html` / `_koerper` replaced (`:1604-1620`); real HTTP on a free port (`:1707`).
  - pty-based approvals via `im_terminal` (`:104-142`); node evaluating page JS when node is installed (`:1518`).
- **Network:** `wetter` hits Open-Meteo for real (`:2877`). New network tools should accept an injectable fetcher so they can be tested offline.
- **`tests/bauauftrag.py`:** a numbered checklist via `haken(nummer, punkt, bedingung, beleg)` (`:43-50`).

---

## 2. The three videos

### Video 1: "Geheimdienst"

| Feature | What exists today | What is missing |
|---|---|---|
| **World news by region** | `Welt.recherche` goes through the Brave MCP (`world.py:306-330`). That server is off by default and needs npx and a key (`config/mcp_servers.json`). No news source and no region model. **About 5%.** | A news tool with a fixed `region` enum: keyless sources (RSS via urllib + xml.etree, GDELT DOC API) or a keyed source, all to verify. Every item needs source and time. Belongs in `FREMDE_INHALTE`. A spoken regional summary from Claude. |
| **Oil, indices, stock markets** | Nothing. | A market tool with a symbol enum and watchlist config (candidates: stooq CSV for indices and futures, ECB FX XML, CoinGecko for crypto, to verify). Caching and rate limits; say "nicht abrufbar" on failure, never guess. |
| **Own business KPIs** | Complete as data: `bookkeeping.auswertung`, `tagesverlauf`, `monatsverlauf`, `belegquote`; `akquise.pipeline`, `cashflow_prognose`; `privat.bedarfsrechnung`; `team.lagebericht` (`team.py:430-513`). Spoken via `lagebericht` / `auswertung`. **About 70%.** | Only the display mode for them (see the switching row). |
| **3D/HUD globe that zooms to a region, with markers** | 2D orthographic dot globe (`ansicht.py:690-749`), customer markers only, focus fixed on home, zoom 1-1.55, no external control. **About 30%.** | A region table (lat, lon, zoom for Iran, USA, Deutschland, Russland, Nahost, Ukraine, China, Europa…). `ORTE` has cities only. A server-pushed focus with eased transitions (lerp of `fokusLat/Lon/zoom` per frame). Zoom up to about 4-6 (the 0.95° dot grid gets sparse, so densify locally if needed). A news marker style with headline labels. A HUD overlay (crosshair, coordinates, source and time). |
| **Display switches by topic** (globe → finance charts → KPI tiles) | The fixed 3-column grid (`:599, 635-654`). Only tool names reach the page through `aktionen`, not their arguments (`status_daten`, `:311-317`). | A display state on the server (`agent.anzeige = {modus, region, thema, version, daten}`), set either by a local tool such as `anzeige_zeigen` (no approval) or implicitly from a tool-name map in `Werkzeuge.run`. Exposed in `status_daten`. A middle "stage" with modes globus / finanzen / kennzahlen (later anruf / sicht). Finance charts can reuse the `verlauf()` SVG pattern; KPI tiles the `ring()` / `balken()` widgets. A line in the system prompt telling Claude to switch the display (`agent.py:136-168`). |
| **Multi-turn** ("Und wie ist es in Deutschland?", "Geh nochmal nach Russland") | Works at the brain level: `agent.verlauf` keeps the history, and the router sends answers to Claude (`router.py:89-91`). "Deutschland" and "Russland" are not small-talk words, so they reach Claude. | Only the region tool plus display focus, so Claude can resolve the reference and repoint the globe. |

### Video 2: "Gedanken lesen"

| Feature | What exists today | What is missing |
|---|---|---|
| **Live webcam** | Only a single still via imagesnap or ffmpeg, then a Claude description (`camera.py:52-127`). The principle forbids continuous video (`:7-9`). Kamera onboarding check at `setup_wizard.py:343-362`. **About 0% for live video.** | A browser `getUserMedia` panel: opt-in, never recorded, never uploaded. Update the principle text, docstring, tool text and Lernpfad. |
| **Hand tracking, 21 landmarks** | Nothing. | A choice of engine: (a) MediaPipe Tasks Vision JS+WASM+model bundled locally, which needs a local file route and adjusted no-network tests; (b) the macOS Vision framework (`VNDetectHumanHandPoseRequest`, 21 joints) through a small Swift helper compiled with `swiftc`, sending JSON to Python, which needs about 30 Hz transport; (c) Python mediapipe, which breaks the stdlib rule. A canvas overlay of the 21 points. |
| **Finger micro-tremor** | Nothing. | Index fingertip relative to the wrist at 30 fps or more, detrended, band power at about 4-12 Hz (Goertzel or FFT in JS; 30 fps gives a 15 Hz ceiling), normalised by hand size, labelled clearly as non-medical. Store a daily index, e.g. through `kennzahl_setzen` (`memory.py:215-224`, one value per day). |
| **Wearable recovery** (Oura, Whoop, Apple Health) | Nothing. Manual entry is possible through `kennzahl_setzen` (`tools.py:219-220`). | Oura API, Whoop (OAuth2; a redirect to localhost is not public ingress), Apple Health (no Mac API: import `export.xml` with `iterparse` from a watched folder, or an iOS Shortcut writing a file to iCloud Drive). All outbound or file-based. Keys in `.env`. Clear message when nothing is connected. |
| **Correlation with sales** | `gespraeche` table (`call_analysis.py:14-32`: datum, ergebnis, punktzahl). `verkaufsmuster` gives the close rate for a whole period only (`:241-294`). Calendar appointments per day via `Kalender.termine` (`calendar_mod.py:166-203`). | A per-day join of recovery, number of appointments and close rate, in buckets with n shown. Say plainly when n is too small. Pearson written by hand (3.9-safe). A rule for which appointments count as sales appointments (title keywords or a link to a lead). |
| **Proactive proposal** ("Soll ich morgen zwei Termine streichen?") | The autopilot checks (`autopilot.py:232-301`) only write drafts; the announcer and `melden` speak. No calendar delete or move. **About 10%.** | A rule (morning job or autopilot check): low recovery plus a full day plus a weak close rate produces a proposal. It must run through `agent.denken` so a "ja" has context, or through a pending-proposal object. New `termin_loeschen` / `termin_verschieben` tools: CalDAV DELETE/PUT with href and If-Match, keep href and etag in `termine()`, require approval and give a reason. Optional customer notice via `nachricht_senden` (approval). |
| **Finger gesture as "yes"** | Today an approval is a strict spoken yes (`dienst.py:60-77`, `webseite.py:257-267`), a button, Telegram or the terminal. | In web mode: a deliberate gesture (e.g. thumbs-up held 1.5 s, only while the approval dialog is open) leads to `POST /api/freigabe {id, ja:true}`. It must be as strict as `jaNein` and must never answer anything other than the open dialog. In Dienst mode the display is GET-only and approvals are voice-only, so this needs a combined voice-or-gesture channel and a narrow POST on the display. That is a security decision. |
| **Particle orb reacting to speech** | The particle brain reacts to state only (`ansicht.py:534`). The old CSS orb is hidden. | A sphere version of the particle engine (§1.3), driven by amplitude (§1.5, options a/b/c). |

### Video 3: "Restaurant anrufen"

| Feature | What exists today | What is missing |
|---|---|---|
| **Find a nearby Asian restaurant** | The OpenStreetMap search knows `restaurant` (`world.py:49`): `overpass_abfrage` (`:109-116`), `osm_betriebe_lesen` returns name, address, phone, web (`:119-142`). `betriebe_suchen` (`:271-302`) is not its own tool; it is reachable only through `leads_finden`, which adds every hit as a sales lead (`akquise.py:446-529`). That is wrong for restaurants. **About 30%.** | A read-only tool such as `lokale_suchen(ort, kueche, radius)` filtering on the OSM `cuisine` tag (asian, chinese, thai, vietnamese, japanese, sushi, korean, indian), returning `opening_hours`, distance and phone. "Nearby" means the home location (`WETTER_ORT`) or browser geolocation. Must not create leads. |
| **Autonomous voice-to-voice call** | `Telefon.anrufen` only plays a one-way TwiML `<Say de-DE>` twice (`telefon.py:147-179`). `zustand()` honestly reports no conversation (`:94-101`), and a test holds that (`abnahme.py:870`). Call status is stored once and never updated (`:175-177`). **About 10%.** | A live Twilio dialog (Media Streams, ConversationRelay, or a Gather action URL) needs Twilio to reach the Mac, which is blocked. Outbound-only route: a hosted voice-agent service started by REST and watched by REST polling or a websocket opened from the Mac (Vapi, Retell, Bland, ElevenLabs agents with Twilio; endpoints and live-transcript support to verify). No webhooks during the call, so the brief must contain every rule up front (date, time window, party size, name, callback number, acceptable alternatives, never pay or give card details). Parse the result afterwards with `agent.json_anfrage`. New `config.py` keys; `FREIGABE_PFLICHTIG` plus `NETZ_SENDEND`; a text in `freigabe_ansage`; a disclosure line ("KI-Assistent im Auftrag von …, Gespräch wird mitgeschrieben"; EU AI Act Art. 50, German § 201 StGB, to verify). A stdlib websocket would have to be written by hand (socket+ssl, RFC 6455). |
| **Phone HUD with live transcript of both sides** | Nothing. `anrufliste` is text only (`telefon.py:200-210`). | A `/api/anruf` endpoint (state: wählt / klingelt / verbunden / beendet, timer, transcript turns) polled about every 1 s. A HUD panel or stage mode on Zentrale and the main page. Add the path to `ANZEIGE_PFADE` for the Dienst display. Hide numbers in discreet mode. |
| **Enter the reservation in the calendar** | `termin_anlegen` uses CalDAV PUT and requires approval (`tools.py:451-454`, `calendar_mod.py:237-290`). | It works once CalDAV is configured. Fix the timezone handling (§0.9). Claude should propose the appointment straight from the parsed call result. |

---

## 3. The 13 use cases

| # | Use case | What exists today (completeness) | What is missing |
|---|---|---|---|
| 1 | **Boot greeting, hardware check, day overview** | Daemon says "Ich bin da. Sag Hey Jarvis…" (`run.py:209`). `selbsttest()` (`run.py:682-937`) checks microphone, voice, ElevenLabs, Whisper, camera, screen control, phone, browser and weather, but only prints. The morning briefing (`agent.py:745-809`) runs only at `BRIEFING_MORGENS`. Web mode has no greeting on page load. **About 35%.** | A spoken start sequence on daemon and web start. Web: one `melden()` on the first browser connection, not on every reconnect. Reuse `Stimme.zustand` (`voice.py:185-195`), `kamera.zustand`, `mail/kalender.verfuegbar`, `systeminfo speicherplatz/wlan` (`tools.py:57-69`; `batterie` is meaningless on an iMac). Day overview from `_bausteine_sammeln`. A boot animation on the HUD. A version without a key, like `_briefing_ohne_claude`. |
| 2 | **File organisation and code generation** | `dateien_suchen` (Spotlight, `mac.py:145`), `datei_lesen` with a blocklist (`:118`), `datei_schreiben` (approval, new files only in Dokumente, Schreibtisch, Downloads or `MAC_SCHREIBORDNER`, `mac.py:61, 218-260`), `ordner_zeigen`. Werkstatt scripts and project files (`werkstatt.py`; running a script shows the full code plus a fingerprint check, `tools.py:566-570, 639-645`). Programmer, web-designer and chatbot-builder roles. **About 50%.** | Move, rename, create folders, sort: a plan-then-approve tool (the moves are listed in the approval; `os.rename` only inside allowed folders; never delete; an undo log). Projects are single Python scripts with a 60 s limit; no multi-file runs, no git. |
| 3 | **Smart home and workplace control** | `programm_oeffnen` (`open -a`, no approval, parameter check, `tools.py:72-76, 969-981`), read-only `systeminfo` (volume, Wi-Fi), `bildschirm_bedienen` (pyautogui, approval per step), `jarvis.py anzeige` opens Zentrale and Gehirn (`run.py:334-357`). **About 15%.** | Lights and scenes: an allowlist of `shortcuts run "<Name>"` (macOS Shortcuts can trigger HomeKit scenes) defined in config, like `SYSTEM_AKTIONEN`; optionally the Hue bridge REST API on the LAN with a key in `.env`. Window layouts via AppleScript and System Events (needs the accessibility permission). Set volume and Focus mode. Display layouts are the Zentrale mode switch from Video 1. Decide which of these need approval. |
| 4 | **Research and web reading** | `recherche` via Brave MCP (`world.py:306-330`, off by default), `browser_oeffnen` / `lesen` / `auftrag` (optional Playwright, approval, stop points `browser.py:41-43`), `flug_suchen`, the researcher role. **About 45%.** | A keyless fallback: a stdlib fetch with `html.parser` text extraction for a given URL, plus RSS. Visible source citations. A result card on Zentrale. |
| 5 | **Email and messaging automation** | IMAP read with sorting and search (`mail.py:82-95, 161, 186`), SMTP send with approval (`:240`), `nachricht_senden` over Telegram, mail, iMessage, SMS, WhatsApp-MCP (`messenger.py:84-232`, approval), Telegram both ways in daemon mode (`run.py:90-139`), the post role, autopilot reply drafts. **About 65%.** | Reply in thread (`In-Reply-To`), attachments, drafts saved to IMAP, rules (an enquiry becomes a lead), timed sending. The WhatsApp MCP package name is unverified. Reading SMS or iMessage stays forbidden. |
| 6 | **Tasks and calendar** | Open items, reminders (recurring, `privat.py:267-363`), routines with a time feeding the scheduler, `termine_lesen` with conflict detection (`calendar_mod.py:105-123, 166-233`), `termin_anlegen`, the scheduler role, `lagebericht`. **About 50%.** | Move and delete appointments (CalDAV with href and etag), a free-slot finder, a travel-time check (the scheduler role's prompt mentions it, but no tool does it), timezone/RRULE fixes, `CALDAV_KALENDER`. Calendar on Zentrale (it uses `daten_sammeln(False)`, so no calendar). |
| 7 | **Content pipeline** (scripts, social posts, video concepts) | Marketing role writing to `werkstatt/projekte` (`team.py:259-276`), web designer, chatbot builder, `autopilot_auftrag` for background drafts. **About 30%.** | A structured pipeline: idea → script → posts per platform → video concept and shot list → editorial calendar, with a view. Posting via OAuth APIs (outward action, so approval). No image or video generation. |
| 8 | **Real-time translation, multilingual voice** | Nothing; everything is German: recognition `de-DE` (`webseite.py:442`), voice choice and `lang` (`:323-332, 360`), Whisper `language="de"` (`voice.py:570-571, 589`), `sprechtext` expands numbers in German only, Twilio `de-DE` (`telefon.py:164-166`). ElevenLabs `eleven_multilingual_v2` (`config.py:152`) could speak other languages. **About 5%.** | An interpreter-mode state (source and target language). In the browser, switch the recognition language per turn. Translate via `agent.text_anfrage` (effort medium) or Gemini. Voice chosen by language; skip `sprechtext` for non-German text. Two-language subtitles on the display. |
| 9 | **Geopolitical news analysis with globe** | See Video 1. **About 10%.** | See Video 1. |
| 10 | **Finance and KPI dashboard** (stocks, crypto, company KPIs) | Company KPIs complete (bookkeeping, pipeline, cashflow, required revenue, Claude costs), shown on Zentrale, the cockpit `/dashboard` (`dashboard.py`; server-side SVG in `dashboard_teile.py:183-305`) and `/sales`. Stocks, crypto and commodities: nothing. **About 45%.** | A market tool, watchlist config, time-series charts, caching, "Stand: Quelle, Uhrzeit" labels, a KPI-tile mode. |
| 11 | **Vision and biometrics** | `umschauen` (single still plus Claude vision, `camera.py:95-127`), `beleg_erfassen` (photo to booking), `speaker.py` voice profile (only decides whether Jarvis listens, never approves anything). **About 10%.** | See Video 2. |
| 12 | **Autonomous AI phone agent** | One-way announcement and SMS (`telefon.py`). **About 10%.** | See Video 3. |
| 13 | **Proactive assistance** | Autopilot checks: due follow-ups, mail, missing receipts, reminders, open items (`autopilot.py:232-301`), drafts into the inbox, announced quietly within quiet hours (`:95-107`). Briefings including calendar conflicts (`calendar_mod.py:230-232`). `verkaufsmuster` flags repeated objections. Rain warning for window jobs (`world.py:249-251`). **About 35%.** | Recommendations from calendar load, stress or recovery and close-rate correlation. A proposal object with an attached action that still goes through approval. Proposals that land in `agent.verlauf` so a "ja" works (§0.11). |

---

## 4. Decisions only the user can make

1. **Globe and visuals:** keep the existing 2D canvas globe, which passes the tests and needs no libraries, or bundle Three.js locally, which needs a static-file route and adjusted no-network tests. A CDN is ruled out by the tests and the "lädt nichts aus dem Netz nach" principle.
2. **Hand-tracking engine:** MediaPipe bundled locally (JS+WASM+model), a macOS Vision Swift helper, or Python mediapipe (breaks the stdlib rule).
3. **Phone agent:** which hosted, outbound-only voice-agent provider, at what cost, how the AI disclosure and transcript consent are worded, and accepting that there are no tool webhooks during the call.
4. **Wearables:** which source (Oura, Whoop, Apple Health export) and which login method.
5. **News and market data:** keyless (RSS, GDELT, stooq, ECB, CoinGecko) or keyed providers, plus their terms of use.
6. **Gesture approval in Dienst mode:** this needs a narrow POST path on the read-only display server.
7. **Live camera:** an explicit change of the "no continuous video" principle, plus the privacy handling of biometric data (local only; hidden in `ANZEIGE_DISKRET` mode).