# P7-start-steuerung Start, Steuerung, Dateien & Inhalte: Hardware-Bericht und Begrüßung beim Hochfahren, Kurzbefehle/Fensterlayouts/Lautstärke, datei_oeffnen repariert, Ordnen mit Plan, Freigabe und Rückgängig, Inhalte-Pipeline mit Redaktionsplan

Anwendungsfaelle: ['1', '2', '3', '7']
Neue Dateien: ['src/modules/hardware.py', 'src/modules/steuerung.py', 'src/modules/inhalte.py']
Geaenderte Dateien: ['src/modules/mac.py (owner: oeffnen, ordnen)', 'src/modules/tools.py (12 tools, systeminfo wlan, PARAMETER_AKTIONEN, sets, __init__)', 'src/modules/freigabe.py (P4-owned registry: 2 entries, delivered as text)', 'src/modules/webapp.py (POST /api/hochfahren)', 'src/agent.py (begruessung)', "src/run.py (daemon greeting, CLI 'hardware')", 'src/modules/team.py (marketing role)', 'src/config.py', 'config/.env.beispiel', 'build_single.py', 'tests/abnahme.py (pruefung_start_steuerung + main)']
Abhaengig von: ['P1-buehne']

## Spezifikation
Owner of hardware.py, steuerung.py, inhalte.py and mac.py.

A. hardware.py

hardware_bericht(ausfuehren=None, zeitlimit=2.0, stimme=None, tools=None) -> dict
- ausfuehren(befehl: list, timeout) -> (rc, stdout). Default: subprocess with shell=False.
- Each probe runs in its own thread, joined with zeitlimit. A probe that times out or raises becomes {'status': 'fehlt', 'text': 'nicht messbar (Zeitüberschreitung)'}.
- Off macOS, every Mac probe reports 'Nur auf dem Mac messbar'.
- Return shape: {'zeit', 'werte': [{'name', 'wert', 'einheit', 'status': 'ok'|'warnung'|'fehlt', 'text'}], 'kurz': one sentence listing only what stands out, e.g. 'Speicher 18 % frei, Wärme erhöht, sonst alles in Ordnung.'}

Probes
- Last: os.getloadavg()[0]/os.cpu_count(). Below 0.7 normal; below 1.5 'hoch' (warnung); otherwise 'sehr hoch'.
- Rechner: sysctl -n hw.model, sysctl -n machdep.cpu.brand_string, platform.mac_ver()[0].
- Arbeitsspeicher: sysctl -n hw.memsize. vm_stat: page size from the regex 'page size of (\d+) bytes'; used = (active + wired + 'occupied by compressor') × page size.
- Speicherdruck: memory_pressure, last line regex 'free percentage: (\d+)%'. Below 20 % → warnung.
- Festplatte: shutil.disk_usage(home). Below 10 % free → warnung.
- Internet: socket.create_connection(('api.anthropic.com', 443), 3), timed in ms. Failure → 'kein Internet', status fehlt.
- WLAN: wlan_bericht().
- Wärme: notifyutil -g com.apple.system.thermalpressurelevel → 0 normal, 1 'erhöht', 2 'stark' (warnung), 3 or 4 'kritisch' (warnung). Temperature in degrees: 'ohne Administratorrechte nicht messbar' (status fehlt, said honestly).
- Laufzeit: sysctl -n kern.boottime, regex 'sec = (\d+)'.
- Batterie: pmset -g batt. Without 'InternalBattery' → no tile, just 'Netzbetrieb'.
- Geräte: system_profiler SPCameraDataType SPAudioDataType SPDisplaysDataType -json, cached per process. Counts cameras, microphones and displays.
- Services: stimme.zustand() (macos_say, elevenlabs, fish, mikrofon), tools.kalender.verfuegbar(), tools.mail.lesen_moeglich(), tools.telegram.verfuegbar(), and the Claude and Gemini keys.

wlan_bericht(ausfuehren=None) -> dict
- networksetup -listallhardwareports: the device of the block whose 'Hardware Port: Wi-Fi'.
- system_profiler SPAirPortDataType, cached 10 min: the network name under 'Current Network Information:'.
- Fallbacks: 'verbunden (Name nicht lesbar)', or 'kein WLAN-Gerät'.
- NEVER uses networksetup -getairportnetwork, which is wrong on macOS 15+.

B. Boot sequence

