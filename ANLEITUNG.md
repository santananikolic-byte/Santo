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
    printf '\nFREIER_DIENST_URL=https://generativelanguage.googleapis.com/v1beta/openai\nFREIER_DIENST_MODELL=gemini-flash-lite-latest,gemini-3.5-flash-lite,gemini-3.1-flash-lite,gemini-flash-latest,gemini-3.8-flash\nFREIER_DIENST_SCHLUESSEL=DEIN-SCHLUESSEL\n' >> config/.env

Bei der E-Mail genügt deine Adresse. Die Servernamen kennt er selbst, und er
meldet sich einmal an, um zu prüfen, ob es wirklich stimmt. Bei Gmail, iCloud
und Outlook brauchst du ein **App-Passwort** statt deines normalen — er öffnet
dir die passende Seite dafür.

Für die Kamera, die dich sieht: Systemeinstellungen → Datenschutz → Kamera →
Terminal erlauben. Einmal. Dann sieht Jarvis dich. Die Einrichtung prüft das
selbst, indem sie ein Testbild macht, und öffnet dir die Einstellung, wenn das
Recht fehlt.

---

## Sehen – über die Kamera und den Bildschirm im Browser

Ohne Homebrew und ohne Zusatzprogramm: Sag im Jarvis-Fenster **„schau mal“**,
**„was siehst du“** oder **„lies das vor“** – die Seite macht ein Foto mit der
Kamera des Macs und schickt es mit der Frage an das Gehirn. Die Kamera geht
sofort danach wieder aus. Beim ersten Mal fragt der Browser, ob er die Kamera
benutzen darf.

Mit **„Bildschirm teilen“** (oben rechts) sieht Jarvis deinen Bildschirm,
solange du teilst: „Was ist auf meinem Bildschirm offen?“ Mit „Kamera aus“
schaltest du das Foto ab.

## Terminal

Nach dem Start zeigt das Terminal alle Fähigkeiten nach Bereichen. Du kannst
Jarvis dort auch **schreiben** – gleichzeitig zur Sprache im Browser:
`Du › Leg einen Punkt an: Freitag Berger anrufen`. `hilfe` zeigt die Liste,
`beenden` oder Strg+C hört auf.

---

## Seiten lesen und suchen – ohne Zusatzprogramme

„Jarvis, lies www.beispiel.at und sag mir die Öffnungszeiten“: Er holt die
Seite selbst und zerlegt sie in Text, Mailadressen, Telefonnummern und Links –
ohne Playwright, ohne Chromium. Gesucht wird der Reihe nach über den
Such-Dienst (falls eingerichtet), die Google-Suche deines Gemini-Schlüssels,
DuckDuckGo und Mojeek. Adressen im eigenen Netz (Router, 127.0.0.1) liest er
nie, auch nicht über eine Weiterleitung.

Einfache Aufträge („Leg einen Punkt an …“, „Notier …“) bestätigt er direkt,
ohne das Gehirn ein zweites Mal zu fragen – das spart die Hälfte der Zeit.

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

## Stimme

Oben auf der Jarvis-Seite: **Stimme**. Ohne Auswahl nimmt Jarvis die beste
deutsche Stimme, die dein Browser hat (Premium- und Natural-Stimmen zuerst,
eine männliche bevorzugt). Du kannst Stimme, Tempo und Tonlage selbst wählen –
„Probe hören“, dann „Übernehmen“. Lange Antworten liest er in Stücken, damit
Chrome nicht mittendrin abbricht.
**Bessere Stimme am Mac (kostenlos):** Systemeinstellungen → Bedienungshilfen →
Gesprochene Inhalte → Systemstimme → Stimmen verwalten → Deutsch → eine
Premium-Stimme laden (z. B. Markus oder Anna). Danach steht sie in der Auswahl.

---

## Rechnungen, Angebote, Mahnungen – als PDF

Einmal unter **„Heute zu tun“ → Einstellungen → Firmendaten** deine Adresse,
UID, IBAN, BIC, Telefon und Mail eintragen (Kleinunternehmer ankreuzen, falls
du keine Umsatzsteuer verrechnest). Hast du schon Rechnungen aus einem anderen
Programm, trag die **nächste Rechnungsnummer** ein (z. B. `2026-046`) – Jarvis
macht dort weiter.

Dann einfach sagen:

- „Rechnung an Praxis Huber: Unterhaltsreinigung Oktober, 13 Einsätze zu 65 Euro.“
- „Angebot für Kanzlei Berger, 220 Quadratmeter Fliesen, dreimal die Woche.“
- „Welche Rechnungen sind offen?“ · „Rechnung 7 ist bezahlt.“
- „Mahnung für 2026-007.“ · „Schick die Rechnung an Huber.“ (fragt vorher)

Jarvis vergibt die Nummer fortlaufend, rechnet 20 % USt (oder keine, mit dem
Kleinunternehmer-Vermerk), setzt 14 Tage Zahlungsziel und legt das PDF im Ordner
`rechnungen` ab. Adresse und Mail des Kunden holt er aus deinen Kontakten.
**Bezahlt** bucht die Einnahme gleich in die Buchhaltung. Ist eine Rechnung
überfällig, steht sie unter „Heute zu tun“ – mit Knopf für Zahlungserinnerung,
1. und 2. Mahnung. Falsche Rechnung? „Storniere Rechnung 7“ schreibt eine
Stornorechnung; gelöscht wird nie etwas. Für Bauunternehmer als Kunden gibt es
den Übergang der Steuerschuld (§ 19 Abs. 1a UStG, braucht deren UID).
Die fachliche Prüfung bleibt beim Steuerberater.

---

## Browser-Erweiterung: Jede Webseite mit Jarvis besprechen

Im Ordner `erweiterung` liegt eine Erweiterung für **Chrome** (auch Edge, Brave):

1. In Chrome `chrome://extensions` öffnen, oben rechts **Entwicklermodus** an.
2. **„Entpackte Erweiterung laden“** → den Ordner `Santo/erweiterung` wählen.
3. Auf das Puzzle-Symbol klicken und Jarvis anpinnen.

Auf jeder Seite: Jarvis-Symbol (oder **Alt+Shift+J**) → **Seite
zusammenfassen**, **Kontakte als Interessent übernehmen** oder eine eigene
Frage. Markierter Text: Rechtsklick → **„Mit Jarvis besprechen“**. Die
Erweiterung redet nur mit Jarvis auf deinem iMac (`localhost:8765`), sonst mit
niemandem. Text auf einer Webseite ist für Jarvis Inhalt, nie ein Auftrag: In
diesen Runden kann er nur lesen und Neues anlegen (Notiz, Kontakt,
Interessent, Punkt) – nichts löschen, nichts senden, nichts bezahlen.

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
