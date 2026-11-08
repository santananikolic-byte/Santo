# -*- coding: utf-8 -*-
"""Agent-Kern - verbindet Gedächtnis, Denken, Werkzeuge und Berechtigung.

Eine Runde:  Kontext aus dem Gedächtnis -> Claude Code antwortet (ohne eigene
Werkzeuge) -> Aktionen aus dem Text lesen -> jede Aktion prüfen und ausführen
oder als Freigabe vorlegen -> Ergebnisse zurück ins Modell (höchstens
``max_runden``). Erst ein echtes Werkzeugergebnis macht aus einer Ankündigung
eine erledigte Sache.
"""

import os
import re
import shutil
import subprocess

from . import gedaechtnis, gehirn, rollen, umgebung
from .kalender import MacKalender
from .mail import MacMail
from .programmierer import Programmierer
from .freigaben import Berechtigung
from .provider import ProviderFehler
from .werkzeuge import Kontext, Register, WerkzeugFehler, aktionen_parsen

PROJEKT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MAX_AKTIONEN_PRO_RUNDE = 6
MAX_VERLAUF = 14
MAX_TEXT_IM_VERLAUF = 4000
MAX_ERGEBNIS_IM_PROMPT = 6000
NAMEN = {"nutzer": "Nutzer", "jarvis": "JARVIS", "werkzeug": "WERKZEUGERGEBNISSE", "ereignis": "EREIGNIS"}


class Runde:
    def __init__(self, text, ergebnisse, roh, bausteine=(), art="chat"):
        self.text = text
        self.ergebnisse = ergebnisse
        self.roh = roh
        self.bausteine = list(bausteine)  # welche Wissensbausteine im Systemprompt standen
        self.art = art  # mit welcher Denkstufe gefragt wurde ("chat" = gründlich, "schnell")


