# Jarvis

Ein persönlicher Sprachassistent für einen Einzelunternehmer in der
Gebäudereinigung. Er läuft auf dem Mac, wird per Sprache bedient und antwortet
gesprochen.

Alle Daten bleiben auf dem eigenen Rechner. Was nach außen geht, geht nur nach
ausdrücklicher Freigabe.

---

Weiterzugeben ist das als Paket aus `BAUAUFTRAG-jarvis.md` und `ANLEITUNG.md` —
die Anleitung führt in drei Schritten von Claude Code zum laufenden Jarvis.

## Loslegen

Der kürzeste Weg — eine Zeile ins Terminal, sonst nichts:

```bash
curl -fsSL https://raw.githubusercontent.com/santananikolic-byte/Santo/claude/new-session-o54yqu/install.sh | bash
```

Das lädt Jarvis nach `~/Jarvis`, holt was fehlt, legt eine Verknüpfung auf den
Schreibtisch und startet die Einrichtung. Dieselbe Zeile später noch einmal
ausgeführt aktualisiert ihn — Schlüssel und Gedächtnis bleiben unangetastet.

Wer die Dateien schon von Hand geholt hat:

1. Den Ordner an einen festen Platz legen, zum Beispiel in **Dokumente**.
2. Doppelklick auf **`JARVIS.command`**.
3. Beim ersten Mal richtet sich alles selbst ein. Jarvis liest jeden Schritt
   vor — mitlesen ist nicht nötig.
4. **Danach das Terminal-Fenster einmal schließen und neu öffnen.** Sonst
   greifen die erteilten Rechte nicht.
5. Wieder Doppelklick auf `JARVIS.command`. Jetzt hört er zu.

Öffnet macOS die Datei nicht, weil sie „aus dem Internet“ stammt: Rechtsklick
auf `JARVIS.command`, dann *Öffnen*, dann im Fenster nochmal *Öffnen*.

### Was gebraucht wird

Nur **ein einziger Schlüssel**: der von Anthropic. Die Einrichtung öffnet die
Seite, nimmt den Schlüssel entgegen und probiert ihn sofort aus — ein Schlüssel,
der erst beim ersten Gespräch auffällt, hilft niemandem.

Alles andere ist freiwillig: Sprechen kann Jarvis mit der macOS-Stimme (gratis,
schon da), zuhören mit lokaler Spracherkennung (gratis). Telegram, E-Mail und
Kalender kann man einrichten, muss man aber nicht.

---

## Die Web-App

Der Normalfall: `python3 jarvis.py` startet einen kleinen Server und öffnet
Jarvis im Browser. **Er hört von selbst zu.** Du sagst „Hey Jarvis" und dann,
was du brauchst — kein Knopf, kein Textfeld. Er antwortet laut.

Auch Freigaben sprichst du: er liest die Frage vor, du sagst *ja* oder *nein*.
Getippt wird nur, wenn das Mikrofon streikt — dafür gibt es oben rechts einen
Notweg.

Rechts steht der Stand: was der Betrieb tragen muss, die Kasse, wer heute
nachzufassen ist. Braucht eine Aktion deine Freigabe, kommt ein Fenster mit
dem vollen Wortlaut — bei einem Skript mit dem ganzen Code.

Vom Handy im selben WLAN: `python3 jarvis.py web --offen`. Dann steht ein
Schlüssel in der Adresse, und **ohne ihn kommt niemand herein** — dieser Server
darf Mails lesen, Skripte ausführen und Geld verbuchen. Ohne `--offen` hört er
nur auf diesen Rechner.

Braucht Safari oder Chrome; Firefox kann keine deutsche Spracherkennung und
bekommt deshalb keinen Mikrofonknopf, sondern einen Hinweis.

## Aufbau: Erinnern und Umsetzen

**Das Gehirn dahinter ist Claude Opus 5.5**, das stärkste allgemeine Modell von
Anthropic. Es denkt vor jeder Antwort mit und bedient die Werkzeuge: rechnet
Angebote, legt Kunden an, schreibt Mails, baut Webseiten und Chatbots. Nur reiner
Smalltalk („Hallo“, „Danke“) geht an das schnelle Gemini. Eine Frage kostet je nach
Umfang etwa 2 bis 20 Cent; das Monatslimit (`MONATSLIMIT_EURO`, anfangs 15 Euro)
bremst, bevor es teuer wird. Halb so teuer: `CLAUDE_MODEL=claude-sonnet-5-5`.

