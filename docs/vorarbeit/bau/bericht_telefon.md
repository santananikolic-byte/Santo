I researched use case 12 and wrote a tested stdlib recipe. Vapi is the right engine for the call, but I could not confirm that Vapi gives the transcript while the call is running without a webhook. Retell is the only candidate whose docs promise a live transcript of both sides over a connection the Mac opens itself.

All Vapi field names below come from the current OpenAPI spec (`curl https://api.vapi.ai/api-json`) and the Vapi docs source (`github.com/VapiAI/docs`, commit of 2026-10-06), not from memory. Your `config.py` defaults `LANDESVORWAHL` to `+43`, so the user is probably in Austria; I give Austria and Germany numbers where they differ.

## 1. Vapi

**Auth:** `Authorization: Bearer <private key>`, JSON body. Base URL is `https://api.vapi.ai`, or `https://api.eu.vapi.ai` for an organisation in the EU region (keep the key and the base URL in the same region).

**Endpoints:**
- `POST /call` starts the call.
- `GET /call/{id}` returns its state.
- `POST /phone-number` imports a number.
- `POST {call.monitor.controlUrl}` with `{"type":"end-call"}` hangs up mid-call (also `say`, `add-message`, `transfer`).
- Do not use `DELETE /call/{id}`: it deletes the record and does not end the call.

**Phone number:** You need `phoneNumberId` from an imported number. The docs say: "You cannot make outbound or international calls with a free Vapi number" (free numbers are US-only and inbound-only). Two ways to use Twilio:
- **Import once:** `POST /phone-number` with `{"provider":"twilio","number":"+43…","twilioAccountSid":"AC…","twilioAuthToken":"…","name":"Jarvis","smsEnabled":false}`. Importing rewrites that Twilio number's voice webhook to Vapi, so incoming calls to it go to Vapi. A separate Twilio number for this is cleaner.
- **Per call, without importing:** send `"phoneNumber":{"twilioPhoneNumber":TWILIO_NUMMER,"twilioAccountSid":…,"twilioAuthToken":…}` instead of `phoneNumberId`. This reuses the existing `TWILIO_*` keys, so only `VAPI_SCHLUESSEL` is new. The spec does not say whether this also rewrites the webhook; I did not test it.
- Either way, Twilio Console → Voice → Settings → Geo permissions must allow AT/DE. German local Twilio numbers are business-only and need an address in the area-code region plus a trade licence or commercial-register excerpt.

**Field changes that would break a request today:**
- `endCallFunctionEnabled` and `assistant.silenceTimeoutSeconds` are gone. I checked that the spec's validation rules reject both as unknown properties. Use `model.tools:[{"type":"endCall"}]` instead.
- `analysisPlan` (including `structuredDataPlan`) is marked deprecated. Use `artifactPlan.structuredOutputs` (inline) or `structuredOutputIds`. The results arrive in `call.artifact.structuredOutputs` as `{uuid:{name,result}}`.
- The structured-outputs guide only shows created outputs referenced by ID. The spec does allow inline ones. If inline is rejected, create it once with `POST /structured-output {name,schema}` and pass its ID.

**Request body:** this exact body passes my validator built from the spec. The model and voice values are my choices, picked for low latency and German support.
```json
{"name":"Jarvis: Tisch bei Lotus","phoneNumberId":"<id>",
 "customer":{"number":"+4312345678","name":"Lotus"},
 "assistant":{"name":"Jarvis Reservierung",
  "firstMessage":"Guten Tag, hier spricht der digitale Assistent von Herrn X - ich bin eine künstliche Intelligenz und rufe in seinem Auftrag an. Ich würde gern einen Tisch reservieren. Passt das gerade kurz?",
  "firstMessageMode":"assistant-speaks-first",
  "model":{"provider":"anthropic","model":"claude-haiku-4-5-20251001","temperature":0.3,"maxTokens":200,
           "messages":[{"role":"system","content":"<Auftrag: Personen, Datum, Uhrzeit, Name, erlaubtes Zeitfenster, keine weiteren Daten, KI-Frage ehrlich beantworten, am Ende alles wiederholen, dann endCall; bei Anrufbeantworter auflegen>"}],
           "tools":[{"type":"endCall"}]},
  "voice":{"provider":"azure","voiceId":"de-DE-KatjaNeural"},
  "transcriber":{"provider":"deepgram","model":"nova-3","language":"de"},
  "voicemailDetection":{"provider":"vapi"},
  "maxDurationSeconds":240,
  "endCallMessage":"Vielen Dank und auf Wiederhören!","backgroundSound":"off",
  "artifactPlan":{"recordingEnabled":false,
     "transcriptPlan":{"enabled":true,"assistantName":"Jarvis","userName":"Restaurant"},
     "structuredOutputs":[{"name":"reservierung","type":"ai","schema":{"type":"object","required":["reserviert"],
        "properties":{"reserviert":{"type":"boolean"},"datum":{"type":"string"},"uhrzeit":{"type":"string"},
        "personen":{"type":"integer"},"name_der_reservierung":{"type":"string"},
        "gegenvorschlag":{"type":"string"},"hinweise":{"type":"string"}}}}]},
  "monitorPlan":{"listenEnabled":false,"controlEnabled":true},
  "metadata":{"quelle":"jarvis"}}}
```

