# JARVIS – Status

Stand: 08.11.2026. Dieser Stand wird nach jeder Stufe nachgeführt.

Bedeutung der Stände:

- **Gebaut** – Code vorhanden.
- **Getestet** – automatische Tests laufen grün. Claude Code ist dabei durch ein Ersatzprogramm simuliert, damit kein Abo-Limit verbraucht wird.
- **Verifiziert** – mit echtem Claude Code ausprobiert. Auf deinem Mac: **bisher nichts**. In der Entwicklungsumgebung gab es einen echten Probelauf (siehe Tabelle).
- **Nicht gebaut** – steht nicht im Code, auch wenn es früher geplant war.
- **Blockiert** / **Wartet auf Freigabe** – braucht etwas, das fehlt, oder deine Entscheidung.

## Was da ist

| Baustein | Stand | Beleg / Hinweis |
|---|---|---|
| Gedächtnis (SQLite): Fakten, Aufgaben, Erinnerungen, Gespräche, Aufträge, Audit; Bereiche Geschäft/Privat getrennt; Import aus `BRAIN.md`; Export; Löschen; tägliche Sicherung; Datenbank-Migration (neue Spalten rüsten sich bei einer schon bestehenden Datenbank selbst nach) | Getestet | `tests/test_speicher.py` (34) |
| Kundenstatus (CRM-Kern) für Kontakte: Stufen Neu → Kontaktiert → Interessiert → Angebot → Gewonnen/Verloren, in der Oberfläche änderbar, JARVIS liest sie nur und setzt sie nie selbst | Getestet | `jarvis_core/api.py` (`PIPELINE_STUFEN`); lokal in der Datenbank - **kein echtes CRM mit Postfach, Telefon oder Kalender** |
| **Gehirn** (`jarvis_core/gehirn.py`): Grundregeln immer, dazu nur die passenden Wissensbausteine (Firmenprüfung, Akquise, Tagesbericht, Preise und Angebote, E-Mail, Kundengespräch) – bei einer einfachen Frage ist der Systemprompt dadurch rund halb so lang; Rückfragen behalten den Baustein | Getestet | `tests/test_gehirn.py` (Prüfstand mit Beispielsätzen und Fallen). Ob die Antworten mit echtem Claude dadurch besser werden, ist **nicht gemessen** |
| **Denkstufen**: Gruß, Merken und kurze Fragen gehen an das schnelle Modell (Standard sonnet), Preise, Kundentexte, Prüfungen und Entscheidungen an das gründliche (Standard opus); im Leitstand abschaltbar | Getestet (simuliert) | `tests/test_gehirn.py`; die Zeitersparnis mit echtem Claude ist **nicht gemessen** |
| **Ehrlichkeitsprüfung im Code**: behauptet eine Antwort „gesendet“, „gelöscht“, „verschoben“, „angerufen“, „bezahlt“ oder „gebucht“, ohne dass ein Werkzeug es belegt, hängt JARVIS sichtbar eine Richtigstellung an (auch im Verlauf und im Audit) | Getestet | `tests/test_gehirn.py`, `tests/test_mail.py`: Beispielsätze in beide Richtungen, u. a. „Berger hat dir eine Mail gesendet“ löst **keine** Richtigstellung aus. Eine Wortprüfung kann Sonderfälle übersehen – sie ist ein Sicherheitsnetz, kein Beweis |
| **Gedächtnissuche für zusammengesetzte Wörter**: „Reinigung“ findet „Treppenhausreinigung“, „Verwaltung“ findet „Hausverwaltung“ | Getestet | `tests/test_gehirn.py` |
| **E-Mail über die Mail-App des Macs** (`jarvis_core/mail.py`): Postfächer aller Konten ansehen und sortieren, E-Mail lesen (Konto + Nummer), Konten und Ordner auflisten (frei; Inhalte zählen als Außenquelle), Entwurf in der Mail-App öffnen (mit Meldung; nach gelesenen Außeninhalten nur mit Freigabe – du schickst selbst ab), **senden und in Ordner verschieben nur nach deiner Freigabe** mit ganzer E-Mail, Absender und Endmarke in der Vorschau; Papierkorb/Spam als Ziel und Löschen gibt es nicht. Kein Passwort in JARVIS – die Mail-App ist schon angemeldet | Getestet mit Ersatz-Mail-App | `tests/test_mail.py`: Nutzertext wird nie Skriptcode, ohne Freigabe geht nichts raus (auch nicht aus Aufträgen, im Notstopp oder wenn eine präparierte E-Mail es verlangt), je ein Test für die 12 Befunde der unabhängigen Prüfung (siehe `SELBSTPRUEFUNG.md`, Stufe 14). **Die AppleScript-Befehle sind auf keinem echten Mac geprüft** – sie folgen der Recherche (gesammeltes Lesen, Konto + Nummer); beim ersten Zugriff fragt macOS nach der Erlaubnis (Automation) |
| Denken über Claude Code mit dem Abo (kein API-Schlüssel), Modell je Aufgabe, Ausweichen bei Limit, Abbruch, Token-Zählung | Getestet (simuliert) | `tests/test_provider.py` (16). **Echter Aufruf auf dem iMac nicht verifiziert.** Alle verwendeten Startoptionen (`--tools ""`, `--safe-mode`, `--system-prompt`, `--output-format json`, `--model`, `--allowedTools` …) wurden gegen die echte Hilfe von Claude Code 2.1.316 geprüft, derselben Version wie auf deinem iMac; unbekannte Zusatzoptionen lässt JARVIS selbständig weg (2.1.318 kennt `--safe-mode` nicht mehr). Neu: `--strict-mcp-config` – keine fremden MCP-Dienste an den Freigaben vorbei; `--bare` bewusst nicht, weil es die Abo-Anmeldung abschaltet |
| Eigenes lokales Gehirn (Ollama) als Alternative zu Claude: Umschalter `gehirn` (claude/lokal) im Leitstand, Modellwahl, nur lokale Adresse (127.0.0.1/localhost) erlaubt, Websuche/Recherche bleibt bei Claude; der Systemcheck richtet sich nach dem gewählten Gehirn | Getestet (simuliert) | `tests/test_lokal.py` (10) mit einem Ersatz-Ollama, Systemcheck in `tests/test_kern.py`. **Echtes Ollama auf deinem Mac nicht verifiziert** – zum Nutzen: Ollama installieren und ein Modell laden. Ein lokales Modell ist deutlich schwächer als Claude; Standard bleibt darum Claude |
| **Mac-Paket `jarvis-mac.zip`** (Aufbau wie die alte Vorlage „jarvis-mac“): `JARVIS.command` richtet beim ersten Doppelklick Python, Claude Code und die Anmeldung mit dem Abo (`claude auth login --claudeai`) ein – jede Installation nur nach Ja –, `EXTRAS.command` mit Nummernmenü, `JARVIS-BEENDEN.command`, `ANLEITUNG.txt`. Kein API-Schlüssel, keine Passwörter, keine Zusatzpakete | Getestet (in der Entwicklungsumgebung entpackt und ausgeführt, mit Ersatz-Claude) | `tests/test_paket.py` (7), u. a.: ohne Ja wird nichts installiert, Meldungen sind nicht geschönt. Der Anmeldebefehl wurde gegen die echte Hilfe von Claude Code 2.1.318 geprüft. **Auf deinem Mac nicht verifiziert** – nur dort prüfbar: Gatekeeper-Sperre beim ersten Öffnen, das Apple-Fenster für Python, `open` für den Browser |
| Echte Gehirn-Probe: echtes Claude Code 2.1.318 (sonnet/haiku, Entwicklungsumgebung) mit den Prompts des neuen Gehirns – Preisrechnung ohne erfundenen Stundensatz, E-Mail als Entwurf mit „Sie“, präparierte Betrugs-Mail erkannt, „Schick ab“ legt nur zur Freigabe vor; zwei gefundene Schwächen behoben und nachgeprüft | **Verifiziert** (dort, je ein Lauf, nicht auf deinem Mac und nicht mit opus) | `SELBSTPRUEFUNG.md`, Stufe 14 |
| Echter Probelauf: echtes Claude Code 2.1.316 (Modell haiku, Entwicklungsumgebung) durch den echten Agenten | **Verifiziert** (dort, nicht auf deinem Mac) | Format der Ausgabe, Startoptionen, Profilwissen, Datei anlegen, Erinnerung, ehrliche Ablehnung von „E-Mail senden“, gültiger Plan; Details in `SELBSTPRUEFUNG.md` |
| Werkzeuge (Dateien in der Werkstatt, Aufgaben, Erinnerungen, Merken, Recherche, Mac-Umgebung, Auftrag planen) und Berechtigung in drei Stufen, Freigaben mit Vorschau, Sperren, Notstopp | Getestet | `tests/test_agent.py` (34) |
| Rolle **Vertrieb/Akquise**: sucht Aufträge/Kunden über öffentliche Quellen, prüft die Firma, schlägt Treffer als Kontakt vor (neue Fakt-Art „kontakt“), entwirft Anschreiben in der Werkstatt | Getestet (simuliert) | `jarvis_core/rollen.py`; **sendet nichts** – E-Mail gibt es nur im Gespräch mit dir, nicht in Aufträgen; Telefon und Kalender sind nicht angebunden |
| Planer, Prüfschicht, Auftragsläufer, Zeitplan, Wiederanlauf nach Neustart | Getestet | `tests/test_auftraege.py` (33) |
| Server: Zugangsschlüssel, Cookie, Host- und Herkunftsprüfung, Ratenbegrenzung, WLAN-Schalter, Start/Stopp, Sicherung/Wiederherstellung/Export | Getestet | `tests/test_kern.py` (42) |
| Oberfläche (orange Leitstand, leuchtender Kern, Chat, Freigaben, Aufträge, Gedächtnis, System, Handy-Layout) | Getestet im Browser (Chromium, simuliertes Claude) | `tests/ui/ui_pruefung.js`, nur für die Entwicklung. **Safari nicht geprüft** |
| Sprachausgabe (macOS `say`, beste deutsche Stimme automatisch) | Getestet mit Ersatzprogramm | echte Stimme nicht verifiziert |
| Spracheingabe „Hey Jarvis“ (Erkennung durch den Browser) | Logik getestet mit simuliertem Erkenner | echte Erkennung nicht verifiziert; nur direkt auf dem Mac möglich (sicherer Kontext) |
| Handy im WLAN | Gebaut | `./jarvis.sh lan an`; nur unverschlüsseltes http; Spracheingabe dort nicht möglich; nicht auf einem echten Handy verifiziert |

