# Der iMac als Kopf von Jarvis

Jarvis läuft dauerhaft auf einem iMac, ohne Fenster und ohne Tippen. Er hört zu,
antwortet laut, arbeitet im Hintergrund weiter (Zeitplan, Autopilot) und startet
sich selbst neu, wenn er abstürzt oder hängt.

## Einrichten, einmalig

1. **Jarvis installieren** und die Einrichtung durchlaufen (`python3 jarvis.py`).
2. **Einmal im Terminal** `python3 jarvis.py daemon` starten und die Fragen von macOS bestätigen:
   Mikrofon, Bedienungshilfen, Bildschirmaufnahme und, wenn Jarvis überall lesen soll,
   Festplattenvollzugriff. Das kann kein Programm für dich tun, das muss ein Mensch bestätigen.
   Mit Strg und C wieder beenden.
3. **Den Dienst einrichten:** `python3 jarvis.py dienst installieren`.
   Ab jetzt startet Jarvis bei jeder Anmeldung von selbst.
4. **Den Mac wach halten**, Systemeinstellungen:
   - Energie: "Ruhezustand bei ausgeschaltetem Display verhindern" einschalten
   - Energie: "Nach einem Stromausfall automatisch starten"
   - Benutzer: automatische Anmeldung für den Benutzer, unter dem Jarvis läuft.
     Bei eingeschalteter FileVault-Verschlüsselung geht das nicht: Dann muss nach einem
     Neustart einmal jemand das Passwort eingeben.

## Bedienen

Alles per Stimme. "Hey Jarvis" und dann sagen, was du brauchst.

- **Freigaben:** Vor allem, was etwas verändert oder nach außen geht (Mail, Anruf,
  Datei anlegen, Skript starten), sagt Jarvis, was er tun will, und fragt "Soll ich?".
  Nur ein klares Ja gilt. Steht ein Nein-Wort in der Antwort ("ja, aber nicht jetzt"),
  ist es ein Nein. Keine Antwort ist ein Nein. Ist die Stimmprüfung an, gibt eine
  fremde Stimme nichts frei.
- **Beenden:** "Jarvis, schalte dich ab". Danach bleibt er aus, bis zur nächsten Anmeldung.
- **Vom Handy:** Sprachnachrichten per Telegram gehen an denselben Kopf.

## Befehle

| Befehl | Wirkung |
|---|---|
| `python3 jarvis.py daemon` | im Vordergrund laufen lassen (zum Testen) |
| `python3 jarvis.py dienst installieren` | Anmeldeobjekt anlegen und starten |
| `python3 jarvis.py dienst status` | läuft er, wann das letzte Lebenszeichen |
| `python3 jarvis.py dienst neustart` | neu starten |
| `python3 jarvis.py dienst entfernen` | wieder entfernen |
| `python3 jarvis.py dienst installieren --trocken` | zeigen, was passieren würde |

Protokoll: `logs/dienst.log` (wird bei 5 Megabyte beiseitegelegt).

## Was er auf dem Mac darf

- **Suchen und Lesen** ohne Nachfrage: `dateien_suchen` (Spotlight) und `datei_lesen`
  (nur Text). Gesperrt bleiben Schlüsselbund, SSH- und Cloud-Schlüssel, Browser-Profile,
  Passwortdateien, `.env` und die Konfiguration von Jarvis selbst. Die Sperre gilt auch
  über Verknüpfungen hinweg.
- **Schreiben** nur mit Freigabe: eine neue Textdatei im Benutzerordner. Nichts
  Vorhandenes ohne ausdrückliches Ersetzen, nichts in Startobjekte (`LaunchAgents`),
  Shell-Profile, Schlüsselordner oder in Jarvis' eigenes Programm.
- **Skripte** schreibt die Werkstatt, ausgeführt werden sie nur nach Freigabe. Weil man
  Code nicht vorlesen kann, sagt Jarvis, was das Skript vorhat (zum Beispiel "will ins
  Netz"), und verweist für den Code auf die Werkstatt.
- **Bildschirm und Browser** bedient er nur mit Freigabe, Schritt für Schritt.

## Ein eigenes Betriebssystem?

Jarvis schreibt kein eigenes Betriebssystem, und das wäre das falsche Mittel. Wer die
Trennung vom privaten Mac will, hat zwei saubere Wege:

1. **Eigener Benutzer am iMac.** Systemeinstellungen, Benutzer, neuen Standardbenutzer
   "jarvis" anlegen, dort automatisch anmelden, Jarvis dort installieren. Eigener Ordner,
   eigener Schlüsselbund, eigene Rechte. Dateien deines Hauptbenutzers sind dann nur
   erreichbar, wenn du einen Ordner ausdrücklich freigibst.
2. **Eine virtuelle Maschine** (zum Beispiel mit UTM oder Parallels) für noch mehr
   Abstand. Dann arbeitet Jarvis in einem eigenen macOS oder Linux, das er nach Belieben
   kaputt machen darf.

Wer ihm den ganzen Mac gibt, nimmt in Kauf, dass ein Fehler oder ein untergeschobener
Text in einer Datei auch dort Schaden anrichten kann. Deshalb gelten die Freigaben und
die Sperrliste auch dann.
