# P3-telefonagent Telefonassistent: Lokale in der Nähe (OSM), autonomer Reservierungsanruf über Vapi (optional Retell mit Live-Mitschrift), Telefon-HUD, Kalendervorschlag

Anwendungsfaelle: ['12', 'Video 3']
Neue Dateien: ['src/modules/lokale.py', 'src/modules/telefonagent.py', 'src/modules/netzsocket.py']
Geaenderte Dateien: ['src/modules/tools.py (4 tools, sets, __init__, zustand, anrufen description)', 'src/modules/freigabe.py (P4-owned registry: one entry, delivered as text)', 'src/modules/telefon.py (zustand hint text only)', 'src/run.py (ausgabe wiring, 2 lines)', 'src/config.py (+ konfig_uebersicht)', 'src/modules/setup_wizard.py (ZUGAENGE tuple)', 'config/.env.beispiel', 'build_single.py', 'tests/abnahme.py (pruefung_telefonagent + main)']
Abhaengig von: ['P1-buehne', 'P4-buero']

## Spezifikation
Owner of lokale.py, telefonagent.py and netzsocket.py. Start from the tested recipe in scratchpad/rezept/telefonagent_rezept.py and translate it into this module structure.

A. lokale.py

KUECHEN: key → cuisine regex
- asiatisch: 'asian|chinese|japanese|thai|vietnamese|sushi|korean|ramen|indonesian|malaysian|taiwanese|cantonese|sichuan|nepalese|indian'
- chinesisch: 'chinese|cantonese|sichuan'
- japanisch: 'japanese|sushi|ramen'
- thai: 'thai'
- vietnamesisch: 'vietnamese'
- indisch: 'indian|nepalese'
- italienisch: 'italian|pizza'
- oesterreichisch: 'austrian|regional'
- griechisch: 'greek'
- tuerkisch: 'turkish|kebab'
- egal: '' (no cuisine filter)

lokale_abfrage(breite, laenge, regex, radius=2500, anzahl=40) -> str
- '[out:json][timeout:25];nwr["amenity"="restaurant"]["cuisine"~"<regex>",i]["name"](around:<radius>,<lat>,<lon>);out center tags <anzahl>;'
- Without a regex, the cuisine clause is left out.

lokale_lesen(daten, breite, laenge) -> list
Each entry:
- name
- kueche: tags['cuisine'], with ';' replaced by ', '
- adresse: street, house number, postcode, city
- telefon: phone, else contact:phone; first part before ';'; normalised with telefon.nummer_pruefen; invalid → ''
- oeffnungszeiten: opening_hours
- web
- lat and lon: node coordinates, or the way 'center'
- abstand_m: haversine distance, integer
Entries without a name are dropped. Sorted by abstand_m.

class Lokale(welt, holen=None)
suchen(ort='', kueche='asiatisch', radius=2500, nur_mit_telefon=True)
- ort defaults to config.WETTER_ORT.
- Geocode via welt.ort_finden.
- Query via holen, or by default welt._overpass_holen, which already has the fallback server.
- Returns at most 10: {'ok', 'ort', 'anzahl', 'lokale', 'quelle': 'OpenStreetMap (ODbL)', 'text': 'Ich habe 6 asiatische Lokale in der Nähe von Wien gefunden. Am nächsten: Lotus, 350 Meter, Telefon +43 1 234 5678, Öffnungszeiten laut Karte: Mo-Sa 11:30-22:00.'}
- Nothing found: 'In %s finde ich auf der Karte kein passendes Lokal mit Telefonnummer.'
- NEVER creates a lead.
- Display: anzeige.zeigen('recherche', {'titel': 'Lokale in der Nähe', 'liste': [{'titel': name + ' · ' + abstand, 'text': kueche + ' · ' + telefon + ' · ' + oeffnungszeiten}], 'quellen': [{'titel': 'OpenStreetMap', 'url': 'https://www.openstreetmap.org'}]})

