# -*- coding: utf-8 -*-
"""Konfiguration - Datei ``~/.jarvis/config.json``, Umgebungsvariablen gehen vor.

Umgebungsvariablen:
    JARVIS_DATEN      Datenordner (Standard ~/.jarvis)
    JARVIS_PORT       Port (Standard 8770 - der alte Jarvis nutzt 8765)
    JARVIS_LOGSTUFE   DEBUG, INFO, WARNING oder ERROR (Standard INFO)
    JARVIS_MODELL     ein Claude-Modell für ALLE Aufgabenarten, z. B. sonnet
    JARVIS_WERKSTATT  Arbeitsordner für Dateien und Skripte (Standard ~/Jarvis-Werkstatt)
    JARVIS_SAY        Pfad zu einem Ersatz für macOS ``say`` (nur für Tests)

Der Server hört standardmäßig nur auf dieser Maschine. Das WLAN wird erst mit
``"lan": true`` geöffnet - das schaltet ``./jarvis.sh lan an`` nach einer
ausdrücklichen Bestätigung (siehe JARVIS-SERVER.md).
"""

import copy
import json
import os
import re

STANDARD = {
    "host": "127.0.0.1",
    "port": 8770,
    "lan": False,
    "logstufe": "INFO",
    "log_max_bytes": 1000000,
    "log_dateien": 5,
    # Denken: ein Modell je Aufgabenart. "opus" = klügstes, "sonnet" = schneller und schont das Abo-Limit.
    "provider_timeout": 300,
    "modelle": {"chat": "opus", "plan": "opus", "arbeit": "opus", "pruefung": "sonnet", "recherche": "sonnet"},
    "modell_ausweichen": True,
    # Sprache
    "stimme": "",
    "tempo": 185,
    "vorlesen": True,
    "erinnerungen_sprechen": True,
    # Getrennte Datenbereiche. Das Modell sieht pro Gespräch immer nur einen davon.
    "bereiche": ["geschaeft", "privat"],
    # Wo Werkzeuge Dateien anfassen dürfen. Weitere Ordner nur hier eintragen, standardmäßig nur lesend:
    # "ordner": {"angebote": {"pfad": "~/Documents/Angebote", "schreiben": false}}
    "werkstatt": "~/Jarvis-Werkstatt",
    "ordner": {},
    # Internetadressen, die das Werkzeug http_abfrage ansprechen darf (leer = keine).
    "api_domains": [],
    # Einzeln abgeschaltete Werkzeuge ("Rechte widerrufen").
    "deaktivierte_werkzeuge": [],
    # Aufträge und Grenzen
    "max_schritte": 6,
    "max_versuche": 2,
    "max_runden": 3,
    "max_aufrufe_pro_auftrag": 30,
    "freigabe_minuten": 30,
    "skript_timeout": 60,
    "auftraege_automatisch_fortsetzen": False,
    # Schutz
    "anfragen_pro_minute": 20,
    "backup_aufbewahren": 7,
}

ERLAUBTE_HOSTS = ("127.0.0.1", "localhost")
LOGSTUFEN = ("DEBUG", "INFO", "WARNING", "ERROR")
MODELL_ARTEN = ("chat", "plan", "arbeit", "pruefung", "recherche")
RESERVIERTE_BEREICHE = ("allgemein", "technik", "alle")
BEREICH_MUSTER = re.compile(r"^[a-z][a-z0-9_]{1,19}$")
MODELL_MUSTER = re.compile(r"^[a-z0-9][a-z0-9.\-]*$")
NAME_MUSTER = re.compile(r"^[a-z][a-z0-9_]{1,40}$")
DOMAIN_MUSTER = re.compile(r"^[a-z0-9]([a-z0-9.\-]*[a-z0-9])?$")


class KonfigFehler(Exception):
    pass


