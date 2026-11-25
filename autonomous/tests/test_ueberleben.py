# -*- coding: utf-8 -*-
"""Überlebens-Agent: Lage aus echten Zahlen (ROT/GELB/GRÜN), Geldchancen, interne Folgeaufgaben, Zeitplan, API.

Regeln, die hier geprüft werden: nichts erfinden (Unbekanntes heißt „unbekannt“), das Simulations-Wallet zählt nie
als Geld, keine externe Aktion und keine Freigabe entsteht, Geldmangel schaltet nichts ab (PDF 6.3).
KEIN Netz in diesen Tests."""

import datetime
import json
import os
import re
import sqlite3
from unittest import mock

from autonomous import api
from autonomous import api_ueberleben  # noqa: F401  (Routen registrieren)
from autonomous import db as db_modul
from autonomous import ueberleben
from autonomous.berechtigungen import AUTO, risikoklasse
from autonomous.db import jetzt
from autonomous.tests.hilfe import KernTest

EIGENTUEMER = "eigentuemer"


class UeberlebenTest(KernTest):
    """Testdaten immer relativ zu heute – so stimmen Fristen, Fälligkeiten und 30-Tage-Fenster."""

    heute = None

    def setUp(self):
        super().setUp()
        self.heute = datetime.date.today()

    def tag(self, verschiebung):
        return (self.heute + datetime.timedelta(days=verschiebung)).isoformat()

    def einnahme(self, betrag, tage_zurueck=0):
        return self.kern.finanzen.einnahme(betrag, "auftrag", "Kunde GmbH", "Zahlung", EIGENTUEMER,
                                           "Kontoauszug 7", "Vater", datum=self.tag(-tage_zurueck))

    def ausgabe(self, betrag, tage_zurueck=0):
        return self.kern.finanzen.ausgabe(betrag, "material", "Baumarkt", "Kauf", EIGENTUEMER,
                                          datum=self.tag(-tage_zurueck))

    def fixkosten(self, bezeichnung="Claude-Abo", betrag="22", intervall="monat", seit=None):
        return ueberleben.fixkosten_anlegen(self.kern, bezeichnung, betrag, intervall, EIGENTUEMER, seit)

    def zeitpunkt(self, tage_zurueck):
        return (datetime.datetime.now().astimezone() - datetime.timedelta(days=tage_zurueck)).isoformat(
            timespec="seconds")

    def ausschreibung(self, titel, frist_tage, status="neu", punkte=80, quelle="evergabe_nrw", plz=None,
                      extern_id=None, begruendung=None, link=None, vergabestelle="Stadt Muster"):
        frist = self.tag(frist_tage) if frist_tage is not None else None
        aid = "as_%s" % (extern_id or re.sub(r"[^a-z0-9]", "", titel.lower())[:20] + str(frist_tage))
        z = jetzt()
        self.kern.db.ausfuehren(
            "INSERT INTO ausschreibungen (id, quelle, extern_id, titel, vergabestelle, plz, region, frist, verfahren,"
            " link, punkte, begruendung, status, gefunden, aktualisiert) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (aid, quelle, extern_id or aid, titel, vergabestelle, plz, "NRW", frist, "UVgO – Ausschreibung",
             link or "https://www.evergabe.nrw.de/VMPCenter/public/company/projectForwarding.do?pid=1", punkte,
             json.dumps(begruendung or ["+35 Leistung passt: „unterhaltsreinigung“ im Titel",
                                        "+25 Vergabemarktplatz NRW – Auftrag vermutlich in NRW"], ensure_ascii=False),
             status, z, z))
        return aid

    def kontakt(self, firma, status="neu"):
        kid = "k_" + re.sub(r"[^a-z0-9]", "", firma.lower())[:20]
        z = jetzt()
        self.kern.db.ausfuehren("INSERT INTO kontakte (id, firma, quelle, status, erstellt, aktualisiert) "
                                "VALUES (?,?,?,?,?,?)", (kid, firma, "Gespräch", status, z, z))
        return kid

    def angebot(self, kontakt_id, status, tage_seit, betrag_cent=29900, titel="Angebot: Google-Profil-Paket",
                art="einmalig", nr=None):
        aid = "an_%s%s%d" % (status[:4], (kontakt_id or "ohne")[-6:], tage_seit)
        nr = nr or "ANG-20261101-%s" % aid[-4:].upper()
        inhalt = {"art": art, "nr": nr, "titel": titel, "betrag_cent": betrag_cent, "kontakt_id": kontakt_id}
        z = self.zeitpunkt(tage_seit)
        self.kern.db.ausfuehren("INSERT INTO angebote (id, kontakt_id, titel, betrag_cent, status, inhalt, erstellt, "
                                "aktualisiert) VALUES (?,?,?,?,?,?,?,?)",
                                (aid, kontakt_id, titel, betrag_cent, status, json.dumps(inhalt), z, z))
        return aid

    def forderung(self, kunde, betrag, faellig_tage, rechnung_ref=None, notiz=None):
        return self.kern.finanzen.forderung_anlegen(kunde, betrag, EIGENTUEMER,
                                                    faellig=self.tag(faellig_tage) if faellig_tage is not None
                                                    else None, rechnung_ref=rechnung_ref, notiz=notiz)


# ---------------------------------------------------------------- Migration 5
class TestMigration(KernTest):
    def test_migration_4_auf_5_ohne_datenverlust(self):
        pfad = os.path.join(os.environ["AUTONOMOUS_DATEN"], "alt4.db")
        voll = db_modul.MIGRATIONEN
        try:
            db_modul.MIGRATIONEN = voll[:4]
            alt = db_modul.Datenbank(pfad)
            self.assertEqual(alt.schema_version(), 4)
            z = jetzt()
            alt.ausfuehren("INSERT INTO kontakte (id, firma, quelle, erstellt, aktualisiert) VALUES (?,?,?,?,?)",
                           ("k_alt", "Bestandskunde GmbH", "Altdaten", z, z))
            alt.ausfuehren("INSERT INTO real_buchungen (id, nr, zeit, datum, art, betrag_cent, kategorie, gegenpartei,"
                           " begruendung, akteur) VALUES ('r_alt', 1, ?, '2026-11-01', 'ausgabe', -2200, 'abo', "
                           "'Anbieter', 'Abo', 'eigentuemer')", (z,))
            alt.ausfuehren("INSERT INTO aufgaben (id, titel, typ, ersteller, verantwortlich, status, erstellt, "
                           "aktualisiert) VALUES ('a_alt', 'Plan', 'tagesplan', 'eigentuemer', 'ceo', 'geplant', ?, ?)",
                           (z, z))
            self.assertIsNone(alt.wert("SELECT name FROM sqlite_master WHERE name='fixkosten'"))
            alt.schliessen()
        finally:
            db_modul.MIGRATIONEN = voll
        neu = db_modul.Datenbank(pfad)
        try:
            self.assertGreaterEqual(neu.schema_version(), 5)
            self.assertEqual(neu.schema_version(), len(db_modul.MIGRATIONEN))
            self.assertEqual(neu.wert("SELECT firma FROM kontakte WHERE id='k_alt'"), "Bestandskunde GmbH")
            self.assertEqual(neu.wert("SELECT betrag_cent FROM real_buchungen WHERE id='r_alt'"), -2200)
            self.assertEqual(neu.wert("SELECT status FROM aufgaben WHERE id='a_alt'"), "geplant")
            self.assertEqual(neu.wert("SELECT COUNT(*) FROM fixkosten"), 0)  # nichts vorbelegt
            neu.ausfuehren("INSERT INTO fixkosten (id, bezeichnung, betrag_cent, intervall, seit, erstellt) "
                           "VALUES ('fk1', 'Claude-Abo', 2200, 'monat', NULL, ?)", (jetzt(),))
            self.assertEqual(neu.wert("SELECT aktiv FROM fixkosten WHERE id='fk1'"), 1)
            for werte in (("fk2", "Null", 0, "monat"), ("fk3", "Minus", -5, "jahr"), ("fk4", "Woche", 100, "woche"),
                          ("fk5", "  ", 100, "monat")):
                with self.assertRaises(sqlite3.IntegrityError, msg=werte[0]):
                    neu.ausfuehren("INSERT INTO fixkosten (id, bezeichnung, betrag_cent, intervall, erstellt) "
                                   "VALUES (?,?,?,?,?)", werte + (jetzt(),))
            self.assertTrue(neu.integritaet())
        finally:
            neu.schliessen()