B. netzsocket.py: minimal RFC 6455 client, stdlib socket, ssl, base64, hashlib, os, struct

class WebSocketLeser(url, kopfzeilen=None, timeout=30, verbinden=None)
- url must be wss:// or ws://.
- Handshake: GET with Sec-WebSocket-Key (16 random bytes, base64) and Sec-WebSocket-Version 13.
- Accept header = base64(sha1(key + '258EAFA5-E914-47CA-95DC-C5AB0DC85B11')), else WebSocketFehler('Handshake abgelehnt').
- nachrichten() is a generator of str:
  - answers ping with a masked pong;
  - assembles fragmented messages;
  - handles 126 and 127 extended lengths;
  - stops on close.
- Client frames are always masked.
- schliessen() sends a close frame.
- verbinden(host, port, tls) -> socket can be injected for tests.

C. telefonagent.py

Texts
- STATUS_PHASE: scheduled → 'vorbereitet', queued → 'waehlt', ringing → 'klingelt', in-progress → 'verbunden', forwarding → 'verbunden', ended → 'beendet'.
- ENDE_DEUTSCH:
  - assistant-ended-call: 'Jarvis hat das Gespräch beendet.'
  - customer-ended-call: 'Das Restaurant hat aufgelegt.'
  - customer-busy: 'Besetzt.'
  - customer-did-not-answer: 'Niemand hat abgenommen.'
  - voicemail: 'Anrufbeantworter – ich habe aufgelegt, ohne etwas zu hinterlassen.'
  - exceeded-max-duration: 'Die Höchstdauer war erreicht.'
  - silence-timed-out: 'Es war zu lange still.'
  - manually-canceled: 'Du hast das Gespräch abgebrochen.'
  - twilio-failed-to-connect-call: 'Twilio konnte nicht verbinden.'
  - Default: 'Das Gespräch ist beendet (%s).'

RESERVIERUNG_SCHEMA
- Exactly as in the research: required ['reserviert']; properties reserviert (bool), datum, uhrzeit, personen (int), name_der_reservierung, gegenvorschlag, hinweise.

auftraggeber()
- config.NUTZER_NAME, unless it is empty or 'Chef'; then config.FIRMA.

erster_satz(auftraggeber)
- 'Guten Tag, hier spricht der digitale Assistent von %s. Ich bin eine künstliche Intelligenz und rufe in seinem Auftrag an. Ich würde gern einen Tisch reservieren – passt das gerade kurz?'

auftrag_text(restaurant, datum, uhrzeit, personen, name, rueckruf, spielraum_min, hinweise)
The German system prompt for the voice agent. Rules:
- Sie-Form; short sentences.
- Goal: a table for N people on <weekday, date> at <time>, in the name of <name>.
- Acceptable window: ± spielraum minutes. If that does not work, ask for the nearest alternative, note it as gegenvorschlag, and do NOT accept it.
- Give only: name, number of people, time, and the callback number if one exists. Otherwise say the guest will call back.
- Never give payment or card details. Never agree to a deposit or prepayment; say the guest will clarify that.
- If asked 'Sind Sie ein Mensch?', answer honestly: an AI.
- Answering machine or phone menu: hang up.
- At the end, repeat every detail, say goodbye, then call endCall.
- Extra hints only if given.

