# -*- coding: utf-8 -*-
"""Werkzeug-Register - was JARVIS tun kann und wie jeder Aufruf geprüft wird.

Das Modell hat keine eigenen Werkzeuge. Es schreibt Aktionen in den Text:

    <aktion werkzeug="aufgabe_anlegen" titel="Angebot Berger" prioritaet="hoch"/>
    <aktion werkzeug="datei_schreiben" pfad="notizen/berger.md">Inhalt der Datei</aktion>

JARVIS liest sie, prüft jede Eingabe (Typ, Länge, Auswahl, Pfad) und lässt sie
durch die Berechtigungsschicht (``freigaben.py``) laufen. Erst dann wird
ausgeführt - oder als Freigabe zur Entscheidung des Nutzers gespeichert.

Stufen: 1 frei (innen, umkehrbar), 2 mit Meldung (neue Datei, Websuche),
3 nur nach Freigabe (Überschreiben, Löschen, Recherche im privaten Bereich).

Dateien: nur in der Werkstatt und in ausdrücklich freigegebenen Ordnern, nie in
versteckten Ordnern, nie über ``..`` oder Verknüpfungen hinaus. Gelöscht wird
nichts endgültig: Überschriebenes und Gelöschtes landet im ``.papierkorb`` der
Werkstatt.
"""

import difflib
import hashlib
import os
import re
import shutil
import time
from html import unescape

from . import umgebung, zeit
from .provider import ProviderFehler

FREI, MELDUNG, FREIGABE = 1, 2, 3
STUFEN = {FREI: "frei", MELDUNG: "mit Meldung", FREIGABE: "nur nach Freigabe des Nutzers"}
MAX_INHALT = 200000
MAX_LESEN = 30000
MAX_EINTRAEGE = 100

AKTION = re.compile(r"<aktion\s+([^<>]*?)\s*(?:/>|>(.*?)</aktion>)", re.S)
ATTRIBUT = re.compile(r'([a-z_]+)\s*=\s*"([^"]*)"')


class WerkzeugFehler(Exception):
    """Fehler, den der Nutzer (und das Modell) verstehen soll."""


class Kontext:
    """Wer ruft auf, in welchem Bereich, in welcher Rolle - und war schon Außenwelt im Spiel (``extern``)?"""

    def __init__(self, agent, bereich, gespraech=None, auftrag_id=None, rolle="allgemein", quelle="chat", warten=False,
                 extern=False):
        self.agent = agent
        self.bereich = bereich
        self.gespraech = gespraech
        self.auftrag_id = auftrag_id
        self.rolle = rolle
        self.quelle = quelle  # chat | auftrag | freigabe
        self.warten = warten  # ein Läufer wartet auf Freigaben
        self.extern = extern


class P:
    """Ein Parameter eines Werkzeugs."""

    def __init__(self, name, pflicht=False, art="text", hilfe="", wahl=None, maximal=500):
        self.name, self.pflicht, self.art, self.hilfe, self.wahl, self.maximal = name, pflicht, art, hilfe, wahl, maximal


class Werkzeug:
    def __init__(self, name, beschreibung, handler, parameter=(), stufe=FREI, koerper=None, liefert_daten=False,
                 extern=False, vorschau=None, risiko="", nur_chat=False, privat_freigabe=False, zustand=None):
        self.name = name
        self.beschreibung = beschreibung
        self.handler = handler
        self.parameter = tuple(parameter)
        self.stufe = stufe  # Zahl oder Funktion (ctx, params) -> Zahl
        self.koerper = koerper  # Name des Parameters, der aus dem Text zwischen den Tags kommt
        self.liefert_daten = liefert_daten  # Ergebnis geht ins Modell zurück
        self.extern = extern  # Ergebnis stammt von außen (Web): danach braucht jede Aktion Freigabe
        self.vorschau = vorschau
        self.risiko = risiko
        self.nur_chat = nur_chat
        self.privat_freigabe = privat_freigabe  # im Bereich "privat" immer Stufe 3
        self.zustand = zustand  # Funktion (ctx, params) -> Text: Stand beim Anfragen (Änderungsschutz)

    def stufe_fuer(self, ctx, params):
        return self.stufe(ctx, params) if callable(self.stufe) else self.stufe

    def kurz(self, params):
        teile = [str(params[p.name])[:60] for p in self.parameter if p.name in params and p.name != "inhalt"][:2]
        return "%s %s" % (self.name, " ".join(teile)) if teile else self.name


