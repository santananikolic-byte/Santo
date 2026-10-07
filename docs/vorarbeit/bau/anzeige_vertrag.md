ANZEIGE-VERTRAG v1. Owner: P1, module src/modules/anzeige.py. Every other package only writes through it.

1. The object
- Werkzeuge.__init__ creates exactly one store, directly after self.memory: self.anzeige = Anzeige().
- Writers get it by injection: a constructor argument anzeige=None, or the attribute stimme.anzeige.
- Every writer wraps every call in try/except Exception and passes, so the display can never break a tool. If anzeige is None, the writer skips silently.

2. Python API (thread-safe, built on threading.Condition)
- KANAELE = ('buehne','stimme','anruf','sicht','untertitel','hochfahren')
- MODI = ('uebersicht','globus','folge','maerkte','kennzahlen','anruf','sicht','untertitel','hochfahren','recherche','inhalte')
- MAX_NUTZLAST = 65536 bytes of JSON.

Anzeige(uhr=None)
- .start: epoch of this process. It changes on restart, and clients then reset all their versions to -1.

melden(kanal: str, daten: dict, dauer_s: float = 0.0) -> int
- Returns the new channel version.
- Returns -1 if the channel is unknown, daten is not a dict, daten is not JSON-serialisable, or it is larger than MAX_NUTZLAST. It then prints '[anzeige] ...'.
- Stores a deep copy, with seit = now and bis = now + dauer_s (0 = no expiry).
- Calls notify_all.

zeigen(modus: str, daten: dict = None, dauer_s: float = None, quelle: str = '') -> dict
- Equivalent to melden('buehne', dict(daten, modus=modus, quelle=quelle), dauer_s or config.ANZEIGE_DAUER).
- Also remembers the payload as letzte(modus).
- Returns {'ok':True,'modus':m,'version':v}.
- Errors:
  - unknown modus: {'ok':False,'fehler':'Diese Ansicht gibt es nicht: X. Möglich sind: ...'}
  - too large: {'ok':False,'fehler':'Die Anzeige-Daten sind zu groß.'}

letzte(modus) -> dict | None

stand(kanal) -> {'version':int,'daten':dict,'seit':float,'bis':float}
- Discreet-filtered (section 5).

warten(nach: dict, timeout: float) -> {kanal: stand}
- Returns as soon as any requested channel's version != nach[kanal]. Using != (not >) also catches a restarted server.
- Returns {} after the timeout.

kurz() -> {'modus': str, 'versionen': {kanal:int}, 'bis': float, 'start': float}
- modus is the current buehne modus, or 'uebersicht' once bis has passed.

anzeige_nach_lesen('buehne:7,anruf:2') -> {'buehne':7,'anruf':2}
- Unknown channels are dropped; numbers that do not parse become -1.

Versions start at 0 per channel and only grow.

3. HTTP routes (P1 implements them in webapp.py)

GET /api/status
- Existing fields plus 'anzeige': Anzeige.kurz().

GET /api/anzeige?nach=buehne:7,stimme:31,anruf:2&warten=20
- Response: {'ok':true,'jetzt':<server epoch float>,'start':<epoch>,'kanaele':{'<kanal>':{'version','daten','seit','bis'}}}
- Only channels that changed are included; {} on timeout.
- warten is clamped to 0..25 s.
- The path is in ANZEIGE_PFADE (GET, read-only).
- Each page holds at most ONE such long-poll, covering every channel it needs.
- Clock offset for the client: offset_ms = jetzt*1000 - Date.now().

POST /api/anzeige/satz {'text': '...'}
- Web mode only, origin-checked, text cut to 400 characters.
- Calls melden('stimme', {'art':'satz','text':t,'start_ms':time.time()*1000,'quelle':'browser'}).
- Response: {'ok':true}.

GET /api/weltkarte
- Response: {'ok':true,'breite':1440,'hoehe':720,'rle':'...'}
- Header Cache-Control: max-age=86400. Path is in ANZEIGE_PFADE.

4. Channel payloads (the 'daten' object)

