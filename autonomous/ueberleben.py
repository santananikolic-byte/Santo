# -*- coding: utf-8 -*-
"""Überlebenslage: Reicht das echte Geld? Und wo kommt als Nächstes Geld her?

Grundregeln:
- Es zählen NUR echte, geprüfte Zahlen aus den realen Finanzen. Das Simulations-Wallet zählt nie als Geld.
- Nichts wird geschätzt oder erfunden: Was nicht in der Datenbank steht, heißt „unbekannt“.
- Feste Kosten trägt nur der Eigentümer ein (Tabelle fixkosten, Migration 5) – nichts ist vorbelegt.
"""

import datetime
import html
import json
import os
import re

from . import auftraege, konfig
from .agenten.akquise import mappe_vorhanden
from .auftraege import PASSEND_AB, QUELLEN_NAMEN, datum_deutsch, dubletten, tage_bis
from .db import jetzt, neue_id
from .produkte import bereinigen
from .wallet import betrag_in_cent, euro

EIGENTUEMER = "eigentuemer"
INTERVALLE = {"monat": "pro Monat", "jahr": "pro Jahr"}
# Geldchancen: je näher am Geld, desto weiter oben (in dieser Reihenfolge)
ARTEN = {"mahnung": "Zahlung anmahnen", "rechnung": "Rechnung schreiben", "nachfassen": "Nachfassen",
         "interessent": "Angebot machen", "ausschreibung": "Ausschreibung"}
NACHFASSEN_NACH_TAGEN = 7         # versendetes Angebot ohne Entscheidung: nachfassen, wenn älter als 7 Tage
FRIST_MINDESTENS_TAGE = 3         # Ausschreibungen mit weniger Vorlauf sind kaum noch zu schaffen
OFFENE_STUFEN = ("neu", "interessant", "vorbereitet")
KEINE_FRIST = "keine Frist erfasst"
# Folgeaufgaben: Überlebensdruck ändert NUR Prioritäten und Arbeitsmenge – er schaltet nie etwas ab (PDF 6.3)
MAPPEN_JE_TAG = {"GRÜN": 1, "GELB": 3, "ROT": 5}   # harte Obergrenze: Bewerbungs-Mappen je Tag
PRIORITAET = {"ROT": 1, "GELB": 2, "GRÜN": 3}      # 1 = zuerst
NACHFASSEN_JE_TAG = 4                              # mit Suche (1) und Mappen (≤ 5) nie mehr als 10 Folgeaufgaben
NACHFASSEN_ABSTAND_TAGE = 7                        # höchstens ein Nachfass-Entwurf je Kontakt in 7 Tagen
SUCHE_ABSTAND_STUNDEN = 20                         # wie die tägliche Suche im Server
FOLGE_TYPEN = ("ausschreibungen_suchen", "ausschreibung_vorbereiten", "nachricht_entwurf")
OFFENE_AUFGABEN = ("geplant", "bereit", "laufend", "wartet_auf_freigabe")
ROLLE = "ueberleben"
AGENT_NAMEN = {"akquise": "Akquise-Agent", "sales": "Sales-Agent"}
_ISO_DATUM = re.compile(r"\d{4}-\d{2}-\d{2}")


def heute():
    return auftraege.heute()  # über das Modul – so legen Tests den Tag fest wie beim Auftrags-Radar


def _nur_eigentuemer(akteur):
    if akteur != EIGENTUEMER:
        raise PermissionError("Feste Kosten trägt nur der Eigentümer ein.")


def _datum_oder_nichts(wert):
    """Optionales Datum (JJJJ-MM-TT) – in jeder Python-Version gleich streng."""
    if wert is None or (isinstance(wert, str) and not wert.strip()):
        return None
    text = str(wert).strip()
    if not _ISO_DATUM.fullmatch(text):
        raise ValueError("Datum bitte als JJJJ-MM-TT angeben (z. B. 2026-11-01).")
    try:
        return datetime.date.fromisoformat(text).isoformat()
    except ValueError:
        raise ValueError("Ungültiges Datum: %s" % text)


# ---------------------------------------------------------------- Fixkosten
def fixkosten_anlegen(kern, bezeichnung, betrag, intervall, akteur, seit=None):
    """Feste Kosten eintragen (z. B. „Claude-Abo“, 22 €, monat). Nur der Eigentümer."""
    _nur_eigentuemer(akteur)
    name = bereinigen(bezeichnung, 120, streng=True, name="Bezeichnung")
    if not name:
        raise ValueError("Bezeichnung fehlt (z. B. „Claude-Abo“).")
    cent = betrag_in_cent(betrag)
    if intervall not in INTERVALLE:
        raise ValueError("Intervall muss „monat“ oder „jahr“ sein.")
    seit = _datum_oder_nichts(seit)
    fid = neue_id("fk_")
    kern.db.ausfuehren("INSERT INTO fixkosten (id, bezeichnung, betrag_cent, intervall, seit, erstellt, aktiv) "
                       "VALUES (?,?,?,?,?,?,1)", (fid, name, cent, intervall, seit, jetzt()))
    kern.protokoll.audit("ueberleben", "Feste Kosten eingetragen", {"id": fid, "betrag_cent": cent,
                                                                    "intervall": intervall})
    return fid


def fixkosten_entfernen(kern, fid, akteur):
    """Blendet einen Eintrag aus (aktiv=0). Gelöscht wird nichts – es bleibt nachvollziehbar."""
    _nur_eigentuemer(akteur)
    if not kern.db.ausfuehren("UPDATE fixkosten SET aktiv=0 WHERE id=? AND aktiv=1", (fid,)):
        raise KeyError("Fixkosten-Eintrag nicht gefunden oder schon entfernt.")
    kern.protokoll.audit("ueberleben", "Feste Kosten entfernt", {"id": fid})


def _monatlich_cent(zeilen):
    """Summe je Monat, Jahresbeträge mit 1/12 – erst am Ende auf Cent gerundet (kaufmännisch)."""
    zwoelftel = sum(z["betrag_cent"] * (12 if z["intervall"] == "monat" else 1) for z in zeilen)
    return (zwoelftel + 6) // 12


def _aktive_fixkosten(kern, tag):
    return kern.db.alle("SELECT * FROM fixkosten WHERE aktiv=1 AND (seit IS NULL OR seit <= ?) "
                        "ORDER BY erstellt, rowid", (tag.isoformat(),))


