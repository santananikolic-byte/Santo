**Verdict:** the overall architecture holds up. That covers the stdlib core, the single display store with long-polls, outbound-only Vapi/Retell calls, MediaPipe served from local files, and the canvas globe. No package plans inbound webhooks, reading Mac databases, non-stdlib Python or keys outside `.env`. The plan is not ready to hand to builders: items 1–11 below are must-fix, because they break existing tests, corrupt the conversation, or leave Video 2 unusable in both operating modes. I checked every reference against the code on this branch.

### Must fix before building

1. **P4 – `meldung_einbringen` breaks the Claude conversation (P5 and P3 also affected).**
   - `_denk_sperre` is an RLock (`agent.py:215`), so a call from the same thread is not blocked.
   - P5's tool `belastung_pruefen` calls `Vorschlaege.einbringen`, which calls `meldung_einbringen` while `_denken` sits between the assistant `tool_use` message and the user `tool_result` message. The inserted user and assistant turns end up between them, and the API rejects the request with a 400.
   - `_denken` only cleans up the history on refusal or the monthly limit (`agent.py:552,581`). After that, every following turn fails until the history is cleared.
   - Calls from other threads (scheduler, autopilot, phone-agent thread) also block for up to `FREIGABE_TIMEOUT` (120 s) while a turn waits for an approval.
   - Fix:
     - Collect messages in a pending list under its own small lock.
     - Flush that list at the start of the next `_denken`, before the user turn is appended. Remove duplicates by text.
     - When a proposal comes from a tool, only return its text; never inject it.
     - Inject only proposals and questions, not every autopilot notice, because each injected pair costs tokens on every later call until it is trimmed.

2. **P6 – the `voice.py` rewrite breaks existing checks (`abnahme.py:1943-1960`, `2198-2242`, `2264-2287`).** Those tests replace these exact entry points:
   - `Stimme._elevenlabs_holen(text, vorher="", nachher="")`, returning `b"mp3"`. `vorige` is only passed as a keyword once request ids exist.
   - `_systemstimme_sprechen`, which must be called once with the joined remaining text.
   - `abspielen`, and `urllib.request.urlopen` with the `request-id` header.
   - The Telegram test expects `sprachdatei_erzeugen` to go through `_elevenlabs_holen`. With P6's `sprachaudio()` it would call the real API with the fake key `"test"` and the check fails.

   Fix:
   - Keep these entry points. Choose the format through an instance attribute that defaults to mp3, and keep `_systemstimme_sprechen(rest)` as the single fallback that splits into chunks and computes levels itself.
   - `pegel_aus_wav` must survive bytes that are not WAV: catch `wave.Error` and publish without a level curve.

3. **Video 2 does not work end to end in either mode, and several tools target the wrong server (P1, P5, P6, P7).**
   - **Dienst mode:** `/sehen` sits on the read-only display (port 8766). `POST /api/sicht/messung` and `/api/freigaben` return 404, so no measurement is stored and no gesture is possible.
   - **Web mode:** the server never speaks. The `stimme` channel only carries `satz` events and the server state never becomes `spricht` (`run.py:499`), so the orb on `/sehen` never moves. Proposals are spoken by the main page in another tab.
   - **P7 `fenster_anordnen`:** opens `localhost:8765`. In Dienst mode the display and the display store live on 8766. Use the same port detection as `run.anzeige_oeffnen` (8766 first).
   - **P6 `dolmetscher_starten`:** opens `8765/dolmetscher`, which does not exist in Dienst mode.
   - Fix:
     - Add a per-feature table to the plan showing what works in Dienst mode and what works in web mode.
     - Tools must say "geht nur in der Web-App" when that is the case.
     - For web mode, put the camera panel and orb into the main page, or let `/sehen` speak the messages itself. Also let `satz` events drive an orb pulse labelled "nachempfunden".
     - Either add a narrow, number-only POST exception for measurements on the display, or list the limitation in `nicht_moeglich`.

4. **P4 – the approval cannot say "what" for the new tools.**
   - `termine_absagen`, `termin_verschieben` and `termin_wiederherstellen` only receive 8-character hash ids. `mail_antworten` receives a Message-ID, and `ordnen_ausfuehren` a `plan_id`. The approval would read "Termine a1b2c3d4 absagen", which breaks constraint 3.
   - P7 relies on an "erweitern" hook that P4 never defines.
   - Fix:
     - Add a resolver map in `freigabe.py`, `FREIGABE_AUFLOESEN[name](werkzeuge, argumente) -> dict`, called in `Werkzeuge._freigabe`. It turns ids into title, time and old→new time, mail headers into recipient and subject, and a plan id into its list of moves.
     - Write the entries for P4's own four tools.
     - Replace the ambiguous template syntax (`{text:120}`, `{ort: in }`, `{an:ein/aus}`) with small functions.
     - P7: add a dependency on P4, and add `required: ['plan_id','begruendung']` to both `ordnen_*` tools, otherwise P4's catalog test 4 fails.

