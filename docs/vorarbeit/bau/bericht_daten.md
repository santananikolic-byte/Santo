# Keyless data sources for use cases 9, 10, 11 and 13: test results

Everything below marked "TESTED" was called from this sandbox on 2026-10-07 (curl, and Python `urllib` where noted). Everything marked "DOCS" comes from documentation only. Stooq could not be tested: it does not respond from here. Oura and Whoop could only be checked for reachability, because both need a login.

## (a) News in German

### A1. Google News RSS: TESTED 200, also with Python's default User-Agent
- **Search:** `https://news.google.com/rss/search?q=<urlencoded>&hl=de&gl=DE&ceid=DE:de`
  - Returns `application/xml`, about 100–140 KB, up to 100 items (105 seen).
  - Items are sorted by relevance, not by date, so always sort by `pubDate`.
  - Without a time filter the items covered 21.09–07.10 (about 2 weeks). With `when:1d` in `q`, all items fell within the last 24 h.
- **Search operators that worked:** `when:1d`, `when:7d`, `intitle:DAX`, `site:tagesschau.de`.
  - `Ölpreis when:1d` came back mostly as finanzen.net analyst noise. Use `intitle:Ölpreis` instead.
  - The industry query `Gebäudereinigung when:7d` returned 14 items.
- **Top stories:** `https://news.google.com/rss?hl=de&gl=DE&ceid=DE:de` returned 34 items.
- **Sections:** `https://news.google.com/rss/headlines/section/topic/WORLD?hl=de&gl=DE&ceid=DE:de` (also `BUSINESS`, `NATION`).
  - These answer with a 302 to `/rss/topics/<id>`. urllib follows it automatically.
  - WORLD returned 55 items, BUSINESS 70.
- **How to parse:** `ET.fromstring(body).findall("./channel/item")`. Fields per item:
  - `title`: has the form "Titel - Quelle". Strip the suffix `" - " + item.findtext("source")`.
  - `source`: the text is the outlet name; the `url` attribute is the outlet's domain.
  - `pubDate`: RFC822 in GMT. Read it with `email.utils.parsedate_to_datetime`.
  - `link`: a `news.google.com/rss/articles/CBMi…` redirect, not the article URL. Resolving it needs JavaScript, so do not try.
  - `description`: only an HTML `<a>` plus `<font>`. Ignore it.
