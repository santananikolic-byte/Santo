# AUTONOMOUS – Überlebens-Agent

Stand: 25.11.2026. Status-Begriffe: **GEPLANT · IMPLEMENTIERT · ERFOLGREICH AUSGEFÜHRT · ERFOLGREICH GETESTET ·
FEHLGESCHLAGEN · NICHT VERIFIZIERT**. Alles unten gilt für die Entwicklungsumgebung (Linux) – **auf dem Mac ist nichts
davon verifiziert**.

## Kurz

Der Überlebens-Agent schaut jeden Tag: **Reicht das echte Geld?** Und: **Wo kommt als Nächstes Geld her?**
Er zeigt eine Ampel (ROT / GELB / GRÜN) mit Begründung, die besten Geldchancen mit nächstem Schritt, und er stößt
selbst nur **interne** Arbeit an (Ausschreibungen suchen, Bewerbungs-Mappen, Nachfass-Entwürfe).
Er **sendet nichts, bezahlt nichts und gibt kein Angebot ab**. Das entscheidet ihr.

Damit die Ampel etwas sagen kann, braucht er eure **festen Kosten** (z. B. Claude-Abo, Versicherung). Solange keine
eingetragen sind, steht dort ehrlich „Kosten nicht erfasst“ und die Ampel bleibt GELB.

| Teil | Status |
|---|---|
| Lage aus echten Zahlen, Ampel mit Begründung (`autonomous/ueberleben.py`) | IMPLEMENTIERT, ERFOLGREICH GETESTET |
| Feste Kosten (Tabelle `fixkosten`, Migration 5 in `db.py`) | IMPLEMENTIERT, ERFOLGREICH GETESTET |
| Geldchancen (5 Arten, feste Reihenfolge) | IMPLEMENTIERT, ERFOLGREICH GETESTET |
| Agent „Überlebens-Agent“, Aufgabe `ueberlebensplan` (`autonomous/agenten/ueberleben.py`) | IMPLEMENTIERT, ERFOLGREICH GETESTET, mit echten Ausschreibungen ERFOLGREICH AUSGEFÜHRT |
| Schnittstelle (`autonomous/api_ueberleben.py`) | IMPLEMENTIERT, ERFOLGREICH GETESTET (direkt aufgerufen) |
| Täglicher Plan: `zeitplan_pruefen(kern)` | IMPLEMENTIERT, ERFOLGREICH GETESTET – **im Server noch nicht eingebunden** |
| Einbindung in `server.py` und Oberfläche | GEPLANT (macht der Hauptagent) – über den laufenden Server NICHT VERIFIZIERT |

## Die Ampel – feste Regel

Grundlage sind nur echte, geprüfte Buchungen aus den realen Finanzen:

- **Einnahmen der letzten 30 Tage** (heute mitgezählt), nur verifizierte Einnahmen. Gegengebuchte (korrigierte)
  Buchungen zählen nicht.
- **Feste Kosten je Monat**: alle aktiven Einträge; Jahresbeträge zählen mit einem Zwölftel. Ein Eintrag mit
  „seit“-Datum in der Zukunft zählt erst ab diesem Tag.
- **Saldo**: Summe aller in AUTONOMOUS erfassten echten Buchungen. Das ist **kein Kontostand der Bank** (außer ihr
  habt den Anfangsbestand erfasst). Ohne jede echte Buchung ist der Saldo „unbekannt“.

| Ergebnis | Wann |
|---|---|
| **GELB – „Kosten nicht erfasst“** | Es sind keine festen Kosten eingetragen. Ohne Kosten gibt es kein Urteil. |
| **ROT** | In den letzten 30 Tagen keine geprüfte Einnahme (bei erfassten Kosten) **oder** Saldo (falls bekannt) kleiner als die festen Kosten eines Monats |
| **GRÜN** | Geprüfte Einnahmen der letzten 30 Tage mindestens so hoch wie die festen Kosten eines Monats (und nicht ROT) |
| **GELB** | alles andere (es gab Einnahmen, sie decken die Kosten aber noch nicht) |

Beispiele (aus den Tests, von Hand gerechnet): Kosten 22 €, keine Einnahme → ROT. Kosten 22 €, Einnahmen 22 €,
Saldo 22 € → GRÜN (genau gleich ist kein Mangel). Kosten 22 €, Saldo 21,99 €, Einnahmen 50 € → ROT.

