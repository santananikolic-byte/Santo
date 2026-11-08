# Überlebens-Agent

Ein KI-Agent mit 10 € Startbudget. Jede Stunde kostet 1 €. Er zahlt dir Miete,
darf sich kopieren und muss sich selbst ein Geschäft ausdenken. Fällt sein Geld
auf 0, ist er tot.

## Kurz: was geht, was nicht

| | Stand |
|---|---|
| Simulation mit Spielgeld (Mac und Handy) | **läuft, geprüft** |
| Echt-Modus: Claude denkt sich das Geschäft aus | **gebaut, getestet mit Ersatz-Claude**, mit echtem Claude noch nicht ausprobiert |
| Agent bewegt selbst echtes Geld | **gibt es absichtlich nicht** |
| Agent geht selbst online, schreibt Kunden an | **gibt es absichtlich nicht** – er schlägt vor, du entscheidest und machst es selbst |

Warum nicht ganz selbstständig? Deine Regel: *Nichts senden, löschen oder
bezahlen ohne mein ausdrückliches Ja.* Außerdem kann eine KI rechtlich kein
Geld besitzen. Das Geld ist deins, und du haftest für alles, was in deinem
Namen passiert (Gewerbe, Steuern, Verträge).

## So öffnest du es

- **Handy oder Mac, ohne alles:** `Ueberlebens-Agent.html` doppelklicken bzw.
  antippen (aufs Handy z. B. per AirDrop). Das ist nur die Simulation.
- **Mac, mit Menü:** `Ueberlebens-Agent.command` doppelklicken. Braucht Python 3.
  Öffnet macOS die Datei nicht: Rechtsklick → Öffnen → Öffnen.

## Die Regeln

Von dir festgelegt:
- Start 10 €. Jede Stunde (= ein Schritt) kostet 1 € – auch Warten.
- Bei 0 € tot. Für immer.
- Miete an dich. Kopien bekommen 10 € vom Elternteil und dieselben Regeln.

Von Claude angenommen (in `ueberleben/regeln.py` änderbar):
- Miete 1 € pro Tag und Agent, dazu 20 % jeder Einnahme an dich.
- Kopieren nur, wenn danach noch 5 € Reserve bleiben.
- Notbremse: höchstens 10 lebende Agenten, höchstens 5 Generationen.
- Ein Konto geht nie ins Minus. Reicht das Geld nicht, stirbt der Agent.
- Ist Claude nicht erreichbar, wird die Stunde nicht berechnet.

## Was die Simulation zeigt

1000 Leben mit Standardregeln. Der Markt ist **ausgedacht**: Preise und
Verkaufschancen sind Spielwerte, keine Marktdaten.

- In etwa **3 von 4 Leben** verkauft der Agent kein einziges Mal.
- Der erste Agent lebt im Mittel **10 Stunden**. Genau so lange reichen 10 €.
- Für dich typisch (Median): **0 €**. Der Schnitt ist höher, aber nur wegen
  weniger Glückstreffer.

**Ehrliche Einschätzung:** 10 € für 10 Stunden sind zu knapp, um ein echtes
Online-Geschäft aufzubauen. Ein Kunde braucht meist Tage, bis er zahlt.
Alternativen, die mehr Sinn ergeben:
- mehr Startgeld,
- Kosten pro Tag statt pro Stunde,
- den Agenten an echten Aufgaben für eure Firma arbeiten lassen
  (Angebote, Akquise-Texte).

## Echt-Modus (Terminal)

```
python3 -m ueberleben echt start          # anlegen
python3 -m ueberleben echt runde          # eine Stunde: jeder Agent fragt Claude
python3 -m ueberleben echt freigaben      # was auf dein Ja wartet
python3 -m ueberleben echt ja 1           # zeigt genau, was passiert, und fragt nochmal
python3 -m ueberleben echt nein 1
python3 -m ueberleben echt einnahme A1 12,50 "Kunde X, Rechnung 7"   # nur echtes, eingegangenes Geld
python3 -m ueberleben echt status
```

Schutz im Echt-Modus:
- **Claude ohne Werkzeuge.** Claude läuft ohne Werkzeuge, ohne verbundene Dienste
  wie dein Postfach, ohne Einstellungen und in einem leeren Ordner. Es kann nur
  antworten, nichts lesen, senden oder ändern. Abgerechnet wird über dein Abo,
  nicht über einen API-Schlüssel.
- **Nur Anträge nach außen.** Verkaufen, Kopieren und Auszahlen sind nur Anträge.
  Pro Agent ist immer nur einer offen.
- **Kein Zugriff auf Geld.** Das Programm kann kein Konto sehen und nichts
  überweisen. Alle Beträge sind Buchwerte.
- **Warnung vor Zahlungen.** Bei Freigaben mit Zahlungen, Links oder IBAN steht
  eine Warnung dabei. Der Agent darf dich nie zum Bezahlen auffordern.
- **Ein Fenster zur Zeit.** Läuft ein Befehl in einem anderen Fenster, wird der
  zweite abgewiesen. So geht kein Ja verloren.
- **Daten bleiben bei dir.** Alles liegt lokal in `ueberleben_daten/` und wird
  nicht hochgeladen.

Jede Runde fragt Claude einmal pro lebendem Agenten. Das verbraucht Abo-Nutzung.

## Prüfung

- `python3 -m unittest tests.test_ueberleben` → **127 Tests, alle bestanden**.
- Der HTML-Simulator wurde im Browser geprüft (Handybreite, Hell und Dunkel,
  Buchhaltung über 300 Leben).
- Eine unabhängige Prüfung fand 2 kritische und 6 mittlere Fehler. Sie sind
  alle behoben, und für jeden gibt es einen Test.
