#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Gedächtnis, Ebene 1 und 2 - Tagesberichte und gezieltes Nachschlagen.

Warum zwei Ebenen? Ein Verlauf von Monaten passt in kein Kontextfenster und
macht jede Antwort langsam und teuer. Deshalb:

* Ebene 1: Abends fasst Jarvis den Tag in wenigen Sätzen zusammen. Viele
  solcher Berichte passen gleichzeitig in den Systemprompt.
* Ebene 2: Vor jeder Antwort werden die tragenden Wörter der Frage in Notizen,
  Kontakten, Tagesberichten und früheren Äußerungen nachgeschlagen. Nur die
  Treffer werden beigelegt.
"""

import re
from datetime import datetime, timedelta

import config
from modules.memory import Memory, db_schema_anlegen, heute_datum, zeitstempel

SCHEMA_RECALL = """
CREATE TABLE IF NOT EXISTS tagesberichte (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    datum TEXT NOT NULL,
    zusammenfassung TEXT NOT NULL,
    entscheidungen TEXT DEFAULT '',
    offen TEXT DEFAULT '',
    angelegt TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_berichte_datum ON tagesberichte(datum);
"""

# Wörter, die in fast jedem Satz vorkommen und deshalb nichts einengen.
STOPPWOERTER = {
    "aber", "alle", "allem", "allen", "aller", "alles", "also", "andere", "auch",
    "auf", "aus", "bei", "beim", "bin", "bis", "bist", "dann", "dass", "dein",
    "deine", "dem", "den", "denn", "der", "des", "dich", "die", "dies", "diese",
    "diesem", "diesen", "dieser", "dieses", "dir", "doch", "dort", "durch",
    "ein", "eine", "einem", "einen", "einer", "eines", "einfach", "etwas",
    "euch", "euer", "eure", "für", "fuer", "gegen", "gewesen", "hab", "habe",
    "haben", "hat", "hatte", "hatten", "hier", "hin", "ich", "ihm", "ihn",
    "ihnen", "ihr", "ihre", "immer", "ist", "jede", "jedem", "jeden", "jeder",
    "jetzt", "kann", "kannst", "können", "koennen", "machen", "mehr", "mein",
    "meine", "mich", "mir", "mit", "muss", "musst", "müssen", "muessen", "nach",
    "nicht", "noch", "nun", "nur", "oben", "oder", "ohne", "schon", "sehr",
    "sein", "seine", "seit", "sich", "sie", "sind", "soll", "sollen", "sondern",
    "sonst", "über", "ueber", "und", "uns", "unser", "unter", "vom", "von",
    "vor", "war", "waren", "warum", "was", "weg", "weil", "weiter", "welche",
    "wenn", "werde", "werden", "wie", "wieder", "will", "wir", "wird", "wirst",
    "wo", "wollen", "wurde", "wurden", "zum", "zur", "zwar", "zwischen",
    "steht", "gibt", "geht", "mach", "sage", "sagen", "bitte", "danke", "jarvis",
}


def schluesselwoerter(text: str, mindestlaenge: int = 4) -> list:
    """Zerlegt einen Satz in seine tragenden Wörter (ab 4 Zeichen, ohne Stoppwörter)."""
    if not text:
        return []
    roh = re.findall(r"[0-9A-Za-zÄÖÜäöüß_-]+", str(text).lower())
    treffer = []
    for wort in roh:
        if len(wort) < mindestlaenge:
            continue
        if wort in STOPPWOERTER:
            continue
        if wort not in treffer:
            treffer.append(wort)
    return treffer[:12]


class Recall:
    """Langzeitgedächtnis: schreibt Tagesberichte und schlägt gezielt nach."""

    def __init__(self, memory: Memory = None):
        self.memory = memory or Memory()
        db_schema_anlegen(SCHEMA_RECALL, self.memory.db_pfad)

    # -- Ebene 1: Tagesberichte --------------------------------------------

    def tagesbericht_speichern(self, zusammenfassung: str, entscheidungen: str = "",
                               offen: str = "", datum: str = "") -> dict:
        """Legt den Bericht eines Tages ab (ein Bericht pro Datum)."""
        zusammenfassung = (zusammenfassung or "").strip()
        if not zusammenfassung:
            return {"ok": False, "fehler": "Der Tagesbericht ist leer."}
        datum = (datum or heute_datum()).strip()
        vorhanden = self.memory._lesen(
            "SELECT id FROM tagesberichte WHERE datum=? LIMIT 1", (datum,))
        if vorhanden:
            self.memory._schreiben(
                "UPDATE tagesberichte SET zusammenfassung=?, entscheidungen=?, offen=?, "
                "angelegt=? WHERE id=?",
                (zusammenfassung, entscheidungen, offen, zeitstempel(), vorhanden[0]["id"]))
            return {"ok": True, "id": vorhanden[0]["id"], "datum": datum, "ersetzt": True}
        nummer = self.memory._schreiben(
            "INSERT INTO tagesberichte (datum, zusammenfassung, entscheidungen, offen, angelegt) "
            "VALUES (?,?,?,?,?)",
            (datum, zusammenfassung, entscheidungen, offen, zeitstempel()))
        return {"ok": True, "id": nummer, "datum": datum, "ersetzt": False}

    def tagesberichte_letzte(self, anzahl: int = 7) -> list:
        """Die jüngsten Tagesberichte, neuester zuerst."""
        return self.memory._lesen(
            "SELECT * FROM tagesberichte ORDER BY datum DESC, id DESC LIMIT ?", (anzahl,))

    def tagesberichte_suchen(self, begriff: str, limit: int = 6) -> list:
        """Sucht in Tagesberichten nach einem Begriff."""
        begriff = (begriff or "").strip()
        if not begriff:
            return []
        muster = "%%%s%%" % begriff
        return self.memory._lesen(
            "SELECT * FROM tagesberichte WHERE zusammenfassung LIKE ? OR entscheidungen LIKE ? "
            "OR offen LIKE ? ORDER BY datum DESC LIMIT ?", (muster, muster, muster, limit))

    # -- Ebene 2: Nachschlagen ---------------------------------------------

    def nachschlagen(self, frage: str, pro_quelle: int = 4) -> dict:
        """Sucht die tragenden Wörter einer Frage in allen Gedächtnisquellen."""
        woerter = schluesselwoerter(frage)
        gefunden = {"woerter": woerter, "notizen": [], "kontakte": [],
                    "berichte": [], "aeusserungen": []}
        if not woerter:
            return gefunden
        gesehen = {"notizen": set(), "kontakte": set(), "berichte": set(),
                   "aeusserungen": set()}
        for wort in woerter:
            for notiz in self.memory.notizen_suchen(wort, pro_quelle):
                if notiz["id"] not in gesehen["notizen"]:
                    gesehen["notizen"].add(notiz["id"])
                    gefunden["notizen"].append(notiz)
            for kontakt in self.memory.kontakt_suchen(wort, pro_quelle):
                if kontakt["id"] not in gesehen["kontakte"]:
                    gesehen["kontakte"].add(kontakt["id"])
                    gefunden["kontakte"].append(kontakt)
            for bericht in self.tagesberichte_suchen(wort, pro_quelle):
                if bericht["id"] not in gesehen["berichte"]:
                    gesehen["berichte"].add(bericht["id"])
                    gefunden["berichte"].append(bericht)
            for zeile in self.memory.aeusserungen_suchen(wort, pro_quelle):
                if zeile["id"] not in gesehen["aeusserungen"]:
                    gesehen["aeusserungen"].add(zeile["id"])
                    gefunden["aeusserungen"].append(zeile)
        for schluessel in ("notizen", "kontakte", "berichte", "aeusserungen"):
            gefunden[schluessel] = gefunden[schluessel][:8]
        return gefunden

    def gedaechtnis_block(self, frage: str = "") -> str:
        """Baut den Gedächtnisteil des Systemprompts.

        Enthält immer die offenen Punkte der letzten 14 Tage und die letzten
        Tagesberichte, dazu die zur Frage passenden Treffer.
        """
        teile = []

        punkte = self.memory.punkte_offen(tage=14)
        if punkte:
            zeilen = ["Offene Punkte der letzten 14 Tage:"]
            for punkt in punkte[:12]:
                faellig = (" (fällig %s)" % punkt["faellig"]) if punkt["faellig"] else ""
                zeilen.append("- [%d] %s%s" % (punkt["id"], punkt["text"], faellig))
            teile.append("\n".join(zeilen))

        berichte = self.tagesberichte_letzte(7)
        if berichte:
            zeilen = ["Was an den letzten Tagen war:"]
            for bericht in berichte:
                satz = "- %s: %s" % (bericht["datum"], bericht["zusammenfassung"])
                if bericht["offen"]:
                    satz += " Noch offen: %s" % bericht["offen"]
                zeilen.append(satz)
            teile.append("\n".join(zeilen))

        if frage:
            treffer = self.nachschlagen(frage)
            zeilen = []
            for notiz in treffer["notizen"]:
                zeilen.append("- Notiz vom %s: %s" % (notiz["angelegt"][:10], notiz["text"]))
            for kontakt in treffer["kontakte"]:
                beschreibung = ", ".join(
                    [t for t in (kontakt["firma"], kontakt["telefon"], kontakt["email"],
                                 kontakt["notiz"]) if t])
                zeilen.append("- Kontakt %s: %s" % (kontakt["name"], beschreibung or "keine Details"))
            for bericht in treffer["berichte"]:
                zeilen.append("- Tagesbericht %s: %s" % (bericht["datum"],
                                                         bericht["zusammenfassung"]))
            for zeile in treffer["aeusserungen"]:
                zeilen.append("- Er sagte am %s: %s" % (zeile["zeit"][:10], zeile["text"][:200]))
            if zeilen:
                teile.append("Passend zur aktuellen Frage:\n" + "\n".join(zeilen[:14]))

        if not teile:
            return ""
        return "Das weißt du aus früheren Tagen:\n\n" + "\n\n".join(teile)

    # -- Tag zusammenfassen -------------------------------------------------

    def tag_zusammenfassen(self, agent=None, datum: str = "") -> dict:
        """Fasst den heutigen Tag zusammen - mit Claude, sonst mechanisch."""
        datum = datum or heute_datum()
        beginn = "%s 00:00:00" % datum
        ende = "%s 23:59:59" % datum

        aeusserungen = self.memory._lesen(
            "SELECT rolle, text, zeit FROM verlauf WHERE zeit BETWEEN ? AND ? ORDER BY id",
            (beginn, ende))
        aktionen = self.memory._lesen(
            "SELECT werkzeug, status, zeit FROM aktionen WHERE zeit BETWEEN ? AND ? ORDER BY id",
            (beginn, ende))
        punkte = self.memory.punkte_offen(tage=1)

        if not aeusserungen and not aktionen:
            bericht = "An diesem Tag ist nichts festgehalten worden."
            self.tagesbericht_speichern(bericht, "", "", datum)
            return {"ok": True, "datum": datum, "zusammenfassung": bericht, "quelle": "leer"}

        rohtext = []
        for zeile in aeusserungen[-60:]:
            rohtext.append("%s: %s" % ("Er" if zeile["rolle"] == "user" else "Jarvis",
                                       zeile["text"][:400]))
        werkzeugliste = ", ".join(sorted({a["werkzeug"] for a in aktionen})) or "keine"

        if agent is not None and getattr(agent, "einsatzbereit", lambda: False)():
            auftrag = (
                "Fasse diesen Arbeitstag für dein eigenes Gedächtnis zusammen. "
                "Antworte als JSON mit den Schlüsseln zusammenfassung, entscheidungen, offen. "
                "zusammenfassung: drei bis fünf Sätze, worum es ging. "
                "entscheidungen: was entschieden wurde, ein Satz oder leer. "
                "offen: was offen blieb, ein Satz oder leer.\n\n"
                "Gespräche des Tages:\n%s\n\nBenutzte Werkzeuge: %s"
                % ("\n".join(rohtext) or "keine", werkzeugliste))
            antwort = agent.json_anfrage(auftrag)
            if antwort.get("ok"):
                daten = antwort["daten"]
                self.tagesbericht_speichern(
                    str(daten.get("zusammenfassung", "")).strip(),
                    str(daten.get("entscheidungen", "")).strip(),
                    str(daten.get("offen", "")).strip(), datum)
                return {"ok": True, "datum": datum, "quelle": "claude",
                        "zusammenfassung": daten.get("zusammenfassung", ""),
                        "entscheidungen": daten.get("entscheidungen", ""),
                        "offen": daten.get("offen", "")}

        # Rückfallebene ohne Claude: mechanisch, aber ehrlich.
        themen = []
        for zeile in aeusserungen:
            if zeile["rolle"] != "user":
                continue
            for wort in schluesselwoerter(zeile["text"])[:3]:
                if wort not in themen:
                    themen.append(wort)
        zusammenfassung = ("%d Gespräche, %d Aktionen. Themen: %s."
                           % (len([z for z in aeusserungen if z["rolle"] == "user"]),
                              len(aktionen), ", ".join(themen[:10]) or "keine erkennbaren"))
        offen_text = "; ".join(p["text"] for p in punkte[:5])
        self.tagesbericht_speichern(zusammenfassung, "", offen_text, datum)
        return {"ok": True, "datum": datum, "quelle": "mechanisch",
                "zusammenfassung": zusammenfassung, "entscheidungen": "", "offen": offen_text}

    def rueckblick(self, tage: int = 7) -> str:
        """Ein zusammenhängender Text über die letzten Tage - für den Wochenrückblick."""
        grenze = (datetime.now() - timedelta(days=tage)).strftime("%Y-%m-%d")
        berichte = self.memory._lesen(
            "SELECT * FROM tagesberichte WHERE datum>=? ORDER BY datum", (grenze,))
        if not berichte:
            return "Für die letzten %d Tage liegen noch keine Tagesberichte vor." % tage
        zeilen = []
        for bericht in berichte:
            zeilen.append("%s: %s" % (bericht["datum"], bericht["zusammenfassung"]))
            if bericht["entscheidungen"]:
                zeilen.append("   Entschieden: %s" % bericht["entscheidungen"])
            if bericht["offen"]:
                zeilen.append("   Offen: %s" % bericht["offen"])
        return "\n".join(zeilen)

    # -- Protokoll ----------------------------------------------------------

    @staticmethod
    def tag_aufloesen(text: str = "") -> str:
        """Macht aus 'heute', 'gestern', '07.10.' oder '2026-10-07' ein Datum.

        Gibt einen leeren Text zurück, wenn der Tag nicht zu lesen ist - der
        Aufrufer sagt das dann, statt still den falschen Tag zu zeigen.
        """
        roh = (text or "").strip().lower()
        heute = datetime.now()
        if roh in ("", "heute"):
            return heute.strftime("%Y-%m-%d")
        if roh == "gestern":
            return (heute - timedelta(days=1)).strftime("%Y-%m-%d")
        if roh == "vorgestern":
            return (heute - timedelta(days=2)).strftime("%Y-%m-%d")
        for muster in ("%Y-%m-%d", "%d.%m.%Y", "%d.%m.%y"):
            try:
                return datetime.strptime(roh, muster).strftime("%Y-%m-%d")
            except ValueError:
                pass
        try:  # '07.10.' ohne Jahr: das laufende Jahr
            tag = datetime.strptime(roh.rstrip(".") + ".%d" % heute.year, "%d.%m.%Y")
            return tag.strftime("%Y-%m-%d")
        except ValueError:
            return ""

    def protokoll(self, tag: str = "heute", thema: str = "", tage: int = 1) -> dict:
        """Das Protokoll eines Tages: Gespräche, Aktionen, Tagesbericht, Offenes.

        ``tage`` > 1 nimmt die davorliegenden Tage dazu (Wochenprotokoll).
        ``thema`` engt die Gespräche auf Zeilen mit diesem Begriff ein.
        """
        datum = self.tag_aufloesen(tag)
        if not datum:
            return {"ok": False, "text": "Den Tag '%s' kann ich nicht lesen. "
                                         "Sag heute, gestern oder ein Datum." % tag}
        tage = max(1, min(int(tage or 1), 31))
        erster = (datetime.strptime(datum, "%Y-%m-%d")
                  - timedelta(days=tage - 1)).strftime("%Y-%m-%d")
        von, bis = "%s 00:00:00" % erster, "%s 23:59:59" % datum
        thema = (thema or "").strip()

        gespraeche = [{"rolle": z["rolle"], "text": z["text"], "zeit": z["zeit"]}
                      for z in self.memory.verlauf_zeitraum(von, bis, thema)]
        aktionen = [{"werkzeug": a["werkzeug"], "status": a["status"],
                     "ergebnis": (a["ergebnis"] or "")[:200], "zeit": a["zeit"]}
                    for a in self.memory.aktionen_zeitraum(von, bis)]
        berichte = self.memory._lesen(
            "SELECT * FROM tagesberichte WHERE datum BETWEEN ? AND ? ORDER BY datum, id",
            (erster, datum))
        berichte = [{"datum": b["datum"], "zusammenfassung": b["zusammenfassung"],
                     "entscheidungen": b["entscheidungen"], "offen": b["offen"]}
                    for b in berichte]
        punkte = [{"id": p["id"], "text": p["text"], "faellig": p["faellig"]}
                  for p in self.memory.punkte_offen()]

        von_ihm = len([g for g in gespraeche if g["rolle"] == "user"])
        saetze = []
        zeitraum = datum if tage == 1 else "%s bis %s" % (erster, datum)
        if not gespraeche and not aktionen:
            saetze.append("Für %s ist nichts protokolliert%s." % (
                zeitraum, (" zum Thema %s" % thema) if thema else ""))
        else:
            saetze.append("%s: %d Äußerungen von dir, %d Aktionen%s." % (
                zeitraum, von_ihm, len(aktionen),
                (" zum Thema %s" % thema) if thema else ""))
            if berichte:
                saetze.append(berichte[-1]["zusammenfassung"])
            letzte = [g for g in gespraeche if g["rolle"] == "user"][-3:]
            if letzte:
                saetze.append("Zuletzt hast du gesagt: %s" % " / ".join(
                    g["text"][:120] for g in letzte))
            werkzeuge = sorted({a["werkzeug"] for a in aktionen})
            if werkzeuge:
                saetze.append("Benutzt: %s." % ", ".join(werkzeuge[:8]))
        if punkte:
            saetze.append("Offen: %s." % "; ".join(p["text"] for p in punkte[:4]))

        return {"ok": True, "datum": datum, "von": erster, "tage": tage,
                "thema": thema, "gespraeche": gespraeche, "aktionen": aktionen,
                "berichte": berichte, "offene_punkte": punkte,
                "text": " ".join(saetze)}