# ---------------------------------------------------------------- Fixkosten
class TestFixkosten(UeberlebenTest):
    def test_keine_werte_vorbelegt(self):
        self.assertEqual(ueberleben.fixkosten_liste(self.kern), [])
        self.assertIsNone(ueberleben.fixkosten_monat_cent(self.kern))

    def test_nur_eigentuemer_traegt_ein_und_entfernt(self):
        with self.assertRaises(PermissionError):
            ueberleben.fixkosten_anlegen(self.kern, "Abo", "22", "monat", "ueberleben")
        fid = self.fixkosten()
        with self.assertRaises(PermissionError):
            ueberleben.fixkosten_entfernen(self.kern, fid, "ceo")
        self.assertEqual(ueberleben.fixkosten_monat_cent(self.kern), 2200)
        ueberleben.fixkosten_entfernen(self.kern, fid, EIGENTUEMER)
        self.assertIsNone(ueberleben.fixkosten_monat_cent(self.kern))
        # Entfernen heißt ausblenden, nicht löschen – nachvollziehbar
        self.assertEqual(self.kern.db.wert("SELECT aktiv FROM fixkosten WHERE id=?", (fid,)), 0)
        with self.assertRaises(KeyError):
            ueberleben.fixkosten_entfernen(self.kern, fid, EIGENTUEMER)
        with self.assertRaises(KeyError):
            ueberleben.fixkosten_entfernen(self.kern, "gibtsnicht", EIGENTUEMER)

    def test_ungueltige_eingaben(self):
        for bezeichnung, betrag, intervall, seit in (("Abo", "0", "monat", None), ("Abo", "-5", "monat", None),
                                                    ("Abo", "abc", "monat", None), ("Abo", "22", "woche", None),
                                                    ("", "22", "monat", None), ("   ", "22", "monat", None),
                                                    ("x" * 121, "22", "monat", None),
                                                    ("Abo", "22", "monat", "31.12.2026"),
                                                    ("Abo", "22", "monat", "2026-13-01")):
            with self.assertRaises(ValueError, msg=(bezeichnung[:10], betrag, intervall, seit)):
                ueberleben.fixkosten_anlegen(self.kern, bezeichnung, betrag, intervall, EIGENTUEMER, seit)
        self.assertEqual(self.kern.db.wert("SELECT COUNT(*) FROM fixkosten"), 0)

    def test_monatssumme_jahresbetraege_durch_12(self):
        self.fixkosten("Claude-Abo", "22", "monat")
        self.fixkosten("Versicherung", "120", "jahr")           # 10,00 € im Monat
        self.assertEqual(ueberleben.fixkosten_monat_cent(self.kern), 3200)
        self.fixkosten("Kammerbeitrag", "100", "jahr")           # 8,333… € → zusammen 40,333… € → 40,33 €
        self.assertEqual(ueberleben.fixkosten_monat_cent(self.kern), 4033)
        self.fixkosten("Ab nächstem Jahr", "500", "monat", seit=self.tag(40))  # beginnt erst später
        self.assertEqual(ueberleben.fixkosten_monat_cent(self.kern), 4033)
        self.fixkosten("Seit letztem Monat", "7,50", "monat", seit=self.tag(-40))  # 47,833… € → 47,83 €
        self.assertEqual(ueberleben.fixkosten_monat_cent(self.kern), 4783)

    def test_reihenfolge_wie_eingetragen_auch_in_derselben_sekunde(self):
        erster = self.fixkosten("Erster Eintrag", "10", "monat")
        zweiter = self.fixkosten("Zweiter Eintrag", "20", "monat")
        # gleiche Sekunde und IDs, die alphabetisch andersherum stehen – die Reihenfolge darf nicht wackeln
        self.kern.db.ausfuehren("UPDATE fixkosten SET erstellt='2026-11-23T10:00:00+01:00'")
        self.kern.db.ausfuehren("UPDATE fixkosten SET id='fk_zzz' WHERE id=?", (erster,))
        self.kern.db.ausfuehren("UPDATE fixkosten SET id='fk_aaa' WHERE id=?", (zweiter,))
        self.assertEqual([f["bezeichnung"] for f in ueberleben.fixkosten_liste(self.kern)],
                         ["Erster Eintrag", "Zweiter Eintrag"])

    def test_liste_bereinigt_und_ohne_steuerzeichen(self):
        fid = self.fixkosten("  Claude-Abo\x07 (Max)  ", "22,00", "monat")
        eintrag = [f for f in ueberleben.fixkosten_liste(self.kern) if f["id"] == fid][0]
        self.assertEqual(eintrag["bezeichnung"], "Claude-Abo (Max)")
        self.assertEqual(eintrag["betrag_cent"], 2200)
        self.assertEqual(eintrag["betrag"], "22,00 €")
        self.assertEqual(eintrag["monatlich_cent"], 2200)
        self.assertEqual(eintrag["intervall"], "monat")


# ---------------------------------------------------------------- Druck-Regel (reine Funktion, von Hand gerechnet)
class TestDruckRegel(UeberlebenTest):
    FAELLE = (
        # Einnahmen 30 Tage, Saldo (None = unbekannt), Fixkosten/Monat (None = nicht erfasst) → Druck, Regel
        (0, None, None, "GELB", "kosten_fehlen"),
        (50000, -10000, None, "GELB", "kosten_fehlen"),          # ohne Kosten weder ROT noch GRÜN
        (0, None, 2200, "ROT", "keine_einnahme"),
        (0, 1000000, 2200, "ROT", "keine_einnahme"),             # viel Saldo, aber 30 Tage nichts verdient
        (1000, 500, 2200, "ROT", "saldo_unter_kosten"),
        (5000, 2199, 2200, "ROT", "saldo_unter_kosten"),         # 1 Cent unter einem Monat
        (2200, 2200, 2200, "GRÜN", "einnahmen_decken_kosten"),   # genau gleich ist kein Mangel
        (2200, None, 2200, "GRÜN", "einnahmen_decken_kosten"),   # Saldo unbekannt verhindert GRÜN nicht
        (2199, 100000, 2200, "GELB", "einnahmen_reichen_nicht"),
        (1, None, 2200, "GELB", "einnahmen_reichen_nicht"),
    )

    def test_regel_exakt(self):
        for einnahmen, saldo, kosten, druck, regel in self.FAELLE:
            d = ueberleben.druck_bestimmen(einnahmen, saldo, kosten)
            self.assertEqual((d["druck"], d["regel"]), (druck, regel), (einnahmen, saldo, kosten))
            self.assertTrue(d["begruendung"].strip())

    def test_begruendung_nennt_die_echten_zahlen(self):
        self.assertIn("Kosten nicht erfasst", ueberleben.druck_bestimmen(0, None, None)["begruendung"])
        self.assertIn("22,00 €", ueberleben.druck_bestimmen(0, None, 2200)["begruendung"])
        rot = ueberleben.druck_bestimmen(1000, 500, 2200)["begruendung"]
        self.assertIn("5,00 €", rot)
        self.assertIn("22,00 €", rot)
        gruen = ueberleben.druck_bestimmen(50000, None, 2200)["begruendung"]
        self.assertIn("500,00 €", gruen)
        # beide ROT-Gründe zugleich: beide werden genannt
        beide = ueberleben.druck_bestimmen(0, 100, 2200)
        self.assertEqual(beide["regel"], "keine_einnahme")
        self.assertIn("1,00 €", beide["begruendung"])