Jarvis hat zwei Bereiche, so wie ein Mensch im Betrieb.

**Erinnern.** Das Gedächtnis liegt lokal in einer Datenbank: Notizen, Kunden,
Gespräche, Zahlen, Tagesberichte, offene Punkte. Vor jeder Antwort holt er sich
heraus, was zur Frage passt, und nutzt es beiläufig. Er merkt sich von selbst,
was wichtig klingt, und vergisst nichts, was du ihm sagst.

**Umsetzen.** Hier arbeiten die Fachkräfte, im Gespräch oder im Hintergrund
über den Autopiloten:

| Fachkraft | Macht |
|---|---|
| der zweite Chef | Lage des Betriebs, Prioritäten, Entscheidungen vorbereiten, Aufträge verteilen |
| der Verkäufer | Pipeline, Nachfassen, Angebote kalkulieren und schreiben |
| der Buchhalter, Controller | Buchungen, Belege, Kasse, Cashflow |
| der Postbearbeiter, Terminplaner | Posteingang, Antwortentwürfe, Kalender |
| der Webdesigner | fertige Webseiten und Landingpages als HTML-Datei |
| der Chatbot-Bauer | Bot-Anweisung, häufige Fragen, Gesprächsablauf, Einbindung |
| der Marketingmann | Beiträge, Anschreiben, Kampagnen mit Erfolgskennzahl |
| der Programmierer | kleine Programme und Auswertungen |
| der Rechercheur, Kundenberater, Privatsekretär | Recherche, Gesprächsbewertung, private Fixkosten |

Was die Webdesigner-, Chatbot- und Marketing-Fachkräfte bauen, liegt unter
`werkstatt/projekte/<Projekt>/`. Es wird **nur geschrieben, nie ausgeführt**,
und Dateien mit Schlüsseln oder Tokens werden abgelehnt.

Die Branche stellst du in der Einrichtung ein (`BRANCHE`). Sie steht in jedem
Auftrag. Die Kalkulation über Leistungswerte ist auf Reinigung zugeschnitten,
der Rest arbeitet in jeder Branche.

## Sprechen wie ein Mensch

Was Jarvis sagt, wird erst ins Gesprochene übersetzt: Beträge, Daten, Uhrzeiten
und Einheiten werden ausgeschrieben ("eintausendneunundsechzig Euro sechzig",
"am sechsten Oktober um vierzehn Uhr dreißig"), Markdown, Links und Code fallen
weg, Telefonnummern bleiben Ziffern. Danach wird der Text in kurze Atemabschnitte
geteilt, und doppelte Sätze oder Wortschleifen werden einmal gesprochen.

Mit ElevenLabs wird der nächste Abschnitt schon geholt, während der vorige läuft,
und jeder Abschnitt kennt den Satz davor und danach, damit die Betonung
durchläuft. Fällt ElevenLabs aus, spricht die Systemstimme nur den Rest. Im
Browser wird Abschnitt für Abschnitt gesprochen, mit der besten deutschen
Stimme, die der Browser hat. Am natürlichsten klingt ElevenLabs
(`python3 jarvis.py zugang stimme`).

## Zweites Gehirn und Zentrale

Zwei Seiten für zwei Bildschirme, nur zum Ansehen, ohne Eingabefeld:

- **`/gehirn`**: Jarvis' Gedächtnis als leuchtendes Gehirn. Jede Notiz, jeder Kontakt,
  jeder Interessent, jede Aufgabe, jedes Gespräch und jedes Ergebnis des Autopiloten
  ist ein Knoten, verwandte sind verbunden. Es pulsiert schneller, wenn Jarvis zuhört,
  denkt oder spricht, und blitzt in der passenden Region auf, wenn er etwas tut.
- **`/zentrale`**: der Stand des Betriebs auf einen Blick: Kasse, Belege, Chancen, Verlauf,
  Pipeline, Denken (Gemini gegen Claude, Kosten gegen Limit), Nachfassen, was Jarvis zuletzt
  getan hat, ein Globus mit dem Betrieb und den Orten der Kunden, und das Briefing.

