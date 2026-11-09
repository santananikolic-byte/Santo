# -*- coding: utf-8 -*-
"""Wissen mit Quellen: jede Zahl belegt, der Stand sichtbar, veraltetes Wissen deutlich markiert."""

import datetime
import os
import shutil
import tempfile
import unittest

from tests.hilfen import AgentBasis

from jarvis_core import gehirn, rollen, wissen  # noqa: E402

PAKET = """# Testwissen
stichworte: testwort
stand: 2026-11-09
pruefen_ab: 2027-01-01

## Teil
- Ein Satz mit Quelle: 15,00 € pro Stunde [1].
%s
## Quellen
[1] Bundesamt: Ein Titel – https://example.org/a
%s"""


class PaketeTest(unittest.TestCase):
    def setUp(self):
        self.ordner = tempfile.mkdtemp(prefix="jarvis_wissen_")

    def tearDown(self):
        shutil.rmtree(self.ordner, ignore_errors=True)

    def schreiben(self, inhalt, name="test"):
        pfad = os.path.join(self.ordner, name + ".md")
        with open(pfad, "w", encoding="utf-8") as f:
            f.write(inhalt)
        return pfad

    def test_alle_pakete_sind_vollstaendig_und_belegt(self):
        pakete = wissen.pakete()
        self.assertEqual([p.name for p in pakete], ["akquise", "auftraege", "ideen", "kalkulation", "personal"])
        for p in pakete:
            with self.subTest(paket=p.name):
                self.assertEqual(wissen.probleme(p), [])  # jede Zahl mit Quelle, jede Quelle genutzt
                self.assertTrue(p.titel)
                self.assertTrue(all(url.startswith("https://") for _titel, url in p.quellen.values()))
                self.assertLessEqual(len(wissen.prompt_text(p)), 5000)  # passt gut in den Systemprompt

    def test_die_wichtigsten_fakten_stehen_drin(self):
        kalkulation = wissen.prompt_text(wissen.paket("kalkulation"))
        for fakt in ("15,00 €", "18,40 €", "13,90 €", "14,60 €", "Steuerschuldnerschaft des Leistungsempfängers",
                     "15 Prozent", "Freistellungsbescheinigung"):
            self.assertIn(fakt, kalkulation)
        auftraege = wissen.prompt_text(wissen.paket("auftraege"))
        for fakt in ("§ 75a", "216.000 €", "5.404.000 €", "evergabe.nrw.de", "AVPQ", "PQ-VOB"):
            self.assertIn(fakt, auftraege)
        self.assertIn("auch gegenüber Firmen", wissen.paket("akquise").text)
        self.assertIn("Sofortmeldung", wissen.paket("personal").text)
        self.assertIn("Eher nicht jetzt", wissen.paket("ideen").text)  # ehrlich, was nicht passt

    def test_betrag_ohne_quelle_wird_gefunden(self):
        p = wissen.lesen(self.schreiben(PAKET % ("- Kostet 20 € extra.\n- Verweis ins Leere [7].", "[2] Zweite: Titel – https://example.org/b")))
        fehler = wissen.probleme(p)
        self.assertIn("Betrag ohne Quelle: - Kostet 20 € extra.", fehler)
        self.assertIn("Verweis [7] ohne Quelle", fehler)
        self.assertIn("Quelle [2] wird nirgends genutzt", fehler)
        self.assertEqual(wissen.probleme(wissen.lesen(self.schreiben(PAKET % ("- Rabatt 5 %% [1].", ""), "zwei"))), [])

    def test_kaputte_pakete_werden_abgelehnt(self):
        gut = PAKET % ("", "")
        faelle = [(gut.replace("stand: 2026-11-09\n", ""), "stand"),
                  (gut.replace("stand: 2026-11-09", "stand: 9.11.2026"), "JJJJ-MM-TT"),
                  (gut.replace("## Quellen", "## Links"), "Quellen"),
                  (gut.replace("[1] Bundesamt: Ein Titel – https://example.org/a", "Bundesamt ohne Nummer"), "nicht lesbar"),
                  (gut.replace("[1] Bundesamt: Ein Titel – https://example.org/a", "[1] Titel – http://unsicher.org"),
                   "nicht lesbar"),
                  (gut.replace("stichworte: testwort", "stichworte: (kaputt"), "Muster"),
                  (gut.replace("# Testwissen\n", ""), "Titel")]
        for inhalt, grund in faelle:
            with self.subTest(grund=grund):
                with self.assertRaises(wissen.WissenFehler) as fall:
                    wissen.lesen(self.schreiben(inhalt))
                self.assertIn(grund, str(fall.exception))

    def test_auswahl_nach_frage(self):
        faelle = [("Wie hoch ist der Mindestlohn in der Reinigung?", {"kalkulation"}),
                  ("Was kostet 500 m² Büroreinigung bei 35 Euro die Stunde, mach ein Angebot", {"kalkulation"}),
                  ("Wir sind Subunternehmer für eine Baufirma, was schreibe ich auf die Rechnung?", {"kalkulation"}),
                  ("Darf ich Hausverwaltungen eine Werbe-Mail schicken?", {"akquise"}),
                  ("Wie finde ich mehr Kunden?", {"akquise"}),
                  ("Wo finde ich Ausschreibungen der Stadt Köln?", {"auftraege"}),
                  ("Kann die Stadtverwaltung uns direkt beauftragen?", {"auftraege"}),
                  ("Ich will jemanden auf Minijob einstellen", {"personal"}),
                  ("Welche zusätzlichen Einnahmen passen zu uns?", {"ideen"}),
                  ("Kann KI uns helfen, mehr Geld zu verdienen?", {"ideen"})]
        for frage, muss in faelle:
            with self.subTest(frage=frage):
                gewaehlt = set(wissen.waehlen(frage))
                self.assertTrue(muss <= gewaehlt, "fehlt %s, gewählt %s" % (muss - gewaehlt, gewaehlt))
        for frage in ("Hallo JARVIS", "Danke dir!", "Ich bin gleich weg", "Gute Idee, mach das", "Wie spät ist es?",
                      "Sortier mein Postfach"):
            self.assertEqual(wissen.waehlen(frage), [], frage)

    def test_vertrieb_hat_akquise_und_auftraege_immer_dabei(self):
        self.assertEqual(wissen.waehlen("", rolle="vertrieb"), ["akquise", "auftraege"])
        self.assertTrue(rollen.erlaubt("vertrieb", "wissen_nachschlagen"))

    def test_veraltetes_wissen_wird_deutlich_markiert(self):
        p = wissen.paket("kalkulation")
        self.assertNotIn("ACHTUNG", wissen.prompt_text(p, heute=p.stand))
        alt = wissen.prompt_text(p, heute=p.pruefen_ab)
        self.assertIn("ACHTUNG: Dieses Wissen ist vom 09.11.2026. Seit 01.01.2027", alt)
        self.assertIn("recherche", alt)
        zeilen = wissen.uebersicht(heute=datetime.date(2027, 1, 2))
        self.assertIn("kalkulation: Löhne, Preise und Steuern (Bau und Reinigung) (Stand 09.11.2026, bitte prüfen", "\n".join(zeilen))
        self.assertNotIn("bitte prüfen", [z for z in zeilen if z.startswith("auftraege")][0])  # gilt bis 2028