# ---------------------------------------------------------------- Lage aus echten Daten
class TestLage(UeberlebenTest):
    def test_ohne_daten_ehrlich(self):
        lage = ueberleben.lage(self.kern)
        self.assertEqual((lage["druck"], lage["regel"]), ("GELB", "kosten_fehlen"))
        self.assertIn("Kosten nicht erfasst", lage["begruendung"])
        self.assertIsNone(lage["saldo_cent"])
        self.assertTrue(lage["saldo"].startswith("unbekannt"))
        self.assertIsNone(lage["reichweite_monate"])
        self.assertTrue(lage["reichweite"].startswith("unbekannt"))
        self.assertIsNone(lage["fixkosten_monat_cent"])
        self.assertEqual(lage["fixkosten_monat"], "nicht erfasst")
        self.assertEqual((lage["einnahmen_30_tage_cent"], lage["einnahmen_30_tage"]), (0, "0,00 €"))
        self.assertEqual((lage["einnahmen_monat_cent"], lage["ausgaben_30_tage_cent"]), (0, 0))
        self.assertEqual(lage["offene_forderungen_cent"], 0)
        self.assertNotIn("15,00", json.dumps(lage, ensure_ascii=False))  # Wallet-Startwert taucht nirgends auf

    def test_echte_zahlen_und_30_tage_fenster(self):
        self.einnahme("300", 0)
        self.einnahme("200", 29)        # noch in den letzten 30 Tagen (heute mitgezählt)
        self.einnahme("1000", 30)       # schon außerhalb
        self.ausgabe("50", 10)
        self.ausgabe("20", 40)
        self.kern.finanzen.forderung_anlegen("Muster GmbH", "499", EIGENTUEMER)
        self.fixkosten("Claude-Abo", "30", "monat")
        lage = ueberleben.lage(self.kern)
        self.assertEqual(lage["einnahmen_30_tage_cent"], 50000)
        monat = 30000 + (20000 if self.tag(-29)[:7] == self.heute.isoformat()[:7] else 0)
        self.assertEqual(lage["einnahmen_monat_cent"], monat)
        self.assertEqual(lage["ausgaben_30_tage_cent"], 5000)
        self.assertEqual(lage["saldo_cent"], 143000)               # 300 + 200 + 1000 − 50 − 20
        self.assertEqual(lage["saldo"], "1.430,00 €")
        self.assertEqual(lage["fixkosten_monat_cent"], 3000)
        self.assertEqual(lage["reichweite_monate"], 47.6)          # 1430 / 30 = 47,66… → abgerundet
        self.assertIn("47,6", lage["reichweite"])
        self.assertEqual(lage["offene_forderungen_cent"], 49900)
        self.assertIn("erwartet, nicht sicher", lage["offene_forderungen"])
        self.assertEqual((lage["druck"], lage["regel"]), ("GRÜN", "einnahmen_decken_kosten"))

    def test_gegengebuchte_einnahme_zaehlt_nicht(self):
        bid = self.einnahme("300", 0)
        self.kern.finanzen.gegenbuchung(bid, "falsch erfasst", EIGENTUEMER)
        self.fixkosten()
        lage = ueberleben.lage(self.kern)
        self.assertEqual(lage["einnahmen_30_tage_cent"], 0)
        self.assertEqual(lage["saldo_cent"], 0)
        self.assertEqual((lage["druck"], lage["regel"]), ("ROT", "keine_einnahme"))

    def test_wallet_zaehlt_nie_als_geld(self):
        self.kern.wallet.buchen("einnahme", "1000", "test", "Spielgeld", EIGENTUEMER)
        self.fixkosten()
        lage = ueberleben.lage(self.kern)
        self.assertEqual(lage["einnahmen_30_tage_cent"], 0)
        self.assertIsNone(lage["saldo_cent"])
        self.assertEqual(lage["druck"], "ROT")
        self.assertNotIn("1.015,00", json.dumps(lage, ensure_ascii=False))

    def test_reichweite_nur_wenn_saldo_und_kosten_bekannt(self):
        self.fixkosten()
        self.assertIsNone(ueberleben.lage(self.kern)["reichweite_monate"])     # Saldo unbekannt
        self.ausgabe("100", 1)
        lage = ueberleben.lage(self.kern)
        self.assertEqual(lage["reichweite_monate"], 0.0)                         # Saldo negativ → 0
        self.assertEqual((lage["druck"], lage["regel"]), ("ROT", "keine_einnahme"))

    def test_reichweite_ohne_kosten_unbekannt(self):
        self.einnahme("500", 1)
        lage = ueberleben.lage(self.kern)
        self.assertIsNone(lage["reichweite_monate"])
        self.assertEqual(lage["druck"], "GELB")

    def test_rot_wenn_saldo_unter_monatskosten(self):
        self.einnahme("10", 0)
        self.ausgabe("5", 0)
        self.fixkosten()
        lage = ueberleben.lage(self.kern)
        self.assertEqual((lage["druck"], lage["regel"]), ("ROT", "saldo_unter_kosten"))

    def test_offene_forderung_ist_kein_geld(self):
        self.kern.finanzen.forderung_anlegen("Großkunde AG", "10000", EIGENTUEMER)
        self.fixkosten()
        lage = ueberleben.lage(self.kern)
        self.assertEqual(lage["offene_forderungen_cent"], 1000000)
        self.assertEqual((lage["druck"], lage["regel"]), ("ROT", "keine_einnahme"))


