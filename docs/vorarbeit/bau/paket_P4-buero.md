# P4-buero Büro: Freigaben mit Was/Warum/Wie und serverseitigen Gestenregeln, proaktive Vorschläge mit Kontext, Kalender korrekt (Zeitzonen, Serien, Löschen/Verschieben mit Papierkorb, freie Zeiten), Mail-Antwort im Faden und Entwürfe

Anwendungsfaelle: ['5', '6', '13 (Vorschlagsmechanik)', "Video 2 (Termine streichen, 'Ja' mit Kontext)", 'Freigabepflicht aller Pakete']
Neue Dateien: ['src/modules/freigabe.py', 'src/modules/vorschlaege.py']
Geaenderte Dateien: ['src/modules/calendar_mod.py (owner)', 'src/modules/mail.py (owner)', 'src/modules/dienst.py (freigabe_ansage)', 'src/modules/telegram_mod.py (approval message text)', "src/modules/tools.py (_freigabe, 'begruendung' on 11 tools, 8 new tools, sets, termine_lesen ids)", 'src/modules/webapp.py (WebFreigabe, /api/freigabe kanal, melden → meldung_einbringen)', 'src/agent.py (meldung_einbringen, system prompt line)', 'src/run.py (Dienst output wrappers)', 'src/modules/team.py (terminplaner, postmeister)', 'src/config.py', 'config/.env.beispiel', 'build_single.py', 'tests/abnahme.py (pruefung_buero + main)']
Abhaengig von: []

## Spezifikation
Owner of freigabe.py, vorschlaege.py, calendar_mod.py and mail.py, and of the approval channel texts.

A. freigabe.py

FREIGABE_ANGABEN: dict tool → {'was': template, 'wie': template, 'konfig': {placeholder: config name}}
Entries for the 11 existing approval tools:
- mail_senden
  - was: 'eine Mail an {an} schicken, Betreff „{betreff}“. Sie beginnt mit: {text:120}'
  - wie: 'per SMTP vom eingerichteten Postfach; der ganze Text steht in den Details'
- termin_anlegen
  - was: 'den Termin „{titel}“ am {beginn} ({dauer_minuten} Minuten) eintragen{ort: in }'
  - wie: 'im Kalender {kalender} über CalDAV'
- nachricht_senden
  - was: 'per {kanal} an {an} schreiben: {text:120}'
- anrufen
  - was: '{nummer} anrufen und ansagen: {ansage:120}'
  - wie: 'Twilio-Anruf, die Ansage wird zweimal vorgelesen'
- sms_senden
  - was: '{nummer} eine SMS schicken: {text:120}'
- skript_ausfuehren: special; keeps the legacy text
- bildschirm_bedienen
  - was: 'den Bildschirm bedienen: {ziel:160}'
  - wie: 'Schritt für Schritt über Screenshots, jeder Schritt einzeln bestätigt'
- browser_auftrag
  - was: 'im Browser: {ziel:160}'
  - wie: 'klickt nur Beschriftungen, meldet sich nirgends an, kauft nichts'
- browser_oeffnen
  - was: 'die Adresse {adresse} öffnen'
  - wie: 'die Adresse selbst geht dabei ins Netz'
- autopilot_schalten
  - was: 'den Autopiloten {an:ein/aus}schalten'
- datei_schreiben
  - was: 'die Datei {pfad} {ueberschreiben:ersetzen/neu anlegen}'
New tools from P3, P4 and P7 get their entries here too.

freigabe_beschreiben(name, argumente) -> dict
- Shape: {'was', 'warum', 'wie', 'argumente': <the dict from Werkzeuge.freigabe_details>}
- Formatting: missing fields become '?', each value is cut to the given or default 120 characters, and ':a/b' picks a word for bool fields.
- warum = argumente['begruendung'], or '(ohne Begründung – Jarvis hat keinen Grund genannt)'.
- Unknown tools, including MCP tools: was = the readable name plus the shortened arguments; wie = 'über das angeschlossene Werkzeug {name}'.

GESTE_GESPERRT = {'skript_ausfuehren', 'bildschirm_bedienen', 'browser_auftrag', 'browser_schritt', 'datei_schreiben', 'ordnen_ausfuehren', 'ordnen_rueckgaengig', 'autopilot_schalten'}

