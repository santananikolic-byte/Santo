# JARVIS-Server (Phase 2)

Der lokale Server ist der Kern des neuen JARVIS. In Phase 2 kann er:

- laufen und anzeigen, dass er läuft (Statusseite und `/status`),
- Anfragen annehmen, prüfen und protokollieren (`/api/anfrage`),
- alles Wichtige als strukturierte Logs festhalten.

**Er beantwortet noch keine Anfragen.** Das kommt in Phase 3, wenn Claude Code
angebunden ist. Jede Antwort des Servers sagt das auch so.

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
| `./jarvis.sh oeffnen` | Statusseite im Browser öffnen |

Oder per Doppelklick im Finder: **Jarvis-starten.command** und
**Jarvis-stoppen.command**.

Statusseite: <http://127.0.0.1:8770>

Läuft er schon, startet `start` keinen zweiten. Ist der Port belegt, meldet
`start` das sofort, statt zu hängen.

## Anfrage senden (zum Ausprobieren)

```
curl -s -X POST http://127.0.0.1:8770/api/anfrage \
     -H 'Content-Type: application/json' \
     -d '{"text": "Prüfe die Muster GmbH"}'
```

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
`anfrage_angenommen`, `zugriff_abgelehnt`, `start_fehlgeschlagen`.

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
- **Ohne Internet** läuft der Server weiter. Antworten (ab Phase 3) brauchen
  aber Internet, weil Claude Code online denkt.

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

20 Tests: Konfiguration, Logs, alle Endpunkte, fehlerhafte Eingaben, fremder
Host, fremde Webseite, doppelter Start, belegter Port, fremdes Programm auf dem
Port, veraltete PID-Datei sowie Start und Stopp über `jarvis.sh` als echter
Hintergrundprozess.