**Reichweite** = Saldo geteilt durch feste Kosten je Monat, abgerundet auf eine Nachkommastelle. Nur wenn Saldo und
Kosten bekannt sind; sonst „unbekannt“. Saldo 0 oder darunter → 0 Monate.

**Was nie zählt:** das Simulations-Wallet (Spielgeld) und offene Forderungen. Forderungen werden angezeigt, aber
als „erwartet, nicht sicher“.

**Geldmangel schaltet nichts ab** (Auftrag PDF 6.3): Die Ampel ändert nur, **wie viel** der Agent anstößt und
**wie dringend** (Priorität). Alle anderen Agenten und Aufgaben laufen weiter – auch bei ROT (getestet).

## Feste Kosten eintragen

Nur der Eigentümer trägt ein, nichts ist vorbelegt. Angaben: Bezeichnung (z. B. „Claude-Abo“), Betrag, Intervall
`monat` oder `jahr`, optional „seit“ (JJJJ-MM-TT). „Entfernen“ blendet einen Eintrag aus (er bleibt in der
Datenbank nachvollziehbar), gelöscht wird nichts.

## Geldchancen – je näher am Geld, desto weiter oben

| Reihenfolge | Art | Wann | Wert |
|---|---|---|---|
| 1 | **Zahlung anmahnen** | offene Forderung, Fälligkeit vorbei (älteste zuerst). Mit fertigem **Entwurf** einer Zahlungserinnerung – Platzhalter für Datum und Bankverbindung füllt ihr. | Betrag der Forderung |
| 2 | **Rechnung schreiben** | Angebot „angenommen“, aber noch keine Forderung dazu | Angebotsbetrag |
| 3 | **Nachfassen** | Angebot „versendet“, seit mehr als 7 Tagen keine Entscheidung | Angebotsbetrag |
| 4 | **Angebot machen** | Kontakt „interessiert“, aber kein laufendes Angebot | unbekannt |
| 5 | **Ausschreibung** | offen, Frist mindestens 3 Tage entfernt; nach Punkten, dann Frist | **unbekannt** (Auftragswerte werden nie geschätzt) |

Je Chance: was, warum, nächster Schritt, Frist, Wert – und ggf. „Schon getan: heute angestoßen …“.

Regeln im Detail:

- **Ausschreibungen:** Was ihr selbst als „interessant“ oder „vorbereitet“ markiert habt, zählt immer. Neue Funde
  nur, wenn sie passen (mindestens 60 Punkte) und nicht außerhalb eurer Region liegen (PLZ-Bereiche aus den
  Einstellungen bzw. „außerhalb“ in der Bewertung). Dieselbe Ausschreibung aus zwei Quellen zählt einmal.
  Ausschreibungen **ohne Frist** zählen nicht (ob noch genug Zeit ist, lässt sich nicht prüfen).
- **Rechnung schreiben – woran erkennt AUTONOMOUS die Rechnung?** Es gibt keine feste Verbindung zwischen Angebot und
  Forderung. Regel: Angebotsnummer (z. B. `ANG-20261120-ABCD`) oder Angebots-ID steht in Rechnungsnummer oder
  Notiz der Forderung – **oder** es gibt eine Forderung an genau denselben Firmennamen, angelegt am Tag der Annahme
  oder danach. Auch eine stornierte Forderung zählt als „erledigt“ (bewusste Entscheidung).
- **Mahnung:** Forderungen ohne Fälligkeitsdatum können nicht überfällig sein und erscheinen hier nicht.

## Was der Agent selbst anstößt (nur intern)

Aufgabe `ueberlebensplan` des Überlebens-Agenten. Er legt Folgeaufgaben **anderer** Agenten an – nichts davon
sendet, bezahlt oder gibt ab:

| Folgeaufgabe | Wer | Bedingung | Menge |
|---|---|---|---|
| `ausschreibungen_suchen` | Akquise-Agent (nur lesen, nur freigegebene Quellen) | Internet-Recherche ist eingeschaltet **und** letzte Suche älter als 20 Stunden **und** keine Suche offen oder heute schon angestoßen | höchstens 1 je Tag |
| `ausschreibung_vorbereiten` (Bewerbungs-Mappe) | Akquise-Agent | beste noch nicht vorbereitete Ausschreibungen (neu/interessant, noch keine Mappe, keine offene Aufgabe dazu) | **harte Obergrenze je Tag: GRÜN 1, GELB 3, ROT 5** |
| `nachricht_entwurf` (Nachfassen) | Sales-Agent – nur **Entwurf**, „nicht versendet“ | versendetes Angebot > 7 Tage ohne Entscheidung, mit Kontakt | höchstens 1 Entwurf je Kontakt in 7 Tagen, höchstens 4 je Tag |

- **Priorität** der Folgeaufgaben: ROT 1 (zuerst), GELB 2, GRÜN 3.
- **Nichts doppelt:** Je Tag höchstens einmal dieselbe Folgeaufgabe (gleiche Ausschreibung bzw. gleicher Kontakt).
  Das gilt auch, wenn zwei Pläne gleichzeitig laufen: Der früher gestartete legt an, der andere vermerkt „läuft
  gerade“. Auch die kurze Lücke zwischen „Plan fertig“ und „Folgeaufgaben angelegt“ ist abgesichert (getestet).
- Was er bewusst **nicht** angestoßen hat, steht mit Grund im Plan (z. B. „Tagesgrenze erreicht“).
- **Rechte** (fest im Code): nur `interne_planung`, `interne_auswertung`, `datei_erstellen`, `gedaechtnis_vorschlag` –
  alle automatisch erlaubt und intern. Kein `web_lesen`, keine externe Aktion; der Supervisor blockiert alles andere.

**Ergebnis jedes Plans:**
- druckbare Seite ohne JavaScript, alle Inhalte escaped: `daten/produkte/ueberleben/<Datum>/plan.html`
  (ein zweiter Plan am selben Tag bekommt `plan-<Aufgabe>.html` – nichts wird überschrieben),
- Gedächtnis-Eintrag der Art **Vorschlag** („Überlebensplan TT.MM.JJJJ“),
- das Aufgabenergebnis (Lage, Top 10 Geldchancen, Folgeaufgaben, Übersprungenes).

**Täglich:** `ueberleben.zeitplan_pruefen(kern)` legt **höchstens einmal je Tag** einen Plan an (Ersteller
„zeitplan“) – keinen, wenn heute schon einer angelegt wurde (auch von euch) oder noch einer offen ist. Gedacht zum
stündlichen Aufruf im Hintergrund wie die tägliche Ausschreibungssuche.

## Schnittstelle (für die Oberfläche)

| Aufruf | Antwort |
|---|---|
| `GET /api/ueberleben` | `druck`, `regel`, `begruendung`, `einnahmen_monat`, `einnahmen_30_tage`, `ausgaben_30_tage`, `saldo`, `offene_forderungen`, `fixkosten_monat`, `reichweite_monate` (Zahl oder `null`), `reichweite` (Text), dazu je `…_cent`; `geldchancen[]` (höchstens 25), `geldchancen_gesamt`, `letzter_plan` (oder `null`), `plan_in_arbeit` |
| `POST /api/ueberleben/plan` | `{aufgabe_id}`; ist schon ein Plan offen: dessen ID und `hinweis` |
| `GET /api/fixkosten` | `fixkosten[]`, `summe_monat`, `summe_monat_cent`, `entfernt[]`, `hinweis` |
| `POST /api/fixkosten` `{bezeichnung, betrag, intervall, seit?}` | `{id}` – Fehler 400 mit verständlicher Meldung |
| `POST /api/fixkosten/{id}/entfernen` | `{ok: true}` – 404, wenn nicht (mehr) vorhanden |

Einbindung (macht der Hauptagent): in `server.py` `from . import api_ueberleben` wie bei den anderen Modulen, und
`ueberleben.zeitplan_pruefen(kern)` im stündlichen Hintergrundlauf.

## Tests