class GehirnTest(unittest.TestCase):
    def test_wissen_im_systemprompt_mit_quellen(self):
        prompt = gehirn.systemprompt("(Katalog)", wissen_pakete=["kalkulation", "gibtsnicht"])
        self.assertIn("WISSEN: LÖHNE, PREISE UND STEUERN (BAU UND REINIGUNG) (Stand 09.11.2026", prompt)
        self.assertIn("Quellen: [1] Bundesamt für Justiz", prompt)
        self.assertIn("https://www.bundesregierung.de/", prompt)
        self.assertIn('Abschnitt "WISSEN" nennst du mit Quelle und Stand', prompt)  # Grundregel

    def test_wissen_heisst_gruendlich_denken(self):
        self.assertEqual(gehirn.denkstufe("Und?", []), "schnell")
        self.assertEqual(gehirn.denkstufe("Und?", ["wissen:ideen"]), "gruendlich")

    def test_keine_werbemail_ohne_einwilligung(self):
        akquise = gehirn.baustein_text("akquise")
        self.assertIn("§ 7 UWG", akquise)
        self.assertNotIn("schriftliche Wege", akquise)  # früher missverständlich: E-Mail ist auch schriftlich
        self.assertIn("Brief", akquise)
        self.assertIn("§ 7 UWG", gehirn.baustein_text("email"))


class AgentWissenTest(AgentBasis):
    def test_denkrahmen_bringt_das_passende_wissen(self):
        prompt, bausteine = self.agent.denkrahmen("allgemein", "Wie hoch ist der Mindestlohn in der Reinigung?")
        self.assertIn("wissen:kalkulation", bausteine)
        self.assertIn("15,00 €", prompt)
        prompt, bausteine = self.agent.denkrahmen("allgemein", "Hallo")
        self.assertFalse([b for b in bausteine if b.startswith("wissen:")])
        self.assertNotIn("WISSEN:", prompt)

    def test_nachschlagen(self):
        liste = self.aktion("wissen_nachschlagen")
        self.assertEqual(liste["status"], "ausgefuehrt", liste)
        self.assertEqual(liste["text"].count("\n- "), 5)
        auftraege = self.aktion("wissen_nachschlagen", thema="auftraege")
        self.assertIn("216.000 €", auftraege["text"])
        self.assertIn("Mindestlohn", self.aktion("wissen_nachschlagen", thema="Mindestlohn")["text"])  # per Stichwort
        e = self.aktion("wissen_nachschlagen", thema="Raketenbau")
        self.assertEqual(e["status"], "fehler")
        self.assertIn("recherche", e["text"])

    def test_antwort_nennt_das_wissen_in_den_bausteinen(self):
        self.chat_antworten("Laut Bundesamt für Justiz sind es 15,00 € pro Stunde (Stand 09.11.2026).")
        code, antwort = self.agent.chat("Wie hoch ist der Mindestlohn in der Gebäudereinigung?")
        self.assertEqual(code, 200, antwort)
        self.assertIn("wissen:kalkulation", antwort["bausteine"])
        self.assertEqual(antwort["denkstufe"], "chat")  # das gründliche Modell, nicht "schnell"
        system = self.aufrufe()[-1]
        self.assertIn("WISSEN: LÖHNE, PREISE UND STEUERN", str(system))


if __name__ == "__main__":
    unittest.main()
