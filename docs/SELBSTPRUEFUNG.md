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
- **Prüfung durch Dritte.** Die Sicherheitsmaßnahmen sind von mir entworfen und getestet. Ein unabhängiger Prüfer-Agent hat
  den Gehirn- und E-Mail-Teil durchgesehen (Stufe 14) – das ist ein zweiter Blick, aber kein Prüfer von außerhalb.