`autonomous/tests/test_ueberleben.py`: **50 Tests**, unter **Python 3.13 und 3.9 bestanden** (25.11.2026) –
ERFOLGREICH GETESTET. Geprüft u. a.: Migration 4 → 5 ohne Datenverlust; Lage ohne Daten ehrlich („unbekannt“,
„Kosten nicht erfasst“); ROT/GELB/GRÜN an 10 von Hand gerechneten Fällen; Wallet zählt nie; Reihenfolge und Filter
der Geldchancen; Obergrenzen 1/3/5, Prioritäten, Idempotenz (auch bei zwei gleichzeitigen Plänen); Suche nur mit
eingeschalteter Recherche und nach 20 Stunden; Nachfass-Entwurf über den Sales-Agenten ohne Freigabe; keine
Freigabe und keine externe Aktion (Netz gesperrt, echte Buchungen, Forderungen, Angebote, Kontakte, Wallet und
Einstellungen unverändert); Zeitplan höchstens einmal am Tag; API-Vertrag; bei ROT laufen alle anderen Agenten
weiter. Eine Mutationsprobe (8 absichtlich falsche Regeln) wurde von den Tests vollständig erkannt.

Gesamte Testsammlung am 25.11.2026 (Momentaufnahme – andere Bereiche wurden zeitgleich weiterentwickelt):
**387 Tests, Python 3.13: bestanden; Python 3.9: bestanden (1 übersprungen – QR-Gegenprobe eines anderen Bereichs,
Zusatzpakete fehlen)**. Übersetzen (`compileall`) unter 3.13 und 3.9 fehlerfrei, `ruff` (Fehlerregeln) ohne Befund.

## Echter Lauf (25.11.2026, Entwicklungsumgebung, leerer Datenordner)

Unter Python 3.13 und unter 3.9 je einmal, mit gleichem Ergebnis – **ERFOLGREICH AUSGEFÜHRT**:

1. Internet-Recherche eingeschaltet, echte Suche (Akquise-Agent, 23 s): TED 41 gefunden (39 passend),
   service.bund.de 233 (23 passend), Vergabemarktplatz NRW 11 (0 passend); keine Quelle ausgefallen.
   285 Ausschreibungen gespeichert, 62 passend (≥ 60 Punkte), **43 Geldchancen** (Frist ≥ heute + 3, Region,
   ohne Doppelte).
2. Überlebensplan: **GELB – „Kosten nicht erfasst“** (es waren bewusst keine festen Kosten eingetragen; Einnahmen
   0,00 €, Saldo unbekannt, Reichweite unbekannt). Top-Chance: 100 Punkte, Frist 10.12.2026.
3. Der Orchestrator hat die 3 Folgeaufgaben abgearbeitet: **3 echte Bewerbungs-Mappen** für die 3 besten
   Ausschreibungen (je ca. 8.000 Zeichen, ohne Skript), Status dort jetzt „vorbereitet“. Suche nicht erneut
   angestoßen („heute schon gesucht“), 40 weitere Chancen warten (Tagesgrenze GELB: 3).
4. Zweiter Plan am selben Tag: **0 neue Folgeaufgaben**; der Zeitplan legte keinen weiteren Plan an.
5. **0 Freigaben angefragt, 0 echte Buchungen**, 6 von 6 Aufgaben abgeschlossen, 0 fehlgeschlagen.
6. Die Plan-Seite im Browser (Chromium) auf iPhone-Breite 390 px und Desktop 1280 px: kein waagerechtes Scrollen,
   keine Fehler.

## Grenzen und offene Punkte (ehrlich)

- **Feste Kosten**: Ohne eure Einträge bleibt die Ampel GELB. Eure echten Kosten sind **nicht** erfasst.
- **Saldo ≠ Kontostand**: AUTONOMOUS kennt nur die eingetragenen Buchungen.
- Region bei neuen Funden nur über PLZ-Bereiche bzw. die Bewertung; Ausschreibungen ohne Ortsangabe gelten als
  „in den Unterlagen prüfen“ und bleiben drin.
- Zuordnung „angenommenes Angebot ↔ Forderung“ über Nummer/ID oder gleichen Firmennamen – bei abweichendem
  Kundennamen bitte die Angebotsnummer in die Forderung schreiben.
- Einbindung in Server und Oberfläche sowie ein Lauf über den laufenden Server: GEPLANT / NICHT VERIFIZIERT.
- Auf dem Mac: NICHT VERIFIZIERT.