vapi_koerper(ziel, restaurant, auftrag, erster, telefon_id='', twilio=None) -> dict
- name: 'Jarvis: Tisch bei <restaurant>'
- Phone: phoneNumberId if telefon_id is set, otherwise phoneNumber = {'twilioPhoneNumber', 'twilioAccountSid', 'twilioAuthToken'} from the TWILIO_* keys.
- customer: {'number': E.164, 'name': restaurant[:40]}
- assistant:
  - name: 'Jarvis Reservierung'
  - firstMessage: erster; firstMessageMode: 'assistant-speaks-first'
  - model: {'provider': 'anthropic', 'model': config.VAPI_MODELL, 'temperature': 0.3, 'maxTokens': 200, 'messages': [{'role': 'system', 'content': auftrag}], 'tools': [{'type': 'endCall'}]}
  - voice: {'provider': 'azure', 'voiceId': config.VAPI_STIMME}
  - transcriber: {'provider': 'deepgram', 'model': 'nova-3', 'language': 'de'}
  - voicemailDetection: {'provider': 'vapi'}
  - maxDurationSeconds: clamp(TELEFONAGENT_MAX_MINUTEN·60, 60, 600)
  - endCallMessage: 'Vielen Dank und auf Wiederhören!'
  - backgroundSound: 'off'
  - artifactPlan: {'recordingEnabled': False, 'transcriptPlan': {'enabled': True, 'assistantName': 'Jarvis', 'userName': 'Restaurant'}, 'structuredOutputs': [{'name': 'reservierung', 'type': 'ai', 'schema': RESERVIERUNG_SCHEMA}]}
  - monitorPlan: {'listenEnabled': False, 'controlEnabled': True}
- metadata: {'quelle': 'jarvis'}
- NEVER include endCallFunctionEnabled, silenceTimeoutSeconds or analysisPlan.

class Telefonagent(memory, anzeige=None, holen=None, uhr=time.time, schlaf=time.sleep)
Attributes:
- agent = None: set in agent_setzen.
- ausgabe = None: callable(text), wired by run.py.
- _laeuft: the current call.
Own table:
- SCHEMA_TELEFONAGENT: CREATE TABLE IF NOT EXISTS telefonagent_anrufe (id INTEGER PRIMARY KEY AUTOINCREMENT, kennung TEXT, anbieter TEXT, restaurant TEXT, nummer TEXT, auftrag TEXT, status TEXT, ergebnis TEXT DEFAULT '', mitschrift TEXT DEFAULT '', kosten REAL, angelegt TEXT, beendet TEXT DEFAULT '')
- Also writes the existing anrufe table with art 'telefonassistent'.

verfuegbar()
- VAPI_SCHLUESSEL is set, or (anbieter 'retell' and RETELL_SCHLUESSEL, RETELL_AGENT_ID and RETELL_NUMMER are all set).

zustand()
- {'eingerichtet', 'anbieter', 'gespraech_moeglich': verfuegbar(), 'live_mitschrift': anbieter == 'retell', 'hinweis'}

reservieren(restaurant, nummer, datum, uhrzeit, personen, name='', spielraum_minuten=30, hinweise='', begruendung='') -> dict
Validation, each with its German error:
- No key: 'Für Anrufe durch den Telefonassistenten fehlt VAPI_SCHLUESSEL in config/.env (dashboard.vapi.ai → API Keys → Private Key). Ansagen und SMS über Twilio gehen weiter.'
- No transport: 'Es fehlt eine Nummer, von der aus angerufen wird: VAPI_TELEFON_ID (in Vapi importierte Twilio-Nummer) oder TWILIO_SID, TWILIO_TOKEN und TWILIO_NUMMER.'
- nummer goes through nummer_pruefen.
- datum: YYYY-MM-DD, today to +60 days; the words 'heute' and 'morgen' are accepted.
- uhrzeit: HH:MM.
- personen: 1..20.
- A call already running: 'Es läuft schon ein Anruf.'
Then:
- POST {VAPI_BASIS}/call with Authorization: Bearer.
- 201 → store the call; anzeige.melden('anruf', {phase: 'waehlt', ...}) and anzeige.zeigen('anruf', {}, 600).
- Start a daemon thread on _verfolgen(kennung, control_url).
- Return {'ok': True, 'kennung', 'text': 'Ich rufe jetzt bei <restaurant> an. Das Gespräch siehst du auf der Zentrale. Ich sage Bescheid, sobald es vorbei ist.'}
- HTTP 401: 'Vapi lehnt den Schlüssel ab.'
- HTTP 400: 'Vapi lehnt den Anruf ab: <message[:200]>'

