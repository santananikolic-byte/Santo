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

## Frühere Stufen (4 bis 6)

Gefunden und behoben beim Bauen der Tests: eine Namenskollision im Log (das Feld „stufe“ überschnitt sich mit der Log-Stufe), eine Pause mitten in
einem Schritt (jetzt nur zwischen Schritten), Tests, die dieselbe Datei erneut schrieben und zu Recht eine Freigabe auslösten, veraltete
Regelzähler im Ersatz-Claude.
Prinzipien, die seitdem gelten: eine nicht auswertbare Prüfung gilt als nicht bestanden; eine Freigabe gilt einmal, verfällt und
wird beim Erteilen erneut gegen Notstopp und Sperren geprüft; nach Zugriff auf Webinhalte braucht jede weitere Aktion eine Freigabe;
das Löschen verschiebt in den Papierkorb der Werkstatt.

## Was ich nicht geprüft habe

- **Echtes Claude Code auf dem iMac.** Alles Denken ist in den Tests simuliert. Ob die verwendeten Startoptionen auf deiner Version
  (2.1.316) ankommen, zeigt erst der erste echte Start. Unbekannte Zusatzoptionen lässt JARVIS selbständig weg.
- **Echte Stimme und echte Spracherkennung.** `say` und die Erkennung des Browsers laufen nur auf dem Mac. Getestet ist die Logik
  dahinter („Hey Jarvis, …“, nur Weckwort, ohne Weckwort, Mikrofon verweigert) mit einem Ersatz-Erkenner.
- **Safari und ein echtes iPhone.** Die Oberfläche ist in Chromium geprüft, auf Handygröße simuliert.
- **Dauerbetrieb.** Kein Lasttest, kein tagelanger Lauf.
- **Prüfung durch Dritte.** Die Sicherheitsmaßnahmen sind von mir entworfen und getestet, nicht von außen geprüft.