- **Terms (from the feed's `<copyright>` element):** "made available solely for the purpose of rendering Google News results within a personal feed reader for personal, non-commercial use." No rate limit is documented. Cache results for 10–15 minutes.

### A2. tagesschau api2u: TESTED 200, JSON
- **`GET https://www.tagesschau.de/api2u/news`**
  - About 650 KB, 175 items.
  - Top-level keys: `news`, `regional`, `nextPage` (for example `…/api2u/news?date=261006`), `newStoriesCountLink`, `type`.
- **`?ressort=`** accepts `inland|ausland|wirtschaft|sport|video|investigativ|wissen`. `ausland` returned 57 items.
- **`?regions=`** accepts 1–16 for the federal states, comma-separated (1=BW, 2=BY, …, 10=NRW, 16=TH).
- **`GET https://www.tagesschau.de/api2u/homepage`** returned 11 top stories. Leave off the trailing slash: with it you get a 308.
- **`GET https://www.tagesschau.de/api2u/search/?searchText=Russland&pageSize=10&resultPage=0`**
  - Returns `{totalItemCount: 378, searchResults: [...]}`, newest first.
- **Item fields:**
  - `title`, `topline`
  - `firstSentence`: good for TTS. It only exists for tagesschau's own stories; regional NDR/BR items have none.
  - `date`: ISO with offset, e.g. `2026-10-07T12:00:16.371+02:00`. Works with `datetime.fromisoformat`.
  - `ressort`: `None` for regional items.
  - `tags`: a list of `[{tag}]`.
  - `type`: `story|video|webview`.
  - `breakingNews`: bool.
  - `details`: a JSON URL with the full text. Its `content[]` blocks have `type` text/headline/box and HTML in `value`. Tested: 5159 characters of text.
  - `detailsweb` / `shareURL`: the HTML page.
- **Region for the globe:** `geotags` was empty in all 175 items. Take the region from the URL path instead: `/ausland/europa|asien|amerika|afrika|ozeanien/…`.
- **Terms** (OpenAPI at https://raw.githubusercontent.com/bundesAPI/tagesschau-api/main/openapi.yaml): "Nutzung … für den privaten, nicht-kommerziellen Gebrauch ist gestattet, die Veröffentlichung hingegen nicht … Es ist unzulässig, mehr als 60 Abrufe pro Stunde zu tätigen." `details` calls count toward the 60. Cache for at least 5 minutes.

### A3. Deutsche Welle RSS: TESTED 200
- **Working feeds:**
  - `https://rss.dw.com/rdf/rss-de-all`: RSS 1.0/RDF, 83 items, 245 KB.
  - `https://rss.dw.com/xml/rss-de-all`: RSS 2.0, 60 KB.
  - `rdf/rss-de-top`, `rdf/rss-de-news`, `rdf/rss-de-deutschland` also work.
  - `rss-de-wirtschaft|eu|welt|pol|asien|nahost` return 200 with an empty 28-byte body. They do not exist.
- **Parsing RDF:** items are direct children of the root, not of `channel`.
  - `ns={'rss':'http://purl.org/rss/1.0/','dc':'http://purl.org/dc/elements/1.1/'}`
  - `root.findall('rss:item',ns)`
  - Fields: `rss:title`, `rss:link`, `rss:description` (plain teaser text), `dc:date` (ISO with Z), `dc:subject` (e.g. "Aktuelles", "Welt").
- **Terms:** I could not find DW's RSS terms.

### A4. GDELT DOC API: optional
- `https://api.gdeltproject.org/api/v2/doc/doc?query=Iran%20sourcelang:german&mode=artlist&format=json&timespan=1d&sort=datedesc` returned 429 here: "Please limit requests to one every 5 seconds". The sandbox shares its IP with other users. It would probably work on the iMac at 1 request per 5 s.

**Recommendation:**
- tagesschau for the general "Weltlage" and Germany overview (has `firstSentence` and full text).
- Google News search for free-form region or topic queries such as `"Iran USA when:1d"` or `"Russland when:1d"`.
- DW as a fallback.

## (b) Markets

### B1. Stooq: NOT reachable from here
- The TLS handshake to stooq.com and stooq.pl is reset after 8–12 s. The proxy log shows `ws_closed_mid_exchange` with 39 B received. This is not a policy 403.
- DOCS (https://github.com/pydata/pandas-datareader/issues/1012): since about March 2026, Stooq downloads (`/q/d/l/`) need an API key obtained via CAPTCHA at https://stooq.com/q/d/?s=spy.us&get_apikey. Without it Stooq returns HTML. The parameter name is not documented.
- Untested symbols for completeness: `^dax ^spx ^ndq ^ndx cb.f cl.f gc.f xauusd eurusd btcusd`. History URL: `https://stooq.com/q/d/l/?s=^dax&i=d`.
- **Do not use Stooq as the primary source.**

### B2. Yahoo Finance (unofficial): TESTED 200 via curl and urllib. Recommended primary source.
- **The User-Agent must be exactly `"Mozilla/5.0"`.**
  - urllib's default UA gets 429.
  - The `curl/8.5.0` UA gets 429.
  - A full Chrome UA string also gets 429.
  - Plain `Mozilla/5.0` gets 200.
- `v7/finance/quote` returns 401 because it needs a crumb. Do not use it.
- **Recommended: one request returns everything plus a sparkline.**
  ```
  https://query1.finance.yahoo.com/v8/finance/spark?symbols=%5EGDAXI,%5EGSPC,%5EIXIC,%5ENDX,%5ESTOXX50E,BZ%3DF,CL%3DF,GC%3DF,EURUSD%3DX,BTC-EUR,ETH-EUR,%5EVIX&range=1mo&interval=1d
  ```
  - About 8 KB of JSON. It is a dict keyed by symbol: `{symbol, timestamp[], close[], fulldayPrice, fulldayChange, fulldayChangePercent, chartPreviousClose, previousClose, dataGranularity, start, end}`.
  - `close[]` can contain `None`; filter it out.
- **Values seen on 07.10.:**

  | Instrument | Symbol | Value | Change |
  |---|---|---|---|
  | DAX | `^GDAXI` | 25153.54 | −1.16 % |
  | S&P 500 | `^GSPC` | 7818.93 | +0.58 % |
  | Nasdaq Composite | `^IXIC` | 27599.89 | |
  | Nasdaq 100 | `^NDX` | 31224.69 | |
  | Euro Stoxx 50 | `^STOXX50E` | 6190.03 | |
  | Brent | `BZ=F` | 102.01 USD | +1.42 % |
  | WTI | `CL=F` | 90.12 | |
  | Gold | `GC=F` | 4143.3 | |
  | EUR/USD | `EURUSD=X` | 1.1197 | |
  | Bitcoin in EUR | `BTC-EUR` | 74837 | |
  | Ethereum in EUR | `ETH-EUR` | 2318 | |
  | VIX | `^VIX` | 15.42 | |

  - Single stocks also work, e.g. `SAP.DE`.
- **Intraday:** `&range=1d&interval=5m` returned 36 points for the DAX and 73 for Brent. In this mode `previousClose` is filled.
- **Single-symbol detail:** `/v8/finance/chart/<sym>?range=5d&interval=1d`
  - `chart.result[0].meta` has `regularMarketPrice`, `previousClose`, `regularMarketChangePercent`, `currency`, `regularMarketTime` (epoch), `shortName`/`longName`, `fiftyTwoWeekHigh`/`fiftyTwoWeekLow`.
  - The series is in `indicators.quote[0].{open,high,low,close,volume}`.
  - Watch out: `chartPreviousClose` is the close before the start of the range, not yesterday's close (except with `range=1d`).
- **Delay:** the DAX `regularMarketTime` lagged by about 15 minutes. Label it "Quelle: Yahoo Finance, verzögert".
- **Terms:** undocumented and against the spirit of Yahoo's ToS. Personal use only; it may break at any time. Cache for at least 60 s.

### B3. CoinGecko: TESTED
- **Current prices:** `https://api.coingecko.com/api/v3/simple/price?ids=bitcoin,ethereum&vs_currencies=eur,usd&include_24hr_change=true&include_last_updated_at=true` returned 200:
  ```
  {"bitcoin":{"usd":83749,"usd_24h_change":-2.58,"eur":74795,"eur_24h_change":-2.16,"last_updated_at":1791367550},"ethereum":{...}}
  ```
  The response sets `Cache-Control: max-age=30`.
- **History:** `/api/v3/coins/bitcoin/market_chart?vs_currency=eur&days=30&interval=daily`
  - The first call got 429 with body `{"status":{"error_code":429,...}}`. After a 20 s pause it returned 200.
  - Result: `{prices:[[ms,price]...] (31 points, the last one is "now"), market_caps, total_volumes}`.
  - `days=7` without `interval` gave 169 hourly points.
- **Keyless rate limit (DOCS):** "IP-based, shared", with no number given. An optional free Demo key goes in the `x-cg-demo-api-key` header (or the `x_cg_demo_api_key` query parameter); it would belong in config/.env as an optional entry. Back off and cache on 429.

### B4. Official ECB EUR/USD rate: TESTED 200, CSV
- `https://data-api.ecb.europa.eu/service/data/EXR/D.USD.EUR.SP00.A?format=csvdata&lastNObservations=30`
- Parse with `csv.DictReader`; the columns are `TIME_PERIOD` and `OBS_VALUE`. Business days only; the last value was 2026-10-06 at 1.1269.
- `https://api.frankfurter.dev/v1/latest?base=EUR&symbols=USD` also returned 200 with the same ECB data.

**Fallback chain:** Yahoo spark → (Stooq, only if the user obtains a key) → CoinGecko for crypto and ECB for EUR/USD → otherwise say "Kursdaten gerade nicht verfügbar".

## (c) Wearables

### C1. Oura API v2
- **TESTED:** reachable. Without a token it returns 400 `{"detail":"Token is missing from Request Authorization Heade"}`.
- **Most important finding (from the OpenAPI spec at https://cloud.ouraring.com/v2/static/json/openapi-1.41.json):** "personal access tokens were deprecated in December 2025 and are no longer available for use." **OAuth2 is now required.**
  - Register an app at https://cloud.ouraring.com/oauth/applications. Up to 10 users are allowed without Oura's approval.
- **OAuth flow (DOCS, https://cloud.ouraring.com/docs/authentication):**
  - **Authorize:** `https://cloud.ouraring.com/oauth/authorize?response_type=code&client_id=..&redirect_uri=..&scope=daily heartrate personal&state=..` (PKCE is optional).
  - **Token:** `POST https://api.ouraring.com/oauth/token` (form-encoded) with `grant_type=authorization_code`, `code`, `redirect_uri`, `client_id`, `client_secret`.
  - **Refresh:** `grant_type=refresh_token`. Refresh tokens are single-use, so store the new one every time. Because it rotates, it needs a writable store, not a static .env value.
  - **Client-side flow** (`response_type=token`): the token lasts 30 days and cannot be refreshed.
  - **Redirect URI:** registered URIs act as a whitelist. The docs do not mention localhost. `http://localhost:8765/...` would be a browser-local redirect with no public ingress; check that it is accepted when registering the app. Otherwise the user can paste the code from the address bar.
  - **Scopes:** `email personal daily heartrate workout tag session spo2 heart_health`.
- **Endpoints** (GET with `Authorization: Bearer`; daily endpoints take `start_date` and `end_date` as YYYY-MM-DD; all responses are `{data:[...], next_token}`):
  - **`/v2/usercollection/daily_readiness`:** `{id, day, score, temperature_deviation, temperature_trend_deviation, timestamp, contributors:{activity_balance, body_temperature, hrv_balance, previous_day_activity, previous_night, recovery_index, resting_heart_rate, sleep_balance, sleep_regularity}}`
  - **`daily_sleep`:** `{day, score, contributors:{deep_sleep, efficiency, latency, rem_sleep, restfulness, timing, total_sleep}}`
  - **`sleep`** (detailed sleep periods): `average_hrv`, `average_heart_rate`, `lowest_heart_rate`, `total_sleep_duration` (seconds), `efficiency`, `type` ("long_sleep"), `bedtime_start`/`bedtime_end`, `readiness{…}`, `hrv{interval,items}`, `heart_rate{interval,items}`
  - **`heartrate`** with `start_datetime` and `end_datetime` as ISO: `{data:[{timestamp, bpm, source}]}`. Per the schema, `source` is one of `awake|rest|sleep|session|live|workout`.
  - **`daily_stress`:** `{day, day_summary ("stressful"…), stress_high (s), recovery_high (s)}`
  - Also available: `daily_resilience`, `daily_spo2`, `personal_info`.
- **Sandbox (TESTED 200):** `https://api.ouraring.com/v2/sandbox/usercollection/<same path>` with `Authorization: Bearer <any string>` returns fake data in exactly the real schema. Readiness returned 6 days, with sample `score: 80`. Use it only for tests in tests/abnahme.py, never on the display.
- **Rate limits:** 429 with `Retry-After` and `X-RateLimit-Limit/Window/Reset/Tier` headers; no numbers are published. Oura recommends webhooks, but those need public ingress and are forbidden here. Poll once or twice a day instead.

### C2. Whoop
- **TESTED:** reachable. `https://api.prod.whoop.com/developer/v2/recovery` returns 401 "Authorization was not valid".
- **Everything else is DOCS** (https://developer.whoop.com/api, /docs/developing/oauth, /docs/developing/rate-limiting):
  - OAuth2 only; there is no personal token. v1 is deprecated.
  - **Recovery:** `GET https://api.prod.whoop.com/developer/v2/recovery?start=<ISO>&end=<ISO>&limit=<=25>&nextToken=`
    - Fields: `score.recovery_score`, `score.resting_heart_rate`, `score.hrv_rmssd_milli`, `score.spo2_percentage`, `score.skin_temp_celsius`, and `score_state` ("SCORED").
    - That pages come back as `records[]` plus `next_token` is from my own knowledge, not confirmed in the docs.
  - **Other endpoints:** `/v2/cycle`, `/v2/activity/sleep`.
  - **OAuth URLs:** authorize at `https://api.prod.whoop.com/oauth/oauth2/auth`, token at `https://api.prod.whoop.com/oauth/oauth2/token`.
  - **Scopes:** `read:recovery read:cycles read:sleep read:profile …`. Add `offline` to get a refresh token.
  - `state` must be exactly 8 characters. Access tokens have `expires_in` 3600.
  - The docs show redirect URIs as `https://…` or a custom scheme; localhost is not documented.
  - **Rate limits:** 100 requests/min and 10,000/day.

### C3. Apple Health export.xml: parser TESTED on a synthetic export with the real structure
- **Getting the file:** iPhone Health app → profile → "Alle Gesundheitsdaten exportieren" gives `export.zip`, containing `apple_health_export/export.xml` and also `export_cda.xml`, `workout-routes/`, `electrocardiograms/`. The user transfers it via AirDrop or iCloud Drive. This is a file the user supplies, not a Mac database, so it is compatible with constraint 2.
- **Record types:**
  - `HKQuantityTypeIdentifierHeartRateVariabilitySDNN`: unit "ms". This is SDNN, not RMSSD, and the Watch measures it only sporadically, a few times a day. It has nested `<HeartRateVariabilityMetadataList><InstantaneousBeatsPerMinute bpm time/>` children.
  - `HKQuantityTypeIdentifierRestingHeartRate`: unit "count/min", about one per day.
  - `HKCategoryTypeIdentifierSleepAnalysis`: `value` is one of `HKCategoryValueSleepAnalysisInBed | …AsleepUnspecified | …AsleepCore | …AsleepDeep | …AsleepREM | …Awake`. Before iOS 16 it was `…Asleep`.
  - Also useful: `HKQuantityTypeIdentifierHeartRate`, `RespiratoryRate`, `OxygenSaturation`, `AppleSleepingWristTemperature`.
- **Record attributes:** `type, sourceName, sourceVersion, device, unit, creationDate, startDate, endDate, value`.
  - Dates look like `"2026-10-07 07:12:33 +0200"`; parse with `strptime(s, "%Y-%m-%d %H:%M:%S %z")`.
  - The file has an internal `<!DOCTYPE HealthData [...]>` block. expat (and so xml.etree) handles it.
- **Streaming read, tested:** `zipfile.ZipFile(p).open(name)` with `ET.iterparse(f, events=("end",))` and `el.clear()` after each Record. The zip does not need to be unpacked.
  - 4.9 MB took 0.14 s (about 35 MB/s). Extrapolated from that rate, a real multi-GB export should take about 1–2 minutes. Real exports are typically hundreds of MB to several GB (my estimate, not measured).
  - For GB-sized files, also take the root from the first `start` event and call `root.clear()` after each Record; `el.clear()` alone leaves empty children attached.
  - Run it in a background thread and cache the per-day results as JSON, keyed on the file's mtime.
- **Pitfalls:**
  - Watch, iPhone and third-party apps (for example the Oura app) write overlapping records. Merge sleep intervals, or filter by `sourceName`.
  - Assign each night to the day you wake up (the `endDate` date).
  - Do not count `Awake` or `InBed` as sleep.

### C4. Recovery score from Apple data only (tested in `health_parse.py`)
This follows standard HRV-guided-training practice (log HRV compared with a personal baseline, resting-pulse rise, sleep compared with need). It is a heuristic of my own, not a validated or medical score. In the UI, label it "eigene Schätzung, kein Medizinprodukt".
- **Baseline:** the previous 30 days, excluding today. If fewer than 14 days of HRV or resting pulse exist, or today has no HRV value, return `None` and have Jarvis say "zu wenig Daten".
- **Today's HRV:** the median of the SDNN samples that start between 00:00 and 08:00 local time.
- **Formula:**
  - `z_hrv = (ln HRV_heute − mean(ln HRV_basis)) / sd(ln HRV_basis)`
  - `z_puls = −(RHR_heute − mean RHR_basis) / sd RHR_basis`
  - Each part is `clamp(50 + 20·z, 0, 100)`.
  - Sleep part: `clamp(100 · Schlafstunden / 7.5, 0, 100)`.
  - `score = 0.45·hrv + 0.30·puls + 0.25·schlaf`. Without sleep data: `0.6·hrv + 0.4·puls`.
- **Bands:** 67 and above green, 34–66 yellow, below 34 red.
- **Synthetic test:** normal days scored 56–61. During a simulated bad week the score fell to between 18 and 42. That gives the "low recovery" signal needed to correlate with the sales log.

## (d) Coordinates for globe markers

### Built-in table: recommended
All 38 points below were checked against Nominatim; every one was within 0.13°.
```
Berlin 52.52,13.405  Wien 48.208,16.373  Bern 46.948,7.447  Washington 38.895,-77.036  Moskau 55.756,37.617
Kiew 50.45,30.524  Teheran 35.689,51.389  Jerusalem 31.778,35.235  Gaza 31.5,34.47  Beirut 33.894,35.502
Damaskus 33.513,36.292  Bagdad 33.315,44.366  Riad 24.713,46.675  Ankara 39.934,32.86  Peking 39.904,116.407
Taipeh 25.033,121.565  Tokio 35.676,139.65  Pjöngjang 39.039,125.762  Seoul 37.566,126.978  Neu-Delhi 28.614,77.209
Islamabad 33.684,73.048  London 51.507,-0.128  Paris 48.857,2.352  Rom 41.903,12.496  Madrid 40.417,-3.704
Warschau 52.23,21.012  Brüssel(EU) 50.85,4.352  Brasília -15.794,-47.882  Ottawa 45.421,-75.697
Mexiko-Stadt 19.433,-99.133  Caracas 10.481,-66.904  Kairo 30.044,31.236  Pretoria -25.747,28.229
Canberra -35.281,149.13  Frankfurt 50.11,8.682  New York 40.713,-74.006  Shanghai 31.23,121.474  Straße von Hormus 26.57,56.25
```
For whole-country focus, Nominatim's representative points are: Russland 64.69,97.75; Iran (my own value) about 32.4,53.7; USA about 39.8,-98.6. A region like "Nahost" is not in Nominatim at all, so it needs its own entry, about 31.5,40.

### Other options
- **Nominatim:** TESTED 200 as a fallback.
  - `https://nominatim.openstreetmap.org/search?q=<name>&format=jsonv2&limit=1&accept-language=de`
  - Returns `lat` and `lon` as strings, `addresstype` (city/country/strait), and a `boundingbox` that can drive the zoom level.
  - German names work: Kiew, Straße von Hormus, Russland, Taiwan. "Nahost" returns nothing.
  - Usage policy: at most 1 request/s, an identifying User-Agent, cache the results, and credit ODbL.
- **Open-Meteo geocoding** (already used in world.py): 4 of 5 requests timed out here, and "Kiew" returned Kiewa in Australia. Not suitable for countries.
- **REST Countries:** v3.1 is shut down; it now answers "This API version has been deprecated". v5 needs an account. Do not use.
- **Better globe outline:** TESTED 200.
  - `https://cdn.jsdelivr.net/npm/world-atlas@2/land-110m.json` (55 KB) and `countries-110m.json` (108 KB, 177 countries, `properties.name` in English).
  - Both are TopoJSON with `transform`, so they need a small arc decoder (about 30 lines of JS).
  - They can be copied into the module so the app stays offline, replacing the hand-drawn `LAND` polygons in ansicht.py.

## Extra for use case 11 (hand tracking runs in the browser; Python stays standard-library only)
All of these returned 200:
- `https://cdn.jsdelivr.net/npm/@mediapipe/tasks-vision@1.1.0/vision_bundle.mjs` (156 KB). `@latest` currently resolves to 1.1.0.
- `…/wasm/vision_wasm_internal.js` and `…/wasm/vision_wasm_internal.wasm` (13 MB).
- Model: `https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker/float16/1/hand_landmarker.task` (7.8 MB).

## Side observation
The proxy log shows that `overpass-api.de` (which world.py uses for business search) also failed from this sandbox, with the same tunnel close as Stooq.

## Test scripts
All in `/tmp/claude-0/-home-user-Santo/960d1cbb-e7e7-5f3d-ab4f-b540bef2bbee/scratchpad/`:
- `parse_news.py`: Google News, tagesschau and DW parsing.
- `yahoo_test.py`: per-symbol Yahoo chart calls with the working User-Agent.
- `gen_health.py`: builds the synthetic Apple Health export.
- `health_parse.py`: streaming parser plus recovery score.
- `orte_check.py`: coordinate check against Nominatim.
- `dl/`: raw responses, including the Oura OpenAPI spec (`dl/oapi.json`) and sandbox samples (`dl/sb_*.json`).