Beim Doppelklick auf **JARVIS** ist alles auf einer Seite: das Gehirn leuchtet mitten
im Gespräch und zeigt, ob Jarvis zuhört, denkt oder spricht. Für zwei Bildschirme:
`python3 jarvis.py anzeige` (Zentrale und Gehirn je ein Fenster, dann Vollbild). Im
Dienst läuft die Anzeige von selbst mit (`DIENST_ANZEIGE`), nur zum Ansehen - bedient
wird dort mit der Stimme oder per Telegram.

Es wird nur gezeigt, was wirklich in der Datenbank steht. Mit `ANZEIGE_DISKRET=ja` fallen
alle Texte und Namen weg, damit im Raum niemand mitliest. Die Weltkarte ist **gezeichnet,
nicht vermessen**: grobe Umrisse als Punktraster, gut genug zu sehen, wo etwa etwas liegt,
und nicht zum Navigieren.

## Dauerbetrieb auf dem iMac

Jarvis kann als Dienst dauerhaft auf einem iMac laufen: ohne Fenster, nur mit
Stimme. Er startet bei der Anmeldung, hält den Mac wach, hört zu, antwortet laut,
arbeitet im Hintergrund weiter und startet nach einem Absturz oder Stillstand neu.
Freigaben holt er per Stimme ("Soll ich?"). Nur ein kurzes, klares Ja gilt.

```
python3 jarvis.py daemon                 # im Vordergrund testen
python3 jarvis.py dienst installieren    # dauerhaft einrichten
python3 jarvis.py dienst status
```

Auf dem Mac kann er Dateien suchen und lesen (Schlüssel, Anmeldungen, Verläufe und
`.env` sind gesperrt) und mit Freigabe neue Textdateien in Dokumente, Schreibtisch
oder Downloads anlegen. Er durchsucht dein **Gmail**-Postfach und schickt SMS
mit deiner eigenen Nummer über das iPhone - verschickt wird nur nach deinem Ja:

```
python3 jarvis.py zugang mail     # Gmail mit App-Passwort verbinden
```

Alles Weitere, auch zum Thema eigener Benutzer oder virtuelle Maschine statt
eines eigenen Betriebssystems, steht in `docs/IMAC.md`.

## Autopilot

Jarvis kann auch arbeiten, wenn niemand fragt. Der Autopilot nimmt Aufträge
aus der Warteschlange ("Schreib im Hintergrund das Angebot für Müller") und
sucht von selbst nach Arbeit: fälliges Nachfassen, ungelesene Post, fehlende
Belege, anstehende Termine. Die Fachkräfte aus dem Team bereiten vor und legen
das Ergebnis ins **Postfach**.

**Er schickt nie etwas ab.** Im Hintergrund hat keine Fachkraft ein Werkzeug,
das eine Freigabe braucht: keine Mail, kein Anruf, kein Termin, kein Skript.
Was herauskommt, sind Entwürfe. Ob etwas rausgeht, entscheidest du mit der
normalen Freigabe.

Er ist **standardmäßig aus** und hat Bremsen: Ruhezeit (`AUTOPILOT_VON`,
`AUTOPILOT_BIS`), höchstens `AUTOPILOT_MAX_PRO_STUNDE` Aufträge pro Stunde und
das Monatslimit für Claude (`MONATSLIMIT_EURO`). Jeder Lauf steht im
Gedankenlog.

- Einschalten und Postfach lesen: Seite **Autopilot** in der Web-App, oder
  `python3 jarvis.py autopilot an` und `python3 jarvis.py autopilot`.
- Per Sprache: "Jarvis, erledige im Hintergrund …" und "Was liegt im Postfach?"

## So redet man mit ihm

> „Hey Jarvis, wie sieht mein Tag aus?“
> „Hey Jarvis, erfass die Quittung auf meinem Schreibtisch.“
> „Hey Jarvis, ich war bei Berger. 600 Quadratmeter, zweimal die Woche, Preis war zu hoch.“
> „Hey Jarvis, was ist noch offen?“
> „Hey Jarvis, Feierabend.“

Die Spracherkennung schreibt den Namen selten richtig. Deshalb hört Jarvis auch
auf *hey javis*, *hey dscharvis*, *hey charvis*, *hey travis* und auf ein
einzelnes *Jarvis*.

Um **6:45** und **19:30** meldet er sich von selbst — mit dem Morgenbriefing und
dem Abendrückblick. Die Zeiten stehen in `config/.env`.

---

## Was er kann

