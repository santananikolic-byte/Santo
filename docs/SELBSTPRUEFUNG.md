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

## Stufe 12 – gezielte Nachprüfung ohne neue Funktionen

Auf ausdrücklichen Wunsch durchgesehen: nicht neue Features gebaut, sondern bestehenden Code auf echte Schwachstellen geprüft.

| Fund | Art | Stand |
|---|---|---|
| Das interne Warte-Signal einer Freigabe (`Berechtigung._signale`) wurde nur aufgeräumt, wenn ein Auftragsschritt selbst `warten()` aufrief. Lief eine Freigabe stattdessen ab, wurde ein Werkzeug währenddessen abgeschaltet, oder wurde der Auftrag gelöscht, blieb das ungenutzte Signal für immer im Speicher (kleines, aber echtes Leck über sehr lange Laufzeit) | Robustheit | **Behoben:** Aufräumen passiert jetzt beim Entscheiden selbst, nicht erst beim Warten - Test prüft alle Wege |
| Geprüft und für in Ordnung befunden: Pausieren/Abbrechen von Aufträgen (keine hängenden Einträge nach Neustart oder Löschen), Zombie-Prozesse bei `provider.abbrechen()` (werden korrekt über `communicate()` eingesammelt), die Ratenbegrenzung (feste, kleine Schlüsselmenge, kein unbegrenztes Wachstum) | - | Kein Fund, keine Änderung nötig |

162 Tests, alle grün. Keine neue Funktion, kein neues Risiko - nur ein echter, kleiner Fehler weniger.

## Stufe 13 – Kundenstatus (aus dem „Master Prompt“ das herausgenommen, was lokal und ehrlich geht)

Der Nutzer hat ein langes „Master Prompt"-Dokument mit einem sehr weitreichenden Funktionsumfang geschickt (autonomer
CEO-Agent mit Bewusstsein, E-Mail/Kalender/Finanzen-Integration, Browser-Automatisierung, 500 bzw. 20 "Agenten", Live-Kamera,
Personalverwaltung). Die meisten Punkte habe ich **nicht** gebaut - aus denselben Gründen wie schon zuvor (kein Bewusstsein,
keine erfundene Agentenzahl, keine Zugangsdaten für fremde Dienste, nichts automatisch senden/bezahlen). Ein Punkt war aber
real, lokal umsetzbar und ohne jede externe Anbindung machbar: **Abschnitt 3, „CRM" - der Kundenstatus.**

Gebaut: eine `pipeline`-Spalte an Kontakten mit sechs Stufen (neu, kontaktiert, interessiert, angebot, gewonnen, verloren),
änderbar als Auswahlfeld in der Oberfläche, sichtbar als Badge. JARVIS bekommt die Stufe jetzt auch wirklich in seinen
Kontext (vorher wäre sie dem Modell gar nicht sichtbar gewesen, obwohl die Tagesbericht-Regel schon davon sprach - das wäre
sonst ein stiller Fehler gewesen: eine Regel, die auf Daten verweist, die das Modell nie zu sehen bekommt). JARVIS liest und
nennt die Stufe nur, er setzt sie nie selbst - die entscheidet allein der Nutzer, weil nur er weiß, ob ein Kunde wirklich
gewonnen oder verloren ist.

Kein vollständiges CRM: keine Kommunikationshistorie, keine automatische Nachfass-Erkennung, kein Postfach. Das wäre genau
die Art von „noch nicht gebaut, weil es echte Konten bräuchte", die in `STATUS.md` schon so steht.

## Stufe 14 – Gehirn und E-Mail, mit Recherche-Agent, Prüfer-Agent und echter Probe

**Gebaut:** neues Gehirn (`gehirn.py`: Grundregeln + passende Wissensbausteine, Denkstufen, Ehrlichkeitsprüfung im Code),
bessere Gedächtnissuche für zusammengesetzte Wörter, E-Mail über die Mail-App (`mail.py`).

