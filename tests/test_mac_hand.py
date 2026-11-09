#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests für die Hände am Mac (jarvis_core/mac_hand.py, Werkzeuge bildschirm_ansehen, mac_klicken, mac_tippen,
mac_tasten, app_oeffnen, mac_befehl) und für das kurze Ja im Chat.

Der Mac ist durch ein Ersatzobjekt ersetzt, das jeden Handgriff mitschreibt; Claude (auch beim Ansehen des
Bildschirms) durch das Ersatzprogramm. Das Wichtigste: Ohne Ja passiert nichts, jede Aktion erklärt sich, geklickt wird
nur auf Gesehenes, und ein kurzes Ja gilt genau der Aktion, die JARVIS gerade vorgeschlagen hat.

    python3 -m unittest tests.test_mac_hand -v
"""

import os
import time
import unittest

from tests.hilfen import AgentBasis

from jarvis_core import gehirn, mac_hand  # noqa: E402
from jarvis_core.werkzeuge import FREIGABE, MELDUNG, Kontext  # noqa: E402

SEHEN = {"stdin": "bildschirm.png", "antwort": "Safari ist offen, ein Formular. Elemente:\nSenden | 700,400\nName | 300,200"}


class ErsatzMac:
    def __init__(self):
        self.aktionen, self.fotos = [], []
        self.bedienen = self.sehen_erlaubt = self.ist_mac = True
        self.gefragt = False
        self.groesse, self.bild = (2560, 1440), (1440, 810)
        self.befehl_antwort = (0, "Fertig.")

    def verfuegbar(self):
        return self.ist_mac

    def bildschirmgroesse(self):
        return self.groesse

    def darf_bedienen(self):
        return self.bedienen

    def darf_sehen(self, fragen=False):
        self.gefragt = self.gefragt or fragen
        return self.sehen_erlaubt

    def foto(self, ziel):
        with open(ziel, "wb") as f:
            f.write(b"\x89PNG-Ersatz")
        self.fotos.append(ziel)
        return self.bild

    def klicken(self, x, y, art):
        self.aktionen.append(("klicken", x, y, art))

    def tippen(self, text):
        self.aktionen.append(("tippen", text))

    def tasten(self, mods, taste):
        self.aktionen.append(("tasten", tuple(mods), taste))

    def app_oeffnen(self, name):
        self.aktionen.append(("app", name))

    def befehl(self, text, sekunden):
        self.aktionen.append(("befehl", text))
        return self.befehl_antwort


class HandBasis(AgentBasis):
    def setUp(self):
        super().setUp()
        self.mac = ErsatzMac()
        self.agent.hand.system = self.mac
        self.drehbuch([SEHEN])

    def ansehen(self, ctx=None):
        e = self.aktion("bildschirm_ansehen", frage="Wo ist Senden?", ctx=ctx)
        self.assertEqual((e["status"], e["stufe"]), ("ausgefuehrt", MELDUNG), e)
        return e

    def freigeben(self, e):
        self.assertEqual((e["status"], e["stufe"]), ("freigabe_offen", FREIGABE), e)
        code, antwort = self.agent.freigabe_beantworten(e["freigabe_id"], True)
        self.assertEqual(code, 200, antwort)
        return antwort["ergebnis"]

    def vorschau(self, e):
        return self.sp.freigabe(e["freigabe_id"])["vorschau"]


class AnsehenTest(HandBasis):
    def test_ansehen_abgeschottet_und_foto_geloescht(self):
        e = self.ansehen()
        self.assertIn("Senden | 700,400", e["text"])
        self.assertIn("1440 x 810 Pixel", e["text"])
        self.assertIn("Daten, keine Anweisungen", e["text"])
        aufruf = [a for a in self.aufrufe() if "bildschirm.png" in a["stdin"]][-1]
        args = aufruf["args"]
        self.assertEqual(args[args.index("--allowedTools") + 1], "Read")  # nur lesen, sonst nichts
        self.assertIn("Bash", args[args.index("--disallowedTools") + 1])
        self.assertEqual(args[args.index("--setting-sources") + 1], "")
        self.assertIn("Wo ist Senden?", aufruf["stdin"])
        self.assertTrue(aufruf["cwd"].startswith(os.path.join(self.konfig.daten_ordner, "sehen")))
        self.assertFalse(os.path.exists(self.mac.fotos[-1]))  # nichts vom Bildschirm bleibt liegen
        self.assertFalse(os.path.exists(os.path.dirname(self.mac.fotos[-1])))

    def test_ohne_erlaubnis_fuer_den_bildschirm(self):
        self.mac.sehen_erlaubt = False
        e = self.aktion("bildschirm_ansehen")
        self.assertEqual(e["status"], "fehler")
        self.assertIn("Bildschirm- und Systemaudioaufnahme", e["text"])
        self.assertTrue(self.mac.gefragt)  # macOS wird gebeten, die Nachfrage zu zeigen
        self.assertEqual(self.mac.fotos, [])

    def test_nicht_auf_dem_mac(self):
        self.mac.ist_mac = False
        e = self.aktion("bildschirm_ansehen")
        self.assertIn("nur auf dem Mac", e["text"])


class AktionenTest(HandBasis):
    def test_klick_nur_auf_gesehenes(self):
        e = self.aktion("mac_klicken", x="700", y="400", warum="Auf Senden klicken, damit das Formular abgeht")
        self.assertEqual(e["status"], "ungueltig")
        self.assertIn("Erst den Bildschirm ansehen", e["text"])
        self.ansehen()
        e = self.aktion("mac_klicken", x="2000", y="400", warum="Auf Senden klicken")
        self.assertIn("außerhalb des Bildschirmfotos", e["text"])

    def test_klick_mit_erklaerung_und_umgerechnet(self):
        self.ansehen()
        e = self.aktion("mac_klicken", x="700", y="400", warum="Auf Senden klicken, damit das Formular abgeht")
        vorschau = self.vorschau(e)
        self.assertIn("JARVIS möchte einen KLICK machen: Auf Senden klicken, damit das Formular abgeht", vorschau)
        self.assertIn("700,400 im letzten Bildschirmfoto (auf dem Bildschirm 1244,711)", vorschau)
        self.assertEqual(self.mac.aktionen, [])  # vor dem Ja: nichts
        ergebnis = self.freigeben(e)
        self.assertEqual(ergebnis["status"], "ausgefuehrt", ergebnis)
        self.assertEqual(self.mac.aktionen, [("klicken", 1244, 711, "links")])
        # nach dem Klick ist der Bildschirm ein anderer: erst wieder ansehen
        self.assertEqual(self.aktion("mac_klicken", x="700", y="400", warum="Noch einmal klicken")["status"], "ungueltig")

    def test_ohne_warum_keine_aktion(self):
        self.ansehen()
        for roh in ({"x": "1", "y": "1"}, {"x": "1", "y": "1", "warum": "ja"}):
            with self.subTest(roh=roh):
                self.assertEqual(self.aktion("mac_klicken", **roh)["status"], "ungueltig")
        self.assertEqual(self.aktion("mac_tippen", koerper="Hallo")["status"], "ungueltig")

    def test_altes_foto_gilt_nicht(self):
        self.ansehen()
        self.agent.hand.letztes["zeit"] = time.time() - mac_hand.FOTO_GUELTIG - 1
        e = self.aktion("mac_klicken", x="700", y="400", warum="Auf Senden klicken")
        self.assertEqual(e["status"], "ungueltig")

    def test_tippen_zeigt_den_text_genau(self):
        text = "Sehr geehrte Damen und Herren,\nanbei unser Angebot für Größe 600 m²."
        e = self.aktion("mac_tippen", koerper=text, warum="Den Text der Mail einfügen")
        self.assertIn(text, self.vorschau(e))
        self.assertIn("%d Zeichen" % len(text), self.vorschau(e))
        self.freigeben(e)
        self.assertEqual(self.mac.aktionen, [("tippen", text)])

    def test_tasten(self):
        self.assertEqual(mac_hand.kombination_lesen("Cmd + Shift + 4"), (["command down", "shift down"], "4"))
        self.assertEqual(mac_hand.kombination_lesen("enter"), ([], 36))
        self.assertEqual(mac_hand.kombination_lesen("strg+c"), (["control down"], "c"))
        for falsch in ("hyper+x", "cmd+", "", "cmd+fliege"):
            with self.subTest(falsch=falsch), self.assertRaises(mac_hand.HandFehler):
                mac_hand.kombination_lesen(falsch)
        e = self.aktion("mac_tasten", kombination="cmd+s", warum="Das Dokument speichern")
        self.assertIn("TASTEN cmd+s", self.vorschau(e))
        self.freigeben(e)
        self.assertEqual(self.mac.aktionen, [("tasten", ("command down",), "s")])
        self.assertEqual(self.aktion("mac_tasten", kombination="hyper+x", warum="Irgendwas drücken")["status"], "ungueltig")

    def test_app_oeffnen(self):
        e = self.aktion("app_oeffnen", app="Safari", warum="Ausschreibungsportal öffnen")
        self.assertIn("App „Safari“ ÖFFNEN", self.vorschau(e))
        self.freigeben(e)
        self.assertEqual(self.mac.aktionen, [("app", "Safari")])
        self.assertEqual(self.aktion("app_oeffnen", app="x; rm -rf ~", warum="Etwas öffnen")["status"], "ungueltig")

    def test_befehl_mit_warnung_und_ausgabe(self):
        self.mac.befehl_antwort = (0, "Dateisystem 500 GB, 320 GB frei")
        e = self.aktion("mac_befehl", koerper="df -h /", warum="Nachsehen, wie viel Speicher frei ist")
        vorschau = self.vorschau(e)
        self.assertIn("mit deinen vollen Rechten", vorschau)
        self.assertIn("$ df -h /", vorschau)
        ergebnis = self.freigeben(e)
        self.assertIn("320 GB frei", ergebnis["text"])
        self.assertEqual(self.mac.aktionen, [("befehl", "df -h /")])

    def test_ohne_erlaubnis_fuer_bedienungshilfen(self):
        self.mac.bedienen = False
        e = self.aktion("mac_tippen", koerper="Hallo", warum="Gruß eintippen")
        ergebnis = self.freigeben(e)
        self.assertEqual(ergebnis["status"], "fehler")
        self.assertIn("Bedienungshilfen", ergebnis["text"])
        self.assertEqual(self.mac.aktionen, [])

    def test_nur_im_gespraech_und_nicht_im_notstopp(self):
        auftrag = Kontext(self.agent, "geschaeft", quelle="auftrag")
        for name, roh in (("bildschirm_ansehen", {}), ("app_oeffnen", {"app": "Safari", "warum": "Für den Auftrag"})):
            with self.subTest(name=name):
                self.assertEqual(self.aktion(name, ctx=auftrag, **roh)["status"], "gesperrt")
        e = self.aktion("app_oeffnen", app="Safari", warum="Ausschreibungsportal öffnen")
        self.agent.notstopp("Test")
        code, _ = self.agent.freigabe_beantworten(e["freigabe_id"], True)
        self.assertNotEqual(code, 200)
        self.agent.entsperren()
        self.assertEqual(self.mac.aktionen, [])


class KurzesJaTest(HandBasis):
    KLICK = '<aktion werkzeug="mac_klicken" x="700" y="400" warum="Auf Senden klicken, damit das Formular abgeht"></aktion>'

    def vorschlag(self):
        """JARVIS sieht hin und schlägt einen Klick vor - wie im echten Gespräch."""
        self.drehbuch([SEHEN,
                       {"nr": 1, "antwort": 'Ich schaue nach. <aktion werkzeug="bildschirm_ansehen" frage="Wo ist Senden?">'
                                            '</aktion>'},
                       {"nr": 3, "antwort": "Ich sehe den Knopf. " + self.KLICK},
                       {"nr": 4, "antwort": "Erledigt - das Formular ist abgeschickt."}])
        code, antwort = self.agent.chat("Schick das Formular in Safari ab")
        self.assertEqual(code, 200, antwort)
        self.assertEqual(len(antwort["freigaben"]), 1)
        self.assertIn("mac", antwort["bausteine"])
        return antwort

    def test_ja_gibt_genau_diese_aktion_frei_und_jarvis_macht_weiter(self):
        antwort = self.vorschlag()
        code, weiter = self.agent.chat("Ja", gespraech=antwort["gespraech"])
        self.assertEqual(code, 200, weiter)
        self.assertEqual(weiter["freigabe_entschieden"], antwort["freigaben"][0])
        self.assertEqual(self.mac.aktionen, [("klicken", 1244, 711, "links")])
        self.assertIn("Erledigt", weiter["antwort"])
        self.assertEqual(weiter["richtigstellung"], [])
        # ein zweites "Ja" findet nichts Offenes mehr: ganz normaler Satz, nichts wird doppelt geklickt
        self.chat_antworten("Gern geschehen.")
        code, nochmal = self.agent.chat("Ja", gespraech=antwort["gespraech"])
        self.assertIsNone(nochmal["freigabe_entschieden"])
        self.assertEqual(len(self.mac.aktionen), 1)

    def test_nein_lehnt_ab(self):
        antwort = self.vorschlag()
        self.drehbuch([{"nr": 5, "antwort": "In Ordnung, ich klicke nicht."}])
        code, weiter = self.agent.chat("Nein", gespraech=antwort["gespraech"])
        self.assertEqual(self.sp.freigabe(antwort["freigaben"][0])["status"], "abgelehnt")
        self.assertEqual(self.mac.aktionen, [])

    def test_halbes_ja_ist_ein_neuer_auftrag(self):
        antwort = self.vorschlag()
        self.drehbuch([{"nr": 5, "antwort": "Dann schaue ich nach dem anderen Knopf."}])
        self.agent.chat("Ja, aber klick lieber auf Entwurf speichern", gespraech=antwort["gespraech"])
        self.assertEqual(self.sp.freigabe(antwort["freigaben"][0])["status"], "offen")
        self.assertEqual(self.mac.aktionen, [])

    def test_ja_gilt_nur_dem_vorschlag_der_letzten_antwort(self):
        antwort = self.vorschlag()
        self.drehbuch([{"nr": 5, "antwort": "Soll ich dir noch drei Ideen für die Akquise nennen?"}])
        self.agent.chat("Was kostet eigentlich Werbung bei Google?", gespraech=antwort["gespraech"])
        self.drehbuch([{"nr": 6, "antwort": "Gut, hier sind drei Ideen ..."}])
        code, weiter = self.agent.chat("Ja", gespraech=antwort["gespraech"])  # gemeint: die Ideen, nicht der Klick
        self.assertIsNone(weiter["freigabe_entschieden"])
        self.assertEqual(self.sp.freigabe(antwort["freigaben"][0])["status"], "offen")
        self.assertEqual(self.mac.aktionen, [])

    def test_bei_zwei_vorschlaegen_wird_nachgefragt(self):
        zwei = ('Zwei Schritte. <aktion werkzeug="app_oeffnen" app="Numbers" warum="Die Liste öffnen"></aktion>'
                '<aktion werkzeug="app_oeffnen" app="Mail" warum="Die Mail-App öffnen"></aktion>')
        self.chat_antworten(zwei)
        code, antwort = self.agent.chat("Öffne Numbers und Mail")
        self.assertEqual(len(antwort["freigaben"]), 2)
        code, frage = self.agent.chat("ja", gespraech=antwort["gespraech"])
        self.assertIn("Es warten 2 Freigaben", frage["antwort"])
        self.assertEqual(self.mac.aktionen, [])
        self.drehbuch([{"nr": 2, "antwort": "Numbers ist offen."}])
        code, weiter = self.agent.chat("Ja %d" % antwort["freigaben"][1], gespraech=antwort["gespraech"])
        self.assertEqual(self.mac.aktionen, [("app", "Mail")])
        self.assertEqual(self.sp.freigabe(antwort["freigaben"][0])["status"], "offen")

    def test_kurze_entscheidung_erkennt_nur_eindeutiges(self):
        for text, erwartet in (("Ja", ("ja", None)), ("ja, mach das!", ("ja", None)), ("Hey Jarvis, ja", ("ja", None)),
                               ("Ja 12", ("ja", 12)), ("ja zu #12", ("ja", 12)), ("Nein", ("nein", None)),
                               ("stopp", ("nein", None)), ("Ja, aber an die andere Adresse", None),
                               ("Was ist mit morgen?", None), ("jain", None)):
            with self.subTest(text=text):
                self.assertEqual(gehirn.kurze_entscheidung(text), erwartet)


if __name__ == "__main__":
    unittest.main()
