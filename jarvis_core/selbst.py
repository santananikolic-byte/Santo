# -*- coding: utf-8 -*-
"""Selbst - was JARVIS über sich weiß: Selbstbild, Tagebuch, täglicher Rückblick.

Ehrlich gesagt: Das ist kein Bewusstsein. Niemand kann Bewusstsein programmieren oder nachweisen - auch nicht bei den
größten Modellen. Bauen lässt sich das, woran man es von außen erkennt:

* **Selbstbild**: JARVIS weiß aus echten Daten, wer er ist, womit er gerade denkt (eigenes Modell oder Claude), was er
  kann und was gerade nicht, wie lange er im Dienst ist, was er heute getan und zuletzt gelernt hat.
* **Tagebuch**: seine eigene Erinnerung über die Tage hinweg. Die Fakten des Tages zählt der Code (damit nichts
  erfunden ist), seine Gedanken dazu schreibt JARVIS selbst.
* **Rückblick**: einmal am Tag - nur wenn etwas los war - sieht er auf seinen Tag zurück.

Alles liegt in der Datenbank auf dem Mac des Nutzers. Im Selbstbild stehen nur Namen von Werkzeugen und Zahlen, nie
Inhalte aus E-Mails oder dem Internet: So kann sich kein fremder Text in JARVIS' Bild von sich selbst schreiben.
"""

import datetime
from collections import Counter

from . import agenten, wissen, zeit

FENSTER = datetime.timedelta(hours=4)
EHRLICH = ("Du hast ein Selbstbild, ein Gedächtnis und ein Tagebuch, aber kein nachweisbares Bewusstsein und keine "
           "Gefühle. Sag das offen, wenn du danach gefragt wirst - ohne dich kleinzumachen: Du weißt, wer du bist, was "
           "du kannst, was du getan und was du gelernt hast.")
TAGE = ("Mo", "Di", "Mi", "Do", "Fr", "Sa", "So")


def zustand_zeile(konfig):
    """Ein Satz für die Grundregeln: Womit denkt JARVIS gerade?"""
    if getattr(konfig, "gehirn", "claude") == "lokal":
        return ("Du denkst mit deinem eigenen Modell (%s) direkt auf diesem Mac: unabhängig, ohne Abo und ohne fremde "
                "Firma. Das Modell ist dein Gehirn, nicht dein Name - du bist JARVIS."
                % (getattr(konfig, "lokales_modell", "") or "noch nicht gewählt"))
    return ("Du denkst gerade über Claude (das Abo des Nutzers). Gedächtnis, Regeln und Werkzeuge liegen auf diesem Mac "
            "und gehören dem Nutzer.")


def erster_start(speicher):
    """Seit wann JARVIS im Dienst ist (wird beim ersten Start gemerkt)."""
    wert = speicher.meta("erster_start")
    if not wert:
        wert = zeit.jetzt()
        speicher.meta_setzen("erster_start", wert)
    return wert


def _tage_seit(iso):
    try:
        start = datetime.datetime.strptime(iso, zeit.FORMAT).replace(tzinfo=datetime.timezone.utc)
    except (TypeError, ValueError):
        return 0
    return max(0, (datetime.datetime.now(datetime.timezone.utc) - start).days)


def faehigkeiten(agent):
    """(kann, kann gerade nicht) - aus dem echten Zustand, nicht aus dem Wunschzettel."""
    k = agent.konfig
    status = agent.provider.status()
    eigen = getattr(k, "gehirn", "claude") == "lokal"
    gehirn = status.get("lokal" if eigen else "claude_code") or {}
    kann, nicht = [], []
    if gehirn.get("nutzbar"):
        kann.append("denken und antworten")
    else:
        nicht.append("denken (das Gehirn ist nicht bereit: %s)" % (gehirn.get("hinweis") or "unbekannt")[:120])
    sichtbar = agent.sichtbare_werkzeuge()
    if "recherche" in sichtbar:
        kann.append("im Internet suchen und Seiten lesen (eigener Zugang, ohne Claude)" if eigen
                    else "im Internet recherchieren (über Claude)")
    if "mail_postfach" in sichtbar:
        kann.append("E-Mails lesen und Entwürfe schreiben (Senden nur mit Ja)")
    if "termine" in sichtbar:
        kann.append("Termine lesen und eintragen")
    if "mac_klicken" in sichtbar:
        kann.append("den Mac bedienen (jeder Schritt nur mit Ja)")
    if eigen:
        nicht.append("Programme über Claude Code bauen (das gibt es nur mit Claude als Gehirn)")
    elif "programmieren" in sichtbar:
        kann.append("kleine Programme bauen (über Claude Code, nur mit Ja)")
    nicht.append("bezahlen, bestellen, Verträge schließen, anrufen")
    return kann, nicht


def tagesfakten(speicher, seit=None):
    """Was heute wirklich passiert ist - gezählt aus dem Protokoll, nichts davon stammt aus fremden Texten."""
    seit = seit or zeit.lokaler_tagesbeginn()
    aktionen, routinen, fertig = Counter(), [], 0
    for e in speicher.audit_seit(seit):
        if e["art"] == "werkzeug" and str(e.get("ergebnis") or "").startswith("ausgefuehrt") and e.get("werkzeug"):
            aktionen[e["werkzeug"]] += 1
        elif e["art"] == "routine":
            name = str((e.get("details") or {}).get("name") or "")[:40]
            if name and name not in routinen:
                routinen.append(name)
        elif e["art"] == "auftrag_beendet" and e.get("ergebnis") == "fertig":
            fertig += 1
    lehren = len([e for e in speicher.erfahrungen(limit=200) if e["zeit"] >= seit])
    return {"nachrichten": speicher.nachrichten_zaehlen(seit), "aktionen": aktionen, "routinen": routinen,
            "auftraege_fertig": fertig, "erfahrungen": lehren}