agent.begruessung(bericht: dict) -> str
- bausteine = self._bausteine_sammeln(morgens=True).
- Without a key: 'Hallo. Ich bin da. ' + bericht['kurz'] + '\n' + bausteine.
- With a key: self.denken('Begrüße %s beim Hochfahren in drei bis fünf gesprochenen Sätzen: ein Satz zum Rechner (nur Auffälliges), dann der Tag – Termine, Post, Wetter, Offenes. Erfinde nichts; was nicht abrufbar war, sag kurz.\n\nRechner: %s\n\nDaten:\n%s' % (...), protokollieren=False, anzeigen=False).

hardware.hochfahren(agent, stimme=None) -> dict
- Flag file config.LOG_VERZEICHNIS / 'hochgefahren.txt' holds today's date.
- neu = (flag != today). If neu, write the flag.
- bericht = hardware_bericht(...).
- schritte = up to 16 of {name, ok: True if ok / False if warnung / None if fehlt, text}.
- begruessung:
  - neu and BEGRUESSUNG_AN → agent.begruessung(bericht);
  - not neu → 'Ich bin wieder da.' plus the warnings only.
- anzeige: melden('hochfahren', {'schritte', 'begruessung', 'fertig': True}) and zeigen('hochfahren', {}, 60).
- Returns {'ok', 'neu', 'schritte', 'begruessung', 'sprechstuecke': sprechstuecke(begruessung)}.

Daemon (run.py dauerbetrieb)
- Replace stimme.sprich('Ich bin da. Sag Hey Jarvis…') with: r = hochfahren(agent, stimme); stimme.sprich(r['begruessung'] + ' Sag Hey Jarvis, wenn du etwas brauchst.')

Web (webapp.py)
- POST /api/hochfahren → hochfahren(self.agent). Not in ANZEIGE_PFADE.

CLI
- 'python3 jarvis.py hardware' prints the bericht.

C. steuerung.py

kurzbefehle_liste(ordner=None, ausfuehren=None)
- ['shortcuts', 'list', '-f', ordner or config.KURZBEFEHL_ORDNER].
- Returns {'ok', 'namen', 'text'}.
- No 'shortcuts' command: 'Kurzbefehle gibt es erst ab macOS 12 – hier fehlt das Programm shortcuts.'
- Empty: "Im Ordner '%s' der Kurzbefehle-App liegt noch nichts. Leg dort Kurzbefehle wie 'Licht Büro an' an – nur solche, die nichts nach außen schicken."

kurzbefehl_ausfuehren(name, eingabe='', ...)
- The name must be in the live list of the folder, else "Den Kurzbefehl '%s' gibt es im Ordner Jarvis nicht. Vorhanden: …"
- eingabe goes through parameter_pruefen when given.
- subprocess.run(['shortcuts', 'run', name], input=eingabe, text=True, timeout=60, shell=False).
- rc != 0: 'Der Kurzbefehl ist fehlgeschlagen: …'
- Never uses -i/-o files.

bildschirme(ausfuehren=None)
- osascript -l JavaScript -e 'ObjC.import("AppKit"); JSON.stringify(ObjC.deepUnwrap($.NSScreen.screens).map ... )'. The builder writes the exact JXA and tests it on the Mac; the test covers only the parser and the y-conversion.
- Produces [{x, y, w, h}] with y converted to a top-left origin: top = hauptHoehe − (y + h).

LAYOUTS
- zentrale: [{'seite': '/zentrale', 'bildschirm': config.ANZEIGE_BILDSCHIRM, 'rahmen': [0, 0, 1, 1]}]
- arbeiten: [{'seite': '/', 'bildschirm': 0, 'rahmen': [0.6, 0, 0.4, 1]}, {'seite': '/zentrale', 'bildschirm': config.ANZEIGE_BILDSCHIRM, 'rahmen': [0, 0, 1, 1]}]
- praesentation: [{'seite': '/zentrale', 'bildschirm': 0, 'rahmen': [0, 0, 1, 1]}]