B. tools.py

_freigabe
- skript_ausfuehren is unchanged: werkstatt.freigabetext, plain text.
- Every other tool: details = json.dumps(freigabe_beschreiben(name, argumente), ensure_ascii=False, default=str).

begruendung on existing tools
- Add 'begruendung': {'type': 'string', 'description': 'Warum das nötig ist, in einem Satz – steht in der Freigabefrage.'} to the input_schema of all 11 existing FREIGABE_PFLICHTIG tools, and add it to 'required'.
- Dispatch ignores the field.

termine_lesen output
- Now includes 'id'.

New catalog section '# -- Kalender und Post --'

termine_absagen
- Description: 'Sagt Termine ab (löscht sie im Kalender). Nur Termine, die du gerade mit termine_lesen gesehen hast, über ihre id. Die Freigabe nennt jeden Termin einzeln. Serientermine bleiben unangetastet; gelöschte kommen in den Papierkorb.'
- Schema: {'ids': {'type': 'array', 'items': {'type': 'string'}, 'maxItems': 10}, 'begruendung': text}; required both.
- Approval.

termin_verschieben
- Description: 'Verschiebt einen eben gelesenen Termin auf einen neuen Beginn (gleiche Dauer, wenn nicht anders angegeben). Braucht eine Freigabe.'
- Schema: {'id': text, 'neuer_beginn': text, 'dauer_minuten': ganz, 'begruendung': text}; required id, neuer_beginn, begruendung.
- Approval.

termin_wiederherstellen
- Description: 'Legt einen abgesagten Termin aus dem Papierkorb wieder an. Braucht eine Freigabe.'
- Schema: {'papierkorb_id': ganz, 'begruendung': text}
- Approval.

freie_zeiten
- Description: 'Freie Zeitfenster an einem Tag zwischen von und bis, mindestens so lang wie angegeben.'
- Schema: {'tag': text ('YYYY-MM-DD', 'heute', 'morgen'), 'von': text (default '08:00'), 'bis': text (default '18:00'), 'mindestens_minuten': ganz (default 60)}
- In no set.

mail_antworten
- Description: 'Antwortet auf eine gelesene Mail im selben Faden (Betreff Re:, In-Reply-To). Braucht eine Freigabe.'
- Schema: {'kennung': text (the Message-ID from mails_lesen or mails_suchen), 'text': text, 'begruendung': text}; required all.
- Approval.

mail_entwurf
- Description: 'Legt eine Mail als Entwurf im Postfach ab (Ordner Entwürfe). Verschickt wird nichts.'
- Schema: {'an', 'betreff', 'text', 'antwort_auf' (Message-ID, optional)}
- Sets: NETZ_SENDEND.

vorschlaege_offen
- Description: 'Was Jarvis von sich aus vorgeschlagen hat und noch offen ist.'
- Schema: {}

vorschlag_beantworten
- Description: 'Hält fest, ob ein Vorschlag angenommen oder abgelehnt wurde. Führt selbst nichts aus.'
- Schema: {'id': ganz, 'angenommen': wahr}

Set changes
- FREIGABE_PFLICHTIG += {'termine_absagen', 'termin_verschieben', 'termin_wiederherstellen', 'mail_antworten'}
- NETZ_SENDEND += {'mail_entwurf'}

__init__ and agent_setzen
- self.vorschlaege = Vorschlaege(self.memory)
- agent_setzen: self.vorschlaege.agent = agent

C. dienst.freigabe_ansage
- If details parses as JSON with a 'was' key, return 'Ich soll %s. Grund: %s. %s' % (was, warum, first sentence of wie).
- Otherwise, the existing legacy branches are unchanged.
- Required: the existing check that 'Komme um neun' appears in the SMS announcement stays true, because was contains the text.

Telegram (telegram_mod.py)
- Approval message: 'FREIGABE: <aktion>\nWas: …\nWarum: …\nWie: …\nDetails: <json>'
- The terminal prompt uses the same format.

D. webapp.py, class WebFreigabe(timeout=None, uhr=None)

