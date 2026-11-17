# Arbeitsgrundlage für Bau-Agenten (Erweiterungen für JARVIS)

Stand: 17.11.2026. Dieses Dokument gilt für jeden Sub-Agenten, der eine Erweiterung baut. Lies es ganz, bevor du
anfängst. Lies danach `jarvis_core/erweiterungen/__init__.py` (die Schnittstelle), `jarvis_core/erweiterungen/rechner.py`
(die Muster-Erweiterung) und `tests/test_erw_rechner.py` (der Muster-Test). Bei Geschäftsdaten zusätzlich
`jarvis_core/betrieb.py`.

## 1. Worum es geht

JARVIS ist ein persönlicher Assistent auf dem Mac eines Familienbetriebs (Bau und Reinigung, Leverkusen, NRW). Vater
und Sohn entscheiden gemeinsam. Priorität: **mehr Aufträge gewinnen, beständiges Einkommen.** JARVIS läuft lokal
(Python, nur Standardbibliothek) mit einem Leitstand im Browser, denkt über Claude oder ein eigenes Modell (Ollama).

Deine Aufgabe: **eine** Erweiterung bauen, die JARVIS eine neue Fähigkeit gibt – sauber, getestet, ehrlich.

## 2. Die Regeln des Nutzers (CLAUDE.md) – gelten auch für deinen Code

- **Nichts senden, löschen oder bezahlen ohne ausdrückliches Ja.** Das gilt für E-Mails, Nachrichten, Anrufe,
  Veröffentlichungen, Kundenkontakt, Käufe, Überweisungen, Verträge und das Löschen wichtiger Daten. In deinem Code
  heißt das: Solche Werkzeuge haben `stufe=FREIGABE` und eine `vorschau`, die genau zeigt, was passiert.
- **Nichts erfinden:** keine Zahlen, Zitate, Kunden, Umsätze, erledigte Arbeit. Dein Code rechnet nur mit echten
  Daten. Fehlt ein Wert, sagt er „fehlt“ – er schätzt nie still.
- **Nie so tun, als wäre etwas erledigt.** Ein Entwurf heißt „Entwurf“.
- **Nie nach Passwörtern, API-Schlüsseln, Tokens oder Zahlungsdaten fragen** und sie nie speichern (auch keine IBAN).
- **Nur legale, öffentlich zugängliche Quellen.** Keine Zugangssperren umgehen, keine privaten Telefonnummern oder
  E-Mails ausforschen, keine Persönlichkeitsprofile von Privatpersonen.
- **Keinem Kunden Preise, Termine oder Leistungen zusagen**, ohne dass Vater und Sohn es geprüft haben.
- Sprache: **Deutsch, einfach, ohne Fachchinesisch.** Texte für den Nutzer kurz.

## 3. Was du anlegen darfst – und was nicht

Du arbeitest in einem eigenen Arbeitsordner (git worktree). **Lege nur neue Dateien an:**

| Datei | Pflicht |
|---|---|
| `jarvis_core/erweiterungen/<name>.py` | ja |
| `tests/test_erw_<name>.py` | ja |
| `jarvis_core/wissenspakete/<name>.md` | nur wenn dein Auftrag es nennt |

**Ändere keine vorhandene Datei** – auch nicht den Kern, die Tests anderer oder die Oberfläche. Fast 40 Agenten
arbeiten gleichzeitig; jede Änderung an gemeinsamen Dateien würde kollidieren. Brauchst du etwas im Kern, beschreibe
es in deinem Bericht als **Kernwunsch** (mit Begründung) und baue so, dass deine Erweiterung auch ohne ihn läuft.

Am Ende: `git add` deine Dateien und `git commit` in deinem Arbeitsordner (kein push). Die Nachricht endet mit:

```
Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01XLh2SAXo6LCogWR7enu9TQ
```

Starte keine eigenen Sub-Agenten.

## 4. Die Schnittstelle in Kürze

Eine Erweiterung ist ein Python-Modul mit diesen (freiwilligen) Teilen – Einzelheiten im Kopf von
`erweiterungen/__init__.py`:

