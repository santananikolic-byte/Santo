# AUTONOMOUS – Anleitung

Ein lokales Unternehmenssystem mit Agenten, Aufgaben, Freigaben, Simulations-Wallet und echten Finanzen.
Es läuft auf dem eigenen Mac, **ohne Installation von Zusatzpaketen** (nur Python 3) und **ohne
kostenpflichtige Dienste**.

## Starten und Stoppen

1. Doppelklick auf **`AUTONOMOUS-starten.command`** (im Hauptordner).
   - Beim ersten Mal sperrt macOS die Datei eventuell. Dann Rechtsklick → *Öffnen* → *Öffnen*.
   - Der Browser öffnet sich mit der Oberfläche. Der Link enthält einen geheimen Zugangsschlüssel. Danach merkt sich der Browser den Zugang.
2. Beenden: Doppelklick auf **`AUTONOMOUS-stoppen.command`**. Aufgaben und Buchungen bleiben gespeichert.

Kommandozeile (im Hauptordner):

```
python3 -m autonomous start        # Vordergrund, Strg+C beendet
python3 -m autonomous link         # Startlink anzeigen
python3 -m autonomous status       # läuft es?
python3 -m autonomous sicherung    # Sicherung jetzt
python3 -m autonomous sicherungen  # Sicherungen auflisten
python3 -m autonomous wiederherstellen autonomous-JJJJMMTT-....db   # nur bei gestopptem System
python3 -m autonomous export       # wichtigste Daten als JSON
python3 -m autonomous test         # alle automatischen Tests
```

### Auf dem iPhone (optional, nur im eigenen WLAN)

Standardmäßig ist AUTONOMOUS nur auf dem Mac selbst erreichbar. Fürs iPhone im Heimnetz:

```
AUTONOMOUS_HOST=0.0.0.0 AUTONOMOUS_ERLAUBTE_HOSTS=DEIN-MAC.local python3 -m autonomous start
```

Dann auf dem iPhone `http://DEIN-MAC.local:8770/?k=SCHLÜSSEL` öffnen. Den Schlüssel zeigt `python3 -m autonomous link`.
**Achtung:** Die Verbindung ist unverschlüsselt. Nur im eigenen WLAN nutzen, nie in fremden Netzen.

## Was wo liegt

| Ordner/Datei | Inhalt |
|---|---|
| `autonomous/daten/` | Datenbank, Zugangsschlüssel, Sicherungen, Exporte, erzeugte Produkte. **Bleibt lokal, nie in Git.** |
| `autonomous/ui/` | Weboberfläche |
| `autonomous/agenten/` | CEO, Research, Product, Sales, Finance, Learning |
| `autonomous/berechtigungen.py` | Supervisor: Risikoklassen, Freigaben, Sperren |
| `autonomous/wallet.py` | Simulations-Wallet (15,00 € SIMULATION) |
| `autonomous/finanzen.py` | Reale Finanzen (nur geprüfte Zahlungen) |
| `autonomous/docs/` | `MARKTANALYSE.md` (Empfehlung erstes Angebot, Quellen), `BEDROHUNGSMODELL.md`, `PHASENBERICHT.md` (Stand, Tests, nächste Schritte) |
| `autonomous/beispiele/` | Beispiele zum Ansehen per Doppelklick (fiktive Musterfirma): Google-Profil-Paket (Entwurf, Prüfliste, Übergabe-Anleitung), Verkaufsseite, Kunden-Webseite |

## Die wichtigsten Regeln im System

- **Nichts geht nach außen ohne dein Ja.** Ein Ja gilt für genau eine Aktion. Ein Nein ist endgültig für genau diese Aktion.
- **Kostenpflichtiges ist gesperrt.** Freischalten nur in den Einstellungen, und auch dann braucht jede Aktion zusätzlich dein Ja.
- **Wallet = Spielgeld.** Es dient nur zum Üben und Planen. Ein Stand von null schaltet nichts ab.
- **Einnahme = nur echtes, geprüftes Geld.** Dafür braucht es einen Zahlungsnachweis (zum Beispiel einen Kontoauszug) und den Namen, wer ihn geprüft hat. Eine Rechnung ist noch keine Einnahme.
- **Agenten erfinden nichts.** Pläne und Zahlen kommen aus der Datenbank. Empfehlungen werden als *Vorschlag* gespeichert. Entscheidungen trefft ihr.

## Das erste Angebot (Vorschlag – ihr entscheidet)

Die Marktanalyse (`docs/MARKTANALYSE.md`) empfiehlt ein **Google-Profil-Paket** für kleine Handwerks-, Bau- und
Reinigungsbetriebe in NRW: Profil prüfen, anlegen oder übernehmen, vollständig ausfüllen, echte Fotos, Übergabe mit
Kurzanleitung. Der Betrieb bleibt Inhaber. Webseiten sind Stufe 2.

In AUTONOMOUS: Bereich **Produkte → Google-Profil-Paket erstellen**. Es entstehen drei Unterlagen für den Termin
vor Ort. **AUTONOMOUS trägt selbst nichts bei Google ein.**

Preis: Die Recherche schlägt 199–349 € netto vor, die Anbieterpreise dazu sind aber **nicht bestätigt** (siehe
Nachprüfung in der Marktanalyse). Erst selbst prüfen, dann festlegen. Auf Verkaufsseite und Angebot steht nur ein
Preis, den ihr eingebt.

## Prüfen, ob alles funktioniert

```
python3 -m autonomous test               # 105 automatische Tests
python3 autonomous/tests/ui_server.py    # Oberfläche im Browser (braucht Node.js + Playwright, nur für Entwickler)
```