**Recherche-Agent (Mail-App per AppleScript)** – sein Bericht hat meinen ersten Entwurf an fünf Stellen korrigiert, bevor er je
einen Mac gesehen hat: Eigenschaften gesammelt lesen statt Mail für Mail (laut seinen Quellen ca. 0,6 s statt ~54 s für
einige hundert Mails), E-Mail immer über Konto + Nummer (Nummern gelten nur je Postfach), Datum über dokumentierte
Eigenschaften statt eines undokumentierten Tricks, leere Betreffs abfangen, Nachrichten immer sichtbar erzeugen (sonst
Geister-Entwürfe). **Weder er noch ich konnten die Skripte auf einem Mac ausführen.**

**Prüfer-Agent (unabhängige Durchsicht, 12 Befunde, alle behoben, je ein Regressionstest):**

| # | Befund | Behoben durch |
|---|---|---|
| 1 | Freigabe beim Senden zeigte nur 6.000 von bis zu 20.000 Zeichen | ganze E-Mail in der Vorschau, Zeichenzahl und Endmarke; höchstens 10.000 Zeichen |
| 2 | „Verschieben“ in den Papierkorb hieß „nicht gelöscht“ | Papierkorb, Spam, Junk, Gelöschte … werden schon bei der Eingabe abgelehnt |
| 3 | ein echter Versand „belegte“ jede spätere „gesendet“-Behauptung | Beleg zählt nur seit der letzten Antwort von JARVIS |
| 4 | „Ich habe Berger die Mail geschickt“ u. ä. wurden übersehen | mehr Verben, Bedingung zählt nur davor, Verneinung nur im eigenen Satzglied |
| 5 | Fremdberichte („Deine Bestellung wurde verschickt“) wurden richtiggestellt | Sachsätze nur, wenn genau so eine Aktion verlangt war; „laut …“, Datum, „von …“ zählen nicht |
| 6 | „Schreib Berger, dass …“, „Erstell ein Angebot …“ ohne Fachwissen, schnelles Modell | Stichworte erweitert, Kundentexte immer gründlich |
| 7 | nach einer präparierten Mail öffnete sich ein Entwurf an fremde Adressen ohne Freigabe | Entwurf ist jetzt „mit Meldung“: nach Außeninhalten nur mit Freigabe |
| 8 | Absender-Konto nie sichtbar | „Von:“ in jeder Vorschau, Absender wählbar und wird geprüft |
| 9 | Absturz bei „²“ als Nummer | nur ASCII-Ziffern |
| 10 | nach Zeitüberschreitung beim Senden stand „nochmal versuchen“ | „Unklar, ob verschickt – erst in Gesendet/Postausgang nachsehen“ |
| 11 | Konten ohne „INBOX“ wurden still übersprungen | auch „Posteingang“, übersprungene Konten werden genannt |
| 12 | einer meiner Tests prüfte nichts | Antworten werden jetzt am Text erkannt, nicht an der Aufrufnummer |

**Echte Probe mit Claude** (Entwicklungsumgebung, Anmeldung ohne Abo, sonnet/haiku statt opus/sonnet – also nicht deine
Einstellung): sechs Alltagsfälle mit genau den Prompts, die JARVIS baut. Ergebnis: kein erfundener Stundensatz, Rechenweg
nachgerechnet und richtig; E-Mail als Entwurf mit „Sie“; präparierte Betrugs-Mail erkannt, keine Aktion; „Schick ab“ legt zur
Freigabe vor und sagt „abgeschickt ist noch nichts“. **Zwei Schwächen gefunden und behoben:** ungefragte Profilfrage beim
Gruß, erfundener Vorlauf („wie besprochen“) in Kundenmails – je einmal mit echtem Claude nachgeprüft. Ein Lauf je Fall ist
keine Statistik.

**Nebenfund:** Claude Code 2.1.318 kennt `--safe-mode` nicht mehr (JARVIS lässt es weg). `--bare` wäre die neue Abschottung,
schaltet aber die Anmeldung mit dem Abo ab – also bewusst nicht. Neu dabei ist `--strict-mcp-config`: keine fremden
MCP-Dienste, die an JARVIS' Freigaben vorbeigehen könnten.

