# Gut Krähenmoor

Ein Survival-Horrorspiel in der Machart von Resident Evil 7: ein Haus statt
eines Labyrinths, Schlüssel und Rätsel, ein Verfolger, den man nicht töten
kann, und eine Geschichte, die man sich aus sechzehn Fundstücken zusammensetzt.

Läuft komplett im Browser. Kein Kauf, keine Installation, keine externen
Dateien — Grafik, Kreatur, Gesicht und sämtliche Geräusche entstehen zur
Laufzeit im Code.

## Spielen

Am Mac: Doppelklick auf **`spielen.html`**. Kopfhörer auf, Licht aus.

Auf dem iPhone: Link öffnen, **quer halten**, Kopfhörer rein. Der Ton läuft
auch bei eingeschaltetem Stummschalter.

| Touch | Wirkung |
|---|---|
| linke Bildhälfte ziehen | gehen — Daumen bis zum Anschlag nach vorn = rennen |
| rechte Bildhälfte wischen | umsehen |
| NEHMEN | benutzen, nehmen, Türen öffnen (leuchtet, wenn etwas in Reichweite ist) |
| LAMPE / TASCHE / VERBAND | wie am Rechner |
| II | Pause |

| Taste | Wirkung |
|---|---|
| `W` `A` `S` `D` | gehen |
| Maus | umsehen (ins Bild klicken fängt den Zeiger) |
| `Shift` | rennen — er hört es |
| `E` | benutzen, nehmen, Türen öffnen |
| `F` | Petroleumlampe an / aus |
| `Tab` | Tasche und Archiv |
| `H` | verbinden |
| `Leertaste` | Dokument weglegen |
| `Esc` | Pause |

## Worum es geht

Deine Schwester Ada ist vor drei Monaten verschwunden. Letzte Woche kam ein
Brief in ihrer Handschrift, abgestempelt **nach** ihrem Verschwinden. Der
Absender ist ein Moorgut, das laut Akten 1974 abgebrannt ist.

Es ist nicht abgebrannt.

## Vorgeschichte und Kapitel

Vor dem Haus steht die Fahrt: Regen, Scheibenwischer, der Brief, das Auto, das
die Polizei am Moorweg gefunden hat, die Kamera mit dem vollen Film. Danach drei
Kapitel — **Das Haus**, **Der Keller**, **Der Gast**.

Im Wohnzimmer liegt ein **Tonband** von 1973. Hennigs Stimme kommt über die
Sprachausgabe des Geräts, tief gestimmt, mit Untertiteln; ohne deutsche Stimme
laufen nur die Untertitel.

## Musik

Eigener Soundtrack, komplett im Code: die schiefe Spieluhr als Leitmotiv im
Menü und am Ende, vereinzelte verstimmte Klaviertöne und Cello beim Erkunden,
und sobald er dich jagt, setzt eine treibende Verfolgungsmusik ein — im Finale
schneller.

## Ablauf

Erdgeschoss und Keller, drei Rätsel, zwei Enden:

1. **Messingschlüssel** in der Küche öffnet das Arbeitszimmer.
2. **Wandtresor** — vier Ziffern. Der Code steht nicht auf einem Zettel; du
   musst ihn aus zwei Dokumenten zusammensetzen. (Der Zeitungsausriss hat die
   Jahreszahl verkohlt. Das Grabsteinfoto hat sie noch.)
3. **Strom** — im Sicherungskasten fehlt eine Schmelzsicherung. Sie liegt im
   Schlachtraum. Ohne Strom bleibt die Zellentür zu.
4. Der **Hofschlüssel** hängt der Moorleiche um den Hals. Wenn du ihn nimmst,
   fängt der letzte Teil an, und im Haus geht jedes Licht aus.

**Licht macht dich sichtbar.** Mit Lampe siehst du etwas, aber er findet dich
schneller. Ohne Lampe verliert er dich — wenn du dazu stehen bleibst. Du
verträgst drei Treffer.

Ob du am Ende allein oder zu zweit hinausgehst, hängt davon ab, ob du Ada
gefunden hast, bevor du den Schlüssel nimmst.

Wer die beiden entscheidenden Papiere findet, kann den Brief aus dem Menü im Archiv noch
einmal lesen. Er liest sich dann anders.

## Technik

- **Raycasting-Renderer** in purem JavaScript, pixelweise in ein `ImageData`:
  Wandprojektion auf Augenhöhe, getrennte Boden- und Deckenabtastung,
  Tiefenpuffer für Sprites, Blut als zweite Bodentextur, die pro Zelle
  eingeblendet wird. Interne Auflösung regelt sich nach gemessener Bildzeit.
- **Grundriss aus Rechtecken** statt handgemalter ASCII, mit Prüfskript für
  Türlagen, Bedienfelder und Erreichbarkeit jedes Raums.
- **Türen mit Zustand**, Schlüsselprüfung, Ebenenwechsel über die Treppe.
- **Verfolger** mit Verdachtswert aus Lampe, Lärm und Sichtlinie; Streifen-,
  Jagd- und Ansturmzustand, Wegfindung per Breitensuche, Zugriff mit
  Trefferverlust statt Sofort-Tod.
- **Ton** vollständig über die Web Audio API: Raumton, Drohne, Herzschlag,
  nasses Atmen, Schritte je nach Untergrund, Ketten, Tropfen, Fliegenschwarm,
  verstimmte Spieluhr, sein Brüllen und das Erwachen im Torf. Korridorhall
  über einen erzeugten Impuls.
- **Texturen, Requisiten und das Gesicht** werden beim Start auf
  Offscreen-Canvas gezeichnet — Fleischerhaken, Eingeweide, Blutschlieren.

## Dateien

- `kraehenmoor.html` — Quelle (HTML-Fragment, wie es als Artifact läuft)
- `spielen.html` — daraus gebaute eigenständige Datei zum lokalen Spielen
- `build.sh` — baut `spielen.html` aus der Quelle

Nach Änderungen an `kraehenmoor.html` einmal `./build.sh` laufen lassen.
