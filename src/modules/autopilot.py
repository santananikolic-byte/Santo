#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Der Autopilot - Jarvis arbeitet weiter, auch wenn niemand fragt.

Das Gespräch ist reaktiv: Jarvis tut etwas, wenn man ihm etwas sagt. Ein
Betrieb läuft aber auch dazwischen. Der Autopilot ist der Teil, der von selbst
arbeitet - mit der Mannschaft aus ``team.py``.

**Er bereitet vor, er handelt nicht.** Das ist die eine Regel, auf der alles
andere steht. Im Hintergrund ist niemand da, der eine Freigabe geben könnte.
Also bekommt jede Fachkraft hier nur die Werkzeuge, die *keine* Freigabe
brauchen. Mails, Anrufe, Termine und Skriptausführung bleiben außen vor. Was
dabei herauskommt, sind Entwürfe: ein fertiges Angebot, ein Nachfasstext, eine
Antwort auf eine Mail. Sie landen im **Postfach**. Ob etwas davon rausgeht,
entscheidet der Chef - mit der normalen Freigabe, wie überall.

Zwei Quellen für Arbeit:

* **Aufträge** des Nutzers: "Schreib im Hintergrund das Angebot für Müller."
* **Nerven**: Fühler, die von selbst Arbeit finden. Ein Interessent, bei dem
  das Nachfassen fällig ist. Ungelesene Post. Ein Beleg, der fehlt.

