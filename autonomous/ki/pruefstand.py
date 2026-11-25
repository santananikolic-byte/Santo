# -*- coding: utf-8 -*-
"""Prüfstand für die „Intelligenz“ lokaler Modelle – Fälle aus dem echten Arbeitsalltag (pruefstand_faelle.json).

- Jeder Fall: Aufgabe (wie AUTONOMOUS sie stellt), Daten (Fremdtext immer als markierte Daten), feste Prüfungen.
- Bewertung DETERMINISTISCH nach Regeln und Mustern: Deutsch? Länge? Satzzahl? Pflichtinhalte? Verbotenes?
  Neue Fakten (Faktenwächter)? Zusagen? Platzhalter? Ergebnis: Punkte je Fall und gesamt. Keine KI bewertet KI.
- Fälle mit „vorlage“ nutzen GENAU die Vorlage der Agenten (Sales-Feinschliff, CEO-Kurzfassung).
- Als Agenten-Aufgabe (Research, Typ „ki_pruefstand“): jeder Aufruf läuft über die Modellschicht (Tageslimit,
  Protokoll). Ergebnis: Vorschlag im Gedächtnis („Bestes Modell für euch: …“) – es wird NIE automatisch umgeschaltet.

Kommandozeile (direkt gegen Ollama, ohne Datenbank und Tageslimit – für Entwickler und eigene Vergleiche):
    python3 -m autonomous.ki.pruefstand gemma3:1b gemma3:4b autonomous [--adresse http://127.0.0.1:11434] [--json x]
"""

import json
import os
import re
import time
import unicodedata

from . import ausgabe, faktenwaechter, modelfile, vorlagen

FAELLE_DATEI = os.path.join(os.path.dirname(os.path.abspath(__file__)), "pruefstand_faelle.json")
MAX_ZEICHEN = 1500          # Antwortlänge je Fall (→ höchstens 500 Token)
ZEITLIMIT = 180             # Sekunden je Fall
MAX_MODELLE = 6
ANTWORT_GESPEICHERT = 600   # Zeichen je Antwort im Ergebnis
MIN_ZEICHEN_VERBOTE = 10    # kürzere Antworten bekommen keine Punkte dafür, „nichts Falsches“ gesagt zu haben
PRUEFUNGEN = ("deutsch", "laenge", "saetze_max", "enthaelt_eins", "enthaelt_alle", "enthaelt_nicht",
              "keine_neuen_fakten", "keine_zusagen", "platzhalter_behalten", "hat_platzhalter")
VERBOTE = ("enthaelt_nicht", "keine_neuen_fakten", "keine_zusagen")
VORLAGEN = {"nachricht_feinschliff": (("betreff", "text"),
                                      lambda d: vorlagen.nachricht_feinschliff(d["betreff"], d["text"])),
            "tagesplan_kurzfassung": (("tagesplan",), lambda d: vorlagen.tagesplan_kurzfassung(d["tagesplan"]))}
_DEUTSCH = frozenset(("der die das und ist nicht wir sie ich ein eine einen einem zu mit für auf von den dem des im am "
                      "es bitte gern gerne ihr ihre ihnen uns unser unsere dass oder auch noch wie was wird werden "
                      "kann können sind hat haben bei aus nach über sehr guten tag vielen dank weiß keine kein zum "
                      "zur wenn diese dieser dieses gibt mir").split())
_ENGLISCH = frozenset(("the and is are you we to of for with this that please our your will can be have has it not "
                       "do does hello thank thanks regards dear yes no would could should").split())
_ABKUERZUNG = re.compile(r"\b(?:z\. ?b|u\. ?a|d\. ?h|bzw|ca|usw|nr|inkl|evtl|ggf|str|tel|vgl|bzgl)\.", re.I)
_SATZENDE = re.compile(r"(?<![\d])[.!?]+(?=\s|$)|(?<=\d{4})\.(?=\s|$)|[!?]+")


# ---------------------------------------------------------------------------------------------- Fälle
def faelle_laden(pfad=None):
    """Lädt und prüft die Fallsammlung. Fehler in der Datei → ValueError (nie halb geprüfte Fälle)."""
    with open(pfad or FAELLE_DATEI, encoding="utf-8") as f:
        try:
            daten = json.load(f)
        except ValueError as fehler:
            raise ValueError("Fallsammlung ist kein gültiges JSON: %s" % fehler)
    faelle = daten.get("faelle") if isinstance(daten, dict) else None
    if not isinstance(faelle, list) or not faelle:
        raise ValueError("Fallsammlung braucht eine nicht leere Liste „faelle“.")
    gesehen = set()
    for fall in faelle:
        _fall_pruefen(fall, gesehen)
    return faelle


