# AUTONOMOUS – Anleitung

Ein lokales Unternehmenssystem mit Agenten, Aufgaben, Freigaben, Simulations-Wallet und echten Finanzen.
Es läuft auf dem eigenen Mac, **ohne Installation von Zusatzpaketen** (nur Python 3.9 oder neuer) und **ohne
kostenpflichtige Dienste**.

## Auf den Mac holen (einmalig)

1. Auf GitHub das Repository `santananikolic-byte/Santo` öffnen, oben den Branch **`claude/elegant-meitner-ho9kqz`**
   wählen, dann **Code → Download ZIP** und die ZIP-Datei per Doppelklick entpacken.
2. Python: Auf dem Mac wird Python 3.9 oder neuer gebraucht. Fehlt es, meldet das Startskript genau das – dann im
   Terminal einmal `xcode-select --install` ausführen (Apple-Entwicklerwerkzeuge, kostenlos).
3. Meldet macOS beim Doppelklick „keine Berechtigung“: im Terminal einmal
   `chmod +x ~/Downloads/Santo-*/AUTONOMOUS-*.command` eingeben (Pfad ggf. anpassen).

Geprüft in der Entwicklungsumgebung mit **Python 3.9** (wie auf dem Mac vorinstalliert) und Python 3.13: alle
automatischen Tests, Oberfläche und ein echter Suchlauf. Auf einem echten Mac: **noch nicht verifiziert**.

## Starten und Stoppen

1. Doppelklick auf **`AUTONOMOUS-starten.command`** (im Hauptordner).
   - Beim ersten Mal sperrt macOS die Datei eventuell. Dann Rechtsklick → *Öffnen* → *Öffnen*.
   - Der Browser öffnet sich mit der Oberfläche. Der Link enthält einen geheimen Zugangsschlüssel. Danach merkt sich der Browser den Zugang.
   - Das Skript prüft vorher: Ist Python eingerichtet und neu genug? Ist der Port frei? Bei einem Problem steht
     dort in einem Satz, was zu tun ist.
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

## KI-Modell (optional, lokal auf dem Mac, kostenlos)

AUTONOMOUS läuft ohne KI vollständig. Mit einem **lokalen** Modell schreiben die Agenten zusätzlich Zusammenfassungen
(z. B. im Marktbericht). Es wird **kein** externer KI-Dienst genutzt – nichts geht an Anthropic, OpenAI oder andere.

1. Ollama von **ollama.com** herunterladen (Download für macOS) und wie ein normales Programm installieren.
2. Im Terminal ein Modell laden, z. B. `ollama pull gemma3:4b` (Mac mit 8 GB Arbeitsspeicher; mit 16 GB oder mehr
   geht auch ein größeres Modell). Das sind einige Gigabyte Download.
3. In AUTONOMOUS: **Einstellungen → KI-Modell** → Anbieter „ollama“, Modellname wie geladen → **Modell testen**.

Wichtig: Jede KI-Ausgabe ist als **„KI-Entwurf – ungeprüft“** gekennzeichnet. Ein kleines Modell macht Fehler – Zahlen
und Fakten stehen deshalb immer gezählt und mit Quelle daneben, die KI-Zusammenfassung ist nur ein Zusatz. Die KI kann
keine Aktion auslösen, nichts versenden und keine Rechte ändern.

Echt geprüft in der Entwicklungsumgebung (21.11.2026) mit **Ollama 0.40.17 und dem Modell gemma3:1b**: Status,
Probeaufruf und ein Marktbericht mit KI-Zusammenfassung über den laufenden Server. Auf dem Mac: noch nicht verifiziert.

## Prüfen, ob alles funktioniert

```
python3 -m autonomous test               # alle automatischen Tests (Stand und Zahlen: docs/PHASENBERICHT.md)
python3 autonomous/tests/ui_server.py    # Oberfläche im Browser (braucht Node.js + Playwright, nur für Entwickler)
```