Der Autopilot ist **standardmäßig aus** und hat Bremsen: Ruhezeiten, eine
Obergrenze je Stunde und das Monatslimit für Claude. Jeder Lauf steht im
Gedankenlog, jedes Ergebnis im Postfach.
"""

import threading
import time
from datetime import datetime, timedelta

import config
from modules.memory import Memory, db_schema_anlegen, heute_datum, zeitstempel
from modules.router import Gedankenlog
from modules.team import HINTERGRUND_HINWEIS, ROLLEN  # noqa: F401

SCHEMA_AUTOPILOT = """
CREATE TABLE IF NOT EXISTS autopilot (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    schluessel TEXT DEFAULT '',
    titel TEXT NOT NULL,
    rolle TEXT NOT NULL,
    auftrag TEXT NOT NULL,
    quelle TEXT DEFAULT 'nutzer',
    prioritaet INTEGER DEFAULT 2,
    status TEXT DEFAULT 'offen',
    ergebnis TEXT DEFAULT '',
    gesehen INTEGER DEFAULT 0,
    angelegt TEXT NOT NULL,
    begonnen TEXT DEFAULT '',
    beendet TEXT DEFAULT '',
    dauer REAL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_autopilot_status ON autopilot(status);
CREATE INDEX IF NOT EXISTS idx_autopilot_schluessel ON autopilot(schluessel);
"""

# Welche Fachkraft passt zu welchen Wörtern? Reihenfolge zählt: das Erste gewinnt.
ROLLEN_STICHWORTE = (
    ("programmierer", ("programm", "skript", "script", "code", "automatisier", "auswertung bauen")),
    ("akquisiteur", ("angebot", "nachfass", "interessent", "lead", "kunde", "kunden", "akquise", "verkauf")),
    ("postmeister", ("mail", "post ", "posteingang", "antwort auf")),
    ("buchhalter", ("beleg", "buchung", "rechnung", "umsatzsteuer", "vorsteuer")),
    ("terminplaner", ("termin", "kalender", "tagesplan", "wochenplan")),
    ("controller", ("zahlen", "cashflow", "kennzahl", "auswertung", "umsatz")),
    ("rechercheur", ("recherch", "herausfinden", "such ", "preise vergleichen")),
    ("privatsekretaer", ("fixkosten", "privat", "versicherung")),
)

def rolle_raten(text: str) -> str:
    """Sucht die passende Fachkraft für einen Auftragstext."""
    klein = (text or "").lower() + " "
    for rolle, woerter in ROLLEN_STICHWORTE:
        if any(w in klein for w in woerter):
            return rolle
    return "akquisiteur"


def _uhrzeit_minuten(text: str):
    try:
        stunde, minute = str(text).split(":")
        return int(stunde) * 60 + int(minute)
    except (ValueError, AttributeError):
        return None


def in_ruhezeit(jetzt: datetime = None) -> bool:
    """Liegt die Zeit außerhalb von AUTOPILOT_VON bis AUTOPILOT_BIS?"""
    jetzt = jetzt or datetime.now()
    von, bis = _uhrzeit_minuten(config.AUTOPILOT_VON), _uhrzeit_minuten(config.AUTOPILOT_BIS)
    if von is None or bis is None or von == bis:
        return False
    minute = jetzt.hour * 60 + jetzt.minute
    if von < bis:
        return not (von <= minute < bis)
    return not (minute >= von or minute < bis)


class Autopilot:
    """Warteschlange, Nerven und der Hintergrundlauf."""

    def __init__(self, tools, ausgabe=None):
        self.tools = tools
        self.memory = tools.memory if hasattr(tools, "memory") else Memory()
        db_schema_anlegen(SCHEMA_AUTOPILOT, self.memory.db_pfad)
        self.ausgabe = ausgabe or (lambda text: print("[autopilot] %s" % text))
        self.gedankenlog = Gedankenlog()
        self._laeuft = False
        self._thread = None
        self._sperre = threading.Lock()
        self.arbeitet_an = ""
        self.letzter_fehler = ""
        # Nach einem Absturz mitten in der Arbeit: nicht als "läuft" hängen lassen.
        self.memory._schreiben("UPDATE autopilot SET status='offen' WHERE status='laeuft'")

    # -- Schalter -----------------------------------------------------------

    @staticmethod
    def an() -> bool:
        return bool(config.AUTOPILOT_AN)

    def schalten(self, an: bool) -> dict:
        """Schaltet den Autopiloten ein oder aus und merkt es sich."""
        config.env_setzen("AUTOPILOT_AN", "ja" if an else "nein")
        if an:
            gestartet = self.start()
            return {"ok": True, "an": True,
                    "text": "Der Autopilot ist an. Er arbeitet zwischen %s und %s Uhr, "
                            "höchstens %d Aufträge pro Stunde, und schickt nichts ab."
                            % (config.AUTOPILOT_VON, config.AUTOPILOT_BIS,
                               config.AUTOPILOT_MAX_PRO_STUNDE)
                            + ("" if gestartet else " (Er lief schon.)")}
        self.stop()
        return {"ok": True, "an": False, "text": "Der Autopilot ist aus."}

    # -- Warteschlange ------------------------------------------------------

    def auftrag_anlegen(self, titel: str, auftrag: str = "", rolle: str = "",
                        prioritaet: int = 2, quelle: str = "nutzer",
                        schluessel: str = "") -> dict:
        """Stellt Arbeit in die Warteschlange. Doppelte (gleicher Schlüssel) nicht."""
        titel = (titel or "").strip()[:140]
        auftrag = (auftrag or titel).strip()[:3000]
        if not titel:
            return {"ok": False, "fehler": "Sag mir, was im Hintergrund erledigt werden soll."}
        if schluessel:
            vorhanden = self.memory._lesen(
                "SELECT id FROM autopilot WHERE schluessel=?", (schluessel,))
            if vorhanden:
                return {"ok": True, "doppelt": True, "id": vorhanden[0]["id"],
                        "text": "Das steht schon in der Liste."}
        gefunden = ""
        if rolle:
            gefunden = self.tools.team.rolle_finden(rolle) or ""
            if not gefunden:
                return {"ok": False, "fehler": "Die Rolle '%s' kenne ich nicht. Ich habe: %s."
                                               % (rolle, ", ".join(ROLLEN))}
        rolle_key = gefunden or rolle_raten(titel + " " + auftrag)
        prioritaet = min(3, max(1, int(prioritaet or 2)))
        nummer = self.memory._schreiben(
            "INSERT INTO autopilot (schluessel, titel, rolle, auftrag, quelle, prioritaet, "
            "status, angelegt) VALUES (?,?,?,?,?,?, 'offen', ?)",
            (schluessel, titel, rolle_key, auftrag, quelle, prioritaet, zeitstempel()))
        return {"ok": True, "id": nummer, "rolle": rolle_key,
                "text": "Notiert. %s kümmert sich im Hintergrund darum%s."
                        % (ROLLEN[rolle_key]["name"][:1].upper() + ROLLEN[rolle_key]["name"][1:],
                           "" if self.an() else ", sobald du den Autopiloten einschaltest")}

    def _hinweis(self, schluessel: str, titel: str, text: str) -> bool:
        """Ein Ergebnis ohne Claude: eine Beobachtung, die direkt ins Postfach geht."""
        if self.memory._lesen("SELECT id FROM autopilot WHERE schluessel=?", (schluessel,)):
            return False
        jetzt = zeitstempel()
        self.memory._schreiben(
            "INSERT INTO autopilot (schluessel, titel, rolle, auftrag, quelle, prioritaet, "
            "status, ergebnis, angelegt, begonnen, beendet) "
            "VALUES (?,?,?,?, 'nerv', 2, 'fertig', ?, ?, ?, ?)",
            (schluessel, titel[:140], "controller", titel[:140], text[:3000], jetzt, jetzt, jetzt))
        return True

    def warteschlange(self, limit: int = 30) -> list:
        return self.memory._lesen(
            "SELECT * FROM autopilot WHERE status IN ('offen','laeuft') "
            "ORDER BY prioritaet, id LIMIT ?", (limit,))

    def postfach(self, limit: int = 30) -> list:
        """Was fertig ist und noch nicht angesehen wurde."""
        return self.memory._lesen(
            "SELECT * FROM autopilot WHERE status IN ('fertig','fehler') AND gesehen=0 "
            "ORDER BY id DESC LIMIT ?", (limit,))

    def verlauf(self, limit: int = 15) -> list:
        return self.memory._lesen(
            "SELECT * FROM autopilot WHERE status IN ('fertig','fehler') AND gesehen=1 "
            "ORDER BY id DESC LIMIT ?", (limit,))

    def gesehen_setzen(self, nummer=None) -> dict:
        """Hakt ein Ergebnis ab - oder alle."""
        if nummer in (None, "", "alle"):
            self.memory._schreiben("UPDATE autopilot SET gesehen=1 WHERE status IN ('fertig','fehler')")
            return {"ok": True, "text": "Alles abgehakt."}
        try:
            nummer = int(nummer)
        except (TypeError, ValueError):
            return {"ok": False, "fehler": "Das ist keine gültige Nummer."}
        self.memory._schreiben("UPDATE autopilot SET gesehen=1 WHERE id=?", (nummer,))
        return {"ok": True, "text": "Abgehakt."}

    def postfach_text(self) -> str:
        """Ein gesprochener Überblick über das Postfach."""
        offen = self.postfach(10)
        if not offen:
            return "Im Postfach liegt nichts Neues."
        zeilen = ["%d Ergebnisse warten auf dich." % len(offen)]
        for e in offen[:5]:
            zeilen.append("%s: %s" % (e["titel"], (e["ergebnis"] or "").strip().split("\n")[0][:160]))
        return " ".join(zeilen)

    # -- Nerven -------------------------------------------------------------

    def nerven_pruefen(self) -> list:
        """Sucht von selbst nach Arbeit. Gibt die neu angelegten Titel zurück."""
        neu, heute = [], heute_datum()

        def mit(titel, auftrag, rolle, schluessel, prio=2):
            ergebnis = self.auftrag_anlegen(titel, auftrag, rolle, prio, "nerv", schluessel)
            if ergebnis.get("ok") and not ergebnis.get("doppelt"):
                neu.append(titel)

        # 1. Nachfassen, das fällig ist - das Geld, das sonst still verloren geht.
        try:
            liste = self.tools.akquise.nachfassliste()
            for e in (liste.get("eintraege") or [])[:3]:
                kontakt = e.get("ansprechpartner") or "den Ansprechpartner"
                mit("Nachfassen bei %s vorbereiten" % e["firma"],
                    "Bereite das Nachfassen bei %s vor (Ansprechpartner: %s, Stufe: %s, "
                    "nächster Schritt: %s, geschätzter Wert %s Euro im Monat). Schreibe eine "
                    "kurze, freundliche Nachricht, die der Chef so abschicken kann, und "
                    "einen Satz, wie er das Telefonat einleiten könnte. Schau vorher in "
                    "den Notizen nach, was mit diesem Kunden bisher besprochen wurde."
                    % (e["firma"], kontakt, e.get("stufe", ""), e.get("schritt", ""),
                       e.get("wert_monat", 0)),
                    "akquisiteur", "nachfass:%s:%s" % (e["id"], heute), 1)
        except Exception as fehler:
            self.letzter_fehler = "Nachfassliste: %s" % fehler

        # 2. Ungelesene Post, höchstens alle drei Stunden.
        try:
            if self.tools.mail.lesen_moeglich():
                block = "%s:%d" % (heute, datetime.now().hour // 3)
                if not self.memory._lesen("SELECT id FROM autopilot WHERE schluessel=?",
                                          ("post:" + block,)):
                    post = self.tools.mail.ungelesene(5)
                    if post.get("ok") and post.get("anzahl", 0) > 0:
                        mit("Posteingang durchsehen (%d ungelesen)" % post["anzahl"],
                            "Sieh den Posteingang durch. Sortiere nach Dringlichkeit und "
                            "schreibe für alles, was eine Antwort braucht, einen fertigen "
                            "Antwortentwurf. Eine Anfrage, die nach Auftrag riecht, "
                            "markierst du ausdrücklich.", "postmeister", "post:" + block, 1)
        except Exception as fehler:
            self.letzter_fehler = "Post: %s" % fehler

        # 3. Beobachtungen ohne Claude: kosten nichts, sind aber oft das Wichtigste.
        try:
            belege = self.tools.bookkeeping.fehlende_belege()
            if belege.get("anzahl"):
                if self._hinweis("belege:%s" % heute, "Belege fehlen", belege["text"]):
                    neu.append("Belege fehlen")
        except Exception as fehler:
            self.letzter_fehler = "Belege: %s" % fehler
        try:
            anstehend = self.tools.privat.erinnerungen_faellig(3)
            if anstehend.get("anzahl"):
                if self._hinweis("erinnerung:%s" % heute, "Es steht etwas an", anstehend["text"]):
                    neu.append("Es steht etwas an")
        except Exception as fehler:
            self.letzter_fehler = "Erinnerungen: %s" % fehler
        try:
            ueberfaellig = [p for p in self.memory.punkte_offen(60, 50)
                            if p.get("faellig") and p["faellig"] <= heute]
            if ueberfaellig:
                text = "%d offene Punkte sind fällig: %s." % (
                    len(ueberfaellig), "; ".join(p["text"] for p in ueberfaellig[:4]))
                if self._hinweis("punkte:%s" % heute, "Offene Punkte sind fällig", text):
                    neu.append("Offene Punkte sind fällig")
        except Exception as fehler:
            self.letzter_fehler = "Punkte: %s" % fehler
        return neu

    # -- Arbeiten -----------------------------------------------------------

    def _in_der_letzten_stunde(self) -> int:
        grenze = (datetime.now() - timedelta(hours=1)).strftime("%Y-%m-%d %H:%M:%S")
        zeilen = self.memory._lesen(
            "SELECT count(*) AS n FROM autopilot WHERE begonnen>=? "
            "AND (dauer>0 OR status='laeuft')", (grenze,))
        return int(zeilen[0]["n"]) if zeilen else 0

    def gesperrt(self, jetzt: datetime = None) -> str:
        """Warum der Autopilot gerade nicht arbeitet - oder leer, wenn er darf."""
        if not self.an():
            return "aus"
        if in_ruhezeit(jetzt):
            return "Ruhezeit (%s bis %s Uhr)" % (config.AUTOPILOT_VON, config.AUTOPILOT_BIS)
        if not self.tools.agent or not self.tools.agent.einsatzbereit():
            return "kein Anthropic-Schlüssel"
        if self.gedankenlog.limit_erreicht():
            return "Monatslimit erreicht"
        if self._in_der_letzten_stunde() >= config.AUTOPILOT_MAX_PRO_STUNDE:
            return "Stundengrenze erreicht"
        return ""

    def naechsten_abarbeiten(self) -> dict:
        """Nimmt den wichtigsten offenen Auftrag und arbeitet ihn ab."""
        with self._sperre:
            offene = self.memory._lesen(
                "SELECT * FROM autopilot WHERE status='offen' ORDER BY prioritaet, id LIMIT 1")
            if not offene:
                return {"ok": True, "leer": True}
            eintrag = offene[0]
            self.memory._schreiben(
                "UPDATE autopilot SET status='laeuft', begonnen=? WHERE id=?",
                (zeitstempel(), eintrag["id"]))
        self.arbeitet_an = eintrag["titel"]
        beginn = time.time()
        try:
            ergebnis = self.tools.team.beauftragen(
                eintrag["rolle"], eintrag["auftrag"], max_runden=6, hintergrund=True)
        except Exception as fehler:
            ergebnis = {"ok": False, "fehler": str(fehler)}
        dauer = round(time.time() - beginn, 1)
        self.arbeitet_an = ""
        if ergebnis.get("ok"):
            status, text = "fertig", (ergebnis.get("text") or "").strip() or "Kein Ergebnis."
        else:
            status, text = "fehler", ergebnis.get("fehler", "Das hat nicht geklappt.")
        self.memory._schreiben(
            "UPDATE autopilot SET status=?, ergebnis=?, beendet=?, dauer=?, gesehen=0 WHERE id=?",
            (status, text[:6000], zeitstempel(), max(dauer, 0.1), eintrag["id"]))
        if status == "fertig":
            self.ausgabe("Autopilot: %s ist fertig. Das Ergebnis liegt im Postfach." % eintrag["titel"])
        return {"ok": status == "fertig", "id": eintrag["id"], "titel": eintrag["titel"],
                "status": status, "dauer": dauer}

    def tick(self, jetzt: datetime = None) -> dict:
        """Ein Durchlauf: Nerven prüfen, dann bis zu ein paar Aufträge abarbeiten."""
        grund = self.gesperrt(jetzt)
        if grund:
            return {"ok": True, "gearbeitet": 0, "gesperrt": grund}
        neu = self.nerven_pruefen()
        erledigt = 0
        for _ in range(max(1, config.AUTOPILOT_MAX_PRO_RUNDE)):
            if self.gesperrt(jetzt):
                break
            ergebnis = self.naechsten_abarbeiten()
            if ergebnis.get("leer"):
                break
            erledigt += 1
        return {"ok": True, "gearbeitet": erledigt, "neu_gefunden": neu}

    # -- Hintergrundlauf ----------------------------------------------------

    def _schleife(self):
        # Beim Start kurz warten: erst soll die Oberfläche da sein.
        for _ in range(20):
            if not self._laeuft:
                return
            time.sleep(1)
        while self._laeuft:
            try:
                if self.an():
                    self.tick()
            except Exception as fehler:
                self.letzter_fehler = str(fehler)
                print("[autopilot] Fehler im Lauf: %s" % fehler)
            for _ in range(max(1, int(config.AUTOPILOT_ABSTAND_MIN)) * 60):
                if not self._laeuft:
                    break
                time.sleep(1)

    def start(self) -> bool:
        if self._laeuft:
            return False
        self._laeuft = True
        self._thread = threading.Thread(target=self._schleife, daemon=True,
                                        name="jarvis-autopilot")
        self._thread.start()
        return True

    def stop(self):
        self._laeuft = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=3)

    def zustand(self) -> dict:
        """Alles, was die Oberfläche braucht."""
        grund = self.gesperrt()
        return {"ok": True, "an": self.an(), "laeuft": self._laeuft,
                "arbeitet_an": self.arbeitet_an, "gesperrt": grund,
                "von": config.AUTOPILOT_VON, "bis": config.AUTOPILOT_BIS,
                "abstand_min": config.AUTOPILOT_ABSTAND_MIN,
                "max_pro_stunde": config.AUTOPILOT_MAX_PRO_STUNDE,
                "postfach": self.postfach(30), "warteschlange": self.warteschlange(30),
                "verlauf": self.verlauf(10), "letzter_fehler": self.letzter_fehler}


SEITE_AUTOPILOT = r"""<!DOCTYPE html>
<html lang="de"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<link rel="icon" href="/symbol.svg" type="image/svg+xml">
<title>Jarvis – Autopilot</title>
<style>
:root{--grund:#EDF0F5;--karte:#fff;--karte2:#F4F6FA;--text:#0E1726;--leise:#566176;--rand:#D9DFE8;
 --akzent:#2447E6;--akzent-text:#fff;--weich:#E3E9FF;--ok:#1B7F4B;--fehler:#BE2F28;
 --sans:-apple-system,BlinkMacSystemFont,"Helvetica Neue",Arial,sans-serif}
@media (prefers-color-scheme:dark){:root{--grund:#0C121C;--karte:#151D2B;--karte2:#1B2434;--text:#E8EDF5;
 --leise:#9AA6BA;--rand:#27324A;--akzent:#7F9CFF;--akzent-text:#0C1220;--weich:#1E2B57;--ok:#5FD08F;--fehler:#FF7B72}}
*{box-sizing:border-box;margin:0;padding:0}
body{background:var(--grund);color:var(--text);font-family:var(--sans);-webkit-font-smoothing:antialiased;
 padding:0 16px 48px;max-width:720px;margin:0 auto;line-height:1.5}
a{color:var(--akzent);text-decoration:none;font-weight:600}
.kopf{padding:20px 0 6px}.kopf h1{font-size:26px;margin:8px 0 4px}
.leise{color:var(--leise);font-size:14px}
.karte{background:var(--karte);border:1px solid var(--rand);border-radius:14px;padding:16px;margin-top:14px}
.zeile{display:flex;gap:10px;align-items:center;flex-wrap:wrap;justify-content:space-between}
h2{font-size:13px;letter-spacing:.12em;text-transform:uppercase;color:var(--leise);margin-bottom:8px}
button{font:inherit;cursor:pointer;border-radius:10px;border:1px solid var(--rand);background:var(--karte2);
 color:var(--text);padding:8px 14px;min-height:40px}
button.haupt{background:var(--akzent);color:var(--akzent-text);border-color:var(--akzent);font-weight:600}
button:disabled{opacity:.5;cursor:not-allowed}
:focus-visible{outline:2px solid var(--akzent);outline-offset:2px}
.schalter{display:flex;align-items:center;gap:12px}
.schalter .lampe{width:12px;height:12px;border-radius:50%;background:var(--leise)}
.schalter.an .lampe{background:var(--ok);box-shadow:0 0 0 4px rgba(27,127,75,.18)}
input[type=text],select,textarea{width:100%;font:inherit;color:inherit;background:var(--karte2);
 border:1px solid var(--rand);border-radius:10px;padding:9px 12px;min-height:42px}
textarea{resize:vertical;min-height:70px}
label{display:block;font-size:14px;font-weight:500;margin:10px 0 4px}
.eintrag{border-top:1px solid var(--rand);padding:12px 0}.eintrag:first-child{border-top:0}
.eintrag h3{font-size:16px;font-weight:600;overflow-wrap:anywhere}
.etikett{display:inline-block;font-size:12px;padding:1px 9px;border-radius:999px;background:var(--karte2);
 border:1px solid var(--rand);color:var(--leise);margin-right:6px}
.etikett.fehler{color:var(--fehler);border-color:var(--fehler)}
.text{white-space:pre-wrap;overflow-wrap:anywhere;margin-top:8px;font-size:15px;max-height:14em;overflow:auto;
 background:var(--karte2);border-radius:10px;padding:10px 12px}
.text.offen{max-height:none}
.aktionen{display:flex;gap:8px;flex-wrap:wrap;margin-top:10px}
.fehlertext{color:var(--fehler);font-size:14px;margin-top:6px}
</style></head><body>
<div class="kopf"><a href="/" id="zurueck">‹ Zurück zu Jarvis</a>
<h1>Autopilot</h1>
<p class="leise">Jarvis arbeitet im Hintergrund weiter und bereitet vor: Nachfassnachrichten, Antwortentwürfe,
Angebote, Skripte. Er schickt nichts ab. Alles, was fertig ist, liegt hier im Postfach, und du entscheidest.</p></div>

<div class="karte"><div class="zeile">
 <div class="schalter" id="schalter"><span class="lampe"></span><div><b id="schaltertext">…</b><div class="leise" id="schalterzeile"></div></div></div>
 <div class="zeile" style="gap:8px"><button id="jetzt" type="button">Jetzt arbeiten</button><button id="umschalten" class="haupt" type="button">Einschalten</button></div>
</div><p class="fehlertext" id="meldung" role="status"></p></div>

<div class="karte"><h2>Neuer Auftrag</h2>
<label for="titel">Was soll erledigt werden?</label><input type="text" id="titel" maxlength="140" placeholder="zum Beispiel Angebot für Hausverwaltung Müller schreiben">
<label for="auftrag">Genauer (freiwillig)</label><textarea id="auftrag" maxlength="3000" placeholder="Fläche, Intervall, Besonderheiten, was du schon weißt"></textarea>
<div class="zeile" style="margin-top:10px;justify-content:flex-start"><div style="flex:1;min-width:180px"><label for="rolle" style="margin-top:0">Wer macht es?</label><select id="rolle"><option value="">Jarvis entscheidet</option></select></div>
<button class="haupt" id="anlegen" type="button" style="align-self:flex-end">In die Warteschlange</button></div></div>

<div class="karte"><div class="zeile"><h2 style="margin:0">Postfach</h2><button id="alleabhaken" type="button">Alle abhaken</button></div><div id="postfach"></div></div>
<div class="karte"><h2>Wartet</h2><div id="warteschlange"></div></div>
<div class="karte"><h2>Zuletzt erledigt</h2><div id="verlauf"></div></div>

<script>
const SCHLUESSEL="{{SCHLUESSEL}}";
const ANHANG=SCHLUESSEL?"?schluessel="+encodeURIComponent(SCHLUESSEL):"";
document.getElementById("zurueck").href="/"+ANHANG;
const ROLLEN={buchhalter:"Buchhalter",akquisiteur:"Verkäufer",terminplaner:"Terminplaner",postmeister:"Postbearbeiter",
 kundenberater:"Kundenberater",rechercheur:"Rechercheur",controller:"Controller",privatsekretaer:"Privatsekretär",programmierer:"Programmierer"};
const $=s=>document.querySelector(s);
function h(tag,props,...kids){const e=document.createElement(tag);for(const k in (props||{})){const v=props[k];if(v==null||v===false)continue;
 if(k==="class")e.className=v;else if(k==="text")e.textContent=v;else if(k.startsWith("on"))e.addEventListener(k.slice(2),v);else e.setAttribute(k,v)}
 kids.flat().forEach(x=>{if(x!=null&&x!==false)e.append(x.nodeType?x:document.createTextNode(String(x)))});return e}
Object.keys(ROLLEN).forEach(k=>$("#rolle").append(h("option",{value:k,text:ROLLEN[k]})));
function sagen(t,fehler){const m=$("#meldung");m.textContent=t||"";m.style.color=fehler?"var(--fehler)":"var(--ok)"}
async function api(methode,daten){
 const r=await fetch("/api/autopilot"+ANHANG,methode==="POST"?{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(daten)}:undefined);
 return r.json()}
function zeit(s){s=String(s||"");return s.length>=16?s.slice(8,10)+"."+s.slice(5,7)+". · "+s.slice(11,16):""}
function eintrag(e,mitKnopf){
 const fehler=e.status==="fehler";
 const text=h("div",{class:"text",tabindex:"0"},e.ergebnis||"");
 const kn=[];
 if(e.ergebnis){kn.push(h("button",{type:"button",text:"Kopieren",onclick:async()=>{try{await navigator.clipboard.writeText(e.ergebnis);sagen("Kopiert.")}catch(x){const r=document.createRange();r.selectNodeContents(text);getSelection().removeAllRanges();getSelection().addRange(r);sagen("Markiert, jetzt kopieren.")}}}));
  kn.push(h("button",{type:"button",text:"Ganz zeigen",onclick:ev=>{text.classList.toggle("offen");ev.target.textContent=text.classList.contains("offen")?"Einklappen":"Ganz zeigen"}}))}
 if(mitKnopf)kn.push(h("button",{class:"haupt",type:"button",text:"Gesehen",onclick:async()=>{await api("POST",{aktion:"gesehen",id:e.id});lade()}}));
 return h("div",{class:"eintrag"},h("h3",{text:e.titel}),
  h("div",{class:"leise"},h("span",{class:"etikett",text:ROLLEN[e.rolle]||e.rolle}),h("span",{class:"etikett"+(fehler?" fehler":""),text:fehler?"nicht geklappt":(e.quelle==="nerv"?"selbst gefunden":"dein Auftrag")}),zeit(e.beendet||e.angelegt)),
  e.ergebnis?text:null,h("div",{class:"aktionen"},kn))}
function liste(box,daten,leer,mitKnopf,wartend){
 box.replaceChildren(...(daten.length?daten.map(e=>wartend?h("div",{class:"eintrag"},h("h3",{text:e.titel}),h("div",{class:"leise"},h("span",{class:"etikett",text:ROLLEN[e.rolle]||e.rolle}),e.status==="laeuft"?"arbeitet gerade daran":"wartet")):eintrag(e,mitKnopf)):[h("p",{class:"leise",text:leer})]))}
async function lade(){
 try{const z=await api("GET");
  $("#schalter").className="schalter"+(z.an?" an":"");
  $("#schaltertext").textContent=z.an?(z.arbeitet_an?"Arbeitet an: "+z.arbeitet_an:"Autopilot ist an"):"Autopilot ist aus";
  $("#schalterzeile").textContent=z.an?(z.gesperrt?"Pausiert: "+z.gesperrt:"Zwischen "+z.von+" und "+z.bis+" Uhr, alle "+z.abstand_min+" Minuten, höchstens "+z.max_pro_stunde+" pro Stunde"):"Er arbeitet nur, wenn du ihn einschaltest.";
  $("#umschalten").textContent=z.an?"Ausschalten":"Einschalten";$("#umschalten").dataset.an=z.an?"1":"0";
  liste($("#postfach"),z.postfach,"Im Postfach liegt nichts Neues.",true,false);
  liste($("#warteschlange"),z.warteschlange,"Nichts in der Warteschlange.",false,true);
  liste($("#verlauf"),z.verlauf,"Noch nichts abgehakt.",false,false);
 }catch(x){sagen("Der Stand ist nicht erreichbar.",true)}}
$("#umschalten").addEventListener("click",async()=>{const an=$("#umschalten").dataset.an!=="1";const r=await api("POST",{aktion:"schalten",an});sagen(r.text||r.fehler,!r.ok);lade()});
$("#jetzt").addEventListener("click",async()=>{const r=await api("POST",{aktion:"jetzt"});sagen(r.text||r.fehler,!r.ok);setTimeout(lade,1500)});
$("#alleabhaken").addEventListener("click",async()=>{await api("POST",{aktion:"gesehen"});lade()});
$("#anlegen").addEventListener("click",async()=>{const titel=$("#titel").value.trim();if(!titel){sagen("Schreib kurz, was erledigt werden soll.",true);return}
 const r=await api("POST",{aktion:"auftrag",titel,auftrag:$("#auftrag").value,rolle:$("#rolle").value});sagen(r.text||r.fehler,!r.ok);
 if(r.ok){$("#titel").value="";$("#auftrag").value=""}lade()});
lade();setInterval(()=>{if(!document.hidden)lade()},20000);
</script></body></html>
"""