# ---------------------------------------------------------------- Geldchancen
class TestGeldchancen(UeberlebenTest):
    def arten(self, chancen):
        return [c["art"] for c in chancen]

    def test_reihenfolge_naeher_am_geld_zuerst(self):
        t1 = self.ausschreibung("Unterhaltsreinigung Rathaus", 20, punkte=70)
        t2 = self.ausschreibung("Glasreinigung Schule", 30, punkte=90)
        t3 = self.ausschreibung("Unterhaltsreinigung Kita", 10, punkte=90)
        self.forderung("Altkunde KG", "400", -5)
        alt = self.forderung("Uraltkunde OHG", "100", -20)
        a = self.kontakt("Firma Angenommen", "gewonnen")
        self.angebot(a, "angenommen", 2)
        b = self.kontakt("Firma Wartet", "angebot")
        self.angebot(b, "versendet", 10)
        self.kontakt("Firma Interessiert", "interessiert")
        chancen = ueberleben.geldchancen(self.kern)
        self.assertEqual(self.arten(chancen), ["mahnung", "mahnung", "rechnung", "nachfassen", "interessent",
                                               "ausschreibung", "ausschreibung", "ausschreibung"])
        self.assertEqual(chancen[0]["bezug_id"], alt)                       # am längsten überfällig zuerst
        self.assertEqual([c["bezug_id"] for c in chancen[5:]], [t3, t2, t1])  # Punkte, dann Frist
        for c in chancen:
            for feld in ("was", "warum", "naechster_schritt", "frist", "wert"):
                self.assertTrue(str(c[feld]).strip(), (c["art"], feld))

    def test_ausschreibungen_filter(self):
        rein = [self.ausschreibung("Unterhaltsreinigung Rathaus Opladen", 10, plz="51379"),
                self.ausschreibung("Glasreinigung genau drei Tage", 3),
                self.ausschreibung("Vom Inhaber vorgemerkt", 15, status="interessant", punkte=40),
                self.ausschreibung("Mappe liegt bereit", 12, status="vorbereitet", punkte=65)]
        raus = [self.ausschreibung("Zu knapp", 2),
                self.ausschreibung("Abgelaufen", -1),
                self.ausschreibung("Frist unbekannt", None),
                self.ausschreibung("Nicht passend", 20, punkte=59),
                self.ausschreibung("Außerhalb PLZ", 20, plz="73230"),
                self.ausschreibung("Außerhalb laut Bewertung", 20, punkte=60, quelle="ted",
                                   begruendung=["+35 Leistung passt", "−50 außerhalb unserer Region (DE300)"]),
                self.ausschreibung("Abgelehnt", 20, status="abgelehnt"),
                self.ausschreibung("Abgegeben", 20, status="abgegeben"),
                self.ausschreibung("Gewonnen", 20, status="gewonnen"),
                self.ausschreibung("Verloren", 20, status="verloren")]
        ids = [c["bezug_id"] for c in ueberleben.geldchancen(self.kern)]
        self.assertEqual(sorted(ids), sorted(rein))
        self.assertFalse(set(ids) & set(raus))

    def test_ausschreibung_wert_unbekannt_nichts_geschaetzt(self):
        self.ausschreibung("Unterhaltsreinigung Grundschule", 14, punkte=85)
        self.ausschreibung("Mit fremdem Link", 14, punkte=70, link="javascript:alert(1)")
        chancen = ueberleben.geldchancen(self.kern)
        self.assertEqual(len(chancen), 2)
        for c in chancen:
            self.assertEqual(c["wert"], "unbekannt")
            self.assertIsNone(c["wert_cent"])
            self.assertIn(datetime.date.fromisoformat(self.tag(14)).strftime("%d.%m.%Y"), c["frist"])
            self.assertIn("Punkte", c["warum"])
        self.assertTrue(chancen[0]["link"].startswith("https://www.evergabe.nrw.de/"))
        self.assertIsNone(chancen[1]["link"])  # nur https-Links werden weitergegeben

    def test_dublette_aus_zwei_quellen_nur_einmal(self):
        titel = "Unterhaltsreinigung Grundschule Lindenweg Opladen"
        haupt = self.ausschreibung(titel, 20, quelle="evergabe_nrw", extern_id="e1")
        self.ausschreibung(titel, 20, quelle="service_bund", extern_id="b1", plz="51379")
        self.assertEqual([c["bezug_id"] for c in ueberleben.geldchancen(self.kern)], [haupt])

    def test_nachfassen_erst_nach_mehr_als_7_tagen(self):
        k1 = self.kontakt("Sieben Tage GmbH", "angebot")
        self.angebot(k1, "versendet", 7)
        self.assertEqual(ueberleben.geldchancen(self.kern), [])
        k2 = self.kontakt("Acht Tage GmbH", "angebot")
        a2 = self.angebot(k2, "versendet", 8, betrag_cent=29900)
        chancen = ueberleben.geldchancen(self.kern)
        self.assertEqual(self.arten(chancen), ["nachfassen"])
        self.assertEqual(chancen[0]["bezug_id"], a2)
        self.assertEqual(chancen[0]["kontakt_id"], k2)
        self.assertIn("8 Tagen", chancen[0]["warum"])
        self.assertEqual(chancen[0]["wert"], "299,00 €")

    def test_dauerauftrag_wert_pro_monat(self):
        k = self.kontakt("Hausverwaltung Rhein", "angebot")
        self.angebot(k, "versendet", 9, betrag_cent=45000, art="reinigung_dauerauftrag")
        self.assertEqual(ueberleben.geldchancen(self.kern)[0]["wert"], "450,00 € pro Monat (netto)")

    def test_angenommen_ohne_forderung_heisst_rechnung_schreiben(self):
        x = self.kontakt("Firma X", "gewonnen")
        self.angebot(x, "angenommen", 2)
        self.forderung("firma x", "299", 14)                 # Forderung nach der Annahme → erledigt
        y_nr = "ANG-20261120-ABCD"
        self.angebot(None, "angenommen", 3, nr=y_nr)
        self.forderung("Unbekannt", "299", 14, notiz="zu %s" % y_nr)   # Angebotsnummer in der Notiz → erledigt
        w = self.kontakt("Firma W", "gewonnen")
        self.angebot(w, "angenommen", 1)
        alt = self.forderung("Firma W", "50", 14)            # ältere Rechnung für einen früheren Auftrag
        self.kern.db.ausfuehren("UPDATE forderungen SET erstellt=? WHERE id=?", (self.zeitpunkt(30), alt))
        z = self.kontakt("Firma Z", "gewonnen")
        az = self.angebot(z, "angenommen", 5)
        chancen = ueberleben.geldchancen(self.kern)
        self.assertEqual(self.arten(chancen), ["rechnung", "rechnung"])
        self.assertEqual(chancen[0]["bezug_id"], az)          # länger angenommen zuerst
        self.assertIn("Rechnung", chancen[0]["naechster_schritt"])
        self.assertEqual(chancen[0]["wert"], "299,00 €")

    def test_interessent_nur_ohne_laufendes_angebot(self):
        mit = self.kontakt("Hat Entwurf", "interessiert")
        self.angebot(mit, "entwurf", 1)
        nach_absage = self.kontakt("Nach Absage", "interessiert")
        self.angebot(nach_absage, "abgelehnt", 20)
        neu = self.kontakt("Ganz Neu", "interessiert")
        self.kontakt("Nur kontaktiert", "kontaktiert")
        chancen = ueberleben.geldchancen(self.kern)
        self.assertEqual(sorted(c["bezug_id"] for c in chancen), sorted([nach_absage, neu]))
        self.assertTrue(all(c["art"] == "interessent" and c["wert"] == "unbekannt" for c in chancen))

    def test_mahnung_nur_bei_ueberfaelliger_forderung_und_nur_als_entwurf(self):
        self.forderung("Pünktlich AG", "100", 0)              # heute fällig: noch nicht überfällig
        self.forderung("Ohne Datum AG", "100", None)
        bezahlt = self.forderung("Bezahlt AG", "100", -10)
        self.kern.finanzen.forderung_bezahlt(bezahlt, "Kontoauszug 9", "Vater", EIGENTUEMER)
        spaet = self.forderung("Spät GmbH", "1.250,50", -1, rechnung_ref="RE-2026-017")
        chancen = ueberleben.geldchancen(self.kern)
        self.assertEqual([c["bezug_id"] for c in chancen], [spaet])
        c = chancen[0]
        self.assertEqual((c["art"], c["wert"], c["wert_cent"]), ("mahnung", "1.250,50 €", 125050))
        self.assertIn("RE-2026-017", c["entwurf"])
        self.assertIn("1.250,50 €", c["entwurf"])
        self.assertIn(datetime.date.fromisoformat(self.tag(-1)).strftime("%d.%m.%Y"), c["entwurf"])
        self.assertIn("ENTWURF", c["entwurf"])
        self.assertIn("nicht", c["naechster_schritt"])        # „… wird nicht automatisch gesendet“