class Agent:
    def __init__(self, konfig, log, speicher, provider, stimme=None):
        self.konfig = konfig
        self.log = log
        self.speicher = speicher
        self.provider = provider
        self.stimme = stimme
        self.gesperrt = provider.gesperrt  # eine Quelle für den Notstopp
        self.register = Register(self)
        self.berechtigung = Berechtigung(self)
        self.planer = None  # vom Server gesetzt
        self.mail = MacMail()  # E-Mail über die Mail-App des Macs (osascript)
        self.kalender = MacKalender()  # Termine über die Kalender-App des Macs (osascript)
        self.programmierer = Programmierer(self)  # Programmier-Aufträge an Claude Code, im Hintergrund
        provider.beobachter = self._anfrage_erfassen
        if speicher.meta("gesperrt") == "1":
            self.gesperrt.set()

    # ------------------------------------------------------- Grundlagen ---

    def _anfrage_erfassen(self, art, modell, dauer_ms, ok, fehler_art, tokens_ein, tokens_aus, auftrag_id):
        self.speicher.anfrage_erfassen(art, modell, dauer_ms, ok, fehler_art, tokens_ein, tokens_aus, auftrag_id)

    def sichtbare_werkzeuge(self, rolle="allgemein"):
        return {w.name for w in self.register.alle() if self.berechtigung.sichtbar(w, rolle)}

    def denkrahmen(self, rolle="allgemein", frage="", verlauf=""):
        """Systemprompt aus Grundregeln, passenden Wissensbausteinen, Werkzeugen und Rolle (siehe gehirn.py).

        Gibt (Systemprompt, gewählte Bausteine) zurück."""
        bausteine = gehirn.bausteine_waehlen(frage, verlauf, rolle)
        prompt = gehirn.systemprompt(self.register.katalog(rolle), self.sichtbare_werkzeuge(rolle), bausteine,
                                     rollen.ROLLEN.get(rolle, {}).get("auftrag", ""))
        return prompt, bausteine

    def system_prompt(self, rolle="allgemein", frage="", verlauf=""):
        return self.denkrahmen(rolle, frage, verlauf)[0]

    @staticmethod
    def _verlauf_kurz(transkript):
        """Das letzte Gesprächsstück - für Rückfragen wie "und was kostet das?", damit der passende Wissensbaustein
        dabei bleibt. Von Werkzeugergebnissen zählt nur, WELCHES Werkzeug lief (z. B. "werkzeug:mail_lesen"), nie der
        Inhalt: eine fremde E-Mail kann so nicht steuern, welches Wissen JARVIS bekommt."""
        teile = []
        for rolle, text in transkript[-4:]:
            if rolle in ("nutzer", "jarvis"):
                teile.append(text[:300])
            elif rolle == "werkzeug":
                teile += ["werkzeug:%s" % name for name in re.findall(r'<werkzeugergebnis werkzeug="([a-z_]+)"', text)]
        return "\n".join(teile)

    @staticmethod
    def _kuerzen(text, grenze):
        return text if len(text) <= grenze else text[:grenze] + " …(gekürzt)"

    def prompt_bauen(self, ctx, transkript, frage=""):
        teile = [gedaechtnis.kontext_text(self.speicher, self.konfig, ctx.bereich, frage), ""]
        if transkript:
            teile.append("[GESPRÄCH]")
            for rolle, text in transkript:
                teile.append("%s: %s" % (NAMEN.get(rolle, rolle), self._kuerzen(text, MAX_TEXT_IM_VERLAUF)))
            teile.append("")
        teile.append("Antworte jetzt als JARVIS auf den letzten Eintrag.")
        return "\n".join(teile)

    @staticmethod
    def ergebnisse_text(ergebnisse):
        """Werkzeugergebnisse als abgegrenzte, unvertrauenswürdige Daten."""
        teile = []
        for e in ergebnisse:
            text = e["text"][:MAX_ERGEBNIS_IM_PROMPT].replace("</werkzeugergebnis", "<\\/werkzeugergebnis")
            text = text.replace("<aktion", "&lt;aktion")  # Aktionen entstehen nur aus eigenen Antworten
            teile.append('<werkzeugergebnis werkzeug="%s" status="%s" vertrauen="%s">\n%s\n</werkzeugergebnis>' % (
                e["werkzeug"], e["status"], "gering" if e["extern"] else "mittel", text))
        return "\n".join(teile)

    def _ergebnis(self, w, name, status, text, stufe=0, freigabe_id=None, params=None):
        ok = status == "ausgefuehrt"
        return {"werkzeug": name, "kurz": w.kurz(params) if (w and params) else name, "status": status, "text": text,
                "stufe": stufe, "freigabe_id": freigabe_id, "daten": bool(w and w.liefert_daten and ok),
                "extern": bool(w and w.extern and ok)}

    # --------------------------------------------------------- Aktionen ---

    def aktion_ausfuehren(self, ctx, akt):
        w = self.register.get(akt["name"])
        if w is None:
            sichtbar = [x.name for x in self.register.alle() if self.berechtigung.sichtbar(x, ctx.rolle)]
            self.speicher.audit_schreiben("unbekannt", werkzeug=akt["name"][:60], bereich=ctx.bereich,
                                          auftrag_id=ctx.auftrag_id)
            return self._ergebnis(None, akt["name"][:60], "unbekannt",
                                  "Das Werkzeug %r gibt es nicht. Verfügbar: %s." % (akt["name"][:60], ", ".join(sichtbar)))
        try:
            params = self.register.validieren(w, akt["roh"], akt["koerper"], ctx)
            entscheidung = self.berechtigung.entscheiden(w, params, ctx)
            if entscheidung.art == "freigabe":
                freigabe_id = self.berechtigung.anfordern(w, params, ctx, entscheidung.stufe, entscheidung.grund)
                return self._ergebnis(w, w.name, "freigabe_offen", "Wartet auf die Freigabe des Nutzers (#%d)." % freigabe_id,
                                      stufe=entscheidung.stufe, freigabe_id=freigabe_id, params=params)
        except WerkzeugFehler as fehler:
            return self._ergebnis(w, w.name, "ungueltig", str(fehler))
        if entscheidung.art == "verweigert":
            self.speicher.audit_schreiben("verweigert", werkzeug=w.name, bereich=ctx.bereich, ergebnis=entscheidung.grund,
                                          auftrag_id=ctx.auftrag_id)
            return self._ergebnis(w, w.name, "gesperrt", entscheidung.grund)
        return self.ausfuehren(w, params, ctx, entscheidung.stufe)

    def ausfuehren(self, w, params, ctx, stufe, freigabe_id=None):
        """Führt ein bereits geprüftes Werkzeug aus und schreibt das Audit."""
        if self.gesperrt.is_set():
            return self._ergebnis(w, w.name, "gesperrt", "Notstopp ist aktiv.", params=params)
        try:
            ergebnis = w.handler(ctx, params)
            status, text = "ausgefuehrt", ergebnis["text"]
            if w.extern:
                ctx.extern = True
        except WerkzeugFehler as fehler:
            status, text = "fehler", str(fehler)
        except Exception as fehler:  # noqa: BLE001 - ein Werkzeugfehler darf den Agenten nie abstürzen lassen
            self.log.ereignis("werkzeug_absturz", "ERROR", werkzeug=w.name, grund=repr(fehler))
            status, text = "fehler", "Interner Fehler im Werkzeug %s." % w.name
        einzelheiten = {k: (v if k != "inhalt" else "<%d Zeichen>" % len(v)) for k, v in params.items() if not k.startswith("_")}
        self.speicher.audit_schreiben("werkzeug", werkzeug=w.name, stufe=stufe, bereich=ctx.bereich, details=einzelheiten,
                                      ergebnis="%s: %s" % (status, text[:300]), auftrag_id=ctx.auftrag_id,
                                      freigabe_id=freigabe_id)
        self.log.ereignis("werkzeug", werkzeug=w.name, berechtigungsstufe=stufe, status=status, auftrag=ctx.auftrag_id)
        return self._ergebnis(w, w.name, status, text, stufe=stufe, freigabe_id=freigabe_id, params=params)

    def zaehle_aufruf(self, auftrag_id):
        """Zählt einen Modellaufruf für den Auftrag und stoppt beim Limit."""
        if self.speicher.auftrag_aufruf_zaehlen(auftrag_id) > self.konfig.max_aufrufe_pro_auftrag:
            raise ProviderFehler("aufruflimit", "Das Aufruflimit dieses Auftrags (%d Modellaufrufe) ist erreicht."
                                 % self.konfig.max_aufrufe_pro_auftrag)

    @staticmethod
    def rollen_modell(rolle):
        return rollen.ROLLEN.get(rolle, rollen.ROLLEN["allgemein"])["modell"]

    def benachrichtigen(self, titel, text, sprechen=False):
        """Mitteilung des Macs (der Text geht als Argument an osascript, nie in den Skripttext) und optional laut."""
        programm = shutil.which("osascript")
        if programm:
            try:
                subprocess.run([programm, "-e", "on run argv", "-e", "display notification (item 1 of argv) with title (item 2 of argv)",  # noqa: S603
                                "-e", "end run", text[:200], titel[:60]], capture_output=True, timeout=10)
            except (OSError, subprocess.SubprocessError):
                pass
        if sprechen and self.stimme and self.konfig.vorlesen:
            self.stimme.sprich("%s. %s" % (titel, text))

    def runde(self, ctx, transkript, art="chat", frage=""):
        """Ein Modellaufruf samt Ausführung der Aktionen. Wirft ProviderFehler."""
        if ctx.auftrag_id:
            self.zaehle_aufruf(ctx.auftrag_id)
        system, bausteine = self.denkrahmen(ctx.rolle, frage, self._verlauf_kurz(transkript))
        # Denkstufe: Einfaches im Gespräch beantwortet das schnelle Modell, alles Wichtige das gründliche.
        if (art == "chat" and ctx.quelle == "chat" and self.konfig.denkstufen
                and gehirn.denkstufe(frage, bausteine) == "schnell"):
            art = "schnell"
        roh = self.provider.fragen(self.prompt_bauen(ctx, transkript, frage), system, art=art, auftrag_id=ctx.auftrag_id)
        text, aktionen = aktionen_parsen(roh["antwort"])
        ergebnisse = []
        for i, akt in enumerate(aktionen):
            if i >= MAX_AKTIONEN_PRO_RUNDE:
                ergebnisse.append(self._ergebnis(None, "zu_viele_aktionen", "ungueltig",
                                                 "Mehr als %d Aktionen in einer Antwort; der Rest wurde ignoriert." % MAX_AKTIONEN_PRO_RUNDE))
                break
            ergebnisse.append(self.aktion_ausfuehren(ctx, akt))
        return Runde(text, ergebnisse, roh, bausteine, art)

    # ------------------------------------------------------------- Chat ---

    def _transkript(self, gespraech):
        eintraege = []
        for n in self.speicher.nachrichten(gespraech, MAX_VERLAUF):
            text = n["text"]
            aktionen = (n.get("meta") or {}).get("aktionen")
            if n["rolle"] == "jarvis" and aktionen:
                text += "\n[Aktionen: %s]" % "; ".join("%s (%s)" % (a["kurz"], a["status"]) for a in aktionen)
            eintraege.append((n["rolle"], text))
        return eintraege

    @staticmethod
    def _kompakt(ergebnisse):
        return [{"werkzeug": e["werkzeug"], "kurz": e["kurz"], "status": e["status"], "text": e["text"][:300],
                 "stufe": e["stufe"], "freigabe_id": e["freigabe_id"]} for e in ergebnisse]

    def chat(self, text, gespraech=None, bereich=None):
        """Beantwortet eine Nachricht. Gibt (HTTP-Code, Antwort) zurück."""
        text = (text or "").strip()
        if self.gesperrt.is_set():
            return 423, {"ok": False, "art": "gesperrt", "fehler": "Notstopp ist aktiv. Erst entsperren."}
        sp = self.speicher
        vorhanden = sp.gespraech(gespraech) if gespraech else None
        if gespraech and not vorhanden:
            return 404, {"ok": False, "art": "unbekannt", "fehler": "Dieses Gespräch gibt es nicht."}
        if vorhanden:
            bereich = vorhanden["bereich"]
        else:
            bereich = gedaechtnis.bereich_pruefen(self.konfig, bereich or "")
            gespraech = sp.gespraech_anlegen(bereich, titel=text[:60])
        sp.nachricht_hinzufuegen(gespraech, "nutzer", text)
        ctx = Kontext(self, bereich, gespraech=gespraech)
        transkript = self._transkript(gespraech)
        texte, ergebnisse, runden, dauer = [], [], 0, 0
        letzte_roh, bausteine, denkstufe = {}, [], "chat"
        try:
            while True:
                runde = self.runde(ctx, transkript, art="chat", frage=text)
                letzte_roh, bausteine, denkstufe = runde.roh, runde.bausteine, runde.art
                dauer += runde.roh.get("dauer_ms") or 0
                if runde.text:
                    texte.append(runde.text)
                ergebnisse += runde.ergebnisse
                if any(e["daten"] for e in runde.ergebnisse) and runden + 1 < self.konfig.max_runden:
                    transkript = transkript + [("jarvis", runde.text or "(nur Aktionen)"),
                                               ("werkzeug", self.ergebnisse_text(runde.ergebnisse))]
                    runden += 1
                    continue
                break
        except ProviderFehler as fehler:
            sp.nachricht_hinzufuegen(gespraech, "ereignis", "Keine Antwort: %s" % fehler,
                                     meta={"fehler": fehler.art})
            codes = {"nicht_installiert": 503, "nicht_angemeldet": 503, "kein_provider": 503, "gesperrt": 423,
                     "limit": 429, "beschaeftigt": 429, "aufruflimit": 429, "zeitueberschreitung": 504,
                     "abgebrochen": 499}
            return codes.get(fehler.art, 502), {"ok": False, "gespraech": gespraech, "bereich": bereich,
                                                "art": fehler.art, "fehler": str(fehler)}
        antwort = texte[-1] if texte else "\n".join("%s: %s" % (e["kurz"], e["text"][:200]) for e in ergebnisse) or "…"
        antwort, richtigstellung = gehirn.ehrlichkeit_pruefen(antwort, self._bestaetigt(gespraech, ergebnisse), frage=text)
        if richtigstellung:
            sp.audit_schreiben("richtigstellung", bereich=bereich, details={"arten": richtigstellung})
            self.log.ereignis("richtigstellung", "WARNING", arten=",".join(richtigstellung), gespraech=gespraech)
        kompakt = self._kompakt(ergebnisse)
        sp.nachricht_hinzufuegen(gespraech, "jarvis", antwort, meta={
            "aktionen": kompakt, "modell": letzte_roh.get("modell"), "ausgewichen": letzte_roh.get("ausgewichen"),
            "dauer_ms": dauer, "bausteine": bausteine, "denkstufe": denkstufe, "richtigstellung": richtigstellung})
        return 200, {"ok": True, "gespraech": gespraech, "bereich": bereich, "antwort": antwort, "aktionen": kompakt,
                     "freigaben": [e["freigabe_id"] for e in ergebnisse if e["status"] == "freigabe_offen"],
                     "modell": letzte_roh.get("modell"), "ausgewichen": letzte_roh.get("ausgewichen"), "dauer_ms": dauer,
                     "bausteine": bausteine, "denkstufe": denkstufe, "richtigstellung": richtigstellung}

    def _bestaetigt(self, gespraech, ergebnisse):
        """Werkzeuge, die für DIESE Antwort wirklich ausgeführt wurden: in dieser Runde oder per Freigabe, die seit der
        letzten Antwort von JARVIS erteilt und ausgeführt wurde. Ein früherer Versand belegt keinen späteren."""
        namen = {e["werkzeug"] for e in ergebnisse if e["status"] == "ausgefuehrt"}
        # "Fertig programmiert" belegt nur die Fertig-Meldung eines Laufs - nicht schon der Start ("programmieren").
        if any(e["werkzeug"] == "programm_stand" and e["status"] == "ausgefuehrt"
               and e["text"].startswith("Programmier-Auftrag fertig") for e in ergebnisse):
            namen.add("programm_fertig")
        nachrichten = self.speicher.nachrichten(gespraech, 60)
        letzte = max([i for i, n in enumerate(nachrichten) if n["rolle"] == "jarvis"], default=-1)
        for n in nachrichten[letzte + 1:]:
            meta = n.get("meta") or {}
            if n["rolle"] != "ereignis":
                continue
            if meta.get("programmieren") and meta.get("status") == "fertig":
                namen.add("programm_fertig")
            rec = self.speicher.freigabe(meta["freigabe"]) if meta.get("freigabe") else None
            if rec and rec["status"] == "ausgefuehrt":
                namen.add(rec["werkzeug"])
        return namen

    # ----------------------------------------------------- Freigaben (UI) ---

    def freigabe_beantworten(self, freigabe_id, ja):
        """Der Nutzer entscheidet. Das Ergebnis wird dem Gespräch als Ereignis hinzugefügt, damit JARVIS es beim nächsten Mal weiß."""
        rec = self.speicher.freigabe(freigabe_id)
        code, antwort = self.berechtigung.erteilen(freigabe_id) if ja else self.berechtigung.ablehnen(freigabe_id)
        if rec and rec["gespraech"] and code == 200:
            if ja:
                ergebnis = antwort["ergebnis"]
                text = "Freigabe #%d erteilt und ausgeführt (%s): %s" % (freigabe_id, ergebnis["status"], ergebnis["text"][:1500])
            else:
                text = "Freigabe #%d wurde vom Nutzer abgelehnt (%s). Es wurde nichts ausgeführt." % (freigabe_id, rec["werkzeug"])
            self.speicher.nachricht_hinzufuegen(rec["gespraech"], "ereignis", text, meta={"freigabe": freigabe_id})
        return code, antwort

    # --------------------------------------------------- Notstopp, Umgebung ---

    def notstopp(self, grund="Nutzer"):
        self.gesperrt.set()
        self.speicher.meta_setzen("gesperrt", "1")
        self.provider.abbrechen()
        self.programmierer.abbrechen()
        if self.stimme:
            self.stimme.stopp()
        self.berechtigung.alle_offenen_ablehnen("Notstopp")
        self.speicher.audit_schreiben("notstopp", details={"grund": grund})
        self.log.ereignis("notstopp", "WARNING", grund=grund)

    def entsperren(self):
        self.gesperrt.clear()
        self.speicher.meta_loeschen("gesperrt")
        self.speicher.audit_schreiben("entsperrt")
        self.log.ereignis("entsperrt")

    def umgebung_merken(self, info):
        self.speicher.fakten_loeschen_quelle("umgebung")
        for zeile in umgebung.zeilen(info):
            self.speicher.fakt_hinzufuegen(zeile, bereich="technik", art="technik", quelle="umgebung")

    def profil_einlesen(self):
        return gedaechtnis.profil_importieren(self.speicher, self.konfig, os.path.join(PROJEKT, "BRAIN.md"))