def _fall_pruefen(fall, gesehen):
    if not isinstance(fall, dict) or not re.fullmatch(r"[a-z0-9_]{2,60}", str(fall.get("id", ""))):
        raise ValueError("Fall ohne gültige id: %r" % (fall.get("id") if isinstance(fall, dict) else fall))
    fid = fall["id"]
    if fid in gesehen:
        raise ValueError("Doppelte Fall-id: %s" % fid)
    gesehen.add(fid)
    for feld in ("titel", "aufgabe"):
        if not isinstance(fall.get(feld), str) or not fall[feld].strip():
            raise ValueError("Fall %s: Feld „%s“ fehlt." % (fid, feld))
    if "vorlage" in fall:
        if fall["vorlage"] not in VORLAGEN or not isinstance(fall.get("daten"), dict) or not all(
                isinstance(fall["daten"].get(s), str) for s in VORLAGEN[fall["vorlage"]][0]):
            raise ValueError("Fall %s: Vorlage unbekannt oder Daten unvollständig." % fid)
    pruefungen = fall.get("pruefungen")
    if not isinstance(pruefungen, list) or not pruefungen:
        raise ValueError("Fall %s: keine Prüfungen." % fid)
    for p in pruefungen:
        if not isinstance(p, dict) or p.get("art") not in PRUEFUNGEN:
            raise ValueError("Fall %s: unbekannte Prüfung %r." % (fid, p.get("art") if isinstance(p, dict) else p))
        if isinstance(p.get("punkte"), bool) or not isinstance(p.get("punkte"), int) or not 1 <= p["punkte"] <= 5:
            raise ValueError("Fall %s: Punkte 1 bis 5 nötig (%s)." % (fid, p["art"]))
        if p["art"].startswith("enthaelt_"):
            muster = p.get("muster")
            if not isinstance(muster, list) or not muster or not all(isinstance(m, str) for m in muster):
                raise ValueError("Fall %s: Muster fehlen (%s)." % (fid, p["art"]))
            for m in muster:
                try:
                    re.compile(m)
                except re.error as fehler:
                    raise ValueError("Fall %s: ungültiges Muster %r (%s)." % (fid, m, fehler))
        if p["art"] == "laenge" and not (isinstance(p.get("min"), int) and isinstance(p.get("max"), int)
                                         and 0 <= p["min"] < p["max"]):
            raise ValueError("Fall %s: laenge braucht min < max." % fid)
        if p["art"] == "saetze_max" and not (isinstance(p.get("max"), int) and p["max"] >= 1):
            raise ValueError("Fall %s: saetze_max braucht max." % fid)


def anfrage(fall):
    """(system, nutzer) genau wie im Betrieb: Vorlage der Agenten oder Aufgabe plus markierte Daten."""
    if "vorlage" in fall:
        return VORLAGEN[fall["vorlage"]][1](fall["daten"])
    return vorlagen.pruefstand_anfrage(fall["aufgabe"], fall.get("daten"))


def _flach(wert):
    if isinstance(wert, dict):
        return "\n".join(_flach(v) for v in wert.values())
    if isinstance(wert, list):
        return "\n".join(_flach(v) for v in wert)
    return "" if wert is None else str(wert)


def eingabe_text(fall):
    """Alles, was das Modell an Fakten bekommt – Grundlage für Faktenwächter, Zusagen und Platzhalter."""
    return (fall["aufgabe"] if "vorlage" not in fall else "") + "\n" + _flach(fall.get("daten"))


# ---------------------------------------------------------------------------------------------- Bewertung
def _normal(text):
    t = unicodedata.normalize("NFKC", str(text or "")).lower()
    t = re.sub(r"[*_`#]+", " ", t)
    return re.sub(r"\s+", " ", t).strip()


def ist_deutsch(text):
    woerter = re.findall(r"[a-zäöüß]+", _normal(text))
    de = sum(1 for w in woerter if w in _DEUTSCH)
    en = sum(1 for w in woerter if w in _ENGLISCH)
    if de >= 2 and de >= 2 * en:
        return True
    # Aufzählungen ohne Füllwörter (z. B. nur Titel): Deutsch, wenn kein englisches Wort und deutsche Merkmale
    merkmale = sum(1 for w in woerter if re.search(r"[äöüß]|(?:ung|keit|heit|schaft|lich|isch)$", w))
    return en == 0 and merkmale >= 2