fenster_anordnen(layout, ausfuehren=None)
- Jarvis pages: ['open', '-na', 'Google Chrome', '--args', '--user-data-dir=' + str(config.PROFIL_VERZEICHNIS / 'chrome-anzeige'), '--app=http://localhost:%d%s' % (WEB_PORT, seite), '--window-position=%d,%d' % (x, y), '--window-size=%d,%d' % (w, h)]
- Missing display index → bildschirm 0, plus a hint.
- Correction afterwards through System Events. Error -1719 → 'Für das Verschieben von Fenstern braucht Jarvis die Bedienungshilfen (Systemeinstellungen > Datenschutz & Sicherheit > Bedienungshilfen).' Error -1743 → the Automation-permission hint.
- No Chrome: 'Für Anzeige-Fenster brauche ich Google Chrome.'

lautstaerke_setzen(prozent)
- Must be an int 0..100, else 'Die Lautstärke geht von 0 bis 100.'
- ['osascript', '-e', 'set volume output volume %d' % p].

D. mac.py

Blocked extensions
- OEFFNEN_GESPERRT = {'.app', '.command', '.sh', '.tool', '.scpt', '.applescript', '.workflow', '.action', '.pkg', '.mpkg', '.dmg', '.terminal', '.py', '.rb', '.pl', '.jar', '.exe', '.bin', '.prefpane', '.kext', '.webloc', '.inetloc', '.fileloc'}

oeffnen(pfad)
- expanduser and realpath; must lie inside home.
- Directories ending in .app, and blocked extensions → 'Programme, Skripte und Installationspakete öffne ich nicht – nur Dokumente, Bilder und PDFs.'
- Missing file → 'Die Datei gibt es nicht.'
- ['open', pfad], no shell.

ordnen_planen(ordner, regel) -> {'ok', 'plan_id', 'zuege': [{'von', 'nach'}], 'text'}
- regel is one of:
  - 'nach_typ': subfolders PDF, Bilder, Tabellen, Texte, Archive, Sonstiges, from an extension map;
  - 'nach_monat': YYYY-MM from mtime;
  - 'nach_kunde': the first matching kontakte/leads firma name in the file name, otherwise left alone.
- The folder must be inside an allowed write root (SCHREIB_ORDNER + MAC_SCHREIBORDNER), using the existing schreiben_pruefen logic. Never inside SCHREIBEN_GESPERRT.
- Only top-level files; hidden files are skipped; at most 200 moves.
- An existing target is skipped and listed.
- Stored in the table ordnungsplaene(id, ordner, regel, zuege_json, angelegt, status).

ordnen_ausfuehren(plan_id)
- os.makedirs for the target folders, then os.rename for each move.
- Re-checks every source and target inside the root; skips if the target exists; never deletes and never overwrites.
- Undo log ordnungs_protokoll(plan_id, von, nach, zeit).

ordnen_rueckgaengig(plan_id)
- Moves back. Skips when the original name is taken again.

E. inhalte.py

SCHEMA_REDAKTION
- redaktionsplan(id INTEGER PRIMARY KEY AUTOINCREMENT, datum TEXT, plattform TEXT, titel TEXT, text TEXT, hashtags TEXT, projekt TEXT, status TEXT DEFAULT 'entwurf', angelegt TEXT)

PLATTFORMEN: key → name and limits
- instagram: Instagram, 2200 characters, 3-8 hashtags
- facebook: Facebook, 3000
- linkedin: LinkedIn, 3000
- tiktok: TikTok, 2200
- google: Google-Unternehmensprofil, 1500
- website: Webseite, 5000

INHALT_AUFTRAG
- German prompt for an outbound-facing content plan of a building-cleaning sole proprietor.
- Asks for ONLY this JSON: {'idee', 'kernbotschaft', 'beitraege': [{'plattform', 'titel', 'text', 'hashtags': []}], 'video': {'titel', 'laenge_s', 'szenen': [{'nr', 'bild', 'ton', 'dauer_s'}]}, 'skript', 'termine': [{'datum': 'YYYY-MM-DD', 'plattform'}]}
- Rules: no invented customer names, prices or certifications; Sie-Form or Du-Form as in JARVIS_STIL.

class Inhalte(memory, werkstatt, agent=None, anzeige=None)

planen(thema, plattformen, ab_datum='', wochen=1, ton='')
- Calls agent.json_anfrage.
- Validates: plattformen ⊆ PLATTFORMEN, text length per platform limit (cut, with a note), dates in the range.
- Writes werkstatt.projekt_datei_schreiben('inhalte-<slug>', file, content) for konzept.md, beitraege.md, video-skript.md and shotliste.md.
- Inserts redaktionsplan rows.
- zeigen('inhalte', {'titel': thema[:80], 'eintraege': [...]}).
- Invalid JSON: 'Der Entwurf kam nicht in der erwarteten Form zurück – bitte noch einmal.'