5. **P2 – tool results are cut at 6000 characters (`agent.py:617-623`).**
   - `lagebild` puts `abschnitte` (four regions of items with long Google redirect URLs) before `anweisung`. The keywords and the required speaking order are cut off, so the topic sequence on the display cannot sync. The same happens to `hinweis` in `weltlage`.
   - Fix: put `anweisung`/`hinweis` first, drop `url` from tool results, cap the teaser at about 160 characters, and test that the JSON stays under 5500 characters.

6. **P1/P2 – the topic sequence (`folge`) advances too early and matches the wrong words.**
   - The per-step timer (30 s) starts when the sequence is written, while Opus is still thinking (often 15–40 s). It should start at the first `stimme` event newer than the sequence.
   - The speech-text conversion turns "S&P 500" into "S und P 500", so that keyword never matches. Use fixed simple keywords ("Märkte", "Betrieb", region names) and run the same folding over the keyword.
   - The instruction must forbid an opening list of topics, or the intro sentence skips ahead through the steps.

7. **P1 – `Anzeige.warten` loops forever with an injected clock.** Its deadline comes from the injected `uhr`; a fake clock never advances. Wait on `time.monotonic` and use `uhr` only for `seit`/`bis`. Also, `zeigen(... dauer_s or ANZEIGE_DAUER)` makes "0 = no expiry" impossible.

8. **P1/P5 – MediaPipe files and caching.**
   - `/sicht/dateien/*` and MediaPipe's own fetches carry no `schluessel`, so they get 403 whenever a token is set (`web --offen`, also on localhost). Either exempt the static files and the OAuth callbacks from the token check (keep the Host check), or pass an explicit fileset with `wasmLoaderPath`/`wasmBinaryPath`/`modelAssetPath` that include `?schluessel=`.
   - `max-age=31536000, immutable` on an unversioned path keeps the old JS for a year after a version bump. That is exactly the JS/WASM mismatch the research warned about. Put the version in the path: `/sicht/dateien/0.10.35/...`.
   - Pin sha256 hashes for all six files now (jsDelivr is reachable) instead of trusting whatever the first download returns.

9. **P2 – `webseite_lesen` does not block internal addresses.**
   - Checking "the final URL after redirects" is too late: urllib has already requested the internal host. Hostnames that resolve to private addresses also pass.
   - Fix: resolve every hop with `getaddrinfo` inside a custom `HTTPRedirectHandler.redirect_request` and reject private, loopback, link-local and reserved addresses.
   - Policy: `browser_oeffnen` requires approval precisely because the address itself discloses something (`tools.py:493-496`). `webseite_lesen` is the same action without approval. Decide this explicitly and write it down.

10. **P7 – `datei_oeffnen` uses a blocklist.**
    - `mac.py:58-59` says "eine Positivliste ist sicherer als jede Sperrliste". The blocklist misses `.shortcut`, `.mobileconfig`, `.scptd`, `.zsh`, `.bash`, `.osax`, `.plugin`, `.service` and more.
    - Use an allowlist of document, image and media types, and apply `MacZugriff.gesperrt()`. Otherwise `config/.env` could be opened in TextEdit and then sent to Claude in a `bildschirm_bedienen` screenshot.

11. **P7 – Shortcuts can bypass the hard constraints.**
    - If shortcut output is returned to Claude, a shortcut in the "Jarvis" folder (for example "Kontakte holen") becomes a side door to Contacts, Calendar or Messages (constraint 2).
    - A shortcut that sends messages bypasses constraint 3.
    - Return only ok/error, never stdout, and ask for approval the first time each shortcut name runs.

### Should fix

12. **P3 – credentials and disclosure.**
    - By default the master `TWILIO_TOKEN` goes to Vapi in the body of every call. Make the one-time import (`VAPI_TELEFON_ID`, ideally a Twilio subaccount or separate number) the recommended path, and say in the setup and in the approval's "how" that Vapi gets Twilio access.
    - The gap map's disclosure "wird mitgeschrieben, nicht aufgenommen" is missing from the first sentence.

13. **Guessed or unverified API details.**
    - Retell `call_analysis.custom_analysis_data` is not in the research; it needs post-call analysis configured on the agent. Mark it "zu prüfen".
    - `VAPI_STIMME='de-DE-ConradNeural'` was not validated. The research validated `de-DE-KatjaNeural` and suggested `de-AT-*` voices, since the user is likely in Austria.
    - The control-URL check "host ends with vapi.ai" is unverified, because the research did not record the host. Trust the URL from the POST response and require https.

14. **Python 3.9.** `datetime.fromisoformat` rejects a trailing `Z` before 3.11. That affects Vapi `startedAt`, DW `dc:date`, Whoop and Oura timestamps; replace `Z` with `+00:00` first. Also forbid `X | None` annotations.

