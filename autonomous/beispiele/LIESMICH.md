# Beispiele (erzeugt von AUTONOMOUS)

Alle Dateien öffnen sich per Doppelklick im Browser, ohne Internet, auch auf dem Handy.

## Erstes Angebot: Google-Profil-Paket (Empfehlung der Marktrecherche)

| Datei | Was es ist |
|---|---|
| `verkaufsseite.html` | Die Verkaufsseite für das **Google-Profil-Paket**, als **Entwurf**. Preis, Lieferzeit, Anbieter, Kontakt, Impressum und Datenschutz sind gelb markierte Platzhalter. Diese Angaben legt ihr fest, AUTONOMOUS erfindet sie nicht. Die Seite verspricht keine Platzierung bei Google. |
| `google-profil-entwurf.html` | Arbeitsunterlage: Entwurf der Profilangaben für eine **erfundene** Musterfirma („Musterfirma Reinigung (Beispiel)“). Er enthält Name, Kategorie-**Vorschläge** (bitte in der Google-Auswahlliste prüfen), eine Beschreibung mit höchstens 750 Zeichen, Leistungen, Servicegebiet, Öffnungszeiten, Kontaktwege, eine Fotoliste und die Punkte, die vor Ort zu klären sind. |
| `google-profil-pruefliste.html` | Prüfliste zum Abhaken beim Termin vor Ort. Sie deckt ab: Inhaberschaft, keine Passwörter, Bestätigung durch Google, Angaben, Fotos, nur echte Bewertungen und Übergabe. |
| `google-profil-uebergabe.html` | Kurzanleitung für den Kunden in einfacher Sprache. Sie erklärt: Sie sind Inhaber, wie man uns als Verwalter entfernt, Angaben ändern, Fotos, Bewertungen. |

Wichtig: Diese Unterlagen tragen **nichts** bei Google ein. Das geschieht beim Termin vor Ort durch den Inhaber oder mit seiner Zustimmung.

## Stufe 2: Webseiten-Paket

| Datei | Was es ist |
|---|---|
| `verkaufsseite-webseiten.html` | Die Verkaufsseite für das Webseiten-Paket, ebenfalls als Entwurf mit Platzhaltern. |
| `beispiel-webseite.html` | Eine Webseite für die **erfundene** Musterfirma. So sieht das Ergebnis des Webseiten-Pakets aus. |

Die Telefonnummer der Musterfirma ist eine Beispielnummer. Die E-Mail-Endung `.example` gibt es nicht. Keine der Seiten nutzt JavaScript, und keine lädt etwas von fremden Servern (keine Schriftarten, keine Tracker).

Neu erzeugen, wenn sich ein Generator ändert:

```
python3 -c "from autonomous.produkte.verkaufsseite import beispiele_schreiben; beispiele_schreiben('autonomous/beispiele')"
```

Tests (`autonomous/tests/test_produkt_vertrieb.py`, `autonomous/tests/test_google_profil.py`) prüfen, dass diese Dateien zum Generator passen und fehlerfrei sind.