anfordern
- Parses JSON details into was, warum and wie. Non-JSON details: was = the readable aktion, details = the text.

offene()
- Adds 'was', 'warum', 'wie', and 'geste_erlaubt' = (config.GESTEN_FREIGABE and aktion not in GESTE_GESPERRT and exactly one open).
- 'details' becomes the readable argumente JSON.

beantworten(kennung, ja, kanal='klick') -> bool
- self.letzter_grund holds the reason.
- For kanal 'geste', ALL of these must hold:
  - GESTEN_FREIGABE is on;
  - exactly one approval is open;
  - aktion is not in GESTE_GESPERRT;
  - now − gestellt_epoch ≥ 2.0 s (store an epoch next to the display timestamp);
  - otherwise False, with letzter_grund e.g. 'Die Geste zählt hier nicht: mehrere Fragen offen.'
- Gesture yes and no are logged via memory: aktion_protokollieren('freigabe', {'aktion': …, 'kanal': 'geste'}, 'per Geste ' + ('ja' if ja else 'nein'), 'ok'). WebFreigabe gets the memory as an optional constructor argument; JarvisWeb passes agent.memory.

POST /api/freigabe
- kanal = str(daten.get('kanal') or 'klick'), must be in {'klick', 'sprache', 'geste'}.
- Response: {'ok': erledigt, 'text': ('Freigabe erteilt.' if ja else 'Abgelehnt.') if erledigt else (self.freigabe.letzter_grund or 'Diese Frage ist nicht mehr offen.')}

JarvisWeb.melden
- After the DB write: try self.agent.meldung_einbringen(text, 'meldung') except Exception: pass.

E. agent.py

meldung_einbringen(self, text, quelle='zeitplan')
- Strip text; if empty, return.
- Under self._denk_sperre:
  - If the last assistant text in verlauf equals text, return.
  - Append {'role': 'user', 'content': '<hinweis quelle="%s">Das Folgende hat Jarvis gerade von sich aus gesagt. Es ist keine Frage von %s.</hinweis>' % (quelle, config.NUTZER_NAME)}.
  - Append {'role': 'assistant', 'content': [{'type': 'text', 'text': text[:4000]}]}.
  - Call self._verlauf_kuerzen().

SYSTEMPROMPT
- Add the line: '- Bei allem, was eine Freigabe braucht, schreibst du in begruendung in einem Satz, warum. Die Freigabe zeigt Was, Warum und Wie.'
- Add the line: '- Steht vor deiner letzten Antwort ein Hinweis, dass du etwas von dir aus gesagt hast, und er antwortet mit ja, dann meint er diesen Vorschlag. Die nötigen Werkzeuge fragen trotzdem einzeln nach Freigabe.'

F. vorschlaege.py

SCHEMA_VORSCHLAEGE
- vorschlaege(id INTEGER PRIMARY KEY AUTOINCREMENT, schluessel TEXT UNIQUE, quelle TEXT, text TEXT, aktion TEXT DEFAULT '', argumente TEXT DEFAULT '{}', status TEXT DEFAULT 'offen', angelegt TEXT, beantwortet TEXT DEFAULT '')

class Vorschlaege(memory, agent=None, ausgabe=None)

einbringen(schluessel, text, quelle, aktion='', argumente=None) -> {'ok', 'id', 'doppelt'}
- If config.VORSCHLAEGE_AN is false: {'ok': False, 'aus': True}.
- If the key already exists: doppelt True, nothing said.
- Otherwise: store the row, then agent.meldung_einbringen(text, quelle).
- Then ausgabe(text) if ausgabe is set. If no ausgabe is set, the caller returns the text, e.g. as a scheduler job.

offene(tage=3)
beantworten(id, angenommen)

G. calendar_mod.py

ics_zeit_lesen(wert, tzid=None, nur_datum=False) -> naive local datetime
- Local zone = config.CALDAV_ZEITZONE (ZoneInfo), else the system local zone.
- A trailing 'Z' is UTC, converted to local.
- TZID uses ZoneInfo(tzid), with a mapping for common Windows names:
  - 'W. Europe Standard Time' → Europe/Berlin
  - 'Central Europe Standard Time' → Europe/Budapest
  - 'Romance Standard Time' → Europe/Paris
  - 'GMT Standard Time' → Europe/London
  - An unknown TZID is treated as local time.