# ---------------------------------------------------------------- Überlebens-Agent
class AgentTest(UeberlebenTest):
    def starten(self, aid):
        """Beansprucht genau diese Aufgabe – wie der Orchestrator (Status „laufend“ und Eintrag im Verlauf)."""
        z = jetzt()
        with self.kern.db.transaktion() as con:
            self.assertEqual(con.execute("UPDATE aufgaben SET status='laufend', gestartet=?, aktualisiert=?, "
                                         "versuche=versuche+1 WHERE id=? AND status='bereit'", (z, z, aid)).rowcount, 1)
            con.execute("INSERT INTO aufgaben_verlauf (aufgabe_id, zeit, von_status, nach_status, akteur, notiz) "
                        "VALUES (?,?,?,?,?,?)", (aid, z, "bereit", "laufend", "orchestrator", "gestartet"))
        return self.kern.aufgaben.hole(aid)

    def plan(self, ersteller=EIGENTUEMER):
        """Legt einen Überlebensplan an und bearbeitet NUR ihn (Folgeaufgaben bleiben liegen)."""
        aid = self.kern.aufgaben.anlegen("Überlebensplan", "ueberlebensplan", "ueberleben", ersteller, {}, 2)
        self.orch._bearbeiten(self.starten(aid))
        a = self.kern.aufgaben.hole(aid)
        self.assertEqual(a["status"], "abgeschlossen", a["fehler"])
        return a

    def alles_zurueck(self, tage):
        """Simuliert vergangene Tage: alle Aufgaben wurden vor `tage` Tagen angelegt (und ggf. beendet)."""
        z = self.zeitpunkt(tage)
        self.kern.db.ausfuehren("UPDATE aufgaben SET erstellt=?, beendet=CASE WHEN beendet IS NULL THEN NULL "
                                "ELSE ? END", (z, z))

    def folgen(self, typ=None):
        sql, p = "SELECT * FROM aufgaben WHERE ersteller='ueberleben'", []
        if typ:
            sql += " AND typ=?"
            p.append(typ)
        zeilen = self.kern.db.alle(sql + " ORDER BY erstellt, id", p)
        for z in zeilen:
            z["eingabe"] = json.loads(z["eingabe"])
        return zeilen

    def rot(self):
        self.fixkosten()                      # Kosten erfasst, keine Einnahme → ROT

    def gruen(self):
        self.fixkosten()
        self.einnahme("100", 1)               # deckt 22 € → GRÜN

    def acht_ausschreibungen(self):
        return [self.ausschreibung("Unterhaltsreinigung Objekt %d" % i, 20 + i, punkte=90 - 2 * i, extern_id="o%d" % i)
                for i in range(8)]            # 90, 88, …, 76 Punkte


class TestAgentGrundlagen(AgentTest):
    def test_rechte_nur_intern_und_kein_web(self):
        agent = self.kern.register.hole("ueberleben")
        self.assertEqual(agent.name, "Überlebens-Agent")
        self.assertIn("ueberlebensplan", agent.aufgabentypen)
        self.assertEqual(agent.rechte, frozenset({"interne_planung", "interne_auswertung", "datei_erstellen",
                                                  "gedaechtnis_vorschlag"}))
        self.assertTrue(all(risikoklasse(r) == AUTO for r in agent.rechte))
        e = self.kern.supervisor.pruefe("ueberleben", "web_lesen", "ted", url="https://api.ted.europa.eu/v3/x")
        self.assertEqual(e.ergebnis, "verboten")

    def test_plan_ende_zu_ende_datei_escaped_und_gedaechtnis(self):
        self.rot()
        self.ausschreibung("<script>alert(1)</script> Unterhaltsreinigung Rathaus", 15, punkte=85)
        self.forderung("<b>Böse</b> GmbH", "120", -3)
        self.kontakt('<img src=x onerror="alert(1)"> Bau GmbH', "interessiert")
        self.ausschreibung("Mit fremdem Link", 16, punkte=70, link="javascript:alert(2)", extern_id="js")
        a = self.plan()
        e = a["ergebnis"]
        self.assertEqual((e["druck"], e["datum"]), ("ROT", self.heute.isoformat()))
        self.assertIn("keine geprüfte Einnahme", e["begruendung"])
        self.assertEqual([c["art"] for c in e["geldchancen"]], ["mahnung", "interessent", "ausschreibung",
                                                                "ausschreibung"])
        self.assertEqual(e["plan_url"], "/produkte/ueberleben/%s/plan.html" % self.heute.isoformat())
        pfad = e["dateien"][0]
        self.assertTrue(pfad.startswith(os.environ["AUTONOMOUS_DATEN"]))
        with open(pfad, encoding="utf-8") as f:
            seite = f.read()
        # Kein echtes Element mit Skript oder Ereignis-Attribut; Fremdtext steht nur escaped drin
        self.assertNotRegex(seite, r"(?i)<script|<[^>]*\son\w+\s*=|<img|<b>|href=\"javascript:")
        self.assertIn("&lt;script&gt;", seite)
        self.assertIn("&lt;img src=x onerror=&quot;", seite)
        self.assertIn("ROT", seite)
        self.assertIn("nichts gesendet", seite)
        self.assertIn("ENTWURF – Zahlungserinnerung", seite)
        eintrag = [g for g in self.kern.gedaechtnis.liste("vorschlag") if g["thema"].startswith("Überlebensplan")]
        self.assertEqual(len(eintrag), 1)
        self.assertEqual((eintrag[0]["autor"], eintrag[0]["aufgabe_id"]), ("ueberleben", a["id"]))
        self.assertIn("ROT", eintrag[0]["inhalt"])

    def test_plan_ohne_daten_ehrlich(self):
        e = self.plan()["ergebnis"]
        self.assertEqual(e["druck"], "GELB")
        self.assertIn("Kosten nicht erfasst", e["begruendung"])
        self.assertEqual((e["geldchancen"], e["folgeaufgaben_geplant"]), ([], []))
        self.assertTrue(any("ausgeschaltet" in u["grund"] for u in e["uebersprungen"]))
        with open(e["dateien"][0], encoding="utf-8") as f:
            seite = f.read()
        self.assertIn("unbekannt", seite)
        self.assertIn("Keine Geldchance", seite)
        self.assertEqual(self.folgen(), [])

    def test_zweiter_plan_am_selben_tag_eigene_datei(self):
        erster = self.plan()["ergebnis"]["dateien"][0]
        zweiter = self.plan()["ergebnis"]
        self.assertNotEqual(zweiter["dateien"][0], erster)
        self.assertTrue(os.path.isfile(erster) and os.path.isfile(zweiter["dateien"][0]))
        self.assertTrue(zweiter["plan_url"].startswith("/produkte/ueberleben/%s/plan-" % self.heute.isoformat()))


