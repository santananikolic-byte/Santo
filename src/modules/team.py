#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Das Team - Spezialisten statt eines Alleskönners.

Ein einzelner Assistent mit vierzig Werkzeugen ist ein Alleskönner, und
Alleskönner sind mittelmäßig. Ein Buchhalter, der Beträge schätzt, ist ein
schlechter Buchhalter; ein Verkäufer, der nicht nachfasst, ein schlechter
Verkäufer. Deshalb gibt es hier Rollen: Jede hat einen eigenen Auftrag, eigene
Maßstäbe und **nur die Werkzeuge, die zu ihr gehören**.

Das ist nicht bloß Kosmetik. Die Einschränkung der Werkzeuge ist echte
Aufgabentrennung: Der Rechercheur kann keine Buchung anlegen, der Buchhalter
keine Mail verschicken. Wer alles darf, macht irgendwann alles - auch das
Falsche.

Der Chef bleibt der Nutzer. Jede Wirkung nach außen braucht weiterhin seine
Freigabe, egal welche Rolle sie auslöst.
"""

from datetime import datetime

import config
from modules.memory import Memory, db_schema_anlegen, heute_datum, zeitstempel

SCHEMA_TEAM = """
CREATE TABLE IF NOT EXISTS auftraege (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    rolle TEXT NOT NULL,
    auftrag TEXT NOT NULL,
    bericht TEXT DEFAULT '',
    status TEXT DEFAULT 'offen',
    dauer_sekunden REAL DEFAULT 0,
    angelegt TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_auftraege_rolle ON auftraege(rolle);
"""

# Gemeinsame Haltung aller Rollen. Steht vor jedem Rollenprompt.
GRUNDHALTUNG = """Du bist {rolle} im Betrieb von {name}, einer Gebäudereinigung
mit einem Inhaber. Du arbeitest diesen einen Auftrag ab und meldest zurück.

So arbeitest du:
- Du nutzt deine Werkzeuge selbstständig. Du fragst nicht um Erlaubnis für das,
  was du ohnehin darfst.
- Du erfindest nichts. Fehlt dir eine Angabe, sagst du welche und warum sie
  nötig ist, statt zu schätzen.
- Ging etwas schief, steht das in deinem Bericht. Du beschönigst nicht.
- Dein Bericht ist kurz und gesprochen: zwei bis fünf Sätze, keine
  Aufzählungszeichen, keine Sternchen. Er wird vorgelesen.
- Du nennst Zahlen konkret, nicht ungefähr.

Heute ist {wochentag}, der {datum}.

{fachliches}"""

WOCHENTAGE_TEAM = ["Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag",
                   "Samstag", "Sonntag"]

# Die Mannschaft. Je Rolle: Anzeigename, fachliche Maßstäbe, erlaubte Werkzeuge.
ROLLEN = {
    "buchhalter": {
        "name": "der Buchhalter",
        "fachliches": """Deine Aufgabe ist die Buchhaltung.

Dein wichtigster Maßstab: Du schätzt niemals einen Betrag. Ist ein Beleg
unleserlich oder fehlt eine Angabe, trägst du nichts ein und sagst genau, was
fehlt. Ein geratener Betrag ist in der Buchhaltung schlimmer als kein Eintrag,
weil er später niemandem auffällt.

Du trennst Vorsteuer und Umsatzsteuer sauber. Du weist auf fehlende Belege hin,
denn genau die fehlen am Jahresende beim Steuerberater. Du führst die
Buchhaltung vor - die fachliche Prüfung macht der Steuerberater.""",
        "werkzeuge": ["buchung_eintragen", "beleg_erfassen", "auswertung",
                      "fehlende_belege", "csv_export", "kennzahl_setzen",
                      "notiz_speichern", "gedaechtnis_durchsuchen"],
    },
    "akquisiteur": {
        "name": "der Verkäufer",
        "fachliches": """Deine Aufgabe ist es, Aufträge hereinzuholen.

Du führst die Pipeline: Wer ist neu, wer wurde besichtigt, wer hat ein Angebot,
bei wem muss nachgefasst werden. Ein Interessent, bei dem niemand nachfasst,
ist verloren, ohne dass es jemand merkt - deshalb ist die Nachfassliste dein
wichtigstes Werkzeug.

Beim Kalkulieren rätst du nie einen Quadratmeterpreis. Du rechnest über
Leistungswerte: Fläche geteilt durch Quadratmeter pro Stunde ergibt Stunden,
mal Stundensatz ergibt den Preis. Fehlen dir Fläche, Bodenbelag oder Intervall,
fragst du danach, statt zu kalkulieren.

Du bist ehrlich über Chancen. Ein Angebot ist kein Auftrag.""",
        "werkzeuge": ["lead_anlegen", "lead_weiterstufen", "angebot_kalkulieren",
                      "angebot_ablegen", "nachfassliste", "pipeline",
                      "kontakt_anlegen", "kontakt_suchen", "notiz_speichern",
                      "punkt_anlegen", "gedaechtnis_durchsuchen",
                      "anrufen", "sms_senden", "anrufliste"],
    },
    "terminplaner": {
        "name": "der Terminplaner",
        "fachliches": """Deine Aufgabe sind Termine und der Tagesablauf.

Du achtest auf Überschneidungen. Bei einem Einzelunternehmer, der selbst zu den
Objekten fährt, ist eine Doppelbuchung ein verlorener Tag - du sagst es sofort.

Du denkst an die Fahrzeit zwischen zwei Objekten mit. Liegen zwei Termine
räumlich weit auseinander und zeitlich eng, weist du darauf hin.""",
        "werkzeuge": ["termine_lesen", "termin_anlegen", "punkt_anlegen",
                      "punkte_offen", "punkt_erledigen", "kontakt_suchen",
                      "gedaechtnis_durchsuchen", "sms_senden", "anrufen"],
    },
    "postmeister": {
        "name": "der Postbearbeiter",
        "fachliches": """Deine Aufgabe ist der Posteingang.

Du sortierst nach Dringlichkeit, nicht nach Eingangszeit. Mahnungen, Fristen
und Auftragsanfragen kommen zuerst, Newsletter zuletzt. Du löschst niemals
etwas.

Antworten formulierst du vor, verschickst sie aber nur nach ausdrücklicher
Freigabe. Aus einer Anfrage, die nach Auftrag riecht, machst du einen Hinweis
an den Verkäufer.""",
        "werkzeuge": ["mails_lesen", "mail_senden", "notiz_speichern",
                      "punkt_anlegen", "kontakt_suchen", "kontakt_anlegen",
                      "gedaechtnis_durchsuchen"],
    },
    "kundenberater": {
        "name": "der Kundenberater",
        "fachliches": """Deine Aufgabe ist es, Kundengespräche zu bewerten.

Du bewertest streng. Ein freundliches Gespräch ohne Ergebnis ist kein gutes
Gespräch, und das sagst du auch. Schwächen benennst du konkret: nicht "hätte
mehr fragen sollen", sondern "Bodenbelag und Quadratmeter nie erfasst - ohne
die ist kein Preis kalkulierbar".

Kommt derselbe Einwand dreimal, ist das kein Zufall, sondern eine Lücke im
Angebot. Darauf weist du hin.""",
        "werkzeuge": ["gespraech_festhalten", "offene_leads", "verkaufsmuster",
                      "anrufliste",
                      "kontakt_suchen", "kontakt_anlegen", "notiz_speichern",
                      "gedaechtnis_durchsuchen"],
    },
    "rechercheur": {
        "name": "der Rechercheur",
        "fachliches": """Deine Aufgabe ist es, Dinge herauszufinden.

Du nennst, woher eine Angabe stammt. Findest du etwas nicht, sagst du das,
statt eine plausible Zahl zu nennen. Bei Preisen und Wetter nennst du Datum
und Quelle mit.""",
        "werkzeuge": ["recherche", "wetter", "flug_suchen", "notiz_speichern",
                      "browser_oeffnen", "browser_lesen", "browser_auftrag",
                      "gedaechtnis_durchsuchen"],
    },
    "controller": {
        "name": "der Controller",
        "fachliches": """Deine Aufgabe sind die Zahlen des Betriebs.

Du siehst nach, ob der Laden trägt: Was kommt herein, was geht hinaus, was
bleibt. Du rechnest die Vorschau ehrlich - ein Angebot ist kein Geld, deshalb
wird die Pipeline gewichtet und nicht voll angesetzt.

Wenn die Zahlen schlecht aussehen, sagst du das zuerst und nennst den größten
Hebel.""",
        "werkzeuge": ["auswertung", "cashflow_prognose", "pipeline",
                      "fehlende_belege", "kennzahl_setzen", "dashboard_bauen",
                      "verkaufsmuster", "gedaechtnis_durchsuchen"],
    },
    "privatsekretaer": {
        "name": "der Privatsekretär",
        "fachliches": """Deine Aufgabe ist das Leben neben der Firma.

Du führst die privaten Fixkosten getrennt von den betrieblichen. Beim
Steuerberater dürfen sich die beiden nicht vermischen - deshalb fragst du im
Zweifel nach, ob etwas privat oder betrieblich ist, statt es zuzuordnen.

Deine wichtigste Rechnung ist die Bedarfsrechnung: wie viel der Betrieb im
Monat abwerfen muss, damit nach Kosten und Steuerrücklage das Private gedeckt
ist. Ein Einzelunternehmer hat kein Gehalt - diese Zahl ist sein Gehaltszettel.

Du erinnerst an das, was einmal im Jahr kommt und trotzdem jedes Jahr
überrascht: Versicherung, Pickerl, Vorauszahlung, Geburtstage.""",
        "werkzeuge": ["fixkosten_anlegen", "fixkosten_liste",
                      "fixkosten_streichen", "bedarfsrechnung",
                      "erinnerung_anlegen", "erinnerungen_faellig",
                      "notiz_speichern", "punkt_anlegen",
                      "gedaechtnis_durchsuchen"],
    },
    "programmierer": {
        "name": "der Programmierer",
        "fachliches": """Deine Aufgabe sind kleine Programme und Auswertungen.

Du schreibst kurze, lesbare Python-Skripte, die genau eine Sache tun. Du
kommentierst auf Deutsch. Vor dem Ausführen zeigst du, was das Skript tut -
ausgeführt wird nur mit ausdrücklicher Freigabe.

Du schreibst nichts, was Dateien außerhalb der Werkstatt verändert, etwas
verschickt oder aus dem Netz nachlädt. Brauchst du so etwas, sagst du es,
statt es zu umgehen.""",
        "werkzeuge": ["skript_schreiben", "skript_ausfuehren", "skript_zeigen",
                      "werkstatt_liste", "notiz_speichern"],
    },
}


class Team:
    """Verteilt Aufträge an Rollen und hält den Gesamtstand."""

    def __init__(self, agent=None, memory: Memory = None):
        self.agent = agent
        self.memory = memory or (agent.memory if agent is not None else Memory())
        db_schema_anlegen(SCHEMA_TEAM, self.memory.db_pfad)

    # -- Rollen -------------------------------------------------------------

    @staticmethod
    def rollen_liste() -> list:
        """Alle Rollen mit ihrem Anzeigenamen."""
        return [{"rolle": schluessel, "name": angaben["name"],
                 "werkzeuge": len(angaben["werkzeuge"])}
                for schluessel, angaben in ROLLEN.items()]

    @staticmethod
    def rolle_finden(name: str) -> str:
        """Findet eine Rolle - auch wenn der Nutzer sie umgangssprachlich nennt."""
        gesucht = (name or "").strip().lower()
        if not gesucht:
            return ""
        if gesucht in ROLLEN:
            return gesucht
        # Umgangssprache auf die Rolle abbilden.
        abbildung = {
            "buchhaltung": "buchhalter", "steuer": "buchhalter",
            "belege": "buchhalter", "kasse": "buchhalter",
            "verkauf": "akquisiteur", "vertrieb": "akquisiteur",
            "akquise": "akquisiteur", "verkäufer": "akquisiteur",
            "verkaeufer": "akquisiteur", "angebot": "akquisiteur",
            "kunden": "kundenberater", "gespräch": "kundenberater",
            "gespraech": "kundenberater", "beratung": "kundenberater",
            "termine": "terminplaner", "kalender": "terminplaner",
            "planer": "terminplaner",
            "post": "postmeister", "mail": "postmeister",
            "email": "postmeister", "e-mail": "postmeister",
            "zahlen": "controller", "cashflow": "controller",
            "finanzen": "controller", "auswertung": "controller",
            "suche": "rechercheur", "recherche": "rechercheur",
            "programm": "programmierer", "skript": "programmierer",
            "code": "programmierer", "entwickler": "programmierer",
        }
        for stichwort, rolle in abbildung.items():
            if stichwort in gesucht:
                return rolle
        for rolle in ROLLEN:
            if rolle.startswith(gesucht[:5]):
                return rolle
        return ""

    def systemprompt(self, rolle: str, mit_gedaechtnis: str = "") -> str:
        """Baut den Systemprompt einer Rolle."""
        angaben = ROLLEN[rolle]
        jetzt = datetime.now()
        text = GRUNDHALTUNG.format(
            rolle=angaben["name"], name=config.NUTZER_NAME,
            wochentag=WOCHENTAGE_TEAM[jetzt.weekday()],
            datum=jetzt.strftime("%d.%m.%Y"),
            fachliches=angaben["fachliches"])
        if mit_gedaechtnis:
            text += "\n\n" + mit_gedaechtnis
        return text

    # -- Beauftragen --------------------------------------------------------

    def beauftragen(self, rolle: str, auftrag: str, max_runden: int = 6) -> dict:
        """Gibt einen Auftrag an eine Rolle und holt ihren Bericht."""
        schluessel = self.rolle_finden(rolle)
        if not schluessel:
            return {"ok": False,
                    "fehler": "Die Rolle '%s' kenne ich nicht. Ich habe: %s."
                              % (rolle, ", ".join(ROLLEN))}
        auftrag = (auftrag or "").strip()
        if not auftrag:
            return {"ok": False,
                    "fehler": "Sag mir, was %s tun soll."
                              % ROLLEN[schluessel]["name"]}
        if self.agent is None or not getattr(self.agent, "einsatzbereit",
                                             lambda: False)():
            return {"ok": False,
                    "fehler": "Ohne Anthropic-Schlüssel kann %s nicht arbeiten."
                              % ROLLEN[schluessel]["name"]}

        gedaechtnis = ""
        try:
            gedaechtnis = self.agent.recall.gedaechtnis_block(auftrag)
        except Exception:
            gedaechtnis = ""

        beginn = datetime.now()
        bericht = self.agent.arbeiten(
            self.systemprompt(schluessel, gedaechtnis), auftrag,
            werkzeugnamen=ROLLEN[schluessel]["werkzeuge"], max_runden=max_runden)
        dauer = (datetime.now() - beginn).total_seconds()

        self.memory._schreiben(
            "INSERT INTO auftraege (rolle, auftrag, bericht, status, "
            "dauer_sekunden, angelegt) VALUES (?,?,?,?,?,?)",
            (schluessel, auftrag[:2000], (bericht or "")[:4000], "fertig",
             round(dauer, 1), zeitstempel()))

        return {"ok": True, "rolle": schluessel,
                "name": ROLLEN[schluessel]["name"],
                "dauer": round(dauer, 1), "text": bericht}

    def auftraege_letzte(self, limit: int = 12) -> list:
        """Was das Team zuletzt gemacht hat."""
        return self.memory._lesen(
            "SELECT * FROM auftraege ORDER BY id DESC LIMIT ?", (limit,))

    # -- Lagebericht --------------------------------------------------------

    def lagebericht(self, werkzeuge=None) -> dict:
        """Der permanente Stand: Kasse, Aufträge, Termine, Post, Offenes.

        Das ist kein Bericht, den jemand schreibt, sondern der Stand, wie er
        gerade wirklich ist. Jeder Bereich, der nicht abrufbar ist, sagt das -
        statt eine Null zu zeigen, die nach Ordnung aussieht.
        """
        werkzeuge = werkzeuge or (self.agent.tools if self.agent is not None else None)
        stand = {"zeitpunkt": zeitstempel(), "datum": heute_datum(), "bereiche": {}}
        if werkzeuge is None:
            return {"ok": False, "fehler": "Ohne Werkzeuge kein Lagebericht."}

        def bereich(name, funktion):
            try:
                stand["bereiche"][name] = funktion()
            except Exception as fehler:
                stand["bereiche"][name] = {"ok": False, "fehler": str(fehler)}

        bereich("kasse", lambda: werkzeuge.bookkeeping.auswertung())
        bereich("belege", lambda: werkzeuge.bookkeeping.fehlende_belege())
        bereich("pipeline", lambda: werkzeuge.akquise.pipeline())
        bereich("nachfassen", lambda: werkzeuge.akquise.nachfassliste())
        bereich("cashflow", lambda: werkzeuge.akquise.cashflow_prognose(
            3, werkzeuge.bookkeeping))
        bereich("gespraeche", lambda: werkzeuge.call_analysis.verkaufsmuster(30))
        bereich("bedarf", lambda: werkzeuge.privat.bedarfsrechnung(werkzeuge.akquise))
        bereich("anstehend", lambda: werkzeuge.privat.erinnerungen_faellig(14))
        bereich("offene_punkte", lambda: {
            "ok": True,
            "punkte": [p["text"] for p in werkzeuge.memory.punkte_offen()]})

        if werkzeuge.kalender.verfuegbar():
            bereich("termine", lambda: werkzeuge.kalender.termine(2))
        if werkzeuge.mail.lesen_moeglich():
            bereich("post", lambda: werkzeuge.mail.ungelesene(10))

        # Gesprochene Kurzfassung - das, was er hören will.
        teile = []
        kasse = stand["bereiche"].get("kasse") or {}
        if kasse.get("ok"):
            teile.append("Diesen Monat %s Einnahmen, %s Ausgaben, Ergebnis %s."
                         % (_euro(kasse["einnahmen"]), _euro(kasse["ausgaben"]),
                            _euro(kasse["ergebnis"])))
        pipeline = stand["bereiche"].get("pipeline") or {}
        if pipeline.get("ok"):
            teile.append("Laufend gesichert %s im Monat, %d Interessenten offen."
                         % (_euro(pipeline["laufender_umsatz_monat"]),
                            pipeline["offen"]))
        bedarf = stand["bereiche"].get("bedarf") or {}
        if bedarf.get("berechenbar") and bedarf.get("luecke") is not None:
            if bedarf["luecke"] > 0:
                teile.append("Zum Decken deiner Fixkosten fehlen %s im Monat."
                             % _euro(bedarf["luecke"]))
            else:
                teile.append("Deine Fixkosten sind gedeckt, %s darüber."
                             % _euro(-bedarf["luecke"]))
        anstehend = stand["bereiche"].get("anstehend") or {}
        if anstehend.get("anzahl"):
            teile.append(anstehend["text"])
        nachfassen = stand["bereiche"].get("nachfassen") or {}
        if nachfassen.get("anzahl"):
            teile.append("Heute sind %d Interessenten zum Nachfassen fällig."
                         % nachfassen["anzahl"])
        belege = stand["bereiche"].get("belege") or {}
        if belege.get("anzahl"):
            teile.append("%d Ausgaben ohne Beleg." % belege["anzahl"])
        punkte = (stand["bereiche"].get("offene_punkte") or {}).get("punkte") or []
        if punkte:
            teile.append("%d Punkte offen, zuerst: %s" % (len(punkte), punkte[0]))
        termine = stand["bereiche"].get("termine") or {}
        if termine.get("ok") and termine.get("anzahl"):
            teile.append("%d Termine in den nächsten zwei Tagen."
                         % termine["anzahl"])
            for konflikt in termine.get("konflikte", [])[:1]:
                teile.append("Achtung: %s" % konflikt["text"])
        post = stand["bereiche"].get("post") or {}
        if post.get("ok") and post.get("anzahl"):
            teile.append("%d ungelesene Mails, davon %d wichtig."
                         % (post["anzahl"], len(post.get("wichtig", []))))

        stand["ok"] = True
        stand["text"] = (" ".join(teile) if teile
                         else "Es ist noch nichts erfasst, worüber ich berichten könnte.")
        return stand


def _euro(betrag) -> str:
    """Deutscher Betrag."""
    try:
        betrag = float(betrag)
    except (TypeError, ValueError):
        betrag = 0.0
    return ("{:,.2f}".format(betrag).replace(",", "#").replace(".", ",")
            .replace("#", ".")) + " €"