# ---------------------------------------------------------------- Parsen ---

def aktionen_parsen(text):
    """Trennt Antworttext und Aktionen. Gibt (bereinigter Text, [{name, roh, koerper}]) zurück."""
    aktionen = []

    def sammeln(treffer):
        attribute = {k: unescape(v) for k, v in ATTRIBUT.findall(treffer.group(1))}
        name = attribute.pop("werkzeug", "")
        koerper = treffer.group(2)
        if koerper is not None:
            koerper = re.sub(r"^\r?\n|\r?\n$", "", koerper)
        aktionen.append({"name": name, "roh": attribute, "koerper": koerper})
        return ""

    rein = AKTION.sub(sammeln, text or "")
    return re.sub(r"\n{3,}", "\n\n", rein).strip(), aktionen


# ------------------------------------------------------------ Pfadsicherheit ---

def pfad_aufloesen(konfig, angabe, schreiben=False, muss_existieren=False):
    """Übersetzt eine Pfadangabe ("notizen/a.md" oder "angebote:2026/b.pdf") sicher in einen echten Pfad.

    Gibt (Zielpfad, Basis, Ordnername) zurück. Wirft WerkzeugFehler, wenn der Pfad aus dem erlaubten Ordner
    herausführen würde (``..``, absolute Pfade, versteckte Ordner, Verknüpfungen) oder der Ordner nur lesbar ist.
    """
    angabe = (angabe or "").strip()
    name, relativ = "werkstatt", angabe
    erster = angabe.split("/")[0]
    if ":" in erster:
        name, _, relativ = angabe.partition(":")
        name = name.strip().lower()
    wurzeln = konfig.wurzeln()
    if name not in wurzeln:
        raise WerkzeugFehler("Unbekannter Ordner %r. Möglich: %s." % (name, ", ".join(sorted(wurzeln))))
    basis, darf_schreiben = wurzeln[name]
    if schreiben and not darf_schreiben:
        raise WerkzeugFehler("Der Ordner %r ist nur lesbar." % name)
    if "\x00" in relativ or os.path.isabs(relativ):
        raise WerkzeugFehler("Der Pfad muss relativ zum Ordner %r sein." % name)
    teile = [t for t in relativ.replace("\\", "/").split("/") if t not in ("", ".")]
    if any(t == ".." for t in teile):
        raise WerkzeugFehler("\"..\" ist nicht erlaubt.")
    if any(t.startswith(".") for t in teile):
        raise WerkzeugFehler("Versteckte Dateien und Ordner sind tabu.")
    if name == "werkstatt" or schreiben:
        os.makedirs(basis, exist_ok=True)
    basis_echt = os.path.realpath(basis)
    ziel = os.path.realpath(os.path.join(basis_echt, *teile))
    if ziel != basis_echt and not ziel.startswith(basis_echt + os.sep):
        raise WerkzeugFehler("Der Pfad führt aus dem Ordner %r heraus." % name)
    if muss_existieren and not os.path.exists(ziel):
        raise WerkzeugFehler("%s gibt es nicht." % (angabe or name))
    return ziel, basis_echt, name


def _sha(ziel):
    try:
        with open(ziel, "rb") as f:
            return hashlib.sha256(f.read()).hexdigest()
    except OSError:
        return ""


