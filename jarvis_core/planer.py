# -*- coding: utf-8 -*-
"""Planer - macht aus einem Ziel überprüfbare Schritte.

Vor dem Planen wird das relevante Gedächtnis des Bereichs geholt. Das Modell
liefert JSON: Schritte mit Rolle, Anweisung, Erfolgskriterium, optionaler
Datei, die danach existieren muss, und Abhängigkeiten. Fehlen wesentliche
Angaben, kommen stattdessen Rückfragen. JARVIS prüft den Plan selbst (Anzahl,
Rollen, Reihenfolge der Abhängigkeiten, Dateipfade) und bittet das Modell bei
Mängeln einmal um Korrektur.

Ergebnis ist immer nur ein **Entwurf**: Er läuft erst, wenn der Nutzer ihn
startet.
"""

from . import gedaechtnis, rollen
from .jsonhilfe import json_finden
from .provider import ProviderFehler
from .werkzeuge import WerkzeugFehler, pfad_aufloesen

PLANER_SYSTEM = ("Du bist der Planer von JARVIS. Du zerlegst ein Ziel des Nutzers in wenige, überprüfbare Schritte. "
                 "Du führst nichts aus. Antworte AUSSCHLIESSLICH mit einem JSON-Objekt, ohne Text davor oder danach.")


class PlanFehler(Exception):
    pass


def plan_pruefen(daten, max_schritte, konfig):
    """Prüft einen Plan. Gibt {"titel", "schritte"} oder {"rueckfragen"} zurück; wirft PlanFehler bei Mängeln."""
    if not isinstance(daten, dict):
        raise PlanFehler("Die Antwort ist kein JSON-Objekt.")
    rueckfragen = [str(r).strip()[:300] for r in daten.get("rueckfragen") or [] if str(r).strip()][:3]
    schritte = daten.get("schritte")
    if rueckfragen and not schritte:
        return {"rueckfragen": rueckfragen}
    if not isinstance(schritte, list) or not schritte:
        raise PlanFehler("\"schritte\" fehlt oder ist leer.")
    if len(schritte) > max_schritte:
        raise PlanFehler("Zu viele Schritte (%d, erlaubt sind höchstens %d). Fasse zusammen." % (len(schritte), max_schritte))
    erlaubt = rollen.auftragsrollen()
    sauber = []
    for nr, s in enumerate(schritte, 1):
        if not isinstance(s, dict):
            raise PlanFehler("Schritt %d ist kein Objekt." % nr)
        titel, anweisung = str(s.get("titel") or "").strip(), str(s.get("anweisung") or "").strip()
        if not titel or not anweisung:
            raise PlanFehler("Schritt %d braucht \"titel\" und \"anweisung\"." % nr)
        rolle = str(s.get("rolle") or "").strip().lower()
        if rolle not in erlaubt:
            raise PlanFehler("Schritt %d: Rolle %r gibt es nicht. Erlaubt: %s." % (nr, rolle, ", ".join(erlaubt)))
        abhaengig = s.get("abhaengig_von") or []
        if not isinstance(abhaengig, list) or not all(isinstance(n, int) and 1 <= n < nr for n in abhaengig):
            raise PlanFehler("Schritt %d: \"abhaengig_von\" darf nur Nummern früherer Schritte enthalten." % nr)
        datei = str(s.get("datei") or "").strip() or None
        if datei:
            try:
                pfad_aufloesen(konfig, datei, schreiben=True)
            except WerkzeugFehler as fehler:
                raise PlanFehler("Schritt %d: \"datei\" ist ungültig (%s)." % (nr, fehler)) from None
        sauber.append({"nr": nr, "rolle": rolle, "titel": titel[:120], "anweisung": anweisung[:1500],
                       "kriterium": str(s.get("kriterium") or "Der Schritt ist sachlich erledigt und begründet.").strip()[:500],
                       "datei": datei, "abhaengig_von": sorted(set(abhaengig))})
    return {"titel": str(daten.get("titel") or "").strip()[:120], "schritte": sauber}


