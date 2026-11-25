# AUTONOMOUS – Bericht je Phase (PDF Abschnitt 14)

Grundlage: „AUTONOMOUS – Master Development Directive v3.0“ (20.11.2026). Stand dieses Berichts: 25.11.2026.

Status-Begriffe (Strict Execution Protocol): **GEPLANT · IMPLEMENTIERT · ERFOLGREICH AUSGEFÜHRT · ERFOLGREICH GETESTET ·
FEHLGESCHLAGEN · NICHT VERIFIZIERT**. „Getestet“ heißt: automatische Tests in der Entwicklungsumgebung (Linux,
Python 3.13). **Auf dem Mac ist nichts verifiziert** – das gilt für jede Zeile unten.

Letzter vollständiger Lauf (25.11.2026, Stand `b90c1eb`/`278d51c`, saubere Kopie): Kompilieren fehlerfrei unter
Python 3.13 und 3.9 · **395 von 395 Unit-Tests bestanden unter Python 3.13, unter Python 3.9 395 mit 1 übersprungenem**
(QR-Gegenprobe, braucht Zusatzpakete) · `ruff` (Fehlerregeln) und `shellcheck` (5 Skripte): keine Befunde ·
**318 von 318 Oberflächen-Prüfungen bestanden unter Python 3.13 und 3.9** · **iPhone-Prüfung 25 von 25** (WebKit,
echte WLAN-Adresse, QR-Code fotografiert und unabhängig gelesen) · **Safari-Engine WebKit 26.6**: alle 9 Bereiche
und die Überlebensplan-Seite ohne Fehler · fehlgeschlagen: keine.

**Echter Gesamtlauf der Einrichtungszeile** (25.11.2026): `curl … | bash` direkt von GitHub, Python 3.9, leerer
Benutzerordner → AUTONOMOUS läuft, Schreibtisch-Symbole da, KI-Einrichtung wählte bei 16 GB gemma3:4b, erstellte
„autonomous“, Probeaufruf „OK“, dann umgestellt (Exit-Code 0). Danach über den laufenden Server: echte Suche
(24 s, 239 Ausschreibungen angezeigt) und Tagesplan mit KI-Kurzfassung (17 s). **ERFOLGREICH AUSGEFÜHRT** – in der
Entwicklungsumgebung (Linux; Ollama war schon installiert). Auf dem Mac: NICHT VERIFIZIERT.

**Echter Gesamtlauf über den laufenden Server** (21.11.2026, echte Internet-Recherche, echtes lokales KI-Modell
Ollama 0.40.17/gemma3:1b): Ausschreibungssuche (3 Quellen ok, 289 gefunden, 59 passend) → Bewerbungsmappe für die
beste Ausschreibung → Marktbericht mit KI-Zusammenfassung (42 Ausschreibungen, 17 Zuschläge, 23 Wettbewerber) →
Geschäftschancen bewerten → Tagesplan: **6 von 6 Aufgaben abgeschlossen, 0 fehlgeschlagen**, KI-Kosten 0 €.
**ERFOLGREICH AUSGEFÜHRT** – in der Entwicklungsumgebung, nicht auf dem Mac.

---

## Phase 1 – Bestandsaufnahme

| Frage (Abschnitt 14) | Antwort |
|---|---|
| Was wurde tatsächlich implementiert? | Umgebung geprüft (Python 3.13, Node 22, kein FastAPI installiert; im Repository liegt JARVIS – **unverändert**). Architektur festgelegt: Python-Standardbibliothek + SQLite, eigenes Paket `autonomous/`. Risiken und Kosten dokumentiert. |
| Welche Tests, mit welchem Ergebnis? | Keine (Analysephase). |
| Was ist noch nicht fertig? | – |
| Probleme oder Risiken? | Backend ohne FastAPI – laut PDF erlaubt („oder eine gleichwertig schlanke Lösung“); gewählt, damit es ohne Installation läuft. |
| Geänderte Dateien | `autonomous/__init__.py`, `konfig.py`, `README.md`, `docs/` |
| Nächster Schritt | Phase 2 |
| Zusätzliche Kosten/Zugänge? | Keine |

## Phase 2 – Funktionsfähiger Kern