**Settings worth knowing:**
- **Model:** the Anthropic models Vapi accepts include `claude-haiku-4-5-20251001`, `claude-sonnet-4-6` and `claude-sonnet-5`. `claude-opus-5-5` is not on the list.
- **Voice:** an Azure voice ID fixes the language; `de-AT-IngridNeural` and `de-AT-JonasNeural` are standard Azure voices for Austria. ElevenLabs alternative: `{"provider":"11labs","voiceId":…,"model":"eleven_flash_v2_5","language":"de"}`; Flash v2.5, Multilingual v2 and v3 support German.
- **Speech recognition:** Deepgram `nova-3` supports `de`.
- **Duration limit:** `maxDurationSeconds` must be between 10 and 43200 (default 600).
- **No answering-machine message:** leaving `voicemailMessage` unset means it hangs up.
- **Recording is on by default.** `recordingEnabled:false` matters: in Germany, recording someone's non-public spoken words without consent is a crime under § 201 StGB; in Austria, check § 120 StGB.

**Example responses:**
- `POST /call` returns 201: `{"id":"…","status":"queued","phoneCallTransport":"pstn","monitor":{"listenUrl":"wss://…/<id>/transport","controlUrl":"https://…/<id>/control"},…}`
- `GET /call/{id}` after the end:
  - `{"status":"ended","endedReason":"assistant-ended-call","startedAt":…,"endedAt":…,"cost":…,"costBreakdown":{…}}`
  - `"artifact":{"messages":[{"role":"bot"|"user"|"system"|…,"message":"…","secondsFromStart":6.1,…}],"transcript":"Jarvis: …\nRestaurant: …","structuredOutputs":{"<uuid>":{"name":"reservierung","result":{…}}}}`
  - plus the deprecated `analysis{summary,structuredData}`.
- Status values: `scheduled|queued|ringing|in-progress|forwarding|ended|not-found|deletion-failed`.
- Useful `endedReason` values: `assistant-ended-call`, `customer-ended-call`, `customer-busy`, `customer-did-not-answer`, `voicemail`, `exceeded-max-duration`, `silence-timed-out`, `manually-canceled`, `twilio-failed-to-connect-call`.

**Live transcript without a webhook:**
- **Not documented.** Vapi's docs only describe live transcripts through webhooks (`serverMessages: transcript`) or the browser SDK. Search summaries of Vapi support threads say "/call/{id} does not provide a transcript while the call is ongoing", but I could not open the thread itself (HTTP 429 / Vercel checkpoint), so treat this as unconfirmed. `vapi listen` (their CLI) needs ngrok, so it is ruled out.
- **What polling does give live:** the status (dialling → ringing → connected with a timer). The full two-sided transcript arrives at the end. The recipe still shows any lines that do appear early. If the HUD replays the lines afterwards using `secondsFromStart`, it must be labelled as the transcript after the call ended (constraint 4).
- **Optional live audio:** the Mac can open `monitor.listenUrl` as an outgoing WebSocket. It sends binary PCM audio only, and the format is not documented (third-party reports say 16 kHz s16le, possibly stereo). That would allow live listening, or a homemade transcript via the local whisper. Treat it as experimental.
- **End detection:** `status` is `ended`, then keep polling until `artifact.structuredOutputs` appears. The docs say analysis "typically completes within a few seconds"; I allow up to 60 s. Hard stop at `maxDurationSeconds` + 180 s. No API rate limit is documented; I poll every 1.5 s and back off on errors.

**Cost per minute (vapi.ai/pricing):**