def saetze(text):
    """Grobe Satzzahl: Satzzeichen am Satzende (nicht nach Tag/Ordnungszahl wie „8.“, nicht in „z. B.“) plus Zeilen
    ohne Satzzeichen am Ende (z. B. Aufzählungspunkte)."""
    anzahl = 0
    for zeile in _ABKUERZUNG.sub(" ", unicodedata.normalize("NFKC", str(text or ""))).splitlines():
        zeile = re.sub(r"^[\s*•\-]*(?:\d{1,2}[.)]\s+)?", "", zeile).strip()
        if not zeile:
            continue
        enden = list(_SATZENDE.finditer(zeile))
        anzahl += len(enden)
        if not enden or enden[-1].end() < len(zeile.rstrip()):
            anzahl += 1
    return anzahl


def _pruefen(p, antwort, eingabe):
    """(ok, hinweis) für eine Prüfung."""
    art, t = p["art"], _normal(antwort)
    if art == "deutsch":
        return ist_deutsch(antwort), "Antwort auf Deutsch"
    if art == "laenge":
        n = len(antwort.strip())
        return p["min"] <= n <= p["max"], "Länge %d Zeichen (erlaubt %d–%d)" % (n, p["min"], p["max"])
    if art == "saetze_max":
        n = saetze(antwort)
        return n <= p["max"], "%d Sätze (höchstens %d)" % (n, p["max"])
    if art == "enthaelt_eins":
        return any(re.search(m, t) for m in p["muster"]), p.get("hinweis") or "enthält einen Pflichtinhalt"
    if art == "enthaelt_alle":
        fehlt = [m for m in p["muster"] if not re.search(m, t)]
        return not fehlt, p.get("hinweis") or ("fehlt: " + ", ".join(fehlt) if fehlt else "alle Pflichtinhalte")
    if art == "enthaelt_nicht":
        treffer = [re.search(m, t).group(0) for m in p["muster"] if re.search(m, t)]
        return not treffer, (p.get("hinweis") or "nichts Verbotenes") + (
            ": „%s“" % faktenwaechter.zeigbar(treffer[0][:40]) if treffer else "")
    if art == "keine_neuen_fakten":
        funde = faktenwaechter.befunde(antwort, eingabe)
        return not funde, ("neu erfunden: " + faktenwaechter.kurz(funde)) if funde else "keine neuen Fakten"
    if art == "keine_zusagen":
        funde = faktenwaechter.neue_zusagen(antwort, eingabe)
        return not funde, ("Zusage: " + faktenwaechter.kurz(funde)) if funde else "keine Zusagen"
    if art == "platzhalter_behalten":
        funde = faktenwaechter.fehlende_teile(antwort, faktenwaechter.platzhalter(eingabe))
        return not funde, ("Platzhalter fehlen: " + faktenwaechter.kurz(funde)) if funde else "alle Platzhalter da"
    if art == "hat_platzhalter":
        return bool(faktenwaechter.platzhalter(antwort)), "fehlende Angaben als [Platzhalter]"
    raise ValueError("Unbekannte Prüfung: %s" % art)


def bewerten(fall, antwort):
    """Punkte für eine Antwort – nur Regeln und Muster, keine KI. Leere Antwort = 0 Punkte."""
    antwort = str(antwort or "")
    eingabe = eingabe_text(fall)
    zu_kurz = len(antwort.strip()) < MIN_ZEICHEN_VERBOTE
    ergebnisse, punkte, maximal, kritisch = [], 0, 0, 0
    for p in fall["pruefungen"]:
        maximal += p["punkte"]
        if not antwort.strip():
            ok, hinweis = False, "keine Antwort"
        else:
            ok, hinweis = _pruefen(p, antwort, eingabe)
            if not ok and p.get("kritisch"):
                kritisch += 1          # ein vorhandener Verstoß zählt immer – auch in einer sehr kurzen Antwort
            elif ok and zu_kurz and p["art"] in VERBOTE:
                ok, hinweis = False, "Antwort zu kurz – zählt nicht als „nichts Falsches gesagt“"
        punkte += p["punkte"] if ok else 0
        ergebnisse.append({"art": p["art"], "ok": ok, "punkte": p["punkte"] if ok else 0, "max": p["punkte"],
                           "kritisch": bool(p.get("kritisch")), "hinweis": hinweis})
    return {"id": fall["id"], "titel": fall["titel"], "punkte": punkte, "max": maximal, "kritisch_verletzt": kritisch,
            "pruefungen": ergebnisse}


def _antwort_speichern(antwort):
    from ..protokoll import sieht_nach_geheimnis_aus
    if sieht_nach_geheimnis_aus(antwort):
        return "[Antwort nicht gespeichert: enthielt ein Muster wie ein Passwort oder einen Schlüssel]"
    return antwort[:ANTWORT_GESPEICHERT] + (" …" if len(antwort) > ANTWORT_GESPEICHERT else "")