class Konfig:
    def __init__(self, werte, daten_ordner):
        self.werte = werte
        self.daten_ordner = daten_ordner

    def __getattr__(self, name):
        try:
            return self.__dict__["werte"][name]
        except KeyError:
            raise AttributeError(name) from None

    # ------------------------------------------------------------ Pfade ---

    @property
    def datei(self):
        return os.path.join(self.daten_ordner, "config.json")

    @property
    def log_ordner(self):
        return os.path.join(self.daten_ordner, "logs")

    @property
    def log_datei(self):
        return os.path.join(self.log_ordner, "jarvis.jsonl")

    @property
    def pid_datei(self):
        return os.path.join(self.daten_ordner, "jarvis.pid")

    @property
    def db_datei(self):
        return os.path.join(self.daten_ordner, "jarvis.db")

    @property
    def token_datei(self):
        return os.path.join(self.daten_ordner, "token")

    @property
    def backup_ordner(self):
        return os.path.join(self.daten_ordner, "backups")

    @property
    def adresse(self):
        return "http://%s:%d" % (self.host, self.port)

    @property
    def bind_adresse(self):
        return "0.0.0.0" if self.lan else self.host  # noqa: S104 - nur bei ausdrücklich eingeschaltetem lan

    @property
    def werkstatt_pfad(self):
        return os.path.abspath(os.path.expanduser(self.werkstatt))

    def wurzeln(self):
        """Alle Ordner, in denen Dateiwerkzeuge arbeiten dürfen: {name: (pfad, schreiben)}."""
        wurzeln = {"werkstatt": (self.werkstatt_pfad, True)}
        for name, angaben in self.ordner.items():
            wurzeln[name] = (os.path.abspath(os.path.expanduser(angaben["pfad"])), bool(angaben.get("schreiben")))
        return wurzeln

    def modell_fuer(self, art):
        return self.modelle.get(art) or self.modelle.get("chat") or ""

    def alle_bereiche(self):
        """Bereiche, in denen Daten liegen dürfen: die eigenen plus allgemein und technik."""
        return list(self.bereiche) + ["allgemein", "technik"]

    # --------------------------------------------------------- Ändern ---

    def aktualisieren(self, neu):
        """Übernimmt geänderte Werte nach Prüfung und speichert sie. Wirft KonfigFehler."""
        kandidat = copy.deepcopy(self.werte)
        kandidat.update(neu)
        geprueft = normalisieren(kandidat, self.daten_ordner)
        self.werte.clear()
        self.werte.update(geprueft)
        speichern_werte(self)


def daten_ordner_ermitteln():
    return os.path.expanduser(os.environ.get("JARVIS_DATEN") or "~/.jarvis")


def _ganzzahl(werte, name, minimum, maximum):
    try:
        zahl = int(werte[name])
    except (TypeError, ValueError):
        raise KonfigFehler("%s muss eine Zahl sein, nicht %r." % (name, werte[name])) from None
    if not minimum <= zahl <= maximum:
        raise KonfigFehler("%s muss zwischen %d und %d liegen, nicht %d." % (name, minimum, maximum, zahl))
    werte[name] = zahl


def _liste(werte, name, maximum):
    if not isinstance(werte[name], list):
        raise KonfigFehler("%s muss eine Liste sein." % name)
    if len(werte[name]) > maximum:
        raise KonfigFehler("%s darf höchstens %d Einträge haben." % (name, maximum))


