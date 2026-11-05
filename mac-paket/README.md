# JARVIS – dein Assistent für Bau & Reinigung

JARVIS läuft auf deinem Mac und hilft dir beim Geschäft: Aufträge finden, Firmen
prüfen, Preise rechnen, Kunden im Blick behalten, Erinnerungen, Tagesbericht.
Du bedienst ihn im **Leitstand** (orange Seite im Browser) – per Text, Knopf oder
Stimme.

Die Kurzfassung zum Loslegen steht in **ANLEITUNG.txt**.

## Was du brauchst

- einen Mac
- dein **Claude-Abo** (Pro oder Max)

**Keinen API-Schlüssel, kein Passwort in einer Datei, keine Zusatzkosten.**
JARVIS denkt über *Claude Code*, das mit deinem Abo angemeldet ist. Ist es mit
einem API-Schlüssel angemeldet (das würde pro Anfrage kosten), weigert sich
JARVIS, es zu benutzen.

## Einrichten

Doppelklick auf `JARVIS.command`. Beim ersten Mal prüft er selbst:

1. **Python** – fehlt es, öffnet sich ein Fenster von Apple („Befehlszeilen-
   entwicklertools“, nicht die große Xcode-App). Installieren, danach nochmal
   doppelklicken.
2. **Claude Code** – fehlt es, fragt er, ob er es installieren soll (offizielle
   Installation von Anthropic). Nur mit deinem Ja.
3. **Anmeldung mit dem Abo** – der Browser geht auf, du meldest dich mit deinem
   Claude-Konto an. Intern ist das der Befehl `claude auth login --claudeai`.
4. **Start** – der Leitstand öffnet sich.

Ab dann: Doppelklick auf `JARVIS.command` = starten, `JARVIS-BEENDEN.command` =
beenden.

## Das Gehirn: Claude oder ein eigenes lokales Modell

Im Leitstand unter **System → Gehirn** stellst du ein, womit JARVIS denkt:

| | Claude (Standard) | Eigenes lokales Modell (Ollama) |
|---|---|---|
| Läuft über | dein Claude-Abo | nur deinen Mac, offline |
| Kosten / Limit | im Abo enthalten, Abo-Limit | kostenlos, kein Limit |
| Qualität | stark | deutlich schwächer, mehr Fehler bei Deutsch und Rechnen |
| Websuche | ja | nein – Recherche läuft immer über Claude |

Für das lokale Modell: Ollama von ollama.com installieren, im Terminal ein
Modell laden (zum Beispiel `ollama pull llama3.1`), dann im Leitstand
umschalten und den Modellnamen eintragen. Das lokale Gehirn spricht nur mit
deinem Mac (127.0.0.1), nie ins Internet.

## Was JARVIS kann

- **Tagesbriefing:** Was ist offen, was ist dringend, die nächsten Schritte für
  mehr Aufträge – nur aus dem, was er wirklich weiß.
- **Akquise:** sucht über öffentliche Quellen (Ausschreibungsportale,
  Firmenverzeichnisse, Kleinanzeigen) nach Aufträgen und möglichen Kunden und
  schlägt sie dir als Kontakt vor, mit Quelle.
- **Firmen und Anrufer prüfen:** Handelsregister, Geschäftsführer, Impressum,
  passt die E-Mail-Domain, Bewertungen, Insolvenzen. Wichtigster Rat: immer über
  die offiziell veröffentlichte Nummer zurückrufen.
- **Kunden-Status:** jeder Kontakt hat eine Stufe – Neu, Kontaktiert,
  Interessiert, Angebot, Gewonnen, Verloren. Die stellst du selbst ein.
- **Preise rechnen:** mit Rechenweg; dazu `Preisrechner.html` zum Doppelklicken.
- **Gedächtnis:** dein Profil (`BRAIN.md`) liest er beim ersten Start ein.
  Geschäft und Privat bleiben getrennt.
- **Aufgaben und Erinnerungen:** er meldet sie laut und als Mitteilung.
- **Entwürfe:** Anschreiben und Angebote als Datei in der „Jarvis-Werkstatt“.
- **Denkt erst nach:** bei Entscheidungen und Rechnungen geht er Ziel, Wissen
  und Annahmen, Möglichkeiten und Risiko durch, bevor er antwortet.
- **Stimme:** spricht mit der besten deutschen Mac-Stimme; zuhören über das
  Mikrofon im Leitstand („Hey Jarvis“).

## Sicherheit und Freigaben

- **Nichts senden, löschen oder bezahlen ohne dein Ja.** JARVIS hat dafür gar
  keine Werkzeuge: kein E-Mail-Versand, keine Anrufe, keine Zahlungen.
