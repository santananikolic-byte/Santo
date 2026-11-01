# JARVIS – Status

Stand: 31.10.2026. Dieser Stand wird nach jeder Stufe nachgeführt.

Bedeutung der Stände:

- **Gebaut** – Code vorhanden.
- **Getestet** – automatische Tests laufen grün. Claude Code ist dabei durch ein Ersatzprogramm simuliert, damit kein Abo-Limit verbraucht wird.
- **Verifiziert** – auf dem echten iMac mit echtem Claude ausprobiert. **Bisher: nichts.**
- **Nicht gebaut** – steht nicht im Code, auch wenn es früher geplant war.
- **Blockiert** / **Wartet auf Freigabe** – braucht etwas, das fehlt, oder deine Entscheidung.

## Was da ist

| Baustein | Stand | Beleg / Hinweis |
|---|---|---|
| Gedächtnis (SQLite): Fakten, Aufgaben, Erinnerungen, Gespräche, Aufträge, Audit; Bereiche Geschäft/Privat getrennt; Import aus `BRAIN.md`; Export; Löschen; tägliche Sicherung | Getestet | `tests/test_speicher.py` (32) |
| Denken über Claude Code mit dem Abo (kein API-Schlüssel), Modell je Aufgabe, Ausweichen bei Limit, Abbruch, Token-Zählung | Getestet (simuliert) | `tests/test_provider.py` (16). **Echter Aufruf auf dem iMac nicht verifiziert** (Startoptionen wie `--safe-mode` sind nach Claude-Code-Version verschieden; unbekannte werden automatisch weggelassen) |
| Werkzeuge (Dateien in der Werkstatt, Aufgaben, Erinnerungen, Merken, Recherche, Mac-Umgebung, Auftrag planen) und Berechtigung in drei Stufen, Freigaben mit Vorschau, Sperren, Notstopp | Getestet | `tests/test_agent.py` (33) |
| Planer, Prüfschicht, Auftragsläufer, Zeitplan, Wiederanlauf nach Neustart | Getestet | `tests/test_auftraege.py` (33) |
| Server: Zugangsschlüssel, Cookie, Host- und Herkunftsprüfung, Ratenbegrenzung, WLAN-Schalter, Start/Stopp, Sicherung/Wiederherstellung/Export | Getestet | `tests/test_kern.py` (42) |
| Oberfläche (orange Leitstand, leuchtender Kern, Chat, Freigaben, Aufträge, Gedächtnis, System, Handy-Layout) | Getestet im Browser (Chromium, simuliertes Claude) | `tests/ui/ui_pruefung.js`, nur für die Entwicklung. **Safari nicht geprüft** |
| Sprachausgabe (macOS `say`, beste deutsche Stimme automatisch) | Getestet mit Ersatzprogramm | echte Stimme nicht verifiziert |
| Spracheingabe „Hey Jarvis“ (Erkennung durch den Browser) | Logik getestet mit simuliertem Erkenner | echte Erkennung nicht verifiziert; nur direkt auf dem Mac möglich (sicherer Kontext) |
| Handy im WLAN | Gebaut | `./jarvis.sh lan an`; nur unverschlüsseltes http; Spracheingabe dort nicht möglich; nicht auf einem echten Handy verifiziert |

Zusammen: **157 automatische Tests** (unter Python 3.8 und 3.9, die Python-Versionen, die Apple auf dem Mac mitliefert) und 57 Prüfpunkte im Browser, alle grün.

## Was es nicht gibt (und warum)

| Baustein | Stand | Grund |
|---|---|---|
| Programme und Skripte ausführen, Test-Arbeiter | Nicht gebaut | braucht eine eigene, strengere Sicherheitsstufe; kommt als eigene Stufe, nicht nebenbei |
| Autostart beim Anmelden (launchd) | Nicht gebaut | außerhalb des Macs nicht testbar; ein ungetesteter Autostart könnte halbe Aufträge neu starten |
| Zugriff von unterwegs | Nicht gebaut | braucht einen verschlüsselten Weg (zum Beispiel Tailscale) und deine Freigabe |
| Browser-Automation | Blockiert | braucht zusätzliche Software und deine Zustimmung |
| Mail, Kalender, Finanzen, Kundenverwaltung | Nicht gebaut | spätere Stufen; Senden bleibt immer freigabepflichtig |
| Selbstverbesserung des eigenen Codes | Nicht gebaut | bewusst nicht: JARVIS ändert seinen Code nicht von allein |
| Mehrere Arbeiter gleichzeitig | Nicht gebaut | ein Modellaufruf zugleich schont dein Abo-Limit |

## Offene Entscheidungen

- Das Repo ist öffentlich, `BRAIN.md` enthält Persönliches. Privat stellen oder `BRAIN.md` aus dem Repo nehmen? (Siehe `BRAIN.md`, „Nächster Schritt 0“.)
- Bessere deutsche Stimme laden (macOS: Systemeinstellungen → Bedienungshilfen → Gesprochene Inhalte → Systemstimme → Stimmen verwalten).

Die Selbstprüfung mit allen gefundenen und behobenen Fehlern steht in `SELBSTPRUEFUNG.md`.
