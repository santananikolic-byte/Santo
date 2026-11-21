# AUTONOMOUS – Konzept Zahlungsanbieter (PDF Abschnitt 7)

Stand: 21.11.2026 · Status: **GEPLANT (nur Konzept)**. Es gibt **keinen** Code, **keine** Anbindung, **keine**
Zugangsdaten und **keine** Geldbewegung. Dieses Dokument beschreibt nur, wie eine spätere Anbindung ablaufen soll.

Auftrag (PDF, Abschnitt 7): „Zahlungsanbieter zunächst nur konzeptionell vorbereiten; keine echte Geldbewegung in
Version 1. Wenn PayPal später angebunden wird, zuerst Sandbox/Testumgebung und möglichst lesende Funktionen
verwenden. Echte Zahlungen müssen durch verlässliche Anbieterbestätigung verifiziert werden.“

## 1. Ziel

Zahlungseingänge von Kunden sollen später **automatisch erkannt** und einer offenen Forderung **vorgeschlagen**
werden, damit der Eigentümer sie schneller und fehlerfrei als echte Einnahme bestätigen kann.
Gebucht wird weiterhin nur durch den Eigentümer.

## 2. Was Version 1 NICHT tut

- keine Verbindung zu PayPal, einer Bank oder einem anderen Zahlungsdienst
- keine Zugangsdaten, API-Schlüssel oder Tokens im System
- keine Auszahlungen, Überweisungen, Erstattungen, Bestellungen
- keine automatische Buchung von Einnahmen
- kein Abruf von Kontoständen

Heute (Stufe 0, **IMPLEMENTIERT, ERFOLGREICH GETESTET**): Der Eigentümer trägt eine eingegangene Zahlung von Hand ein.
Die Datenbank nimmt eine Einnahme nur mit **Zahlungsnachweis** (z. B. Kontoauszug-Referenz) **und** dem Namen der
prüfenden Person an (`finanzen.einnahme(...)`, `finanzen.forderung_bezahlt(...)`; nur Akteur „eigentuemer“;
Tests in `tests/test_finanzen.py`).

## 3. Stufenplan

| Stufe | Inhalt | Darf | Darf nicht |
|---|---|---|---|
| 0 – heute | Zahlungen von Hand mit Nachweis erfassen | Eigentümer bucht | alles Automatische |
| 1 – Sandbox, lesend | Testumgebung des Anbieters, nur Testdaten | Testzahlungen lesen, Zuordnung zu Test-Forderungen vorschlagen | echte Konten, echtes Geld, Schreibzugriffe |
| 2 – echtes Konto, nur lesend | Zahlungseingänge abrufen | Eingänge lesen, Zuordnung **vorschlagen** | buchen ohne Bestätigung, Geld bewegen |
| 3 – Auszahlungen | – | – | **Nie automatisch.** Falls je gewünscht: nur einzeln, nach ausdrücklicher Freigabe (Aktion `echte_zahlung`, Risikoklasse FREIGABE) |

Jede Stufe beginnt erst nach ausdrücklicher Zustimmung des Eigentümers. Ob und wie ein Anbieter eine Testumgebung
und rein lesende Zugriffsrechte anbietet, ist **vor Anbindung zu prüfen** (nicht geprüft).

## 4. Wie eine Zahlung zur verifizierten Einnahme wird (ab Stufe 2)

1. **Anbieterbestätigung:** Der Zahlungsstatus wird direkt beim Anbieter abgefragt bzw. über eine vom Anbieter
   verifizierbare Benachrichtigung empfangen. **Nicht** als Beleg zählen: E-Mails, Screenshots, Aussagen des Kunden,
   Rechnungen, Angebote, erwartete Zahlungen. Die genaue Schnittstelle ist **vor Anbindung zu prüfen**.
2. **Abgleich mit einer offenen Forderung:** Betrag, Währung und Referenz (z. B. Rechnungsnummer) müssen passen.
   Passt etwas nicht, wird nichts zugeordnet, sondern ein Hinweis angezeigt.
3. **Bestätigung durch den Eigentümer:** Erst sein Ja bucht – über die vorhandene Funktion
   `finanzen.forderung_bezahlt(forderung_id, zahlungsnachweis=<Transaktionskennung des Anbieters>,
   verifiziert_von=<Name>)`. Ein Agent kann das nicht (nur Akteur „eigentuemer“).
4. **Korrekturen** nur per Gegenbuchung (Buchungen sind unveränderbar).

## 5. Sicherheit und Geheimnisse

- Zugangsdaten **nie** im Quellcode, in Git, in Protokollen oder in normalen Konfigurationsdateien.
- Ablage später nur in einem geschützten Speicher des Betriebssystems (auf dem Mac: Schlüsselbund) oder in einer
  Datei außerhalb des Projekts, nur für den Besitzer lesbar (Rechte 600). Konkrete Umsetzung **vor Anbindung prüfen**.
- Nur die kleinstmöglichen Rechte beim Anbieter anfordern (lesend), soweit der Anbieter das erlaubt.
- Vorhanden und nutzbar: Protokoll schwärzt Passwort-/Token-/Schlüssel-Muster (`protokoll.schwaerzen`), der
  Supervisor lehnt Agentenergebnisse mit vermuteten Geheimnissen ab (`Supervisor.ergebnis_pruefen`).
- Jeder Abruf beim Anbieter wird protokolliert (ohne Geheimnisse); Abrufe nur zu freigegebenen Adressen
  (wie heute beim Auftrags-Radar über `berechtigungen.url_erlaubt`).

## 6. Vor einer Anbindung zu klären (Entscheidung Eigentümer)

- **Kosten:** Anbieter, Zweck, Preis bzw. Gebührenmodell und Alternativen schriftlich zeigen, bevor etwas
  eingerichtet wird (PDF Abschnitt 3). Gebühren sind hier **nicht geprüft**.
- **Steuer:** Behandlung der Einnahmen und Gebühren mit dem Steuerberater klären.
- **Datenschutz:** Welche Kundendaten der Anbieter liefert, wie lange sie gespeichert werden, Hinweis in der
  Datenschutzerklärung.
- **Verbraucherrecht/Impressum**, falls an Privatkunden verkauft wird.
- **Freigabe:** Die Nutzung eines kostenpflichtigen Dienstes ist im System gesperrt (`kostenpflichtig_erlaubt` =
  aus) und zusätzlich je Aktion freigabepflichtig (Aktion `kostenpflichtiger_dienst`).

## 7. Abgrenzung: internes Wallet und reale Finanzen

- **Internes Wallet = SIMULATION** (Tabelle `wallet_buchungen`, Datenbank erzwingt `simulation = 1`). Daten eines
  Zahlungsanbieters fließen **nie** ins Wallet.
- **Reale Finanzen** (Tabelle `real_buchungen`, `simulation = 0`): nur hier landen echte, verifizierte Zahlungen.
- Beide Bereiche werden nie addiert. Der private Kontostand des Eigentümers wird nie als AUTONOMOUS-Guthaben gezeigt.
- Ein Wallet-Stand von null stoppt keine kostenlosen Kernfunktionen; ein nicht freigegebener Zahlungsdienst blockiert
  nur diesen Dienst.
