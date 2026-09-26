# Gut Krähenmoor

Ein Survival-Horrorspiel in der Machart von Resident Evil 7: ein Haus über drei
Stockwerke, Schlüssel und Rätsel, ein Verfolger, den man nicht töten kann, und
eine Geschichte, die man sich aus einundzwanzig Fundstücken zusammensetzt.

Echtes 3D im Browser (three.js): Die Petroleumlampe ist ein Spotlicht mit
Schattenwurf, Kerzen flackern als eigene Lichtquellen, nasse Kellerböden
spiegeln, Türen schwingen auf. Figuren, Leichen und Schlachthälften sind aus
3D-Teilen gebaut und werfen Schatten an die Wand. Alles andere — Texturen,
Gesichter, Musik, Geräusche — entsteht zur Laufzeit im Code.

## Spielen

**iPhone:** Link öffnen, **quer halten**, Kopfhörer rein. Der Ton läuft auch bei
eingeschaltetem Stummschalter.

**Mac:** Doppelklick auf **`spielen.html`** — läuft auch ohne Internet, die
3D-Bibliothek ist eingebettet.

| Touch | Wirkung |
|---|---|
| linke Bildhälfte ziehen | gehen — Daumen bis zum Anschlag nach vorn = rennen |
| rechte Bildhälfte wischen | umsehen, auch nach oben und unten |
| NEHMEN | benutzen, nehmen, Türen öffnen (leuchtet, wenn etwas in Reichweite ist) |
| LAMPE / TASCHE / VERBAND | Lampe an/aus, Gegenstände und Archiv, verbinden |
| II | Pause |

| Tastatur | Wirkung |
|---|---|
| `W` `A` `S` `D` | gehen |
| Maus (oder Pfeiltasten) | umsehen |
| `Shift` | rennen — er hört es |
| `E` | benutzen |
| `F` | Lampe |
| `Tab` | Tasche und Archiv |
| `H` | verbinden |
| `Leertaste` | Dokument weglegen |
| `Esc` | Pause |

## Die Geschichte

Deine Schwester Ada ist vor drei Monaten verschwunden. Die Polizei hat ihr Auto
am Moorweg gefunden, den Schlüssel steckend, die Kamera mit vollem Film auf dem
Beifahrersitz. Letzte Woche kam ein Brief in ihrer Handschrift, abgestempelt
**nach** ihrem Verschwinden. Absender: ein Moorgut, das laut Kataster seit 1974
nicht mehr existiert.

Es existiert.

Die Vorgeschichte erzählt die Fahrt dorthin. Danach vier Kapitel:

1. **Das Haus** — Messingschlüssel, Arbeitszimmer, der Wandtresor. Der Code
   steht nirgends; er setzt sich aus zwei Papieren zusammen.
2. **Der Keller** — Schlachtraum, Zellen, ein Sicherungskasten, in dem eine
   Sicherung fehlt. Daneben mit Kreide: *„G. hat sie mit rauf genommen."*
3. **Der Dachboden** — Gretes Zimmer. Sie hat 1974 das Haus angezündet. Es hat
   nicht funktioniert. Ihr Schlüssel steckt im Bauch ihrer Puppe, und die
   Puppen schauen dich an, sobald du dich umdrehst.
4. **Der Gast** — was 1971 im Torf lag, und warum jeder Brief aus diesem Haus
   *sein* Brief ist.

Zwei Tonaufnahmen: Hennigs Tonband von 1973 und Adas Diktiergerät, beide über
die Sprachausgabe des Geräts mit Untertiteln. Wer die richtigen Papiere findet,
liest den Brief aus dem Menü im Archiv noch einmal — und er liest sich anders.

Zwei Enden, je nachdem, ob du Ada vor dem Finale findest.

## Musik

Eigener Soundtrack, komplett im Code: die schiefe Spieluhr als Leitmotiv,
verstimmte Klaviertöne und Cello beim Erkunden, Verfolgungsmusik, sobald er
dich jagt, im Finale schneller.

## Dateien

- `kraehenmoor.html` — Quelle (so läuft es als Artifact, 3D-Bibliothek von cdnjs)
- `spielen.html` — gebaute Offline-Datei mit eingebetteter 3D-Bibliothek
- `build.sh` — baut `spielen.html` aus der Quelle
- `vendor/three.r128.min.js` — three.js r128, MIT-Lizenz

Nach Änderungen an `kraehenmoor.html` einmal `./build.sh` laufen lassen.