4a. buehne
Always has 'modus' (one of MODI). Optional on every modus: 'titel' (up to 80 characters), 'stand' (source and time line, up to 160), 'quelle' (writer id).

uebersicht: {}
- Today's three-column Zentrale.

globus:
- 'fokus': {'lat','lon','zoom' (1..6),'name'}
- 'marker': up to 12 of {'lat','lon','titel' (≤60),'art' ('nachricht'|'ort'|'zuhause'|'kunde'|'lokal'),'text' (≤200),'quelle','zeit' (ISO)}
- 'boegen': up to 6 of {'von':[lat,lon],'nach':[lat,lon]}
- 'liste': up to 8 of {'titel','quelle','zeit'}

folge:
- 'schritte': 2 to 8 of {'stichwort': str, 'ansicht': <any buehne payload with its own modus, never 'folge'>}
- 'max_s_je_schritt': 10..60, default 30
- The page shows step 1 at once. It moves to the next step when a stimme event (art 'pegel' or 'satz') arrives whose text contains that step's stichwort. Matching ignores case and folds umlauts (ä→ae, ö→oe, ü→ue, ß→ss). It also moves on after max_s_je_schritt.
- After the last step the page holds that view until bis.

maerkte:
- 'kurse': up to 12 of {'schluessel','symbol','name','wert':float,'einheit':str,'aenderung_prozent':float|null,'verlauf':[float, up to 60],'zeit':ISO}
- 'zeitraum': 'heute' | 'monat'
- 'fehlend': [name]

kennzahlen:
- 'kacheln': up to 8 of {'name','wert':float,'einheit':'€'|'%'|'','ziel':float|null,'text':str,'farbe':'gut'|'schlecht'|'neutral'}
- Without 'kacheln' the page builds the tiles from its own /api/zentrale data and skips nulls.

anruf, sicht, untertitel, hochfahren: {}
- The content comes from the channel of the same name.

recherche:
- 'absaetze': up to 6 strings of ≤400
- 'quellen': up to 5 of {'titel','url'}
- 'liste': up to 10 of {'titel','text'}

inhalte:
- 'eintraege': up to 20 of {'datum' (YYYY-MM-DD),'plattform','titel','status'}

4b. stimme (dauer_s 0)
One of three shapes:
- {'art':'pegel','start_ms':epoch ms,'rahmen_ms':20,'pegel':[int 0..255, up to 9000],'text':str,'quelle':'elevenlabs'|'fish'|'say'}
- {'art':'satz','text','start_ms','quelle':'browser'}
- {'art':'aus'}
The client reads the current level at index floor((Date.now()+offset-start_ms)/rahmen_ms). This channel is never discreet-filtered, because its text is never rendered.

4c. anruf
Fields:
- 'kennung', 'anbieter' ('vapi'|'retell'), 'ziel', 'nummer'
- 'phase': 'vorbereitet'|'waehlt'|'klingelt'|'verbunden'|'beendet'|'fehler'
- 'beginn' (epoch|null), 'ende' (epoch|null)
- 'mitschrift': up to 60 of {'wer':'jarvis'|'gegenueber','text','t' (seconds from start),'endgueltig':bool}, newest last
- 'mitschrift_live': bool. When false, the HUD labels the transcript 'Mitschrift nach Gesprächsende'.
- 'ergebnis': {'reserviert':bool,'datum','uhrzeit','personen','name_der_reservierung','gegenvorschlag','hinweise'} | null
- 'grund_ende': str
- 'kosten_usd': float | null
Written on every change. dauer_s is 0 while the call is active and 120 after 'beendet' or 'fehler'.

4d. sicht
- 'handruhe': {'mm','rauschen_mm','rhythmus_hz' (or null),'fps','vergleich','tag'} | null
- 'erholung': {'wert','band' ('gruen'|'gelb'|'rot'),'quelle','tag'} | null
- 'zusammenhang': {'text','n','tabelle':[{'stufe','tage','termine','gespraeche','abschlussquote' (or null)}]} | null
- 'hinweis': 'Selbstbeobachtung, kein Medizinprodukt.'

4e. untertitel
{'von','nach','original','uebersetzung','sprecher':'ich'|'gast','zeit'}