| Frage | Antwort |
|---|---|
| Implementiert | Server nur auf 127.0.0.1 mit Zugangsschlüssel, Host-/Herkunftsprüfung, CSP (`server.py`, `api.py`); SQLite mit Migrationen (`db.py`, aktuell Schema 3); Aufgaben mit allen Status aus Abschnitt 9, Verlauf, begrenzten Wiederholungen, Wiederherstellung nach Neustart (`aufgaben.py`); Orchestrator mit begrenzter Parallelität (`orchestrator.py`); echter Systemstatus (`kern.py`); Protokoll mit Schwärzung (`protokoll.py`); Sicherung/Wiederherstellung/Export (`sicherung.py`); Gedächtnis Fakt/Entscheidung/Hypothese/Vorschlag (`gedaechtnis.py`); Start/Stopp per Doppelklick. |
| Tests | `test_kern.py` 26, `test_sicherheit.py` 23, `test_last.py` 2 – **ERFOLGREICH GETESTET**. Start/Stopp-Skripte **ERFOLGREICH AUSGEFÜHRT** (Linux). |
| Nicht fertig | – |
| Probleme/Risiken | Auf dem Mac NICHT VERIFIZIERT (Gatekeeper beim ersten Öffnen, Python-Zertifikate bei python.org-Installationen). |
| Dateien | siehe „Implementiert“, dazu `AUTONOMOUS-starten.command`, `AUTONOMOUS-stoppen.command` |
| Nächster Schritt | Phase 3 |
| Kosten/Zugänge | Keine |

## Phase 3 – Wallet und Finanzen

| Frage | Antwort |
|---|---|
| Implementiert | Internes Wallet mit 15,00 € **SIMULATION**, unveränderbare Historie (Trigger), Gegenbuchungen, Reservierungen, Gebühren, Budgets mit Warnungen (`wallet.py`). Reale Finanzen in eigener Tabelle: Einnahme nur mit Zahlungsnachweis und Prüfer, Forderungen ≠ Einnahmen, nur der Eigentümer bucht (`finanzen.py`). Wallet-Stand 0 stoppt nichts. |
| Tests | `test_finanzen.py` 16 – **ERFOLGREICH GETESTET** (u. a. „Null-Guthaben stoppt keine Kernfunktionen“, „keine Vermischung“). |
| Nicht fertig | – |
| Probleme/Risiken | – |
| Dateien | `wallet.py`, `finanzen.py` |
| Nächster Schritt | Phase 4 |
| Kosten/Zugänge | Keine |

## Phase 4 – Erste Agenten

| Frage | Antwort |
|---|---|
| Implementiert | CEO, Research, Product und Supervisor (dazu Sales, Finance, Learning). Rechte unveränderlich im Code; zentrale Prüfung jeder Aktion mit Risikoklasse AUTO/FREIGABE/VERBOTEN; ein Ja gilt für genau eine Ausführung; ein Nein ist bindend, auch für andere Agenten (`berechtigungen.py`, `agenten/`). |
| Tests | `test_sicherheit.py` (Freigaben, Rechte, Parallelität), `test_kern.py` (Übergabe CEO → andere Rolle) – **ERFOLGREICH GETESTET**. |
| Nachgeliefert (21.11.2026) | **Lokale KI-Schicht** (`autonomous/ki/`, `modell.py`): austauschbar (keiner/Ollama, nur lokal), Ausgabe immer „KI-Entwurf – ungeprüft“, kann keine Aktion auslösen, Tageslimit und Protokoll – ERFOLGREICH GETESTET und mit **echtem Ollama 0.40.17 + Modell gemma3:1b ERFOLGREICH AUSGEFÜHRT** (Status, Probeaufruf, Marktbericht mit KI-Zusammenfassung über den laufenden Server). **Research-Agent untersucht Märkte selbst** (`marktbericht`): Nachfrage, Wettbewerber (Zuschläge), Auftraggeber, Anforderungen aus amtlichen EU-Daten (TED) – ERFOLGREICH AUSGEFÜHRT, z. B. 365 Tage NRW: 473 Ausschreibungen, 269 Zuschläge, 275 Unternehmen mit Zuschlag. |
| Probleme/Risiken | Ein kleines Modell macht inhaltliche Fehler (im echten Lauf beobachtet) – deshalb stehen Zahlen immer gezählt mit Quelle daneben, KI-Text ist nur gekennzeichneter Zusatz. Auf dem Mac NICHT VERIFIZIERT. |
| Dateien | `berechtigungen.py`, `agenten/__init__.py`, `ceo.py`, `research.py`, `product.py`, `sales.py`, `finance.py`, `learning.py`, `modell.py` |
| Nächster Schritt | Phase 5 |
| Kosten/Zugänge | Keine |