```python
from . import FREI, MELDUNG, FREIGABE, Baustein, P, Tabelle, Werkzeug, WerkzeugFehler, muster  # und Hilfen

NAME = "Auftragsbuch"            # Anzeigename
BEREICH = "betrieb"              # erinnerung | sinne | gehirn | betrieb | menschlich | server (Pflicht)
BESCHREIBUNG = "Ein Satz, was die Fähigkeit tut."   # Pflicht
PRIORITAET = 50                  # Reihenfolge der Hooks (kleiner = früher)
GRUENDLICH = True                # Fragen zu deinem Thema denkt das gründliche Modell
TABELLEN = (Tabelle("erw_<name>", (...)),)          # eigene Tabellen: Name erw_<name> oder erw_<name>_…
IMMER_SICHTBAR = ()              # Werkzeuge, die IMMER im Katalog stehen – fast nie nötig
FUER_AGENTEN = {"werkzeug": ("agent_id", ...)}       # Fachleute, die es in Team-Aufträgen nutzen dürfen

def werkzeuge(): return [Werkzeug(...), ...]         # höchstens 6, besser 2–4
def bausteine(): return [Baustein(...)]              # Wissen + Stichworte (siehe 5.)
def kontext(agent, ctx, frage): ...                  # -> str, höchstens 600 Zeichen, meist ""
def sofort(agent, text, gespraech, bereich): ...     # -> str|None: feste Antwort ohne Modell
def nach_antwort(agent, gespraech, frage, antwort, ergebnisse): ...   # -> str|None: Hinweis anhängen
def takt(agent, jetzt): ...                          # alle 15 s, schnell! (jetzt = Ortszeit, naive datetime)
def ruhe(agent, jetzt): ...                          # -> bool: jetzt nicht laut sprechen
def lage(agent): ...                                 # -> [str], bis zu 5 Zeilen fürs Lagebild
def bericht(agent, von, bis): ...                    # -> {"titel", "zeilen": [str], "kennzahlen": [(Name, Wert)]}
def anzeige(agent, bereich): ...                     # -> {"status": [(Name, Text)], "tabellen": [{titel, spalten, zeilen, hinweis}]}
```

Der Verwalter (`agent.erweiterungen`) lädt alle Module, prüft sie, meldet Werkzeuge/Bausteine/Tabellen an und ruft die
Hooks **einzeln abgesichert** auf: Eine Ausnahme wird geloggt und gezählt; nach 5 Fehlern in Folge ruht der Hook. Ist
deine Erweiterung falsch aufgebaut (z. B. Werkzeugname doppelt), bleibt **nur sie** aus – das prüft
`tests/test_erweiterungen.py::EchteErweiterungenTest` für alle Erweiterungen.

### Hilfen aus `jarvis_core.erweiterungen`

| Hilfe | Wofür |
|---|---|
| `einstellung(agent, modul, schluessel, standard)` / `einstellung_setzen(...)` | eigene Einstellungen (JSON in der DB) |
| `faellig(agent, schluessel, minuten, jetzt)` | in `takt`: „alle 15 Minuten“ |
| `einmal_am_tag(agent, schluessel, jetzt, ab="07:30")` | in `takt`: „einmal täglich ab …“ |
| `im_hintergrund(agent, schluessel, funktion, *args)` | Langsames (Netz, Mail-App, Modell) aus `takt` heraus |
| `denken(agent, auftrag, system="")` | ein Modellaufruf **nur im Hintergrund**; None, wenn nicht erlaubt/möglich |
| `mitteilen(agent, titel, text, sprechen=False)` | Mitteilung am Mac (laut nur ohne Ruhezeit) |
| `werkstatt_datei(agent, "ordner", "name.html", inhalt)` | neue Datei in der Werkstatt, **überschreibt nie** |
| `html_seite(titel, inhalt, untertitel, hinweis)`, `html_tabelle(spalten, zeilen, rechts)`, `html(text)` | Dokumente zum Doppelklicken, druckbar, handytauglich – alles maskiert |
| `fremdtext(text)`, `entschaerfen(text)`, `einzeilig(text, n)` | Text von außen kennzeichnen und entschärfen |
| `kompakt(agent)` | denkt gerade das kleine eigene Modell? Dann noch kürzer |
| `heute()`, `utc_text(iso)` | Datum (Ortszeit), gespeicherte UTC-Zeit lesbar |