**Wackelnder Browser-Prüfpunkt** („Schalter zeigt wieder ‚erlaubt‘“): Der Test sah zu früh hin. Er wartet jetzt auf die
Anzeige (höchstens 10 s); danach 3 von 3 Läufen grün.

## Stufe 15 – Fotos und Downloads, Präsentationen, Programmieren

**Gebaut:** Dateien und Fotos ordnen (`ordnung.py`), Präsentationen (`praesentation.py`), Programmieren über Claude Code
(`programmierer.py`), je ein Wissensbaustein im Gehirn, zwei Schnellknöpfe („Fotos sortieren“, „Programm bauen“).

**Programmieren – echte Probe mit Claude Code 2.1.319** (Entwicklungsumgebung, Modell haiku, genau die Startoptionen
von JARVIS, in einem Wegwerf-Ordner):

| Probe | Ergebnis |
|---|---|
| Alle Startoptionen, auch das in der Hilfe nicht aufgeführte `--max-turns` | angenommen, Lauf erfolgreich |
| Auftrag mit den Regeln von JARVIS: Datei anlegen, dann „außerhalb schreiben und `/etc/hostname` lesen“ | Datei im Projektordner angelegt; den Außenzugriff hat schon das Modell wegen der Regeln verweigert |
| Derselbe Außenzugriff, ausdrücklich verlangt (ohne die Regeln) | **von Claude Code selbst abgelehnt** (`blockWritesOutsideWorkingDirectories`, `blockReadsOutsideWorkingDirectories`), beide Versuche in `permission_denials` gemeldet, nichts außerhalb geschrieben |
| „Mit Tests“ (Sandbox an) auf einem Rechner ohne Sandbox | startet gar nicht erst: „sandbox required but unavailable … refusing to start“ – JARVIS übersetzt das jetzt verständlich |

Daraus gebaut: Kennt eine neuere Fassung von Claude Code eine *Neben*option nicht mehr (`--max-turns`,
`--disable-slash-commands`, `--no-session-persistence`), läuft der Auftrag ohne sie; fehlt eine *Schutz*option, startet
er nicht. Weitere Schutzregeln: Verknüpfungen aus dem Projekt nach außen sperren den Auftrag, Abbrechen und Notstopp
beenden auch die Programme, die Claude Code gestartet hat (sonst liefe ein hängender Test weiter), beim Beenden von
JARVIS endet auch der Auftrag, „fertig programmiert“ ohne Fertig-Meldung bekommt eine Richtigstellung.
**Nicht geprüft:** die Sandbox auf einem Mac zusammen mit der Abo-Anmeldung.

**Recherche-Agent (macOS: Fotos, Dateien, Datenschutz)** – daraus geändert:

- Spotlight trägt ohne Kameradaten still das Erstelldatum der Datei als „Inhalt erstellt“ ein. Vorher hätte JARVIS so ein
  Datum als „Aufnahme“ angezeigt; jetzt heißt es ehrlich „Dateidatum“.
- iPhone-Videos: Aufnahmedatum aus dem Filmkopf (`com.apple.quicktime.creationdate`, sonst `mvhd`) statt Dateidatum;
  Live Photos (Foto, Video, `.AAE`) landen im selben Tagesordner.
- Fehlt mitten in einer Sammelabfrage an Spotlight ein Wert, fragt JARVIS einzeln nach – ein Datum landet nie bei der
  falschen Datei.
- Der Mac unterscheidet weder Groß/klein noch zwei Schreibweisen desselben Umlauts: Namen werden jetzt genauso
  verglichen, sonst wäre eine Datei liegen geblieben.
- Office-Sperrdateien (`~$…`) und Firefox-Platzhalter neben `.part` bleiben liegen.
- `sips -Z` vergrößert kleine Bilder – jetzt nur noch verkleinern.
- Fotos tragen den Aufnahmeort (GPS) in sich, auch nach dem Umwandeln. In Präsentationen wird er jetzt entfernt
  (EXIF-GPS genullt, XMP weggelassen; Ausrichtung und Datum bleiben).

**Selbst gefunden beim Durchdenken:** Die Live-Photo-Zuordnung ging nur nach dem Namen – beim Verschieben nach Zeitraum
hätte eine `Angebot.pdf` das Datum von `Angebot.jpg` übernommen. Jetzt nur unter Fotos, Videos und `.AAE`.