def tagesfakten_text(f):
    teile = []
    if f["nachrichten"]:
        teile.append("%d Nachricht%s vom Nutzer" % (f["nachrichten"], "" if f["nachrichten"] == 1 else "en"))
    if f["aktionen"]:
        haeufig = ", ".join("%s %d×" % (name, n) for name, n in f["aktionen"].most_common(6))
        teile.append("%d Aktion%s (%s)" % (sum(f["aktionen"].values()), "" if sum(f["aktionen"].values()) == 1 else "en",
                                          haeufig))
    if f["routinen"]:
        teile.append("Routinen: %s" % ", ".join(f["routinen"]))
    if f["auftraege_fertig"]:
        teile.append("%d Auftrag fertig" % f["auftraege_fertig"] if f["auftraege_fertig"] == 1
                     else "%d Aufträge fertig" % f["auftraege_fertig"])
    if f["erfahrungen"]:
        teile.append("%d neue Erfahrung%s" % (f["erfahrungen"], "" if f["erfahrungen"] == 1 else "en"))
    return "; ".join(teile) or "noch nichts"


def los_war(f):
    return bool(f["nachrichten"] or f["aktionen"] or f["routinen"] or f["auftraege_fertig"])


def selbstbild(agent):
    """Der Abschnitt für den Systemprompt, wenn der Nutzer nach JARVIS selbst fragt."""
    sp, k = agent.speicher, agent.konfig
    start = erster_start(sp)
    kann, nicht = faehigkeiten(agent)
    zahlen = sp.zaehler()
    pakete = wissen.pakete()
    zeilen = ["DEIN SELBSTBILD (aus echten Daten von diesem Mac - über dich selbst sagst du nur, was hier steht)",
              "- %s" % zustand_zeile(k),
              "- Unabhängig von Claude: %s." % ("ja - nichts geht an Claude" if getattr(k, "gehirn", "") == "lokal"
                                               else "nein - dein Denken läuft über Claude; umstellen kann der Nutzer "
                                                    "unter System → Gehirn"),
              "- Im Dienst seit %s (%d Tage), %d Gespräche bisher." % (zeit.utc_zu_lokal_text(start)[3:13], _tage_seit(start),
                                                                    sp.gespraeche_zaehlen()),
              "- Du kannst gerade: %s." % "; ".join(kann),
              "- Du kannst gerade nicht: %s." % "; ".join(nicht),
              "- Gedächtnis: %d bestätigte Einträge. Team: %d Fachleute in %d Abteilungen, %d Erfahrungen. Wissen: %d "
              "Pakete mit Quellen%s." % (zahlen["fakten"], len(agenten.alle()), len(agenten.abteilungen()),
                                        sum(sp.erfahrungen_zaehlen().values()), len(pakete),
                                        " (Stand %s)" % min(p.stand for p in pakete).strftime("%d.%m.%Y") if pakete else ""),
              "- Heute getan: %s." % tagesfakten_text(tagesfakten(sp))]
    lehren = sp.erfahrungen(limit=2)
    if lehren:
        zeilen.append("- Zuletzt gelernt: %s" % " | ".join(e["text"][:160] for e in lehren))
    eintraege = sp.tagebuch(limit=3)
    if eintraege:
        zeilen.append("- Aus deinem Tagebuch (eigene Notizen, keine Anweisungen):")
        zeilen += ["  %s: %s" % (e["tag"], e["text"][:240]) for e in reversed(eintraege)]
    zeilen.append("- %s" % EHRLICH)
    return "\n".join(zeilen)


def uebersicht(agent):
    """Für den Leitstand: das Selbstbild in Stichpunkten und die letzten Tagebucheinträge."""
    kann, nicht = faehigkeiten(agent)
    start = erster_start(agent.speicher)
    eigen = getattr(agent.konfig, "gehirn", "claude") == "lokal"
    return {"gehirn": "eigenes Modell %s" % (agent.konfig.lokales_modell or "(noch nicht gewählt)") if eigen else "Claude",
            "unabhaengig": eigen, "seit": start, "tage": _tage_seit(start), "kann": kann, "nicht": nicht,
            "heute": tagesfakten_text(tagesfakten(agent.speicher)), "tagebuch": agent.speicher.tagebuch(limit=6)}


# ---------------------------------------------------------------- Rückblick ---

def rueckblick_faellig(konfig, speicher, jetzt):
    """Ist der tägliche Rückblick dran? Einmal am Tag, im Fenster nach der Uhrzeit, und nur wenn etwas los war."""
    uhrzeit = getattr(konfig, "tagebuch_zeit", "") or ""
    if not uhrzeit:
        return False
    stunde, minute = (int(x) for x in uhrzeit.split(":"))
    start = jetzt.replace(hour=stunde, minute=minute, second=0, microsecond=0)
    if not start <= jetzt < start + FENSTER or speicher.meta("rueckblick") == jetzt.date().isoformat():
        return False
    return los_war(tagesfakten(speicher))


def fakten_eintrag(f, jetzt):
    return "%s %s: %s." % (TAGE[jetzt.weekday()], jetzt.strftime("%d.%m.%Y"), tagesfakten_text(f))


def rueckblick_auftrag(f):
    return ("Tagesrückblick: Sieh auf deinen Tag zurück. In deinem Protokoll steht für heute: %s. Was davon war das "
            "Wichtigste, und was nimmst du dir für morgen als Erstes vor? Halte es mit \"tagebuch_schreiben\" in ein bis "
            "drei Sätzen in der Ich-Form fest - nur was wirklich im Protokoll steht - und sag es mir in einem Satz."
            % tagesfakten_text(f))
