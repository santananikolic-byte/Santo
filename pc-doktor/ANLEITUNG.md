# PC-Doktor – alten Gamer-PC wieder fit machen

Ein Programm für Windows 10/11, das die typischen Probleme alter Gamer-PCs
behebt: abbrechende Downloads, Epic Games Launcher, der nicht installiert,
Dateien, die sich nicht öffnen lassen, kaputte Systemdateien und ein
langsamer PC.

## So startest du es

1. Auf GitHub im Repository oben auf **Code → Download ZIP** klicken.
2. ZIP-Datei mit Rechtsklick → **Alle extrahieren**.
3. Im Ordner `pc-doktor` doppelt auf **`PC-Doktor.bat`** klicken.
4. Falls ein blaues Fenster „Der Computer wurde durch Windows geschützt“
   erscheint: **Weitere Informationen → Trotzdem ausführen**.
5. Die Frage nach Administratorrechten mit **Ja** bestätigen.
6. Im Menü **A** drücken und Enter → alles wird der Reihe nach repariert.
7. Wenn es fertig ist: **PC neu starten** (Menüpunkt N).

Dauer: etwa 30–60 Minuten. Nicht abbrechen, während DISM/SFC läuft.

## Was die Menüpunkte machen

| Punkt | Was passiert |
|---|---|
| **A** | Alles unten der Reihe nach (vorher wird ein Wiederherstellungspunkt angelegt) |
| **1** Diagnose | Zeigt Speicherplatz, Festplattenzustand, RAM, falsche Uhrzeit, Internet, Epic-Server, abgeschaltete Dienste, alte Grafiktreiber – ändert nichts |
| **2** Aufräumen | Löscht Temp-Dateien, Update-Reste, Shader-Caches, Papierkorb, Windows-Datenträgerbereinigung |
| **3** Windows reparieren | DISM + SFC (repariert Systemdateien), Windows Installer neu registrieren, Festplatte prüfen |
| **4** Internet | Uhrzeit synchronisieren, TLS 1.2 einschalten, DNS/Winsock zurücksetzen, Proxy entfernen, optional schnellen DNS |
| **5** Spiele-Bausteine | Visual C++ (alle Versionen), DirectX, .NET – fehlen die, starten Spiele nicht („DLL fehlt“) |
| **6** Epic Games | Epic beenden, kaputten Webcache löschen, Installer neu laden (setzt abgebrochene Downloads fort), installieren, Firewall-Freigabe |
| **7** Downloads öffnen | Entsperrt Dateien im Download-Ordner, repariert .exe/.msi/.zip-Zuordnung, installiert winget, optional 7-Zip, VLC, Adobe Reader |
| **8** Leistung | Höchstleistungs-Energieplan, Spielmodus, Xbox-Hintergrundaufnahme aus, Laufwerk optimieren, Link zum Grafiktreiber |
| **9** Virenscan | Windows-Defender-Schnellscan |

Ein Bericht über alles, was passiert ist, liegt danach auf dem
**Desktop** (`PC-Doktor-Bericht_….txt`). Wenn etwas nicht klappt, schick
mir diesen Bericht – dann sehe ich genau, wo es hängt.

## Warum der Epic-Download abbricht – die häufigsten Gründe

1. **Zu wenig Speicherplatz** auf C: → Punkt 2.
2. **Falsche Uhrzeit** am PC → sichere Verbindungen scheitern → Punkt 4.
3. **Windows zu alt** (Epic braucht Windows 10 Version 2004 oder neuer)
   → Diagnose zeigt das an; dann Windows Update laufen lassen.
4. **Windows Installer kaputt / abgeschaltet** → Punkt 3.
5. **Kaputter Webcache** im Launcher (weißes Fenster, Download hängt) → Punkt 6.
6. **Antivirus / Firewall blockt** → Punkt 6 trägt eine Freigabe ein.

## Rückgängig machen

Vor den Reparaturen legt das Programm einen Wiederherstellungspunkt
„Vor PC-Doktor“ an. Zurück geht es über: Startmenü → „Wiederherstellungspunkt
erstellen“ → **Systemwiederherstellung** → „Vor PC-Doktor“ auswählen.

Deine Spiele, Fotos und Dokumente werden nicht gelöscht.
