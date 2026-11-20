# -*- coding: utf-8 -*-
"""Product-Agent: erstellt das erste Angebot (Webseiten-Paket), die Verkaufsseite und prüft Qualität.

Arbeitet deterministisch ohne Modell. Jede Datei entsteht nach Prüfung durch den Supervisor
(Aktion ``datei_erstellen`` mit Pfad) im freigegebenen Datenordner. Nach dem Erzeugen läuft
automatisch die Qualitätsprüfung; Mängel und offene Punkte werden ehrlich gemeldet."""

import json
import os

from . import Agent
from .. import konfig
from ..db import jetzt, neue_id
from ..produkte import datei_schreiben, produkt_eintragen, produkt_hole, sicherer_pfad
from ..produkte import qualitaet, verkaufsseite, webseite


WEBSEITEN_FELD = "webseiten"  # Kennung des Geschäftsfelds „Webseiten“ in der Marktbewertung


def _preisvorschlag_recherche():
    """Liest einen Preisvorschlag aus der Marktrecherche – nur für das Ergebnis, nie für die Seite.
    Die Datei gilt als nicht vertrauenswürdig: nur Zahlen und kurze Texte werden übernommen."""
    pfad = os.path.join(konfig.VORLAGEN, "marktbewertung.json")
    if not os.path.isfile(pfad):
        return None
    try:
        with open(pfad, encoding="utf-8") as f:
            daten = json.load(f)
        empfehlung = daten.get("empfehlung") or {}
        vorschlag = empfehlung.get("preis_vorschlag_eur") or {}
        angebot = str(empfehlung.get("angebot") or "")[:300]
        quelle = "datei:autonomous/daten_vorlagen/marktbewertung.json"
        if str(empfehlung.get("feld_id") or "") != WEBSEITEN_FELD:
            # Der Preisvorschlag gehört zu einem anderen Angebot – nicht dem Webseiten-Paket zuordnen
            return {"abweichende_empfehlung": angebot, "feld_id": str(empfehlung.get("feld_id") or "")[:60],
                    "hinweis": "Die Marktrecherche empfiehlt als erstes Angebot ein anderes Paket. Ihr "
                               "Preisvorschlag gilt für jenes Paket, nicht für das Webseiten-Paket – Entscheidung "
                               "beim Inhaber.", "quelle": quelle}
        zahl = lambda x: isinstance(x, (int, float)) and not isinstance(x, bool) and 0 < x < 1_000_000
        if not (zahl(vorschlag.get("min")) and zahl(vorschlag.get("max"))):
            return {"hinweis": "Marktbewertung vorhanden, aber ohne verwertbaren Preisvorschlag.", "quelle": quelle}
        return {"min_eur": vorschlag["min"], "max_eur": vorschlag["max"], "angebot": angebot,
                "status": "Vorschlag aus Marktrecherche – nicht freigegeben", "quelle": quelle}
    except (OSError, ValueError, AttributeError, TypeError):
        return {"hinweis": "Marktbewertung nicht lesbar."}


