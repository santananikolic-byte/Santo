# BRAIN

Bestätigter Stand aus den Interviews, Runde 1 und 2, und dem Daily Brain Update
(30.10.2026). Nur Einträge, die bestätigt wurden — nichts geraten.

---

## CORE PROFILE

- **C1** Familienbetrieb mit meinem Vater: **Bau und Reinigung** (Bau, Gebäude-,
  Büro- und Treppenhausreinigung).
- **C2** Aufträge sind **projektbasiert und wechselhaft**, kaum feste Daueraufträge.
- **C3** Sitz **Leverkusen bei Köln**, tätig in ganz NRW (z. B. Düren, Düsseldorf),
  bis zu 100 km Anfahrt. Möglicherweise bald auch **Berlin**.
- **C4** Kernproblem: **Unbeständigkeit** — mal fehlen Aufträge, mal Mitarbeiter.
  Hohe Kosten (Personal, Sprit, Material, Steuern, Energie) fressen das Kapital.
- **C5** Lebensziele: Sorgenfreiheit, Familie, Gesundheit, Hausbau, Reisen, Hochzeit.
- **C6** Finanzziele: Etappe **1 Mio. €/Monat** (je 500.000 € für mich und meinen
  Vater), Vision bis zu **200 Mio. €/Jahr**. 20.000 = Minimum, um über die Runden
  zu kommen.
- **C7** Strategie: Neben A (Bau) und B (Reinigung) weitere Einnahmequellen C, D
  und mehr aufbauen — **KI ausdrücklich eingeschlossen**.
- **C8** Persönlich: gibt derzeit vorsichtig Geld aus, zahlt Miete, hat **noch
  keinen Führerschein** und möchte ihn machen.
- **C9** Kommunikation: Deutsch, spricht frei und ausführlich, will fertige
  Dateien, die per Doppelklick laufen.
- **C10** Entscheidungen über Geld, Aufträge und Projekte treffen **mein Vater und
  ich gemeinsam**.
- **C11** **Wenige Mitarbeiter** — das Team soll **wachsen**.
- **C12** **Offen für alle Kundenarten**, keine feste Zielgruppe.
- **C13** Preise: Mein Vater passt sie **je nach Auftrag an**; ich halte das für
  **nicht richtig** und hätte gern eine feste Kalkulation.
- **C14** Hauptsorge: **Identitätsbetrug** — Leute geben sich als Inhaber oder
  Vertreter einer Firma aus; das kostet Zeit und Nerven.
- **C15** Geräte: **Mac und Handy**.
- **C16** Ergebnisse will ich **vor dem Speichern zur Bestätigung sehen**.
- **C17** Ich formuliere Aufträge in festen Blöcken (ZIEL, KONTEXT, REGELN,
  GRENZEN, OUTPUT, STOP).
- **C18** Interviews: höchstens 10 Fragen pro Runde, eine nach der anderen,
  jeweils mit einem Satz Begründung.

## PROJECT BRAIN

| # | Projekt | Stand |
|---|---|---|
| P1 | **Jarvis** (Sprachassistent auf dem Mac) | Code existiert in diesem Repo, aber **noch nicht eingerichtet und nicht getestet**. Hauptauftrag: Aufträge finden und Informationsvorsprung verschaffen. |
| P2 | **Akquise** | Heute: Portale (Account des Vaters), Anrufe, Kleinanzeigen, viele eigene Anfragen. Es fehlen Partner, Netzwerk, Empfehlungen. |
| P3 | **Daueraufträge** | Ziel: feste, wiederkehrende Reinigungsobjekte für beständiges Einkommen. |
| P4 | **Zusätzliche Einnahmequellen (C/D)** | Noch offen. KI gewünscht; vorhanden: Chatbot-Lead-Liste (50 Firmen), Lena. |
| P5 | **Kosten und Steuern** | Jarvis soll Kostentreiber und Steuerlast sichtbar machen, Vor-/Nachteile von Investitionen zeigen. |
| P6 | **Führerschein** | Kurzfristiges persönliches Ziel, Finanzierung ungeklärt. |
| P7 | **Firmen- und Anruferprüfung** | Neu. Vor jedem Auftrag prüfen: Firma im Handelsregister, Geschäftsführer/Prokuristen, Impressum, passt die E-Mail-Domain, Bewertungen, Insolvenzen. **Rückruf-Regel:** immer über die offizielle Nummer, nie über die vom Anrufer genannte. Schriftliche Bestätigung von der Firmenadresse. |
| P8 | **Feste Preiskalkulation** | Neu. Stundensatz und Leistungswerte statt Preise nach Gefühl. |
| P9 | **Mitarbeiter gewinnen** | Neu. Eigenes Ziel, damit mehr Aufträge angenommen werden können. |
| P10 | **Brain und Arbeitsregeln** | `BRAIN.md` (dieses Profil) und `CLAUDE.md` (Arbeitsregeln, die Claude bei jeder Sitzung automatisch liest) liegen im Repo. |
| P12 | **Jarvis als Einzeldatei** | `jarvis.html`: Jarvis zum Doppelklicken im Browser, mit „Hey Jarvis“, Stimme, Websuche (Firmenprüfung) und Gedächtnis mit Bestätigung. Braucht einen Claude-API-Schlüssel, der nur im Browser gespeichert wird. Mit echtem Schlüssel noch nicht getestet. |
| P13 | **Jarvis im Mac-Terminal** | `jarvis_terminal.py`: Start mit `python3 jarvis_terminal.py`. Läuft über das eigene Claude-Abo (Claude Code), ohne API-Schlüssel und ohne Zusatzkosten. Eigenes Sprachsystem: hört dauerhaft zu und reagiert auf „Hey Jarvis“ (Apples Spracherkennung, auf dem Mac selbst, wenn der Mac das kann), spricht mit der besten Stimme auf dem Mac (Premium/Siri), Merken per gesprochenem Ja/Nein. Daten in `~/.jarvis-terminal/`. Einrichten auf dem iMac mit einer Zeile: `curl -fsSL https://raw.githubusercontent.com/santananikolic-byte/Santo/claude/jarvis-voice-assistant-70695g/jarvis-imac.sh \| bash`, danach Doppelklick auf „Jarvis“ auf dem Schreibtisch. Auf einem echten Mac und mit echtem Schlüssel noch nicht getestet. |
| P14 | **JARVIS-Server (neuer Kern)** | Phase 1 erledigt (iMac 2017 Intel, macOS 13.7.8, Claude Code 2.1.316 mit Pro-Abo angemeldet, Python 3.9.6, Swift 5.8.1; Node/Homebrew/Codex/Gemini fehlen; nur einfache deutsche Stimmen). Phase 2 erledigt: lokaler Server `jarvis_core/` auf 127.0.0.1:8770 mit Status, JSON-Logs, Start/Stopp (`./jarvis.sh`), 20 Tests grün unter Python 3.9. Auf dem iMac gestartet (Status aktiv). Phase 3 erledigt: beantwortet Fragen über Claude Code mit dem Pro-Abo (ohne Werkzeuge, ohne API-Schlüssel), setzt Gespräche fort, lädt CLAUDE.md und BRAIN.md als Wissen; Statusseite mit Eingabefeld, `./jarvis.sh frage`. 25 Tests grün (Claude Code simuliert). Echte Antwort auf dem iMac noch nicht geprüft. |
| P11 | **JARVIS Master Prompt** | `jarvis-master-prompt.html`: der Prompt als Webseite, offline per Doppelklick, auch auf dem Handy lesbar. |

