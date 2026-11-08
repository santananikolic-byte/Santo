# -*- coding: utf-8 -*-
"""Bedienung über das Terminal.

    python3 -m ueberleben simulation              1000 Leben mit Spielgeld durchspielen
    python3 -m ueberleben leben                   ein Leben Schritt für Schritt zeigen
    python3 -m ueberleben echt start              Echt-Modus anlegen (Claude denkt, du entscheidest)
    python3 -m ueberleben echt runde [--anzahl 3] Agenten eine Stunde arbeiten lassen (fragt Claude)
    python3 -m ueberleben echt status             Kasse, Agenten, was du bekommen hast
    python3 -m ueberleben echt freigaben          Was auf dein Ja wartet
    python3 -m ueberleben echt ja 4               Freigabe 4 erteilen (fragt nochmal nach)
    python3 -m ueberleben echt nein 4             Freigabe 4 ablehnen
    python3 -m ueberleben echt einnahme A1 12,50 "Kunde X, Rechnung 7"
                                                  Echte Einnahme buchen - nur, wenn das Geld wirklich da ist
"""

import argparse
import contextlib
import json
import os
import re
import sys
import tempfile

try:
    import fcntl  # Mac und Linux
except ImportError:  # pragma: no cover - Windows
    fcntl = None

from .gehirne import ClaudeGehirn
from .kolonie import Kolonie, LadeFehler, RegelVerstoss
from .regeln import AKTIONEN, cent_aus_text, euro
from .simulation import bericht, ein_leben, viele_leben
from .welt import EchteWelt, zusammenfassung


# Fester Ort neben dem Programm - egal, aus welchem Ordner man es startet.
STANDARD_ORDNER = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "ueberleben_daten")


def datenordner():
    return os.environ.get("UEBERLEBEN_DATEN") or STANDARD_ORDNER


class Belegt(Exception):
    pass


@contextlib.contextmanager
def sperre():
    """Nur ein Befehl zur Zeit darf den Echt-Modus ändern. Sonst könnte ein zweites Fenster ein Ja überschreiben."""
    os.makedirs(datenordner(), exist_ok=True)
    with open(os.path.join(datenordner(), "zustand.lock"), "a+") as f:
        if fcntl is not None:
            try:
                fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError:
                raise Belegt("Der Echt-Modus ist gerade in einem anderen Fenster in Arbeit. Warte, bis das fertig ist.")
        try:
            yield
        finally:
            if fcntl is not None:
                fcntl.flock(f, fcntl.LOCK_UN)


def zustand_pfad():
    return os.path.join(datenordner(), "zustand.json")


def laden():
    pfad = zustand_pfad()
    if not os.path.exists(pfad):
        raise SystemExit("Noch kein Echt-Modus angelegt. Erst: python3 -m ueberleben echt start")
    try:
        with open(pfad, "r", encoding="utf-8") as f:
            daten = json.load(f)
    except ValueError as fehler:
        raise SystemExit(f"Die Datei {pfad} ist beschädigt ({fehler}). Nichts geändert.")
    try:
        k = Kolonie.aus_dict(daten)
    except LadeFehler as fehler:
        raise SystemExit(f"{fehler}\nDatei: {pfad}. Nichts geändert.")
    if not k.echt:
        raise SystemExit("Diese Datei ist nicht im Echt-Modus. Aus Sicherheit wird nichts ausgeführt.")
    return k


def speichern(k):
    k.pruefen()
    os.makedirs(datenordner(), exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=datenordner(), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(k.als_dict(), f, ensure_ascii=False, indent=1)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, zustand_pfad())
    except BaseException:
        with contextlib.suppress(OSError):
            os.remove(tmp)
        raise


def bestaetigen(frage, eingabe=input):
    try:
        return eingabe(f"{frage} Tippe 'ja' zum Bestätigen: ").strip().lower() == "ja"
    except EOFError:
        return False


WARNWOERTER = re.compile(r"(überweis|ueberweis|bezahl|zahl|kauf|iban|\bDE\d{2}|paypal|kreditkarte|passwort|"
                         r"https?://|www\.|bitcoin|krypto|gutschein|vorkasse)", re.I)