def _stand_pruefen(ziel, erwartet):
    if erwartet is not None and _sha(ziel) != erwartet:
        raise WerkzeugFehler("Die Datei hat sich seit der Anfrage geändert. Bitte neu anfragen.")


def _in_papierkorb(basis, ziel, kopieren):
    ordner = os.path.join(basis, ".papierkorb")
    os.makedirs(ordner, exist_ok=True)
    ziel_name = "%s_%s" % (time.strftime("%Y%m%d-%H%M%S"), os.path.basename(ziel))
    ablage = os.path.join(ordner, ziel_name)
    (shutil.copy2 if kopieren else shutil.move)(ziel, ablage)
    return os.path.relpath(ablage, basis)


# ------------------------------------------------------------ Handler ---

def _aufgabe_anlegen(ctx, p):
    faellig = p.get("faellig")
    todo_id = ctx.agent.speicher.todo_anlegen(p["titel"], ctx.bereich, p.get("beschreibung", ""),
                                              p.get("prioritaet", "normal"), faellig, quelle="jarvis")
    return {"text": "Aufgabe #%d angelegt: %s" % (todo_id, p["titel"])}


def _aufgabe_status(ctx, p):
    sp = ctx.agent.speicher
    todo = sp.todo(p["id"])
    if not todo or todo["bereich"] != ctx.bereich:  # Aufgaben anderer Bereiche bleiben unsichtbar
        raise WerkzeugFehler("Aufgabe #%d gibt es in diesem Bereich nicht." % p["id"])
    sp.todo_setzen(p["id"], status=p["status"])
    return {"text": "Aufgabe #%d ist jetzt %s: %s" % (p["id"], p["status"], todo["titel"])}


def _erinnerung_setzen(ctx, p):
    if p["faellig"] <= zeit.jetzt():
        raise WerkzeugFehler("Der Zeitpunkt liegt in der Vergangenheit.")
    erinnerung_id = ctx.agent.speicher.erinnerung_anlegen(p["text"], p["faellig"], ctx.bereich)
    return {"text": "Erinnerung #%d gesetzt für %s: %s" % (erinnerung_id, zeit.utc_zu_lokal_text(p["faellig"]), p["text"])}


def _merken(ctx, p):
    fakt_id, neu = ctx.agent.speicher.fakt_hinzufuegen(p["text"], bereich=ctx.bereich, art=p.get("art", "fakt"),
                                                       status="vorschlag", quelle="jarvis")
    if not neu:
        return {"text": "Das kenne ich schon oder hast du schon verworfen (Eintrag #%d)." % fakt_id}
    return {"text": "Als Vorschlag notiert (#%d). Er gilt erst, wenn der Nutzer ihn im Bereich Gedächtnis bestätigt." % fakt_id}


def _auflisten(ctx, p):
    ziel, basis, name = pfad_aufloesen(ctx.agent.konfig, p.get("pfad", ""), muss_existieren=True)
    if not os.path.isdir(ziel):
        raise WerkzeugFehler("Das ist kein Ordner.")
    eintraege = []
    for eintrag in sorted(os.listdir(ziel)):
        if eintrag.startswith("."):
            continue
        voll = os.path.join(ziel, eintrag)
        eintraege.append(eintrag + "/" if os.path.isdir(voll) else "%s (%d Bytes)" % (eintrag, os.path.getsize(voll)))
    rest = max(0, len(eintraege) - MAX_EINTRAEGE)
    text = "\n".join(eintraege[:MAX_EINTRAEGE]) or "(leer)"
    return {"text": "%s:\n%s%s" % (os.path.relpath(ziel, basis) if ziel != basis else name + ":", text,
                                    "\n… und %d weitere" % rest if rest else "")}


