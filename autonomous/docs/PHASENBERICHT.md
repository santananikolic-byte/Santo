# AUTONOMOUS – Phasenbericht (Abschnitt 14 des Entwicklungsauftrags)

> **ENTWURF** – Oberfläche und Google-Profil-Paket sind noch in Arbeit; dieser Bericht wird nach deren Abschluss
> mit den echten Testzahlen aktualisiert.

Stand: 20.11.2026. Bedeutung: **Getestet** = automatische Tests laufen grün in der Entwicklungsumgebung (Linux, Python 3.13).
**Auf dem Mac verifiziert** = noch **nichts** – der erste echte Start auf dem Mac steht aus.

## Kurzfassung

| Phase | Stand | Beleg |
|---|---|---|
| 1 Bestandsaufnahme | erledigt | Abschnitt „Phase 1“ unten |
| 2 Funktionsfähiger Kern | erledigt, getestet | `tests/test_kern.py`, `tests/test_sicherheit.py` (Server) |
| 3 Wallet und Finanzen | erledigt, getestet | `tests/test_finanzen.py` |
| 4 Erste Agenten | erledigt, getestet | CEO, Research, Product, Sales, Finance, Learning + Supervisor |
| 5 Erstes Produkt und Vertrieb | Webseiten-Paket, Verkaufsseite, Vertrieb: erledigt, getestet. Google-Profil-Paket: **in Arbeit** | `tests/test_produkt_vertrieb.py`, `beispiele/` |
| 6 Erweiterung | teilweise | Finance, Sales, Learning vorhanden; Lasttest vorhanden; Kennzahlen über CEO-Agent |

Gesamtergebnis der automatischen Tests: siehe Abschnitt „Tests“ am Ende (echte Zahlen des letzten Laufs).

---

## Phase 1 – Bestandsaufnahme

**Vorgefunden:** Im Repository liegt bereits JARVIS (`jarvis_core/`, Sprachassistent, nur Python-Standardbibliothek).
AUTONOMOUS wurde **daneben** als eigenes Paket `autonomous/` gebaut; an JARVIS wurde nichts verändert.
In der Umgebung: Python 3.13, kein FastAPI installiert, Node 22, Playwright/Chromium für Oberflächentests.

**Technische Entscheidung (umkehrbar, risikoarm):**

- **Backend: Python-Standardbibliothek** (`http.server`, `sqlite3`) statt FastAPI. Grund: Auf dem Mac soll alles **per Doppelklick ohne Installation** laufen (Vorgabe aus CLAUDE.md). Der Auftrag erlaubt „eine gleichwertig schlanke Lösung“. Ein späterer Wechsel zu FastAPI ist möglich, weil die Routen in `api.py` sauber getrennt sind.
- **Datenhaltung:** SQLite mit nummerierten Migrationen (`db.py`), WAL-Modus.
- **Keine zusätzlichen Pakete, nichts von GitHub heruntergeladen.** Jede fremde Abhängigkeit wäre ein zusätzliches Sicherheits- und Wartungsrisiko, ohne dass sie hier gebraucht wird.
- **Kein PostgreSQL, Redis, Docker, kein Agenten-Framework** – kein konkreter Bedarf (Abschnitt 4).

**Kosten:** 0 €. Keine kostenpflichtigen Dienste, keine API-Schlüssel.

## Phase 2 – Funktionsfähiger Kern

**Implementiert:**

- Start/Stopp: `AUTONOMOUS-starten.command`, `AUTONOMOUS-stoppen.command`, `python3 -m autonomous start|link|status|sicherung|sicherungen|wiederherstellen|export|test`.
- Server nur auf 127.0.0.1, Zugangsschlüssel, Host- und Herkunftsprüfung, strikte CSP (`server.py`).
- Persistente Aufgabenverwaltung mit allen geforderten Status, Verlauf jedes Statuswechsels, begrenzten Wiederholungen, Wiederherstellung nach Neustart (`aufgaben.py`).
- Orchestrierung mit begrenzter Parallelität (1–8 Arbeiter), atomarer Aufgabenvergabe (`orchestrator.py`).
- Echter Systemstatus für das Dashboard (`kern.py` → `/api/status`, `/api/dashboard`).
- Protokoll mit Schwärzung von Geheimnissen (`protokoll.py`), tägliche und manuelle Sicherung, geprüfte Wiederherstellung, JSON-Export (`sicherung.py`).
- Gedächtnis mit Trennung **Fakt / Entscheidung / Hypothese / Vorschlag**; Agenten dürfen nur Vorschläge und Hypothesen anlegen, Fakten nur mit prüfbarer Quelle (`gedaechtnis.py`).

**Ausgeführt und beobachtet (nicht nur Unit-Tests):** Server im Container gestartet, über HTTP komplette Abläufe durchgespielt (Ziel → Tagesplan → Marktbewertung → Webseite → Angebot → Versand-Freigabe), Start/Stopp-Skripte ausgeführt, sauberes Beenden bestätigt.

## Phase 3 – Wallet und Finanzen

**Implementiert:**

- Internes Wallet mit **15,00 € SIMULATION**; jede Buchung mit ID, laufender Nummer, Zeitstempel, Betrag, Währung, Kategorie, Art, Status, Begründung (`wallet.py`).
- **Unveränderbare Historie** per Datenbank-Trigger; Korrektur nur durch Gegenbuchung.
- Budgets mit Warnungen (Wallet und real getrennt).
- Reale Finanzen in **eigener Tabelle** (`finanzen.py`): Einnahme nur mit Zahlungsnachweis **und** Prüfer – von der Datenbank erzwungen; Forderungen ≠ Einnahmen; nur der Eigentümer bucht.
- **Wallet-Stand null oder negativ stoppt nichts** – der Systemstatus ist unabhängig vom Wallet.