class TestFolgeaufgaben(AgentTest):
    def test_gruen_eine_mappe(self):
        self.gruen()
        besten = self.acht_ausschreibungen()
        plan = self.plan()
        self.assertEqual(plan["ergebnis"]["druck"], "GRÜN")
        folgen = self.folgen("ausschreibung_vorbereiten")
        self.assertEqual([f["eingabe"]["ausschreibung_id"] for f in folgen], besten[:1])
        self.assertEqual((folgen[0]["verantwortlich"], folgen[0]["eltern_id"], folgen[0]["prioritaet"]),
                         ("akquise", plan["id"], 3))

    def test_plan_vermerkt_was_heute_angestossen_wurde(self):
        self.gruen()
        erste, zweite = self.acht_ausschreibungen()[:2]
        k = self.kontakt("Wartet GmbH", "angebot")
        angebot = self.angebot(k, "versendet", 10)
        e = self.plan()["ergebnis"]
        vermerk = {c["bezug_id"]: c.get("angestossen") for c in e["geldchancen"]}
        self.assertIn("Akquise-Agent", vermerk[erste])          # GRÜN: genau eine Mappe – für die beste
        self.assertIsNone(vermerk[zweite])
        self.assertIn("Sales-Agent", vermerk[angebot])
        with open(e["dateien"][0], encoding="utf-8") as f:
            self.assertIn("Heute angestoßen", f.read())

    def test_gelb_drei_mappen(self):
        besten = self.acht_ausschreibungen()             # ohne Kosten → GELB
        self.assertEqual(self.plan()["ergebnis"]["druck"], "GELB")
        folgen = self.folgen("ausschreibung_vorbereiten")
        self.assertEqual(sorted(f["eingabe"]["ausschreibung_id"] for f in folgen), sorted(besten[:3]))
        self.assertTrue(all(f["prioritaet"] == 2 for f in folgen))

    def test_rot_fuenf_mappen_harte_obergrenze(self):
        self.rot()
        besten = self.acht_ausschreibungen()
        e = self.plan()["ergebnis"]
        self.assertEqual(e["druck"], "ROT")
        folgen = self.folgen("ausschreibung_vorbereiten")
        self.assertEqual(sorted(f["eingabe"]["ausschreibung_id"] for f in folgen), sorted(besten[:5]))
        self.assertTrue(all(f["prioritaet"] == 1 for f in folgen))
        self.assertTrue(any("Tagesgrenze" in u["grund"] for u in e["uebersprungen"]))

    def test_schon_vorbereitete_und_offene_werden_nicht_doppelt_angestossen(self):
        self.rot()
        fertig = self.ausschreibung("Schon vorbereitet", 20, status="vorbereitet", punkte=95)
        offen = self.ausschreibung("Mappe in Arbeit", 21, punkte=94)
        self.kern.aufgaben.anlegen("Mappe", "ausschreibung_vorbereiten", "akquise", EIGENTUEMER,
                                   {"ausschreibung_id": offen})
        neu = self.ausschreibung("Noch nichts passiert", 22, punkte=93)
        self.plan()
        self.assertEqual([f["eingabe"]["ausschreibung_id"] for f in self.folgen("ausschreibung_vorbereiten")], [neu])
        self.assertNotIn(fertig, json.dumps(self.folgen()))

    def test_idempotent_am_selben_tag(self):
        self.rot()
        self.acht_ausschreibungen()
        k = self.kontakt("Wartet GmbH", "angebot")
        self.angebot(k, "versendet", 10)
        self.kern.einstellungen.setze("internet_recherche_erlaubt", True, EIGENTUEMER)
        self.plan()
        zaehlen = lambda: {t: len(self.folgen(t)) for t in ("ausschreibung_vorbereiten", "nachricht_entwurf",
                                                             "ausschreibungen_suchen")}
        self.assertEqual(zaehlen(), {"ausschreibung_vorbereiten": 5, "nachricht_entwurf": 1,
                                     "ausschreibungen_suchen": 1})
        zweiter = self.plan()["ergebnis"]
        self.assertEqual(zweiter["folgeaufgaben_geplant"], [])
        self.assertEqual(zaehlen(), {"ausschreibung_vorbereiten": 5, "nachricht_entwurf": 1,
                                     "ausschreibungen_suchen": 1})
        self.assertTrue(zweiter["uebersprungen"])

    def test_naechster_tag_naechste_mappen(self):
        self.rot()
        alle = self.acht_ausschreibungen()
        self.plan()
        self.orch.alle_abarbeiten()                        # echte Mappen entstehen (lokal, ohne Netz)
        vorbereitet = self.kern.db.wert("SELECT COUNT(*) FROM ausschreibungen WHERE status='vorbereitet'")
        self.assertEqual(vorbereitet, 5)
        self.alles_zurueck(1)                              # alles war gestern
        self.plan()
        neu = [f["eingabe"]["ausschreibung_id"] for f in self.folgen("ausschreibung_vorbereiten")
               if f["status"] != "abgeschlossen"]
        self.assertEqual(sorted(neu), sorted(alle[5:]))

    def test_suche_nur_wenn_recherche_an_und_letzter_lauf_aelter_als_20_stunden(self):
        e = self.plan()["ergebnis"]
        self.assertEqual(self.folgen("ausschreibungen_suchen"), [])
        self.assertTrue(any("ausgeschaltet" in u["grund"] for u in e["uebersprungen"]))
        self.kern.einstellungen.setze("internet_recherche_erlaubt", True, EIGENTUEMER)
        vor_2_stunden = (datetime.datetime.now().astimezone() - datetime.timedelta(hours=2)).isoformat(
            timespec="seconds")
        self.kern.db.ausfuehren("INSERT INTO suchlaeufe (zeit, quelle, ergebnis) VALUES (?, 'ted', 'ok')",
                                (vor_2_stunden,))
        e = self.plan()["ergebnis"]
        self.assertEqual(self.folgen("ausschreibungen_suchen"), [])
        self.assertTrue(any("20 Stunden" in u["grund"] for u in e["uebersprungen"]))
        vor_21_stunden = (datetime.datetime.now().astimezone() - datetime.timedelta(hours=21)).isoformat(
            timespec="seconds")
        self.kern.db.ausfuehren("UPDATE suchlaeufe SET zeit=?", (vor_21_stunden,))
        self.plan()
        suche = self.folgen("ausschreibungen_suchen")
        self.assertEqual([(s["verantwortlich"], s["status"]) for s in suche], [("akquise", "bereit")])

    def test_nachfassen_als_entwurf_ueber_sales_ohne_freigabe(self):
        k = self.kontakt("Wartet GmbH", "angebot")
        self.angebot(k, "versendet", 10, titel="Angebot: Treppenhausreinigung")
        self.angebot(None, "versendet", 12, titel="Ohne Kontakt")
        self.plan()
        folgen = self.folgen("nachricht_entwurf")
        self.assertEqual(len(folgen), 1)
        self.assertEqual((folgen[0]["verantwortlich"], folgen[0]["eingabe"]["kontakt_id"]), ("sales", k))
        self.assertIn("Angebot", folgen[0]["eingabe"]["anlass"])
        self.orch.alle_abarbeiten()
        entwurf = self.kern.aufgaben.hole(folgen[0]["id"])
        self.assertEqual(entwurf["status"], "abgeschlossen", entwurf["fehler"])
        self.assertEqual(entwurf["ergebnis"]["vorlage"], "nachfassen")
        self.assertIn("Treppenhausreinigung", entwurf["ergebnis"]["text"])
        self.assertEqual((entwurf["ergebnis"]["sendefertig"], entwurf["ergebnis"]["status"]),
                         (False, "ENTWURF – nicht versendet"))
        self.assertEqual(self.kern.db.wert("SELECT COUNT(*) FROM freigaben"), 0)

    def test_nachfassen_hoechstens_alle_7_tage_je_kontakt(self):
        k = self.kontakt("Wartet GmbH", "angebot")
        self.angebot(k, "versendet", 10)
        self.plan()
        self.orch.alle_abarbeiten()                                      # der Entwurf ist fertig
        self.assertEqual(len(self.folgen("nachricht_entwurf")), 1)
        self.alles_zurueck(3)
        self.plan()
        self.assertEqual(len(self.folgen("nachricht_entwurf")), 1)      # Entwurf von vor 3 Tagen reicht
        self.alles_zurueck(8)
        self.plan()
        self.assertEqual(len(self.folgen("nachricht_entwurf")), 2)

    def test_gleichzeitige_plaene_legen_nichts_doppelt_an(self):
        self.rot()
        drei = [self.ausschreibung("Reinigung Objekt %d" % i, 20, punkte=80 + i, extern_id="g%d" % i)
                for i in range(3)]
        erster = self.kern.aufgaben.anlegen("Plan A", "ueberlebensplan", "ueberleben", EIGENTUEMER)
        a = self.kern.aufgaben.naechste_beanspruchen(["ueberleben"])     # A läuft (z. B. im anderen Arbeiter)
        self.assertEqual(a["id"], erster)
        zweiter = self.kern.aufgaben.anlegen("Plan B", "ueberlebensplan", "ueberleben", EIGENTUEMER)
        self.assertTrue(self.orch.einmal())                                # B läuft parallel und wird fertig
        b = self.kern.aufgaben.hole(zweiter)
        self.assertEqual(b["status"], "abgeschlossen")
        self.assertEqual(b["ergebnis"]["folgeaufgaben_geplant"], [])
        self.assertTrue(any("läuft gerade" in u["grund"] for u in b["ergebnis"]["uebersprungen"]))
        self.orch._bearbeiten(a)                                           # jetzt wird A fertig
        self.assertEqual(self.kern.aufgaben.hole(erster)["status"], "abgeschlossen")
        ids = [f["eingabe"]["ausschreibung_id"] for f in self.folgen("ausschreibung_vorbereiten")]
        self.assertEqual(sorted(ids), sorted(drei))

    def test_geplante_noch_nicht_angelegte_folgeaufgaben_zaehlen_mit(self):
        """Lücke zwischen „Plan fertig“ und „Folgeaufgaben angelegt“: ein zweiter Plan darf nichts doppelt planen."""
        self.rot()
        ids = [self.ausschreibung("Reinigung Haus %d" % i, 20, punkte=90 - i, extern_id="h%d" % i) for i in range(7)]
        vorher = self.kern.aufgaben.anlegen("Plan A", "ueberlebensplan", "ueberleben", EIGENTUEMER)
        self.kern.aufgaben.naechste_beanspruchen(["ueberleben"])
        geplant = [{"schluessel": "ausschreibung_vorbereiten:%s" % i, "typ": "ausschreibung_vorbereiten",
                    "verantwortlich": "akquise", "bezug_id": i} for i in ids[:4]]
        self.kern.aufgaben.abschliessen(vorher, {"folgeaufgaben_geplant": geplant}, "ueberleben")
        self.plan()
        neu = [f["eingabe"]["ausschreibung_id"] for f in self.folgen("ausschreibung_vorbereiten")]
        self.assertEqual(neu, [ids[4]])                     # 4 schon geplant + 1 = Tagesgrenze ROT (5)