def _lesen(ctx, p):
    ziel, _, _ = pfad_aufloesen(ctx.agent.konfig, p["pfad"], muss_existieren=True)
    if not os.path.isfile(ziel):
        raise WerkzeugFehler("%s ist keine Datei." % p["pfad"])
    with open(ziel, "rb") as f:
        daten = f.read(MAX_LESEN + 1)
    if b"\x00" in daten:
        raise WerkzeugFehler("%s ist keine Textdatei." % p["pfad"])
    text = daten[:MAX_LESEN].decode("utf-8", "replace")
    return {"text": text + ("\n… (gekürzt, Datei ist länger)" if len(daten) > MAX_LESEN else "")}


def _schreiben_stufe(ctx, p):
    ziel, _, _ = pfad_aufloesen(ctx.agent.konfig, p["pfad"], schreiben=True)
    return MELDUNG if not os.path.exists(ziel) else FREIGABE


def _schreiben_zustand(ctx, p):
    ziel, _, _ = pfad_aufloesen(ctx.agent.konfig, p["pfad"], schreiben=True)
    return _sha(ziel)


def _schreiben_vorschau(ctx, p):
    ziel, _, _ = pfad_aufloesen(ctx.agent.konfig, p["pfad"], schreiben=True)
    if not os.path.exists(ziel):
        return "Neue Datei %s (%d Zeichen):\n\n%s" % (p["pfad"], len(p["inhalt"]), p["inhalt"][:4000])
    try:
        with open(ziel, "r", encoding="utf-8", errors="replace") as f:
            alt = f.read()
    except OSError:
        alt = ""
    diff = "".join(difflib.unified_diff(alt.splitlines(True), p["inhalt"].splitlines(True), "bisher", "neu", n=2))
    return "Datei %s wird ÜBERSCHRIEBEN (die alte Fassung bleibt im .papierkorb).\n\nÄnderungen:\n%s" % (
        p["pfad"], diff[:6000] or "(kein Unterschied im Text)")


def _schreiben(ctx, p):
    ziel, basis, _ = pfad_aufloesen(ctx.agent.konfig, p["pfad"], schreiben=True)
    if os.path.isdir(ziel):
        raise WerkzeugFehler("%s ist ein Ordner." % p["pfad"])
    _stand_pruefen(ziel, p.get("_sha"))
    os.makedirs(os.path.dirname(ziel), exist_ok=True)
    gesichert = _in_papierkorb(basis, ziel, kopieren=True) if os.path.exists(ziel) else None
    zwischen = ziel + ".jarvis-neu"
    with open(zwischen, "w", encoding="utf-8", newline="") as f:
        f.write(p["inhalt"])
    os.replace(zwischen, ziel)
    with open(ziel, "r", encoding="utf-8", newline="") as f:
        if f.read() != p["inhalt"]:
            raise WerkzeugFehler("Das Schreiben konnte nicht bestätigt werden.")
    return {"text": "Geschrieben und geprüft: %s (%d Zeichen)%s" % (
        p["pfad"], len(p["inhalt"]), "; alte Fassung: %s" % gesichert if gesichert else "")}


def _loeschen_zustand(ctx, p):
    ziel, _, _ = pfad_aufloesen(ctx.agent.konfig, p["pfad"], schreiben=True, muss_existieren=True)
    return _sha(ziel)


def _loeschen_vorschau(ctx, p):
    return "Datei %s wird in den Papierkorb der Werkstatt verschoben. Sie wird NICHT endgültig gelöscht." % p["pfad"]


def _loeschen(ctx, p):
    ziel, basis, _ = pfad_aufloesen(ctx.agent.konfig, p["pfad"], schreiben=True, muss_existieren=True)
    if not os.path.isfile(ziel):
        raise WerkzeugFehler("%s ist keine Datei. Ordner werden nicht gelöscht." % p["pfad"])
    _stand_pruefen(ziel, p.get("_sha"))
    return {"text": "In den Papierkorb verschoben: %s -> %s" % (p["pfad"], _in_papierkorb(basis, ziel, kopieren=False))}