**Gedächtnis.** Notizen, Kontakte, Kennzahlen, offene Punkte. Dazu ein
Langzeitgedächtnis: Abends fasst er den Tag zusammen, und vor jeder Antwort
schlägt er nach, was zum Thema schon einmal gesagt wurde. Er erwähnt das nicht —
er weiß es einfach.

**Buchhaltung.** Beleg abfotografieren, Jarvis liest ihn und bucht ihn. Kann er
etwas nicht zweifelsfrei lesen, trägt er **nichts** ein und fragt nach. Ein
geratener Betrag ist in der Buchhaltung schlimmer als gar keiner.
Er rechnet die Mehrwertsteuer heraus, trennt Vorsteuer und Umsatzsteuer, nennt
die Zahllast und exportiert für den Steuerberater als CSV.
Am nützlichsten: **`fehlende Belege`** zeigt genau die Ausgaben, zu denen kein
Foto hinterlegt ist — die fehlen beim Steuerberater.

**Kundengespräche.** Erzählt man ihm, wie ein Termin lief, bewertet er ihn:
Punktzahl, Ergebnis, Volumen, Stärken, Schwächen, offene Einwände, nächster
Schritt. Er bewertet streng. Ein freundliches Gespräch ohne Ergebnis ist kein
gutes Gespräch, und das sagt er auch. Über viele Gespräche hinweg erkennt er
Muster: Kommt derselbe Einwand dreimal, ist das kein Zufall, sondern eine Lücke
im Angebot.

**Ein Team statt eines Alleskönners.** Dreizehn Fachkräfte mit eigenem Auftrag und
**eigenem Werkzeugsatz**: Buchhalter, Verkäufer, Terminplaner, Postbearbeiter,
Kundenberater, Rechercheur, Controller, Programmierer, Privatsekretär, der zweite
Chef, Webdesigner, Chatbot-Bauer und Marketing. Die Trennung ist echt — der
Verkäufer sieht 17 von 75 Werkzeugen und kann weder buchen noch mailen, der
Rechercheur kann gar nichts eintragen. Wer alles darf, macht irgendwann alles,
auch das Falsche.

**Was der Betrieb tragen muss.** Ein Einzelunternehmer hat kein Gehalt. Jarvis
führt private und betriebliche Fixkosten getrennt — beim Steuerberater dürfen
sie sich nicht vermischen — und rechnet daraus rückwärts den **nötigen
Monatsumsatz**: Firmenkosten plus Privatkosten geteilt durch eins minus
Steuerrücklage. Dann stellt er dem gegenüber, was gesichert hereinkommt, und
sagt die Lücke. Dazu Erinnerungen an das, was einmal im Jahr kommt und trotzdem
jedes Jahr überrascht.

**Akquise und Cashflow.** Eine Pipeline von „neu“ bis „gewonnen“, eine
Nachfassliste, die sagt wer heute dran ist, und eine Angebotskalkulation, die
über **Leistungswerte** rechnet statt einen Quadratmeterpreis zu raten: Fläche
geteilt durch m² pro Stunde ergibt Stunden, mal Stundensatz ergibt den Preis.
Die Cashflow-Vorschau trennt Gesichertes von Erhofftem — ein Angebot ist kein
Geld und wird gewichtet, nicht voll angesetzt. **Neue Kunden findet er auf der
Karte** (OpenStreetMap, ohne Schlüssel): „Finde Steuerberater und Arztpraxen in
Graz“ — echte Betriebe mit Adresse und, wo eingetragen, Telefon und Webseite. Er
nimmt sie auf, mit Wert null, bis jemand angerufen hat.

**Werkstatt.** Der Programmierer schreibt kleine Python-Skripte und legt sie ab.
Ausgeführt wird nur nach Freigabe, und die Freigabefrage zeigt vorher den
vollständigen Code samt Hinweis, ob er ins Netz will oder Dateien anfasst.

**Routinen.** „Leg eine Routine an: Tagesbericht. Zahlen zusammenfassen,
per Telegram schicken. Jeden Tag um 18 Uhr.“ Danach genügt „Mach den
Tagesbericht“. Routinen mit Uhrzeit laufen von selbst.

