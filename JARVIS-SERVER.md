# JARVIS-Server (Phase 3)

Der lokale Server ist der Kern des neuen JARVIS. Stand Phase 3 kann er:

- laufen und anzeigen, dass er läuft (Statusseite und `/status`),
- **Fragen beantworten – über Claude Code mit deinem Claude-Abo**,
- Gespräche fortsetzen, auch nach einem Neustart,
- dein Wissen aus `CLAUDE.md` und `BRAIN.md` mitgeben,
- alles Wichtige als strukturierte Logs festhalten.

**Er hat noch keine Werkzeuge:** Er sucht nicht im Internet, liest keine
Dateien, führt nichts aus und sendet nichts. Er sagt das auch ehrlich, wenn
eine Aufgabe das bräuchte. Werkzeuge kommen mit der Berechtigungsschicht.

Er braucht nur Python 3.9 oder neuer (auf dem Mac schon vorhanden), keine
Zusatzpakete, keinen API-Schlüssel und keinen bezahlten Dienst.

## Starten und Beenden

Im Ordner `~/Santo`:

| Befehl | Was passiert |
|---|---|
| `./jarvis.sh start` | startet im Hintergrund und zeigt die Adresse |
| `./jarvis.sh stopp` | beendet ihn |
| `./jarvis.sh status` | läuft er? seit wann? wie viele Anfragen? |
| `./jarvis.sh logs 50` | die letzten 50 Log-Einträge |
| `./jarvis.sh oeffnen` | Statusseite mit Eingabefeld im Browser öffnen |
| `./jarvis.sh frage "Was steht an?"` | eine Frage im Terminal stellen |
| `./jarvis.sh provider` | ist Claude Code bereit? (verbraucht kein Kontingent) |

Oder per Doppelklick im Finder: **Jarvis-starten.command** und
**Jarvis-stoppen.command**.

Statusseite: <http://127.0.0.1:8770>

Läuft er schon, startet `start` keinen zweiten. Ist der Port belegt, meldet
`start` das sofort, statt zu hängen.

## Fragen stellen