## Phase 5 – Erstes Produkt und Vertrieb

| Frage | Antwort |
|---|---|
| Implementiert | Marktanalyse mit Quellen (`docs/MARKTANALYSE.md`, Empfehlung **Google-Profil-Paket**, Preisspanne als **UNSICHER** markiert – Anbieterpreise nicht bestätigt). Erzeugbare Produkte: Google-Profil-Paket (Entwurf, Prüfliste, Übergabe-Anleitung), Kunden-Webseite; Verkaufsseite ohne erfundenen Preis; Kontakte mit Einwilligungsnachweis, Pipeline, Angebote (Entwurf → geprüft → selbst versendet); Versand nur nach Freigabe (Version 1 hat keinen Versandkanal und sagt das). **Rückmeldungen messen** (PDF 2.3): erfassen und auswerten, Verbesserungen nur als Vorschlag. |
| Tests | `test_google_profil.py` 18, `test_produkt_vertrieb.py` 22, `test_rueckmeldungen.py` 15 – **ERFOLGREICH GETESTET**; Rückmeldungen zusätzlich über den echten Server **ERFOLGREICH AUSGEFÜHRT**. |
| Nicht fertig | **Echte Rückmeldungen von Kunden** – geht nur mit euch (Angebot und Preis entscheiden, eigenes Profil als Test, 5–10 Betriebe ansprechen). Bis dahin ist Phase 5 nicht abgeschlossen. |
| Probleme/Risiken | Zahlungsbereitschaft nicht belegt; Impressum/Datenschutz/Steuer nur als offene Punkte (keine Rechtsberatung). |
| Dateien | `produkte/*`, `agenten/product.py`, `agenten/sales.py`, `api_vertrieb.py`, `beispiele/*`, `docs/MARKTANALYSE.md`, `daten_vorlagen/marktbewertung.json` |
| Nächster Schritt | Entscheidung des Eigentümers über erstes Angebot und Preis |
| Kosten/Zugänge | Keine |

## Phase 6 – Erweiterung

