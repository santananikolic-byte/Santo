# Liberty City — GTA-artiges Stadt-Game für Roblox

Ein vollständiges, server-autoritatives Grundgerüst: Fahrzeuge, Fahndungslevel,
Polizei-KI, Wirtschaft mit dauerhaftem Speicherstand, Aufträge und
Touch-Steuerung fürs Handy.

Kein fertiges Spiel — ein tragfähiges Fundament, auf dem eins entstehen kann.
Alles, was schwer nachzurüsten ist, wenn man es falsch anfängt (Wirtschaft,
Persistenz, Netzwerkgrenzen), ist hier von Anfang an richtig gebaut.

---

## Losfahren

```bash
# Rojo einmalig installieren
cargo install rojo   # oder: https://rojo.space

cd roblox-city
rojo serve
```

In Roblox Studio das Rojo-Plugin öffnen und verbinden. Danach `F5`.

Das Spiel läuft sofort: liegt keine Karte im Platz, baut `WorldService` eine
Teststadt aus Straßenraster und Blöcken, verteilt vier Streifenwagen und setzt
einen Spawnpunkt. Sobald eine echte Karte da ist, hält der Service sich raus.

**Ohne DataStore-Zugriff** (Studio ohne aktivierte API) läuft alles trotzdem —
Profile bleiben dann nur im Speicher der Sitzung. Der Service sagt es im Log.

### Prüfen

```bash
./tools/check.sh          # Syntax aller Dateien + Testlauf
```

