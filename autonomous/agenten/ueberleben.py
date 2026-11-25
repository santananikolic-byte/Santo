# -*- coding: utf-8 -*-
"""Überlebens-Agent: kämpft jeden Tag darum, dass echtes Geld reinkommt – mit erlaubten, internen Mitteln.

- Bewertet die Lage NUR aus echten, geprüften Zahlen (ROT / GELB / GRÜN mit Begründung). Wallet zählt nie.
- Sucht die besten Geldchancen (überfällige Forderungen, fehlende Rechnungen, Nachfassen, Interessenten,
  Ausschreibungen) und stößt dafür intern Folgeaufgaben anderer Agenten an: Suche (Akquise, nur lesen),
  Bewerbungs-Mappen (Akquise), Nachfass-ENTWÜRFE (Sales).
- Überlebensdruck ändert nur Prioritäten und Arbeitsmenge – er schaltet nie etwas ab (PDF 6.3).
- Sendet nichts, bezahlt nichts, gibt kein Angebot ab und liest selbst nicht im Internet.
"""

from . import Agent
from .. import ueberleben as logik
from ..auftraege import datum_deutsch
from ..produkte import datei_schreiben, sicherer_pfad

TOP_CHANCEN = 10


class UeberlebensAgent(Agent):
    rolle = logik.ROLLE
    name = "Überlebens-Agent"
    beschreibung = ("Kämpft jeden Tag darum, dass echtes Geld reinkommt: bewertet die Lage aus echten Zahlen "
                    "(ROT/GELB/GRÜN), findet die besten Geldchancen und stößt intern Folgeaufgaben an. Sendet, "
                    "bezahlt und gibt nichts ab.")
    rechte = frozenset({"interne_planung", "interne_auswertung", "datei_erstellen", "gedaechtnis_vorschlag"})
    aufgabentypen = {
        "ueberlebensplan": "Tagesplan gegen Geldmangel: Lage aus echten Zahlen, beste Geldchancen, interne "
                           "Folgeaufgaben (Suche, Bewerbungs-Mappen, Nachfass-Entwürfe) – nichts wird gesendet",
    }

    def aufgabe_ueberlebensplan(self, aufgabe, k):
        self.darf(k, "interne_auswertung", "ueberlebenslage", aufgabe)
        tag = logik.heute()
        lage = logik.lage(k, tag)
        chancen = logik.geldchancen(k, tag)
        self.darf(k, "interne_planung", "ueberlebensplan", aufgabe)
        folgen, uebersprungen = logik.folgeaufgaben_planen(k, lage["druck"], chancen, aufgabe["id"], tag)
        logik.angestossen_vermerken(chancen, folgen)
        plan = {
            "datum": tag.isoformat(),
            "druck": lage["druck"],
            "regel": lage["regel"],
            "begruendung": lage["begruendung"],
            "lage": lage,
            "geldchancen": chancen[:TOP_CHANCEN],
            "geldchancen_gesamt": len(chancen),
            "folgeaufgaben_geplant": [dict(f) for f in folgen],
            "uebersprungen": uebersprungen,
            "hinweis": "Nur interne Vorbereitung: nichts gesendet, nichts bezahlt, kein Angebot abgegeben. "
                       "Entscheidungen treffen Vater und Sohn.",
        }
        pfad, relativ = self._datei(k, aufgabe, tag, logik.plan_html(plan))
        self.darf(k, "gedaechtnis_vorschlag", "ueberlebensplan", aufgabe)
        k.gedaechtnis.merken("vorschlag", "Überlebensplan %s" % datum_deutsch(plan["datum"]), logik.plan_text(plan),
                             "ueberleben:ueberlebensplan", self.rolle, aufgabe["id"])
        plan.update(dateien=[pfad], plan_url="/produkte/" + relativ, folgeaufgaben=folgen)
        return plan

    def _datei(self, k, aufgabe, tag, inhalt):
        """plan.html – gibt es die heute schon (zweiter Plan am Tag), dann plan-<Aufgabe>.html. Nie überschreiben."""
        ordner = tag.isoformat()
        for name in ("plan.html", "plan-%s.html" % aufgabe["id"]):
            pfad = sicherer_pfad("ueberleben", ordner, name)
            self.darf(k, "datei_erstellen", "ueberleben:%s/%s" % (ordner, name), aufgabe, datei_pfad=pfad)
            try:
                datei_schreiben(pfad, inhalt)
            except FileExistsError:
                continue
            return pfad, "ueberleben/%s/%s" % (ordner, name)
        raise ValueError("Die Plan-Datei für diese Aufgabe gibt es schon.")