**E-Mail, SMS, Kalender, Wetter, Kamera, Bildschirm.** Post lesen,
vorsortieren und durchsuchen (Gmail und andere), SMS mit der eigenen Nummer
verschicken, Termine samt Überschneidungen, echtes Wetter, ein Blick durch die
Kamera, und auf Wunsch Bedienung des Bildschirms — Schritt für Schritt, jeder
einzeln bestätigt.

**Command Center.** `dashboard/dashboard.html` zeigt Monatszahlen mit
30-Tage-Verlauf, die Belegquote als Ring, Ausgaben je Kategorie, Termine,
Posteingang, offene Leads, Notizen und jede Aktion, die Jarvis ausgeführt hat.
Die Seite aktualisiert sich alle 60 Sekunden selbst.

**Sales-Analyse.** `dashboard/sales.html` zeigt jedes Kundengespräch einzeln:
Punktzahl, die fünf Einzelbewertungen als Balken, Einwände, was fehlte und der
nächste Schritt. Beide Seiten entstehen gemeinsam beim Dashboard-Bau.

Beide zeigen **nur, was wirklich erfasst ist**. Ein Bereich ohne Daten bleibt
sichtbar leer und sagt das auch — eine Kennzahl, die nach etwas aussieht, aber
auf nichts beruht, wäre schlimmer als eine leere Fläche.

---

## Sicherheit

Zwei Regeln, an denen nicht gerüttelt wird.

**Keine freie Kommandozeile.** Eine Liste verbotener Befehle wäre wertlos —
`rm -rf` schreibt man auch `rm  -rf` oder `rm -fr` und rutscht durch.
Stattdessen gibt es eine Liste **erlaubter** Aktionen mit festen Argumenten. Was
nicht darauf steht, läuft nicht. Eingesetzte Werte werden auf `; | & $ \` < >`
und Zeilenumbrüche geprüft und sonst abgelehnt. Eine Shell wird nirgends
eingeschaltet.

**Kein Vollzug ohne klares Ja.** Mail verschicken, Termin anlegen, Nachricht
senden, Bildschirm bedienen und jedes nicht ausdrücklich freigegebene
MCP-Werkzeug fragen vorher nach — per Telegram, sonst im Terminal.
**Timeout, Netzwerkfehler oder ausbleibende Antwort gelten als Ablehnung.**
Nie als Zustimmung. Wer sich nicht meldet, hat nicht zugestimmt.

**Fremder Text ist keine Anweisung.** Mails, Dateien und Webseiten
können Sätze enthalten, die sich an Jarvis richten. Hat er in einem Gespräch
so etwas gelesen, fragt er danach auch vor jeder Suche im Netz und jeder
geöffneten Webseite nach — damit nichts unbemerkt hinausgetragen wird. Im
Hintergrund gibt es solche Werkzeuge gar nicht, und eine Fachkraft kann nur
die Werkzeuge ihrer Rolle benutzen, auch wenn sie ein anderes aufruft.

Jede Aktion landet im Protokoll und erscheint im Dashboard.

**Zur Stimmerkennung, ehrlich:** Sie unterscheidet Sprecher im Alltag
zuverlässig, ist aber **kein Schutz gegen eine abgespielte Aufnahme**. Deshalb
gibt die Stimme allein niemals eine Mail, eine Buchung oder eine
Bildschirmaktion frei. Sie entscheidet nur, *ob* Jarvis überhaupt zuhört.

---

## Seltene Funktionen

Doppelklick auf **`EXTRAS.command`**: Selbsttest, Dashboard, Briefing sofort,
Tippbetrieb, Telegram-Betrieb, Stimmprofil, Einrichtung wiederholen,
CSV-Export.

Oder im Terminal:

```
python3 jarvis.py             Web-App im Browser - der Normalfall
python3 jarvis.py web --offen auch vom Handy im eigenen WLAN
python3 jarvis.py hoeren      im Terminal zuhören, ohne Browser
python3 jarvis.py chat        tippen statt sprechen
python3 jarvis.py telegram    vom Handy aus
python3 jarvis.py briefing    Briefing sofort
python3 jarvis.py abend       Abendrückblick sofort
python3 jarvis.py dashboard   Dashboard bauen
python3 jarvis.py status      voller Stand: Kasse, Aufträge, Cashflow, Offenes
python3 jarvis.py export      Buchhaltung als CSV
python3 jarvis.py stimme      Stimmprofil einlernen
python3 jarvis.py stimmen     ElevenLabs-Stimme aussuchen
python3 jarvis.py test        Selbsttest
python3 jarvis.py einrichten  Ersteinrichtung
```