| Part | Price |
|---|---|
| Vapi hosting | $0.05 |
| Deepgram speech recognition | ~$0.0095 |
| Model | $0.008–0.045 |
| ElevenLabs voice | $0.015–0.024 |
| Twilio to AT landline / mobile | $0.0176 / $0.0495 |
| Twilio to DE landline / mobile | $0.0283 / $0.042 |

That is roughly $0.11–0.18 per minute, so about $0.30–0.60 for a 2–3 minute reservation call. New accounts get $5 free credit.

## 2. The other providers

- **Retell AI:** the best fit for constraint 1. `wss://api.retellai.com/v2/monitor-call/{call_id}` is an outgoing connection with `Authorization: Bearer <key>` and pushes the live transcript as JSON: `transcript_snapshot`, then `transcript_updated` (an item with the same `id` replaces the earlier one as a sentence grows), then `call_ended`. It only works once the call is `ongoing`, with at most 5 watchers.
  - The call itself is `POST https://api.retellai.com/v2/create-phone-call {from_number,to_number,override_agent_id,retell_llm_dynamic_variables}`, and `GET /v2/get-call/{id}` returns the transcript after the end.
  - It needs a stored agent (`/create-retell-llm` + `/create-agent`, `language` `de-DE`, `begin_message`) and an identity check (KYC) before outbound calls.
  - Retell-managed numbers reach 15 countries. Germany is $0.10/min; Austria is not on the list. The create-call reference says "only US", which contradicts the international-calling page. An Austrian caller ID needs an imported Twilio number via Elastic SIP Trunking.
  - Price: about $0.055 platform + $0.064 model (Claude 5 Sonnet) + $0.015 voice per minute, plus phone costs; $10 free credit.
- **Bland AI:** `POST https://api.bland.ai/v1/calls {phone_number,task,first_sentence,language:"de"|"babel-de",from,max_duration,record:false}`, then poll `GET /v1/calls/{id}`. The webhook is optional. The docs do not promise a live transcript; it is ready after the call. International calls need $5 of purchased credit, and `from` must be a number you own or uploaded from Twilio.
- **Twilio ConversationRelay:** ruled out. Twilio opens a WebSocket to a `wss://` server you host (the same goes for Media Streams), which needs inbound access to the Mac.

**Recommendation:** use Vapi as the default backend (polling, transcript after the call), with Retell as an optional backend if the user wants the real live transcript in the phone HUD.

## 3. Disclosure in the first sentence

EU AI Act Art. 50(1) has applied since 2 August 2026 under Art. 113. It requires that people "are informed that they are interacting with an AI system", and Art. 50(5) says this must happen "in a clear and distinguishable manner at the latest at the time of the first interaction". So the first sentence must say:
- that it is an AI ("ich bin eine künstliche Intelligenz"),
- on whose behalf it calls,
- and why.

The system prompt must also answer "Bist du ein Mensch?" honestly. Vapi has an optional `compliancePlan.recordingConsentPlan` (`verbal` or `stay-on-line`), which is only needed if recording is switched on.

## 4. Finding a nearby Asian restaurant (OpenStreetMap)

Overpass query (tested by script against the code; Overpass itself was not reachable from this sandbox):
```
[out:json][timeout:25];
nwr["amenity"="restaurant"]["cuisine"~"asian|chinese|japanese|thai|vietnamese|sushi|korean|ramen|indonesian|malaysian|taiwanese|cantonese|sichuan|nepalese|indian",i]["name"](around:2500,LAT,LON);
out center tags 40;
```
- The OSM wiki says cuisine values are combined with ";" (e.g. `chinese;thai`), so substring matching is correct.
- `out center` gives ways a centre point. Then take `phone`, or else `contact:phone`; if there are several numbers separated by ";", use the first.
- Drop entries without a phone number, sort by distance, show `opening_hours`, and normalise the number with the existing `telefon.nummer_pruefen`.
- `world.py` already has `OVERPASS_URLS` and a fallback server; reuse them.
- From this sandbox, overpass-api.de reset the connection and kumi.systems and private.coffee timed out, so the query is not checked against live data.

## 5. Recipe and tests

