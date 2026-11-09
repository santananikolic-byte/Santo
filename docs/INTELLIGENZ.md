# Wie JARVIS denkt

Stand: 09.11.2026. Dieses Dokument erklärt in einfachen Worten:

- wie eine KI wie JARVIS funktioniert,
- was eine Intelligenz braucht, um selbstständig zu arbeiten,
- wie das in JARVIS gebaut ist.

## 1. Wie eine KI funktioniert

**Das Gehirn ist ein Sprachmodell: Claude.**
Es hat aus sehr vielen Texten gelernt, wie Sprache, Wissen und Schlussfolgern zusammenhängen. Es bekommt einen Text (Auftrag plus Hintergrund) und schreibt die beste Fortsetzung, Wort für Wort. Gut denkt es vor allem dann, wenn es Schritt für Schritt arbeiten darf.

**Was das Modell allein nicht hat:**

- **kein Gedächtnis:** Jeder Aufruf beginnt bei null.
- **keine Hände:** Es kann nichts tun, nur schreiben.
- **keine Ziele:** Es wartet, bis jemand fragt.
- **keine Selbstkontrolle:** Es merkt nicht von selbst, wenn es sich irrt. Es weiß nicht, was es nicht weiß.
- **kein Lernen:** Nach dem Training lernt es nicht dazu.

Man kann es sich vorstellen wie einen hochbegabten Menschen, der jeden Morgen ohne Erinnerung aufwacht.

**Daraus folgt das Wichtigste:** Die Klugheit eines Assistenten kommt zur Hälfte vom Modell und zur Hälfte von der Organisation drumherum. Das Modell selbst kann ich nicht klüger machen; Opus ist schon das stärkste. Ich kann ihm aber alles geben, was ihm fehlt. So wird aus einem klugen Kopf eine starke Firma.

## 2. Was eine Intelligenz braucht, um selbstständig zu arbeiten

| Baustein | Was er leistet | Wo er in JARVIS steckt |
|---|---|---|
| **Sinne** | Was ist los? | Gespräch, Stimme, E-Mails, Kalender, Dateien, Bildschirm, Internet |
| **Gedächtnis** | Was weiß ich über euch? | Gedächtnis mit Fakten, Kontakten und Aufgaben, bestätigt von euch |
| **Wissen** | Was gilt draußen? | 5 Wissenspakete, jede Zahl mit Quelle und Datum |
| **Ziele und Rhythmus** | Was ist wichtig, wann tue ich etwas? | Ziel „mehr Aufträge“; Routinen wie das Morgenbriefing und den Akquise-Wochenstart |
| **Arbeitsteilung** | Fachleute statt Alleskönner | **127 Fachleute in 15 Abteilungen** (siehe unten) |
| **Planen** | Ein großes Ziel in prüfbare Schritte zerlegen | Der Planer wählt für jeden Schritt den passenden Fachmann |
| **Handeln** | Werkzeuge mit Erlaubnisstufen | Was etwas verändert oder nach außen geht, braucht euer Ja |
| **Prüfen** | Ein zweites Paar Augen | Unabhängiger Prüfer je Schritt, Prüfregeln je Fachmann, Ehrlichkeitsprüfung im Code |
| **Lernen** | Fehler nicht zweimal machen | **Erfahrungsgedächtnis:** Die Kritik des Prüfers wird zur Lehre des Fachmanns |
| **Weisheit** | Grenzen kennen | Wissen von Annahme trennen, Risiko nennen, nachfragen, wenn etwas fehlt |

Ein Kind kann sprechen. Erwachsen wird eine Intelligenz erst durch die anderen Bausteine: Sie plant, teilt Arbeit auf, prüft sich, lernt aus Fehlern und kennt ihre Grenzen. Genau diese Bausteine sind jetzt eingebaut.

## 3. Der Denkkreislauf bei jeder Frage

1. **Verstehen:** Worum geht es, welche Abteilung ist gefragt?
2. **Erinnern:** Gedächtnis, passendes Wissen mit Quelle, Erfahrungen der Fachleute.
3. **Beraten:** Die ein bis zwei passendsten Fachleute bringen ihren Auftrag und ihre Prüfregeln mit. Das kostet keinen zusätzlichen Aufruf. Unter der Antwort steht dann zum Beispiel „Beraten von: Kalkulator Treppenhaus, Kalkulationsleiter“.
4. **Entscheiden:** Eine kleine Frage beantwortet JARVIS selbst. Ein großes Vorhaben gibt er an sein Team. Er plant die Schritte, und ihr startet sie mit einem kurzen **„Ja“**.
5. **Handeln:** Jeder Schritt läuft als **eigener Agent**: ein eigener Modellaufruf, nur die Werkzeuge dieses Fachmanns, sein Wissen und seine Erfahrungen.
6. **Prüfen:** Ein unabhängiger Prüfer bewertet jeden Schritt. Nur Belegtes zählt.
7. **Lernen:** Was der Prüfer bemängelt hat, merkt sich der Fachmann für das nächste Mal. Im Leitstand seht ihr alle Erfahrungen und könnt jede einzeln vergessen lassen.
8. **Initiative:** Am Ende schlägt JARVIS den nächsten Schritt vor. Die Routinen laufen von selbst.