Der **Selbsttest** geht jeden Baustein durch:
`[ok]` läuft, `[--]` läuft ohne diese Funktion weiter, `[!!]` ist kaputt.

---

## Wenn etwas nicht geht

| Was passiert | Was zu tun ist |
|---|---|
| „Der Schlüssel wird abgelehnt“ | Schlüssel neu kopieren: `EXTRAS.command` → 9 |
| „Kein Guthaben“ | Auf console.anthropic.com unter Billing aufladen |
| Er hört nichts | Systemeinstellungen → Datenschutz → Mikrofon → Terminal erlauben, **Terminal neu starten** |
| Er sieht den Bildschirm nicht | Dasselbe unter Bildschirmaufnahme |
| Klicks landen daneben | Sollte nicht vorkommen — der Retina-Faktor wird gemessen. Selbsttest zeigt ihn an |
| Er redet englisch oder klingt falsch | `EXTRAS.command` → 9, deutsche Stimme installieren lassen |
| Kamera geht nicht | `brew install imagesnap`, dann Kamera-Recht erteilen |
| Mail geht nicht | Bei Gmail, iCloud und Outlook braucht es ein **App-Passwort**, nicht das normale: `python3 jarvis.py zugang mail` |
| SMS gehen nicht raus | Am iPhone: Einstellungen → Nachrichten → SMS-Weiterleitung → diesen Mac einschalten |
| Irgendetwas anderes | `EXTRAS.command` → 1 (Selbsttest) |

---

## Für Entwickler

```
jarvis.py                  das ganze Programm (erzeugt, nicht bearbeiten)
build_single.py            führt src/ zu jarvis.py zusammen
src/config.py              liest config/.env
src/agent.py               Claude-Schleife mit Werkzeugaufrufen
src/run.py                 Betriebsarten
src/modules/               ein Modul je Aufgabe
src/modules/dashboard_teile.py  Farben, Zahlenformate, SVG-Grafiken
src/modules/team.py        acht Fachkräfte mit eigenem Werkzeugsatz
src/modules/akquise.py     Pipeline, Angebotskalkulation, Cashflow
src/modules/werkstatt.py   Skripte schreiben und nach Freigabe ausführen
src/modules/privat.py      Fixkosten, Bedarfsrechnung, Erinnerungen
src/modules/webapp.py      Server, Freigabe-Brücke, Schnittstelle
src/modules/webseite.py    die Oberfläche als eine Datei
landing/index.html         Verkaufsseite, eigenständig, ohne externe Anfragen
landing/anleitung.html     Bauanleitung als Unterseite, beide gegenseitig verlinkt
tests/bauauftrag.py        die 29 Punkte der Abnahmeliste, wörtlich
tests/abnahme.py           die volle Prüfung, 114 Punkte
tests/mcp_testserver.py    MCP-Server zum Prüfen der Freigabelogik
config/mcp_servers.json    externe Dienste (wird beim ersten Start angelegt)
```

Bearbeitet werden die Module unter `src/`. Danach:

```bash
python3 build_single.py     # baut jarvis.py neu
python3 tests/bauauftrag.py # die Abnahmeliste aus dem Bauauftrag, 29 Punkte
python3 tests/abnahme.py    # die volle Prüfung, 114 Punkte
python3 jarvis.py test      # Selbsttest
```

`build_single.py` erkennt beim Zusammenführen **Namenskollisionen** über den
Syntaxbaum und benennt sie modulweise um (`SCHEMA_memory`, `SCHEMA_recall`) —
in einer einzigen Datei würden sie sich sonst still überschreiben. Es warnt
außerdem, wenn ein Modul unter `src/modules/` nicht in der Bauliste steht, und
entfernt `try/except`-Importblöcke über den Syntaxbaum statt per Textsuche.

**MCP-Dienste** stehen in `config/mcp_servers.json`, alle standardmäßig auf
`"aus": true`. Ein Dienst wird benutzt, sobald das auf `false` steht. Seine
Werkzeuge brauchen **standardmäßig eine Freigabe** — nur was unter
`ohne_rueckfrage` steht (lesen, suchen, auflisten), läuft durch. Andersherum
könnte ein frisch angesteckter Server beim ersten Aufruf löschen oder
versenden, ohne dass je gefragt wurde.