class Planer:
    def __init__(self, agent):
        self.agent = agent

    def _rollen_text(self):
        zeilen = []
        for name in rollen.auftragsrollen():
            zeilen.append("- %s: %s" % (name, ", ".join(rollen.ROLLEN[name]["werkzeuge"])))
        return "\n".join(zeilen)

    def _prompt(self, ziel, bereich, antworten, fehler):
        a = self.agent
        teile = [gedaechtnis.kontext_text(a.speicher, a.konfig, bereich, ziel), "", "[ZIEL]", ziel]
        if antworten:
            teile += ["[ANTWORTEN DES NUTZERS AUF DEINE RÜCKFRAGEN]", antworten]
        teile += ["", "[VERFÜGBARE ROLLEN UND IHRE WERKZEUGE]", self._rollen_text(), "",
                  "[REGELN]",
                  "- 1 bis %d Schritte. Jeder Schritt wird von GENAU EINER Rolle mit deren Werkzeugen allein erledigt." % a.konfig.max_schritte,
                  "- Es gibt keine Werkzeuge zum Senden, Bezahlen, Bestellen, Installieren oder Ausführen von Programmen. Plane das "
                  "nicht als Schritt; bereite höchstens Entwürfe als Dateien in der Werkstatt vor.",
                  "- \"kriterium\": konkret und prüfbar. \"datei\": optional, Pfad einer Datei in der Werkstatt, die danach existieren "
                  "muss. \"abhaengig_von\": Nummern früherer Schritte, deren Ergebnis dieser Schritt braucht.",
                  "- Fehlen wesentliche Angaben, antworte stattdessen mit {\"rueckfragen\": [\"…\"]} (höchstens 3).",
                  "", "[FORMAT]",
                  '{"titel": "…", "schritte": [{"rolle": "recherche", "titel": "…", "anweisung": "…", "kriterium": "…", '
                  '"datei": "notizen/x.md", "abhaengig_von": []}]}']
        if fehler:
            teile += ["", "Dein letzter Plan war ungültig: %s Antworte erneut, nur mit gültigem JSON." % fehler]
        return "\n".join(teile)

    def erstellen(self, ziel, bereich, gespraech=None, antworten="", ersetze=None):
        """Erstellt einen Planentwurf. Gibt {"ok", "auftrag_id", "status", "text"} zurück; wirft WerkzeugFehler."""
        a = self.agent
        ziel = " ".join((ziel or "").split())[:1000]
        if not ziel:
            raise WerkzeugFehler("Das Ziel fehlt.")
        bereich = gedaechtnis.bereich_pruefen(a.konfig, bereich)
        fehler, plan = "", None
        for _ in range(2):
            try:
                roh = a.provider.fragen(self._prompt(ziel, bereich, antworten, fehler), PLANER_SYSTEM, art="plan")
            except ProviderFehler as problem:
                raise WerkzeugFehler("Planen nicht möglich: %s" % problem) from None
            try:
                plan = plan_pruefen(json_finden(roh["antwort"]), a.konfig.max_schritte, a.konfig)
                break
            except PlanFehler as problem:
                fehler = str(problem)
        if plan is None:
            raise WerkzeugFehler("Der Plan war auch nach einer Korrektur ungültig: %s" % fehler)
        sp = a.speicher
        if "rueckfragen" in plan:
            auftrag_id = sp.auftrag_anlegen(ziel[:80], ziel, bereich, status="rueckfrage", gespraech=gespraech,
                                            rueckfragen=plan["rueckfragen"])
            text = "Vor dem Planen brauche ich Antworten (Auftrag #%d):\n%s" % (
                auftrag_id, "\n".join("%d. %s" % (i, r) for i, r in enumerate(plan["rueckfragen"], 1)))
            status = "rueckfrage"
        else:
            auftrag_id = sp.auftrag_anlegen(plan["titel"] or ziel[:80], ziel, bereich, status="entwurf", gespraech=gespraech)
            for s in plan["schritte"]:
                sp.schritt_anlegen(auftrag_id, s["nr"], s["rolle"], s["titel"], s["anweisung"], s["kriterium"],
                                   datei=s["datei"], abhaengig_von=s["abhaengig_von"])
            schaetzung = min(2 * len(plan["schritte"]), a.konfig.max_aufrufe_pro_auftrag)
            zeilen = ["%d. [%s] %s – Kriterium: %s" % (s["nr"], s["rolle"], s["titel"], s["kriterium"]) for s in plan["schritte"]]
            text = ("Plan #%d erstellt (nur Entwurf): %s\n%s\nGeschätzt etwa %d Modellaufrufe aus deinem Abo-Limit. "
                    "Er startet erst, wenn du ihn im Bereich Aufgaben startest."
                    % (auftrag_id, plan["titel"] or ziel[:80], "\n".join(zeilen), schaetzung))
            status = "entwurf"
        if ersetze:
            sp.auftrag_loeschen(ersetze)
        sp.audit_schreiben("auftrag_geplant", bereich=bereich, details={"status": status, "ziel": ziel[:200]}, auftrag_id=auftrag_id)
        return {"ok": True, "auftrag_id": auftrag_id, "status": status, "text": text}

    def neu_planen(self, auftrag_id, antworten):
        """Nach Rückfragen: mit den Antworten des Nutzers erneut planen."""
        auftrag = self.agent.speicher.auftrag(auftrag_id)
        if not auftrag or auftrag["status"] != "rueckfrage":
            raise WerkzeugFehler("Zu diesem Auftrag gibt es keine offenen Rückfragen.")
        return self.erstellen(auftrag["ziel"], auftrag["bereich"], gespraech=auftrag["gespraech"],
                              antworten=(antworten or "")[:2000], ersetze=auftrag_id)