_verfolgen(kennung, control_url)
- Every 1.5 s: GET {VAPI_BASIS}/call/{kennung}.
- On an error, back off ×2 up to 10 s.
- Map status to phase. beginn = startedAt.
- Transcript lines: artifact.messages with role 'bot' → 'jarvis', 'user' → 'gegenueber'. Skip 'system' and tool lines. t = secondsFromStart; endgueltig = True.
- On every change: anzeige.melden('anruf', …) with mitschrift_live False.
- After 'ended': keep polling until artifact.structuredOutputs contains name 'reservierung' (fallback: analysis.structuredData), for at most 60 s.
- If there is still no result but a transcript exists: agent.json_anfrage('Lies dieses Telefonat und gib nur JSON nach diesem Schema zurück: …' + transcript).
- Hard stop at maxDuration + 180 s: phase 'fehler', grund_ende 'Ich habe den Anruf nicht mehr verfolgen können.'
- Finally:
  - Store ergebnis, mitschrift, kosten, status.
  - melden with phase 'beendet' and dauer_s 120.
  - Call ausgabe(text):
    - Reserved: 'Der Anruf bei Lotus ist vorbei: reserviert für Donnerstag, 9. Oktober, 19:30 Uhr, 2 Personen auf den Namen X. Soll ich das in den Kalender eintragen?'
    - Otherwise: '… Nicht reserviert. Gegenvorschlag: 20:30 Uhr. Soll ich zusagen lassen?' or just grund_ende.
  - Also call agent.meldung_einbringen(text, 'telefonassistent') if it exists (P4 contract).

status(kennung='')
- The last call from the DB, plus live state if it is running.

beenden()
- POST control_url {'type': 'end-call'}.
- control_url must start with 'https://' and its host must end in 'vapi.ai', else 'Diese Steuer-Adresse traue ich nicht.'
- No call running: 'Es läuft gerade kein Anruf.'

Retell (TELEFONAGENT_ANBIETER='retell')
- POST https://api.retellai.com/v2/create-phone-call {'from_number': RETELL_NUMMER, 'to_number', 'override_agent_id': RETELL_AGENT_ID, 'retell_llm_dynamic_variables': {'auftrag', 'erster_satz', 'datum', 'uhrzeit', 'personen', 'name'}}
- Poll GET https://api.retellai.com/v2/get-call/{id} until call_status == 'ongoing'.
- Then WebSocketLeser('wss://api.retellai.com/v2/monitor-call/' + id, {'Authorization': 'Bearer ' + key}) in the thread:
  - transcript_snapshot replaces all lines;
  - transcript_updated replaces the line with the same id, else appends: pure function retell_zeilen_anwenden(zeilen, nachricht);
  - call_ended ends it.
- mitschrift_live = True.
- Result from the final get-call: call_analysis.custom_analysis_data, else the json_anfrage fallback.
- The Retell agent is created once in the Retell dashboard (German, begin message {{erster_satz}}, prompt {{auftrag}}). This is documented in the .env.beispiel comment.

D. tools.py

__init__
- After self.welt: self.lokale = Lokale(self.welt)
- After self.anzeige exists: self.telefonagent = Telefonagent(self.memory, anzeige=self.anzeige)

agent_setzen
- self.telefonagent.agent = agent

Catalog section '# -- Telefonassistent --'

lokale_suchen
- Description: 'Sucht Restaurants und Lokale in der Nähe (OpenStreetMap) nach Küche, mit Entfernung, Telefon und Öffnungszeiten. Legt keine Interessenten an.'
- Schema: {'ort': text, 'kueche': {'type': 'string', 'enum': sorted(KUECHEN)}, 'radius_m': ganz}
- Sets: FREMDE_INHALTE.