**Files:**
- `/tmp/claude-0/-home-user-Santo/960d1cbb-e7e7-5f3d-ab4f-b540bef2bbee/scratchpad/rezept/telefonagent_rezept.py` (stdlib only, German identifiers):
  - `overpass_asiatisch`, `restaurants_lesen`, `restaurants_suchen`: restaurant search
  - `anruf_koerper`, `anruf_starten`, `anruf_holen`: start and fetch the call
  - `anruf_verfolgen(schluessel, kennung, melden, takt=1.5, nachlauf=60)`: polling loop that reports status, each line, end or error
  - `ergebnis_lesen`: reads `structuredOutputs`, falling back to `analysis.structuredData`
  - `ENDE_DEUTSCH`: German texts for `endedReason`
  - `anruf_beenden(controlUrl)`: hang up
  - `WebSocketLeser`: minimal WebSocket reader that answers ping, handles split messages and close; client frames are masked
  - `retell_live_mitschrift`
- `/tmp/claude-0/-home-user-Santo/960d1cbb-e7e7-5f3d-ab4f-b540bef2bbee/tools/test_rezept.py`
- `/tmp/claude-0/-home-user-Santo/960d1cbb-e7e7-5f3d-ab4f-b540bef2bbee/tools/pruefe_schema.py`

**What was tested:**
- The request body against the Vapi spec. The validator does catch errors: it flagged `endCallFunctionEnabled`, `silenceTimeoutSeconds` and a wrong type when I planted them.
- The polling loop against a local fake Vapi server (statuses, new lines, waiting for the result).
- The WebSocket reader against a local server imitating the Retell stream (ping, split message, message over 125 bytes, close).
- Distance sorting of Overpass results.

**Not tested:** real Vapi or Retell calls (no keys here), and the encrypted `wss` connection to Retell (this sandbox only goes out through a proxy).

**Fitting it into Jarvis:**
- New config keys: `VAPI_SCHLUESSEL`, optionally `VAPI_TELEFON_ID`, optionally `RETELL_SCHLUESSEL`. Without a key, Jarvis says what is missing.
- New tool `restaurant_anrufen`, added to `FREIGABE_PFLICHTIG` and `NETZ_SENDEND`.
- The approval text should say: what (restaurant, number, people, time), why, and how (AI agent that identifies itself as AI, at most 4 minutes, no recording, about €0.30–0.60).
- Afterwards, `termin_anlegen` (already approval-required) only when `reserviert` is true.

## Sources
- [Vapi OpenAPI](https://api.vapi.ai/api-json) and [Vapi docs source](https://github.com/VapiAI/docs)
- Vapi: [Create call](https://docs.vapi.ai/api-reference/calls/create), [Get call](https://docs.vapi.ai/api-reference/calls/get), [Outbound calling](https://docs.vapi.ai/calls/outbound-calling), [Free telephony](https://docs.vapi.ai/free-telephony), [Import Twilio](https://docs.vapi.ai/phone-numbers/import-twilio), [Phone number create](https://docs.vapi.ai/api-reference/phone-numbers/create), [Live call control](https://docs.vapi.ai/calls/call-features), [Structured outputs](https://docs.vapi.ai/assistants/structured-outputs), [Pricing](https://vapi.ai/pricing)
- Vapi live-transcript thread (could not be opened): [support.vapi.ai](https://support.vapi.ai/t/29173773/getting-the-latest-transcript-from-an-ongoing-call)
- Retell: [Monitor call WebSocket](https://docs.retellai.com/api-references/monitor-call-websocket), [Create phone call](https://docs.retellai.com/api-references/create-phone-call), [Get call](https://docs.retellai.com/api-references/get-call), [International calling](https://docs.retellai.com/deploy/international-call), [Outbound calls](https://docs.retellai.com/deploy/outbound-call), [KYC](https://docs.retellai.com/accounts/kyc), [Pricing](https://www.retellai.com/pricing)
- Bland: [Send call](https://docs.bland.ai/api-v1/post/calls), [Call details](https://docs.bland.ai/api-v1/get/calls-id)
- Twilio: [ConversationRelay](https://www.twilio.com/docs/voice/conversationrelay), [DE pricing](https://www.twilio.com/en-us/voice/pricing/de), [AT pricing](https://www.twilio.com/en-us/voice/pricing/at), [DE regulatory](https://www.twilio.com/en-us/guidelines/de/regulatory), [DE voice guidelines](https://www.twilio.com/en-us/guidelines/de/voice), [Geo permissions](https://www.twilio.com/docs/sip-trunking/voice-dialing-geographic-permissions)
- EU AI Act: [Art. 50](https://artificialintelligenceact.eu/article/50/), [Art. 113](https://artificialintelligenceact.eu/article/113/)
- [§ 201 StGB](https://dejure.org/gesetze/StGB/201.html)
- [OSM Key:cuisine](https://wiki.openstreetmap.org/wiki/Key:cuisine)