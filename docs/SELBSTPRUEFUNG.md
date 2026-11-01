# JARVIS – Selbstprüfung

Nach jeder Stufe habe ich meine eigene Arbeit kritisch durchgesehen, Fehler gesucht, sichere Korrekturen eingebaut und die
Funde hier festgehalten. „Behoben“ heißt: Korrektur im Code **und** ein Test, der sie absichert, wo das sinnvoll ist.

## Stufe 7 – Zugang, Schnittstelle, Server

| Fund | Art | Stand |
|---|---|---|
| Verbindungen, die nichts mehr senden, hielten einen Serverfaden ewig fest (im WLAN-Modus ein Risiko) | Sicherheit | **Behoben:** Zeitlimit 60 Sekunden pro Verbindung (`server.py`) |
| Der Datenordner `~/.jarvis` war für andere Benutzer des Macs lesbar (Rechte 755); nur die Schlüsseldatei war 600 | Sicherheit | **Behoben:** Ordner bekommt Rechte 700 (`konfig.py`, Test in `test_kern.py`) |
| `wissen.py` aus Phase 3 war toter Code (nirgends mehr eingebunden) | Aufräumen | **Behoben:** gelöscht |
| Das Feld `phase` im Status war veraltet und irreführend | Aufräumen | **Behoben:** entfernt, Version auf 0.8.0 |
| Zwei Testannahmen waren falsch (nicht der Server): das Wort „Finanzziele“ steht auch in einer Geschäfts-Entscheidung; „BRAIN.md neu einlesen“ ersetzt Einträge, statt sie zu ergänzen | Test | **Behoben:** Tests prüfen jetzt eindeutige Merkmale („500.000“, „Familienbetrieb“) und die Anzahl |
| `/status` ist ohne Schlüssel abrufbar und nennt Prozessnummer und Python-Version | Hinweis | **Akzeptiert:** nötig, damit `jarvis.sh` den Server erkennt; enthält nichts Persönliches (Test sichert die Feldliste ab) |
| Im WLAN-Modus ist die Verbindung unverschlüsselt (http), das Cookie hat kein `Secure` | Grenze | **Offen, dokumentiert:** nur in vertrauten Netzen nutzen; verschlüsselter Weg (Tailscale) wäre eine spätere Stufe |
| Die Ratenbegrenzung gilt je Art des Aufrufs, nicht je Gerät | Grenze | **Akzeptiert:** für einen Nutzer ausreichend |
| Wiederherstellen aus einer Sicherung ersetzt die Datenbank | Risiko | **Abgesichert:** nur bei gestopptem Server, die Sicherung wird vorher geprüft, der bisherige Stand wird zuerst gesichert |

## Stufe 8 – Oberfläche

Der Browser-Test hat Fehler gefunden, die kein Code-Lesen gezeigt hätte:

| Fund | Art | Stand |
|---|---|---|
| Auf dem Handy war der Leitstand breiter als der Bildschirm (Diagramm sprengte das Raster) | Darstellung | **Behoben:** Raster darf schrumpfen; Test prüft alle fünf Ansichten auf seitliches Scrollen |
| Nach dem Umlegen eines Schalters wurde die Ansicht nicht neu gezeichnet (falscher Anzeigezustand) | Fehler | **Behoben:** nur Texteingaben sperren das Neuzeichnen |
| Eingetippter Text ging verloren, wenn JARVIS noch antwortete oder die Verbindung abbrach | Fehler | **Behoben:** Text bleibt stehen bzw. kommt zurück; Test mit abgebrochener Verbindung |
| Lange Antworten: manche Browser brechen eine Anfrage nach etwa einer Minute ab, der Server arbeitet trotzdem weiter | Risiko | **Abgemildert:** die Oberfläche schaut dann nach, ob JARVIS noch arbeitet, statt einen falschen Fehler zu melden. **Safari nicht geprüft** |
| Der Werkzeugschalter hieß „gesperrt“ und war bei „erlaubt“ aus (verwirrend) | Bedienung | **Behoben:** Schalter an = erlaubt |
| Die Oberfläche zeigte nicht, welche Werkzeuge ein Schritt wirklich ausgeführt hat | Ehrlichkeit | **Behoben:** „Tatsächlich ausgeführte Werkzeuge“ je Schritt |
| Freigaben per Sprache („ja“) sind absichtlich nicht möglich: Fehlerkennung oder das Echo der eigenen Stimme dürften nie etwas freigeben | Entscheidung | Freigaben nur per Klick |

## Stufe 10 – Echter Probelauf mit Claude Code

In der Entwicklungsumgebung gibt es dieselbe Version von Claude Code wie auf deinem Mac (2.1.316). Damit habe ich zum ersten Mal **nicht
simuliert** geprüft (kleines, günstiges Modell, wenige Aufrufe; die Anmeldeart dort ist kein Abo, deshalb lief es an JARVIS' Schutz vorbei
nur in einem Wegwerf-Skript, nie im Produkt):