restaurant_anrufen
- Description: 'Lässt einen KI-Telefonassistenten ein Restaurant anrufen und einen Tisch reservieren. Er sagt im ersten Satz, dass er eine KI ist, nennt nur Name, Personen, Zeit und Rückrufnummer, zahlt nichts und legt nach höchstens vier Minuten auf. Braucht eine Freigabe. Danach erst den Termin vorschlagen, nie ungefragt eintragen.'
- Schema: {'restaurant': text, 'nummer': text, 'datum': text, 'uhrzeit': text, 'personen': ganz, 'name': text, 'spielraum_minuten': ganz, 'hinweise': text, 'begruendung': text}
- Required: ['restaurant', 'nummer', 'datum', 'uhrzeit', 'personen', 'begruendung'].
- Sets: FREIGABE_PFLICHTIG and NETZ_SENDEND.

anruf_status
- Description: 'Stand und Ergebnis des letzten Telefonassistenten-Anrufs, mit Mitschrift.'
- Schema: {}
- Sets: FREMDE_INHALTE.

anruf_beenden
- Description: 'Beendet den laufenden Anruf des Telefonassistenten sofort.'
- Schema: {}
- In no set. Stopping is safe.

Other tools.py edits
- The anrufen description gets the sentence: 'Für ein echtes Gespräch, etwa eine Reservierung, nimm restaurant_anrufen.'
- zustand() gets 'telefonassistent': self.telefonagent.zustand().

E. FREIGABE_ANGABEN entry, added to P4's freigabe.py
- was: 'Anruf bei {restaurant} ({nummer}): Tisch für {personen} Personen am {datum} um {uhrzeit} Uhr auf den Namen {name}, Spielraum ±{spielraum_minuten} Minuten'
- wie: 'Ein KI-Telefonassistent (Vapi, Stimme {stimme}) ruft an, sagt im ersten Satz, dass er eine KI ist und in deinem Auftrag anruft, nennt nur Name, Personen, Zeit und deine Rückrufnummer, nimmt nichts auf und legt spätestens nach {max} Minuten auf. Kosten etwa 0,30 bis 0,60 Euro. Er bezahlt nichts und gibt keine Kartendaten.'
- {stimme} and {max} are filled from config by the P4 formatter, through a 'konfig' extras dict in the entry.

F. Other shared edits

telefon.py
- Telefon.zustand keeps gespraech_moeglich False; the test at :870 stays unchanged.
- hinweis becomes: 'Ansagen und SMS gehen. Ein echtes Gespräch führt der Telefonassistent (VAPI_SCHLUESSEL).'

run.py
- webbetrieb, after autopilot.ausgabe: agent.tools.telefonagent.ausgabe = web.melden
- dauerbetrieb, after the zeitplan is created: agent.tools.telefonagent.ausgabe = ansager.sagen if dienst else stimme.sprich

