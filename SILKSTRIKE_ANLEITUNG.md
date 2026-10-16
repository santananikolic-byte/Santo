# SILKSTRIKE – Blutturnier

Dein eigenes Spiel: offene Stadt zum Schwingen und harte 1-gegen-1-Kämpfe mit Exekutionen. Alle Figuren und die Story sind eigene Ideen, nichts ist kopiert.

**Umfang:** 32 Swift-Dateien mit rund 21.700 Zeilen, eigene Story mit 7 Kapiteln, 7 Kämpfer, 6 Arenen, 22 Zwischensequenzen.

---

## Was drin ist

- **Story:** Prolog, 6 Kapitel und Epilog. Kai Ronan alias **Silkstrike** gegen das Blutturnier von Kaiser Malrek. Dazu kommen die Schwarzseide, sein dunkles Spiegelbild Nachtseide, Lena, Saya, Vex, Brutus und Inferna. 22 Zwischensequenzen mit Kamerafahrten, Untertiteln und deutscher Sprachausgabe.
- **Offene Welt Neo-Haven:**
  - Orte: rund 80 Häuserblöcke, Hafen mit Kran, Dom, Gießerei, Park mit einem Riss am Himmel, Labor-Hochhaus und der Blutturm im Finale.
  - Fortbewegung: Netzschwingen mit echter Pendel-Physik, Wandlauf, Netz-Zip.
  - Leben in der Stadt: Kultisten-Gangs, Autoverkehr, Leuchtreklame, Regen und 40 versteckte Blutsiegel.
- **Kampfmodus (1 gegen 1):**
  - Grundlagen: Runden, Timer, Kombos, Würfe, Blocken und Juggles.
  - Angriffe: 2 Spezialangriffe pro Kämpfer, Projektile und der **Brutal-Schlag**, ein Super-Angriff in Zeitlupe.
  - Finale: Am Ende kommt **„VOLLENDE ES!“**, dann die **Exekution**. Jeder Kämpfer hat eine eigene, filmreife Exekution.
  - Gegner: Eine KI mit 4 Schwierigkeitsstufen.
- **Grafik:**
  - Rendert in der vollen Auflösung deines Displays.
  - Effekte: HDR, Bloom, Schatten, Umgebungslicht (SSAO), Bewegungsunschärfe, Tiefenschärfe in Zwischensequenzen.
  - Partikel: Blut, Feuer, Funken, Regen, Asche.
- **Sound:** Effekte, Musik und Ansager werden live erzeugt. Die Dialoge spricht die deutsche Systemstimme.
- **Steuerung:** Touch mit Joystick und Knöpfen. Gamecontroller (PlayStation, Xbox, MFi) und Tastatur werden automatisch erkannt.
- **Einstellungen:** Grafikstufe, Blut an oder aus, Schwierigkeit, Lautstärken, Kamera.

---

## Weg 1 (empfohlen): iPad mit Swift Playgrounds

1. Lade **`Silkstrike.swiftpm.zip`** auf dein iPad.
2. Öffne die Dateien-App und tippe auf die ZIP-Datei. Sie wird entpackt.
3. Tippe auf den Ordner **`Silkstrike`** (Symbol mit dem orangefarbenen Vogel). Er öffnet sich in **Swift Playgrounds**.
4. Tippe oben auf **▶︎ Ausführen**.
5. Für Vollbild tippe oben auf das App-Symbol und wähle „Im Vollbild ausführen“.

Das Spiel bleibt in Playgrounds gespeichert und lässt sich jederzeit wieder starten.

## Weg 2: iPhone oder iPad mit einem Mac und Xcode (echte App auf dem Homescreen)

1. Kopiere `Silkstrike.swiftpm` auf den Mac und öffne den Ordner mit **Xcode** (Doppelklick).
2. Schließe dein iPhone per Kabel an und wähle es oben als Ziel aus.
3. Öffne **Signing & Capabilities** und wähle bei **Team** deine Apple-ID (kostenlos möglich).
4. Drücke **▶︎**. Die App wird auf dein iPhone installiert.
5. Beim ersten Start auf dem iPhone: Einstellungen → Allgemein → VPN & Geräteverwaltung → deiner Apple-ID vertrauen.