class ProductAgent(Agent):
    rolle = "product"
    name = "Product-Agent"
    beschreibung = ("Erstellt digitale Produkte (Webseiten-Paket, Verkaufsseite), prüft ihre Qualität und "
                    "dokumentiert Einschränkungen.")
    rechte = frozenset({"datei_erstellen", "test_ausfuehren", "interne_auswertung", "gedaechtnis_vorschlag",
                        "lokale_recherche"})
    aufgabentypen = {
        "webseite_erstellen": "Ein-Seiten-Webseite für einen Betrieb erzeugen (Eingabe: firma, branche, ort, "
                              "leistungen, telefon?, email?, slogan?, einzugsgebiet?, oeffnungszeiten?)",
        "verkaufsseite_erstellen": "Verkaufsseite für das Webseiten-Paket erzeugen (Eingabe optional: preis, "
                                   "lieferzeit, preis_hinweis, anbieter, telefon, email)",
        "qualitaetspruefung": "Qualität eines erzeugten Produkts prüfen (Eingabe: produkt_id)",
    }

    # ------------------------------------------------------------------
    def _schreiben(self, k, aufgabe, produkt_id, dateiname, inhalt):
        pfad = sicherer_pfad(produkt_id, dateiname)
        self.darf(k, "datei_erstellen", "produkt:%s/%s" % (produkt_id, dateiname), aufgabe, datei_pfad=pfad)
        return datei_schreiben(pfad, inhalt)

    def aufgabe_webseite_erstellen(self, aufgabe, k):
        d = webseite.eingabe_pruefen(aufgabe["eingabe"])
        produkt_id = neue_id("p_")
        pfad = self._schreiben(k, aufgabe, produkt_id, "index.html", webseite.erzeugen(d))
        self.darf(k, "test_ausfuehren", "qualitaet:" + produkt_id, aufgabe)
        pruefung = qualitaet.zusammenfassen({"index.html": qualitaet.datei_pruefen(pfad, d)})
        pruefung["geprueft"] = jetzt()
        grenzen = webseite.einschraenkungen(d)
        name = "Webseite: %s" % d["firma"]
        status = produkt_eintragen(k, produkt_id, name, "webseite", ["index.html"], pruefung, grenzen, aufgabe["id"])
        k.protokoll.info("product", "Webseite erzeugt", {"produkt": produkt_id, "status": status})
        return {"produkt_id": produkt_id, "name": name, "status": status, "dateien": [pfad],
                "ansehen_url": "/produkte/%s/index.html" % produkt_id,
                "qualitaet": {"bestanden": pruefung["bestanden"], "offene_punkte": pruefung["offene_punkte"],
                              "maengel": [p["name"] for p in pruefung["pruefungen"] if not p["ok"]]},
                "einschraenkungen": grenzen}

    def aufgabe_verkaufsseite_erstellen(self, aufgabe, k):
        d = verkaufsseite.eingabe_pruefen(aufgabe["eingabe"])
        produkt_id = neue_id("p_")
        index = self._schreiben(k, aufgabe, produkt_id, "index.html", verkaufsseite.erzeugen(d))
        beispiel = self._schreiben(k, aufgabe, produkt_id, "beispiel.html", verkaufsseite.beispiel_erzeugen())
        self.darf(k, "test_ausfuehren", "qualitaet:" + produkt_id, aufgabe)
        pruefung = qualitaet.zusammenfassen({
            "index.html": qualitaet.datei_pruefen(index, d),
            "beispiel.html": qualitaet.datei_pruefen(beispiel, webseite.eingabe_pruefen(webseite.BEISPIEL_DATEN)),
        })
        pruefung["geprueft"] = jetzt()
        grenzen = verkaufsseite.einschraenkungen(d)
        name = "Verkaufsseite: Webseiten-Paket"
        status = produkt_eintragen(k, produkt_id, name, "verkaufsseite", ["index.html", "beispiel.html"], pruefung,
                                   grenzen, aufgabe["id"])
        k.protokoll.info("product", "Verkaufsseite erzeugt", {"produkt": produkt_id, "status": status})
        ergebnis = {"produkt_id": produkt_id, "name": name, "status": status, "dateien": [index, beispiel],
                    "ansehen_url": "/produkte/%s/index.html" % produkt_id,
                    "preis_auf_seite": "ja (vom Inhaber)" if d["preis_cent"] is not None else
                                       "nein – Platzhalter „wird vom Inhaber festgelegt“",
                    "qualitaet": {"bestanden": pruefung["bestanden"], "offene_punkte": pruefung["offene_punkte"],
                                  "maengel": [p["datei"] + ": " + p["name"] for p in pruefung["pruefungen"]
                                              if not p["ok"]]},
                    "einschraenkungen": grenzen}
        if d["preis_cent"] is None:
            self.darf(k, "lokale_recherche", "marktbewertung", aufgabe)
            vorschlag = _preisvorschlag_recherche()
            if vorschlag:
                ergebnis["preis_vorschlag_recherche"] = vorschlag
        return ergebnis

    def aufgabe_qualitaetspruefung(self, aufgabe, k):
        produkt_id = aufgabe["eingabe"].get("produkt_id")
        produkt = produkt_hole(k, produkt_id) if isinstance(produkt_id, str) else None
        if not produkt:
            raise KeyError("Produkt nicht gefunden.")
        self.darf(k, "test_ausfuehren", "qualitaet:" + produkt["id"], aufgabe)
        eingaben = self._eingaben_der_erstellung(k, produkt)
        ergebnisse = {}
        for name in produkt["dateien"]:
            pfad = sicherer_pfad(produkt["ordner"], name)
            if not os.path.isfile(pfad):
                ergebnisse[name] = {"pruefungen": [{"name": "Datei vorhanden", "ok": False, "hinweis": "fehlt"}],
                                    "bestanden": False, "offene_punkte": []}
                continue
            bezug = eingaben if name == "index.html" else (
                webseite.eingabe_pruefen(webseite.BEISPIEL_DATEN) if name == "beispiel.html" else None)
            ergebnisse[name] = qualitaet.datei_pruefen(pfad, bezug)
        pruefung = qualitaet.zusammenfassen(ergebnisse)
        pruefung["geprueft"] = jetzt()
        status = "qualitaet_ok" if pruefung["bestanden"] else "qualitaet_mangel"
        k.db.ausfuehren("UPDATE produkte SET status=?, qualitaet=? WHERE id=?",
                        (status, json.dumps(pruefung, ensure_ascii=False), produkt["id"]))
        return {"produkt_id": produkt["id"], "status": status, "bestanden": pruefung["bestanden"],
                "pruefungen": pruefung["pruefungen"], "offene_punkte": pruefung["offene_punkte"]}

    @staticmethod
    def _eingaben_der_erstellung(k, produkt):
        """Die (geprüften) Eingaben, aus denen das Produkt entstand – für den Escaping-Abgleich."""
        if not produkt.get("aufgabe_id"):
            return None
        zeile = k.db.eins("SELECT eingabe FROM aufgaben WHERE id=?", (produkt["aufgabe_id"],))
        if not zeile:
            return None
        try:
            roh = json.loads(zeile["eingabe"] or "{}")
            if produkt["typ"] == "webseite":
                return webseite.eingabe_pruefen(roh)
            if produkt["typ"] == "verkaufsseite":
                return verkaufsseite.eingabe_pruefen(roh)
        except (ValueError, TypeError):
            return None
        return None

