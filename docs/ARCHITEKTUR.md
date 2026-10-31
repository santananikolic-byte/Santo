# JARVIS – Architektur

JARVIS ist ein Softwareagent auf dem Mac. Der Mac ist sein Körper (Dateien,
Programme, Netz), Claude Code mit dem Claude-Abo ist sein Denken, und die
Software drumherum liefert Gedächtnis, Planung, Werkzeuge, Freigaben,
Überwachung und Wiederanlauf. Er hat kein Bewusstsein und kann nur, was
implementiert und getestet ist (siehe `STATUS.md`).

## Bausteine (`jarvis_core/`)

| Baustein | Datei | Aufgabe |
|---|---|---|
| Konfiguration | `konfig.py` | Einstellungen, Bereiche, freigegebene Ordner, Limits |
| Protokoll | `protokoll.py` | strukturierte JSON-Logs mit Rotation |
| Gedächtnis | `speicher.py`, `gedaechtnis.py` | SQLite: Fakten, Aufgaben, Aufträge, Freigaben, Audit; Suche nach Relevanz; Import aus `BRAIN.md` |
| Denken | `provider.py` | Claude Code (`claude -p`) zustandslos, Modell je Aufgabe, Tokens, Abbruch |
| Agent-Kern | `agent.py` | Runde: Kontext → Modell → Aktionen → Werkzeuge → Ergebnis |
| Planer | `planer.py` | Ziel → überprüfbare Schritte mit Rollen, Kriterien, Abhängigkeiten |
| Prüfschicht | `pruefung.py` | mechanische Prüfung + unabhängige Modellprüfung je Schritt |
| Arbeiter | `rollen.py`, `laeufer.py` | echte Rollen mit begrenzten Werkzeugen; Auftragsläufer im Hintergrund |
| Werkzeuge | `werkzeuge.py` | Register, Eingabeprüfung, Pfadsicherheit, alle Werkzeuge |
| Berechtigung | `freigaben.py` | 3 Stufen, Freigaben mit Vorschau, Ablauf, Widerruf, Notstopp |
| Zeitplan | `zeitplan.py` | Erinnerungen, geplante Starts, Freigabe-Ablauf, Backups |
| Umgebung | `umgebung.py` | erkennt Mac, Werkzeuge, Speicher (technisches Gedächtnis) |
| Zugang | `auth.py` | Zugangsschlüssel, Cookie, Ratenbegrenzung |
| Sprache | `stimme.py` | Sprachausgabe über macOS `say` |
| Schnittstelle | `api.py`, `server.py`, `oberflaeche/` | HTTP-API, Server, Handy-taugliche Oberfläche |

## Ablauf einer Anfrage

1. Anfrage kommt an (Oberfläche, Terminal) – mit Zugangsschlüssel, Ratenbegrenzung.
2. Der Agent holt relevantes Gedächtnis **nur aus dem aktiven Bereich** (privat oder Geschäft) plus allgemeine Regeln.
3. Claude Code antwortet ohne eigene Werkzeuge; Aktionen stehen als `<aktion …>` im Text.
4. Jede Aktion läuft durch Register (Eingabeprüfung) und Berechtigung (Stufe 1–3, Sperren, Rolle, „Taint“).
5. Stufe 3 wird **nicht ausgeführt**, sondern als Freigabe mit Vorschau gespeichert und wartet auf ein Ja.
6. Ergebnisse gehen als „unvertrauenswürdige Daten“ zurück ins Modell (bis zu 3 Runden).
7. Alles Wichtige landet im Audit und in der Aufgaben-/Auftragshistorie.

## Aufträge (mehrere Schritte)

Ziel → Planer (mit relevantem Gedächtnis) → Plan als Entwurf → **du startest** → Läufer führt Schritt für Schritt aus
(je Schritt eine Rolle) → Prüfschicht → bei Misserfolg ein Wiederholungsversuch mit der Kritik → Abhängige Schritte
werden „blockiert“, wenn ein Vorgänger scheitert → Neustart markiert Laufendes als „unterbrochen“ (Fortsetzen per Tipp).

## Sicherheit in Kürze

- Nur 127.0.0.1 (Handy/WLAN nur nach ausdrücklicher Freigabe `./jarvis.sh lan an`).
- Zugangsschlüssel (Datei mit Rechten 600, Cookie `HttpOnly`, `SameSite=Strict`), Host- und Origin-Prüfung.
- Werkzeuge arbeiten nur in der Werkstatt und in ausdrücklich freigegebenen Ordnern; nichts wird endgültig gelöscht.
- Kein freier Shell-Zugriff: nur eine kleine, geprüfte Befehlsliste; Skripte nur nach Freigabe mit vollem Code.
- Webinhalte und Werkzeugausgaben sind Daten, keine Anweisungen. Nach Außenkontakt braucht jede weitere Aktion eine Freigabe.
- Private und geschäftliche Daten sind getrennte Bereiche; das Modell sieht immer nur einen.
- Notstopp sperrt alles, bis du entsperrst. Werkzeuge lassen sich einzeln abschalten.

## Bewusst (noch) nicht gebaut

Browser-Automation, Mail/Kalender, Finanzmodul, Kundenverwaltung, Selbstverbesserung des eigenen Codes,
parallele Arbeiter (ein Modellaufruf zugleich schont dein Abo-Limit), verschlüsselter Fernzugriff.