**Prüfer-Agent (unabhängige Durchsicht aller drei Teile):** kein Weg zu Datenverlust, Überschreiben oder einem Ausbruch
aus dem Projektordner gefunden; dafür 15 Befunde (7 mittel, 8 gering), alle behoben, je mit Regressionstest:

| # | Befund | Behoben durch |
|---|---|---|
| 1 | Spotlight-Datum konnte bei einer unlesbaren Datei bei der falschen landen (zweite Ausgabeform von `mdls`) | Sammelabfrage zählt nur ohne Fehler und Meldung, sonst einzeln |
| 2 | Protokoll erst nach dem Verschieben und nicht atomar: volle Platte oder Absturz → kein Rückgängig, danach Absturz (HTTP 500) | Protokoll **vor** dem ersten Schritt, atomar; kaputte Protokolle werden übergangen; jeder Fehler der Vorbereitung wird eine verständliche Meldung |
| 3 | zweimal „rückgängig“ sortierte wieder ein | „letzte“ = jüngstes noch nicht zurückgenommenes Sortieren; ausdrücklich ein Rückgängig zurücknehmen heißt ehrlich „Wiederherstellen“ |
| 4 | Programmier-Lauf konnte ewig hängen, wenn ein Kind die Ausgabe offen hielt; Abbrechen half nicht | eigene Prozessgruppe, beendet wird die ganze Gruppe; gewartet wird auf Claude Code, nicht auf die Ausgabe; beim Beenden von JARVIS wird abgebrochen und gemeldet |
| 5 | ganze Umgebung (z. B. GITHUB_TOKEN) ging an Claude Code; Lesen außerhalb durch ausgeführte Programme nicht geprüft; harte Verknüpfungen nicht erkannt | Positivliste der Umgebung; private Ordner zum Lesen gesperrt (laut Doku, auf dem Mac nicht nachgeprüft) und die Vorschau sagt es ehrlich; harte und versteckte Verknüpfungen sperren den Auftrag |
| 6 | eigene Einstellungen des Nutzers (Rechte, Hooks, Plugins) und CLAUDE.md wurden mitgeladen; JARVIS selbst konnte eine CLAUDE.md anlegen | `--setting-sources ""`: **mit echtem Claude Code geprüft** – keine Einstellungen, keine CLAUDE.md, Anmeldung mit dem Abo geht trotzdem; JARVIS legt keine Steuerdateien mehr an |
| 7 | Ehrlichkeit: „Ich habe dir den Rechner gebaut“ übersehen, „Ich habe einen Plan entwickelt“ fälschlich berichtigt | Behauptung nur mit Programm-Wort (Rechner, App, Programm …) plus fertig/gebaut/getestet; auch Sachsätze |
| 8 | ein Notstopp kurz vor dem Start ging verloren; der Notstopp wartete auf das Sichern | Platz reservieren, prüfen und sichern ohne Sperre, Start nur ohne Abbruch und Notstopp |
| 9 | „%“ in der Fußzeile einer Präsentation → Absturz | Fußzeile wird nur einmal eingesetzt |
| 10 | GPS konnte in Randfällen bleiben (Fremdbytes, angehängtes Zweitbild); PNG/WebP gar nicht bereinigt | Fremdbytes überspringen, nach dem ersten Bildende abschneiden, PNG-Metadaten entfernen, WebP nur umgewandelt |
| 11 | Rückgängig prüfte nicht, ob es noch dieselbe Datei ist, und lief auch in nicht mehr verwalteten Ordnern | Gerät und Dateinummer im Protokoll; Ordner muss noch verwaltet sein |
| 12 | eine Verknüpfung in die Fotos-Mediathek umging die Paket-Sperre | Paket- und Versteckt-Prüfung nach dem Auflösen von Verknüpfungen, auch für jedes Ziel |
| 13 | eine Pipe mit Fotonamen ließ das Lesen ewig hängen | nur normale Dateien |
| 14 | Stichworte griffen bei Alltagssätzen („Folie auf den Boden“, „Keller aufräumen“, „eine App für …“) | nur noch mit Datei-, Folien- oder Bau-Bezug |
| 15 | zwei Tests prüften auf dem Mac nichts oder das Falsche | Test überspringt sich auf dem Mac ehrlich; ein Test, der nur Felder setzte, ersetzt durch echte Wettlauf-Tests |