| Frage | Antwort |
|---|---|
| Implementiert | Finance-, Sales-, Learning-Agent. **Auftrags-Radar** (vorgezogen, vom Eigentümer akzeptiert): Akquise-Agent liest öffentliche Ausschreibungen (TED, service.bund.de, Vergabemarktplatz NRW) – nur nach Einschalten, nur diese Quellen, nur lesen; Bewertung 0–100 mit Begründung; Bewerbungsmappe; tägliche Suche. **Reinigungs-Kalkulation** (Stundensatz bleibt OFFEN, bis ihr ihn festlegt) und Angebot Dauerauftrag. Kennzahlen (CEO, Learning). Lasttest. Zahlungsanbieter **nur als Konzept** (`docs/ZAHLUNGEN.md`, PDF 7). Bedrohungsmodell ergänzt (PDF 11). Oberfläche für alle neuen Funktionen. |
| Tests | `test_auftraege.py` 26, `test_netz.py` 5, `test_kalkulation.py` 22 – **ERFOLGREICH GETESTET**. Echter Suchlauf am 21.11.2026 **ERFOLGREICH AUSGEFÜHRT**: 287 gefunden (TED 38, service.bund.de 236, Vergabemarktplatz NRW 13), 58 als passend gewertet (teils dieselbe Ausschreibung in zwei Quellen), 0 Dubletten beim zweiten Lauf, 0 Abrufe bei ausgeschalteter Recherche. Oberfläche 190/190. Lasttest: 600 Aufgaben mit 4 Arbeitern in rund 1 s. |
| Nachgeliefert (21.11.2026) | **Sicherheitsprüfung** mit den Skills `securitymaxxing:audit/injection/api` (unabhängiger Prüfer, nur lesend): 0 kritisch, 0 hoch, 1 mittel, 7 niedrig – alle **behoben** mit `securitymaxxing:fix` und je einem Test (`tests/test_haertung.py`), Prüfskripte danach ohne Befund. **HawkScan** (DAST): NICHT AUSGEFÜHRT – Programm `hawk`, StackHawk-Konto/Schlüssel und Docker fehlen. **3 Code-Fehler** mit `ruff` gefunden und behoben (u. a. falsche Zuordnung von Angebotszahlen im Marktbericht, Test beweist: vorher 5,5 statt 8). **2 weitere Fehler** behoben: doppelt definierte Funktion `_zahl` ließ „Geschäftschancen bewerten“ abbrechen (gefunden von der Oberflächen-Prüfung, jetzt mit Unit-Test); Testhilfsprozesse wurden nicht abgewartet (Warnung unter Python 3.9, jetzt 0). **Oberfläche**: Marktbericht (CEO-Zentrale), KI-Modell mit „Modell testen“ (Einstellungen, echt mit gemma3:1b geprüft) und die 10 wichtigsten Punkte des Design-Reviews umgesetzt (Skills `ui-consistency`, `ui-design-review`). **Mac-Lauffähigkeit**: alle Tests, echter Suchlauf und Oberfläche unter Python 3.9; Startskript prüft Python-Version und belegten Port (4 Fälle ERFOLGREICH AUSGEFÜHRT). |
| Nachgeliefert (22.11.2026) | **Dubletten-Erkennung** (`auftraege/dubletten.py`): gleiche Ausschreibung aus mehreren Quellen wird vorsichtig erkannt, Doppelte standardmäßig ausgeblendet, „Auch gefunden bei …“ – ERFOLGREICH GETESTET; an echten Daten vom 22.11.2026: 9 Gruppen, alle von Hand als echte Dubletten bestätigt, 0 Fehlgriffe. **3 Schwächen der Oberfläche behoben** (missverständliche rote „0“, „Angebot daraus erstellen“ bei offenem Preis, interne Namen im KI-Protokoll). |
| Nicht fertig | Hausverwaltungen automatisch finden: NICHT IMPLEMENTIERT (keine verlässliche, erlaubte Quelle). Dubletten zwischen Vergabemarktplatz NRW und anderen Quellen: an echten Daten noch nicht vorgekommen, daher dort nicht erprobt. Safari: mit der **echten Safari-Engine WebKit 26.6 in iPhone-13-Emulation ERFOLGREICH GETESTET** (22.11.2026: alle 9 Bereiche ohne Darstellungs- und Skriptfehler, keine waagerechte Scrollleiste; erzeugte Seiten unter der neuen Sicherheitsrichtlinie korrekt, Telefon- und E-Mail-Links vorhanden; Skript `tests/ui_safari_pruefung.js`). Auf einem echten iPhone/Mac: NICHT VERIFIZIERT. |
| Nachgeliefert (23.–25.11.2026) | **MacBook Air als eigener Server**: Dauerbetrieb über macOS (LaunchAgent: startet bei jeder Anmeldung, nach Absturz neu), Symbole „starten/stoppen/Autostart aus“, Daten bleiben bei Aktualisierung (echt geprüft: Schlüssel unverändert). **iPhone im eigenen WLAN**: Schalter (Standard aus), QR-Code, nur mit geheimem Link. **Überlebens-Agent**: Ampel ROT/GELB/GRÜN nur aus echten, geprüften Buchungen, feste Kosten (nur der Eigentümer trägt ein), Geldchancen nach Nähe zum Geld, täglicher Plan mit begrenzten internen Folgeaufgaben (Standard an, abschaltbar); echter Lauf: 285 Ausschreibungen → 43 Geldchancen → 3 echte Bewerbungs-Mappen, 0 Freigaben, 0 Buchungen. **Eigenes KI-Modell „autonomous“** (angepasst, nicht trainiert: Gemma 3 + eingebaute Arbeitsregeln): Prüfstand mit 15 Fällen, Bewertung nur nach festen Regeln – „autonomous“ auf gemma3:4b 98 %, Basismodell 76 % (echter Lauf, Linux ohne Grafikkarte); Faktenwächter für KI-Vorschläge in Sales und CEO; Einrichtungsskript ohne Fragen. Unabhängige UI-Prüfung (Skill `ui-consistency:verifying`, Kalibrierung mit eingebauter Abweichung gefunden): 0 Abweichungen nach 2 Runden. Sicherheitsprüfung (`securitymaxxing:diff`) des Überlebens-Agenten: keine Befunde. |
| Grenzen der KI (echt beobachtet) | Im echten Lauf vom 25.11.2026 drehte die KI-Kurzfassung einen Satz um: Plan „Noch keine Ziele festgelegt – bitte anlegen“, KI „Bitte legen Sie noch keine Ziele fest“. Der Faktenwächter prüft Zahlen, Kontakte, Preise und Zusagen, nicht den Sinn. Darum bleibt der Plan maßgeblich und jeder KI-Text als ungeprüft gekennzeichnet. Im Prüfstand empfahl auch das beste Modell einmal den Rückruf unter der Nummer eines Betrugsanrufers. gemma3:12b ist nicht gemessen und wird deshalb nie automatisch gewählt. |
| Probleme/Risiken | Fremdseiten können ihr Format ändern → die Suche dieser Quelle schlägt dann fehl (wird angezeigt, andere Quellen laufen weiter). Vergabemarktplatz NRW: nur die 20 neuesten Einträge der Startseite. |
| Dateien | `netz.py`, `auftraege/*`, `agenten/akquise.py`, `api_auftraege.py`, `produkte/kalkulation.py`, `server.py`, `db.py` (Migration 2 und 3), `ui/*`, `docs/ZAHLUNGEN.md`, `docs/BEDROHUNGSMODELL.md` |
| Nächster Schritt | Entscheidung A/B/C (KI-Modell und eigene Marktrecherche); danach erster echter Start auf dem Mac |
| Kosten/Zugänge | Keine Kosten. Für die Tests in der Entwicklungsumgebung wurden freigegeben (jeweils vom Eigentümer bestätigt): 4 Ausschreibungsseiten sowie ollama.com, github.com, registry.ollama.ai und der Modell-Downloadspeicher (für das echte KI-Modell). |

