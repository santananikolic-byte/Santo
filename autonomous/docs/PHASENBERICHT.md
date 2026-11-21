# AUTONOMOUS – Bericht je Phase (PDF Abschnitt 14)

Grundlage: „AUTONOMOUS – Master Development Directive v3.0“ (20.11.2026). Stand dieses Berichts: 21.11.2026.

Status-Begriffe (Strict Execution Protocol): **GEPLANT · IMPLEMENTIERT · ERFOLGREICH AUSGEFÜHRT · ERFOLGREICH GETESTET ·
FEHLGESCHLAGEN · NICHT VERIFIZIERT**. „Getestet“ heißt: automatische Tests in der Entwicklungsumgebung (Linux,
Python 3.13). **Auf dem Mac ist nichts verifiziert** – das gilt für jede Zeile unten.

Letzter vollständiger Lauf (21.11.2026): Kompilieren fehlerfrei · **232 von 232 Unit-Tests bestanden unter Python 3.13
und unter Python 3.9** (wie auf dem Mac vorinstalliert) · Prüfwerkzeug `ruff` (Fehlerregeln): keine Fehler ·
Oberflächen-Prüfung: wird nach Abschluss der laufenden Oberflächen-Arbeit eingetragen · fehlgeschlagen: keine.

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
| Nachgeliefert (21.11.2026) | **Sicherheitsprüfung** mit den Skills `securitymaxxing:audit/injection/api` (unabhängiger Prüfer, nur lesend): 0 kritisch, 0 hoch, 1 mittel, 7 niedrig – alle **behoben** mit `securitymaxxing:fix` und je einem Test (`tests/test_haertung.py`), Prüfskripte danach ohne Befund. **HawkScan** (DAST): NICHT AUSGEFÜHRT – Programm `hawk`, StackHawk-Konto/Schlüssel und Docker fehlen. **3 Code-Fehler** mit `ruff` gefunden und behoben (u. a. falsche Zuordnung von Angebotszahlen im Marktbericht, Test beweist: vorher 5,5 statt 8). **Mac-Lauffähigkeit**: alle Tests, echter Suchlauf und Oberfläche unter Python 3.9; Startskript prüft Python-Version und belegten Port (4 Fälle ERFOLGREICH AUSGEFÜHRT). |
| Nicht fertig | Zusammenführung gleicher Ausschreibungen aus zwei Quellen: NICHT IMPLEMENTIERT. Hausverwaltungen automatisch finden: NICHT IMPLEMENTIERT (keine verlässliche, erlaubte Quelle). Safari mit der neuen Sicherheitsrichtlinie für erzeugte Seiten: NICHT VERIFIZIERT. |
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
