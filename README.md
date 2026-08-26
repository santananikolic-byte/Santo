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
curl -fsSL https://raw.githubusercontent.com/santananikolic-byte/Santo/claude/jarvis-voice-assistant-70695g/install.sh | bash
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

**Ein Team statt eines Alleskönners.** Acht Fachkräfte mit eigenem Auftrag und
**eigenem Werkzeugsatz**: Buchhalter, Verkäufer, Terminplaner, Postbearbeiter,
Kundenberater, Rechercheur, Controller, Programmierer. Die Trennung ist echt —
der Verkäufer sieht 11 von 50 Werkzeugen und kann weder buchen noch mailen, der
Rechercheur kann gar nichts eintragen. Wer alles darf, macht irgendwann alles,
auch das Falsche.

**Akquise und Cashflow.** Eine Pipeline von „neu“ bis „gewonnen“, eine
Nachfassliste, die sagt wer heute dran ist, und eine Angebotskalkulation, die
über **Leistungswerte** rechnet statt einen Quadratmeterpreis zu raten: Fläche
geteilt durch m² pro Stunde ergibt Stunden, mal Stundensatz ergibt den Preis.
Die Cashflow-Vorschau trennt Gesichertes von Erhofftem — ein Angebot ist kein
Geld und wird gewichtet, nicht voll angesetzt.

**Werkstatt.** Der Programmierer schreibt kleine Python-Skripte und legt sie ab.
Ausgeführt wird nur nach Freigabe, und die Freigabefrage zeigt vorher den
vollständigen Code samt Hinweis, ob er ins Netz will oder Dateien anfasst.

**Routinen.** „Leg eine Routine an: Tagesbericht. Zahlen zusammenfassen,
per Telegram schicken. Jeden Tag um 18 Uhr.“ Danach genügt „Mach den
Tagesbericht“. Routinen mit Uhrzeit laufen von selbst.

**E-Mail, Kalender, Wetter, Kamera, Bildschirm.** Post lesen und vorsortieren,
Termine samt Überschneidungen, echtes Wetter, ein Blick durch die Kamera, und
auf Wunsch Bedienung des Bildschirms — Schritt für Schritt, jeder einzeln
bestätigt.

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
python3 jarvis.py             Dauerbetrieb: hört zu und meldet sich von selbst
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
| Mail geht nicht | Bei Gmail, iCloud und Outlook braucht es ein **App-Passwort**, nicht das normale |
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
landing/index.html         Verkaufsseite, eigenständig, ohne externe Anfragen
landing/anleitung.html     Bauanleitung als Unterseite, beide gegenseitig verlinkt
tests/abnahme.py           führt die Abnahmeliste wirklich aus
tests/mcp_testserver.py    MCP-Server zum Prüfen der Freigabelogik
config/mcp_servers.json    externe Dienste (wird beim ersten Start angelegt)
```

Bearbeitet werden die Module unter `src/`. Danach:

```bash
python3 build_single.py     # baut jarvis.py neu
python3 tests/abnahme.py    # führt die Abnahmeliste aus
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