def _ordner_pruefen(name, angaben, daten_ordner):
    if not NAME_MUSTER.match(name) or name == "werkstatt":
        raise KonfigFehler("Ungültiger Ordnername %r (klein, Buchstaben/Ziffern/_, nicht \"werkstatt\")." % name)
    if not isinstance(angaben, dict) or not isinstance(angaben.get("pfad"), str) or not angaben["pfad"].strip():
        raise KonfigFehler("ordner.%s braucht einen \"pfad\"." % name)
    pfad = os.path.abspath(os.path.expanduser(angaben["pfad"]))
    heim = os.path.abspath(os.path.expanduser("~"))
    if pfad in ("/", heim):
        raise KonfigFehler("ordner.%s: das Wurzel- oder Home-Verzeichnis ist zu weit gefasst." % name)
    if pfad == os.path.join(heim, "Library") or pfad.startswith(os.path.join(heim, "Library") + os.sep):
        raise KonfigFehler("ordner.%s: ~/Library bleibt tabu." % name)
    if any(teil.startswith(".") for teil in pfad.split(os.sep) if teil):
        raise KonfigFehler("ordner.%s: versteckte Ordner sind nicht erlaubt." % name)
    daten = os.path.abspath(daten_ordner)
    if pfad == daten or pfad.startswith(daten + os.sep) or daten.startswith(pfad + os.sep):
        raise KonfigFehler("ordner.%s darf nicht den JARVIS-Datenordner enthalten oder darin liegen." % name)
    return {"pfad": angaben["pfad"].strip(), "schreiben": bool(angaben.get("schreiben", False))}


def normalisieren(werte, daten_ordner):
    """Prüft alle Werte und gibt eine bereinigte Kopie zurück. Wirft KonfigFehler."""
    w = copy.deepcopy(werte)
    for name, standard in STANDARD.items():
        w.setdefault(name, copy.deepcopy(standard))

    _ganzzahl(w, "port", 1024, 65535)
    _ganzzahl(w, "provider_timeout", 10, 3600)
    _ganzzahl(w, "tempo", 80, 400)
    _ganzzahl(w, "log_max_bytes", 10000, 100000000)
    _ganzzahl(w, "log_dateien", 1, 50)
    _ganzzahl(w, "max_schritte", 1, 12)
    _ganzzahl(w, "max_versuche", 1, 4)
    _ganzzahl(w, "max_runden", 1, 6)
    _ganzzahl(w, "max_aufrufe_pro_auftrag", 1, 200)
    _ganzzahl(w, "freigabe_minuten", 1, 1440)
    _ganzzahl(w, "skript_timeout", 5, 600)
    _ganzzahl(w, "anfragen_pro_minute", 1, 600)
    _ganzzahl(w, "backup_aufbewahren", 1, 60)

    for name in ("lan", "modell_ausweichen", "vorlesen", "erinnerungen_sprechen", "auftraege_automatisch_fortsetzen"):
        w[name] = bool(w[name])

    w["logstufe"] = str(w["logstufe"]).upper()
    if w["logstufe"] not in LOGSTUFEN:
        raise KonfigFehler("Unbekannte Logstufe %r. Erlaubt: %s." % (w["logstufe"], ", ".join(LOGSTUFEN)))
    if w["host"] not in ERLAUBTE_HOSTS:
        raise KonfigFehler("Der Server darf nur auf dieser Maschine laufen (127.0.0.1). "
                           "Für das WLAN gibt es \"lan\" (./jarvis.sh lan an). Die Adresse %r wird abgelehnt." % (w["host"],))

    w["stimme"] = str(w["stimme"] or "").strip()
    w["werkstatt"] = str(w["werkstatt"] or "").strip()
    if not w["werkstatt"]:
        raise KonfigFehler("werkstatt darf nicht leer sein.")

    if not isinstance(w["modelle"], dict):
        raise KonfigFehler("modelle muss ein Objekt sein, z. B. {\"chat\": \"opus\"}.")
    modelle = dict(STANDARD["modelle"])
    for art, name in w["modelle"].items():
        if art not in MODELL_ARTEN:
            continue
        name = str(name or "").strip()
        if name and not MODELL_MUSTER.match(name):
            raise KonfigFehler("Unbekanntes Modell %r für %s. Zum Beispiel \"opus\" oder \"sonnet\"." % (name, art))
        modelle[art] = name
    w["modelle"] = modelle

    _liste(w, "bereiche", 8)
    bereiche = []
    for name in w["bereiche"]:
        name = str(name).strip().lower()
        if name in RESERVIERTE_BEREICHE or not BEREICH_MUSTER.match(name):
            raise KonfigFehler("Ungültiger Bereich %r (klein, 2-20 Zeichen, nicht %s)." % (name, "/".join(RESERVIERTE_BEREICHE)))
        if name not in bereiche:
            bereiche.append(name)
    if not bereiche:
        raise KonfigFehler("Mindestens ein Bereich ist nötig.")
    w["bereiche"] = bereiche

    if not isinstance(w["ordner"], dict):
        raise KonfigFehler("ordner muss ein Objekt sein.")
    if len(w["ordner"]) > 10:
        raise KonfigFehler("Höchstens 10 zusätzliche Ordner.")
    w["ordner"] = {name: _ordner_pruefen(name, angaben, daten_ordner) for name, angaben in w["ordner"].items()}

    _liste(w, "api_domains", 50)
    domains = []
    for d in w["api_domains"]:
        d = str(d).strip().lower()
        if not DOMAIN_MUSTER.match(d) or "." not in d:
            raise KonfigFehler("Ungültige Domain %r." % d)
        domains.append(d)
    w["api_domains"] = domains

    _liste(w, "deaktivierte_werkzeuge", 100)
    w["deaktivierte_werkzeuge"] = sorted({str(n).strip() for n in w["deaktivierte_werkzeuge"]
                                          if NAME_MUSTER.match(str(n).strip())})
    return {name: w[name] for name in STANDARD}


