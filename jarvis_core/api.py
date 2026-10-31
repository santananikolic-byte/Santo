# -*- coding: utf-8 -*-
"""API - die Logik hinter den HTTP-Endpunkten (der Server selbst steht in ``server.py``).

Jede Methode gibt ``(HTTP-Code, Antwort-dict)`` zurück. Zugangsschlüssel, Host-
und Herkunftsprüfung und Ratenbegrenzung erledigt der Server vorher.

Wichtig: Nur diese Schnittstelle kann Freigaben erteilen, Werkzeuge sperren oder
Daten löschen - das Modell erreicht sie nicht. Die Handlungen des Nutzers in der
Oberfläche sind seine ausdrückliche Entscheidung.
"""

from . import gedaechtnis, rollen, werkzeuge, zeit
from .konfig import KonfigFehler
from .protokoll import letzte_eintraege
from .werkzeuge import WerkzeugFehler

FAKT_ARTEN = ("fakt", "profil", "projekt", "entscheidung", "regel", "praeferenz", "ziel", "strategie", "technik")
BESTAETIGUNG_LOESCHEN = "ALLES LÖSCHEN"
EINSTELLUNGEN = ("stimme", "tempo", "vorlesen", "erinnerungen_sprechen", "modelle", "modell_ausweichen")
MAX_TEXT = 10000


def _int(wert):
    try:
        return int(wert)
    except (TypeError, ValueError):
        return None