4f. hochfahren
{'schritte':[up to 16 of {'name','ok':true|false|null,'text'}],'begruessung':str,'fertig':bool}

5. Discreet mode (config.ANZEIGE_DISKRET, applied in stand())
- anruf: nummer → '', ziel → 'Anruf', every mitschrift text → ''.
- untertitel: original and uebersetzung → ''.
- inhalte: every eintraege titel → 'Beitrag'.
- kennzahlen, globus and recherche stay unchanged (numbers only, or public sources).

6. Who writes what
P1
- anzeige_zeigen → any modus.
- kennzahlen → zeigen('kennzahlen', {'kacheln': kennzahlen_kacheln(tools)}).
- The main page writes stimme/satz through POST /api/anzeige/satz.

P2
- weltlage and nachrichten_suchen → globus.
- lagebild → folge (dauer 600).
- maerkte and aktienkurs → maerkte.
- webseite_lesen → recherche.

P3
- lokale_suchen → recherche.
- restaurant_anrufen → zeigen('anruf') plus the anruf channel on every phase change.

P5
- erholung_lesen, leistung_zusammenhang and every stored Handruhe measurement → sicht channel plus zeigen('sicht').

P6
- Stimme → stimme (pegel or aus).
- POST /api/uebersetzen → untertitel plus zeigen('untertitel', dauer 300).

P7
- Boot → hochfahren channel plus zeigen('hochfahren', dauer 60).
- inhalte_planen → inhalte.

7. Readers
/zentrale
- All six channels in one long-poll.
- Keeps the /api/zentrale poll (every 15 s) and the /api/status chip poll (every 2 s).

/gehirn
- Long-polls only stimme, and only when it is not embedded or has received no postMessage level for 5 s.

Main page /
- Long-polls anruf for the compact call overlay.
- Gets hochfahren through POST /api/hochfahren (P7).

/sehen
- Reads GET /api/sicht/stand and /api/sicht/verlauf (P5) and GET /api/freigaben.

8. Browser-internal messages (no server involved)
Parent page → /gehirn iframe via postMessage, origin checked:
- {'zustand': 'bereit'|'hoert'|'denkt'|'spricht'}
- {'pegel': 0..1}: real, from an AnalyserNode.
- {'sprechen': 'start'|'wort'|'ende'}: speechSynthesis events. The orb labels this 'Pegel nachempfunden'.

9. Related contracts
Approvals (P4)
- GET /api/freigaben → offen[] of {'id','aktion','was','warum','wie','details','gestellt','rest','geste_erlaubt'}
- POST /api/freigabe {'id','ja':bool,'kanal':'klick'|'sprache'|'geste'} → {'ok':bool,'text'}

Vision (P5)
- GET /sicht/dateien/<name>, where name is one of: vision_bundle.mjs, vision_wasm_internal.js, vision_wasm_internal.wasm, vision_wasm_nosimd_internal.js, vision_wasm_nosimd_internal.wasm, gesture_recognizer.task.
- GET /api/sicht/stand → {'ok','an','dateien_da','geste','handlaenge_mm','erholung'|null,'handruhe_letzte'|null,'hinweis'}
- GET /api/sicht/verlauf?tage=14 → {'ok','messungen':[...]}
- POST /api/sicht/messung, payload:
  - 'art': 'ruhe'|'halten'
  - 'mm': 0..20
  - 'rauschen_mm': number or null
  - 'rhythmus_hz': 3..14 or null
  - 'spitze_verhaeltnis': number or null
  - 'fps': 10..120
  - 'dauer_s': 4..30
  - 'bilder': int
  - 'handlaenge_mm': 60..130
  - Response: {'ok','text','vergleich'}

Voice (P6)
- POST /api/sprache {'text','sprache'} → audio/mpeg on success, or 503 {'fehler'}.
- /api/zustand gains 'stimme_im_browser' and 'stimme_anbieter'.
- POST /api/uebersetzen.

Boot (P7)
- POST /api/hochfahren → {'ok','neu','schritte','begruessung','sprechstuecke'}.