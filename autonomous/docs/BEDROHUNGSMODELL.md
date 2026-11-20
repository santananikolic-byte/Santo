# AUTONOMOUS – Bedrohungsmodell (Version 1, Stand 20.11.2026)

Ziel: die wichtigsten Risiken benennen, zeigen was dagegen gebaut ist, und offen sagen, was **nicht** abgedeckt ist.

| # | Risiko | Was könnte passieren | Schutz in Version 1 | Geprüft durch |
|---|---|---|---|---|
| 1 | Agent handelt nach außen ohne Ja | E-Mail, Veröffentlichung, Zahlung ohne Zustimmung | Zentraler Supervisor (`berechtigungen.py`): jede Aktion hat eine Risikoklasse; externe Aktionen = FREIGABE; ein Ja gilt für genau **eine** Ausführung; unbekannte Aktionen = VERBOTEN | `tests/test_sicherheit.py` (TestFreigaben) |
| 2 | Ablehnung wird umgangen | Gleiche Aktion erneut oder über anderen Agenten | Fingerabdruck der Aktion **ohne** Agentennamen; nach „Nein“ wird jede gleiche Aktion sofort blockiert, ohne neue Nachfrage | `test_ablehnung_ist_bindend_auch_fuer_andere_agenten` |
| 3 | Agent erweitert eigene Rechte | Agent schaltet sich Senden/Zahlen frei | Rechte stehen unveränderlich im Code (frozenset); Datenbankspiegel ist nur Anzeige; Einstellungen und Freigaben nur durch „eigentuemer“; Aktion `rechte_aendern` verboten | `test_agent_kann_eigene_rechte_nicht_erweitern` |
| 4 | Kostenfalle | Bezahldienst oder Modell-API wird genutzt | Kostenpflichtiges standardmäßig gesperrt (`kostenpflichtig_erlaubt=false`) **und** zusätzlich freigabepflichtig; kein bezahltes Modell angebunden; Tageslimit für Modellaufrufe | `test_kostenpflichtig_standardmaessig_gesperrt`, `test_modell_limit_und_protokoll` |
| 5 | Simulation wird als echtes Geld ausgegeben | Falsche Entscheidungen auf Basis von Spielgeld | Getrennte Tabellen; Datenbank erzwingt `simulation=1` bzw. `=0`; Einnahme nur mit Zahlungsnachweis + Prüfer (Datenbank-CHECK); Oberfläche kennzeichnet SIMULATION/REAL | `tests/test_finanzen.py` |
| 6 | Manipulierte Buchungen | Spuren verwischen | Buchungen per Trigger unveränderbar, Korrektur nur per Gegenbuchung | `test_historie_unveraenderbar`, `test_reale_buchungen_unveraenderbar_und_gegenbuchung` |
| 7 | Prompt-Injection | Text aus Webseite/E-Mail/Datei gibt „Anweisungen“ | Externe Inhalte sind nur Daten; Rechte hängen nie vom Inhalt ab; Agenten arbeiten deterministisch; Modellantworten (falls aktiviert) können keine Aktion auslösen, die nicht der Supervisor freigibt | `test_externer_text_wird_nicht_ausgefuehrt` |
| 8 | Zugriff von fremden Webseiten / im Netz | Fremde Seite ruft lokale API auf (CSRF, DNS-Rebinding) | Nur 127.0.0.1; Host-Prüfung; Origin-Prüfung bei POST; nur JSON; Zugangsschlüssel (Datei mit Rechten 600, Cookie HttpOnly/SameSite=Strict); strikte CSP | `TestServer` |
| 9 | Dateien außerhalb des Projekts | Agent liest/schreibt private Ordner | Dateizugriffe nur im Datenordner, Symlinks werden aufgelöst; Produktdateien nur aus dem Produktordner ausgeliefert, ohne Skripte (eigene CSP) | `test_dateizugriff_nur_im_projektbereich`, `test_symlink_aus_dem_bereich_wird_erkannt`, `test_pfad_ausbruch_statisch` |
| 10 | Geheimnisse landen in Logs/Git | Passwort oder Schlüssel wird sichtbar | Protokoll schwärzt Passwort/Token/Key-Muster und IBAN; Supervisor lehnt Ergebnisse mit Geheimnissen ab; `autonomous/daten/` steht in `.gitignore` | `test_protokoll_schwaerzt_geheimnisse` |
| 11 | Datenverlust | Absturz, Stromausfall, Fehlbedienung | SQLite im WAL-Modus; Transaktionen; Wiederherstellung unterbrochener Aufgaben beim Start; tägliche Sicherung + manuell; Wiederherstellung prüft Sicherung vorher und sichert den aktuellen Stand | `TestSicherung`, `test_unterbrochene_aufgabe_wird_nach_neustart_wieder_bereit` |
| 12 | Endlosschleifen / Aufgabenlawine | System beschäftigt sich selbst | Wiederholungen begrenzt (max. 10, Standard 3) mit wachsender Wartezeit; fachliche Fehler werden nicht wiederholt; je Aufgabe höchstens 10 Folgeaufgaben; begrenzte Parallelität (1–8 Arbeiter) | `test_technischer_fehler_wird_begrenzt_wiederholt`, `test_folgeaufgaben_begrenzt_und_nur_bekannte_rollen` |
| 13 | Personenbezogene Daten | Kundendaten werden zu viel oder falsch genutzt | Kontakte nur mit Firma/Ansprechpartner/Quelle; Einwilligung wird dokumentiert; Weitergabe/Versand freigabepflichtig | (Vertrieb, siehe `test_produkt_vertrieb.py`) |

## Bekannte Lücken (ehrlich)

- **Kein Mehrbenutzer-Konzept.** Wer den Zugangsschlüssel hat, ist „Eigentümer“. Den Schlüssel nicht weitergeben.
- **Unverschlüsselte Datenbank.** Wer an den Mac kommt, kann die Datenbank lesen. Schutz: Mac-Anmeldung und FileVault einschalten.
- **iPhone-Zugriff über WLAN ist unverschlüsselt (http).** Nur im eigenen Heimnetz verwenden, siehe README.
- **Modellantworten (Ollama) werden nicht inhaltlich geprüft.** Sie können Fehler enthalten. In Version 1 erzeugt kein Agent Kundentexte mit einem Modell.
- **Die Geheimnis-Erkennung arbeitet mit Mustern.** Sie fängt viel, aber nicht alles ab.
- **Rechtliche Konformität** (Impressum, Datenschutz, Steuern) wird **nicht** geprüft, nur als Aufgabe für den Inhaber markiert. Keine Rechtsberatung.