config.py
- VAPI_SCHLUESSEL = _text('VAPI_SCHLUESSEL')
- VAPI_BASIS = _text('VAPI_BASIS', 'https://api.vapi.ai') (EU organisation: https://api.eu.vapi.ai)
- VAPI_TELEFON_ID = _text('VAPI_TELEFON_ID')
- VAPI_MODELL = _text('VAPI_MODELL', 'claude-haiku-4-5-20251001')
- VAPI_STIMME = _text('VAPI_STIMME', 'de-DE-ConradNeural')
- TELEFONAGENT_ANBIETER = _text('TELEFONAGENT_ANBIETER', 'vapi')
- TELEFONAGENT_MAX_MINUTEN = _ganzzahl('TELEFONAGENT_MAX_MINUTEN', 4)
- TELEFONAGENT_RUECKRUF = _text('TELEFONAGENT_RUECKRUF')
- RETELL_SCHLUESSEL, RETELL_AGENT_ID, RETELL_NUMMER: _text
- konfig_uebersicht gets 'Telefonassistent': bool(VAPI_SCHLUESSEL or RETELL_SCHLUESSEL)

setup_wizard.ZUGAENGE
- Append ('telefonassistent', 'Vapi (Telefonassistent)', 'VAPI_SCHLUESSEL', 'https://dashboard.vapi.ai/')

build_single.py
- 'modules/netzsocket' and 'modules/telefonagent' directly after 'modules/telefon'.
- 'modules/lokale' directly after 'modules/world'.

## Tests
New function pruefung_telefonagent(agent).

Overpass query and parsing
1. lokale_abfrage(48.2, 16.37, KUECHEN['asiatisch']) contains 'cuisine', 'around:2500,48.2', 'out center tags'.
2. lokale_lesen on fake Overpass JSON with:
   - a node;
   - a way carrying 'center';
   - phone '+43 1 2345678;+43 1 999';
   - a contact:phone fallback;
   - an entry without a name.
   Expected: sorted by distance; the first phone becomes '+4312345678'; the nameless entry is dropped.

Lokale.suchen with a fake welt (ort_finden returns coordinates) and a fake holen
3. ok, at most 10 results.
4. The leads count is the same before and after.
5. nur_mit_telefon drops entries without a phone.

vapi_koerper
6. None of these keys anywhere: endCallFunctionEnabled, silenceTimeoutSeconds, analysisPlan.
7. artifactPlan.recordingEnabled is False.
8. firstMessage contains 'künstliche Intelligenz'.
9. maxDurationSeconds == 240.
10. model.tools == [{'type': 'endCall'}].
11. transcriber.language == 'de'.
12. customer.number starts with '+'.
13. With telefon_id set: phoneNumberId is present and phoneNumber is absent.

reservieren validation
14. No key → ok False, with 'VAPI_SCHLUESSEL'.
15. Key but no transport → 'VAPI_TELEFON_ID'.
16. Date in the past → ok False.
17. personen 0 → ok False.

Full flow
Setup:
- fake holen, fake uhr, schlaf as a no-op, fake anzeige, ausgabe collector;
- _verfolgen is called synchronously.
Scripted responses:
- POST /call returns {'id': 'c1', 'status': 'queued', 'monitor': {'controlUrl': 'https://phone.vapi.ai/c1/control'}}.
- GETs return in turn: ringing; in-progress; ended with 4 messages but no structuredOutputs; ended with structuredOutputs {'u1': {'name': 'reservierung', 'result': {'reserviert': True, 'datum': '2026-10-09', 'uhrzeit': '19:30', 'personen': 2}}}.
18. The anzeige phases are ['waehlt', 'klingelt', 'verbunden', 'beendet'].
19. The last payload has ergebnis.reserviert True, 4 mitschrift lines with wer in {jarvis, gegenueber}, and mitschrift_live False.
20. ausgabe was called exactly once, with a text containing 'Kalender'.
21. The telefonagent_anrufe row has status 'beendet'.

Other endings and errors
22. endedReason 'voicemail' → the text contains 'Anrufbeantworter' and ergebnis is None.
23. Three HTTP 500 GETs → schlaf was called with increasing values; the flow then recovers.
24. A clock past max + 180 → phase 'fehler'.

beenden
25. Posts {'type': 'end-call'} to the control URL.
26. A control URL on another host → refused.

Approval sets
27. restaurant_anrufen is in FREIGABE_PFLICHTIG and in NETZ_SENDEND.
28. lauf_beginnen(hintergrund=True), then tools.run('restaurant_anrufen', {...}) → refused with 'Hintergrund', and the fake kanal was never asked.
29. lokale_suchen and anruf_status are in FREMDE_INHALTE.

WebSocketLeser
Use socket.socketpair through the verbinden injection. A server thread checks Sec-WebSocket-Key and answers 101 with the correct Accept, then sends:
- a ping;
- a text message split into 2 fragments;
- a 200-byte message (126 length form);
- a close frame.
30. The generator yields 2 messages.
31. The server received a masked pong.
32. Close ends the generator.
33. A wrong Accept → WebSocketFehler.

Retell
34. retell_zeilen_anwenden: an update with the same id replaces the line, a new id appends.

State flags
35. agent.tools.telefon.zustand()['gespraech_moeglich'] is False: the existing check stays.
36. telefonagent.zustand()['gespraech_moeglich'] == bool(config.VAPI_SCHLUESSEL).