def _recherche_vorschau(ctx, p):
    return "Websuche mit dieser Frage:\n\n%s\n\nDie Frage verlässt den Mac und geht an eine Websuche." % p["frage"]


def _recherche(ctx, p):
    try:
        ergebnis = ctx.agent.provider.recherchieren(p["frage"], auftrag_id=ctx.auftrag_id)
    except ProviderFehler as fehler:
        raise WerkzeugFehler("Recherche nicht möglich: %s" % fehler) from None
    return {"text": ergebnis["antwort"][:8000]}


def _umgebung(ctx, p):
    info = umgebung.sammeln(ctx.agent.konfig)
    ctx.agent.umgebung_merken(info)
    return {"text": "\n".join(umgebung.zeilen(info))}


def _auftrag_planen(ctx, p):
    ergebnis = ctx.agent.planer.erstellen(p["ziel"], ctx.bereich, gespraech=ctx.gespraech)
    return {"text": ergebnis["text"]}


# ------------------------------------------------------------ Register ---

class Register:
    def __init__(self, agent):
        self.agent = agent
        self._werkzeuge = {}
        for w in self._standard():
            self._werkzeuge[w.name] = w

    @staticmethod
    def _standard():
        pfad = P("pfad", True, hilfe="Datei oder Ordner, z. B. notizen/a.md oder angebote:2026/b.txt", maximal=300)
        return [
            Werkzeug("aufgabe_anlegen", "Legt eine Aufgabe für den Nutzer an.", _aufgabe_anlegen, [
                P("titel", True, maximal=200), P("beschreibung", maximal=2000),
                P("prioritaet", art="wahl", wahl=("hoch", "normal", "niedrig")),
                P("faellig", art="datum", hilfe="JJJJ-MM-TT oder JJJJ-MM-TT HH:MM, Ortszeit")]),
            Werkzeug("aufgabe_status", "Hakt eine Aufgabe ab oder öffnet sie wieder.", _aufgabe_status, [
                P("id", True, art="zahl"), P("status", True, art="wahl", wahl=("offen", "erledigt"))]),
            Werkzeug("erinnerung_setzen", "Setzt eine Erinnerung; zur Zeit meldet JARVIS sie laut und per Mitteilung.",
                     _erinnerung_setzen, [P("text", True, maximal=300),
                                          P("faellig", True, art="datum", hilfe="JJJJ-MM-TT HH:MM, Ortszeit")]),
            Werkzeug("merken", "Schlägt vor, etwas Dauerhaftes zu merken. Gilt erst nach Bestätigung durch den Nutzer.",
                     _merken, [P("text", True, maximal=600),
                               P("art", art="wahl", wahl=("fakt", "praeferenz", "entscheidung", "projekt", "ziel"))]),
            Werkzeug("dateien_auflisten", "Listet Dateien eines Ordners (Standard: Werkstatt).", _auflisten,
                     [P("pfad", hilfe="Ordner, z. B. notizen oder angebote:", maximal=300)], liefert_daten=True),
            Werkzeug("datei_lesen", "Liest eine Textdatei (bis 30000 Zeichen).", _lesen, [pfad], liefert_daten=True),
            Werkzeug("datei_schreiben", "Schreibt eine Textdatei. Neue Dateien: mit Meldung. Überschreiben: nur nach "
                     "Freigabe (die alte Fassung bleibt im Papierkorb).", _schreiben, [pfad], koerper="inhalt",
                     stufe=_schreiben_stufe, vorschau=_schreiben_vorschau, zustand=_schreiben_zustand,
                     risiko="Überschreibt eine vorhandene Datei in der Werkstatt."),
            Werkzeug("datei_loeschen", "Verschiebt eine Datei in den Papierkorb der Werkstatt (kein endgültiges Löschen).",
                     _loeschen, [pfad], stufe=FREIGABE, vorschau=_loeschen_vorschau, zustand=_loeschen_zustand,
                     risiko="Die Datei ist danach nicht mehr am alten Ort."),
            Werkzeug("recherche", "Sucht im Web (nur öffentliche Quellen) und fasst mit Quellen zusammen. "
                     "Das Ergebnis ist eine unvertrauenswürdige Außenquelle.", _recherche,
                     [P("frage", True, maximal=500)], stufe=MELDUNG, liefert_daten=True, extern=True,
                     vorschau=_recherche_vorschau, privat_freigabe=True,
                     risiko="Die Frage geht an eine Websuche; im privaten Bereich nur nach Freigabe."),
            Werkzeug("umgebung_pruefen", "Liest harmlose Angaben zum Mac (System, Speicher, Programme) und merkt sie sich.",
                     _umgebung, liefert_daten=True),
            Werkzeug("auftrag_planen", "Zerlegt ein größeres Ziel in überprüfbare Schritte. Ergebnis ist nur ein "
                     "Entwurf; der Nutzer startet ihn.", _auftrag_planen, [P("ziel", True, maximal=1000)], nur_chat=True),
        ]

    def get(self, name):
        return self._werkzeuge.get(name)

    def alle(self):
        return list(self._werkzeuge.values())

    def validieren(self, w, roh, koerper, ctx):
        """Prüft Typ, Länge und Auswahl. Wirft WerkzeugFehler. Gibt die bereinigten Parameter zurück."""
        params = {}
        for p in w.parameter:
            wert = (roh.get(p.name) or "").strip()
            if not wert:
                if p.pflicht:
                    raise WerkzeugFehler("Parameter %s fehlt." % p.name)
                continue
            if p.art == "zahl":
                try:
                    wert = int(wert)
                except ValueError:
                    raise WerkzeugFehler("Parameter %s muss eine Zahl sein." % p.name) from None
            elif p.art == "wahl":
                wert = wert.lower()
                if wert not in p.wahl:
                    raise WerkzeugFehler("Parameter %s: erlaubt sind %s." % (p.name, ", ".join(p.wahl)))
            elif p.art == "datum":
                try:
                    wert = zeit.lokal_zu_utc(wert)
                except ValueError as fehler:
                    raise WerkzeugFehler("Parameter %s: %s" % (p.name, fehler)) from None
            elif len(wert) > p.maximal:
                raise WerkzeugFehler("Parameter %s ist zu lang (höchstens %d Zeichen)." % (p.name, p.maximal))
            params[p.name] = wert
        if w.koerper:
            if koerper is None or not koerper.strip():
                raise WerkzeugFehler("Der Inhalt fehlt (Text zwischen <aktion …> und </aktion>).")
            if len(koerper) > MAX_INHALT:
                raise WerkzeugFehler("Der Inhalt ist zu lang (höchstens %d Zeichen)." % MAX_INHALT)
            params[w.koerper] = koerper
        if w.zustand:
            params["_sha"] = w.zustand(ctx, params)
        return params

    def katalog(self, rolle="allgemein"):
        """Beschreibung der erlaubten Werkzeuge für den Systemprompt."""
        zeilen = []
        for w in self._werkzeuge.values():
            if not self.agent.berechtigung.sichtbar(w, rolle):
                continue
            teile = []
            for p in w.parameter:
                zusatz = " (%s)" % "|".join(p.wahl) if p.wahl else (" (%s)" % p.hilfe if p.hilfe else "")
                teile.append("%s%s%s" % (p.name, "*" if p.pflicht else "", zusatz))
            if w.koerper:
                teile.append("Text zwischen den Tags = %s*" % w.koerper)
            stufe = w.stufe_fuer(None, None) if not callable(w.stufe) else None
            hinweis = STUFEN[stufe] if stufe else "frei, mit Meldung oder nur nach Freigabe (je nach Fall)"
            zeilen.append("- %s: %s Parameter: %s. Stufe: %s." % (w.name, w.beschreibung, "; ".join(teile) or "keine", hinweis))
        return "\n".join(zeilen)