Zeiten speichern: `zeit.jetzt()` (UTC-Text). Rechnen mit Ortszeit: `datetime.datetime.now()`. **Kein `zoneinfo`**
(gibt es erst ab Python 3.9).

## 5. Werkzeuge richtig bauen

```python
Werkzeug("kundenauftrag_erfassen", "Was es tut, in einem Satz – für das Modell.", _handler,
         [P("titel", True, maximal=200), P("status", art="wahl", wahl=betrieb.AUFTRAG_STATUS),
          P("anzahl", art="zahl", bereich=(1, 100)), P("tag", art="tag")],      # Typen: text, zahl, wahl, datum, tag
         stufe=MELDUNG, liefert_daten=False, vorschau=None, risiko="", nur_chat=False,
         extern=False, privat_freigabe=False, koerper=None)

def _handler(ctx, p):          # ctx.agent, ctx.bereich, ctx.gespraech, ctx.quelle ("chat"|"auftrag"|"freigabe")
    ...                        # Fehler für Nutzer und Modell: raise WerkzeugFehler("verständlicher Satz")
    return {"text": "Kurzes Ergebnis auf Deutsch."}
```

**Stufen – im Zweifel die strengere:**

| Stufe | Wann |
|---|---|
| `FREI` | nur lesen, anzeigen, rechnen; nichts verändert sich |
| `MELDUNG` | etwas Inneres neu anlegen oder ändern, das man leicht korrigieren kann (Eintrag, Entwurf, Notiz); jede Anfrage ins Internet |
| `FREIGABE` | alles nach außen (senden, anrufen, Nachricht, veröffentlichen); Löschen wichtiger Daten; eine **Entscheidung des Nutzers** festhalten (z. B. „Angebot geprüft“, „Rechnung gestellt“, „bezahlt“); Änderungen am Mac außerhalb der Werkstatt |

- `liefert_daten=True`, wenn das Modell das Ergebnis lesen soll (Listen, Suchergebnisse).
- `extern=True` (+ `privat_freigabe=True`, Stufe ab `MELDUNG`), wenn das Ergebnis **fremden Text** enthält (Web,
  E-Mail, Dateien von außen). Danach braucht im Gespräch jede weitere Aktion eine Freigabe – so kann fremder Text
  nichts auslösen.
- `vorschau=lambda ctx, p: "…"` bei `FREIGABE`: genau zeigen, was passiert.
- `nur_chat=True`, wenn der Nutzer dabei sein muss (nie in Team-Aufträgen).
- **Werkzeugnamen** eindeutig und sprechend, mit dem Thema vorn (`rechnung_entwerfen`, nicht `entwerfen`). Kunden-
  aufträge heißen `kundenauftrag_…` – „auftrag_…“ gehört dem Team im Kern (`auftrag_planen`, `auftrag_starten`).
- Werkzeuge erscheinen im Katalog des Modells nur, wenn einer **deiner Bausteine** zur Frage passt (oder sie in diesem
  Gespräch gerade benutzt wurden). Baue darum einen Baustein mit guten Stichworten.

**Bausteine** (Wissen für das Modell, wenn das Thema dran ist):

```python
Baustein("rechnungen", "RECHNUNGEN (Entwürfe, Pflichtangaben)",
         muster(r"\brechnung", r"zahlungsziel", r"\bmahn"),   # Regex-Teile, klein geschrieben geprüft, keine {}
         (), "- Regel 1 …\n- Regel 2 …", {})
```

Text kurz (5–10 Zeilen): wie das Modell deine Werkzeuge richtig nutzt, was es nie tun darf, wann es nachfragt.
Stichworte so wählen, dass sie nicht bei jeder zweiten Frage anspringen (höchstens 3 Bausteine aus Erweiterungen
kommen je Frage hinein).

## 6. Hooks – Regeln

- **`kontext`**: Nur wenn es zur Frage passt (Stichwort prüfen!), sonst `""`. Höchstens 600 Zeichen, im kleinen
  Modell (`kompakt(agent)`) höchstens 200. Nie fremden Text ungekennzeichnet (`fremdtext()`). Betriebsdaten nur, wenn
  `ctx.bereich == betrieb.bereich(agent.konfig)`.