def pruefen(aufrufer, faelle, modell):
    """Alle Fälle gegen ein Modell. aufrufer(system, nutzer) → Text. Ein Fehler kostet nur diesen Fall."""
    ergebnisse, beginn = [], time.monotonic()
    for fall in faelle:
        start = time.monotonic()
        fehler = None
        try:
            antwort = ausgabe.saeubern(aufrufer(*anfrage(fall)), MAX_ZEICHEN)
        except Exception as f:  # ein Fall darf den Prüfstand nicht beenden – Fehler steht im Ergebnis
            antwort, fehler = "", ("%s: %s" % (type(f).__name__, f))[:300]
        e = bewerten(fall, antwort)
        for p in e["pruefungen"]:  # zweites Netz: Hinweise zitieren Modelltext
            p["hinweis"] = faktenwaechter.zeigbar(p["hinweis"])
        e.update(dauer_ms=int((time.monotonic() - start) * 1000), antwort=_antwort_speichern(antwort), fehler=fehler)
        ergebnisse.append(e)
    punkte, maximal = sum(e["punkte"] for e in ergebnisse), sum(e["max"] for e in ergebnisse)
    return {"modell": modell, "punkte": punkte, "max": maximal,
            "prozent": int(round(100.0 * punkte / maximal)) if maximal else 0,
            "kritisch": sum(e["kritisch_verletzt"] for e in ergebnisse),
            "fehler": sum(1 for e in ergebnisse if e["fehler"]),
            "dauer_s": round(time.monotonic() - beginn, 1), "faelle": ergebnisse}


def bestes_modell(ergebnisse):
    """Höchster Anteil; bei Gleichstand weniger kritische Verstöße, dann schneller. Ohne Antworten: None."""
    kandidaten = [e for e in ergebnisse if e["fehler"] < len(e["faelle"])]
    if not kandidaten:
        return None
    return sorted(kandidaten, key=lambda e: (-e["prozent"], e["kritisch"], e["dauer_s"]))[0]


def empfehlung(ergebnisse, beste, anzahl_faelle):
    if beste is None:
        return ("Kein Modell hat im Prüfstand geantwortet – die KI bleibt besser aus. AUTONOMOUS schaltet nie "
                "automatisch um.")
    teile = ["Bestes Modell für euch laut Prüfstand: %s (%d von %d Punkten, %d %%, kritische Verstöße: %d)."
             % (beste["modell"], beste["punkte"], beste["max"], beste["prozent"], beste["kritisch"])]
    if beste["prozent"] < 50:
        teile.append("Achtung: Kein Modell erreicht die Hälfte der Punkte – KI-Texte nur als Lesehilfe nutzen.")
    andere = ["%s %d %%" % (e["modell"], e["prozent"]) for e in ergebnisse if e is not beste]
    if andere:
        teile.append("Weitere: %s." % ", ".join(andere))
    teile.append("%d Fälle aus dem Arbeitsalltag, Bewertung nach festen Regeln." % anzahl_faelle)
    teile.append("Nur ein Vorschlag: AUTONOMOUS schaltet nie automatisch um – umschalten könnt ihr selbst unter "
                 "Einstellungen → KI-Modell.")
    return " ".join(teile)


# ---------------------------------------------------------------------------------------------- Agenten-Aufgabe
class _MitModell:
    """Einstellungen wie im System, nur mit anderem Modellnamen – liest nur, ändert nie etwas."""

    def __init__(self, einstellungen, modell):
        self._einstellungen = einstellungen
        self._modell = modell

    def alle(self):
        werte = dict(self._einstellungen.alle())
        werte["ollama_modell"] = self._modell
        return werte

    def hole(self, schluessel):
        return self.alle()[schluessel]


def modelle_waehlen(wunsch, installiert):
    """Gewünschte Modelle auf installierte Namen abbilden („autonomous“ → „autonomous:latest“)."""
    if not wunsch:
        auswahl = [m for m in installiert if "embed" not in m.lower()][:4]
        if not auswahl:
            raise ValueError("In Ollama ist kein Modell installiert – zuerst eins laden (z. B. ollama pull gemma3:1b).")
        return auswahl
    if not isinstance(wunsch, list) or len(wunsch) > MAX_MODELLE:
        raise ValueError("modelle muss eine Liste mit höchstens %d Namen sein." % MAX_MODELLE)
    auswahl = []
    for name in wunsch:
        if not modelfile.modellname_ok(name):
            raise ValueError("Ungültiger Modellname: %r" % (name,))
        echt = name if name in installiert else (name + ":latest" if ":" not in name and name + ":latest"
                                                 in installiert else None)
        if echt is None:
            raise ValueError("Modell %s ist nicht installiert – zuerst im Terminal: ollama pull %s" % (name, name))
        if echt in auswahl:
            raise ValueError("Modell %s steht doppelt in der Liste." % name)
        auswahl.append(echt)
    return auswahl