class TestSicherheitUndBetrieb(AgentTest):
    def test_keine_freigaben_und_keine_externen_aktionen(self):
        self.rot()
        self.forderung("Spät GmbH", "300", -9)
        self.angebot(self.kontakt("Angenommen GmbH", "gewonnen"), "angenommen", 3)
        k = self.kontakt("Wartet GmbH", "angebot")
        self.kern.db.ausfuehren("UPDATE kontakte SET einwilligung='ja', einwilligung_nachweis='Mail vom 2.11.' "
                                "WHERE id=?", (k,))
        self.angebot(k, "versendet", 9)
        self.kontakt("Interessiert GmbH", "interessiert")
        self.acht_ausschreibungen()
        vorher = {t: self.kern.db.alle("SELECT * FROM %s ORDER BY rowid" % t)
                  for t in ("real_buchungen", "forderungen", "angebote", "kontakte", "wallet_buchungen",
                            "einstellungen")}
        with mock.patch("autonomous.netz.abrufen", side_effect=AssertionError("kein Netz erlaubt")) as netz:
            self.plan()
            self.orch.alle_abarbeiten()
        netz.assert_not_called()
        self.assertEqual(self.kern.db.wert("SELECT COUNT(*) FROM freigaben"), 0)
        zahlen = self.kern.aufgaben.zaehlen()
        self.assertEqual((zahlen["wartet_auf_freigabe"], zahlen["fehlgeschlagen"], zahlen["abgebrochen"]), (0, 0, 0))
        for tabelle, zeilen in vorher.items():
            if tabelle == "angebote" or tabelle == "kontakte":
                self.assertEqual([(z["id"], z["status"]) for z in self.kern.db.alle(
                    "SELECT * FROM %s ORDER BY rowid" % tabelle)], [(z["id"], z["status"]) for z in zeilen], tabelle)
            else:
                self.assertEqual(self.kern.db.alle("SELECT * FROM %s ORDER BY rowid" % tabelle), zeilen, tabelle)
        self.assertFalse(self.kern.db.wert("SELECT COUNT(*) FROM protokoll WHERE ereignis LIKE 'Freigabe%'"))
        entwurf = self.folgen("nachricht_entwurf")[0]
        self.assertFalse(self.kern.aufgaben.hole(entwurf["id"])["ergebnis"]["sendefertig"])

    def test_geldmangel_schaltet_nichts_ab(self):
        self.rot()
        self.ausgabe("500", 2)                                  # Saldo deutlich unter null
        self.kern.wallet.buchen("ausgabe", "25", "test", "Spielgeld weg", EIGENTUEMER)   # Wallet −10 €
        einstellungen = self.kern.einstellungen.alle()
        rollen = sorted(self.kern.register.rollen())
        andere = [("ceo", "tagesplan"), ("ceo", "kennzahlen"), ("finance", "finanzbericht"),
                  ("learning", "auswertung"), ("sales", "pipeline_auswertung"), ("akquise", "auswertung")]
        for rolle, typ in andere:
            self.kern.aufgaben.anlegen(typ, typ, rolle, EIGENTUEMER)
        plan = self.kern.aufgaben.anlegen("Plan", "ueberlebensplan", "ueberleben", EIGENTUEMER)
        for rolle, typ in andere:                              # auch nach dem ROT-Plan läuft alles weiter
            self.kern.aufgaben.anlegen(typ + " danach", typ, rolle, EIGENTUEMER, prioritaet=5)
        self.orch.alle_abarbeiten()
        self.assertEqual(self.kern.aufgaben.hole(plan)["ergebnis"]["druck"], "ROT")
        zahlen = self.kern.aufgaben.zaehlen()
        self.assertEqual(zahlen["abgeschlossen"], 2 * len(andere) + 1)
        self.assertEqual((zahlen["fehlgeschlagen"], zahlen["abgebrochen"]), (0, 0))
        self.assertEqual(self.kern.status()["betrieb"], "laeuft")
        self.assertEqual(self.kern.einstellungen.alle(), einstellungen)
        self.assertEqual(sorted(self.kern.register.rollen()), rollen)