plan(tage=30)
status_setzen(id, status)
- status is one of entwurf, freigegeben, veroeffentlicht.
- Only marks the row: publishing is done by the user.

F. tools.py

Catalog section '# -- Start und Steuerung --'

hardware_pruefen
- Description: 'Prüft den Rechner: Last, Speicher, Festplatte, Netz, WLAN, Wärme, Kamera, Mikrofon, Dienste. Nur lesend.'
- Schema: {}

kurzbefehle
- Description: "Zeigt die Kurzbefehle im Ordner 'Jarvis' der Kurzbefehle-App (Licht, Szenen, Fokus)."
- Schema: {}

kurzbefehl_ausfuehren
- Description: "Führt einen Kurzbefehl aus dem Ordner 'Jarvis' aus – etwa Licht, Szene oder Fokus. Andere Kurzbefehle führe ich nicht aus."
- Schema: {'name': text, 'eingabe': text}; required name.

fenster_anordnen
- Description: 'Ordnet die Fenster nach einem festen Layout: zentrale (Zentrale auf dem zweiten Bildschirm), arbeiten, praesentation.'
- Schema: {'layout': {'type': 'string', 'enum': sorted(LAYOUTS)}}

lautstaerke_setzen
- Description: 'Stellt die Lautstärke des Macs (0 bis 100).'
- Schema: {'prozent': ganz}

datei_oeffnen
- Description: 'Öffnet eine Datei mit dem passenden Programm (Dokument, Bild, PDF). Programme, Skripte und Installationspakete öffne ich nicht.'
- Schema: {'pfad': text}
- Remove 'datei_oeffnen' from PARAMETER_AKTIONEN. The dispatch branch goes BEFORE the PARAMETER_AKTIONEN branch.

ordnen_planen
- Description: 'Plant, wie Dateien in einem Ordner sortiert würden (nach Typ, Monat oder Kunde), und zeigt jeden Zug. Verschiebt noch nichts.'
- Schema: {'ordner': text, 'regel': {'enum': ['nach_typ', 'nach_monat', 'nach_kunde']}}

ordnen_ausfuehren
- Description: 'Führt einen geplanten Sortiervorgang aus. Braucht eine Freigabe, die die Züge zeigt. Löscht nie etwas; rückgängig mit ordnen_rueckgaengig.'
- Schema: {'plan_id': ganz, 'begruendung': text}
- Approval.

ordnen_rueckgaengig
- Schema: {'plan_id': ganz, 'begruendung': text}
- Approval.

Catalog section '# -- Inhalte --'

inhalte_planen
- Description: 'Plant Inhalte von der Idee bis zum Redaktionsplan: Kernbotschaft, Beiträge je Plattform, Videokonzept mit Szenenliste, Sprechtext und Termine. Legt alles als Projekt in der Werkstatt ab. Veröffentlicht wird nichts.'
- Schema: {'thema': text, 'plattformen': {'type': 'array', 'items': {'type': 'string', 'enum': sorted(PLATTFORMEN)}}, 'ab_datum': text, 'wochen': ganz, 'ton': text}; required thema.

redaktionsplan
- Schema: {'tage': ganz}

inhalt_status
- Schema: {'id': ganz, 'status': {'enum': ['entwurf', 'freigegeben', 'veroeffentlicht']}}

Other tools.py edits
- systeminfo: if schluessel == 'wlan', return hardware.wlan_bericht() turned into a text dict. The SYSTEM_AKTIONEN key stays, so the enum is unchanged.
- __init__: self.inhalte = Inhalte(self.memory, self.werkstatt, anzeige=self.anzeige)
- agent_setzen: self.inhalte.agent = agent
- FREIGABE_PFLICHTIG += {'ordnen_ausfuehren', 'ordnen_rueckgaengig'}