Am einfachsten auf der Statusseite (<http://127.0.0.1:8770>): Text eingeben,
**Senden** (oder Strg+Enter). Das Gespräch läuft weiter, bis du auf
**Neues Gespräch** klickst. Oder im Terminal:

```
./jarvis.sh frage "Wie gewinnen wir mehr Daueraufträge in Leverkusen?"
```

Für Programme (`curl` & Co.):

```
curl -s -X POST http://127.0.0.1:8770/api/anfrage \
     -H 'Content-Type: application/json' \
     -d '{"text": "Hallo", "gespraech": "<Kennung aus der letzten Antwort, optional>"}'
```

Antwort: `{"ok": true, "antwort": "…", "gespraech": "…", "provider": "claude_code", "dauer_ms": …}`.
Bei Fehlern: `{"ok": false, "art": "…", "fehler": "…"}` mit HTTP 503 (nicht
installiert, nicht angemeldet, falsche Anmeldeart), 429 (Limit erreicht oder
beschäftigt), 504 (zu langsam) oder 502 (sonstiger Fehler von Claude Code).

JARVIS bearbeitet **immer nur eine Anfrage gleichzeitig**. Das schont dein
Kontingent und den Mac. Eine zweite wartet bis zu 2 Minuten.

## Anbieter: was geht, was nicht

Geprüft auf deinem iMac am 31.10.2026 (Phase 1) und im Code abgesichert:

| Anbieter | Stand | Was er kann | Grenzen |
|---|---|---|---|
| **Claude Code** | ✅ installiert (2.1.316), angemeldet mit Claude-Abo (Pro) | Fragen beantworten, Gespräche fortsetzen | Zählt zu deinem Abo-Limit. Ist es erreicht, meldet JARVIS, ab wann es weitergeht. Jede Anfrage braucht ein paar Sekunden Startzeit. In Phase 3 ohne Werkzeuge. |
| Codex | ❌ nicht installiert | – | braucht Node.js und ein ChatGPT-Konto; Installation nur nach deiner Freigabe |
| Gemini CLI | ❌ nicht installiert | – | braucht Node.js und ein Google-Konto; Installation nur nach deiner Freigabe |

So stellt JARVIS sicher, dass **nichts extra kostet**:

- Claude Code wird nur genutzt, wenn die Anmeldeart `claude.ai` ist, also das
  Abo. Ist es über einen API-Schlüssel angemeldet, verweigert JARVIS die
  Nutzung, und Claude wird gar nicht erst gefragt.
- Umgebungsvariablen, die Claude Code auf eine bezahlte Abrechnung umlenken
  würden (`ANTHROPIC_API_KEY`, `ANTHROPIC_AUTH_TOKEN`,
  `CLAUDE_CODE_USE_BEDROCK`, `CLAUDE_CODE_USE_VERTEX`,
  `CLAUDE_CODE_USE_FOUNDRY`), werden für jeden Aufruf entfernt.
- Es gibt keinen Ersatzweg über eine API. Ist Claude Code nicht bereit, sagt
  JARVIS das, statt still woanders hinzugehen.

Claude Code läuft im eigenen Datenordner `~/.jarvis` mit `--tools ""`, also
ohne Zugriff auf Dateien oder Befehle. Dein Wissen bekommt es über den
Systemprompt: die JARVIS-Regeln plus `CLAUDE.md` und `BRAIN.md` aus dem
Projektordner. **Änderst du diese Dateien, starte den Server neu**
(`./jarvis.sh stopp` und `./jarvis.sh start`).
## Konfiguration

Beim ersten Start entsteht `~/.jarvis/config.json`:

```json
{
  "host": "127.0.0.1",
  "port": 8770,
  "logstufe": "INFO",
  "log_max_bytes": 1000000,
  "log_dateien": 5
}
```

Umgebungsvariablen gehen vor: `JARVIS_PORT`, `JARVIS_LOGSTUFE`, `JARVIS_DATEN`
(anderer Datenordner). Der Port ist 8770, weil der alte Jarvis 8765 nutzt.

## Logs

`~/.jarvis/logs/jarvis.jsonl` – eine JSON-Zeile pro Ereignis, zum Beispiel:

```json
{"zeit": "2026-10-31T16:02:11+01:00", "stufe": "INFO", "ereignis": "anfrage_angenommen", "id": "3f2a…", "laenge": 21, "anfang": "Prüfe die Muster GmbH"}
```

Ab 1 MB wird die Datei rotiert, die letzten 5 bleiben erhalten. Fehler beim
Start stehen zusätzlich in `~/.jarvis/logs/konsole.log`.

Ereignisse: `server_gestartet`, `server_gestoppt`, `stopp_signal`,
`provider_geprueft`, `anfrage_angenommen`, `anfrage_beantwortet`,
`anfrage_fehlgeschlagen`, `zugriff_abgelehnt`, `start_fehlgeschlagen`,
`interner_fehler`.

Von jeder Frage stehen die ersten 200 Zeichen im Log, von Antworten nur die
Länge. Gesprächszuordnungen liegen in `~/.jarvis/gespraeche.json`.

## Sicherheit

- Der Server hört **nur auf 127.0.0.1**, also nur auf diesem Mac. Eine andere
  Adresse in der Konfiguration wird abgelehnt.
- Der Host-Kopf jeder Anfrage muss auf diesen Mac zeigen. Das schützt vor
  DNS-Rebinding, einem Trick, mit dem fremde Webseiten lokale Server ansprechen.
- Anfragen, die eine fremde Webseite aus dem Browser schickt, werden abgelehnt.
- Höchstens 64 KB pro Anfrage, höchstens 10 000 Zeichen Text.
- Andere Programme und Benutzer **auf demselben Mac** können den Server
  erreichen und die Logs lesen (`/api/logs` zeigt den Anfang jeder Anfrage).
  Auf einem iMac mit einem Benutzer ist das in Ordnung. Ein Zugangsschlüssel
  für lokale Programme kommt, sobald JARVIS Aktionen ausführen kann (Phase 5).

## Was du wissen musst

- **Erreichbar nur, solange der Mac läuft.** Ruhezustand, Ausschalten oder
  Abmelden beenden den Server bzw. lassen ihn nicht antworten.
- **Kein automatischer Neustart.** Ein Autostart (über einen macOS-LaunchAgent)
  kommt erst, wenn JARVIS Aufgaben nach einem Neustart sicher wiederaufnehmen
  kann (Phase 5). Sonst startet er womöglich halbe Aufgaben neu.
- **Ohne Internet** läuft der Server weiter, kann aber nicht antworten, weil
  Claude Code online denkt.

## Fernzugriff später (noch nicht eingebaut)

Vom Handy aus geht es nur, wenn man den Server bewusst erreichbar macht. Die
sicheren Wege, jeweils nur nach deiner Freigabe:

| Weg | Kosten | Risiko |
|---|---|---|
| **Tailscale** (privates Netz zwischen deinen Geräten) | für private Nutzung kostenlos | gering: nur deine angemeldeten Geräte; braucht ein zusätzliches Programm und ein Konto |
| **SSH-Tunnel** | kostenlos | gering, aber umständlich am Handy |
| Port im Router öffnen | kostenlos | **hoch**: der Server stünde im ganzen Internet. Nicht empfohlen. |

In jedem Fall käme vorher ein Zugangsschlüssel dazu.

## Umzug in die Cloud (nur zur Einordnung)

Damit JARVIS auch bei ausgeschaltetem Mac läuft, bräuchte er einen Rechner,
der immer an ist:

- **Bezahlter Server (VPS):** monatliche Kosten. Außerdem müsste Claude Code
  dort angemeldet werden, deine Daten lägen auf fremder Hardware, und der
  Server wäre aus dem Internet erreichbar. Das erfordert deutlich mehr
  Absicherung.
- **Ein eigener Rechner, der immer läuft** (zum Beispiel ein alter Mac oder ein
  Mini-PC): keine laufenden Gebühren außer Strom.

Nichts davon ist vorgesehen, solange du es nicht ausdrücklich willst.

## Tests

```
python3 -m unittest tests.test_kern -v
```

25 Tests: Konfiguration, Logs, alle Endpunkte, fehlerhafte Eingaben, fremder
Host, fremde Webseite, doppelter Start, belegter Port, fremdes Programm auf dem
Port, veraltete PID-Datei, Start und Stopp über `jarvis.sh` als echter
Hintergrundprozess – und Claude Code (simuliert, damit kein Kontingent
verbraucht wird): Antwort, Gespräch fortsetzen, keine Weitergabe von
API-Schlüsseln, keine Werkzeuge, nicht installiert, nicht angemeldet,
API-Schlüssel-Anmeldung abgelehnt, Limit, kaputte Ausgabe, Zeitüberschreitung.