def freigabe_text(f):
    d = f.get("details") or {}
    teile = [f"#{f['id']} [{f['status']}] {f['agent']} will '{f['aktion']}' ({AKTIONEN[f['aktion']]['text']})",
             f"    Grund: {f.get('begruendung') or '-'}"]
    if f["aktion"] == "auszahlen":
        teile.append(f"    Betrag: {euro(int(d.get('betrag', 0)))} an dich")
    if d.get("schritt"):
        teile.append(f"    Vorschlag des Agenten (prüfen!): {str(d['schritt'])[:600]}")
    if WARNWOERTER.search(" ".join(str(x) for x in (f.get("begruendung"), d.get("schritt"), d.get("plattform")))):
        teile.append("    ACHTUNG: Hier geht es um Zahlungen, Links oder Zugangsdaten. Der Agent darf dich nie zum "
                     "Bezahlen auffordern. Im Zweifel: nein.")
    return "\n".join(teile)


def was_passiert(k, f):
    a = k.agenten[f["agent"]]
    if f["aktion"] == "kopieren":
        return f"{a.id} gibt {euro(k.regeln.startbudget)} an eine neue Kopie ab. Es wird kein echtes Geld bewegt."
    if f["aktion"] == "auszahlen":
        return (f"Im Buch gehen bis zu {euro(int(f['details'].get('betrag', 0)))} von {a.id} an dich. Das ist eine Buchung, "
                f"keine Überweisung - das Programm hat keinen Zugriff auf ein Konto.")
    return ("Nichts wird automatisch gesendet. Du führst den Schritt selbst aus (oder nicht). Kommt dadurch Geld rein, "
            "buchst du es mit 'echt einnahme'.")


def main(argv=None, eingabe=input, gehirn=None):
    p = argparse.ArgumentParser(prog="python3 -m ueberleben", description="Überlebens-Agent")
    sub = p.add_subparsers(dest="befehl", required=True)
    s = sub.add_parser("simulation")
    s.add_argument("--laeufe", type=int, default=1000)
    s.add_argument("--tage", type=int, default=30)
    s.add_argument("--ohne-kopien", action="store_true")
    l = sub.add_parser("leben")
    l.add_argument("--saat", type=int, default=7)
    l.add_argument("--tage", type=int, default=30)
    e = sub.add_parser("echt")
    e.add_argument("was", choices=["start", "runde", "status", "freigaben", "ja", "nein", "einnahme"])
    e.add_argument("werte", nargs="*")
    e.add_argument("--anzahl", type=int, default=1)
    a = p.parse_args(argv)

    if a.befehl == "simulation":
        print(bericht(viele_leben(max(1, a.laeufe), max_stunden=24 * max(1, a.tage), kopierfreude=not a.ohne_kopien)))
        return 0
    if a.befehl == "leben":
        k = ein_leben(saat=a.saat, max_stunden=24 * max(1, a.tage))
        for x in k.ereignisse:
            print(f"Std {x['stunde']:>4}  {x['agent']:<4} {x['text']}")
        print()
        print(zusammenfassung(k))
        return 0

    try:
        with sperre():
            return echt(a, eingabe, gehirn)
    except Belegt as fehler:
        print(fehler)
        return 1