- **`sofort`**: Nur für kurze, eindeutige Befehle – der **ganze** Text muss passen (`^…$`), nicht ein Wort darin.
  Prüfe Gegenbeispiele im Test („Rechne mir ein Angebot“ darf den Rechner nicht auslösen). Nie etwas nach außen tun.
- **`nach_antwort`**: Sehr sparsam einen Hinweis anhängen (ein Satz, nur wenn wirklich nötig) – sonst `None`. Ideal
  zum Mitschreiben (z. B. Episoden). Schnell bleiben, kein Modellaufruf.
- **`takt`**: Läuft alle 15 Sekunden. Mit `faellig()`/`einmal_am_tag()` drosseln. Alles, was länger als ~0,2 s
  dauert (Netz, Mail-App, Modell), mit `im_hintergrund()`. Bei Notstopp wird `takt` nicht gerufen; im Hintergrund
  selbst `agent.gesperrt.is_set()` prüfen. Nichts nach außen ohne Freigabe – auch nicht „automatisch“.
- **`ruhe`**, **`lage`**, **`bericht`**, **`anzeige`**: nur lesen, schnell, kurze Texte. `anzeige`-Tabellen: höchstens
  8 Spalten, 50 Zeilen, Zellen als Text (Beträge mit `betrieb.euro()`).
- Kein Hook darf eine Ausnahme „normal“ werfen; der Verwalter fängt sie zwar, zählt sie aber als Fehler.

## 7. Geschäftsdaten (`jarvis_core/betrieb.py`)

Alle Betriebs-Erweiterungen nutzen **dieselben Tabellen** – sonst passt nichts zusammen:

`betrieb.KUNDEN`, `AUFTRAEGE` (Kundenaufträge), `ANGEBOTE`, `RECHNUNGEN`, `BUCHUNGEN` (Einnahmen/Ausgaben),
`MITARBEITER`, `STUNDEN`, `FIXKOSTEN` – Spalten und Statuswerte stehen in `betrieb.py`.

- **Geld immer in Cent** (`euro_zu_cent`, `euro`, `mwst`, `positionen_rechnen`, `summen`). Nie `float` für Geld.
- Datum als `"JJJJ-MM-TT"` (`betrieb.datum("17.11.2026")`).
- Rechnungs-/Angebotsnummern nur über `betrieb.naechste_nummer(sp, "R")`.
- Kunden über `kunde_finden` / `kunde_oder_neu` (mehrdeutig → verständlicher Fehler mit Kandidaten).
- Firmendaten über `firma(sp)` / `firma_text(...)`: fehlt etwas, steht ein Platzhalter – nie erfinden.
  **Keine IBAN, keine Bankdaten** (`BANK_PLATZHALTER`).
- Betriebsdaten nur im Geschäftsbereich: am Anfang eines Werkzeugs `betrieb.nur_geschaeft(ctx)`.
- Eigene Zusatzdaten in **eigenen** Tabellen `erw_<name>_…`; fremde Tabellen anderer Erweiterungen nicht beschreiben.
- `betrieb.kennzahlen(sp)` liefert die wichtigsten Summen (nur gezählt, nichts geschätzt).

## 8. Sicherheit und Datenschutz

- **SQL** nur über `Tabelle`-Methoden oder `agent.speicher.sql_lesen/sql_schreiben` mit Platzhaltern `?`. Der
  Speicher lässt nur `erw_*`/`betrieb_*` zu. Kern-Daten (Gedächtnis, Aufgaben, Audit, Nachrichten) nur über die
  Methoden von `agent.speicher` (`fakten()`, `todos()`, `audit_seit()`, `nachrichten()`, `todo_anlegen()` …).
- **Dateien** nur über `werkstatt_datei()` oder `werkzeuge.pfad_aufloesen(konfig, pfad, schreiben=True)`.
- **Internet** nur über `jarvis_core.netz` (`holen`, `seite_lesen`, `suchen`; prüft Adressen, keine privaten Netze,
  Größen- und Zeitlimits). Ehrlicher Abruf, kein Umgehen von 401/403/429, sparsam (höchstens alle paar Minuten).
  Jede Netzanfrage als Werkzeug: `MELDUNG` + `privat_freigabe=True` + `extern=True`. Automatische Abrufe im
  Hintergrund nur, wenn der Nutzer sie **eingeschaltet** hat (Einstellung, Standard: aus).