FREIGABE_ANGABEN entries (added to P4's freigabe.py)
- ordnen_ausfuehren
  - was: '{anzahl} Dateien im Ordner {ordner} umsortieren: {zuege:30}'. The P4 formatter receives the plan through an 'erweitern' hook: tools passes argumente plus the plan data.
  - wie: 'nur verschieben, nie löschen oder überschreiben; rückgängig mit ordnen_rueckgaengig'
- ordnen_rueckgaengig
  - was: 'Sortiervorgang {plan_id} rückgängig machen'

G. Other shared edits

team.py
- ROLLEN['marketing']['werkzeuge'] += ['inhalte_planen', 'redaktionsplan']
- ROLLEN['programmierer']['werkzeuge'] += ['ordnen_planen']

config.py
- BEGRUESSUNG_AN = _wahrheit('BEGRUESSUNG_AN', True)
- KURZBEFEHL_ORDNER = _text('KURZBEFEHL_ORDNER', 'Jarvis')
- ANZEIGE_BILDSCHIRM = _ganzzahl('ANZEIGE_BILDSCHIRM', 1)
- INHALTE_PLATTFORMEN = _text('INHALTE_PLATTFORMEN', 'instagram,facebook,google')

build_single.py
- 'modules/hardware' and 'modules/steuerung' directly after 'modules/mac'.
- 'modules/inhalte' directly after 'modules/werkstatt'.

## Tests
New function pruefung_start_steuerung(agent). Uses a temporary HOME (monkeypatched os.environ['HOME']) and a temporary LOG_VERZEICHNIS.

hardware_bericht with a fake ausfuehren
1. vm_stat sample with 'page size of 16384 bytes' → used GB correct.
2. memory_pressure line 'System-wide memory free percentage: 61%' → 61.
3. kern.boottime '{ sec = 1791300000, usec = 0 }' → laufzeit computed.
4. thermal level '2' → status warnung with 'stark'.
5. pmset output without InternalBattery → no Batterie tile.
6. A probe that sleeps 5 s → status fehlt, and the whole report finishes in under 3 s.
7. With a fake platform that is not macOS → every Mac value is 'fehlt', with 'Nur auf dem Mac'.

wlan_bericht
8. On a -listallhardwareports sample → device en1. On a system_profiler sample → the network name.
9. tools.run('systeminfo', {'was': 'wlan'}) never calls '-getairportnetwork'. Check by monkeypatching subprocess.run.

Boot
10. POST /api/hochfahren over real HTTP: first call neu True with schritte; second call the same day neu False; the hochfahren channel version increases.
11. agent.begruessung without a key contains 'Ich bin da' and the bausteine.

Shortcuts
12. kurzbefehl_ausfuehren with the fake list ['Licht Büro an']:
   - name 'Alles löschen' → refused, with 'gibt es im Ordner Jarvis nicht';
   - eingabe 'a;b' → refused;
   - valid → captured args ['shortcuts', 'run', 'Licht Büro an'], with input passed through stdin.

Displays and layouts
13. The bildschirme parser plus y-conversion: main 2560×1440, second display at x 2560, y −200, height 1080 → top = 1440 − (−200 + 1080) = 560.
14. fenster_anordnen('zentrale') → open args contain '--app=http://localhost:8765/zentrale' and '--window-position=2560,560'.
15. Fake error -1719 → 'Bedienungshilfen'.

Volume
16. lautstaerke_setzen(150) → refused; 30 → osascript args.

datei_oeffnen
17. '~/Desktop/x.command' → refused.
18. '~/Documents/a.pdf' (file created) → args ['open', path].
19. '/etc/hosts' → refused.
20. datei_oeffnen is in namen().

Sorting files
21. In tmpHOME/Documents/Test with a.pdf, b.jpg, c.pdf and an existing PDF/c.pdf: ordnen_planen 'nach_typ' → 2 moves plus 1 skipped.
22. tools.run('ordnen_ausfuehren') with a fake approval channel that answers yes → files moved, protocol rows written, and the total file count is unchanged (nothing deleted).
23. ordnen_rueckgaengig restores the original paths.
24. Planning in '/etc' → refused.
25. ordnen_ausfuehren in the background → refused without asking.

Inhalte
26. planen with a fake agent.json_anfrage returning valid JSON with 3 termine → 3 redaktionsplan rows; 4 project files in the werkstatt; the fake anzeige got 'inhalte'.
27. Invalid JSON → 'nicht in der erwarteten Form'.
28. A text longer than the platform limit is cut, with a note.
29. inhalt_status 'veroeffentlicht' only marks the row.

Catalog
30. ordnen_ausfuehren and ordnen_rueckgaengig are FREIGABE_PFLICHTIG and have FREIGABE_ANGABEN entries.
