# P6-stimme-dolmetscher Stimme & Dolmetscher: Anbieterkette Fish/ElevenLabs/say, WAV-Pegel für den Orb, Servertimme im Browser, mehrsprachiges Sprechen, Dolmetscher-Seite mit Untertiteln

Anwendungsfaelle: ['8', 'Video 2 (Orb reagiert auf echte Sprachamplitude)', '1 (Stimme beim Hochfahren)', 'Fish Audio aus dem Nutzervorschlag']
Neue Dateien: ['src/modules/stimmanbieter.py', 'src/modules/dolmetscher.py']
Geaenderte Dateien: ['src/modules/voice.py (owner)', 'src/modules/sprechtext.py (owner: sprechstuecke_fremd)', 'src/modules/tools.py (stimme_setzen anzeige, tool dolmetscher_starten)', 'src/modules/webapp.py (POST /api/sprache, POST /api/uebersetzen, GET /dolmetscher, /api/zustand fields, rate limiter)', 'src/agent.py (text_anfrage effort parameter)', 'src/config.py (+ konfig_uebersicht)', 'src/modules/setup_wizard.py (ZUGAENGE tuple)', 'config/.env.beispiel', 'build_single.py', 'tests/abnahme.py (pruefung_stimme_dolmetscher + main)']
Abhaengig von: ['P1-buehne']

## Spezifikation
Owner of stimmanbieter.py, dolmetscher.py, voice.py and sprechtext.py.

A. stimmanbieter.py (stdlib: json, urllib, wave, array, io, math, sys)

URLs
- FISH_URL = 'https://api.fish.audio/v1/tts'
- ELEVENLABS_TTS = 'https://api.elevenlabs.io/v1/text-to-speech/%s'