Mit einer kostenlosen Apple-ID läuft die App 7 Tage, danach einfach erneut ▶︎ drücken. Mit dem Apple-Entwicklerprogramm (99 €/Jahr) geht es auch per TestFlight ohne Kabel.

## Weg 3: Alles in einer Datei (zum Kopieren)

Die Datei **`Silkstrike_KOMPLETT.swift`** enthält das ganze Spiel.

1. Erstelle in Swift Playgrounds eine **neue App**.
2. Lösche die Vorlagedateien `MyApp.swift` und `ContentView.swift`.
3. Lege eine neue Datei an, zum Beispiel `Spiel.swift`.
4. Kopiere den kompletten Inhalt von `Silkstrike_KOMPLETT.swift` hinein und drücke ▶︎.

Wenn Playgrounds dabei viele Fehler zu „concurrency“ oder „Sendable“ meldet, ist das neue Projekt auf Swift 6 eingestellt. Nimm dann Weg 1: Das fertige Projekt ist auf Swift 5 eingestellt.

---

## Steuerung (Touch)

| Offene Welt | |
|---|---|
| Linker Daumen | Laufen, im Sprung lenken |
| Rechte Bildschirmhälfte wischen | Kamera |
| **NETZ** (halten) | Schwingen, loslassen = Schwung mitnehmen |
| **SPRUNG** | Springen, an der Wand: Wandsprung |
| **ZIP** | Netz-Zip dorthin, wohin die Kamera zeigt |
| **ANGRIFF** | Kombos gegen Kultisten, auf Distanz Netzschlag |
| **RISS BETRETEN** | Mission starten (am roten Lichtstrahl) |

| Kampf | |
|---|---|
| Joystick links/rechts | Laufen |
| Joystick hoch / runter | Springen / Ducken |
| **SCHLAG**, **TRITT** | Kombos: Schlag-Schlag-Tritt, Tritt-Tritt, Tritt-Schlag |
| Ducken + Schlag | Uppercut (schleudert hoch) |
| Ducken + Tritt | Feger (wirft um) |
| **BLOCK** + **SCHLAG** (nah) | Wurf, bricht jede Deckung |
| Spezial 1 und 2 | Spezialangriffe des Kämpfers |
| **BRUTAL** | erscheint bei voller Leiste: Super-Angriff in Zeitlupe |
| **EXEKUTION** | bei „VOLLENDE ES!“ innerhalb von 6 Sekunden |

---

## Ehrlich gesagt: Grafik und Größe

- **Grafik:** Stadt, Figuren, Texturen und Effekte entstehen beim Start komplett im Code. Mit HDR, Bloom, Schatten und Partikeln sieht das düster und filmisch aus. Fotoecht wie ein PS5-Spiel ist es aber nicht. Dafür braucht man professionelle 3D-Modelle und Motion-Capture-Animationen. Die lassen sich später einbauen, zum Beispiel als USDZ-Modelle.
- **Speicherplatz:** Weil alles im Code entsteht, ist das Projekt nur wenige MB groß. Das ist kein Zeichen von „klein“: Große Spiele sind vor allem wegen fertiger Video-, Ton- und Modelldateien so groß.
- **Bildrate:** Auf iPads mit ProMotion läuft das Spiel mit bis zu 120 FPS, auf iPhones mit 60 FPS. Bei Ruckeln stellst du in den Einstellungen die Grafikstufe „Leistung“ ein.

## Projektstruktur

```
Silkstrike.swiftpm/
  Package.swift        App-Einstellungen (Playgrounds & Xcode)
  App/                 Einstiegspunkt + GameManager (Spielablauf)
  Core/                gemeinsame Typen, Eingabe, Spielschleife, Mathe
  Graphics/            Rendering, Texturen, Geometrie, Effekte
  Character/           Figuren-Modelle, Animationen, Zerstückelung
  Audio/               Sound-Synthese, Musik, Sprache, Haptik
  Data/                Kämpfer + Story/Zwischensequenzen
  World/               Stadt, Schwingen, Kamera, Kultisten
  Kombat/              Arenen, Kampfsystem, KI, Exekutionen
  Cutscene/            Zwischensequenz-Player + Kulissen
  UI/                  Menüs, HUDs, Touch-Steuerung
```