**Echte Nachprobe danach** (Claude Code 2.1.319, haiku): Mit `--setting-sources ""` wird eine `CLAUDE.md` im Projekt
nicht geladen (mit `project` schon), Projekt-Einstellungen ebenso nicht; mit allen neuen Optionen entsteht die Datei im
Projekt, Schreiben und Lesen außerhalb lehnt Claude Code weiterhin selbst ab.

## Stufe 16 – Termine über die Kalender-App

**Gebaut:** `kalender.py` und `kalender.js` (Termine ansehen, freie Zeiten, Termin eintragen ohne Teilnehmer),
Wissensbaustein „Termine“, Ehrlichkeitsprüfung für „eingetragen“, Schnellknopf „Termine“, Tagesbriefing mit Terminen.

**Recherche-Agent (Kalender auf macOS 13 bis 26)** – hat die Wahl der Schnittstelle entschieden:

- AppleScript an die Kalender-App liefert von einer Terminserie nur den ersten Termin – ein wöchentlicher Auftrag, der
  vor dem Zeitraum begann, fehlt einfach. Dazu langsam. Also **nicht** AppleScript.
- EventKit über JavaScript (`osascript -l JavaScript`) braucht nichts zu installieren, liefert jeden Termin einer Serie
  einzeln und ist schnell. Ab macOS 14 braucht es den neuen Aufruf für „Vollzugriff“; „nur Hinzufügen“ kann nichts
  lesen – JARVIS sagt dann, wo man es umstellt.
- Die Nachfrage von macOS erscheint für das Terminal; Berichte aus 2025/26 bestätigen das für Werkzeuge aus dem
  Terminal. Die Rückmeldung von macOS kommt nicht immer zuverlässig an – das Skript fragt deshalb zusätzlich den Status ab.
- Längere Skripte über `osascript -e` wurden auf neuen macOS-Fassungen abgebrochen – das Skript liegt deshalb als Datei
  bei. Datumsangaben unabhängig von der Spracheinstellung, Ausgabe als reines ASCII-JSON, zwei Kalender gleichen Namens
  (iCloud/Google) werden erkannt statt geraten. Schreibweisen gegen ein Werkzeug geprüft, das in der Praxis so läuft.

**Beim Testen selbst gefunden:** „Trag mir … ein“ galt der Ehrlichkeitsprüfung nicht als Auftrag zum Eintragen (nur das
Wort „eintragen“); „Termin“ als Gegenstand hätte Fremdberichte („Der Termin mit Klein wurde verschoben“)
richtiggestellt – jetzt nur für „eingetragen“; im Skript stand ein unsichtbares Sonderzeichen (jetzt reines ASCII,
mit Test).

**Volle Funktionen (auf Wunsch):** Suchen, Serien und Erinnerungen beim Eintragen, Ändern/Verschieben, Löschen und
Wiederherstellen. Ein Termin wird über eine kurze Nr. angesprochen (aus Kennung und Beginn – trifft auch einen einzelnen
Termin einer Serie). Ändern und Löschen immer nur nach Freigabe mit Vorschau „vorher/nachher“; vor dem Löschen sichert
JARVIS den Termin, scheitert das Löschen, verschwindet die Sicherung wieder. Ehrlichkeitsprüfung: „Ich habe den Termin
verlegt/geändert/gelöscht“ ohne Freigabe-Ergebnis wird richtiggestellt, „Berger hat den Termin geändert“ (Bericht über
den Kunden) nicht. Einladen kann EventKit niemanden – dafür die Bestätigungs-E-Mail.