anbieter_reihenfolge() -> list
- STIMME_ANBIETER 'auto' → [p for p in ('fish', 'elevenlabs') if that provider's key is set].
- 'fish' or 'elevenlabs' → [that one], if its key is set, else [].
- 'mac' → [].

fish_holen(text, format='mp3', rate=22050, holen=None) -> (bytes or None, fehler)
- Headers: Authorization: Bearer FISH_API_KEY; Content-Type: application/json; model: FISH_MODELL. The model goes in a HEADER.
- Body: {'text', 'reference_id': FISH_STIMME_ID, 'format', 'latency': FISH_LATENZ, 'normalize': False}, plus 'sample_rate': rate for wav and pcm.
- Errors:
  - 401: 'Fish Audio lehnt den Schlüssel ab.'
  - 402: 'Bei Fish Audio ist kein Guthaben mehr.'
  - 503: 'Fish Audio ist gerade überlastet.'

elevenlabs_holen(text, format='mp3', vorher='', nachher='', vorige=None, sprache='', holen=None) -> (bytes or None, request_id, fehler)
- format 'pcm' → '?output_format=pcm_22050' and NO 'Accept: audio/mpeg'.
- format 'mp3' → as today.
- sprache, only if the model id contains 'flash' or 'turbo' → 'language_code'.
- voice_settings as today.

sprachaudio(text, format='mp3', sprache='de') -> {'ok', 'daten', 'typ', 'anbieter', 'fehler'}
- Walks the provider chain.
- typ: audio/mpeg for mp3, audio/wav for wav.

pcm_als_wav(pcm, rate=22050) -> bytes
- wave module, 1 channel, 16 bit.

pegel_aus_wav(quelle, rahmen_ms=20) -> list of int 0..255
- Reads 16-bit PCM through array('h'); byteswap if sys.byteorder == 'big'.
- Per frame: RMS → dBFS → (dB + 50)/50·255, clamped.
- Python 3.9-safe. No audioop.

say_befehl(text, ziel_wav, stimme, rate) -> list
- ['say', '-r', rate, '-v', stimme, '-o', ziel_wav, '--data-format=LEI16@22050', text]
- The -v part is left out when there is no stimme.

B. voice.py

- Stimme gains the attribute anzeige = None.

sprich(text, sprache='de')
- stuecke = sprechstuecke(text) for German, otherwise sprechstuecke_fremd(text).
- For each provider in anbieter_reihenfolge(): _anbieter_sprechen(stuecke, anbieter, sprache).
  - This generalises today's _elevenlabs_sprechen: queue, prefetch, stop.
  - Fetch per chunk as WAV: ElevenLabs pcm → pcm_als_wav; Fish format 'wav'.
  - Write a temp .wav and compute pegel_aus_wav.
  - IMMEDIATELY before abspielen(pfad):
    self._anzeige_melden({'art': 'pegel', 'start_ms': time.time()*1000 + config.STIMME_VORLAUF_MS, 'rahmen_ms': 20, 'pegel': p, 'text': stueck, 'quelle': anbieter})
- Remaining chunks fall back to the system voice:
  1. subprocess.run(say_befehl(...)).
  2. If the WAV is missing or empty: say -o x.aiff, then afconvert -f WAVE -d LEI16@22050 x.aiff x.wav.
  3. If that fails too: the old plain 'say' call, and publish {'art': 'aus'} first so the orb animates from state.
  - Play the WAV through abspielen(): afplay, which makes 'say' interruptible.
- stoppen() publishes {'art': 'aus'}.
- _anzeige_melden wraps everything in try/except.

sprachdatei_erzeugen
- For Telegram: uses sprachaudio(text, 'mp3') first, then the existing say/ffmpeg path.

zustand()
- Adds 'fish': bool(config.FISH_API_KEY) and 'anbieter': anbieter_reihenfolge().

Mac voice for other languages
- stimme_fuer_sprache(code) parses 'say -v ?' lines ('Name  xx_YY  # …') and picks the first voice whose locale starts with the code. Cached.

C. sprechtext.py

def sprechstuecke_fremd(text, ziel=220) -> list
- Uses the existing schleifen_entfernen and abschnitte.
- No German number expansion.

D. dolmetscher.py (imports BASIS_STIL from modules.ansicht and gemini_fragen from modules.router)

SPRACHEN: code → (name, BCP-47)
- de: Deutsch, de-DE
- en: Englisch, en-GB
- tr: Türkisch, tr-TR
- hr: Kroatisch, hr-HR
- sr: Serbisch, sr-RS
- bs: Bosnisch, bs-BA
- sq: Albanisch, sq-AL
- pl: Polnisch, pl-PL
- ro: Rumänisch, ro-RO
- hu: Ungarisch, hu-HU
- sk: Slowakisch, sk-SK
- cs: Tschechisch, cs-CZ
- bg: Bulgarisch, bg-BG
- uk: Ukrainisch, uk-UA
- ru: Russisch, ru-RU
- ar: Arabisch, ar-SA
- fa: Persisch, fa-IR
- it: Italienisch, it-IT
- fr: Französisch, fr-FR
- es: Spanisch, es-ES

UEBERSETZER_SYSTEM
- 'Du bist Dolmetscher zwischen {von_name} und {nach_name}. Übersetze nur die letzte Äußerung. Gib ausschließlich die Übersetzung aus – ohne Anführungszeichen, ohne Erklärung. Fachbegriffe der Gebäudereinigung (Unterhaltsreinigung, Grundreinigung, Baureinigung, Bauendreinigung, Glasreinigung, Leistungsverzeichnis) korrekt übertragen. Namen, Zahlen, Uhrzeiten und Beträge unverändert.'

uebersetzen(text, von, nach, verlauf=None, agent=None) -> dict
Validation:
- von and nach must be in SPRACHEN and must differ.
- text: 1..1500 characters.
Engine:
- DOLMETSCHER_GEHIRN 'auto' → Gemini if a key exists, else Claude.
- Gemini: gemini_fragen(text, system, verlauf=[]).
- Claude: agent.text_anfrage(system + '\n\nLetzte Äußerungen:\n…\n\nZu übersetzen:\n' + text, effort='low', max_tokens=2000).
Result:
- {'ok', 'uebersetzung', 'von', 'nach', 'sprechstuecke', 'zeit'}.
- sprechstuecke = sprechstuecke(...) when nach == 'de', else sprechstuecke_fremd(...).
Errors:
- No key: 'Zum Übersetzen brauche ich Gemini oder Claude – es ist kein Schlüssel hinterlegt.'
- Unknown language: "Die Sprache '%s' kenne ich nicht. Möglich: …"

SEITE_DOLMETSCHER: inline only, with a {{SCHLUESSEL}} placeholder
- Two large buttons: 'Ich spreche Deutsch' and 'Gast spricht <Sprache ▾>'. The select takes its options from DOLMETSCHER_SPRACHEN, and ?nach= preselects one.
- Toggle 'abwechselnd', on by default.
- SpeechRecognition:
  - lang = SPRACHEN[x][1] for the active speaker;
  - a language change does stop() and then start() on the existing onend;
  - interim results are shown.
- A final result → POST /api/uebersetzen {text, von, nach, verlauf: the last 4} → show the original small and the translation large.
- Speaking:
  - If /api/zustand.stimme_im_browser: POST /api/sprache {text: chunk, sprache: nach} → <audio>.
  - Otherwise speechSynthesis with besteStimme(lang): the voice whose lang starts with the code, preferring premium, enhanced, natural or neural voices.
- Recognition pauses while speaking.
- A local list of the last 10 exchanges, never stored on the server, with a 'Verlauf leeren' button.
- Note on the page: 'Die Spracherkennung des Browsers schickt den Ton an den Hersteller des Browsers (Google bei Chrome, Apple bei Safari).'
- Contains prefers-reduced-motion and no http or https URLs.

E. webapp.py

Imports
- from modules.stimmanbieter import sprachaudio, anbieter_reihenfolge
- from modules.dolmetscher import SEITE_DOLMETSCHER, uebersetzen

JarvisWeb.__init__
- self._sprache_zeiten = []: a sliding window of 60 requests per 60 s.

POST /api/sprache
- text = str(daten.get('text') or '')[:600].strip(); sprache must be in SPRACHEN, default 'de'.
- Empty text → 400.
- Over the limit → 429 {'fehler': 'Zu viele Sprachanfragen in kurzer Zeit.'}
- r = sprachaudio(text, 'mp3', sprache).
- ok → 200 with the raw bytes and Content-Type r['typ'], via _kopf_setzen.
- Otherwise → 503 {'fehler': r['fehler'] or 'Keine Sprachausgabe eingerichtet.'}
- Not in ANZEIGE_PFADE.

POST /api/uebersetzen
- → uebersetzen(..., agent=self.agent).
- On ok: self.agent.tools.anzeige.melden('untertitel', {von, nach, original, uebersetzung, sprecher: daten.get('sprecher', 'gast'), zeit}) and zeigen('untertitel', {}, 300), inside try/except.

GET /dolmetscher
- The HTML page.

/api/zustand
- Adds 'stimme_im_browser': bool(config.STIMME_IM_BROWSER and anbieter_reihenfolge()).
- Adds 'stimme_anbieter': (anbieter_reihenfolge() or [''])[0].

F. tools.py

stimme_setzen
- After the existing lines: if stimme is not None: stimme.anzeige = self.anzeige

Catalog section '# -- Dolmetscher --'
- dolmetscher_starten
  - Description: 'Öffnet den Dolmetscher im Browser: du sprichst Deutsch, der Gast seine Sprache; Jarvis übersetzt hin und her und zeigt Untertitel auf der Zentrale.'
  - Schema: {'nach': {'type': 'string', 'enum': sorted(k for k in SPRACHEN if k != 'de')}}; required.
  - Dispatch: if shutil.which('open'), run subprocess ['open', 'http://localhost:%d/dolmetscher?nach=%s' % (WEB_PORT, nach)] with shell=False, where WEB_PORT is imported from modules.macapp. ok text 'Der Dolmetscher ist offen: Du sprichst Deutsch, der Gast <Sprache>.'
  - Otherwise ok with the address as text.
  - In no set.

G. agent.py
- text_anfrage(self, auftrag, bild_base64='', bild_typ='image/jpeg', max_tokens=8000, effort='medium')
- Passes effort on to _claude_runde. Existing callers are unchanged.

H. config.py
- STIMME_ANBIETER = _text('STIMME_ANBIETER', 'auto')
- FISH_API_KEY = _text('FISH_API_KEY')
- FISH_STIMME_ID = _text('FISH_STIMME_ID')
- FISH_MODELL = _text('FISH_MODELL', 's2.1-pro')
- FISH_LATENZ = _text('FISH_LATENZ', 'balanced')
- STIMME_IM_BROWSER = _wahrheit('STIMME_IM_BROWSER', True)
- STIMME_VORLAUF_MS = _ganzzahl('STIMME_VORLAUF_MS', 60)
- DOLMETSCHER_GEHIRN = _text('DOLMETSCHER_GEHIRN', 'auto')
- DOLMETSCHER_SPRACHEN = _text('DOLMETSCHER_SPRACHEN', 'tr,hr,sr,bs,sq,pl,ro,hu,en,uk,ru,ar')
- konfig_uebersicht gets 'Fish Audio': bool(FISH_API_KEY)

setup_wizard.ZUGAENGE
- Append ('fish', 'Fish Audio (Stimme)', 'FISH_API_KEY', 'https://fish.audio/app/api-keys/')

build_single.py
- 'modules/stimmanbieter' directly after 'modules/sprechtext' (before modules/voice).
- 'modules/dolmetscher' directly after 'modules/ansicht'.

## Tests
New function pruefung_stimme_dolmetscher(agent). The original config values are saved and restored.

Provider chain
1. anbieter_reihenfolge:
   - only ELEVENLABS key → ['elevenlabs'];
   - both keys with 'auto' → ['fish', 'elevenlabs'];
   - 'mac' → [];
   - 'fish' without a key → [].

fish_holen with a fake holen
2. Headers contain model == FISH_MODELL and 'Bearer'; body normalize False; format 'wav' sends sample_rate 22050.
3. 402 → 'kein Guthaben'.

elevenlabs_holen
4. format 'pcm' → the URL contains 'output_format=pcm_22050' and the request has no 'Accept: audio/mpeg' header.

Audio helpers
5. pcm_als_wav → wave.open reads 22050 Hz, 1 channel, sample width 2.
6. pegel_aus_wav on a WAV generated in the test (1 s silence, then 1 s of a 1 kHz sine at 0.5) → 100 values; the mean of the first 50 is < 30, of the last 50 > 180.

Stimme._anbieter_sprechen
The fetch is faked; abspielen is monkeypatched to record calls and return True; anzeige is a fake.
7. A 'pegel' message is recorded BEFORE each abspielen call.
8. start_ms is within now + STIMME_VORLAUF_MS ± 200.
9. stoppen() → 'aus'.

Other voice checks
10. say_befehl contains '--data-format=LEI16@22050' and '-o'.
11. sprechstuecke_fremd('Price is 12.50 EUR on 3/4') keeps '12.50' and '3/4'.

uebersetzen
12. With a monkeypatched gemini_fragen → ok, and the system text contains 'Gebäudereinigung'.
13. von == nach → ok False.
14. 'xx' → ok False, with 'kenne ich nicht'.
15. No keys → ok False, with 'kein Schlüssel'.
16. The Claude path calls text_anfrage with effort 'low': monkeypatch agent._claude_runde and capture effort.

HTTP
17. POST /api/sprache with no keys → 503 JSON 'fehler'.
18. The 61st request inside 60 s → 429.
19. POST /api/uebersetzen with uebersetzen monkeypatched → 200; the anzeige untertitel version increases.
20. GET /dolmetscher → no http(s) in the page (SVG namespace removed); contains 'lang' handling and the browser-vendor note.
21. /api/zustand has 'stimme_im_browser'.

Tool
22. dolmetscher_starten({'nach': 'tr'}) on Linux without 'open' → ok True, with 'localhost' in the text.
