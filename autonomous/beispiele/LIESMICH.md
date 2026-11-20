# Beispiele (erzeugt von AUTONOMOUS)

Beide Dateien öffnen sich per Doppelklick im Browser, ohne Internet, auch auf dem Handy.

| Datei | Was es ist |
|---|---|
| `beispiel-webseite.html` | Eine Webseite für eine **erfundene** Musterfirma („Musterfirma Reinigung (Beispiel)“). Die Telefonnummer ist eine Beispielnummer, die E-Mail-Endung `.example` gibt es nicht. So sieht das Ergebnis des Webseiten-Pakets aus. |
| `verkaufsseite.html` | Die Verkaufsseite für das Webseiten-Paket, als **Entwurf**: Preis, Lieferzeit, Anbieter, Kontakt, Impressum und Datenschutz sind gelb markierte Platzhalter. Diese Angaben legt ihr fest, AUTONOMOUS erfindet sie nicht. |

Beide Seiten nutzen kein JavaScript und laden nichts von fremden Servern (keine Schriftarten, keine Tracker).

Neu erzeugen, wenn sich der Generator ändert:

```
python3 -c "from autonomous.produkte.verkaufsseite import beispiele_schreiben; beispiele_schreiben('autonomous/beispiele')"
```

Ein Test (`autonomous/tests/test_produkt_vertrieb.py`) prüft, dass diese Dateien zum Generator passen.