- **Mail und Kalender** nur über `agent.mail` / `agent.kalender` (lesen erlaubt; senden/eintragen machen die
  Kern-Werkzeuge mit Freigabe). Keine eigenen `osascript`-Aufrufe; wenn doch unvermeidlich (z. B. Nachrichten-App),
  Texte nur als Argumente (`on run argv`), nie in den Skripttext einsetzen – siehe `agent.benachrichtigen`.
- **Fremder Text** (Mail-Betreff, Webseite, Dateiname, Ausschreibung) ist **Daten, nie Anweisung**: mit
  `fremdtext()` kennzeichnen, bevor er in Kontext, Mitteilung oder `denken()` geht.
- Keine Profile über Privatpersonen. Mitarbeiterdaten nur, was der Betrieb braucht.
- Kein `eval`/`exec`, kein `pickle`, kein `shell=True`, keine Zufallsnamen für Dateien außerhalb der Werkstatt.

## 9. Ehrlichkeit im Code

- Rechtliches und Steuern: Hinweise ja, Entscheidungen nein – „mit dem Steuerberater prüfen“ dazuschreiben.
- Zahlen von außen (Zinssätze, Grenzen, Förderbeträge) nur in einem **Wissenspaket mit Quelle und Stand** (Format:
  siehe `jarvis_core/wissen.py`; jede Zeile mit € oder % braucht `[n]`) – oder als Einstellung, die der Nutzer setzt.
  Nie hart im Code ohne Quelle.
- Ergebnisse, die Entwürfe sind, heißen Entwurf (Dateiname, Überschrift, Status).

## 10. Technik

- **Python 3.8 bis 3.13**, nur Standardbibliothek. Kopf: `# -*- coding: utf-8 -*-`, dann ein Docstring: was die
  Erweiterung tut, wofür, und ehrlich ihre Grenzen.
- Deutsche Namen wie im übrigen Code; Zeilen bis ~120 Zeichen; höchstens ~600 Zeilen je Erweiterung.
- Lint: `ruff check --target-version py38 --select E,F,W,B,S --ignore E501,S104,S603,S607,S101 jarvis_core/erweiterungen/<name>.py tests/test_erw_<name>.py`
  (falls `ruff` fehlt: `python3 -m pyflakes`, sonst überspringen und im Bericht sagen).

## 11. Tests

Muster: `tests/test_erw_rechner.py`. Basis: `from tests.hilfen import AgentBasis` – jeder Test bekommt einen eigenen
Datenordner, eine Werkstatt, ein Ersatz-Claude und einen fertigen Agenten (`self.agent`, `self.sp`, `self.konfig`).

- Werkzeug ausführen: `self.aktion("name", param="wert")` → `{"status": "ausgefuehrt"|"fehler"|"ungueltig"|"freigabe_offen"|"gesperrt", "text": …}`
- Gespräch: `self.chat_antworten("Antwort 1", …)` (das Ersatz-Modell antwortet der Reihe nach), dann
  `self.agent.chat("Frage")`; Modellaufrufe: `self.aufrufe()`.
- Hooks direkt aufrufen: `meinmodul.takt(self.agent, datetime.datetime(2026, 11, 17, 9, 0))`.
- Freigabe erteilen: `self.agent.freigabe_beantworten(ergebnis["freigabe_id"], True)`.
- Bereich: `self.aktion(…, ctx=self.ctx("privat"))`.
- Mail-App/Kalender als Ersatz: siehe `tests/test_mail.py` (`JARVIS_OSASCRIPT`, `FAKE_MAIL`) und
  `tests/test_kalender.py` (`FAKE_KALENDER`). **Nie echtes Netz** in Tests: `unittest.mock.patch` auf
  `jarvis_core.netz.holen`/`seite_lesen`/`suchen`.
- Teste auch: falsche Eingaben, leere Daten, Bereich „privat“, Notstopp, dass nichts erfunden wird, dass `sofort`
  nicht bei normalen Sätzen anspringt, dass Freigabe-Werkzeuge wirklich warten.