## DECISION LOG

| # | Datum | Entscheidung |
|---|---|---|
| D1 | 30.10.2026 | Etappenziel **1 Mio. €/Monat**, je zur Hälfte für mich und meinen Vater. |
| D2 | 30.10.2026 | Mehrere Einnahmequellen aufbauen, KI ist eine davon. |
| D3 | 30.10.2026 | Wichtigste Aufgabe von Jarvis: **Aufträge finden**. |
| D4 | 30.10.2026 | Akquise nur über legale, öffentlich zugängliche Quellen — keine Umgehung von Zugangssperren. |
| D5 | 30.10.2026 | Priorität der nächsten 3 Monate: **mehr Aufträge gewinnen**. |
| D6 | 30.10.2026 | „Inoffizielle Quellen“ heißt vor allem: **früh von Aufträgen erfahren** und **Kunden auf Echtheit prüfen**. |
| D7 | 30.10.2026 | Prüfung nur über legale, öffentliche Quellen und offizielle Rückrufe — keine Ausforschung privater Nummern oder E-Mails, keine Persönlichkeitsprofile von Privatpersonen. |
| D8 | 30.10.2026 | `BRAIN.md` und `CLAUDE.md` liegen im GitHub-Repo — bewusst entschieden, trotz Hinweis auf das Risiko eines öffentlichen Repos. |
| D9 | 30.10.2026 | Finanzziele stehen nur in `BRAIN.md`, nicht in `CLAUDE.md`. |

## RULES

- **Nichts senden, löschen oder bezahlen ohne mein ausdrückliches Ja.** Vorher
  kurz zeigen, was genau passiert. Ein Ja gilt nur für diese eine Aktion.
- Keinem Kunden Preise, Termine oder Leistungen zusagen, ohne dass wir es
  geprüft haben.

## LEARNINGS

- Bei offenen Zahlenfragen nicht mehrfach nachbohren, sondern sie am Ende zur
  Bestätigung vorlegen.

## ERLEDIGT

| Datum | Aufgabe |
|---|---|
| 30.10.2026 | JARVIS-Prompt als einzelne HTML-Datei gebaut, auf Handy und Desktop getestet, gepusht. |
| 30.10.2026 | Interview Runde 1 und 2 abgeschlossen und bestätigt. |
| 30.10.2026 | OZ-CORE-Zusammenfassung (13 Abschnitte) erstellt. |
| 30.10.2026 | `CLAUDE.md` erstellt, bestätigt und gepusht. |
| 30.10.2026 | README angepasst: Familienbetrieb in Bau und Reinigung statt Einzelunternehmer in der Gebäudereinigung. |
| 30.10.2026 | `jarvis.html` gebaut (Jarvis als Einzeldatei mit Sprache), mit simulierten Antworten getestet. |
| 30.10.2026 | `jarvis_terminal.py` gebaut (Jarvis im Terminal), mit simulierten Antworten getestet. |

## NACHTRÄGE (offen)

- Welche Portale mein Vater nutzt und welches am meisten bringt — trage ich später
  in Jarvis ein.
- Unser konkreter Stundensatz bzw. unsere Preise.
- Genaue Zahl der Mitarbeiter, fest angestellt oder Aushilfen.
- Entscheidungsstil: eher schnell oder erst alles durchrechnen?

## NÄCHSTER SCHRITT

0. Das Repo ist **öffentlich** (am 30.10.2026 geprüft: Dateien sind ohne Anmeldung
   abrufbar). Entscheidung offen: privat stellen (dann funktionieren die
   Ein-Zeilen-Installer nicht mehr ohne Anmeldung) oder BRAIN.md aus dem Repo nehmen.
1. Jarvis auf dem Mac installieren (Installationszeile aus der README).
2. Anthropic-Schlüssel nur lokal in der Einrichtung eintragen — nie in einen Chat.
3. Danach als erste neue Funktion: Firmen- und Anruferprüfung (P7).