- VALUE=DATE → midnight, and the event is marked ganztaegig.

ics_termine_lesen
- Reads the parameters of DTSTART/DTEND, plus RRULE, EXDATE, RECURRENCE-ID and STATUS.
- STATUS:CANCELLED events are skipped.

REPORT
- The query uses <C:calendar-data><C:expand start=… end=…/></C:calendar-data>.
- If an event still carries an RRULE, local expansion runs: regel_ausdehnen(beginn, rrule, exdates, von, bis) handles FREQ DAILY / WEEKLY with BYDAY / MONTHLY with BYMONTHDAY / YEARLY, plus INTERVAL, COUNT and UNTIL.
- Unsupported parts (BYSETPOS, BYWEEKNO and the like) give the first occurrence only, plus a hinweis.

Multistatus parsing
- xml.etree over {DAV:}response: href, getetag, calendar-data.
- Each event keeps href, etag, uid, serie (RRULE or RECURRENCE-ID present) and ganztaegig.
- Short id = sha1(href + beginn)[:8]. The id → event map is kept for 30 minutes.

CALDAV_KALENDER
- If it starts with http, it is the collection URL.
- Otherwise: CALDAV_URL.rstrip('/') + '/' + quote(name) + '/'.
- Used for reading and writing.

termin_anlegen
- Writes DTSTART/DTEND in UTC with 'Z'.

termine_absagen(ids, begruendung)
- Unknown or expired id: 'Ich muss die Termine erst lesen – frag mich nach den Terminen, dann sage ich dir, welche ich absagen würde.'
- A series event: 'Das ist ein Serientermin. Einzelne Termine einer Serie sage ich nicht ab – das machst du bitte im Kalender.'
- Before deleting: GET the href and store the ICS in the table kalender_papierkorb(id, href, ics, titel, beginn, geloescht_am).
- DELETE with If-Match: etag.
- 412: 'Der Termin wurde inzwischen geändert – ich lösche ihn nicht. Lies die Termine neu.'
- Returns the done and refused lists.

termin_verschieben(id, neuer_beginn, dauer_minuten=None)
- Series events are refused as above.
- GET the ICS, replace DTSTART and DTEND (in UTC), PUT with If-Match.

termin_wiederherstellen(papierkorb_id)
- PUT the stored ICS to its href, with If-None-Match: *.

freie_zeiten(tag, von, bis, mindestens)
- Merges overlapping events and returns the gaps.

H. mail.py

- ungelesene and suchen items gain 'kennung' (Message-ID) and 'uid'.
- antwort_bauen(kopf: dict, text) -> email.message.EmailMessage:
  - Subject 'Re: ' + original, without doubling 'Re:';
  - In-Reply-To = Message-ID;
  - References = the old References + Message-ID;
  - quotes the first 20 lines with '> '.
- antworten(kennung, text):
  - IMAP SEARCH HEADER Message-ID, then fetch the headers;
  - send via SMTP.
- entwurf_ablegen(an, betreff, text, antwort_auf=''):
  - Find the Drafts folder via the \Drafts flag in LIST, falling back to 'Drafts', 'Entwürfe', '[Gmail]/Entwürfe'.
  - IMAP APPEND with the \Draft flag.
  - No IMAP: 'Für Entwürfe im Postfach fehlt der IMAP-Zugang.'

I. Other shared edits

run.py dauerbetrieb, when dienst
- The zeitplan ausgabe and the autopilot ausgabe become lambdas that first call agent.meldung_einbringen(t, 'zeitplan' or 'autopilot') and then ansager.sagen / ansager.leise.

team.py
- terminplaner werkzeuge += ['freie_zeiten', 'termine_absagen', 'termin_verschieben']
- postmeister werkzeuge += ['mail_antworten', 'mail_entwurf']
- Background filtering in team.py removes the approval and network tools automatically.

config.py
- CALDAV_ZEITZONE = _text('CALDAV_ZEITZONE', 'Europe/Vienna')
- GESTEN_FREIGABE = _wahrheit('GESTEN_FREIGABE', False)
- VORSCHLAEGE_AN = _wahrheit('VORSCHLAEGE_AN', True)

