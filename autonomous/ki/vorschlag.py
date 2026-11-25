# -*- coding: utf-8 -*-
"""Zusätzlicher KI-Vorschlag für Agenten (Sales: Feinschliff, CEO: Kurzfassung) – abgesichert im Code.

Ablauf: Fremddaten auf Anweisungen prüfen (dann KEIN Aufruf) → nur wenn das Modell erreichbar und installiert ist →
Aufruf über die Modellschicht (Tageslimit, Protokoll, Säubern, Kennzeichnung) → Faktenwächter. Findet der Wächter
etwas, wird der Vorschlag verworfen und das protokolliert. Der deterministische Text des Agenten bleibt IMMER die
Hauptausgabe; der KI-Text löst nie etwas aus.

Der Aufrufer prüft vorher selbst: Modell eingestellt (kern.modell.verfuegbar()) und Recht „lokales_modell“."""

from . import faktenwaechter
from ..protokoll import sieht_nach_geheimnis_aus

HINWEIS_OK = "Zusätzlicher KI-Vorschlag – ungeprüft. Maßgeblich ist der Text oben."


def erstellen(modell, protokoll, agent, aufgabe_id, system, nutzer, eingabe, pflicht=(), max_zeichen=1500,
              zeitlimit=90, original=None):
    """Gibt die Felder zurück, die das Agentenergebnis ergänzen: {"ki_vorschlag", "ki_hinweis"} oder nur
    {"ki_hinweis"} (kein Vorschlag, mit Grund). `original`: Text, den die KI verbessern soll – kommt er (bis auf
    Leerzeichen) unverändert zurück, ist das kein Vorschlag."""
    from ..modell import ModellNichtVerfuegbar

    verdacht = faktenwaechter.verdacht_auf_anweisung(eingabe)
    if verdacht:
        protokoll.warnung(agent, "KI-Vorschlag ausgelassen: Anweisung in den Daten vermutet",
                          {"aufgabe": aufgabe_id, "fundstellen": verdacht[:5]})
        return {"ki_hinweis": "Kein KI-Vorschlag: In den Daten steht ein Text, der wie eine Anweisung an die KI "
                              "aussieht („%s“). Bitte die Quelle prüfen – der Text oben ist vollständig."
                              % verdacht[0][:40]}
    st = modell.pruefen()
    if not (st.get("erreichbar") and st.get("modell_vorhanden")):
        return {"ki_hinweis": "Kein KI-Vorschlag: %s" % (st.get("hinweis") or "lokales Modell nicht erreichbar.")}
    try:
        g = modell.frage_gekennzeichnet(system, nutzer, agent=agent, aufgabe_id=aufgabe_id, max_zeichen=max_zeichen,
                                        zeitlimit=zeitlimit)
    except ModellNichtVerfuegbar as f:
        return {"ki_hinweis": "Kein KI-Vorschlag: %s" % f}
    if not g["text"].strip():
        return {"ki_hinweis": "Kein KI-Vorschlag: Das Modell hat nichts geantwortet."}
    if original is not None and faktenwaechter.gleicher_text(g["text"], original):
        return {"ki_hinweis": "Kein KI-Vorschlag: Das Modell hat den Text nicht verändert."}
    funde = (faktenwaechter.befunde(g["text"], eingabe) + faktenwaechter.neue_zusagen(g["text"], eingabe)
             + faktenwaechter.fehlende_teile(g["text"], pflicht))
    if sieht_nach_geheimnis_aus(g["text"]):
        funde.append({"art": "geheimnis", "wert": "Muster wie Passwort/Schlüssel"})
    if funde:
        protokoll.warnung(agent, "KI-Vorschlag verworfen (Faktenwächter)", {"aufgabe": aufgabe_id, "befunde": funde[:10]})
        hinweis = ("KI-Vorschlag verworfen (Faktenwächter): %s. Der Text oben ist vollständig und unverändert."
                   % faktenwaechter.kurz(funde))
        if sieht_nach_geheimnis_aus(hinweis):  # zweites Netz: nie ein Muster wie ein Schlüssel im Ergebnis
            hinweis = "KI-Vorschlag verworfen (Faktenwächter). Der Text oben ist vollständig und unverändert."
        return {"ki_hinweis": hinweis}
    return {"ki_vorschlag": g, "ki_hinweis": HINWEIS_OK}