class Api:
    def __init__(self, server):
        self.s = server

    # ------------------------------------------------------------ Lesen ---

    def get(self, pfad, query):
        route = {
            "/api/zustand": self.zustand, "/api/logs": self.logs, "/api/audit": self.audit, "/api/export": self.export,
            "/api/stimmen": self.stimmen, "/api/suche": self.suche, "/api/auftrag": self.auftrag_details,
        }.get(pfad)
        return route(query) if route else None

    def post(self, pfad, daten):
        route = {
            "/api/anfrage": self.anfrage, "/api/abbrechen": self.abbrechen, "/api/sprich": self.sprich,
            "/api/still": self.still, "/api/einstellungen": self.einstellungen, "/api/provider/pruefen": self.provider_pruefen,
            "/api/fakt": self.fakt, "/api/todo": self.todo, "/api/erinnerung": self.erinnerung, "/api/auftrag": self.auftrag,
            "/api/freigabe": self.freigabe, "/api/werkzeug": self.werkzeug, "/api/notstopp": self.notstopp,
            "/api/entsperren": self.entsperren, "/api/profil/einlesen": self.profil_einlesen, "/api/umgebung": self.umgebung,
            "/api/sicherung": self.sicherung, "/api/alles-loeschen": self.alles_loeschen,
        }.get(pfad)
        return route(daten) if route else None

    def _bereich(self, wert):
        return gedaechtnis.bereich_pruefen(self.s.konfig, wert or "")

    def zustand(self, query):
        s, sp, k = self.s, self.s.speicher, self.s.konfig
        bereich = self._bereich(query.get("bereich"))
        alle = query.get("alle") == "1"
        filter_bereich = None if alle else bereich
        kennung = query.get("gespraech")
        gespraech = sp.gespraech(kennung) if kennung else None
        if gespraech and gespraech["bereich"] != bereich:
            gespraech = None
        gespraech = gespraech or sp.letztes_gespraech(bereich)
        auftraege = sp.auftraege(bereich=filter_bereich, limit=12)
        for a in auftraege:
            a["schritte"] = sp.schritte(a["id"])
        sichtbare_bereiche = None if alle else [bereich, "allgemein", "technik"]
        aktiv, zuletzt = sp.schritte_aktiv(), sp.schritte_zuletzt(8)
        for eintrag in aktiv + zuletzt:
            eintrag["rolle_name"] = rollen.ROLLEN.get(eintrag["rolle"], {}).get("name", eintrag["rolle"])
        return 200, {
            "ok": True,
            "status": s.status(),
            "system": {
                "provider": s.provider.status(), "stimme": s.stimme.status(), "modelle": k.modelle,
                "modell_ausweichen": k.modell_ausweichen, "bereiche": k.bereiche, "werkstatt": k.werkstatt_pfad,
                "ordner": sorted(n for n in k.wurzeln() if n != "werkstatt"), "daten_ordner": k.daten_ordner,
                "verbrauch": sp.verbrauch_heute(), "letzte_sicherung": sp.meta("letzte_sicherung"),
                "beschaeftigt": s.provider.beschaeftigt(), "gesperrt": s.agent.gesperrt.is_set(),
                "freigabe_minuten": k.freigabe_minuten, "erinnerungen_sprechen": bool(k.erinnerungen_sprechen),
                "lan": bool(k.lan), "max_aufrufe_pro_auftrag": k.max_aufrufe_pro_auftrag,
                "werkzeuge": [{"name": w.name, "beschreibung": w.beschreibung, "gesperrt": w.name in k.deaktivierte_werkzeuge,
                               "stufe": "wechselnd" if callable(w.stufe) else werkzeuge.STUFEN[w.stufe]}
                              for w in s.agent.register.alle()],
            },
            "bereich": bereich,
            "gespraech": gespraech["kennung"] if gespraech else None,
            "nachrichten": sp.nachrichten(gespraech["kennung"], 60) if gespraech else [],
            "zaehler": sp.zaehler(),
            "todos": sp.todos(bereich=filter_bereich, limit=80),
            "auftraege": auftraege,
            "freigaben": sp.freigaben("offen"),
            "fakten": sp.fakten(status=["bestaetigt", "vorschlag"], bereiche=sichtbare_bereiche),
            "erinnerungen": sp.erinnerungen(bereich=filter_bereich),
            "fokus": gedaechtnis.fokus(sp, bereich),
            "agenten": {"orchestrator": {"name": "Orchestrator", "modell": k.modell_fuer("chat"),
                                         "zustand": "gesperrt" if s.agent.gesperrt.is_set()
                                         else ("arbeitet" if s.provider.beschaeftigt() else "bereit")},
                        "rollen": [{"id": rolle_id, "name": rolle["name"], "modell": k.modell_fuer(rolle["modell"]),
                                    "werkzeuge": list(rolle["werkzeuge"]) if rolle["werkzeuge"] else []}
                                   for rolle_id, rolle in rollen.ROLLEN.items() if rolle_id != "allgemein"],
                        "aktiv": aktiv, "zuletzt": zuletzt},
            "diagramme": {"stunden": sp.anfragen_stunden(24), "antwortzeiten": sp.antwortzeiten(30)},
            "log": letzte_eintraege(s.log.datei, 14),
        }

    def logs(self, query):
        anzahl = _int(query.get("anzahl", "50"))
        if anzahl is None:
            return 400, {"ok": False, "fehler": "anzahl muss eine Zahl sein."}
        return 200, {"ok": True, "eintraege": letzte_eintraege(self.s.log.datei, max(1, min(anzahl, 500)))}

    def audit(self, query):
        anzahl = _int(query.get("anzahl", "100"))
        if anzahl is None:
            return 400, {"ok": False, "fehler": "anzahl muss eine Zahl sein."}
        return 200, {"ok": True, "eintraege": self.s.speicher.audit_liste(max(1, min(anzahl, 500)), art=query.get("art") or None)}

    def export(self, query):
        self.s.speicher.audit_schreiben("export")
        return 200, {"ok": True, "daten": self.s.speicher.exportieren()}

    def stimmen(self, query):
        return 200, {"ok": True, "stimme": self.s.stimme.status()}

    def suche(self, query):
        text = (query.get("q") or "").strip()
        if not text:
            return 400, {"ok": False, "fehler": "q fehlt."}
        return 200, {"ok": True, "treffer": gedaechtnis.suchen(self.s.speicher, self._bereich(query.get("bereich")), text)}

    def auftrag_details(self, query):
        auftrag = self.s.speicher.auftrag(_int(query.get("id")) or 0)
        if not auftrag:
            return 404, {"ok": False, "fehler": "Diesen Auftrag gibt es nicht."}
        auftrag["schritte"] = self.s.speicher.schritte(auftrag["id"])
        return 200, {"ok": True, "auftrag": auftrag}

    # --------------------------------------------------------- Gespräch ---

    def anfrage(self, daten):
        text = daten.get("text")
        if not isinstance(text, str) or not text.strip():
            return 400, {"ok": False, "fehler": "Feld \"text\" fehlt oder ist leer."}
        if len(text) > MAX_TEXT:
            return 413, {"ok": False, "fehler": "Der Text ist länger als %d Zeichen." % MAX_TEXT}
        kennung = daten.get("gespraech")
        if kennung is not None and not isinstance(kennung, str):
            return 400, {"ok": False, "fehler": "Ungültige Gesprächskennung."}
        with self.s.zaehlsperre:
            self.s.anfragen += 1
        return self.s.agent.chat(text, gespraech=kennung or None, bereich=daten.get("bereich"))

    def abbrechen(self, daten):
        return 200, {"ok": True, "abgebrochen": self.s.agent.provider.abbrechen()}

    def sprich(self, daten):
        text = daten.get("text")
        if not isinstance(text, str) or not text.strip():
            return 400, {"ok": False, "fehler": "Feld \"text\" fehlt."}
        if self.s.agent.gesperrt.is_set():
            return 423, {"ok": False, "fehler": "Notstopp ist aktiv."}
        return 200, {"ok": True, "gesprochen": self.s.stimme.sprich(text[:MAX_TEXT])}

    def still(self, daten):
        self.s.stimme.stopp()
        return 200, {"ok": True}

    def einstellungen(self, daten):
        neu = {k: daten[k] for k in EINSTELLUNGEN if k in daten}
        if not neu:
            return 400, {"ok": False, "fehler": "Keine bekannte Einstellung."}
        try:
            self.s.konfig.aktualisieren(neu)
        except KonfigFehler as fehler:
            return 400, {"ok": False, "fehler": str(fehler)}
        self.s.speicher.audit_schreiben("einstellungen", details=neu)
        return 200, {"ok": True, "stimme": self.s.stimme.status(), "modelle": self.s.konfig.modelle}

    def provider_pruefen(self, daten):
        return 200, {"ok": True, "provider": self.s.provider.pruefen()}

    # --------------------------------------------------------- Gedächtnis ---

    def fakt(self, daten):
        sp, k = self.s.speicher, self.s.konfig
        aktion, fakt_id = daten.get("aktion"), _int(daten.get("id"))
        try:
            if aktion == "hinzufuegen":
                bereich = daten.get("bereich") or k.bereiche[0]
                art = daten.get("art") or "fakt"
                if bereich not in k.alle_bereiche() or art not in FAKT_ARTEN:
                    return 400, {"ok": False, "fehler": "Unbekannter Bereich oder unbekannte Art."}
                neu_id, neu = sp.fakt_hinzufuegen(str(daten.get("text") or ""), bereich=bereich, art=art, quelle="nutzer",
                                                  wichtig=bool(daten.get("wichtig")))
                return 200, {"ok": True, "id": neu_id, "neu": neu}
            vorhanden = sp.fakt(fakt_id) if fakt_id else None
            if not vorhanden:
                return 404, {"ok": False, "fehler": "Diesen Eintrag gibt es nicht."}
            if aktion == "bestaetigen":
                sp.fakt_setzen(fakt_id, status="bestaetigt")
            elif aktion == "verwerfen":
                sp.fakt_setzen(fakt_id, status="verworfen")
            elif aktion == "loeschen":
                sp.fakt_loeschen(fakt_id)
            elif aktion == "aendern":
                felder = {}
                if "text" in daten:
                    felder["text"] = str(daten["text"])
                if "bereich" in daten:
                    if daten["bereich"] not in k.alle_bereiche():
                        return 400, {"ok": False, "fehler": "Unbekannter Bereich."}
                    felder["bereich"] = daten["bereich"]
                if "art" in daten:
                    if daten["art"] not in FAKT_ARTEN:
                        return 400, {"ok": False, "fehler": "Unbekannte Art."}
                    felder["art"] = daten["art"]
                if "wichtig" in daten:
                    felder["wichtig"] = int(bool(daten["wichtig"]))
                sp.fakt_setzen(fakt_id, **felder)
            else:
                return 400, {"ok": False, "fehler": "Unbekannte Aktion."}
        except ValueError as fehler:
            return 400, {"ok": False, "fehler": str(fehler)}
        sp.audit_schreiben("gedaechtnis_" + aktion, details={"id": fakt_id}, bereich=vorhanden["bereich"])
        return 200, {"ok": True}

    def todo(self, daten):
        sp, k = self.s.speicher, self.s.konfig
        aktion = daten.get("aktion")
        try:
            if aktion == "anlegen":
                bereich = self._bereich(daten.get("bereich"))
                faellig = zeit.lokal_zu_utc(daten["faellig"]) if daten.get("faellig") else None
                todo_id = sp.todo_anlegen(str(daten.get("titel") or ""), bereich, str(daten.get("beschreibung") or ""),
                                          daten.get("prioritaet") if daten.get("prioritaet") in ("hoch", "normal", "niedrig") else "normal",
                                          faellig, quelle="nutzer")
                return 200, {"ok": True, "id": todo_id}
            todo = sp.todo(_int(daten.get("id")) or 0)
            if not todo:
                return 404, {"ok": False, "fehler": "Diese Aufgabe gibt es nicht."}
            if aktion == "status" and daten.get("status") in ("offen", "erledigt"):
                sp.todo_setzen(todo["id"], status=daten["status"])
            elif aktion == "loeschen":
                sp.todo_loeschen(todo["id"])
            else:
                return 400, {"ok": False, "fehler": "Unbekannte Aktion."}
        except ValueError as fehler:
            return 400, {"ok": False, "fehler": str(fehler)}
        return 200, {"ok": True, "bereiche": k.bereiche}

    def erinnerung(self, daten):
        sp = self.s.speicher
        aktion = daten.get("aktion")
        try:
            if aktion == "anlegen":
                erinnerung_id = sp.erinnerung_anlegen(str(daten.get("text") or ""), zeit.lokal_zu_utc(str(daten.get("faellig") or "")),
                                                      self._bereich(daten.get("bereich")))
                return 200, {"ok": True, "id": erinnerung_id}
            erinnerung_id = _int(daten.get("id")) or 0
            if aktion == "erledigt":
                ok = sp.erinnerung_setzen(erinnerung_id, status="erledigt")
            elif aktion == "loeschen":
                ok = sp.erinnerung_loeschen(erinnerung_id)
            else:
                return 400, {"ok": False, "fehler": "Unbekannte Aktion."}
        except ValueError as fehler:
            return 400, {"ok": False, "fehler": str(fehler)}
        return (200, {"ok": True}) if ok else (404, {"ok": False, "fehler": "Diese Erinnerung gibt es nicht."})

    # ----------------------------------------------------------- Aufträge ---

    def auftrag(self, daten):
        aktion = daten.get("aktion")
        try:
            if aktion == "planen":
                ziel = daten.get("ziel")
                if not isinstance(ziel, str) or not ziel.strip():
                    return 400, {"ok": False, "fehler": "Das Ziel fehlt."}
                return 200, self.s.agent.planer.erstellen(ziel, self._bereich(daten.get("bereich")))
            if aktion == "neu_planen":
                return 200, self.s.agent.planer.neu_planen(_int(daten.get("id")) or 0, str(daten.get("antworten") or ""))
            start_um = None
            if aktion == "starten" and daten.get("start_um"):
                start_um = zeit.lokal_zu_utc(str(daten["start_um"]))
                if start_um <= zeit.jetzt():
                    return 400, {"ok": False, "fehler": "Der Startzeitpunkt liegt in der Vergangenheit."}
        except (WerkzeugFehler, ValueError) as fehler:
            return 400, {"ok": False, "fehler": str(fehler)}
        ok, meldung = self.s.laeufer.steuern(str(aktion), _int(daten.get("id")) or 0, start_um=start_um)
        return (200 if ok else 409), {"ok": ok, "meldung": meldung, "fehler": None if ok else meldung}

    # -------------------------------------------- Freigaben, Rechte, Notstopp ---

    def freigabe(self, daten):
        freigabe_id, entscheidung = _int(daten.get("id")), daten.get("entscheidung")
        if not freigabe_id or entscheidung not in ("ja", "nein"):
            return 400, {"ok": False, "fehler": "id und entscheidung (ja oder nein) fehlen."}
        return self.s.agent.freigabe_beantworten(freigabe_id, entscheidung == "ja")

    def werkzeug(self, daten):
        name, gesperrt = daten.get("name"), daten.get("gesperrt")
        if not isinstance(name, str) or not isinstance(gesperrt, bool):
            return 400, {"ok": False, "fehler": "name und gesperrt (true/false) fehlen."}
        if not self.s.agent.berechtigung.werkzeug_sperren(name, gesperrt):
            return 404, {"ok": False, "fehler": "Dieses Werkzeug gibt es nicht."}
        return 200, {"ok": True, "gesperrt": self.s.konfig.deaktivierte_werkzeuge}

    def notstopp(self, daten):
        self.s.agent.notstopp("Nutzer")
        return 200, {"ok": True, "gesperrt": True}

    def entsperren(self, daten):
        self.s.agent.entsperren()
        return 200, {"ok": True, "gesperrt": False}

    # ----------------------------------------------------------- Wartung ---

    def profil_einlesen(self, daten):
        ergebnis = self.s.agent.profil_einlesen()
        return (200 if ergebnis["ok"] else 404), ergebnis

    def umgebung(self, daten):
        ergebnis = self.s.agent.aktion_ausfuehren(werkzeuge.Kontext(self.s.agent, self.s.konfig.bereiche[0], quelle="chat"),
                                                  {"name": "umgebung_pruefen", "roh": {}, "koerper": None})
        return 200, {"ok": ergebnis["status"] == "ausgefuehrt", "text": ergebnis["text"]}

    def sicherung(self, daten):
        ziel = self.s.zeitplan.sicherung_machen()
        return 200, {"ok": True, "datei": ziel}

    def alles_loeschen(self, daten):
        if daten.get("bestaetigung") != BESTAETIGUNG_LOESCHEN:
            return 400, {"ok": False, "fehler": "Zur Sicherheit muss \"%s\" eingegeben werden." % BESTAETIGUNG_LOESCHEN}
        self.s.speicher.alles_loeschen()
        self.s.speicher.audit_schreiben("alles_geloescht")
        return 200, {"ok": True}
