# JARVIS – Status

Bedeutung der Stände:

- **Geplant** – steht auf dem Plan, noch kein Code.
- **Gebaut** – Code vorhanden.
- **Getestet** – automatische Tests laufen grün (Claude Code dabei simuliert, damit kein Abo-Limit verbraucht wird).
- **Verifiziert** – auf dem echten iMac mit echtem Claude ausprobiert. *Bisher nichts.*
- **Blockiert** – braucht etwas, das fehlt.
- **Wartet auf Freigabe** – braucht deine Entscheidung.

Dieser Stand wird nach jeder Stufe nachgeführt (siehe unten Tabelle).

| Baustein | Stand | Beleg / Hinweis |
|---|---|---|
| Server, Logs, Start/Stopp | Getestet | `tests/test_kern.py` |
| Sprachausgabe (macOS `say`) | Getestet (Ersatzprogramm) | echte Stimme nicht verifiziert |
| Claude Code als Denken | Getestet (simuliert) | echter Aufruf nicht verifiziert |
| Gedächtnis, Aufgaben, Aufträge | Geplant | Stufe 4 |
| Werkzeuge und Freigaben | Geplant | Stufe 5 |
| Agent-Kern, Planer, Prüfung, Läufer | Geplant | Stufe 6 |
| Oberfläche (orange Leitstand) | Geplant | Stufe 7 |
| Handy-Zugriff im WLAN | Geplant | nur nach deiner Freigabe |
| Autostart (launchd) | Geplant | nicht testbar außerhalb des Macs |
| Browser-Automation | Blockiert | braucht zusätzliche Software, deine Zustimmung |
| Mail, Kalender, Finanzen, Kunden | Geplant | spätere Stufen |