- Was er sich merken will, ist erst ein Vorschlag – du bestätigst.
- Datei überschreiben oder löschen: nur nach deiner Freigabe im Leitstand.
  „Löschen“ heißt: in den Papierkorb der Werkstatt, nicht endgültig.
- **Notstopp:** ein Klick (oder EXTRAS → 9), und alles steht.
- Der Leitstand ist nur auf deinem Mac erreichbar. Das Handy kommt nur dazu,
  wenn du es erlaubst (EXTRAS → 5).

## Handy

EXTRAS → 5 → „an“ erlaubt den Zugriff aus deinem WLAN, EXTRAS → 6 zeigt den
Link. Den Link am Handy öffnen. Hinweis: Das ist nur im eigenen WLAN gedacht
(keine Verschlüsselung), und die Spracheingabe geht dort nicht.

## Was anders ist als in der alten Fassung (jarvis-mac vom August)

| Alte Fassung | Diese Fassung | Warum |
|---|---|---|
| brauchte einen API-Schlüssel von console.anthropic.com | läuft über dein Claude-Abo | API kostet pro Anfrage; du wolltest nur das Abo |
| installierte viele Zusatzpakete (numpy, whisper …) | nichts zusätzlich, nur Python vom Mac | weniger, das kaputtgehen kann |
| Passwörter für Mail, Kalender, Telegram in `config/.env` | keine Passwörter in Dateien | deine Regel: nie Passwörter in Dateien |
| E-Mails senden, Telegram, Bildschirm steuern | gibt es nicht | „Nichts senden ohne mein Ja“ – kommt nur später, und dann nur mit Freigabe |
| Spracherkennung mit faster-whisper | Spracherkennung im Browser | ohne Installation |

Noch **nicht** dabei (aus der alten Fassung): automatisches Morgen-Briefing um
06:45, Auswertung von Kundengesprächen mit Punktzahl, Buchhaltung mit Belegfotos,
Mail und Kalender. Das kann später kommen – Mail und Kalender aber nur so, dass
JARVIS liest und entwirft und du selbst sendest.

## Wenn etwas nicht läuft

1. **EXTRAS → 2 (Selbsttest).** Er sagt bei jedem Punkt, was fehlt, und darunter
   die Lösung. `✓` = gut, `!` = geht auch ohne, `✗` = muss behoben werden.
2. **„nicht angemeldet“** → EXTRAS → 3 (Claude-Abo anmelden).
3. **„angemeldet über … statt über das Claude-Abo“** → Claude Code ist mit einem
   API-Schlüssel angemeldet. Im Terminal `claude auth logout`, dann EXTRAS → 3.
4. **Doppelklick tut nichts / „keine Berechtigung“** → `RECHTE_SETZEN.command`
   doppelklicken. Geht auch das nicht: Terminal öffnen, `sh ` tippen (mit
   Leerzeichen), die Datei `RECHTE_SETZEN.command` ins Fenster ziehen, Enter.
5. **„Port ist belegt“** → läuft noch ein alter JARVIS? Erst
   `JARVIS-BEENDEN.command`, dann neu starten.
6. **Er spricht nicht** → Systemeinstellungen → Bedienungshilfen → Gesprochene
   Inhalte → Systemstimme → Stimmen verwalten → Deutsch → eine „Premium“-Stimme
   laden.
7. **Mikrofon im Leitstand geht nicht** → in Chrome am einfachsten. In Safari
   erst Systemeinstellungen → Tastatur → Diktat einschalten.

Hilft das nicht: ein Foto vom Fenster an Claude schicken.

## Was im Ordner liegt

```
ANLEITUNG.txt            Kurzanleitung
README.md                diese Datei
JARVIS.command           Start (richtet sich beim ersten Mal selbst ein)
JARVIS-BEENDEN.command   Beenden
EXTRAS.command           Selbsttest, Anmeldung, Handy, Sicherung, Notstopp
RECHTE_SETZEN.command    nur nötig, wenn ein Doppelklick nicht geht
Preisrechner.html        Preisrechner, läuft ohne Internet
BRAIN.md                 dein Profil – liest JARVIS beim ersten Start ein
config/LIES-MICH.txt     warum hier nichts einzutragen ist
docs/STATUS.md           ehrlicher Stand: was gebaut, getestet, ausprobiert ist
jarvis.sh                Steuerung (wird von den .command-Dateien benutzt)
jarvis_core/             das Programm selbst (nur Python, keine Zusatzpakete)
```

## Ehrlicher Stand

Alles ist in der Entwicklungsumgebung automatisch getestet (mit einem
Ersatz für Claude, damit dein Abo nicht verbraucht wird). **Auf deinem Mac ist es
noch nicht ausprobiert.** Was beim ersten Start hakt, bitte mit Foto melden –
genau dafür ist der Selbsttest da. Einzelheiten in `docs/STATUS.md`.