Braucht die [Luau-CLI](https://github.com/luau-lang/luau/releases), in `PATH`
oder über `LUAU_COMPILE=` und `LUAU=`.

---

## Aufbau

```
src/
  shared/       läuft auf beiden Seiten
    Config      alle Stellschrauben an einem Ort
    Net         jedes Remote des Spiels, deklariert und ratenbegrenzt
    RateLimiter Token-Bucket pro Spieler
    Signal      leichtgewichtige Ereignisse
    Util        Formatierung, Zahlenprüfung, Abgleich von Speicherständen

  server/
    Data/
      Profile       Form und Standardwerte eines Speicherstands
      DataService   Laden, Sperren, Speichern
    Services/
      EconomyService    der einzige Ort, an dem sich ein Betrag ändert
      WantedService     Fahndungslevel als Punktekonto
      VehicleService    Besitz, Antrieb, Diebstahl, Aufräumen
      VehicleFactory    baut Fahrzeuge aus Grundkörpern
      PoliceService     Streife, Verfolgung, Verhaftung
      CopFactory        baut den R6-Rig eines Beamten
      JobService        Aufträge und Auszahlung
      ShopService       Kaufvorgänge
      AntiCheatService  Bewegungsprüfung
      WorldService      Teststadt, falls die Baustelle leer ist

  client/
    UI                     Bausteine und Farben
    Controllers/
      HudController        Geld, Sterne, Aufträge, Meldungen
      DriveController      Touch-Steuerung fürs Fahren
      InteractionController Kontextknopf: einsteigen, aussteigen
      MenuController       Garage, Autohaus, Auftragsliste
```

---

## Die vier Entscheidungen, die das Ding tragen

### 1. Geld ändert sich an genau einer Stelle

Jede Gutschrift und jede Abbuchung läuft durch `EconomyService`. Kein anderer
Service fasst `data.cash` an. Zwischen dem Lesen eines Kontostands und dem
Schreiben des neuen Werts wird nie geyieldet — ein `task.wait` an dieser Stelle
ist die klassische Dupe-Lücke, bei der zwei Anfragen denselben Stand lesen und
beide ihre Erhöhung schreiben.

Auszahlungen aus wiederholbaren Abläufen tragen einen Idempotenzschlüssel.
Ein doppelt gemeldeter Auftragsabschluss zahlt einmal.

### 2. Sitzungssperre gegen den ältesten Roblox-Dupe

Ohne Sperre funktioniert das hier: Spieler joint Server A, wartet aufs Laden,
joint parallel Server B mit demselben Speicherstand, gibt auf A alles aus und
lässt B mit dem alten Stand speichern. Geld verdoppelt.

`DataService` hält eine Sperre mit der JobId des Servers und einem Zeitstempel.
Ein zweiter Server, der eine frische fremde Sperre vorfindet, lädt nicht — der
Spieler bekommt einen ehrlichen Hinweis statt eines stillen Nullstands.

Ein Schreibvorgang erledigt beides: speichern und Sperre erneuern. Zwei
getrennte Timer wären doppelt so viele DataStore-Aufrufe für denselben Effekt.

### 3. Der Client schickt Absichten, keine Ergebnisse

Es gibt kein Remote namens `JobCompleted`, keines, das einen Preis entgegennimmt,
und keines, über das der Client seine Position meldet. Der Kaufvorgang bekommt
einen Katalogschlüssel, den Preis kennt nur der Server. Ob ein Auftrag erfüllt
ist, entscheidet der Server, indem er nachsieht.

Jedes Remote ist in `Net.luau` deklariert und hat ein Rate-Limit. Ein Remote,
das per `Instance.new` irgendwo im Code entsteht, hat garantiert weder das eine
noch das andere.

### 4. Anti-Cheat weiß, was es nicht kann

In Roblox gehört die Physik des eigenen Charakters dem Client. Der Server kann
nicht verhindern, dass jemand seine Position setzt — nur bemerken und
zurückdrehen. `AntiCheatService` prüft Tempo, Sprungweite und Schwebeverhalten
und ist damit eine Heuristik, kein Beweis.

Deshalb liegt das Gewicht woanders: Geld, Fahndung und Aufträge leben komplett
auf dem Server. Wer durch die Bewegungsprüfung rutscht, bewegt sich schnell —
aber erzeugt kein Geld.

Die Schwellen stehen in der Service-Datei und nicht in der geteilten Config:
alles in `ReplicatedStorage` ist für jeden Client lesbar, und Grenzwerte, die
der Gegner kennt, sind Grenzwerte, an denen er entlangfährt.

---

## Was drin ist

**Fahrzeuge** — Sechs Modelle im Katalog, aus Grundkörpern gebaut, ohne externe
Assets. Vorderachse mit Servo-Motor-Kette für die Lenkung, Hinterachse als
Antrieb. Drehmoment fällt zum Höchsttempo hin ab, statt hart abgeriegelt zu
werden. Netzwerkbesitz geht an den Fahrer, damit nichts ruckelt; die Wahrheit
über Besitz und Geld bleibt beim Server.

**Fahndungslevel** — Punktekonto statt Sternenzähler, damit sich Vergehen
unterschiedlich gewichten lassen. Der Verfall hält an, solange ein Beamter
Sichtkontakt hat: Verstecken heißt, den Sichtkontakt zu brechen, nicht einen
Timer abzuwarten.

**Polizei** — Beamte werden nach Sternenlevel eingesetzt, verfolgen über
`PathfindingService`, erkennen Festfahren und verhaften bei Nähe und niedrigem
Tempo. Sie denken fünfmal pro Sekunde, nicht jeden Frame.

Sie schießen nicht. Ein Waffensystem braucht eigenes Anti-Cheat für
Trefferprüfung, Feuerrate und Reichweite, und ein halbfertiges ist schlimmer
als keines. Die Verhaftung erfüllt denselben Zweck: sie kostet und beendet die
Jagd.

**Aufträge** — Lieferung, Ladenüberfall, Bankraub. Zeitlimit, Zielmarkierung,
Verweildauer, Auszahlung mit Zeitbonus. Ein aktiver Auftrag pro Spieler.

**Mobile** — Eigene Pedale und Lenktasten statt des Standard-Daumenstiks;
zum Fahren will man Gas und Lenkung getrennt. Der Standard-Stick wird
abgeschaltet, solange jemand am Steuer sitzt — zwei Steuerungen, die in
dasselbe Feld schreiben, ergeben ein zuckendes Fahrzeug. Die Lenkung fährt
weich in die Zielstellung: ein Knopf ist digital, ein Lenkrad nicht.

---

## Was fehlt

Ehrliche Liste, keine Wunschliste:

- **Karte.** Die Teststadt ist ein Raster aus Blöcken, kein Level-Design.
- **Fußgänger.** Es gibt keine Zivilisten, also auch keine Vergehen an ihnen —
  die Punktwerte dafür stehen schon in der Config.
- **Mehrspieler-Raubüberfälle.** `Heist` hat `MinCrewSize` und
  `CrewBonusPerMember` in der Config, aber `JobService` wertet die Crew noch
  nicht aus. Der Auftrag läuft solo.
- **Fahrzeugschaden.** Autos sind unkaputtbar.
- **Ein Spieler, der auf einem fahrenden Auto steht**, überschreitet das
  Fußtempo und wird zurückgesetzt. Bekannter Fehlalarm.
- **Tests für alles mit Instanzen.** Der Testlauf deckt Formatierung,
  Speicherstand-Abgleich, Token-Bucket und Signal ab. Was Roblox-Instanzen
  anfasst, gehört in einen Testlauf in Studio — ein API-Nachbau wäre selbst
  die größte Fehlerquelle im Projekt.

---

## Balance ändern

Fast alles steht in `src/shared/Config.luau`: Preise, Höchsttempo, Auszahlungen,
Verfallszeiten, Anzahl der Beamten pro Stern, Sichtweiten, Speicherintervalle.

Was bewusst **nicht** dort steht: die Schwellen des Anti-Cheat. Siehe oben.
