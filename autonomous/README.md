# AUTONOMOUS – Anleitung

Ein lokales Unternehmenssystem mit Agenten, Aufgaben, Freigaben, Simulations-Wallet und echten Finanzen.
Es läuft auf dem eigenen Mac, **ohne Installation von Zusatzpaketen** (nur Python 3.9 oder neuer) und **ohne
kostenpflichtige Dienste**.

## Auf den Mac holen (einmalig)

**Am einfachsten – eine Zeile im Terminal** (Programme → Dienstprogramme → Terminal), auch für jede Aktualisierung:

```
curl -fsSL https://raw.githubusercontent.com/santananikolic-byte/Santo/claude/elegant-meitner-ho9kqz/autonomous-einrichten.sh | bash
```

Sie prüft Python, lädt AUTONOMOUS nach `~/AUTONOMOUS`, behält bei einer Aktualisierung eure Daten, richtet den
Dauerbetrieb ein (siehe unten), legt drei Symbole auf den Schreibtisch und öffnet die Oberfläche. Kein sudo,
nichts Bezahltes.

Oder von Hand:

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

### Dauerbetrieb: der Mac als eigener Server

Mit der Einrichtungszeile läuft AUTONOMOUS auf dem Mac wie ein eigener Server: Es startet bei jeder Anmeldung von
selbst und nach einem Absturz neu – ohne offenes Fenster. Dafür legt die Einrichtung eine kleine Datei für macOS an
(`~/Library/LaunchAgents/de.autonomous.server.plist`, nur für euren Benutzer, kein sudo). Meldungen landen in
`autonomous/daten/server.log`.

| Symbol auf dem Schreibtisch | Was passiert |
|---|---|
| **AUTONOMOUS starten** | startet AUTONOMOUS (läuft es schon: öffnet nur den Browser) |
| **AUTONOMOUS stoppen** | beendet AUTONOMOUS sauber. Beim nächsten Anmelden startet es wieder von selbst. |
| **AUTONOMOUS Autostart aus** | beendet AUTONOMOUS und schaltet den Dauerbetrieb ganz ab. Wieder an: Einrichtungszeile erneut ausführen. |

Gut zu wissen:
- Der Mac muss eingeschaltet und angemeldet sein. Im Ruhezustand (MacBook zugeklappt) ist AUTONOMOUS in der Regel nicht erreichbar.
- macOS meldet eventuell „Hintergrundobjekt hinzugefügt“ (Absender: python3). Das ist AUTONOMOUS. Abschalten ginge
  auch unter Systemeinstellungen → Allgemein → Anmeldeobjekte.
- Den Ordner `~/AUTONOMOUS` bitte nicht in „Schreibtisch“, „Dokumente“ oder „Downloads“ verschieben. Auf diese
  Ordner darf ein Hintergrunddienst unter macOS nur mit extra Erlaubnis zugreifen. Nach einem Umzug: Einrichtungszeile
  erneut ausführen.
- Stand: Die Skripte sind in der Entwicklungsumgebung mit einem **nachgebauten** launchctl geprüft (Linux). Ob macOS
  den Dienst genauso startet und nach einem Absturz neu startet: auf einem echten Mac **noch nicht verifiziert**.

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

## Auf dem iPhone benutzen

Standardmäßig ist AUTONOMOUS nur auf dem Mac selbst erreichbar. Fürs iPhone im eigenen WLAN:

1. iPhone und Mac ins **selbe WLAN**. AUTONOMOUS läuft auf dem Mac.
2. Am Mac: **Einstellungen → iPhone verbinden** → „Zugriff aus dem eigenen WLAN erlauben“ anhaken →
   **iPhone-Zugriff speichern**. Fragt der Mac, ob „python3“ eingehende Verbindungen annehmen darf: **Erlauben**.
3. Den **QR-Code** mit der iPhone-Kamera scannen und den Link öffnen.
4. In Safari auf das Teilen-Symbol tippen → **Zum Home-Bildschirm**. Ab dann startet AUTONOMOUS dort wie eine App.

Wichtig:
- Der Link ist wie ein Schlüssel: geheim halten, nicht weiterschicken.
- Die Verbindung im WLAN ist **unverschlüsselt** (http). Nur im eigenen WLAN nutzen, nie in fremden oder öffentlichen
  Netzen (Café, Hotel).
- Ausschalten: Haken weg → speichern. Dann kommt über das WLAN sofort niemand mehr hinein.
- Bekommt der Mac eine neue Adresse (z. B. nach einem Neustart des Routers): den neuen QR-Code scannen.

Stand: In der Entwicklungsumgebung echt geprüft. Die Safari-Engine (WebKit 26.6) in iPhone-13-Emulation öffnete den
Link über die Netzwerkadresse (nicht 127.0.0.1). Der QR-Code wurde aus der Oberfläche fotografiert und mit einem
unabhängigen Leser dekodiert. Eine Einstellung wurde gespeichert, eine fremde Herkunft abgelehnt (403), und nach dem
Ausschalten war die Adresse nicht mehr erreichbar. Mit echtem iPhone und echtem Mac: **noch nicht verifiziert**.

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
python3 autonomous/tests/iphone_pruefung.py   # iPhone im WLAN mit Safari-Engine und QR-Gegenprobe (nur für Entwickler:
                                              # Node.js, Playwright mit WebKit, zxing-cpp und Pillow)
```
