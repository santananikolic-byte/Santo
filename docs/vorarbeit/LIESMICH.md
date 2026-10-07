# Vorarbeit für die Video-Funktionen

Hier liegt, was vor dem Bau recherchiert und ausprobiert wurde: Berichte, der
Anzeige-Vertrag, die Pläne der sieben Pakete (P1 Bühne bis P7 Start), die Kritik
an diesen Plänen und kleine Prototypen.

**Das ist nicht Teil von Jarvis.** Nichts davon steht in `src/`, nichts davon
kommt in `jarvis.py`, und `build_single.py` liest diesen Ordner nicht. Die
Prototypen sind Wegwerfcode zum Nachlesen, keine Bibliotheken zum Importieren.

## Was wo liegt

| Pfad | Inhalt |
|------|--------|
| `bau/anzeige_vertrag.md` | Anzeige-Vertrag v1: Kanäle, Ansichten, Routen, Diskretmodus |
| `bau/paket_P1-…` bis `bau/paket_P7-…` | die Pläne der sieben Pakete samt Prüfungen |
| `bau/kritik.md` | Prüfbericht zu den Plänen - was vor dem Bau zu ändern war |
| `bau/bericht_*.md` | Rechercheberichte: Daten, Karte, Sicht, Stimme, Telefon |
| `bau/plan_rahmen.json` | der Rahmenplan als Daten |
| `rezept/telefonagent_rezept.py` | Telefonagent über Vapi, nur ausgehende Verbindungen, WebSocket-Leser für Retell |
| `health_parse.py`, `gen_health.py` | Apple-Health-Export lesen; Testexport erzeugen |
| `parse_news.py`, `yahoo_test.py` | Nachrichtenquellen und Kurse ausprobiert |
| `vision_prototyp/` | Handerkennung, Daumen-Geste, Handruhe-Simulation, Pegel aus WAV |

Die Pläne nennen diese Dateien noch mit ihrem alten Ort im Arbeitsordner der
Recherche (`/tmp/claude-0/…/scratchpad/…`). Der Teil nach `scratchpad/` ist der
Pfad hier: aus `…/scratchpad/rezept/telefonagent_rezept.py` wird
`docs/vorarbeit/rezept/telefonagent_rezept.py`.

## Was der Kern schon anders festgelegt hat

Der erste Bauschritt (Gerüst) hat einige Punkte aus `bau/kritik.md` bereits
umgesetzt. Wo Plan und Code sich widersprechen, gilt der Code:

- Die Kanäle heißen `ANZEIGE_KANAELE`, die Ansichten `ANZEIGE_MODI`
  (`src/modules/anzeige.py`). `warten()` misst mit der Monotonuhr,
  `zeigen(..., dauer_s=0)` heißt "kein Ablauf".
- Der Diskretmodus filtert auch `sicht` und `hochfahren`.
- `FREIGABE_ANGABEN` enthält kleine Funktionen statt einer Vorlagensprache,
  dazu gibt es `FREIGABE_AUFLOESEN` für Kennungen (`src/modules/freigabe.py`).
- Werkzeuge schreiben über `Werkzeuge.zeigen` und `Werkzeuge.melden`; beide tun
  im Hintergrund nichts.
- Meldungen ins Gespräch: `JarvisAgent.meldung_vormerken` statt
  `meldung_einbringen` - eingefügt wird erst am Anfang der nächsten Frage.
- Die Seite `/sehen` gehört zu P5, nicht zu P1.
- Alle neuen Module stehen schon in der Bauliste; in den gemeinsamen Dateien
  hat jedes Paket seine Marken `# [Px Name] Anfang` / `# [Px Name] Ende`.