## Phase 4 – Erste Agenten

| Rolle | Aufgabentypen | Darf |
|---|---|---|
| CEO | tagesplan, kennzahlen, auftrag_verteilen, chancen_bewerten | planen, auswerten, Vorschläge |
| Research | marktbewertung, quellen_pruefen | lokale Daten auswerten |
| Product | webseite_erstellen, google_profil_paket, verkaufsseite_erstellen, qualitaetspruefung | Dateien nur im Datenordner |
| Sales | angebot_entwurf, nachricht_entwurf, pipeline_auswertung, angebot_versenden | Entwürfe; Kundenkontakt **nur mit Freigabe** |
| Finance | finanzbericht, liquiditaet, wirtschaftlichkeit, simulation_buchen | nur Simulation buchen |
| Learning | auswertung | nur Vorschläge, ändert keine Regeln |
| Supervisor | prüft jede Aktion und jedes Ergebnis | blockiert, protokolliert |

Rechte stehen unveränderlich im Code. Ein Agent kann seine Rechte nicht erweitern (getestet).
Das Register trägt bis zu 500 logische Rollen, ohne je Rolle einen Prozess zu starten (Lasttest).

## Phase 5 – Erstes Produkt und Vertrieb

- **Marktanalyse** mit 94 Quellen: `docs/MARKTANALYSE.md` und `daten_vorlagen/marktbewertung.json`.
  Empfehlung (VORSCHLAG): **Google-Profil-Paket** für kleine Handwerks-, Bau- und Reinigungsbetriebe in NRW; Webseiten als Stufe 2.
  **Nachgeprüft:** Bitkom-Zahlen (94 % Website, 88 % Verzeichnisse) und Kleinunternehmer-Grenzen bestätigt.
  **Nicht bestätigt:** die konkreten Anbieterpreise (Seiten in der Arbeitsumgebung gesperrt, Kontrollsuchen fanden andere Werte: 99 € bis 499 €). Die Preisspanne 199–349 € ist darum als **UNSICHER** markiert.
- **Erzeugbare Produkte:** Webseite für einen Betrieb (eine Datei, ohne JavaScript, ohne fremde Server) und Google-Profil-Paket (Profil-Entwurf, Prüfliste, Übergabe-Anleitung), jeweils mit automatischer Qualitätsprüfung.
- **Verkaufsseite** ohne erfundenen Preis: Preis und Lieferzeit erscheinen nur, wenn ihr sie festlegt.
- **Vertrieb:** Kontakte mit Einwilligungsnachweis, Pipeline, Angebote als druckbare Entwürfe, Ablauf Entwurf → geprüft → (selbst) versendet → angenommen/abgelehnt. Versand nur nach Freigabe – und auch dann sendet Version 1 nichts selbst (kein Versandkanal angebunden), das System sagt das offen.
- **Beispiele zum Ansehen:** `autonomous/beispiele/` (fiktive „Musterfirma Reinigung (Beispiel)“).

## Phase 6 – Erweiterung (Stand)

- Finance-, Sales- und Learning-Agent: vorhanden.
- Kennzahlen: CEO-Aufgabe `kennzahlen`, Learning-Auswertung je Rolle (Erfolgsquote, Dauer, Fehler).
- Lasttest: 600 Aufgaben, 4 Arbeiter, keine doppelte Vergabe (Messwert im Testlauf ausgegeben).
- **Nicht gebaut:** weitere Automatisierungen (erst nach echtem Bedarf), echte Versandkanäle, Zahlungsanbieter (PayPal nur konzeptionell), Krypto-Wallet (ausdrücklich nicht Teil von Version 1).

## Probleme und Risiken

- **Nichts davon ist auf dem Mac verifiziert.** Erster Start: Doppelklick auf `AUTONOMOUS-starten.command`.
- **Preise und Nachfrage sind nicht belegt.** Ob Betriebe für das Google-Profil-Paket zahlen, zeigt erst ein Test mit 5–10 Gesprächen. Erster Testkunde: der eigene Betrieb.
- **Rechtliches:** Impressum, Datenschutz, Gewerbe- und Steuerfragen sind nur als offene Punkte markiert – keine Rechtsberatung. Vor dem ersten Verkauf mit Steuerberater klären (Kleinunternehmer-Regel über den Familienbetrieb vermutlich nicht nutzbar).
- **Werbung:** Keine Werbe-E-Mails oder Werbeanrufe ohne Einwilligung (§ 7 UWG). Das System empfiehlt Brief oder persönliches Gespräch.
- Bekannte technische Lücken: siehe `docs/BEDROHUNGSMODELL.md`, Abschnitt „Bekannte Lücken“.

## Nächster konkreter Schritt

1. Vater und Sohn entscheiden: Google-Profil-Paket als erstes Angebot ja/nein, Preis festlegen.
2. AUTONOMOUS auf dem Mac starten, das Paket für den **eigenen Betrieb** erzeugen und das eigene Google-Profil damit vervollständigen (echter Praxistest, kostet nichts).
3. Danach Verkaufsseite mit festgelegtem Preis erzeugen und 5–10 Betriebe aus dem eigenen Umfeld persönlich ansprechen.

## Zusätzliche Kosten oder Zugänge?

**Keine.** Optional später (nur mit eurer Zustimmung und Preisangabe): lokales Modell über Ollama (kostenlos, eigene Hardware), Hosting für Kunden-Webseiten, ein Versandkanal.

## Tests

Siehe unten – wird nach jedem vollständigen Lauf aktualisiert.
