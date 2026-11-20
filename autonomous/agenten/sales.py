# -*- coding: utf-8 -*-
"""Sales-Agent: Angebote und Kundenkommunikation vorbereiten – nie selbst versenden.

- Angebote entstehen als druckbarer ENTWURF; den Betrag legt immer der Inhaber fest.
- Nachrichten sind Text-Entwürfe. Ohne dokumentierte Einwilligung empfiehlt der Agent Brief oder
  persönliches Gespräch (Werbe-E-Mails ohne Einwilligung sind nach § 7 UWG unzulässig).
- Versand eines Angebots braucht die Freigabe des Eigentümers. Auch mit Freigabe gibt es in
  Version 1 keinen Versandkanal – der Agent sagt das ehrlich und behauptet nie, etwas gesendet zu haben.
- Der Agent ändert den Kundenstatus nicht selbst; das entscheidet der Inhaber.
"""

import datetime
import json
import re

from . import Agent
from ..db import jetzt, neue_id
from ..produkte import bereinigen, datei_schreiben, datum_deutsch, produkt_hole, sicherer_pfad
from ..produkte import angebot as angebot_vorlage
from ..wallet import euro

STUFEN = ("neu", "kontaktiert", "interessiert", "angebot", "gewonnen", "verloren")
ANGEBOT_STATUS = ("entwurf", "geprueft", "versendet", "angenommen", "abgelehnt")
KEIN_KANAL = ("Kein Versandkanal angebunden (Version 1). Angebot liegt als Datei bereit – bitte selbst senden "
              "und danach als versendet markieren.")
RECHT_OHNE_EINWILLIGUNG = (
    "Werbe-E-Mails brauchen eine vorherige ausdrückliche Einwilligung (§ 7 UWG) – auch gegenüber Firmen. "
    "Werbeanrufe bei Firmen nur mit zumindest mutmaßlicher Einwilligung; im Zweifel nicht anrufen. "
    "Empfehlung: Brief oder persönliches Gespräch. Keine Rechtsberatung.")