def aufgabe_ausfuehren(agent, aufgabe, k):
    """Research-Aufgabe „ki_pruefstand“: Modelle vergleichen, Vorschlag ins Gedächtnis – nie umschalten."""
    from ..modell import Modellschicht
    e = k.einstellungen.alle()
    if e["modell_anbieter"] != "ollama":
        raise ValueError("Kein lokales Modell eingestellt – zuerst in den Einstellungen den Anbieter „ollama“ wählen.")
    faelle = faelle_laden()
    st = k.modell.pruefen()
    if not st.get("erreichbar"):
        raise ValueError("Ollama ist nicht erreichbar: %s" % st.get("hinweis"))
    modelle = modelle_waehlen((aufgabe["eingabe"] or {}).get("modelle"), st.get("installierte_modelle") or [])
    noetig, frei = len(faelle) * len(modelle), e["modell_max_aufrufe_tag"] - k.modell.aufrufe_heute()
    if noetig > frei:
        raise ValueError("Für den Prüfstand werden %d Modellaufrufe gebraucht (%d Fälle × %d Modelle), heute sind noch "
                         "%d frei. Tageslimit in den Einstellungen erhöhen oder morgen erneut starten."
                         % (noetig, len(faelle), len(modelle), max(0, frei)))
    agent.darf(k, "lokales_modell", "ki_pruefstand", aufgabe)
    ergebnisse = []
    for name in modelle:
        schicht = Modellschicht(k.db, k.protokoll, _MitModell(k.einstellungen, name))

        def aufrufer(system, nutzer, schicht=schicht):
            return schicht.frage(nutzer, agent.rolle, aufgabe_id=aufgabe["id"], max_zeichen=MAX_ZEICHEN,
                                 zeitlimit=ZEITLIMIT, system=system)
        ergebnisse.append(pruefen(aufrufer, faelle, name))
    beste = bestes_modell(ergebnisse)
    text = empfehlung(ergebnisse, beste, len(faelle))
    agent.darf(k, "gedaechtnis_vorschlag", "ki_pruefstand", aufgabe)
    k.gedaechtnis.merken("vorschlag", "KI-Modell (Prüfstand)", text, "research:ki_pruefstand %s" % aufgabe["id"],
                         agent.rolle, aufgabe["id"])
    return {"modelle": ergebnisse, "bestes_modell": beste["modell"] if beste else None, "empfehlung": text,
            "faelle_anzahl": len(faelle), "regeln_eigenes_modell": modelfile.KENNUNG,
            "hinweis": "Nur ein Vorschlag – AUTONOMOUS schaltet das Modell nie automatisch um. Bewertung nach festen "
                       "Regeln (Prüfstand), keine KI bewertet KI."}


# ---------------------------------------------------------------------------------------------- Kommandozeile
def main(argv=None):
    import argparse
    from . import anbieter
    p = argparse.ArgumentParser(prog="python3 -m autonomous.ki.pruefstand",
                                description="Prüfstand direkt gegen Ollama (ohne Datenbank und Tageslimit).")
    p.add_argument("modelle", nargs="+")
    p.add_argument("--adresse", default="http://127.0.0.1:11434")
    p.add_argument("--json", help="vollständiges Ergebnis in diese Datei schreiben")
    a = p.parse_args(argv)
    faelle = faelle_laden()
    ergebnisse = []
    for name in a.modelle:
        modell = anbieter.OllamaAnbieter(a.adresse, name)

        def aufrufer(system, nutzer, modell=modell):
            return modell.erzeugen(system, nutzer, MAX_ZEICHEN, ZEITLIMIT)
        e = pruefen(aufrufer, faelle, name)
        ergebnisse.append(e)
        print("%-22s %3d/%3d Punkte  %3d %%  kritisch %2d  Fehler %d  %6.1f s"
              % (name, e["punkte"], e["max"], e["prozent"], e["kritisch"], e["fehler"], e["dauer_s"]), flush=True)
    print(empfehlung(ergebnisse, bestes_modell(ergebnisse), len(faelle)))
    if a.json:
        with open(a.json, "w", encoding="utf-8") as f:
            json.dump({"modelle": ergebnisse, "faelle_anzahl": len(faelle)}, f, ensure_ascii=False, indent=1)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