# ---------------------------------------------------------------- Zeitplan
class TestZeitplan(AgentTest):
    def test_hoechstens_einmal_am_tag(self):
        aid = ueberleben.zeitplan_pruefen(self.kern)
        self.assertIsNotNone(aid)
        a = self.kern.aufgaben.hole(aid)
        self.assertEqual((a["typ"], a["verantwortlich"], a["ersteller"]), ("ueberlebensplan", "ueberleben", "zeitplan"))
        self.assertIsNone(ueberleben.zeitplan_pruefen(self.kern))         # schon angelegt
        self.orch.alle_abarbeiten()
        self.assertEqual(self.kern.aufgaben.hole(aid)["status"], "abgeschlossen")
        self.assertIsNone(ueberleben.zeitplan_pruefen(self.kern))         # heute schon erledigt
        self.alles_zurueck(1)                                             # ein neuer Tag
        neu = ueberleben.zeitplan_pruefen(self.kern)
        self.assertIsNotNone(neu)
        self.assertNotEqual(neu, aid)
        self.assertEqual(self.kern.db.wert("SELECT COUNT(*) FROM aufgaben WHERE typ='ueberlebensplan'"), 2)

    def test_plan_des_eigentuemers_von_heute_zaehlt_mit(self):
        self.plan()
        self.assertIsNone(ueberleben.zeitplan_pruefen(self.kern))

    def test_offener_plan_von_gestern_wird_nicht_verdoppelt(self):
        self.kern.aufgaben.anlegen("Plan", "ueberlebensplan", "ueberleben", EIGENTUEMER, sofort_bereit=False)
        self.alles_zurueck(1)
        self.assertIsNone(ueberleben.zeitplan_pruefen(self.kern))

    def test_plan_anlegen_gibt_offenen_plan_zurueck(self):
        aid, neu = ueberleben.plan_anlegen(self.kern, EIGENTUEMER)
        self.assertTrue(neu)
        self.assertEqual(ueberleben.plan_anlegen(self.kern, EIGENTUEMER), (aid, False))


# ---------------------------------------------------------------- Schnittstelle
class TestSchnittstelle(AgentTest):
    def test_ueberleben_vertrag(self):
        self.fixkosten()
        self.ausschreibung("Unterhaltsreinigung Rathaus", 14)
        d = self.api("GET", "/api/ueberleben")
        for feld in ("druck", "begruendung", "reichweite_monate", "einnahmen_30_tage", "ausgaben_30_tage", "saldo",
                     "offene_forderungen", "fixkosten_monat", "geldchancen", "letzter_plan"):
            self.assertIn(feld, d)
        self.assertEqual((d["druck"], d["fixkosten_monat"], d["letzter_plan"]), ("ROT", "22,00 €", None))
        self.assertEqual([c["art"] for c in d["geldchancen"]], ["ausschreibung"])
        self.assertEqual(json.loads(json.dumps(d, ensure_ascii=False))["druck"], "ROT")   # JSON-fähig
        aid = self.api("POST", "/api/ueberleben/plan")["aufgabe_id"]
        zweiter = self.api("POST", "/api/ueberleben/plan")
        self.assertEqual(zweiter["aufgabe_id"], aid)                       # läuft schon → kein zweiter
        self.assertIn("hinweis", zweiter)
        a = self.kern.aufgaben.hole(aid)
        self.assertEqual((a["typ"], a["verantwortlich"], a["ersteller"]),
                         ("ueberlebensplan", "ueberleben", EIGENTUEMER))
        self.orch._bearbeiten(self.starten(aid))
        d = self.api("GET", "/api/ueberleben")
        self.assertEqual((d["letzter_plan"]["aufgabe_id"], d["letzter_plan"]["druck"]), (aid, "ROT"))
        self.assertEqual(d["letzter_plan"]["plan_url"], "/produkte/ueberleben/%s/plan.html" % self.heute.isoformat())
        self.assertEqual(d["letzter_plan"]["folgeaufgaben"], 1)
        self.assertNotEqual(self.api("POST", "/api/ueberleben/plan")["aufgabe_id"], aid)  # danach wieder möglich

    def test_fixkosten_schnittstelle(self):
        self.assertEqual(self.api("GET", "/api/fixkosten")["fixkosten"], [])
        fid = self.api("POST", "/api/fixkosten", {"bezeichnung": "Claude-Abo", "betrag": "22", "intervall": "monat"})["id"]
        self.api("POST", "/api/fixkosten", {"bezeichnung": "Versicherung", "betrag": 120, "intervall": "jahr",
                                            "seit": self.tag(-100)})
        d = self.api("GET", "/api/fixkosten")
        self.assertEqual([f["bezeichnung"] for f in d["fixkosten"]], ["Claude-Abo", "Versicherung"])
        self.assertEqual((d["summe_monat_cent"], d["summe_monat"]), (3200, "32,00 €"))
        for falsch in ({"bezeichnung": "Abo", "betrag": "22", "intervall": "woche"},
                       {"bezeichnung": "Abo", "betrag": "0", "intervall": "monat"},
                       {"betrag": "22", "intervall": "monat"},
                       {"bezeichnung": "Abo", "intervall": "monat"},
                       {"bezeichnung": "Abo", "betrag": "22"},
                       {"bezeichnung": "Abo", "betrag": "22", "intervall": "monat", "seit": "morgen"},
                       {"bezeichnung": ["Liste"], "betrag": "22", "intervall": "monat"}):
            with self.assertRaises(api.ApiFehler, msg=falsch) as f:
                self.api("POST", "/api/fixkosten", falsch)
            self.assertEqual(f.exception.status, 400, falsch)
        self.assertEqual(self.api("POST", "/api/fixkosten/%s/entfernen" % fid), {"ok": True})
        d = self.api("GET", "/api/fixkosten")
        self.assertEqual(([f["bezeichnung"] for f in d["fixkosten"]], d["summe_monat_cent"]), (["Versicherung"], 1000))
        self.assertEqual([f["bezeichnung"] for f in d["entfernt"]], ["Claude-Abo"])
        with self.assertRaises(api.ApiFehler) as f:
            self.api("POST", "/api/fixkosten/%s/entfernen" % fid)
        self.assertEqual(f.exception.status, 404)
        self.assertEqual(self.api("GET", "/api/ueberleben")["fixkosten_monat"], "10,00 €")