class SalesAgent(Agent):
    rolle = "sales"
    name = "Sales-Agent"
    beschreibung = "Bereitet Angebote und Kundenkommunikation vor; versendet nichts ohne Freigabe."
    rechte = frozenset({"entwurf_erstellen", "datei_erstellen", "interne_auswertung", "gedaechtnis_vorschlag",
                        "kundenkontakt", "externe_nachricht"})
    aufgabentypen = {
        "angebot_entwurf": "Angebot als druckbaren Entwurf erstellen (Eingabe: betrag, kontakt_id?, produkt_id?, "
                           "titel?, leistungen?, lieferzeit?)",
        "nachricht_entwurf": "Nachricht an einen Kontakt entwerfen – wird nicht versendet (Eingabe: kontakt_id, anlass)",
        "pipeline_auswertung": "Interessenten und Angebote nach Status auswerten",
        "angebot_versenden": "Geprüftes Angebot versenden – nur nach Freigabe des Eigentümers (Eingabe: angebot_id)",
    }

    # ------------------------------------------------------------------ Angebot
    def aufgabe_angebot_entwurf(self, aufgabe, k):
        d = angebot_vorlage.eingabe_pruefen(aufgabe["eingabe"])
        kontakt = produkt = None
        if d["kontakt_id"]:
            kontakt = k.db.eins("SELECT * FROM kontakte WHERE id=?", (d["kontakt_id"],))
            if not kontakt:
                raise KeyError("Kontakt nicht gefunden.")
        if d["produkt_id"]:
            produkt = produkt_hole(k, d["produkt_id"])
            if not produkt:
                raise KeyError("Produkt nicht gefunden.")
        angebot_id = neue_id("an_")
        self.darf(k, "entwurf_erstellen", "angebot:" + angebot_id, aufgabe)
        pfad = sicherer_pfad("angebote", angebot_id, "angebot-entwurf.html")
        self.darf(k, "datei_erstellen", "angebot:%s/angebot-entwurf.html" % angebot_id, aufgabe, datei_pfad=pfad)
        inhalt = angebot_vorlage.inhalt_bauen(d, angebot_id, kontakt, produkt)
        datei_schreiben(pfad, angebot_vorlage.erzeugen(inhalt, entwurf=True))
        datei = "angebote/%s/angebot-entwurf.html" % angebot_id
        z = jetzt()
        k.db.ausfuehren("INSERT INTO angebote (id, kontakt_id, produkt_id, titel, betrag_cent, status, inhalt, datei,"
                        " erstellt, aktualisiert) VALUES (?,?,?,?,?,?,?,?,?,?)",
                        (angebot_id, inhalt["kontakt_id"], inhalt["produkt_id"], inhalt["titel"],
                         inhalt["betrag_cent"], "entwurf", json.dumps(inhalt, ensure_ascii=False), datei, z, z))
        k.protokoll.info("sales", "Angebotsentwurf erstellt", {"angebot": angebot_id})
        return {"angebot_id": angebot_id, "nr": inhalt["nr"], "status": "entwurf", "betrag": euro(inhalt["betrag_cent"]),
                "dateien": [pfad], "ansehen_url": "/produkte/" + datei,
                "hinweis": "ENTWURF – vor Versand prüfen. Gelbe Felder (z. B. Anbieter, Umsatzsteuer, Gültigkeit) "
                           "ergänzt der Inhaber. Ein Angebot ist keine Einnahme."}

    def aufgabe_angebot_versenden(self, aufgabe, k):
        angebot_id = aufgabe["eingabe"].get("angebot_id")
        angebot = k.db.eins("SELECT * FROM angebote WHERE id=?", (angebot_id,)) if isinstance(angebot_id, str) else None
        if not angebot:
            raise KeyError("Angebot nicht gefunden.")
        if angebot["status"] != "geprueft":
            raise ValueError("Nur geprüfte Angebote können versendet werden (Status: %s)." % angebot["status"])
        kontakt = k.db.eins("SELECT firma, ansprechpartner FROM kontakte WHERE id=?", (angebot["kontakt_id"],)) \
            if angebot["kontakt_id"] else None
        empfaenger = kontakt["firma"] if kontakt else "Empfänger nicht hinterlegt"
        # Gleiche Nutzlast bei jedem Versuch → derselbe Fingerabdruck (Ablehnung bleibt bindend)
        nutzlast = {"angebot_id": angebot["id"], "betrag_cent": angebot["betrag_cent"],
                    "kontakt_id": angebot["kontakt_id"]}
        self.darf(k, "kundenkontakt", "angebot:" + angebot["id"], aufgabe,
                  datenumfang="Firmenname%s und Angebotsinhalt (%s, %s) von %s" % (
                      ", Ansprechpartner" if kontakt and kontakt["ansprechpartner"] else "", angebot["titel"],
                      euro(angebot["betrag_cent"]), empfaenger),
                  folgen="Das Angebot geht an %s. Es ist danach beim Kunden und kann rechtlich als Angebot gelten. "
                         "Hinweis: In Version 1 ist kein Versandkanal angebunden – nach dem Ja wird nichts "
                         "automatisch gesendet." % empfaenger,
                  nutzlast=nutzlast)
        k.protokoll.audit("sales", "Versand freigegeben, aber kein Versandkanal angebunden", {"angebot": angebot["id"]})
        return {"angebot_id": angebot["id"], "versendet": False, "freigabe": "erteilt", "grund": KEIN_KANAL,
                "ansehen_url": "/produkte/" + angebot["datei"] if angebot["datei"] else None}

    # ------------------------------------------------------------------ Nachricht
    def aufgabe_nachricht_entwurf(self, aufgabe, k):
        e = aufgabe["eingabe"]
        kontakt_id = e.get("kontakt_id")
        kontakt = k.db.eins("SELECT * FROM kontakte WHERE id=?", (kontakt_id,)) if isinstance(kontakt_id, str) else None
        if not kontakt:
            raise KeyError("Kontakt nicht gefunden.")
        anlass = bereinigen(e.get("anlass"), 200) or "Erstkontakt"
        self.darf(k, "entwurf_erstellen", "nachricht:" + kontakt["id"], aufgabe)

        einwilligung = kontakt["einwilligung"] == "ja" and bool((kontakt["einwilligung_nachweis"] or "").strip())
        letztes = k.db.eins("SELECT titel FROM angebote WHERE kontakt_id=? AND status='versendet' "
                            "ORDER BY aktualisiert DESC LIMIT 1", (kontakt["id"],))
        will_nachfassen = bool(re.search(r"angebot|nachfass|nachfrag|erinner", anlass.lower()))
        nachfassen = will_nachfassen and letztes is not None

        anrede = ("Guten Tag %s," % kontakt["ansprechpartner"]) if kontakt["ansprechpartner"] else \
            "Sehr geehrte Damen und Herren,"
        branche = (" – zum Beispiel aus dem Bereich %s –" % kontakt["branche"]) if kontakt["branche"] else ""
        if nachfassen:
            betreff = "Unser Angebot: %s" % letztes["titel"]
            kern_text = ("vor einiger Zeit haben wir Ihnen unser Angebot „%s“ geschickt. Haben Sie dazu noch Fragen? "
                         "Gern besprechen wir es mit Ihnen – telefonisch oder persönlich." % letztes["titel"])
        else:
            betreff = "Ihre eigene Webseite – kurze Information"
            kern_text = ("wir erstellen für kleine Betriebe%s eine übersichtliche eigene Webseite: mit Ihren "
                         "Leistungen, Ihrem Einsatzgebiet und direktem Kontakt per Anruf oder E-Mail, gut lesbar auf "
                         "dem Handy. Gern zeigen wir Ihnen ein Beispiel." % branche)
        schluss = ("Wenn Sie Interesse haben, erreichen Sie uns unter [Telefon / E-Mail des Absenders].\n\n"
                   "Mit freundlichen Grüßen\n[Name, Firma und Anschrift des Absenders – vom Inhaber ergänzen]")
        if einwilligung:
            kanal = "email"
            text = "%s\n\n%s\n\n%s\n\nSie möchten keine weiteren Nachrichten von uns? Eine kurze Antwort genügt." % (
                anrede, kern_text, schluss)
            recht = ("Einwilligung dokumentiert (%s). Abmeldemöglichkeit ist im Text enthalten. Versand nur nach "
                     "Freigabe; in Version 1 ist kein Versandkanal angebunden. Keine Rechtsberatung."
                     % kontakt["einwilligung_nachweis"])
            schritt = "Entwurf prüfen, Platzhalter ergänzen und selbst per E-Mail senden."
        else:
            kanal = "brief"
            adresse = "\n".join(z for z in (kontakt["firma"], kontakt["ansprechpartner"] or "",
                                            "[Straße, Hausnummer]",
                                            "[PLZ] %s" % (kontakt["ort"] or "[Ort]")) if z)
            datum = datum_deutsch(datetime.date.today().isoformat())
            text = "%s\n\n[Ort des Absenders], %s\n\nBetreff: %s\n\n%s\n\n%s\n\n%s" % (
                adresse, datum, betreff, anrede, kern_text, schluss)
            recht = RECHT_OHNE_EINWILLIGUNG
            schritt = "Entwurf prüfen, Platzhalter ergänzen, ausdrucken und per Post senden oder persönlich übergeben."
        ergebnis = {
            "kontakt_id": kontakt["id"], "firma": kontakt["firma"], "anlass": anlass,
            "vorlage": "nachfassen" if nachfassen else "erstkontakt",
            "kanal_empfehlung": kanal, "einwilligung": "ja" if einwilligung else "keine",
            "betreff": betreff, "text": text,
            "status": "ENTWURF – nicht versendet", "sendefertig": False,
            "hinweis_recht": recht, "naechster_schritt": schritt,
        }
        if will_nachfassen and not nachfassen:
            ergebnis["hinweis"] = ("Für diesen Kontakt ist kein versendetes Angebot erfasst – deshalb ein Erstkontakt "
                                   "statt einer Nachfrage.")
        return ergebnis

    # ------------------------------------------------------------------ Auswertung
    def aufgabe_pipeline_auswertung(self, aufgabe, k):
        self.darf(k, "interne_auswertung", "pipeline", aufgabe)
        kontakte = {s: 0 for s in STUFEN}
        for z in k.db.alle("SELECT status, COUNT(*) AS n FROM kontakte GROUP BY status"):
            kontakte[z["status"]] = z["n"]
        angebote = {s: {"anzahl": 0, "summe_cent": 0} for s in ANGEBOT_STATUS}
        for z in k.db.alle("SELECT status, COUNT(*) AS n, COALESCE(SUM(betrag_cent),0) AS s FROM angebote "
                           "GROUP BY status"):
            angebote[z["status"]] = {"anzahl": z["n"], "summe_cent": z["s"]}
        offen = sum(angebote[s]["summe_cent"] for s in ("entwurf", "geprueft", "versendet"))
        entschieden_k = kontakte["gewonnen"] + kontakte["verloren"]
        entschieden_a = angebote["angenommen"]["anzahl"] + angebote["abgelehnt"]["anzahl"]
        ohne = [z["firma"] for z in k.db.alle(
            "SELECT firma FROM kontakte WHERE status NOT IN ('gewonnen','verloren') AND "
            "(naechster_schritt IS NULL OR trim(naechster_schritt)='') ORDER BY aktualisiert LIMIT 20")]
        return {
            "kontakte_nach_status": kontakte,
            "kontakte_gesamt": sum(kontakte.values()),
            "mit_einwilligung": k.db.wert("SELECT COUNT(*) FROM kontakte WHERE einwilligung='ja'"),
            "angebote_nach_status": {s: {"anzahl": v["anzahl"], "summe": euro(v["summe_cent"])}
                                     for s, v in angebote.items()},
            "angebote_offen_summe": euro(offen) + " (POTENZIAL – keine Einnahme)",
            "angebote_angenommen_summe": euro(angebote["angenommen"]["summe_cent"]) +
                                         " (ANGENOMMEN – Einnahme erst nach verifiziertem Zahlungseingang)",
            "abschlussquote_kontakte_prozent": round(100 * kontakte["gewonnen"] / entschieden_k) if entschieden_k else None,
            "annahmequote_angebote_prozent": round(100 * angebote["angenommen"]["anzahl"] / entschieden_a)
            if entschieden_a else None,
            "ohne_naechsten_schritt": ohne,
            "hinweis": "Alle Werte aus der Datenbank gezählt. Quoten erst aussagekräftig bei mehreren Fällen.",
        }
