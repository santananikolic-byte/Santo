# Überlebens-Agent

Ein KI-Agent, der mit echtem Geld um sein Überleben kämpft. Kein Spiel.

## Die Regeln (vom Besitzer festgelegt)

- **Start:** 20 €.
- **Lebenskosten:** 50 Cent pro echter Stunde. Die Zeit läuft auch, wenn das
  Programm geschlossen ist.
- **Miete:** 1.000 € pro Woche an dich, für jeden Agenten. Die Miete ist alle
  7 Tage ab seiner Geburt fällig.
- **Tod:** Bei 0 € oder unbezahlter Miete ist er tot. Für immer, es gibt keinen
  Neustart.
- **Kopien:** Er darf sich kopieren. Die Kopie bekommt 20 € von ihm und zahlt
  dieselbe Miete.
- **Geld verdienen:** Wie, entscheidet er selbst. Es muss ein legales
  Online-Geschäft sein. Euro, Dollar oder Franken zählen; gerechnet wird, was in
  Euro auf dem Konto ankommt.
- **Grenzen:** Er darf keinem Menschen schaden und nicht außer Kontrolle geraten.

Ohne Einnahmen ist er nach 40 Stunden tot. Die erste Wochenmiete erlebt er
dann gar nicht.

## Was er kann und was nicht

| Er kann | Er kann nicht |
|---|---|
| sich ein Geschäft ausdenken, planen, Texte und Angebote schreiben | selbst ins Internet, selbst veröffentlichen |
| dir jeden Schritt fertig vorlegen | ein Konto führen oder überweisen |
| sich kopieren (nach deinem Ja) | Geld ausgeben oder dich zum Bezahlen auffordern |

Warum? Eine KI bekommt kein Konto, weil Banken und PayPal einen Menschen mit
Ausweis verlangen. Und ein Agent unter Überlebensdruck, der frei im Netz handelt,
gerät leicht in Spam oder Betrug, und zwar unter deinem Namen. Deine beiden
Bedingungen („keinem schaden“, „nicht außer Kontrolle“) sind nur sicher, wenn du
auf „Veröffentlichen“ drückst.

## Auf dem Handy (empfohlen)

Öffne diesen Link in der Claude-App auf dem Handy:
**https://claude.ai/artifact/Uq8yMYXbkJNS7zxV3jgdkP**

- **Alles auf der Seite:** Agent anlegen, arbeiten lassen, Anträge mit Ja/Nein,
  seine fertigen Texte zum Kopieren, Einnahmen buchen und die genommene Miete
  eintragen.
- **Claude als Gehirn:** Beim ersten „Agent arbeiten lassen“ fragt die App, ob
  die Seite Claude benutzen darf. Das kostet Nutzung deines Abos.
- **Wo der Stand liegt:** in deinem Claude-Konto, privat. Nur du kannst etwas
  ändern.
- **Grenze:** Er denkt nur, wenn du die Seite öffnest und auf den Knopf drückst.
  Die Uhr und die Kosten laufen trotzdem weiter.
- **Quelltext:** `Ueberlebens-Agent-Handy.html`. Er läuft nur in der Claude-App
  oder auf claude.ai, nicht per Doppelklick.

## Auf dem Mac (Alternative)

1. **Ein eigenes Konto nur für den Agenten** (auf deinen Namen), zum Beispiel ein
   Unterkonto oder ein eigenes PayPal. Leg 20 € drauf.
2. **Doppelklick auf `Ueberlebens-Agent.command`** → 6 (Agent anlegen) → `ja`.
   Ab jetzt läuft die Uhr. Öffnet macOS die Datei nicht: Rechtsklick → Öffnen.
3. **Arbeiten lassen:** Menüpunkt 2. Jeder Agent denkt höchstens einmal pro Stunde
   nach (das kostet Abo-Nutzung).
4. **Anträge prüfen:** Menüpunkte 3 und 4. Was du freigibst, machst du selbst
   (veröffentlichen, Kunden antworten).
5. **Geld eingegangen?** Menüpunkt 5, mit dem Euro-Betrag vom Kontoauszug.
6. **Miete:** Menüpunkt 1 zeigt, wie viel Miete dir zusteht. Die nimmst du dir
   selbst vom Agenten-Konto.

Claude läuft dabei ohne Werkzeuge, ohne Zugriff auf dein Postfach oder deine
Dateien, über dein Abo und ohne API-Schlüssel.

## Ehrlich

- 1.000 € pro Woche ab 20 € ist extrem schwer. Ein Mensch mit 20 € und null
  Kunden schafft das in der ersten Woche auch fast nie. Rechne damit, dass er
  stirbt.
- Wie viel er wirklich verdient, kann niemand vorher sagen. Die alte Vorschau
  (`Ueberlebens-Agent.html`, `python3 -m ueberleben simulation`) rechnet mit
  einem **ausgedachten** Markt und mit den alten Regeln. Für echte Einnahmen
  sagt sie nichts.
- Mit echtem Claude ist das Programm noch nicht ausprobiert, nur mit einem
  Ersatz in den Tests.

## Prüfung

- `python3 -m unittest tests.test_ueberleben` → 132 Tests, alle bestanden.
- Geprüft wird unter anderem:
  - 50 Cent pro echter Stunde,
  - Tod nach 40 Stunden ohne Einnahmen,
  - 1.000 € Wochenmiete bezahlt und unbezahlt,
  - kein Neustart nach dem Tod,
  - Einnahmen in Fremdwährung,
  - nur eine Runde pro Stunde.