15. **P5 – OAuth tokens and two processes.**
    - When the Dienst and the double-clicked web app both run, both schedulers can use the same single-use Oura/Whoop refresh token, and reuse can revoke the grant. Reload `.env` and take a file lock before refreshing, and let only one process poll.
    - The OAuth `state` lives in the memory of the process that started the flow (the CLI), while the redirect lands on the web app. Store it in the DB or a file.

16. **P1 – discreet mode has gaps.** The contract has no filter for the `sicht` channel (health data; the risk list claims it is hidden), for `hochfahren.begruessung` (contains appointment titles and customer names), or for `/api/sicht/stand` on the display.

17. **Merge order between packages.**
    - Every package appends at the same anchors: the catalog, dispatch, `__init__`, `_get`/`_post`, `main()`, the system prompt and `_bausteine_sammeln` (P2, P5 and P7 all edit it). Three modules are placed "directly after `modules/sprechtext`" and four "after `modules/world`".
    - The first merge should fix the final build list, add empty labelled section anchors in P1…P7 order (stable tool order also keeps the prompt cache), and fix the order of lines in `__init__`.
    - P5's `getattr(self,'vorschlaege',None)` silently returns None if its line lands before P4's; look it up when the check runs instead.

18. **Dependencies and package size.**
    - P1's `/sehen` depends on P5 (all `/api/sicht/*` routes and the files) and on P4 (the approval fields). Move `SEITE_SEHEN` to P5.
    - P1 is too large to be the first merge. Split `anzeige.py` and its routes from the pages.
    - P7 depends on P4.

19. **Research files are not in the repo.** The plan points builders to scratchpad files (`telefonagent_rezept.py`, `health_parse.py`, `vision_prototyp/*`). Those exist only in this session's `/tmp`, so parallel builders will not have them. Commit them under `docs/vorarbeit/`, outside `src/` so they stay out of `jarvis.py`.

20. **Some tests are not actually offline.**
    - P7 test 10 (`/api/hochfahren`) runs `_bausteine_sammeln`, which calls the weather service (Open-Meteo). `hardware_bericht` also opens a socket that cannot be replaced in tests.
    - P2 test 28 calls the weather service the same way.
    - On a Mac, P6 test 22 really opens a browser window. Make the opener injectable.
    - P1 test 11 goes through `zentrale_daten`, which can start place lookups.

21. **Background runs switch the display.** The autopilot's researcher (`weltlage`) and controller (`maerkte`) would switch the Zentrale for minutes with nobody talking. Dispatch should pass `zeigen=not self.im_hintergrund()`.

22. **P4/P5 details.**
    - The CalDAV query window labels local midnight as UTC (`calendar_mod.py:172-173`); include it in the timezone fix.
    - P5's close rate (won ÷ all calls) differs from the existing `verkaufsmuster` (won ÷ (won + lost)). Use the existing definition.

23. **P6 defaults.**
    - `STIMME_IM_BROWSER=True` silently moves every web answer from free browser speech to paid ElevenLabs/Fish for users who already have a key. Make it default False or ask once.
    - In "auto" mode, choose Fish only if `FISH_STIMME_ID` is also set; otherwise it uses a default voice that is probably not German.
    - Gemini translation is capped at `GEMINI_MAX_TOKENS=600`, so long utterances get cut. That needs a `max_tokens` parameter in `router.gemini_fragen`, and `router.py` is not in P6's file list.

24. **Not covered and not listed in `nicht_moeglich`.**
    - Use case 5: attachments, timed sending, and mail rules (an enquiry becomes a lead).
    - Use case 6: calendar on the Zentrale.
    - Video 2: "the gesture answers the proactive question". In the plan the gesture only confirms the later `termine_absagen` approval, after a spoken "ja". Either add "accept proposal by gesture" or list it honestly.

25. **Build traps.**
    - `KANAELE` collides with `messenger.KANAELE`, and `adresse_pruefen` with `browser.adresse_pruefen`. The build renames them automatically, but the plan claims they are unique. Rename to `ANZEIGE_KANAELE` and `webadresse_pruefen`.
    - A bare word `config` in a page's JS line aborts the build (`build_single.py:263-277`), and `config.x` inside any string gets rewritten.
    - Add `modelle/` to `.gitignore` (about 20 MB).
    - Chrome with a fresh profile needs `--no-first-run --no-default-browser-check`.

26. **Minor.**
    - Each embedded iframe opens its own long-poll, which conflicts with the six-connections-per-host budget. The parent page should forward the data to the iframe.
    - `kennzahl_setzen` appends a row per call (not one per day) and would put health values into the general KPI table.
    - The phone HUD should call `zeigen('anruf',…,120)` again at the end of the call.
    - `belastung_pruefen` must return '' when `VORSCHLAEGE_AN` is off.
    - The boot greeting can be silent without a user click (browser autoplay rules); show "Ton einschalten".
    - The new Claude features (daily greeting, translation fallback, content planning, call analysis) eat into the default 15 € monthly limit (`MONATSLIMIT_EURO`).