---

## Abweichungen vom ursprünglichen Auftrag (offen gelegt)

1. **Backend ohne FastAPI** – laut PDF zulässig („gleichwertig schlanke Lösung“), gewählt für „läuft ohne Installation“.
2. ~~Agenten ohne KI-Modell / Research-Agent ohne eigene Recherche~~ – **erledigt** am 21.11.2026 (lokales Modell, echte Marktuntersuchung aus amtlichen Daten; siehe Phase 4).
3. **Reihenfolge:** Auftrags-Radar und Kalkulation wurden vor dem Abschluss von Phase 5 (echte Rückmeldungen) gebaut.
4. **Hausverwaltungen automatisch finden** wurde angekündigt, aber nicht umgesetzt.
5. **Berichte je Phase** wurden erst nachträglich in diesem Format erstellt, nicht nach jeder Phase.
6. **HawkScan** (dynamischer Sicherheitstest) konnte nicht laufen (Programm, Konto und Docker fehlen); ersetzt durch eine unabhängige Prüfung gegen den laufenden Server mit den Skills `securitymaxxing`.
7. **Ungenaue Commit-Nachricht:** Der Zwischenstand-Commit `e9b8dbc` (23.11.2026) sagt „alle Tests grün“. In dem Moment waren die Unit-Tests grün, die Oberflächen-Prüfung aber rot (der neue Test war absichtlich zuerst geschrieben). Der fertige Stand (`8917eb9`) ist vollständig grün.
8. **Basismodell:** Der KI-Agent hatte ab 14 GB Arbeitsspeicher gemma3:12b vorgesehen. Weil 12b nie gemessen wurde, wählt das Skript jetzt ab 6 GB das gemessene gemma3:4b; 12b nur auf ausdrücklichen Wunsch.