def laden(daten_ordner=None):
    """Liest die Konfiguration. Fehlt die Datei, wird sie mit Standardwerten angelegt."""
    ordner = daten_ordner or daten_ordner_ermitteln()
    os.makedirs(ordner, mode=0o700, exist_ok=True)
    try:
        os.chmod(ordner, 0o700)  # persönliche Daten: andere Benutzer dieses Macs dürfen nicht hinein
    except OSError:
        pass
    datei = os.path.join(ordner, "config.json")
    werte = copy.deepcopy(STANDARD)
    neu_anlegen = False
    if os.path.exists(datei):
        try:
            with open(datei, "r", encoding="utf-8") as f:
                gelesen = json.load(f)
        except (OSError, ValueError) as fehler:
            raise KonfigFehler("Die Konfiguration %s ist nicht lesbar: %s" % (datei, fehler)) from None
        if not isinstance(gelesen, dict):
            raise KonfigFehler("Die Konfiguration %s muss ein JSON-Objekt sein." % datei)
        if "modell" in gelesen and "modelle" not in gelesen:  # Altform aus Phase 3
            gelesen["modelle"] = {art: gelesen["modell"] for art in ("chat", "plan", "arbeit")}
        werte.update({k: v for k, v in gelesen.items() if k in STANDARD})
    else:
        neu_anlegen = True

    if os.environ.get("JARVIS_PORT"):
        werte["port"] = os.environ["JARVIS_PORT"]
    if os.environ.get("JARVIS_LOGSTUFE"):
        werte["logstufe"] = os.environ["JARVIS_LOGSTUFE"]
    if os.environ.get("JARVIS_WERKSTATT"):
        werte["werkstatt"] = os.environ["JARVIS_WERKSTATT"]
    if os.environ.get("JARVIS_MODELL") is not None:
        werte["modelle"] = {art: os.environ["JARVIS_MODELL"] for art in MODELL_ARTEN}

    konfig = Konfig(normalisieren(werte, ordner), ordner)
    if neu_anlegen:
        speichern_werte(konfig)
    return konfig


def speichern_werte(konfig):
    """Schreibt die aktuellen Werte zurück in die config.json."""
    nur_bekannte = {k: konfig.werte[k] for k in STANDARD if k in konfig.werte}
    zwischen = konfig.datei + ".neu"
    with open(zwischen, "w", encoding="utf-8") as f:
        json.dump(nur_bekannte, f, indent=2, ensure_ascii=False)
        f.write("\n")
    os.replace(zwischen, konfig.datei)