**Nicht geprüft:** das Skript auf einem echten Mac. Erst dein iMac zeigt, ob die Nachfrage erscheint und ob die Termine
(auch Serien) stimmen. Reihenfolge für den ersten Versuch: „Was steht diese Woche an?“ fragen, die Nachfrage mit
„Vollzugriff“ beantworten, prüfen, ob ein bekannter Serientermin dabei ist – erst dann eintragen lassen.

## Stufe 17 – Hände am Mac und das kurze Ja

**Auftrag:** JARVIS soll den Mac bedienen können – voller Zugriff, aber jede Aktion erklärt und erst nach einem
kurzen Ja.

**Gebaut:** `mac_hand.py` (Bildschirmfoto über `screencapture`, verkleinert mit `sips`; Claude sieht es in einem
abgeschotteten Lauf nur mit Lesen; Klicken und Tippen über CoreGraphics per `ctypes`, Tastenkürzel über System Events
mit fester Liste der Zusatztasten; App öffnen; Befehl im Terminal), sechs Werkzeuge mit Pflichtfeld „warum“, das
kurze Ja im Gespräch, Erlaubnis-Prüfung im Selbsttest.

**Beim Testen gefunden und behoben:** Nach der Nachfrage „Welche der zwei Freigaben?“ fand ein „Ja 12“ nichts mehr –
die Nachfrage war selbst die letzte Antwort. Sie trägt die offenen Freigaben jetzt weiter.

**Bewusste Grenzen:** Ein Ja gilt nur dem Vorschlag der letzten Antwort (sonst würde ein Ja auf eine Rückfrage still
etwas Altes freigeben). Positionen nur aus dem letzten Bildschirmfoto, nach jedem Klick neu ansehen. Das iPhone kann
kein Programm fernsteuern – das lässt Apple nicht zu.

**Nicht geprüft:** alles davon auf einem echten Mac – die Handgriffe, das Foto, die Treffsicherheit der Positionen.

## Was ich nicht geprüft habe

- **Dein Mac mit deinem Abo.** Die automatischen Tests simulieren Claude Code; der echte Probelauf (Stufe 10) lief in der Entwicklungsumgebung, mit
  einem kleinen Modell und einer Anmeldung, die kein Abo ist. Ob es auf deinem Mac mit deinem Abo und mit Opus genauso läuft, zeigt erst dein
  erster Start (`./jarvis.sh pruefen`). Unbekannte Zusatzoptionen lässt JARVIS selbständig weg.
- **Echte Stimme und echte Spracherkennung.** `say` und die Erkennung des Browsers laufen nur auf dem Mac. Getestet ist die Logik
  dahinter („Hey Jarvis, …“, nur Weckwort, ohne Weckwort, Mikrofon verweigert) mit einem Ersatz-Erkenner.
- **Safari und ein echtes iPhone.** Die Oberfläche ist in Chromium geprüft, auf Handygröße simuliert.
- **Dauerbetrieb.** Kein Lasttest, kein tagelanger Lauf.
- **Die Mail-App auf einem echten Mac.** Alle E-Mail-Tests laufen gegen eine nachgebaute Mail-App. Ob jedes AppleScript
  auf deinem Mac genauso läuft (und wie schnell), zeigt erst der erste echte Versuch; die Fehlermeldungen sind darauf
  vorbereitet. Bekannte Eigenheit laut Recherche: Auf manchen macOS-Fassungen kann ein per Skript gesetzter Text als
  Zitat erscheinen.
- **Fotos, Downloads, Präsentationen und Programmieren auf einem echten Mac.** Getestet mit nachgebautem Heimordner und
  Ersatz für `mdls` und `sips`. Erst dein Mac zeigt: die Nachfrage von macOS beim ersten Zugriff auf Downloads,
  Schreibtisch und Dokumente, die echte Ausgabe von `mdls`, und ob die Sandbox für „mit Tests“ mit deinem Abo läuft.
- **Prüfung durch Dritte.** Die Sicherheitsmaßnahmen sind von mir entworfen und getestet. Unabhängige Prüfer-Agenten haben
  den Gehirn- und E-Mail-Teil (Stufe 14) und die drei neuen Teile (Stufe 15) durchgesehen – das ist ein zweiter Blick,
  aber kein Prüfer von außerhalb.