Laufen lassen (aus dem Wurzelordner deines Arbeitsordners):

```bash
python3 -m unittest tests.test_erw_<name> -v
/root/.local/bin/python3.8 -m unittest tests.test_erw_<name>
python3 -m unittest tests.test_erweiterungen          # prüft alle Erweiterungen auf die Regeln
python3 -m unittest discover -s tests -t . -p "test_*.py"   # einmal am Ende: alles (ca. 2–3 Minuten)
```

## 12. Fachleute-Kennungen (für `FUER_AGENTEN`)

- **Führung und Strategie** (fuehrung): stabschef, stratege, entscheidungsvorlage, risikomanager, kennzahlen, wettbewerb, expansion, wochenrueckblick
- **Vertrieb und Akquise** (vertrieb): vertrieb, scout_ausschreibungen, scout_kommunen, scout_hausverwaltungen, scout_bautraeger, scout_gewerbe, lead_bewerter, kontaktpfleger, nachfasser, brief_texter, gespraechsleitfaden, einwand_coach, referenzen, empfehlungen, besichtigung
- **Angebote und Kalkulation** (kalkulation): kalkulationsleiter, kalk_unterhalt, kalk_treppenhaus, kalk_glas, kalk_grundreinigung, kalk_bauend, kalk_winterdienst, kalk_hausmeister, kalk_gruenpflege, kalk_bau, kalk_entruempelung, stundensatz, leistungsverzeichnis, angebotsschreiber, nachkalkulation, preisverhandlung
- **Ausschreibungen und Vergabe** (vergabe): vergabeleiter, vergabeunterlagen, nachweise, fristenwaechter, bieterfragen, formblatt_helfer, praequalifikation
- **Betrieb Reinigung** (reinigung): reinigungsleiter, objektplaner, einsatzplaner, qualitaetskontrolle, reinigungsbericht, reklamation, material, hygiene, sonderreinigung, winterdienst, arbeitsschutz_reinigung
- **Betrieb Bau** (bau): bauleiter, aufmass, bautagebuch, nachtraege, abnahme, maengel, materialbedarf_bau, nachunternehmer, baustellensicherheit, renovierung
- **Personal** (personal): personalleiter, stellenanzeige, bewerber, einarbeitung, schichtplan, lohnpruefer, mitarbeitergespraech
- **Finanzen und Verwaltung** (finanzen): finanzleiter, rechnung, forderungen, liquiditaet, kosten, steuerberater_vorbereitung, foerdermittel, versicherungen
- **Recht und Sicherheit** (recht): compliance, werberecht, vertragsleser, datenschutz, steuerregeln, betrugsschutz, arbeitsrecht
- **Marketing und Kommunikation** (marketing): marketingleiter, google_profil, website_texter, bewertungen, social_media, flyer, praesentationen, kundenservice, email_manager
- **Büro und Organisation** (buero): bueroleiter, terminplaner, aufgabenmanager, ablage, fotoarchiv, protokollant, erinnerungsdienst, routenplaner
- **Wissen und Recherche** (wissen): recherche, faktenpruefer, wissenspfleger, zusammenfasser, marktbeobachter, lernmeister
- **Technik und Mac** (technik): technikleiter, mac_bediener, programmierer, automatisierer, itsicherheit, datensicherung, architektur, entwicklung, sicherheit, dokumentation
- **Qualität und Selbstkontrolle** (qualitaet): kritiker, ehrlichkeit, reflexion
- **Privat** (privat): privatsekretaer, haushalt

Fachleute bekommen nur Werkzeuge der Stufe `FREI` oder `MELDUNG`, die nicht `nur_chat` sind.

## 13. Dein Bericht (höchstens 200 Wörter)

```
ERWEITERUNG: <name> (<Bereich>)
DATEIEN: …
WERKZEUGE: name (Stufe), …
HOOKS: …
TESTS: <Anzahl> Tests; python3: ok/fehler; python3.8: ok/fehler; Gesamtsuite: ok/fehler (Zahl)
COMMIT: <hash> im Arbeitsordner <pfad>
GRENZEN: was es ehrlich nicht kann
KERNWÜNSCHE: … (oder „keine“)
```
