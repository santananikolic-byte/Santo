# JARVIS-Server

Der lokale JARVIS läuft auf deinem Mac und denkt über **Claude Code mit deinem Claude-Abo**. Er braucht nur Python 3.8 oder neuer
(auf dem Mac schon da), keine Zusatzpakete, **keinen API-Schlüssel und keinen bezahlten Dienst**.

Was gebaut, getestet und noch nicht auf dem echten Mac geprüft ist, steht ehrlich in `docs/STATUS.md`. Die Selbstprüfung steht in
`docs/SELBSTPRUEFUNG.md`, der Aufbau in `docs/ARCHITEKTUR.md`.

## Einrichten und Starten

**Zum ersten Mal (auch auf einem frischen Mac):** diese eine Zeile ins Terminal einfügen und Enter drücken.

```
curl -fsSL https://raw.githubusercontent.com/santananikolic-byte/Santo/HEAD/jarvis-einrichten.sh | bash
```

Macht das Einfügen im Terminal Probleme (zum Beispiel stehen vor jedem Zeichen Backslashes `\`), tippe stattdessen diese drei kurzen Zeilen ab:

```
git clone https://github.com/santananikolic-byte/Santo
cd Santo
./jarvis-einrichten.sh
```

Das Einrichten holt JARVIS nach `~/Santo`, prüft Python, Git und Claude Code, bietet an, Fehlendes zu installieren (immer erst nach Rückfrage),
hilft bei der Anmeldung mit deinem Claude-Abo, zeigt eine Checkliste, startet JARVIS und öffnet ihn im Browser. Fehlen die
Apple-Entwicklerwerkzeuge, öffnet sich ein Installationsfenster von Apple; danach dieselbe Zeile nochmal einfügen.

**Danach:** Doppelklick auf **Jarvis-starten.command** im Ordner `Santo` (holt die neueste Fassung, startet, öffnet) und
**Jarvis-stoppen.command**. Oder im Terminal:

```
cd ~/Santo && git pull && ./jarvis.sh start && ./jarvis.sh oeffnen
```

Läuft etwas nicht, zeigt `./jarvis.sh pruefen` eine Checkliste mit der Lösung für jeden Punkt.

`oeffnen` öffnet deinen persönlichen Link. Er enthält einen geheimen Schlüssel, setzt ein Cookie im Browser und verschwindet dann aus
der Adresszeile. Ohne diesen Link kommt niemand an JARVIS heran.

## Die Oberfläche

| Reiter | Was du dort machst |
|---|---|
| **Jarvis** | Der leuchtende Kern zeigt, was JARVIS gerade tut (bereit, hört zu, denkt, spricht, Notstopp). Schreiben oder sprechen, Antworten vorlesen lassen, Freigaben erteilen. |
| **Leitstand** | Nur echte Zahlen: Anfragen pro Stunde, Antwortzeiten, Aufträge, Verbrauch, Agenten, Freigaben, Ereignisse. Nichts ist erfunden oder simuliert. |
| **Aufträge** | Ziel beschreiben → JARVIS macht einen **Entwurf** mit Schritten → du startest ihn (sofort oder zeitgeplant) → Prüfschicht kontrolliert jeden Schritt. Pausieren, Abbrechen, Fortsetzen, Wiederholen. |
| **Wissen** | Gedächtnis (JARVIS schlägt nur vor, du bestätigst), Aufgaben, Erinnerungen, Suche. **Geschäft** und **Privat** sind getrennt. |
| **System** | Modelle, Stimme, Werkzeuge einzeln sperren, Sicherung, Export, Protokolle, „Alles löschen“. |

Oben rechts: **NOTSTOPP**. Er hält sofort alles an (laufende Anfrage, Aufträge, Sprache) und lehnt offene Freigaben ab.

## Sprache

- **Vorlesen:** über die Stimme des Macs (`say`). JARVIS wählt automatisch die beste deutsche Stimme. Für eine natürlichere Stimme:
  Systemeinstellungen → Bedienungshilfen → Gesprochene Inhalte → Systemstimme → Stimmen verwalten → Deutsch → „Premium“ oder „Erweitert“ laden.
- **Zuhören:** Mikrofon-Taste (einmal) oder Schalter **„Hey Jarvis“** (dauerhaft: „Hey Jarvis, was steht heute an?“). Die Erkennung macht
  dein **Browser** (Safari: Apple, Chrome: Google), nicht JARVIS. Sie läuft nur direkt auf dem Mac (Adresse 127.0.0.1).
- **Freigaben gibst du nur per Klick**, nie per Sprache.

## Was JARVIS darf

Drei Stufen, im Code erzwungen (nicht nur im Prompt):

1. **Frei:** lesen, auflisten, planen.
2. **Mit Meldung:** neue Dateien in der Werkstatt, Aufgaben, Erinnerungen, Recherche.
3. **Nur nach deinem Ja:** Dateien überschreiben oder löschen (mit Vorschau, nichts wird endgültig gelöscht), alles nach einer Webrecherche im privaten Bereich.

JARVIS **sendet, bezahlt und installiert nichts** und führt keine Programme aus. Seine Dateien liegen in `~/Jarvis-Werkstatt`; weitere Ordner gibst du
selbst in `~/.jarvis/config.json` frei (nur lesen).

## Befehle (`./jarvis.sh …`)

| Befehl | Wirkung |
|---|---|
| `start` / `stopp` / `status` | starten, beenden, Zustand anzeigen |
| `oeffnen` / `link` | Oberfläche öffnen / Link anzeigen |
| `frage "…"` | eine Frage im Terminal stellen |
| `notstopp` / `entsperren` | alles anhalten / wieder freigeben |
| `pruefen` | Systemcheck: Python, Claude Code, Stimme, Port, Ordner – mit Lösung bei jedem Fehler |
| `provider` | ist Claude Code bereit? (verbraucht kein Kontingent) |
| `logs [N]` | die letzten Log-Einträge |
| `backup` / `wiederherstellen DATEI` | Datenbank sichern / zurückholen (nur bei gestopptem Server) |
| `export [DATEI]` | alle Daten als JSON (Rechte 600) |
| `lan an` / `lan aus` | Zugriff aus dem WLAN erlauben / sperren |
| `umgebung` | was JARVIS über diesen Mac erkennt |

## Handy im WLAN

1. `./jarvis.sh lan an` (zeigt die Risiken und fragt nach „ja“), dann `./jarvis.sh stopp` und `./jarvis.sh start`.
2. `./jarvis.sh link` zeigt zusätzlich die WLAN-Adressen. Diesen Link auf dem Handy öffnen.

Grenzen, ehrlich: Die Verbindung ist **nicht verschlüsselt** (nur in einem Netz nutzen, dem du vertraust). Spracheingabe geht auf dem Handy so nicht
(der Browser verlangt dafür eine sichere Verbindung); tippen und Diktieren der Tastatur gehen. **Von unterwegs** geht es nicht; dafür bräuchte es einen
verschlüsselten Weg wie Tailscale, den es hier noch nicht gibt. Den Router niemals für JARVIS öffnen.

## Sicherheit in Kürze

- Hört nur auf `127.0.0.1` (außer du schaltest `lan an`). Host-Prüfung gegen DNS-Rebinding, Herkunftsprüfung gegen fremde Webseiten.
- Alles unter `/api/` braucht den Schlüssel (Datei `~/.jarvis/token`, Rechte 600; Cookie `HttpOnly`, `SameSite=Strict`). Datenordner `~/.jarvis` hat Rechte 700.
- Ratenbegrenzung, Größenlimit, Zeitlimit pro Verbindung.
- Inhalte aus dem Internet und Werkzeugausgaben gelten als **unvertrauenswürdige Daten**, nie als Anweisung. Danach braucht jede weitere Aktion eine Freigabe.
- Geschäft und Privat sind getrennt: Das Modell sieht pro Gespräch nur einen Bereich.
- Alles Verändernde steht im **Audit** (System → Protokolle).

## Daten

Alles liegt in `~/.jarvis/`: Datenbank `jarvis.db`, `config.json`, `token`, `logs/`, `backups/` (täglich, die letzten 7 bleiben). Einstellungen änderst du
unter System; weitere Möglichkeiten (Port, WLAN, Ordner, Limits) stehen in `config.json`. Umgebungsvariablen gehen vor: `JARVIS_PORT`, `JARVIS_DATEN`,
`JARVIS_WERKSTATT`, `JARVIS_MODELL`, `JARVIS_LOGSTUFE`.

Beim ersten Start liest JARVIS `BRAIN.md` ein (**ersetzt** beim erneuten Einlesen die importierten Einträge; deine eigenen bleiben).

## So bleibt es kostenlos

- Claude Code wird nur genutzt, wenn die Anmeldeart das **Abo** (`claude.ai`) ist. Bei einer Anmeldung über API-Schlüssel verweigert JARVIS die Nutzung.
- Umgebungsvariablen, die auf eine bezahlte Abrechnung umlenken würden (`ANTHROPIC_API_KEY` u. a.), werden bei jedem Aufruf entfernt.
- Es gibt keinen Ersatzweg über eine bezahlte Schnittstelle. Ist Claude Code nicht bereit, sagt JARVIS das.
- Immer nur **ein** Modellaufruf zugleich. Bei Abo-Limit weicht er **sichtbar** von Opus auf Sonnet aus (abschaltbar).

## Tests

```
python3 -m unittest discover -s tests -t . -p "test_*.py"        # 161 Tests (Python 3.8 und 3.9), Claude Code simuliert
node tests/ui/ui_pruefung.js [Ordner für Bildschirmfotos]       # Browser-Test (nur Entwicklung: braucht Node und Playwright)
```