build_single.py
- 'modules/freigabe' directly after 'modules/sprechtext' (before dienst and tools).
- 'modules/vorschlaege' directly after 'modules/routines'.

## Tests
New function pruefung_buero(agent). Run it together with the whole existing abnahme: the approval checks at :1744-1761, :2049-2068 and :2629-2670 must stay green.

freigabe_beschreiben
1. freigabe_beschreiben('mail_senden', {'an': 'a@b.at', 'betreff': 'Angebot', 'text': 'Hallo', 'begruendung': 'Nachfassen'}) → was contains 'a@b.at', warum == 'Nachfassen', wie is not empty.
2. Without begruendung → warum contains 'ohne Begründung'.
3. 'mcp__x__y' → a generic was.

Catalog
4. Every own tool in FREIGABE_PFLICHTIG has 'begruendung' in input_schema.required and an entry in FREIGABE_ANGABEN, except skript_ausfuehren, which is special-cased.

freigabe_ansage
5. On new-style JSON for sms_senden → contains 'Grund:' and 'Komme um neun'.
6. The legacy strings still work: the existing checks.

WebFreigabe with an injected clock
7. anfordern runs in a thread; offene() has was, warum, wie and geste_erlaubt.
8. GESTEN_FREIGABE False → beantworten(id, True, 'geste') is False.
9. Flag True, approval 1 s old → False; at 2.1 s → True, and the thread gets erlaubt True.
10. Two open approvals → False, with letzter_grund containing 'mehrere'.
11. aktion skript_ausfuehren → geste_erlaubt False and beantworten False.
12. kanal 'klick' always works.
13. A gesture approval writes an aktionen row.
14. HTTP on the nur_anzeige server: POST /api/freigabe → 404.

meldung_einbringen
15. agent.meldung_einbringen('Soll ich morgen zwei Termine streichen?') adds 2 messages; the same text again adds 0.
16. A following real user turn 'ja' → gehirn_waehlen('ja', gemini_da=True, vorher=agent._claude_zuvor()) is 'claude'. Simulate this by appending the user turn first, as _denken does.

Calendar
17. ics_zeit_lesen('20261009T173000Z') with CALDAV_ZEITZONE Europe/Vienna → 19:30.
18. TZID America/New_York 09:00 → 15:00.
19. VALUE=DATE → ganztaegig.
20. Multistatus parsing on fake XML keeps href and etag.
21. The REPORT body contains '<C:expand'.
22. Local RRULE FREQ=WEEKLY;BYDAY=MO,WE over 14 days → 4 occurrences; EXDATE removes one.
23. STATUS:CANCELLED is skipped.
24. termin_anlegen PUTs an ICS whose DTSTART ends in 'Z' and is correctly converted (19:30 local → 17:30Z).

Deleting and moving, with a fake _anfrage
25. termine_absagen sends DELETE with If-Match equal to the etag.
26. 412 → the refusal text.
27. A series event → the series refusal.
28. An unknown id → 'erst lesen'.
29. A papierkorb row is stored.
30. termin_wiederherstellen PUTs the stored ICS with If-None-Match.
31. termin_verschieben PUTs a changed DTSTART and keeps the duration.

freie_zeiten
32. Events 09:00-10:00 and 11:00-12:30, window 08-18, minimum 60 → [08:00-09:00, 10:00-11:00, 12:30-18:00].

Vorschlaege
33. einbringen twice with the same key → the second is doppelt; agent.verlauf grew by 2 only once; the ausgabe fake was called once.
34. VORSCHLAEGE_AN False → nothing stored.

Mail
35. antwort_bauen sets In-Reply-To, References and 'Re: Angebot', and on 'Re: Angebot' does not double the prefix.
36. entwurf_ablegen without IMAP → the German error.

Approval sets
37. termine_absagen, termin_verschieben, termin_wiederherstellen and mail_antworten are FREIGABE_PFLICHTIG.
38. mail_entwurf is in NETZ_SENDEND.
39. In the background, termine_absagen is refused without asking.
