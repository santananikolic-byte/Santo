#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Führt alle Module aus ``src/`` zu der einen Datei ``jarvis.py`` zusammen.

Beim Zusammenführen richten zwei Dinge echten Schaden an, wenn man sie übersieht.

**Namenskollisionen.** Namen wie ``SCHEMA``, ``API_URL`` oder ``_now`` gibt es in
mehreren Modulen. In getrennten Dateien stört das nicht - jede hat ihren eigenen
Namensraum. In einer einzigen Datei überschreiben sie sich *still*, und der
Fehler taucht erst zur Laufzeit an ganz anderer Stelle auf ("Tabelle action_log
existiert nicht"). Deshalb werden über den Syntaxbaum alle Namen auf oberster
Ebene gesammelt, Mehrfachvergaben gefunden und modulweise umbenannt
(``SCHEMA_memory``, ``SCHEMA_recall``, ...). Umbenannt wird über den
Token-Strom, nicht per Textsuche - so bleiben gleichlautende Wörter in Texten
und Kommentaren unangetastet.

**Vergessene Module.** Ein Modul kann existieren, aber nicht in der Bauliste
stehen - dann fehlt es still in der Einzeldatei. Vor jedem Bau werden deshalb
alle ``.py`` unter ``src/modules/`` gegen die Liste abgeglichen.

Außerdem: ``try/except``-Importblöcke werden **über den Syntaxbaum** entfernt,
nicht per Textsuche. Eine Textsuche würde nur die ``import``-Zeile treffen und
das eingerückte ``np = None`` im ``except``-Zweig stehen lassen - die Datei wäre
kaputt. Der Syntaxbaum entfernt immer den ganzen Block, und oben in der
Einzeldatei steht er genau einmal.
"""

import ast
import io
import os
import re
import sys
import tokenize
from pathlib import Path

WURZEL = Path(__file__).resolve().parent
QUELLE = WURZEL / "src"
ZIEL = WURZEL / "jarvis.py"

# Module in Abhängigkeitsreihenfolge. Der Name ist der Pfad ohne ".py".
BAULISTE = [
    "config",
    "modules/memory",
    "modules/router",
    "modules/recall",
    "modules/sprechtext",
    "modules/voice",
    "modules/speaker",
    "modules/mail",
    "modules/calendar_mod",
    "modules/telegram_mod",
    "modules/telefon",
    "modules/bookkeeping",
    "modules/call_analysis",
    "modules/akquise",
    "modules/privat",
    "modules/routines",
    "modules/camera",
    "modules/mcp_client",
    "modules/world",
    "modules/browser",
    "modules/messenger",
    "modules/computer_use",
    "modules/werkstatt",
    "modules/team",
    "modules/mac",
    "modules/autopilot",
    "modules/dienst",
    "modules/ansicht",
    "modules/webseite",
    "modules/dashboard_teile",
    "modules/dashboard",
    "modules/sales_view",
    "modules/scheduler",
    "modules/lernpfad",
    "modules/webapp",
    "modules/setup_wizard",
    "modules/macapp",
    "modules/tools",
    "agent",
    "run",
]

# Diese Namen gehören zum Projekt selbst - ihre Importe fallen beim
# Zusammenführen weg, weil dann alles in einer Datei steht.
INTERNE_MODULE = {"config", "agent", "run", "modules"}

KOPF = '''#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Jarvis - persönlicher Sprachassistent für die Gebäudereinigung.

Diese Datei ist erzeugt. Bearbeite die Module unter src/ und baue neu mit:

    python3 build_single.py

Betriebsarten:

    python3 jarvis.py             Web-App im Browser - der Normalfall
    python3 jarvis.py web --offen auch vom Handy im eigenen WLAN
    python3 jarvis.py hoeren      im Terminal zuhören, ohne Browser
    python3 jarvis.py chat        tippen statt sprechen
    python3 jarvis.py telegram    vom Handy aus
    python3 jarvis.py status      voller Stand des Betriebs
    python3 jarvis.py briefing    Briefing sofort
    python3 jarvis.py abend       Abendrückblick sofort
    python3 jarvis.py dashboard   Dashboard bauen
    python3 jarvis.py export      Buchhaltung als CSV
    python3 jarvis.py stimme      Stimmprofil einlernen
    python3 jarvis.py stimmen     ElevenLabs-Stimme aussuchen
    python3 jarvis.py test        Selbsttest
    python3 jarvis.py einrichten  geführte Ersteinrichtung

Alle Daten bleiben lokal auf diesem Rechner.
"""

'''

FUSS = '''

# ===========================================================================
# Einstieg
# ===========================================================================

if __name__ == "__main__":
    try:
        sys.exit(hauptprogramm())
    except KeyboardInterrupt:
        print("\\nAbgebrochen.")
        sys.exit(130)
'''


# ---------------------------------------------------------------------------
# Hilfsmittel
# ---------------------------------------------------------------------------

def modulname(pfad: str) -> str:
    """Kurzer, eindeutiger Name eines Moduls - dient als Umbenennungs-Suffix."""
    return pfad.split("/")[-1]


def ist_intern(name: str) -> bool:
    """Gehört dieser Importname zum Projekt selbst?"""
    if not name:
        return False
    return name.split(".")[0] in INTERNE_MODULE


def ist_importblock(knoten: ast.AST) -> bool:
    """Ist das ein ``try/except``-Block, der nur Importe enthält?

    Genau diese Blöcke halten optionale Abhängigkeiten am Leben. Sie werden aus
    den Modulen entfernt und stehen in der Einzeldatei einmal ganz oben.
    """
    if not isinstance(knoten, ast.Try):
        return False
    if not knoten.body:
        return False
    for eintrag in knoten.body:
        if not isinstance(eintrag, (ast.Import, ast.ImportFrom)):
            return False
    for behandler in knoten.handlers:
        for eintrag in behandler.body:
            if isinstance(eintrag, (ast.Import, ast.ImportFrom, ast.Pass)):
                continue
            if isinstance(eintrag, ast.Assign):
                continue
            if isinstance(eintrag, ast.Expr):
                continue
            return False
    return True


def top_level_namen(baum: ast.Module) -> set:
    """Alle Namen, die ein Modul auf oberster Ebene vergibt."""
    namen = set()
    for knoten in baum.body:
        if isinstance(knoten, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            namen.add(knoten.name)
        elif isinstance(knoten, ast.Assign):
            for ziel in knoten.targets:
                if isinstance(ziel, ast.Name):
                    namen.add(ziel.id)
                elif isinstance(ziel, (ast.Tuple, ast.List)):
                    for teil in ziel.elts:
                        if isinstance(teil, ast.Name):
                            namen.add(teil.id)
        elif isinstance(knoten, ast.AnnAssign) and isinstance(knoten.target, ast.Name):
            namen.add(knoten.target.id)
    return namen


def name_ersetzen(quelltext: str, umbenennungen: dict) -> str:
    """Benennt Namen über den Token-Strom um - nie in Texten oder Kommentaren.

    Attributzugriffe (``etwas.SCHEMA``) bleiben unangetastet, sonst würde eine
    fremde Eigenschaft mit umbenannt.
    """
    if not umbenennungen:
        return quelltext
    ergebnis = []
    letztes_zeichen = ""
    try:
        marken = list(tokenize.generate_tokens(io.StringIO(quelltext).readline))
    except tokenize.TokenError:
        return quelltext

    zeilen = quelltext.splitlines(keepends=True)
    ausgabe = list(zeilen)
    # Von hinten nach vorn ersetzen, damit die Spaltenangaben gültig bleiben.
    aenderungen = []
    for index, marke in enumerate(marken):
        if marke.type != tokenize.NAME or marke.string not in umbenennungen:
            continue
        vorher = ""
        rueck = index - 1
        while rueck >= 0 and marken[rueck].type in (tokenize.NL, tokenize.NEWLINE,
                                                    tokenize.INDENT, tokenize.DEDENT,
                                                    tokenize.COMMENT):
            rueck -= 1
        if rueck >= 0:
            vorher = marken[rueck].string
        if vorher == ".":
            continue  # Attributzugriff, nicht unser Name.
        aenderungen.append(marke)
    del letztes_zeichen, ergebnis

    for marke in reversed(aenderungen):
        zeile = marke.start[0] - 1
        von, bis = marke.start[1], marke.end[1]
        text = ausgabe[zeile]
        ausgabe[zeile] = text[:von] + umbenennungen[marke.string] + text[bis:]
    return "".join(ausgabe)


def config_bezug_aufloesen(quelltext: str) -> str:
    """Macht aus ``config.CLAUDE_MODEL`` das blanke ``CLAUDE_MODEL``.

    In der Einzeldatei gibt es kein Modul ``config`` mehr - seine Werte sind
    ganz normale Namen. Ohne diesen Schritt käme zur Laufzeit
    "config is not defined".
    """
    return re.sub(r"\bconfig\.([A-Za-z_][A-Za-z0-9_]*)", r"\1", quelltext)


def config_reste_finden(quelltext: str) -> list:
    """Sucht nach ``config``, das die Umschreibung nicht erwischt hat.

    ``config.WERT`` wird ersetzt, ``getattr(config, "WERT")`` aber nicht - dort
    steht ``config`` als blosser Name. In der Einzeldatei gibt es dieses Modul
    nicht mehr, und die Zeile stuerzt ab, sobald jemand sie erreicht. Genau so
    ein Rest hat den Selbsttest der Einzeldatei einmal lautlos zerlegt.
    Solche Stellen sollen beim Bauen auffallen, nicht beim Nutzer.
    """
    reste = []
    ohne_zeichenketten = re.compile(
        r'''("""(?:.|\n)*?"""|\'\'\'(?:.|\n)*?\'\'\'|"[^"\n]*"|\'[^\'\n]*\')''')
    for nummer, zeile in enumerate(quelltext.splitlines(), start=1):
        nackt = ohne_zeichenketten.sub("", zeile).split("#", 1)[0]
        if re.search(r"\bconfig\b", nackt):
            reste.append("Zeile %d: %s" % (nummer, zeile.strip()[:90]))
    return reste


# ---------------------------------------------------------------------------
# Einlesen
# ---------------------------------------------------------------------------

def modul_zerlegen(pfad: Path, name: str) -> dict:
    """Zerlegt ein Modul in Importe, optionale Importblöcke und Rumpf."""
    quelltext = pfad.read_text(encoding="utf-8")
    baum = ast.parse(quelltext, filename=str(pfad))
    zeilen = quelltext.splitlines()
    entfernen = set()

    einfache_importe = []
    optionale_bloecke = []
    doku = ""
    verschachtelt_intern = []

    # Interne Importe, die tief im Code stecken, würden in der Einzeldatei
    # fehlschlagen. Sie werden gemeldet, statt still durchzurutschen.
    for knoten in ast.walk(baum):
        if isinstance(knoten, ast.ImportFrom) and ist_intern(knoten.module or ""):
            if knoten not in baum.body:
                verschachtelt_intern.append("Zeile %d: from %s import ..."
                                            % (knoten.lineno, knoten.module))
        elif isinstance(knoten, ast.Import):
            for teil in knoten.names:
                if ist_intern(teil.name) and knoten not in baum.body:
                    verschachtelt_intern.append("Zeile %d: import %s"
                                                % (knoten.lineno, teil.name))

    for index, knoten in enumerate(baum.body):
        beginn = getattr(knoten, "lineno", 0)
        ende = getattr(knoten, "end_lineno", beginn)
        if isinstance(knoten, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) \
                and knoten.decorator_list:
            beginn = min([beginn] + [d.lineno for d in knoten.decorator_list])

        # Moduldokumentation wird zur Überschrift des Abschnitts.
        if index == 0 and isinstance(knoten, ast.Expr) and \
                isinstance(getattr(knoten, "value", None), ast.Constant) and \
                isinstance(knoten.value.value, str):
            doku = knoten.value.value
            entfernen.update(range(beginn, ende + 1))
            continue

        if isinstance(knoten, ast.Import):
            for teil in knoten.names:
                if ist_intern(teil.name):
                    continue
                einfache_importe.append(
                    "import %s%s" % (teil.name,
                                     (" as %s" % teil.asname) if teil.asname else ""))
            entfernen.update(range(beginn, ende + 1))
            continue

        if isinstance(knoten, ast.ImportFrom):
            if not ist_intern(knoten.module or ""):
                namen = ", ".join(
                    "%s%s" % (teil.name, (" as %s" % teil.asname) if teil.asname else "")
                    for teil in knoten.names)
                einfache_importe.append("from %s import %s" % (knoten.module, namen))
            entfernen.update(range(beginn, ende + 1))
            continue

        if ist_importblock(knoten):
            optionale_bloecke.append("\n".join(zeilen[beginn - 1:ende]))
            entfernen.update(range(beginn, ende + 1))
            continue

        if isinstance(knoten, ast.If) and _ist_main_block(knoten):
            entfernen.update(range(beginn, ende + 1))
            continue

    behalten = [zeile for nummer, zeile in enumerate(zeilen, 1)
                if nummer not in entfernen]
    rumpf = "\n".join(behalten).strip("\n")

    return {"name": name, "pfad": pfad, "doku": doku, "rumpf": rumpf,
            "importe": einfache_importe, "optionale": optionale_bloecke,
            "namen": top_level_namen(baum), "verschachtelt": verschachtelt_intern}


def _ist_main_block(knoten: ast.If) -> bool:
    """Erkennt ``if __name__ == "__main__":``."""
    pruefung = knoten.test
    if not isinstance(pruefung, ast.Compare):
        return False
    return isinstance(pruefung.left, ast.Name) and pruefung.left.id == "__name__"


# ---------------------------------------------------------------------------
# Bauen
# ---------------------------------------------------------------------------

def bauliste_pruefen() -> list:
    """Gleicht alle vorhandenen Module gegen die Bauliste ab."""
    warnungen = []
    vorhanden = set()
    for datei in sorted((QUELLE / "modules").glob("*.py")):
        if datei.name == "__init__.py":
            continue
        vorhanden.add("modules/%s" % datei.stem)
    for datei in sorted(QUELLE.glob("*.py")):
        vorhanden.add(datei.stem)

    fehlend = vorhanden - set(BAULISTE)
    for name in sorted(fehlend):
        warnungen.append("Das Modul '%s' steht nicht in der Bauliste und fehlt "
                         "deshalb in jarvis.py." % name)
    for name in BAULISTE:
        pfad = QUELLE / ("%s.py" % name)
        if not pfad.exists():
            warnungen.append("Die Bauliste nennt '%s', aber die Datei fehlt." % name)
    return warnungen


def bauen(ziel: Path = None) -> int:
    """Baut die Einzeldatei. Gibt 0 zurück, wenn alles geklappt hat."""
    ziel = ziel or ZIEL
    print("Baue %s" % ziel)

    warnungen = bauliste_pruefen()
    for warnung in warnungen:
        print("  [WARNUNG] %s" % warnung)

    module = []
    for eintrag in BAULISTE:
        pfad = QUELLE / ("%s.py" % eintrag)
        if not pfad.exists():
            continue
        module.append(modul_zerlegen(pfad, modulname(eintrag)))

    for modul in module:
        for meldung in modul["verschachtelt"]:
            print("  [WARNUNG] %s: verschachtelter Projekt-Import - %s"
                  % (modul["name"], meldung))

    # -- Namenskollisionen --------------------------------------------------
    zaehler = {}
    for modul in module:
        for name in modul["namen"]:
            zaehler.setdefault(name, []).append(modul["name"])
    kollisionen = {name: orte for name, orte in zaehler.items() if len(orte) > 1}

    if kollisionen:
        print("  %d Namenskollisionen gefunden, ich benenne sie modulweise um:"
              % len(kollisionen))
        for name in sorted(kollisionen):
            print("    %-24s in %s" % (name, ", ".join(kollisionen[name])))

    for modul in module:
        umbenennungen = {name: "%s_%s" % (name, modul["name"])
                         for name in modul["namen"] if name in kollisionen}
        if umbenennungen:
            modul["rumpf"] = name_ersetzen(modul["rumpf"], umbenennungen)

    # -- config-Bezüge auflösen --------------------------------------------
    for modul in module:
        if modul["name"] != "config":
            modul["rumpf"] = config_bezug_aufloesen(modul["rumpf"])
            reste = config_reste_finden(modul["rumpf"])
            if reste:
                # Abbruch statt Warnung: eine solche Zeile stuerzt spaeter beim
                # Nutzer ab, und zwar erst dann, wenn er sie zufaellig erreicht.
                raise SystemExit(
                    "\nABBRUCH: In '%s' bleibt nach dem Umschreiben ein Bezug auf "
                    "das Modul 'config' stehen:\n  %s\n\nIn der Einzeldatei gibt es "
                    "dieses Modul nicht mehr. Schreib die Stelle als config.NAME, "
                    "dann wird sie ersetzt.\n"
                    % (modul["name"], "\n  ".join(reste)))

    # -- Importe zusammenlegen ---------------------------------------------
    schlichte, aus_modulen = [], {}
    for modul in module:
        for zeile in modul["importe"]:
            if zeile.startswith("from "):
                # Mehrere "from datetime import ..." zu einer Zeile zusammenlegen,
                # sonst steht dasselbe Modul mehrfach oben.
                herkunft, _, namen = zeile[len("from "):].partition(" import ")
                eintrag = aus_modulen.setdefault(herkunft, [])
                for name in namen.split(","):
                    name = name.strip()
                    if name and name not in eintrag:
                        eintrag.append(name)
            elif zeile not in schlichte:
                schlichte.append(zeile)
    einfache = sorted(schlichte)
    for herkunft in sorted(aus_modulen):
        einfache.append("from %s import %s"
                        % (herkunft, ", ".join(sorted(aus_modulen[herkunft]))))

    optionale, gesehen_blocks = [], set()
    for modul in module:
        for block in modul["optionale"]:
            schluessel = re.sub(r"\s+", " ", block).strip()
            if schluessel not in gesehen_blocks:
                gesehen_blocks.add(schluessel)
                optionale.append(block)

    # -- Zusammensetzen -----------------------------------------------------
    teile = [KOPF]
    teile.append("\n".join(einfache))
    teile.append("\n")
    if optionale:
        teile.append("\n# --------------------------------------------------------"
                     "-------------------\n"
                     "# Optionale Abhängigkeiten. Fehlt eine, fällt nur das\n"
                     "# betroffene Werkzeug aus - nie das ganze Programm.\n"
                     "# --------------------------------------------------------"
                     "-------------------\n")
        teile.append("\n\n".join(optionale))
        teile.append("\n")

    for modul in module:
        ueberschrift = modul["doku"].strip().splitlines()
        titel = ueberschrift[0] if ueberschrift else modul["name"]
        teile.append("\n\n# " + "=" * 73)
        teile.append("# %s  -  %s" % (modul["name"], titel))
        for zeile in ueberschrift[1:]:
            teile.append("# %s" % zeile.rstrip())
        teile.append("# " + "=" * 73 + "\n")
        teile.append(modul["rumpf"])

    teile.append(FUSS)
    inhalt = "\n".join(teile)

    # -- Prüfen und schreiben ----------------------------------------------
    try:
        ast.parse(inhalt, filename=str(ziel))
    except SyntaxError as fehler:
        notpfad = ziel.with_suffix(".kaputt.py")
        notpfad.write_text(inhalt, encoding="utf-8")
        print("  [FEHLER] Die erzeugte Datei ist syntaktisch kaputt: %s" % fehler)
        print("           Zur Ansicht abgelegt unter %s" % notpfad)
        return 1

    ziel.write_text(inhalt, encoding="utf-8")
    try:
        os.chmod(str(ziel), 0o755)
    except OSError:
        pass

    print("  %d Module, %d Zeilen, %d Zeichen"
          % (len(module), inhalt.count("\n") + 1, len(inhalt)))
    print("  %d Importe, %d optionale Importblöcke"
          % (len(einfache), len(optionale)))
    print("Fertig: %s" % ziel)
    return 0


if __name__ == "__main__":
    sys.exit(bauen())