| Fund | Stand |
|---|---|
| Alle Startoptionen existieren laut echter Hilfe; `--tools ""` schaltet alle Werkzeuge ab, `--safe-mode` schaltet CLAUDE.md, Plugins und Hooks ab | **Bestätigt** |
| Die echte JSON-Ausgabe hat das erwartete Feld `result` und `usage`; der Aufruf kam nach etwa 6 Sekunden zurück | **Bestätigt** |
| Die Token-Zahlen waren falsch: das echte Claude meldet fast die ganze Eingabe unter `cache_*`, `input_tokens` allein war „2“ | **Behoben**, Test mit der echten Form |
| Das echte Modell kennt dein Profil aus `BRAIN.md`, legt Dateien über das Aktionsformat an, setzt Erinnerungen, plant im richtigen JSON | **Bestätigt** |
| E-Mail senden: lehnt ehrlich ab („dafür habe ich kein Werkzeug“) und weist auf den offenen Stundensatz hin, statt einen Preis zuzusagen | **Bestätigt** |
| Es sprach den Nutzer mit „Sie“ an und schrieb gestelzte Sätze („…sehe ich erst, wenn das Werkzeug das bestätigt“) | **Behoben:** Regeln verlangen „du“, kurze Ankündigung statt Erklärung |
| Fehlte noch: aktives Mitdenken wie ein Geschäftsführer-Assistent (Priorität, nächster Schritt, eine Frage mit Begründung, Vorschläge für zwei Entscheider) | **Ergänzt** in den Grundregeln; im zweiten Lauf antwortete das Modell entsprechend |

Das ist ein Probelauf, kein Beweis für alles: andere Modelle (Opus, Sonnet) und deine Anmeldung per Abo sind weiterhin ungetestet.

## Frühere Stufen (4 bis 6)

Gefunden und behoben beim Bauen der Tests: eine Namenskollision im Log (das Feld „stufe“ überschnitt sich mit der Log-Stufe), eine Pause mitten in
einem Schritt (jetzt nur zwischen Schritten), Tests, die dieselbe Datei erneut schrieben und zu Recht eine Freigabe auslösten, veraltete
Regelzähler im Ersatz-Claude.
Prinzipien, die seitdem gelten: eine nicht auswertbare Prüfung gilt als nicht bestanden; eine Freigabe gilt einmal, verfällt und
wird beim Erteilen erneut gegen Notstopp und Sperren geprüft; nach Zugriff auf Webinhalte braucht jede weitere Aktion eine Freigabe;
das Löschen verschiebt in den Papierkorb der Werkstatt.

## Stufe 11 – Rolle Vertrieb/Akquise

| Fund | Art | Stand |
|---|---|---|
| Die neue Regel-Passage nannte das Werkzeug `datei_schreiben` beim Namen. Dadurch stand der Name immer im Systemprompt, auch wenn das Werkzeug für eine Rolle gesperrt oder abgeschaltet war - zwei Tests schlugen genau deshalb an | Sicherheit (Information sickert durch) | **Behoben:** Werkzeugnamen nicht mehr in der allgemeinen Regel-Prosa nennen; die Werkzeugliste selbst wird schon pro Rolle gefiltert |
| Im Browser-Test prüfte ich, ob die gesendete Nachricht das Wort „Akquise" enthält - das stand aber nur im Knopf-Namen, nicht im tatsächlich gesendeten Text | Test | **Behoben:** Test prüft jetzt ein Wort, das wirklich im gesendeten Text steht |
| Mein erster Rollen-Test rief „Datei löschen" auf eine Datei auf, die es gar nicht gab - das schlug schon bei der Eingabeprüfung fehl, bevor die Rollenprüfung überhaupt lief, und verschleierte, was eigentlich getestet werden sollte | Test | **Behoben:** Datei vorher anlegen, damit wirklich die Rollensperre geprüft wird |

Die neue Rolle **Vertrieb/Akquise** darf dieselben Werkzeuge wie die Recherche-Rolle (recherche, Dateien lesen/auflisten/schreiben, merken) und
keine zusätzlichen. Sie bereitet nur Entwürfe und Kontaktvorschläge vor; Senden, Anrufen und Preiszusagen bleiben ausgeschlossen, weil es dafür
keine Werkzeuge gibt - nicht weil es eine Regel verbietet, die sich umgehen ließe. E-Mail-Postfach, Telefon, Kalender und Buchhaltung sind nach
wie vor nicht angebunden (siehe `STATUS.md`).

## Was ich nicht geprüft habe

- **Dein Mac mit deinem Abo.** Die automatischen Tests simulieren Claude Code; der echte Probelauf (Stufe 10) lief in der Entwicklungsumgebung, mit
  einem kleinen Modell und einer Anmeldung, die kein Abo ist. Ob es auf deinem Mac mit deinem Abo und mit Opus genauso läuft, zeigt erst dein
  erster Start (`./jarvis.sh pruefen`). Unbekannte Zusatzoptionen lässt JARVIS selbständig weg.
- **Echte Stimme und echte Spracherkennung.** `say` und die Erkennung des Browsers laufen nur auf dem Mac. Getestet ist die Logik
  dahinter („Hey Jarvis, …“, nur Weckwort, ohne Weckwort, Mikrofon verweigert) mit einem Ersatz-Erkenner.
- **Safari und ein echtes iPhone.** Die Oberfläche ist in Chromium geprüft, auf Handygröße simuliert.
- **Dauerbetrieb.** Kein Lasttest, kein tagelanger Lauf.
- **Prüfung durch Dritte.** Die Sicherheitsmaßnahmen sind von mir entworfen und getestet, nicht von außen geprüft.
