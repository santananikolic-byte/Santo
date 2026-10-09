#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Autopilot - Jarvis arbeitet von selbst, ohne dass man ihn anstößt.

Zweimal am Tag (und auf Knopfdruck) macht er die Vorarbeit, die sonst liegen
bleibt, und legt das Ergebnis auf die Seite "Heute zu tun":

1. **Neue Betriebe** aus OpenStreetMap - kostenlos, ohne Schlüssel - für den
   eigenen Ort und die gewählten Branchen. Zu jedem schreibt er ein kurzes
   Anruf-Skript.
2. **Nachfassen**: Wer laut Pipeline heute dran ist.
3. **Posteingang**: Zu wichtigen Mails entwirft er eine Antwort.
4. **Cashflow**: Läuft ein Monat ins Minus, sagt er es.

**Was er bewusst nicht tut: von selbst Mails an fremde Firmen schicken.**
Werbemails ohne Einwilligung sind in Österreich und Deutschland in der Regel
unzulässig, und ein Postfach, das Kaltmails verschickt, wird schnell gesperrt.
Gesendet wird erst, wenn der Nutzer auf der Seite klickt - der Klick ist die
Freigabe. Neue Betriebe bekommen deshalb ein Anruf-Skript, keine Mail.

**Robust ohne Gehirn:** Ist der Gratis-Dienst gerade ausgelastet, nimmt er
Vorlagen statt selbst geschriebener Texte. Die Arbeit bleibt nicht liegen, nur
weil ein Kontingent leer ist.
"""

import email.utils
import json
import threading
import urllib.error
import urllib.parse
import urllib.request

import config
from modules.memory import db_schema_anlegen, heute_datum, zeitstempel

SCHEMA_AUTOPILOT = """
CREATE TABLE IF NOT EXISTS autopilot_aufgaben (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    schluessel TEXT NOT NULL,
    art TEXT NOT NULL,
    titel TEXT NOT NULL,
    firma TEXT DEFAULT '',
    an TEXT DEFAULT '',
    betreff TEXT DEFAULT '',
    text TEXT DEFAULT '',
    grund TEXT DEFAULT '',
    lead_id INTEGER DEFAULT 0,
    status TEXT DEFAULT 'offen',
    angelegt TEXT NOT NULL,
    erledigt_am TEXT DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_autopilot_status ON autopilot_aufgaben(status);
CREATE INDEX IF NOT EXISTS idx_autopilot_schluessel ON autopilot_aufgaben(schluessel);
CREATE TABLE IF NOT EXISTS autopilot_laeufe (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    start TEXT NOT NULL,
    ende TEXT DEFAULT '',
    ergebnis TEXT DEFAULT ''
);
"""

# Mehrere öffentliche Server: Ist einer ausgelastet oder weg, nimmt Jarvis den nächsten.
OVERPASS_SERVER = ["https://overpass-api.de/api/interpreter",
                   "https://overpass.kumi.systems/api/interpreter",
                   "https://overpass.private.coffee/api/interpreter"]
OVERPASS_URL = OVERPASS_SERVER[0]

# Welche OpenStreetMap-Merkmale zu welcher Branche gehören.
BRANCHEN_OSM = {
    "Arztpraxen": [("amenity", "doctors"), ("amenity", "dentist")],
    "Physiotherapie": [("healthcare", "physiotherapist")],
    "Apotheken": [("amenity", "pharmacy")],
    "Steuerberater": [("office", "tax_advisor"), ("office", "accountant")],
    "Kanzleien": [("office", "lawyer"), ("office", "notary")],
    "Versicherungen": [("office", "insurance")],
    "Immobilien": [("office", "estate_agent")],
    "Autohäuser": [("shop", "car")],
    "Fitnessstudios": [("leisure", "fitness_centre")],
    "Hotels": [("tourism", "hotel")],
    "Kindergärten": [("amenity", "kindergarten")],
    "Restaurants": [("amenity", "restaurant")],
}
STANDARD_BRANCHEN = "Arztpraxen,Steuerberater,Kanzleien,Autohäuser,Fitnessstudios"

# Worauf es der jeweiligen Branche bei der Reinigung ankommt - für Skript und Vorlage.
BRANCHEN_PUNKT = {
    "Arztpraxen": "Hygiene und Desinfektion nach Plan, auch außerhalb der Sprechzeiten",
    "Physiotherapie": "saubere Behandlungsräume und Desinfektion der Liegen",
    "Apotheken": "gepflegte Verkaufsräume, gereinigt vor Öffnung",
    "Steuerberater": "diskrete Büroreinigung nach Feierabend",
    "Kanzleien": "diskrete Reinigung, Akten bleiben unberührt",
    "Versicherungen": "gepflegte Büros und Besprechungsräume",
    "Immobilien": "gepflegtes Büro und Endreinigung von Objekten",
    "Autohäuser": "glänzender Schauraum und saubere Glasflächen",
    "Fitnessstudios": "Hygiene in Duschen, Umkleiden und an den Geräten",
    "Hotels": "Unterstützung bei Zimmern und öffentlichen Bereichen",
    "Kindergärten": "gründliche Reinigung mit kindgerechten Mitteln",
    "Restaurants": "Gastraum und Sanitär, gereinigt vor Öffnung",
}

ARTEN = {"anruf": "Anrufen", "nachfassen": "Nachfassen", "antwort": "Mail beantworten",
         "hinweis": "Hinweis"}


def _sauber(text: str) -> str:
    """Entfernt Zeichen, die eine Overpass-Abfrage aufbrechen könnten."""
    return "".join(z for z in (text or "") if z not in '"\\;[](){}').strip()


def osm_abfrage(ort: str, branchen: list, anzahl: int = 40) -> str:
    """Baut die Overpass-Abfrage für die Branchen in einem Ort."""
    teile = []
    for branche in branchen:
        for schluessel, wert in BRANCHEN_OSM.get(branche, []):
            teile.append('nwr["%s"="%s"]["name"](area.a);' % (schluessel, wert))
    return ('[out:json][timeout:35];'
            'area["name"="%s"]["boundary"="administrative"]->.a;'
            '(%s);out tags center %d;' % (_sauber(ort), "".join(teile), int(anzahl)))


def _branche_von(tags: dict) -> str:
    for branche, merkmale in BRANCHEN_OSM.items():
        for schluessel, wert in merkmale:
            if tags.get(schluessel) == wert:
                return branche
    return ""


def osm_betriebe(ort: str, branchen: list, anzahl: int = 40, url: str = None) -> dict:
    """Holt Betriebe aus OpenStreetMap. Kostenlos, ohne Schlüssel."""
    ort = _sauber(ort)
    branchen = [b for b in branchen if b in BRANCHEN_OSM]
    if not ort:
        return {"ok": False, "fehler": "Es ist kein Ort eingestellt."}
    if not branchen:
        return {"ok": False, "fehler": "Es ist keine bekannte Branche gewählt."}
    daten = urllib.parse.urlencode({"data": osm_abfrage(ort, branchen, anzahl)}).encode()
    roh = None
    for server in ([url] if url else OVERPASS_SERVER):
        anfrage = urllib.request.Request(
            server, data=daten, method="POST",
            headers={"User-Agent": "Jarvis-Gebaeudereinigung/1.0",
                     "Content-Type": "application/x-www-form-urlencoded"})
        try:
            with urllib.request.urlopen(anfrage, timeout=40) as antwort:
                roh = json.loads(antwort.read().decode("utf-8"))
            break
        except (urllib.error.URLError, OSError, ValueError):
            continue
    if roh is None:
        return {"ok": False, "fehler": "OpenStreetMap ist gerade nicht erreichbar. "
                                       "Beim nächsten Lauf versuche ich es wieder."}

    betriebe = []
    for element in roh.get("elements", []):
        tags = element.get("tags") or {}
        name = (tags.get("name") or "").strip()
        if not name:
            continue
        strasse = " ".join(t for t in (tags.get("addr:street", ""),
                                       tags.get("addr:housenumber", "")) if t)
        ortsteil = " ".join(t for t in (tags.get("addr:postcode", ""),
                                        tags.get("addr:city", "")) if t)
        betriebe.append({
            "firma": name, "branche": _branche_von(tags),
            "adresse": ", ".join(t for t in (strasse, ortsteil) if t),
            "telefon": tags.get("phone") or tags.get("contact:phone") or "",
            "email": tags.get("email") or tags.get("contact:email") or "",
            "webseite": tags.get("website") or tags.get("contact:website") or "",
        })
    # Wer eine Telefonnummer hat, kommt zuerst - angerufen wird zuerst.
    betriebe.sort(key=lambda b: (not b["telefon"], not b["email"]))
    return {"ok": True, "betriebe": betriebe}


def anruf_vorlage(betrieb: dict, ort: str = "") -> str:
    """Ein Anruf-Skript ohne Gehirn - damit nie etwas liegen bleibt."""
    punkt = BRANCHEN_PUNKT.get(betrieb.get("branche", ""), "zuverlässige Reinigung")
    return (
        "Guten Tag, hier spricht %s von %s. Wir reinigen Betriebe hier%s. "
        "Darf ich kurz fragen, wer bei Ihnen die Reinigung macht und ob Sie "
        "damit zufrieden sind?\n\n"
        "Falls Interesse: Bei %s kommt es vor allem auf %s an. Ich schaue mir die "
        "Räume gern kostenlos an und schicke Ihnen danach ein festes Angebot. "
        "Wann passt es Ihnen diese Woche?\n\n"
        "Falls kein Interesse: Darf ich mich in ein paar Monaten noch einmal melden?"
        % (config.NUTZER_NAME, config.FIRMA, (" in %s" % ort) if ort else "",
           betrieb.get("firma", "Ihnen"), punkt))


class Autopilot:
    """Arbeitet die Vorarbeit von selbst ab und legt sie zur Freigabe vor."""

    def __init__(self, memory, akquise=None, mail=None, bookkeeping=None, welt=None):
        self.memory = memory
        self.welt = welt  # für die Websuche, wenn OpenStreetMap ausfällt
        self.akquise = akquise
        self.mail = mail
        self.bookkeeping = bookkeeping
        self._laeuft = threading.Lock()
        self.osm_url = None  # für Tests umstellbar
        db_schema_anlegen(SCHEMA_AUTOPILOT, memory.db_pfad)

    # -- Einstellungen -------------------------------------------------------

    @staticmethod
    def einstellungen() -> dict:
        branchen = [b.strip() for b in (config.AUTOPILOT_BRANCHEN or STANDARD_BRANCHEN)
                    .split(",") if b.strip() in BRANCHEN_OSM]
        return {"an": bool(config.AUTOPILOT_AN), "ort": config.AUTOPILOT_ORT,
                "name": config.NUTZER_NAME, "firma": config.FIRMA,
                "branchen": branchen, "alle_branchen": list(BRANCHEN_OSM),
                "uhrzeiten": config.AUTOPILOT_UHRZEITEN,
                "neue_pro_lauf": int(config.AUTOPILOT_NEUE_LEADS)}

    @staticmethod
    def einstellungen_setzen(ort=None, branchen=None, an=None, name=None,
                             firma=None) -> dict:
        if name is not None and _sauber(str(name)):
            config.env_setzen("NUTZER_NAME", _sauber(str(name))[:60])
        if firma is not None and _sauber(str(firma)):
            config.env_setzen("FIRMA", _sauber(str(firma))[:80])
        if ort is not None:
            config.env_setzen("AUTOPILOT_ORT", _sauber(str(ort))[:80])
        if branchen is not None:
            gueltig = [b for b in branchen if b in BRANCHEN_OSM]
            config.env_setzen("AUTOPILOT_BRANCHEN", ",".join(gueltig) or STANDARD_BRANCHEN)
        if an is not None:
            config.env_setzen("AUTOPILOT_AN", "ja" if an else "nein")
        return {"ok": True, "text": "Gespeichert.", "einstellungen": Autopilot.einstellungen()}

    # -- Aufgaben ------------------------------------------------------------

    def aufgabe_anlegen(self, schluessel: str, art: str, titel: str, text: str = "",
                        firma: str = "", an: str = "", betreff: str = "", grund: str = "",
                        lead_id: int = 0) -> int:
        """Legt eine Aufgabe an - aber nie zweimal dieselbe."""
        if self.memory._lesen("SELECT id FROM autopilot_aufgaben WHERE schluessel=? LIMIT 1",
                              (schluessel,)):
            return 0
        return self.memory._schreiben(
            "INSERT INTO autopilot_aufgaben (schluessel, art, titel, firma, an, betreff, "
            "text, grund, lead_id, status, angelegt) VALUES (?,?,?,?,?,?,?,?,?,'offen',?)",
            (schluessel, art, titel[:200], firma, an, betreff[:200], text[:6000],
             grund[:500], int(lead_id or 0), zeitstempel()))

    def aufgaben(self, status: str = "offen", limit: int = 100) -> list:
        zeilen = self.memory._lesen(
            "SELECT * FROM autopilot_aufgaben WHERE status=? ORDER BY "
            "CASE art WHEN 'antwort' THEN 0 WHEN 'nachfassen' THEN 1 WHEN 'anruf' THEN 2 "
            "ELSE 3 END, id DESC LIMIT ?", (status, int(limit)))
        return [dict(z) for z in zeilen]

    def offen_anzahl(self) -> int:
        zeilen = self.memory._lesen(
            "SELECT count(*) AS n FROM autopilot_aufgaben WHERE status='offen'")
        return zeilen[0]["n"] if zeilen else 0

    def aufgabe_erledigen(self, nummer: int, aktion: str, text: str = None,
                          betreff: str = None) -> dict:
        """Senden, Erledigt oder Verwerfen - der Klick des Nutzers ist die Freigabe."""
        zeilen = self.memory._lesen("SELECT * FROM autopilot_aufgaben WHERE id=?",
                                    (int(nummer or 0),))
        if not zeilen:
            return {"ok": False, "text": "Diese Aufgabe gibt es nicht."}
        aufgabe = dict(zeilen[0])
        if aufgabe["status"] != "offen":
            return {"ok": False, "text": "Diese Aufgabe ist schon erledigt."}
        text = aufgabe["text"] if text is None else str(text)
        betreff = aufgabe["betreff"] if betreff is None else str(betreff)

        if aktion == "senden":
            if aufgabe["art"] != "antwort":
                return {"ok": False, "text": "Senden gibt es nur für Antworten auf Mails."}
            if self.mail is None or not self.mail.senden_moeglich():
                return {"ok": False, "text": "Der Mailversand ist nicht eingerichtet."}
            ergebnis = self.mail.senden(aufgabe["an"], betreff, text)
            if not ergebnis.get("ok"):
                return {"ok": False, "text": ergebnis.get("fehler", "Senden fehlgeschlagen.")}
            status = "gesendet"
        elif aktion == "erledigt":
            status = "erledigt"
            if aufgabe["art"] == "anruf" and aufgabe["lead_id"] and self.akquise is not None:
                # Angerufen: der Betrieb ist jetzt kontaktiert, Nachfassen läuft an.
                self.akquise.lead_weiterstufen(aufgabe["firma"], "kontaktiert",
                                               "angerufen (Autopilot)")
        elif aktion == "verwerfen":
            status = "verworfen"
        else:
            return {"ok": False, "text": "Unbekannte Aktion."}

        self.memory._schreiben(
            "UPDATE autopilot_aufgaben SET status=?, text=?, betreff=?, erledigt_am=? "
            "WHERE id=?", (status, text, betreff, zeitstempel(), aufgabe["id"]))
        self.memory.aktion_protokollieren("autopilot_%s" % aktion,
                                          {"aufgabe": aufgabe["titel"]}, status)
        return {"ok": True, "status": status,
                "text": {"gesendet": "Gesendet.", "erledigt": "Erledigt.",
                         "verworfen": "Verworfen."}[status]}

    # -- Ein Lauf --------------------------------------------------------------

    def laufen(self, agent=None) -> dict:
        """Ein kompletter Arbeitsdurchgang. Läuft nie zweimal gleichzeitig."""
        if not self._laeuft.acquire(blocking=False):
            return {"ok": False, "text": "Der Autopilot arbeitet gerade schon."}
        lauf = self.memory._schreiben("INSERT INTO autopilot_laeufe (start) VALUES (?)",
                                      (zeitstempel(),))
        zaehler, hinweise = {}, []
        try:
            for name, schritt in (("anruf", self._neue_betriebe),
                                  ("nachfassen", self._nachfassen),
                                  ("antwort", self._posteingang),
                                  ("hinweis", self._cashflow)):
                try:
                    anzahl, hinweis = schritt(agent)
                except Exception as fehler:  # ein Schritt darf die anderen nicht stoppen
                    anzahl, hinweis = 0, "%s: %s" % (ARTEN[name], fehler)
                zaehler[name] = anzahl
                if hinweis:
                    hinweise.append(hinweis)
            neu = sum(zaehler.values())
            teile = []
            if zaehler.get("anruf"):
                teile.append("%d neue Betriebe zum Anrufen" % zaehler["anruf"])
            if zaehler.get("nachfassen"):
                teile.append("%d zum Nachfassen" % zaehler["nachfassen"])
            if zaehler.get("antwort"):
                teile.append("%d Mails zu beantworten" % zaehler["antwort"])
            if zaehler.get("hinweis"):
                teile.append("%d Hinweise zum Geld" % zaehler["hinweis"])
            text = ("Autopilot: %s. Alles liegt unter 'Heute zu tun'." % ", ".join(teile)
                    if teile else "Autopilot: Nichts Neues. Offen sind %d Aufgaben."
                    % self.offen_anzahl())
            if hinweise:
                text += " Hinweis: " + " | ".join(hinweise)
            self.memory._schreiben("UPDATE autopilot_laeufe SET ende=?, ergebnis=? WHERE id=?",
                                   (zeitstempel(), text, lauf))
            self.memory.aktion_protokollieren("autopilot", zaehler, text)
            return {"ok": True, "neu": neu, "zaehler": zaehler, "hinweise": hinweise,
                    "offen": self.offen_anzahl(), "text": text}
        finally:
            self._laeuft.release()

    def letzter_lauf(self) -> dict:
        zeilen = self.memory._lesen("SELECT * FROM autopilot_laeufe ORDER BY id DESC LIMIT 1")
        return dict(zeilen[0]) if zeilen else {}

    # -- Die Schritte -------------------------------------------------------------

    def _neue_betriebe(self, agent):
        einstellungen = self.einstellungen()
        if not einstellungen["ort"]:
            return 0, "Kein Ort eingestellt - trag ihn auf der Seite 'Heute zu tun' ein."
        if self.akquise is None:
            return 0, ""
        gefunden = osm_betriebe(einstellungen["ort"], einstellungen["branchen"],
                                url=self.osm_url)
        if not gefunden.get("ok"):
            # Zweiter Weg: Websuche, die Treffer zerlegt das Gehirn.
            neue = self._betriebe_ueber_suche(agent, einstellungen)
            if not neue:
                return 0, gefunden.get("fehler", "")
            return self._anrufe_anlegen(agent, neue, einstellungen["ort"])
        neue = []
        for betrieb in gefunden["betriebe"]:
            if len(neue) >= einstellungen["neue_pro_lauf"]:
                break
            if not betrieb["telefon"] and not betrieb["email"]:
                continue  # niemand erreichbar - nutzlos
            ergebnis = self.akquise.lead_anlegen(
                betrieb["firma"], telefon=betrieb["telefon"], email=betrieb["email"],
                adresse=betrieb["adresse"], quelle="OpenStreetMap %s" % einstellungen["ort"],
                notiz=" ".join(t for t in (betrieb["branche"], betrieb["webseite"]) if t),
                naechster_schritt="anrufen und fragen, wer die Reinigung macht")
            if ergebnis.get("ok"):
                betrieb["lead_id"] = ergebnis["id"]
                neue.append(betrieb)
        if not neue:
            return 0, ("Keine neuen Betriebe mit Telefon in %s gefunden."
                       % einstellungen["ort"]) if not gefunden["betriebe"] else ""
        return self._anrufe_anlegen(agent, neue, einstellungen["ort"])

    def _betriebe_ueber_suche(self, agent, einstellungen) -> list:
        """Neue Betriebe über die Websuche - wenn OpenStreetMap nicht antwortet."""
        if self.welt is None or self.akquise is None or agent is None \
                or not getattr(agent, "einsatzbereit", lambda: False)():
            return []
        try:
            ergebnis = self.akquise.leads_finden(
                einstellungen["ort"], ", ".join(einstellungen["branchen"]),
                einstellungen["neue_pro_lauf"], self.welt, agent)
        except Exception:
            return []
        neue = []
        for firma in (ergebnis.get("neu") or []) if ergebnis.get("ok") else []:
            lead = self.akquise.lead_finden(firma)
            if lead is None:
                continue
            neue.append({"firma": lead["firma"], "branche": lead["notiz"] or "",
                         "adresse": lead["adresse"] or "", "telefon": lead["telefon"] or "",
                         "email": lead["email"] or "", "webseite": "",
                         "lead_id": lead["id"]})
        return neue

    def _anrufe_anlegen(self, agent, neue: list, ort: str):
        """Zu jedem neuen Betrieb eine Anruf-Aufgabe mit Skript."""
        einstellungen = {"ort": ort}
        skripte = self._skripte(agent, neue, einstellungen["ort"])
        for betrieb in neue:
            skript = skripte.get(betrieb["firma"]) or anruf_vorlage(betrieb, einstellungen["ort"])
            details = ["Telefon: %s" % (betrieb["telefon"] or "keins eingetragen")]
            if betrieb["adresse"]:
                details.append("Adresse: %s" % betrieb["adresse"])
            if betrieb["webseite"]:
                details.append("Webseite: %s" % betrieb["webseite"])
            if betrieb["email"]:
                details.append("E-Mail: %s (anschreiben erst nach Einwilligung, "
                               "zum Beispiel wenn sie am Telefon Ja sagen)" % betrieb["email"])
            self.aufgabe_anlegen(
                "lead:%d" % betrieb["lead_id"], "anruf",
                "%s anrufen" % betrieb["firma"], skript + "\n\n" + "\n".join(details),
                firma=betrieb["firma"], an=betrieb["telefon"],
                grund="Neu aus OpenStreetMap, %s" % (betrieb["branche"] or "Betrieb"),
                lead_id=betrieb["lead_id"])
        return len(neue), ""

    @staticmethod
    def _skripte(agent, betriebe: list, ort: str) -> dict:
        """Lässt die Skripte vom Gehirn schreiben - eine Anfrage für alle."""
        if agent is None or not getattr(agent, "einsatzbereit", lambda: False)():
            return {}
        liste = "\n".join("- %s (%s)" % (b["firma"], b["branche"] or "Betrieb")
                          for b in betriebe)
        auftrag = (
            "Schreib Anruf-Skripte für eine Gebäudereinigung. Der Anrufer heißt %s, die "
            "Firma heißt %s, sie arbeitet in %s. Benutze genau diese Namen, keine "
            "Platzhalter in eckigen Klammern.\n"
            "Für jeden Betrieb: drei bis fünf gesprochene Sätze, per Sie, freundlich, "
            "konkret für die Branche. Ziel ist ein kostenloser Besichtigungstermin.\n"
            "Wichtig: Sprich neutral an ('Guten Tag'), rate keine Namen, Titel oder "
            "Anrede. Behaupte nichts über die eigene Firma (keine Spezialisierung, keine "
            "Zertifikate, keine Preise), was hier nicht steht.\n\n"
            "Betriebe:\n%s\n\nAntworte nur als JSON: "
            '{"skripte": [{"firma": "...", "skript": "..."}]}'
            % (config.NUTZER_NAME, config.FIRMA, ort, liste))
        try:
            antwort = agent.json_anfrage(auftrag, max_tokens=3000)
        except Exception:
            return {}
        if not antwort.get("ok"):
            return {}
        ergebnis = {}
        for eintrag in (antwort.get("daten") or {}).get("skripte") or []:
            if isinstance(eintrag, dict) and eintrag.get("firma") and eintrag.get("skript"):
                ergebnis[str(eintrag["firma"])] = str(eintrag["skript"]).strip()
        return ergebnis

    def _nachfassen(self, agent):
        if self.akquise is None:
            return 0, ""
        liste = self.akquise.nachfassliste()
        anzahl = 0
        for eintrag in (liste.get("eintraege") or [])[:15]:
            text = "Nächster Schritt: %s\nTelefon: %s%s" % (
                eintrag.get("schritt") or "melden", eintrag.get("telefon") or "unbekannt",
                ("\nSeit %d Tagen überfällig." % eintrag["seit_tagen"])
                if eintrag.get("seit_tagen") else "")
            if self.aufgabe_anlegen("nachfassen:%d:%s" % (eintrag["id"], heute_datum()),
                                    "nachfassen", "%s nachfassen" % eintrag["firma"], text,
                                    firma=eintrag["firma"], an=eintrag.get("telefon", ""),
                                    grund="Stufe: %s" % eintrag.get("stufe", ""),
                                    lead_id=eintrag["id"]):
                anzahl += 1
        return anzahl, ""

    def _posteingang(self, agent):
        if self.mail is None or not self.mail.lesen_moeglich():
            return 0, ""
        post = self.mail.ungelesene(15)
        if not post.get("ok"):
            return 0, post.get("fehler", "")
        anzahl = 0
        for mail in (post.get("wichtig") or [])[:3]:
            adresse = email.utils.parseaddr(mail.get("absender", ""))[1]
            schluessel = "mail:%s:%s" % (adresse, mail.get("betreff", ""))
            if self.memory._lesen("SELECT id FROM autopilot_aufgaben WHERE schluessel=?",
                                  (schluessel,)):
                continue
            entwurf = ""
            if agent is not None and getattr(agent, "einsatzbereit", lambda: False)():
                antwort = agent.text_anfrage(
                    "Schreib eine kurze, höfliche Antwort auf diese Mail im Namen von %s, "
                    "%s (Gebäudereinigung). Per Sie, sachlich. Versprich nichts, was nicht "
                    "in der Mail steht; Termine nur vorschlagen. Nur den Mailtext, ohne "
                    "Betreff.\n\nVon: %s\nBetreff: %s\nText: %s"
                    % (config.NUTZER_NAME, config.FIRMA, mail.get("absender", ""),
                       mail.get("betreff", ""), mail.get("auszug", "")), max_tokens=1500)
                if antwort.get("ok"):
                    entwurf = antwort.get("text", "")
            betreff = mail.get("betreff", "")
            if not betreff.lower().startswith("re:"):
                betreff = "Re: " + betreff
            if self.aufgabe_anlegen(
                    schluessel, "antwort" if (entwurf and "@" in adresse) else "hinweis",
                    "Antwort an %s" % (mail.get("absender") or adresse),
                    entwurf or "Diese Mail wartet auf eine Antwort:\n%s" % mail.get("auszug", ""),
                    an=adresse, betreff=betreff,
                    grund="Wichtige Mail: %s" % mail.get("betreff", "")):
                anzahl += 1
        return anzahl, ""

    def _cashflow(self, agent):
        if self.akquise is None:
            return 0, ""
        prognose = self.akquise.cashflow_prognose(3, self.bookkeeping)
        anzahl = 0
        for monat in prognose.get("monate") or []:
            if monat["ergebnis"] < 0:
                if self.aufgabe_anlegen(
                        "cash:%s" % monat["monat"], "hinweis",
                        "Im %s fehlen etwa %.0f Euro" % (monat["monat"], -monat["ergebnis"]),
                        "Erwartete Einnahmen %.0f Euro, Kosten %.0f Euro. Jeder gewonnene "
                        "Auftrag schließt die Lücke - deshalb heute die Anrufe."
                        % (monat["einnahmen"], monat["kosten"]),
                        grund="Cashflow-Prognose"):
                    anzahl += 1
        return anzahl, ""
