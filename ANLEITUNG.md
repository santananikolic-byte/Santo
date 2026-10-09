# So baust du deinen Jarvis mit Claude Code

Du hast Claude Code schon. Damit baust du genau den Jarvis von den Bildern —
der dich durch die Kamera sieht, deine Mails sortiert, im Netz recherchiert,
ein Gedächtnis hat und auf deinem Mac arbeitet. Das ist der echte, mit echten
Zugriffen — kein Browser-Spielzeug.

Es sind drei Schritte. Mehr nicht.

---

## Schritt 1 — Ordner anlegen

Öffne das Terminal (Programme → Dienstprogramme → Terminal) und tippe:

    mkdir jarvis && cd jarvis

Dann leg die Datei `BAUAUFTRAG-jarvis.md` (die aus diesem Chat) in genau
diesen Ordner. Am einfachsten: Datei herunterladen, dann im Finder in den
`jarvis`-Ordner ziehen.

---

## Schritt 2 — Claude Code starten und den Auftrag geben

Im Terminal, im `jarvis`-Ordner:

    claude

Wenn Claude Code läuft, schreib genau das:

    Lies BAUAUFTRAG-jarvis.md komplett und bau das System Schritt für Schritt.
    Halte dich an die Sicherheitsregeln und arbeite die Abnahmeliste am Ende
    wirklich ab, bevor du fertig meldest.

Jetzt arbeitet Claude Code für dich. Es schreibt die Dateien, installiert was
fehlt, und prüft sich am Ende selbst. Das dauert eine Weile — lass es laufen.

**Tipp:** Wenn es nachfragt, ob es einen Befehl ausführen darf, lies kurz und
sag ja. Willst du, dass es ohne ständiges Nachfragen durchläuft, drück
`Shift + Tab`, bis „auto" dasteht. Aber nur, wenn du dabei bleibst.

---

## Schritt 3 — Jarvis starten

Wenn Claude Code fertig ist, liegt im Ordner eine Datei `JARVIS.command`.
Doppelklick drauf (beim ersten Mal Rechtsklick → „Öffnen", weil macOS fremd­
gestartete Programme erst bestätigen lässt).

Jarvis startet immer und öffnet sich im Browser (`http://localhost:8765`). Beim
ersten Mal fragt ein Fenster, **womit er denken soll**. Du hast drei Wege, und
keiner davon zwingt dich zu Guthaben:

1. **Gratis-Schlüssel (der schnellste Weg, kostenlos).** Hol dir bei Google oder
   Groq einen Schlüssel ohne Karte und ohne Guthaben:
   `aistudio.google.com/apikey` (Google Gemini) oder `console.groq.com/keys`
   (Groq). Wähl im Fenster den Anbieter, füg den Schlüssel ein, klick auf
   „Gratis-Dienst nutzen“. Jarvis probiert ihn sofort aus.
   Bei Google trägt er mehrere Modelle ein: Ist das Gratis-Kontingent eines
   aufgebraucht, nimmt er automatisch das nächste. Grenzen pro Minute und Tag
   gibt es trotzdem. Das Gespräch geht an den Anbieter.
2. **Ein Modell auf deinem Rechner (Ollama).** Kostenlos und ohne Limit, aber
   langsamer und schwächer. Ollama (`ollama.com/download`) muss installiert und
   geöffnet sein.
3. **Anthropic-Schlüssel.** Claude antwortet, das kostet Guthaben unter
   `console.anthropic.com`.

Danach fragt er nach den übrigen Zugängen — E-Mail, Telegram. Die sind
freiwillig.

**Ohne Fenster, per Terminal** (zum Beispiel für Google): Diese Zeilen tragen
den Gratis-Schlüssel direkt ein. `DEIN-SCHLUESSEL` ersetzt du durch deinen:

    cd ~/Jarvis
    printf '\nFREIER_DIENST_URL=https://generativelanguage.googleapis.com/v1beta/openai\nFREIER_DIENST_MODELL=gemini-flash-latest,gemini-flash-lite-latest,gemini-3.8-flash,gemini-3.5-flash,gemini-3.1-flash-lite\nFREIER_DIENST_SCHLUESSEL=DEIN-SCHLUESSEL\n' >> config/.env

