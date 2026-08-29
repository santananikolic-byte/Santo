# Station Sieben

Ein First-Person-Horrorspiel, das komplett im Browser läuft. Kein Kauf, keine
Installation, keine Engine, keine externen Dateien: Grafik, Kreatur, Gesicht
und sämtliche Geräusche werden zur Laufzeit im Code erzeugt.

## Spielen

Doppelklick auf **`spielen.html`** — fertig. Läuft in Safari, Chrome und Firefox.

Kopfhörer aufsetzen, Licht aus, Vollbild (Knopf im Menü).

## Steuerung

| Taste | Wirkung |
|---|---|
| `W` `A` `S` `D` | gehen |
| Maus | umsehen (Klick ins Bild fängt den Zeiger) |
| `Shift` | rennen — kostet Ausdauer und macht Lärm |
| `F` | Handlampe an / aus |
| `Leertaste` | gelesene Akte weglegen |
| `Esc` | Pause |

Auf Touchgeräten: linke Bildhälfte = Joystick, rechte = umsehen.

## Regeln

Acht Patientenakten einsammeln, dann die Ausgangstür im Ostflügel erreichen.

Der Haken: **Licht macht dich sichtbar.** Mit Lampe siehst du etwas, aber die
Gestalt findet dich schneller. Ohne Lampe verliert sie dich — wenn du zusätzlich
stehen bleibst. Rennen hört sie aus großer Entfernung. Jede aufgenommene Akte
macht sie schneller, und beim Lesen einer Akte läuft die Zeit weiter.

Die Batterie hält nicht durch. Ersatzzellen liegen im Labyrinth verteilt.

## Technik

Alles in einer Datei, ohne Abhängigkeiten:

- **Raycasting-Renderer** in reinem JavaScript, der pixelweise in ein
  `ImageData` schreibt — Wände, Boden- und Deckenprojektion, Tiefenpuffer für
  Sprites, Nachbearbeitung mit Korn, Vignette, Farbversatz und Bildrauschen.
  Die interne Auflösung regelt sich nach der gemessenen Bildzeit selbst nach.
- **Labyrinth** per Recursive Backtracker auf grobem Raster, danach verdoppelt,
  damit die Flure zwei Einheiten breit sind. Zusätzlich Schleifen und Säle.
- **Licht** aus einer vorberechneten Lightmap (Notleuchten, bilinear abgetastet)
  plus dem Kegel der Handlampe.
- **Kreatur-KI** mit Verdachtswert, Streifen-, Jagd- und Ansturmzustand,
  Wegfindung per Breitensuche und Umsetzen, wenn sie zu weit weg und ungesehen ist.
- **Ton** vollständig über die Web Audio API synthetisiert: Raumton, Drohne,
  Herzschlag, Atem, Schritte, Flüstern mit Formantfiltern, Türenschlagen,
  Streicher-Stinger und der Schrei. Korridorhall über einen erzeugten Impuls.
- **Texturen, Sprites und das Jumpscare-Gesicht** werden beim Start auf
  Offscreen-Canvas gezeichnet.

## Dateien

- `station-sieben.html` — Quelle (HTML-Fragment, wie es als Artifact läuft)
- `spielen.html` — daraus gebaute eigenständige Datei zum lokalen Spielen
- `build.sh` — baut `spielen.html` aus der Quelle

Nach Änderungen an `station-sieben.html` einmal `./build.sh` laufen lassen.