def echt(a, eingabe, gehirn):
    if a.was == "start":
        if os.path.exists(zustand_pfad()):
            print(f"Es gibt schon einen Echt-Modus in {zustand_pfad()}. Nichts geändert.")
            return 1
        k = Kolonie(echt=True)
        k.gruenden()
        speichern(k)
        print(f"Angelegt in {datenordner()}.")
        print(f"A1 hat {euro(k.regeln.startbudget)} - als Buchwert, nicht als echtes Geld. Das Programm hat keinen Zugriff")
        print("auf ein Konto. Echtes Geld kommt nur ins Buch, wenn du eine wirklich eingegangene Einnahme buchst.")
        return 0

    k = laden()
    if a.was == "status":
        print(zusammenfassung(k))
        print("(Alle Beträge sind Buchwerte. Was du wirklich bekommst, siehst du auf deinem Konto.)")
        print(f"Offene Freigaben: {len(k.offene_freigaben())}")
        return 0
    if a.was == "freigaben":
        offen = k.offene_freigaben()
        print("\n\n".join(freigabe_text(f) for f in offen) if offen else "Keine offenen Freigaben.")
        return 0
    if a.was in ("ja", "nein"):
        if len(a.werte) != 1 or not re.fullmatch(r"[0-9]{1,9}", a.werte[0]):
            print("Bitte genau eine Nummer angeben, z. B.: echt ja 3")
            return 2
        nr = int(a.werte[0])
        f = next((x for x in k.freigaben if x["id"] == nr), None)
        if f is None:
            print(f"Freigabe #{nr} gibt es nicht.")
            return 1
        if f["status"] != "offen":
            print(f"Freigabe #{nr} ist schon entschieden ({f['status']}).")
            return 1
        if a.was == "ja":
            if not k.agenten[f["agent"]].lebt:
                f["status"] = "verfallen"
                speichern(k)
                print(f"{f['agent']} ist inzwischen tot. Freigabe #{nr} verfällt.")
                return 1
            print(freigabe_text(f))
            print("Was passiert: " + was_passiert(k, f))
            if not bestaetigen("Diese eine Aktion freigeben?", eingabe):
                print("Nicht bestätigt. Nichts passiert.")
                return 1
        try:
            k.freigabe_entscheiden(nr, a.was == "ja")
        except RegelVerstoss as fehler:
            speichern(k)
            print(f"Geht nicht: {fehler}")
            return 1
        speichern(k)
        print("Erledigt im Buch: " + ("freigegeben" if a.was == "ja" else "abgelehnt") + ".")
        return 0
    if a.was == "einnahme":
        if len(a.werte) < 2:
            print('So: echt einnahme A1 12,50 "Wofür"')
            return 2
        agent = k.agenten.get(a.werte[0])
        if agent is None:
            print(f"Agent {a.werte[0]} gibt es nicht.")
            return 1
        try:
            betrag = cent_aus_text(a.werte[1])
        except ValueError as fehler:
            print(fehler)
            return 2
        text = (" ".join(a.werte[2:]) or "Einnahme")[:200]
        if not agent.lebt:
            print(f"{agent.id} ist tot und kann nichts mehr einnehmen. Nichts gebucht.")
            return 1
        if not bestaetigen(f"Ist {euro(betrag)} für {agent.id} wirklich auf dem Konto eingegangen?", eingabe):
            print("Nicht bestätigt. Nichts gebucht.")
            return 1
        try:
            k.einnahme(agent, betrag, text)
        except RegelVerstoss as fehler:
            print(fehler)
            return 1
        speichern(k)
        print(f"Gebucht. {agent.id} hat jetzt {euro(agent.guthaben)}.")
        return 0
    if a.was == "runde":
        if not 1 <= a.anzahl <= 24:
            print("--anzahl muss zwischen 1 und 24 liegen (jede Runde fragt Claude und kostet Abo-Nutzung).")
            return 2
        gehirn = gehirn or ClaudeGehirn()
        if isinstance(gehirn, ClaudeGehirn) and not gehirn.verfuegbar():
            print("Claude Code ist nicht installiert (Befehl 'claude' fehlt). Ohne Claude kann der Agent nicht denken.")
            return 1
        for _ in range(a.anzahl):
            if not k.lebende():
                print("Alle Agenten sind tot.")
                break
            for agent_id, ent in k.runde(gehirn, EchteWelt()):
                print(f"{agent_id}: {ent.aktion} - {ent.begruendung}")
            speichern(k)  # nach jeder Runde, damit nichts verloren geht
        print()
        print(zusammenfassung(k))
        if k.offene_freigaben():
            print(f"\n{len(k.offene_freigaben())} Freigabe(n) warten auf dich: python3 -m ueberleben echt freigaben")
        return 0
    return 2


if __name__ == "__main__":
    sys.exit(main())