## 4. Die Organisation

| Abteilung | Fachleute | Beispiele |
|---|---|---|
| Führung und Strategie | 8 | Stabschef, Strategieberater, Entscheidungsvorlagen, Risikomanager |
| Vertrieb und Akquise | 15 | Ausschreibungs-Scout, Kommunal-Lotse, Hausverwaltungs-Scout, Brief-Texter |
| Angebote und Kalkulation | 16 | Kalkulator Treppenhaus, Glas, Winterdienst, Stundensatz-Rechner, Angebotsschreiber |
| Ausschreibungen und Vergabe | 7 | Vergabe-Leiter, Vergabeunterlagen-Analyst, Fristen-Wächter, PQ-Lotse |
| Betrieb Reinigung | 11 | Objektplaner, Einsatzplaner, Qualitätskontrolle, Reklamations-Manager |
| Betrieb Bau | 10 | Bauleiter, Aufmaß, Bautagebuch, Nachträge, Abnahme, Mängel |
| Personal | 7 | Personalleiter, Stellenanzeigen, Bewerber-Vorauswahl, Mindestlohn-Prüfer |
| Finanzen und Verwaltung | 8 | Rechnungs-Entwurf, Forderungen, Liquidität, Fördermittel-Scout |
| Recht und Sicherheit | 7 | Werberecht-Prüfer, Vertrags-Leser, Datenschutz, Betrugsschutz |
| Marketing und Kommunikation | 9 | Google-Profil, Website-Texter, Bewertungen, Kundenservice |
| Büro und Organisation | 8 | Terminplaner, Aufgaben, Ablage, Protokollant |
| Wissen und Recherche | 6 | Rechercheur, Faktenprüfer, Wissenspfleger, Lernmeister |
| Technik und Mac | 10 | Technik-Leiter, Mac-Bediener, Programmierer, IT-Sicherheit |
| Qualität und Selbstkontrolle | 3 | Kritiker, Ehrlichkeits-Wächter, Reflexion |
| Privat | 2 | Privatsekretär, Haushalts-Planer |

**Jeder Fachmann hat:**

- einen Auftrag (was er tut, wie und was nicht),
- seine Werkzeuge (nie mehr als nötig),
- sein Wissen,
- 3 bis 4 Prüfregeln,
- Stichworte, bei denen er gefragt wird.

**Keiner darf senden, bezahlen oder Termine eintragen.** Das passiert nur im Gespräch mit euch und nur nach eurem Ja.

## 5. Warum es 127 sind und nicht 500

**Das ist ehrlich gesagt die bessere Wahl.** Ein Agent ist bei JARVIS kein eigenes Gehirn. Er ist eine Rolle für dasselbe Gehirn. Mehr Rollen bringen mehr Abdeckung, aber nicht mehr Intelligenz. Dafür gibt es drei Gründe:

- **Euer Betrieb hat keine 500 verschiedenen Fachgebiete.** Der Rest wären Kopien mit anderem Namen, etwa „Kalkulator Treppenhaus Köln“ und „Kalkulator Treppenhaus Leverkusen“.
- **Je mehr Auswahl, desto schlechter die Zuteilung.** Das ist wie in einer Firma mit 500 Leuten für 3 Aufgaben: Niemand weiß, wer zuständig ist.
- **Jeder Einsatz eines Agenten ist ein Modellaufruf aus eurem Abo.** 500 gleichzeitig würden das Limit in Minuten aufbrauchen.

**Darum ist die Organisation auf Wachstum gebaut.** Taucht eine neue Art Aufgabe auf, die kein Fachmann abdeckt, schlägt JARVIS einen neuen vor. Nach eurem Ja stellt er ihn ein. Möglich sind bis zu 400 eigene, zusammen also über 500. Jeder davon hat dann aber eine echte Aufgabe.

## 6. Was das nicht ist

- **Kein eigenes Bewusstsein.** Die Fachleute sind gut beschriebene Rollen für Claude, keine Menschen.
- **Nicht immer richtig.** Prüfer und Prüfregeln senken Fehler, aber sie schließen sie nicht aus. Deshalb gilt weiter: Nichts geht ohne euer Ja raus, und Zahlen kommen nur mit Quelle.
- **Kein Ersatz für Steuerberater und Anwalt.** Die Fachleute bereiten Gespräche mit ihnen gut vor.