def fixkosten_monat_cent(kern, tag=None):
    """Feste Kosten je Monat in Cent – oder None, wenn keine erfasst sind (dann ist es UNBEKANNT, nicht 0)."""
    zeilen = _aktive_fixkosten(kern, tag or heute())
    return _monatlich_cent(zeilen) if zeilen else None


def fixkosten_liste(kern, tag=None):
    tag = tag or heute()
    ergebnis = []
    for z in kern.db.alle("SELECT * FROM fixkosten WHERE aktiv=1 ORDER BY erstellt, rowid"):
        z = dict(z)
        z["betrag"] = euro(z["betrag_cent"])
        z["intervall_name"] = INTERVALLE[z["intervall"]]
        z["monatlich_cent"] = _monatlich_cent([z])
        z["monatlich"] = euro(z["monatlich_cent"])
        z["zaehlt_schon"] = not z["seit"] or z["seit"] <= tag.isoformat()
        ergebnis.append(z)
    return ergebnis


# ---------------------------------------------------------------- Überlebensdruck
def druck_bestimmen(einnahmen_30_cent, saldo_cent, kosten_monat_cent):
    """ROT / GELB / GRÜN nach einer festen, nachvollziehbaren Regel.

    - Keine festen Kosten erfasst → GELB („Kosten nicht erfasst“) – ohne Kosten kein Urteil.
    - ROT, wenn in den letzten 30 Tagen keine geprüfte Einnahme erfasst ist (bei erfassten Kosten)
      oder wenn der Saldo (falls bekannt) kleiner ist als die festen Kosten eines Monats.
    - GRÜN, wenn die geprüften Einnahmen der letzten 30 Tage die festen Kosten eines Monats decken.
    - Sonst GELB.
    saldo_cent=None heißt: unbekannt (keine echte Buchung erfasst)."""
    if not kosten_monat_cent:
        text = ("Kosten nicht erfasst: Ohne eure festen Kosten (z. B. Claude-Abo, Versicherung, Miete) lässt sich "
                "nicht sagen, ob das Geld reicht. Bitte unter „Feste Kosten“ eintragen.")
        if not einnahmen_30_cent:
            text += " In den letzten 30 Tagen ist keine geprüfte Einnahme erfasst."
        return {"druck": "GELB", "regel": "kosten_fehlen", "begruendung": text}
    kosten = euro(kosten_monat_cent)
    rot = []
    if not einnahmen_30_cent:
        rot.append(("keine_einnahme", "In den letzten 30 Tagen ist keine geprüfte Einnahme erfasst, aber es laufen "
                                      "feste Kosten von %s pro Monat." % kosten))
    if saldo_cent is not None and saldo_cent < kosten_monat_cent:
        rot.append(("saldo_unter_kosten", "Der Saldo der erfassten Buchungen (%s) ist kleiner als die festen Kosten "
                                          "eines Monats (%s)." % (euro(saldo_cent), kosten)))
    if rot:
        return {"druck": "ROT", "regel": rot[0][0], "begruendung": " ".join(t for _, t in rot)}
    if einnahmen_30_cent >= kosten_monat_cent:
        return {"druck": "GRÜN", "regel": "einnahmen_decken_kosten",
                "begruendung": "Die geprüften Einnahmen der letzten 30 Tage (%s) decken die festen Kosten eines "
                               "Monats (%s)." % (euro(einnahmen_30_cent), kosten)}
    return {"druck": "GELB", "regel": "einnahmen_reichen_nicht",
            "begruendung": "Es gab geprüfte Einnahmen (%s in den letzten 30 Tagen), sie decken die festen Kosten "
                           "eines Monats (%s) aber noch nicht." % (euro(einnahmen_30_cent), kosten)}


# ---------------------------------------------------------------- Lage aus echten Zahlen
def _summe(kern, art, von, bis):
    """Summe einer Buchungsart im Zeitraum. Gegengebuchte (korrigierte) Buchungen zählen nicht."""
    return int(kern.db.wert(
        "SELECT COALESCE(SUM(b.betrag_cent),0) FROM real_buchungen b WHERE b.art=? AND b.datum >= ? AND b.datum <= ? "
        "AND NOT EXISTS (SELECT 1 FROM real_buchungen g WHERE g.gegenbuchung_zu = b.id)", (art, von, bis)) or 0)


def _dezimal(zahl):
    return ("%.1f" % zahl).replace(".", ",")