Zusammen: **248 automatische Tests** (unter Python 3.8, 3.9 und 3.13; 3.8 und 3.9 liefert Apple auf dem Mac mit) und 64 Prüfpunkte im Browser, alle grün.

## Was es nicht gibt (und warum)

| Baustein | Stand | Grund |
|---|---|---|
| Programme und Skripte ausführen, Test-Arbeiter | Nicht gebaut | braucht eine eigene, strengere Sicherheitsstufe; kommt als eigene Stufe, nicht nebenbei |
| Autostart beim Anmelden (launchd) | Nicht gebaut | außerhalb des Macs nicht testbar; ein ungetesteter Autostart könnte halbe Aufträge neu starten |
| Zugriff von unterwegs | Nicht gebaut | braucht einen verschlüsselten Weg (zum Beispiel Tailscale) und deine Freigabe |
| Browser-Automation | Blockiert | braucht zusätzliche Software und deine Zustimmung |
| Kalender, Finanzen, Buchhaltung | Nicht gebaut | spätere Stufen |
| E-Mails löschen, weiterleiten, Anhänge | Nicht gebaut | Löschen bewusst nie; Weiterleiten und Anhänge erst, wenn das Senden auf deinem Mac erprobt ist |
| Anrufe | Nicht gebaut | JARVIS kann keine Gespräche führen; höchstens später einen Anruf über dein iPhone starten, sprechen musst du selbst |
| Selbstverbesserung des eigenen Codes | Nicht gebaut | bewusst nicht: JARVIS ändert seinen Code nicht von allein |
| Mehrere Arbeiter gleichzeitig | Nicht gebaut | ein Modellaufruf zugleich schont dein Abo-Limit |

## Offene Entscheidungen

- Das Repo ist öffentlich, `BRAIN.md` enthält Persönliches. Privat stellen oder `BRAIN.md` aus dem Repo nehmen? (Siehe `BRAIN.md`, „Nächster Schritt 0“.)
- Bessere deutsche Stimme laden (macOS: Systemeinstellungen → Bedienungshilfen → Gesprochene Inhalte → Systemstimme → Stimmen verwalten).

Die Selbstprüfung mit allen gefundenen und behobenen Fehlern steht in `SELBSTPRUEFUNG.md`.