Bei der E-Mail genügt deine Adresse. Die Servernamen kennt er selbst, und er
meldet sich einmal an, um zu prüfen, ob es wirklich stimmt. Bei Gmail, iCloud
und Outlook brauchst du ein **App-Passwort** statt deines normalen — er öffnet
dir die passende Seite dafür.

Für die Kamera, die dich sieht: Systemeinstellungen → Datenschutz → Kamera →
Terminal erlauben. Einmal. Dann sieht Jarvis dich. Die Einrichtung prüft das
selbst, indem sie ein Testbild macht, und öffnet dir die Einstellung, wenn das
Recht fehlt.

---

## Autopilot: Er arbeitet von selbst

Unter **„Heute zu tun“** (Link oben auf der Jarvis-Seite, oder
`http://localhost:8765/autopilot`) trägst du einmal ein: deinen Namen, deine
Firma, den **Ort**, in dem du Kunden suchst, und die **Branchen** (Arztpraxen,
Steuerberater, Kanzleien, Autohäuser, Fitnessstudios …).

Danach arbeitet Jarvis zweimal am Tag von selbst (08:30 und 13:30) und auf
Knopfdruck („Jetzt arbeiten“):

- **Neue Betriebe** aus OpenStreetMap (kostenlos, ohne Schlüssel), mit Telefon,
  Adresse, Webseite – und zu jedem ein **Anruf-Skript**. Sie landen in der
  Pipeline.
- **Nachfassen**: wer heute dran ist.
- **Posteingang**: Antwortentwürfe für wichtige Mails.
- **Cashflow**: Warnung, wenn ein Monat ins Minus läuft.

Alles steht auf der Seite. Dort rufst du an, hakst ab oder klickst **Senden**.
**Jarvis schickt nie von selbst Mails** – gesendet wird erst nach deinem Klick.
Neue Betriebe bekommen ein Anruf-Skript statt einer Werbemail, weil Werbemails
an Firmen ohne Einwilligung in Österreich und Deutschland in der Regel
unzulässig sind. Ist das Gratis-Kontingent gerade leer, nimmt er Vorlagen –
die Arbeit bleibt nicht liegen.

Per Sprache: „Jarvis, Autopilot starten“ oder „Was ist heute zu tun?“

---

## Was er dann kann

- **Sehen** — „Hey Jarvis, schau mal" nimmt ein Kamerabild auf und beschreibt es
- **Mails sortieren** — wichtig, später, Rauschen; Vorschläge zum Antworten
- **Recherchieren** — echtes Wetter sofort; für Preise und Flüge einmalig den
  Such-Dienst einschalten (`config/mcp_servers.json`, Eintrag `suche`)
- **Nachrichten senden** — Telegram, Mail, SMS, WhatsApp (immer mit deinem Ja)
- **Telefonieren** — „Ruf den Berger an und sag ihm, ich komme um zehn": er
  wählt und sagt den Satz an. Auch SMS. Vor jedem Anruf fragt er dich.
  Dafür brauchst du einmalig ein Twilio-Konto — die Einrichtung fragt danach.
- **Buchhaltung** — Beleg vor die Kamera, er bucht ihn vor
- **Gedächtnis** — er vergisst nichts, durchsucht alles Frühere
- **Dein Mac** — mit Bestätigung Dinge bedienen, sortieren
- **Reden** — er hört zu und antwortet gesprochen, ernst und ruhig
- **Zwei Übersichten** — ein Command Center mit deinen Zahlen und eine
  Sales-Analyse, die jedes Kundengespräch einzeln aufschlüsselt. Beide öffnest
  du über `EXTRAS.command`, Punkt 2.

---

## Wenn etwas klemmt

Sag es Claude Code direkt im selben Fenster, wörtlich, was auf dem Bildschirm
steht:

    Beim Start kommt dieser Fehler: [Text einfügen]. Behebe ihn.

Claude Code sieht deinen echten Rechner und kann den Fehler wirklich finden —
anders als ein Chat, der raten muss. Das ist der ganze Vorteil.