def lage(kern, tag=None):
    """Die Überlebenslage – nur aus echten, geprüften Daten. Unbekanntes bleibt unbekannt (None)."""
    tag = tag or heute()
    t = tag.isoformat()
    von_30 = (tag - datetime.timedelta(days=29)).isoformat()   # die letzten 30 Tage, heute mitgezählt
    einnahmen_monat = _summe(kern, "einnahme", tag.replace(day=1).isoformat(), t)
    einnahmen_30 = _summe(kern, "einnahme", von_30, t)
    ausgaben_30 = -_summe(kern, "ausgabe", von_30, t)
    saldo = None
    if kern.db.wert("SELECT COUNT(*) FROM real_buchungen"):
        saldo = int(kern.db.wert("SELECT COALESCE(SUM(betrag_cent),0) FROM real_buchungen"))
    forderungen = kern.db.eins("SELECT COALESCE(SUM(betrag_cent),0) AS summe, COUNT(*) AS anzahl FROM forderungen "
                               "WHERE status='offen'")
    kosten = fixkosten_monat_cent(kern, tag)
    druck = druck_bestimmen(einnahmen_30, saldo, kosten)
    reichweite = None
    if saldo is not None and kosten:
        reichweite = 0.0 if saldo <= 0 else (saldo * 10 // kosten) / 10   # abgerundet – lieber vorsichtig
    if reichweite is not None:
        reichweite_text = "%s Monate (Saldo geteilt durch die festen Kosten eines Monats)" % _dezimal(reichweite)
    elif not kosten:
        reichweite_text = "unbekannt – feste Kosten nicht erfasst"
    else:
        reichweite_text = "unbekannt – noch keine echte Buchung erfasst (kein Saldo)"
    return {
        "datum": t,
        "stand": jetzt(),
        "druck": druck["druck"],
        "regel": druck["regel"],
        "begruendung": druck["begruendung"],
        "einnahmen_monat_cent": einnahmen_monat,
        "einnahmen_monat": euro(einnahmen_monat),
        "einnahmen_30_tage_cent": einnahmen_30,
        "einnahmen_30_tage": euro(einnahmen_30),
        "ausgaben_30_tage_cent": ausgaben_30,
        "ausgaben_30_tage": euro(ausgaben_30),
        "saldo_cent": saldo,
        "saldo": euro(saldo) if saldo is not None else "unbekannt (noch keine echte Buchung erfasst)",
        "offene_forderungen_cent": int(forderungen["summe"]),
        "offene_forderungen_anzahl": forderungen["anzahl"],
        "offene_forderungen": ("%s (erwartet, nicht sicher)" % euro(forderungen["summe"]) if forderungen["anzahl"]
                               else "0,00 € (keine offene Forderung)"),
        "fixkosten_monat_cent": kosten,
        "fixkosten_monat": euro(kosten) if kosten else "nicht erfasst",
        "kosten_erfasst": bool(kosten),
        "reichweite_monate": reichweite,
        "reichweite": reichweite_text,
        "hinweis": ("Nur echte, geprüfte Zahlen aus den realen Finanzen. Das Simulations-Wallet zählt nie als Geld. "
                    "Offene Forderungen sind erwartet, aber nicht sicher. Saldo = Summe der in AUTONOMOUS erfassten "
                    "echten Buchungen (kein Kontostand der Bank)."),
    }


# ---------------------------------------------------------------- Geldchancen
def _json_oder_leer(text, standard):
    try:
        wert = json.loads(text or "null")
    except (TypeError, ValueError):
        return standard
    return wert if isinstance(wert, type(standard)) else standard


def _chance(art, bezug_id, was, warum, naechster_schritt, frist=KEINE_FRIST, frist_datum=None, wert="unbekannt",
            wert_cent=None, **extra):
    c = {"art": art, "art_name": ARTEN[art], "was": was, "warum": warum, "naechster_schritt": naechster_schritt,
         "frist": frist, "frist_datum": frist_datum, "wert": wert, "wert_cent": wert_cent, "bezug_id": bezug_id,
         "link": None}
    c.update(extra)
    return c


def _tage_seit(zeitstempel, tag):
    try:
        return (tag - datetime.date.fromisoformat(str(zeitstempel)[:10])).days
    except ValueError:
        return None


def _angebot_wert(zeile, inhalt):
    cent = int(zeile.get("betrag_cent") or 0)
    if cent <= 0:
        return "unbekannt", None
    if inhalt.get("art") == "reinigung_dauerauftrag":
        return "%s pro Monat (netto)" % euro(cent), cent
    return euro(cent), cent


def _mahnung_entwurf(f):
    rechnung = f.get("rechnung_ref") or "[Rechnungsnummer]"
    return ("ENTWURF – Zahlungserinnerung (nicht versendet – bitte prüfen, ergänzen und selbst senden)\n\n"
            "%s\n[Anschrift des Kunden]\n\n"
            "Betreff: Zahlungserinnerung zur Rechnung %s\n\n"
            "Sehr geehrte Damen und Herren,\n\n"
            "zu unserer Rechnung %s über %s, fällig am %s, konnten wir bisher keinen Zahlungseingang feststellen. "
            "Bitte überweisen Sie den Betrag bis zum [Datum – vom Inhaber festlegen] auf das Konto "
            "[Bankverbindung – vom Inhaber ergänzen]. Sollte sich Ihre Zahlung mit diesem Schreiben überschnitten "
            "haben, betrachten Sie es bitte als gegenstandslos.\n\n"
            "Mit freundlichen Grüßen\n[Name, Firma und Anschrift des Absenders – vom Inhaber ergänzen]"
            % (f["kunde"], rechnung, rechnung, euro(f["betrag_cent"]), datum_deutsch(f["faellig"])))


def _mahnungen(kern, tag):
    chancen = []
    for f in kern.db.alle("SELECT * FROM forderungen WHERE status='offen' AND faellig IS NOT NULL AND faellig < ? "
                          "ORDER BY faellig, betrag_cent DESC, rowid", (tag.isoformat(),)):
        tage = _tage_seit(f["faellig"], tag)
        chancen.append(_chance(
            "mahnung", f["id"], "Zahlung anmahnen: %s" % f["kunde"],
            "Die Forderung über %s ist seit %d Tag(en) überfällig (fällig am %s). Echtes Geld ist es erst mit dem "
            "Zahlungseingang." % (euro(f["betrag_cent"]), tage, datum_deutsch(f["faellig"])),
            "Zahlungserinnerung prüfen, ergänzen und selbst senden – der Entwurf wird nicht automatisch verschickt. "
            "Nach dem Zahlungseingang die Forderung mit Nachweis als bezahlt buchen.",
            "überfällig seit %s" % datum_deutsch(f["faellig"]), f["faellig"], euro(f["betrag_cent"]),
            f["betrag_cent"], entwurf=_mahnung_entwurf(f)))
    return chancen


def _hat_forderung(angebot, nr, forderungen):
    """Gibt es zu einem angenommenen Angebot schon eine Forderung? Regel (nachvollziehbar, ohne Raten):
    Angebots-ID oder -Nummer steht in Rechnungsnummer oder Notiz – oder eine Forderung an denselben Kunden
    (Firmenname gleich) wurde am Tag der Annahme oder danach angelegt. Auch eine stornierte zählt (bewusst erledigt)."""
    firma = (angebot.get("firma") or "").strip().casefold()
    angenommen = str(angebot.get("aktualisiert") or "")[:10]
    for f in forderungen:
        text = "%s %s" % (f.get("rechnung_ref") or "", f.get("notiz") or "")
        if angebot["id"] in text or (nr and nr in text):
            return True
        if firma and (f.get("kunde") or "").strip().casefold() == firma and str(f.get("erstellt"))[:10] >= angenommen:
            return True
    return False


def _rechnungen(kern, tag):
    forderungen = kern.db.alle("SELECT id, kunde, rechnung_ref, notiz, erstellt FROM forderungen")
    chancen = []
    for a in kern.db.alle("SELECT a.*, k.firma FROM angebote a LEFT JOIN kontakte k ON k.id = a.kontakt_id "
                          "WHERE a.status='angenommen' ORDER BY a.aktualisiert, a.rowid"):
        inhalt = _json_oder_leer(a["inhalt"], {})
        nr = inhalt.get("nr") if isinstance(inhalt.get("nr"), str) else None
        if _hat_forderung(a, nr, forderungen):
            continue
        wert, cent = _angebot_wert(a, inhalt)
        chancen.append(_chance(
            "rechnung", a["id"], "Rechnung schreiben: %s" % (a["firma"] or a["titel"]),
            "Angebot %s („%s“) ist angenommen, aber es gibt noch keine Forderung dazu. Ohne Rechnung kommt kein "
            "Geld." % (nr or a["id"], a["titel"]),
            "Rechnung schreiben und unter Finanzen als Forderung anlegen (Angebotsnummer %s bei Rechnungsnummer "
            "oder Notiz angeben, dann erkennt AUTONOMOUS sie)." % (nr or a["id"]),
            "%s – so bald wie möglich" % KEINE_FRIST, None, wert, cent, kontakt_id=a["kontakt_id"]))
    return chancen


def _nachfassen(kern, tag):
    chancen = []
    for a in kern.db.alle("SELECT a.*, k.firma FROM angebote a LEFT JOIN kontakte k ON k.id = a.kontakt_id "
                          "WHERE a.status='versendet' ORDER BY a.aktualisiert, a.rowid"):
        tage = _tage_seit(a["aktualisiert"], tag)
        if tage is None or tage <= NACHFASSEN_NACH_TAGEN:
            continue
        inhalt = _json_oder_leer(a["inhalt"], {})
        wert, cent = _angebot_wert(a, inhalt)
        if a["kontakt_id"]:
            schritt = ("Freundlich nachfragen: Den Nachfass-Entwurf schreibt der Sales-Agent – prüfen und selbst "
                       "senden oder anrufen. Gesendet wird nichts automatisch.")
        else:
            schritt = "Dem Angebot einen Kontakt zuordnen oder selbst beim Kunden nachfragen."
        gueltig = inhalt.get("gueltig_bis") if isinstance(inhalt.get("gueltig_bis"), str) else ""
        chancen.append(_chance(
            "nachfassen", a["id"], "Nachfassen: %s (%s)" % (a["titel"], a["firma"] or "ohne Kontakt"),
            "Seit %d Tagen versendet, noch keine Entscheidung erfasst." % tage, schritt,
            ("Angebot gültig bis %s" % gueltig) if gueltig.strip() else KEINE_FRIST, None, wert, cent,
            kontakt_id=a["kontakt_id"], firma=a["firma"], angebot_titel=a["titel"]))
    return chancen


def _interessenten(kern, tag):
    chancen = []
    for k in kern.db.alle("SELECT * FROM kontakte k WHERE status='interessiert' AND NOT EXISTS (SELECT 1 FROM "
                          "angebote a WHERE a.kontakt_id = k.id AND a.status IN ('entwurf','geprueft','versendet',"
                          "'angenommen')) ORDER BY aktualisiert, rowid"):
        schritt = ("Bedarf klären, Preis festlegen (das macht nur ihr) und dann unter Vertrieb ein Angebot entwerfen "
                   "lassen.")
        if (k.get("naechster_schritt") or "").strip():
            schritt += " Notiert: %s" % k["naechster_schritt"].strip()
        chancen.append(_chance("interessent", k["id"], "Angebot machen: %s" % k["firma"],
                               "Als „interessiert“ markiert, aber es gibt noch kein laufendes Angebot.", schritt,
                               kontakt_id=k["id"]))
    return chancen


def _region_passt(zeile, plz_bereich):
    """True/False, wenn sich die Region aus PLZ oder Bewertung ergibt – sonst None (in den Unterlagen prüfen)."""
    plz = (zeile.get("plz") or "").strip()
    if plz:
        return plz[:2] in plz_bereich
    gruende = _json_oder_leer(zeile.get("begruendung"), [])
    if any(isinstance(g, str) and "außerhalb" in g and g.lstrip().startswith(("−", "-")) for g in gruende):
        return False
    return None


def ausschreibungs_kandidaten(kern, tag):
    """Offene Ausschreibungen mit genug Vorlauf, beste zuerst (Punkte, dann Frist).

    Was ihr selbst markiert habt (interessant, vorbereitet), zählt immer. Neue Funde nur, wenn sie passen
    (mindestens PASSEND_AB Punkte) und nicht außerhalb der Region aus den Einstellungen liegen.
    Doppelte aus mehreren Quellen zählen einmal (Haupteintrag)."""
    plz_bereich = set(kern.einstellungen.hole("region_plz") or [])
    zeilen = kern.db.alle("SELECT * FROM ausschreibungen WHERE frist IS NOT NULL AND substr(frist,1,10) >= ?",
                          (tag.isoformat(),))
    grenze = (tag + datetime.timedelta(days=FRIST_MINDESTENS_TAGE)).isoformat()
    kandidaten = []
    for z in dubletten.anreichern(zeilen):
        if z["vermutlich_gleich_wie"] or z["status"] not in OFFENE_STUFEN or str(z["frist"])[:10] < grenze:
            continue
        if z["status"] == "neu" and ((z["punkte"] or 0) < PASSEND_AB or _region_passt(z, plz_bereich) is False):
            continue
        kandidaten.append(z)
    kandidaten.sort(key=lambda z: (-(z["punkte"] or 0), str(z["frist"]), z["id"]))
    return kandidaten


def _ausschreibungen(kern, tag):
    chancen = []
    for z in ausschreibungs_kandidaten(kern, tag):
        gruende = [g for g in _json_oder_leer(z.get("begruendung"), []) if isinstance(g, str)]
        tage = tage_bis(z["frist"], tag)
        mappe = mappe_vorhanden(z.get("unterlagen"))
        if mappe:
            schritt = ("Bewerbungs-Mappe liegt bereit: Vergabeunterlagen auf der Plattform holen, Preis kalkulieren "
                       "und das Angebot selbst abgeben – AUTONOMOUS gibt nichts ab.")
        elif z["status"] == "vorbereitet":
            schritt = ("Als vorbereitet markiert, aber keine Mappe gefunden – im Auftrags-Radar die Mappe neu "
                       "erstellen lassen, dann selbst abgeben.")
        else:
            schritt = ("Bewerbungs-Mappe vorbereiten lassen (macht der Akquise-Agent), dann die Unterlagen prüfen und "
                       "entscheiden, ob ihr anbietet.")
        link = z.get("link") if str(z.get("link") or "").startswith("https://") else None
        chancen.append(_chance(
            "ausschreibung", z["id"],
            "%s%s" % (z["titel"][:160], (" – %s" % z["vergabestelle"][:80]) if z.get("vergabestelle") else ""),
            "%d Punkte nach festen Regeln: %s" % (z["punkte"] or 0, "; ".join(gruende[:3]) or "ohne Begründung"),
            schritt, "%s (noch %d Tage)" % (datum_deutsch(z["frist"]), tage), str(z["frist"])[:10],
            link=link, punkte=z["punkte"], status=z["status"], titel=z["titel"],
            quelle_name=QUELLEN_NAMEN.get(z["quelle"], z["quelle"]),
            wert_hinweis="der Auftragswert steht nicht in den Daten und wird nicht geschätzt",
            unterlagen_url=("/produkte/" + z["unterlagen"]) if mappe else None))
    return chancen


def geldchancen(kern, tag=None):
    """Alle Geldchancen, je näher am Geld desto weiter oben:
    überfällige Forderungen → angenommene Angebote ohne Rechnung → Nachfassen → Interessenten → Ausschreibungen."""
    tag = tag or heute()
    return (_mahnungen(kern, tag) + _rechnungen(kern, tag) + _nachfassen(kern, tag) + _interessenten(kern, tag)
            + _ausschreibungen(kern, tag))


# ---------------------------------------------------------------- Folgeaufgaben (nur intern)
def _folge_schluessel(typ, eingabe):
    """Was als „dieselbe Folgeaufgabe“ gilt: gleicher Typ für dieselbe Ausschreibung bzw. denselben Kontakt."""
    if typ == "ausschreibung_vorbereiten":
        return "%s:%s" % (typ, eingabe.get("ausschreibung_id"))
    if typ == "nachricht_entwurf":
        return "%s:%s" % (typ, eingabe.get("kontakt_id"))
    return typ


def _bestand(con, aufgabe_id, tag):
    """Liest in EINER Transaktion, was es schon gibt – damit auch zwei gleichzeitige Pläne nichts doppelt anlegen."""
    t = tag.isoformat()
    ab = (tag - datetime.timedelta(days=NACHFASSEN_ABSTAND_TAGE - 1)).isoformat()
    b = {"bekannt": set(), "mappen_heute": set(), "nachfassen_heute": set(), "nachricht_kuerzlich": set(),
         "frueherer_plan_laeuft": False, "suche_offen": False, "suche_kuerzlich": False}

    def merken(schluessel, typ, datum, eigen):
        b["bekannt"].add(schluessel)
        if eigen and datum == t and typ == "ausschreibung_vorbereiten":
            b["mappen_heute"].add(schluessel)
        if eigen and datum == t and typ == "nachricht_entwurf":
            b["nachfassen_heute"].add(schluessel)
        if typ == "nachricht_entwurf" and datum >= ab:
            b["nachricht_kuerzlich"].add(schluessel)

    platz = ",".join("?" * len(FOLGE_TYPEN))
    offen = ",".join("?" * len(OFFENE_AUFGABEN))
    for z in con.execute("SELECT typ, ersteller, status, erstellt, eingabe FROM aufgaben WHERE typ IN (%s) AND "
                         "(substr(erstellt,1,10) >= ? OR status IN (%s))" % (platz, offen),
                         FOLGE_TYPEN + (ab,) + OFFENE_AUFGABEN).fetchall():
        datum = str(z["erstellt"])[:10]
        schluessel = _folge_schluessel(z["typ"], _json_oder_leer(z["eingabe"], {}))
        if datum == t or z["status"] in OFFENE_AUFGABEN or z["typ"] == "nachricht_entwurf":
            merken(schluessel, z["typ"], datum, z["ersteller"] == ROLLE)
        if z["typ"] == "ausschreibungen_suchen" and z["status"] in OFFENE_AUFGABEN:
            b["suche_offen"] = True
    # Pläne von heute, die schon fertig sind: ihre Folgeaufgaben legt der Orchestrator gerade erst an (Lücke)
    for z in con.execute("SELECT ergebnis FROM aufgaben WHERE typ='ueberlebensplan' AND status='abgeschlossen' AND "
                         "id != ? AND (substr(beendet,1,10) = ? OR substr(erstellt,1,10) = ?)",
                         (aufgabe_id, t, t)).fetchall():
        for f in _json_oder_leer(z["ergebnis"], {}).get("folgeaufgaben_geplant") or []:
            if isinstance(f, dict) and isinstance(f.get("schluessel"), str):
                merken(f["schluessel"], f.get("typ"), t, True)
    # Läuft gerade ein anderer Plan, der früher gestartet wurde? Dann legt ER die Folgeaufgaben an.
    starts = {z["id"]: z["start"] for z in con.execute(
        "SELECT a.id, (SELECT MAX(v.id) FROM aufgaben_verlauf v WHERE v.aufgabe_id = a.id AND "
        "v.nach_status = 'laufend') AS start FROM aufgaben a WHERE a.typ='ueberlebensplan' AND "
        "a.status='laufend'").fetchall()}
    mein_start = starts.pop(aufgabe_id, None)
    b["frueherer_plan_laeuft"] = any(mein_start is None or (s or 0) < mein_start for s in starts.values())
    grenze = (datetime.datetime.now().astimezone() - datetime.timedelta(hours=SUCHE_ABSTAND_STUNDEN)).isoformat(
        timespec="seconds")
    b["suche_kuerzlich"] = bool(
        con.execute("SELECT 1 FROM aufgaben WHERE typ='ausschreibungen_suchen' AND erstellt >= ?", (grenze,)).fetchone()
        or con.execute("SELECT 1 FROM suchlaeufe WHERE zeit >= ?", (grenze,)).fetchone())
    return b


def folgeaufgaben_planen(kern, druck, chancen, aufgabe_id, tag=None):
    """Plant die internen Folgeaufgaben des Tages. Gibt (folgeaufgaben, uebersprungen) zurück.

    Erlaubt sind nur interne Schritte anderer Agenten: Suche (Akquise, nur lesen, nur wenn eingeschaltet),
    Bewerbungs-Mappe (Akquise) und Nachfass-ENTWURF (Sales). Nichts davon sendet, bezahlt oder gibt ab.
    Je Tag höchstens einmal dieselbe Folgeaufgabe; Mappen je Tag höchstens MAPPEN_JE_TAG[druck]."""
    tag = tag or heute()
    prio = PRIORITAET[druck]
    recherche = bool(kern.einstellungen.hole("internet_recherche_erlaubt"))
    with kern.db.transaktion() as con:
        b = _bestand(con, aufgabe_id, tag)
    if b["frueherer_plan_laeuft"]:
        return [], [{"was": "Folgeaufgaben", "grund": "Ein anderer Überlebensplan läuft gerade – er legt die "
                                                      "Folgeaufgaben an. So entsteht nichts doppelt."}]
    folgen, uebersprungen = [], []

    def folge(titel, typ, verantwortlich, eingabe, schluessel, bezug_id=None):
        folgen.append({"titel": titel[:200], "typ": typ, "verantwortlich": verantwortlich, "eingabe": eingabe,
                       "prioritaet": prio, "schluessel": schluessel, "bezug_id": bezug_id})
        b["bekannt"].add(schluessel)

    # 1. Neue Ausschreibungen suchen (macht der Akquise-Agent – nur lesen, nur freigegebene Quellen)
    was = "Suche nach neuen Ausschreibungen"
    if not recherche:
        uebersprungen.append({"was": was, "grund": "Internet-Recherche ist ausgeschaltet – erst wenn ihr sie in den "
                                                   "Einstellungen einschaltet, sucht der Akquise-Agent (nur lesen)."})
    elif b["suche_offen"]:
        uebersprungen.append({"was": was, "grund": "Eine Suche ist schon angestoßen und noch nicht fertig."})
    elif "ausschreibungen_suchen" in b["bekannt"]:
        uebersprungen.append({"was": was, "grund": "Heute wurde schon eine Suche angestoßen."})
    elif b["suche_kuerzlich"]:
        uebersprungen.append({"was": was, "grund": "Letzte Suche vor weniger als %d Stunden – noch nicht wieder "
                                                   "nötig." % SUCHE_ABSTAND_STUNDEN})
    else:
        folge("Ausschreibungen suchen (Überlebensplan)", "ausschreibungen_suchen", "akquise", {},
              "ausschreibungen_suchen")

    # 2. Bewerbungs-Mappen für die besten noch nicht vorbereiteten Ausschreibungen
    grenze = MAPPEN_JE_TAG[druck]
    rest = max(0, grenze - len(b["mappen_heute"]))
    schon, wartend = 0, 0
    for c in chancen:
        if c["art"] != "ausschreibung" or c.get("status") not in ("neu", "interessant") or c.get("unterlagen_url"):
            continue
        schluessel = _folge_schluessel("ausschreibung_vorbereiten", {"ausschreibung_id": c["bezug_id"]})
        if schluessel in b["bekannt"]:
            schon += 1
        elif rest <= 0:
            wartend += 1
        else:
            folge("Bewerbungs-Mappe: %s" % (c.get("titel") or c["was"])[:120], "ausschreibung_vorbereiten",
                  "akquise", {"ausschreibung_id": c["bezug_id"]}, schluessel, c["bezug_id"])
            rest -= 1
    if schon:
        uebersprungen.append({"was": "Bewerbungs-Mappen", "grund": "%d Ausschreibung(en): Mappe heute schon "
                                                                   "angestoßen oder in Arbeit." % schon})
    if wartend:
        uebersprungen.append({"was": "Bewerbungs-Mappen", "grund": "Tagesgrenze erreicht (%s: höchstens %d Mappe(n) "
                                                                   "je Tag) – %d weitere passende Ausschreibung(en) "
                                                                   "warten auf den nächsten Plan."
                                                                   % (druck, grenze, wartend)})

    # 3. Nachfassen: Entwurf durch den Sales-Agenten – gesendet wird nichts
    rest = max(0, NACHFASSEN_JE_TAG - len(b["nachfassen_heute"]))
    for c in chancen:
        if c["art"] != "nachfassen":
            continue
        was = "Nachfass-Entwurf: %s" % (c.get("firma") or c["was"])
        if not c.get("kontakt_id"):
            uebersprungen.append({"was": was, "grund": "Zum Angebot ist kein Kontakt hinterlegt – bitte selbst "
                                                       "nachfragen oder einen Kontakt zuordnen."})
            continue
        schluessel = _folge_schluessel("nachricht_entwurf", {"kontakt_id": c["kontakt_id"]})
        if schluessel in b["bekannt"] or schluessel in b["nachricht_kuerzlich"]:
            uebersprungen.append({"was": was, "grund": "Für diesen Kontakt gibt es schon einen Entwurf aus den "
                                                       "letzten %d Tagen." % NACHFASSEN_ABSTAND_TAGE})
        elif rest <= 0:
            uebersprungen.append({"was": was, "grund": "Heute schon %d Nachfass-Entwürfe – der Rest folgt im "
                                                       "nächsten Plan." % NACHFASSEN_JE_TAG})
        else:
            folge("Nachfassen: %s" % (c.get("firma") or c["was"]), "nachricht_entwurf", "sales",
                  {"kontakt_id": c["kontakt_id"],
                   "anlass": "Nachfassen zum Angebot „%s“" % (c.get("angebot_titel") or "")[:150]},
                  schluessel, c["bezug_id"])
            rest -= 1
    return folgen, uebersprungen


def angestossen_vermerken(chancen, folgen):
    """Vermerkt bei jeder Geldchance, was der Plan heute dafür angestoßen hat (nur zur Anzeige)."""
    je_bezug = {f["bezug_id"]: f for f in folgen if f.get("bezug_id")}
    for c in chancen:
        f = je_bezug.get(c["bezug_id"])
        if f:
            c["angestossen"] = "Heute angestoßen: %s (%s)" % (f["titel"], AGENT_NAMEN.get(f["verantwortlich"],
                                                                                         f["verantwortlich"]))
    return chancen


# ---------------------------------------------------------------- Plan als Text und als druckbare Seite
def plan_text(plan):
    lage_ = plan["lage"]
    zeilen = ["Überlebensdruck: %s – %s" % (plan["druck"], plan["begruendung"]),
              "Geprüfte Einnahmen (30 Tage): %s · Feste Kosten je Monat: %s · Saldo: %s · Reichweite: %s"
              % (lage_["einnahmen_30_tage"], lage_["fixkosten_monat"], lage_["saldo"], lage_["reichweite"]),
              "Offene Forderungen: %s" % lage_["offene_forderungen"], "", "Heute zuerst:"]
    for i, c in enumerate(plan["geldchancen"], 1):
        zeilen.append("%d. [%s] %s → %s (Frist: %s · Wert: %s)" % (i, c["art_name"], c["was"], c["naechster_schritt"],
                                                                  c["frist"], c["wert"]))
    if not plan["geldchancen"]:
        zeilen.append("Keine Geldchance in den Daten gefunden.")
    zeilen += ["", "Selbst angestoßen (nur intern): %d Folgeaufgabe(n)" % len(plan["folgeaufgaben_geplant"])]
    zeilen += ["- %s (%s)" % (f["titel"], AGENT_NAMEN.get(f["verantwortlich"], f["verantwortlich"]))
               for f in plan["folgeaufgaben_geplant"]]
    zeilen += ["", "Es wurde nichts gesendet, nichts bezahlt und kein Angebot abgegeben."]
    return "\n".join(zeilen)


def _e(wert):
    return html.escape(str(wert if wert is not None else ""), quote=True)


def _zeilen(text):
    return "<br>".join(_e(z) for z in str(text).split("\n"))


PLAN_CSS = (
    "*{box-sizing:border-box}html{-webkit-text-size-adjust:100%}"
    "body{margin:0;font-family:system-ui,-apple-system,'Segoe UI',Roboto,Arial,sans-serif;font-size:16px;"
    "line-height:1.55;color:#111827;background:#f3f4f6;overflow-wrap:break-word}"
    ".blatt{max-width:860px;margin:0 auto;background:#fff;padding:24px 18px 40px}"
    "h1{font-size:1.5rem;line-height:1.25;margin:.2em 0 .5em}h2{font-size:1.15rem;margin:1.8em 0 .6em;"
    "padding-bottom:.25em;border-bottom:2px solid #e5e7eb}h3{font-size:1.02rem;margin:.2em 0 .4em}"
    ".kopf{color:#4b5563;font-size:.9rem;margin:0}"
    ".ampel{border-radius:12px;padding:14px 16px;border:2px solid}.ampel p{margin:.4em 0 0}"
    ".ampel strong{font-size:1.15rem}"
    ".rot{background:#fef2f2;border-color:#dc2626;color:#7f1d1d}"
    ".gelb{background:#fffbeb;border-color:#d97706;color:#78350f}"
    ".gruen{background:#f0fdf4;border-color:#16a34a;color:#14532d}"
    ".hinweis{background:#eff6ff;border:1px solid #93c5fd;color:#1e3a8a;border-radius:10px;padding:10px 14px;"
    "font-weight:600}"
    "table{width:100%;border-collapse:collapse;table-layout:fixed}"
    "th,td{text-align:left;vertical-align:top;padding:8px 6px;border-bottom:1px solid #e5e7eb}"
    "th{width:44%;color:#374151;font-weight:600}td{overflow-wrap:anywhere}"
    "ol.chancen{padding-left:1.4em}ol.chancen>li{margin:0 0 16px;padding:10px 12px;border:1px solid #e5e7eb;"
    "border-radius:10px}"
    ".art{display:inline-block;font-size:.8rem;font-weight:700;text-transform:uppercase;letter-spacing:.04em;"
    "color:#0e7490}"
    "dl{margin:.3em 0 0}dt{font-weight:600;color:#374151;margin-top:.35em}dd{margin:0}"
    ".entwurf{white-space:pre-wrap;background:#fffbeb;border:2px dashed #d97706;border-radius:10px;padding:10px 12px;"
    "font-family:inherit;font-size:.92rem;margin:.6em 0 0}"
    "a{color:#0e7490;overflow-wrap:anywhere}.klein{font-size:.9rem;color:#4b5563}ul{padding-left:1.3em}"
    "li{margin:.3em 0}"
    "@media (max-width:520px){th,td{display:block;width:100%;padding:4px 0}th{border-bottom:none;padding-top:10px}}"
    "@media print{body{background:#fff}.blatt{padding:0}a{color:#000}ol.chancen>li{break-inside:avoid}}"
)
_AMPEL_KLASSE = {"ROT": "rot", "GELB": "gelb", "GRÜN": "gruen"}


def _chance_html(c):
    teile = ['<li><span class="art">%s</span><h3>%s</h3><dl>' % (_e(c["art_name"]), _e(c["was"])),
             "<dt>Warum</dt><dd>%s</dd>" % _e(c["warum"]),
             "<dt>Nächster Schritt</dt><dd>%s</dd>" % _e(c["naechster_schritt"]),
             ("<dt>Schon getan</dt><dd>%s</dd>" % _e(c["angestossen"])) if c.get("angestossen") else "",
             "<dt>Frist</dt><dd>%s</dd>" % _e(c["frist"]),
             "<dt>Wert</dt><dd>%s</dd>" % _e(c["wert"] + (" – " + c["wert_hinweis"] if c.get("wert_hinweis") else ""))]
    if c.get("link"):
        teile.append('<dt>Quelle</dt><dd><a href="%s" rel="noopener noreferrer">%s</a></dd>'
                     % (_e(c["link"]), _e(c.get("quelle_name") or "Ausschreibung ansehen")))
    teile.append("</dl>")
    if c.get("entwurf"):
        teile.append('<div class="entwurf">%s</div>' % _zeilen(c["entwurf"]))
    teile.append("</li>")
    return "".join(teile)


def plan_html(plan):
    """Druckbare Seite ohne JavaScript; jeder Inhalt ist escaped."""
    lage_ = plan["lage"]
    datum = datum_deutsch(plan["datum"])
    zeilen_lage = (
        ("Geprüfte Einnahmen in diesem Monat", lage_["einnahmen_monat"]),
        ("Geprüfte Einnahmen in den letzten 30 Tagen", lage_["einnahmen_30_tage"]),
        ("Ausgaben in den letzten 30 Tagen", lage_["ausgaben_30_tage"]),
        ("Saldo (Summe der erfassten echten Buchungen)", lage_["saldo"]),
        ("Feste Kosten je Monat", lage_["fixkosten_monat"]),
        ("Reichweite", lage_["reichweite"]),
        ("Offene Forderungen", lage_["offene_forderungen"]),
    )
    chancen = "".join(_chance_html(c) for c in plan["geldchancen"])
    if chancen:
        chancen = '<ol class="chancen">%s</ol>' % chancen
        if plan.get("geldchancen_gesamt", 0) > len(plan["geldchancen"]):
            chancen += '<p class="klein">%d weitere Geldchancen stehen in AUTONOMOUS unter „Überleben“.</p>' % (
                plan["geldchancen_gesamt"] - len(plan["geldchancen"]))
    else:
        chancen = ("<p>Keine Geldchance in den Daten gefunden. Das heißt nicht, dass es keine gibt – nur, dass "
                   "AUTONOMOUS noch keine kennt: Ausschreibungen suchen lassen, Kontakte und Angebote eintragen.</p>")
    folgen = "".join("<li>%s <span class=\"klein\">(%s)</span></li>"
                     % (_e(f["titel"]), _e(AGENT_NAMEN.get(f["verantwortlich"], f["verantwortlich"])))
                     for f in plan["folgeaufgaben_geplant"]) or "<li>Heute nichts Neues angestoßen.</li>"
    nicht = "".join("<li><strong>%s:</strong> %s</li>" % (_e(u["was"]), _e(u["grund"])) for u in plan["uebersprungen"])
    return (
        '<!doctype html><html lang="de"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        "<title>Überlebensplan %s</title><style>%s</style></head><body><main class=\"blatt\">"
        '<p class="kopf">AUTONOMOUS · Überlebens-Agent · erstellt %s</p>'
        "<h1>Überlebensplan für %s</h1>"
        '<div class="ampel %s"><strong>Überlebensdruck: %s</strong><p>%s</p></div>'
        '<p class="hinweis">Nur Vorbereitung: Es wurde nichts gesendet, nichts bezahlt und kein Angebot abgegeben. '
        "Das entscheidet ihr.</p>"
        "<h2>1. Lage aus echten Zahlen</h2><table>%s</table>"
        '<p class="klein">%s</p>'
        "<h2>2. Heute zuerst: die besten Geldchancen</h2>%s"
        "<h2>3. Was der Agent selbst angestoßen hat (nur intern)</h2><ul>%s</ul>%s"
        "<h2>4. Was nur ihr entscheidet</h2><ul>"
        "<li>Preise festlegen, Angebote abgeben und Verträge annehmen.</li>"
        "<li>Nachrichten, Nachfragen und Zahlungserinnerungen prüfen und selbst senden.</li>"
        "<li>Einnahmen erst buchen, wenn das Geld da ist – mit Zahlungsnachweis.</li>"
        "<li>Feste Kosten aktuell halten (Bereich „Überleben“ → Feste Kosten).</li></ul>"
        "</main></body></html>"
        % (_e(datum), PLAN_CSS, _e(datum_deutsch(lage_["stand"])), _e(datum), _AMPEL_KLASSE[plan["druck"]],
           _e(plan["druck"]), _e(plan["begruendung"]),
           "".join("<tr><th>%s</th><td>%s</td></tr>" % (_e(a), _e(b)) for a, b in zeilen_lage),
           _e(lage_["hinweis"]), chancen, folgen,
           ("<h3>Bewusst nicht angestoßen</h3><ul>%s</ul>" % nicht) if nicht else ""))


# ---------------------------------------------------------------- Anlegen, Zeitplan, letzter Plan
def plan_anlegen(kern, ersteller, prioritaet=2):
    """Legt einen Überlebensplan an. Ist schon einer offen, wird DIESER zurückgegeben. Ergebnis: (id, neu)."""
    titel = "Überlebensplan %s" % datum_deutsch(heute().isoformat())
    with kern.db.transaktion() as con:   # Prüfen und Anlegen in einem Schritt – auch bei zwei Klicks zugleich
        offen = con.execute("SELECT id FROM aufgaben WHERE typ='ueberlebensplan' AND status IN (%s) "
                            "ORDER BY erstellt, rowid LIMIT 1" % ",".join("?" * len(OFFENE_AUFGABEN)),
                            OFFENE_AUFGABEN).fetchone()
        if offen:
            return offen["id"], False
        return kern.aufgaben.anlegen(titel, "ueberlebensplan", ROLLE, ersteller, {}, prioritaet), True


def zeitplan_pruefen(kern):
    """Für den täglichen Zeitplan (z. B. stündlich aufrufen): legt höchstens EINMAL je Tag einen Überlebensplan an.

    Keiner, wenn heute schon einer angelegt wurde (egal von wem, egal mit welchem Ausgang) oder noch einer offen
    ist. Gibt die Aufgaben-ID zurück oder None."""
    if kern.register.hole(ROLLE) is None:
        return None
    t = heute().isoformat()
    with kern.db.transaktion() as con:
        if con.execute("SELECT 1 FROM aufgaben WHERE typ='ueberlebensplan' AND (substr(erstellt,1,10) = ? OR status "
                       "IN (%s))" % ",".join("?" * len(OFFENE_AUFGABEN)), (t,) + OFFENE_AUFGABEN).fetchone():
            return None
        aid = kern.aufgaben.anlegen("Überlebensplan %s" % datum_deutsch(t), "ueberlebensplan", ROLLE, "zeitplan",
                                    {}, 2)
    kern.protokoll.info("zeitplan", "Täglicher Überlebensplan angelegt", {"aufgabe": aid})
    return aid


def _datei_da(url):
    if not url or not str(url).startswith("/produkte/"):
        return False
    wurzel = os.path.realpath(konfig.unterordner("produkte"))
    pfad = os.path.realpath(os.path.join(wurzel, os.path.normpath(str(url)[len("/produkte/"):])))
    return pfad.startswith(wurzel + os.sep) and os.path.isfile(pfad)


def letzter_plan(kern):
    """Kurzfassung des letzten fertigen Überlebensplans (oder None)."""
    z = kern.db.eins("SELECT id, beendet, ergebnis FROM aufgaben WHERE typ='ueberlebensplan' AND "
                     "status='abgeschlossen' ORDER BY beendet DESC, erstellt DESC LIMIT 1")
    if not z:
        return None
    e = _json_oder_leer(z["ergebnis"], {})
    return {"aufgabe_id": z["id"], "beendet": z["beendet"], "datum": e.get("datum"), "druck": e.get("druck"),
            "begruendung": e.get("begruendung"),
            "plan_url": e.get("plan_url") if _datei_da(e.get("plan_url")) else None,
            "folgeaufgaben": len(e.get("folgeaufgaben_geplant") or []),
            "geldchancen_gesamt": e.get("geldchancen_gesamt")}


def plan_in_arbeit(kern):
    z = kern.db.eins("SELECT id FROM aufgaben WHERE typ='ueberlebensplan' AND status IN (%s) "
                     "ORDER BY erstellt, rowid LIMIT 1" % ",".join("?" * len(OFFENE_AUFGABEN)), OFFENE_AUFGABEN)
    return z["id"] if z else None


def fixkosten_uebersicht(kern):
    tag = heute()
    summe = fixkosten_monat_cent(kern, tag)
    entfernt = kern.db.alle("SELECT id, bezeichnung, betrag_cent, intervall, seit, erstellt FROM fixkosten "
                            "WHERE aktiv=0 ORDER BY erstellt DESC, rowid DESC LIMIT 50")
    for z in entfernt:
        z["betrag"] = euro(z["betrag_cent"])
    return {"fixkosten": fixkosten_liste(kern, tag), "summe_monat_cent": summe,
            "summe_monat": euro(summe) if summe else "nicht erfasst", "entfernt": entfernt,
            "hinweis": "Nur ihr tragt feste Kosten ein (z. B. „Claude-Abo, 22 €, monatlich“). Jahresbeträge zählen "
                       "mit einem Zwölftel je Monat. Nichts ist vorbelegt."}
