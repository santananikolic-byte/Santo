#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Browser-Steuerung über das echte Seitengerüst.

Die Bildschirmsteuerung in ``computer_use`` klickt auf Pixel. Das geht bei
einer Webseite regelmäßig daneben: ein Banner rutscht nach, die Seite lädt
noch, das Fenster ist anders breit - und der Klick landet neben dem Knopf.

Hier wird stattdessen die Seite selbst gelesen. Jeder Knopf, jedes Feld und
jeder Link hat eine Beschriftung, und geklickt wird auf die Beschriftung, nicht
auf eine Koordinate. Das ist der Unterschied zwischen "klick bei 840, 512" und
"klick auf 'Weiter zur Buchung'".

Playwright ist ein zusätzliches Paket. Fehlt es, sagt das Modul das im Klartext
und alles andere läuft weiter.
"""

import json
import re
import time

import config

try:
    from playwright.sync_api import sync_playwright
except Exception:
    # Ohne installiertes Playwright wirft schon der Import.
    sync_playwright = None

# Mehr Schritte braucht kein sinnvoller Vorgang, und die Bremse verhindert,
# dass sich der Agent in einer Seite verläuft und Geld verbrennt.
MAX_SCHRITTE = 15

# Länge des Seitentexts, der an Claude geht. Ein vollständiges Portal hat
# schnell 200.000 Zeichen - davon sind die ersten paar tausend die, in denen
# der gesuchte Knopf steht.
MAX_TEXT = 4000
MAX_ELEMENTE = 60

# Nach diesen Beschriftungen wird nicht weitergeklickt, sondern gefragt.
HALTEPUNKTE = ["bezahlen", "kostenpflichtig", "kaufen", "jetzt buchen",
               "zahlungspflichtig", "abo abschliessen", "abo abschließen",
               "bestellung abschicken", "endgültig löschen", "konto löschen"]

# Beides - das Lesen und das Anfassen - muss exakt dieselbe Liste erzeugen,
# sonst zeigt Nummer 7 beim Klicken auf ein anderes Element als beim Lesen.
# Deshalb steht die Auswahl genau einmal hier und wird in beide Skripte
# eingesetzt, statt zweimal abgeschrieben zu werden.
SAMMEL_JS = """
  const sichtbar = (e) => {
    const r = e.getBoundingClientRect();
    if (r.width < 2 || r.height < 2) return false;
    const s = getComputedStyle(e);
    return s.visibility !== 'hidden' && s.display !== 'none' && s.opacity !== '0';
  };
  const beschriften = (e) => (
    e.getAttribute('aria-label') || e.getAttribute('placeholder') ||
    e.getAttribute('name') || e.getAttribute('title') ||
    e.getAttribute('value') || (e.innerText || '').trim() || ''
  ).replace(/\\s+/g, ' ').slice(0, 90);
  const artVon = (e) => {
    const tag = e.tagName.toLowerCase();
    const typ = (e.getAttribute('type') || '').toLowerCase();
    if (tag === 'a') return 'link';
    if (tag === 'select') return 'auswahl';
    if (tag === 'textarea') return 'feld';
    if (tag === 'input') {
      if (typ === 'submit' || typ === 'button') return 'knopf';
      if (typ === 'checkbox' || typ === 'radio') return 'haken';
      return 'feld';
    }
    return 'knopf';
  };
  const sammeln = () => {
    const auswahl = 'a[href], button, input, textarea, select, [role=button], [onclick]';
    const treffer = [];
    document.querySelectorAll(auswahl).forEach((e) => {
      if (!sichtbar(e) || e.disabled) return;
      if ((e.getAttribute('type') || '').toLowerCase() === 'hidden') return;
      if (!beschriften(e) && artVon(e) !== 'feld') return;
      treffer.push(e);
    });
    return treffer;
  };
"""

STEUER_PROMPT = """Du bedienst eine Webseite. Du bekommst den Seitentext und eine
nummerierte Liste aller anklickbaren Elemente und Eingabefelder.

Antworte ausschließlich als JSON, ohne Fließtext:
{"gedanke": "was du siehst und warum", "aktion": "klicken", "ziel": 7, "text": ""}

Erlaubte Aktionen:
- "klicken"  - ziel ist die Nummer aus der Liste
- "tippen"   - ziel ist die Nummer eines Eingabefelds, text ist der Inhalt
- "auswaehlen" - ziel ist die Nummer einer Auswahlliste, text ist der Wert
- "oeffnen"  - text ist eine vollständige Adresse mit https://
- "warten"   - die Seite lädt noch
- "fertig"   - text ist das Ergebnis in einem Satz für den Nutzer
- "abbruch"  - text sagt, warum es nicht weitergeht

Regeln:
Du gibst nie ein Passwort ein und legst nie ein Konto an. Triffst du eine
Anmeldemaske, brichst du ab und sagst, dass der Nutzer sich selbst anmelden
muss.
Du schließt nie einen Kauf ab. Bis zur Übersicht vor dem Bezahlen darfst du
gehen, dann ist Schluss.
Du erfindest keine Daten. Fehlt dir eine Angabe, brichst du ab und fragst.
Ein Suchergebnis ist noch keine Buchung - sag klar, was du wirklich erreicht
hast."""


def adresse_pruefen(adresse: str):
    """Prüft eine Adresse. Gibt ``(adresse, fehler)`` zurück."""
    roh = (adresse or "").strip()
    if not roh:
        return None, "Es fehlt die Adresse."
    schema = re.match(r"^([a-z][a-z0-9+.-]*):", roh, re.I)
    if schema and schema.group(1).lower() not in ("http", "https"):
        # file:// oder javascript: würde den Browser irgendwohin schicken, nur
        # nicht ins Netz. Ein fehlendes Schema wird ergänzt, ein falsches nicht
        # stillschweigend umgebogen.
        return None, ("'%s' ist keine Web-Adresse. Ich öffne nur http und https."
                      % (adresse or "")[:60])
    if not schema:
        roh = "https://" + roh.lstrip("/")
    if not re.match(r"^https?://[^\s/:]+(:\d+)?([/?#]|$)", roh, re.I):
        return None, "Die Adresse '%s' ergibt keinen Sinn." % (adresse or "")[:60]
    return roh, ""


def haltepunkt(beschriftung: str) -> str:
    """Nennt den Haltebegriff, wenn eine Beschriftung einen enthält."""
    text = (beschriftung or "").lower()
    for begriff in HALTEPUNKTE:
        if begriff in text:
            return begriff
    return ""


class Browser:
    """Ein echter Browser, der das Seitengerüst liest statt Pixel zu raten."""

    def __init__(self, agent=None, sichtbar: bool = True):
        self.agent = agent
        # Sichtbar ist Absicht: der Nutzer soll mitlesen, was passiert, und sich
        # bei Bedarf selbst anmelden. Unsichtbar läuft nur die Abnahme.
        self.sichtbar = sichtbar
        # Normalerweise nimmt Playwright sein eigenes Chromium. Wer schon einen
        # Chrome auf der Platte hat, trägt den Pfad in BROWSER_PROGRAMM ein.
        self.programm = (config.BROWSER_PROGRAMM or "").strip()
        self._spiel = None
        self._browser = None
        self._seite = None
        self.profil = config.BASIS / "browserprofil"

    # -- Zustand ------------------------------------------------------------

    @staticmethod
    def verfuegbar() -> bool:
        return sync_playwright is not None

    def zustand(self) -> dict:
        return {"verfuegbar": self.verfuegbar(),
                "offen": self._seite is not None,
                "adresse": self.adresse(),
                "hinweis": ("bereit" if self.verfuegbar() else
                            "Playwright fehlt: pip3 install playwright "
                            "und danach python3 -m playwright install chromium")}

    def adresse(self) -> str:
        try:
            return self._seite.url if self._seite is not None else ""
        except Exception:
            return ""

    def _fehlt(self) -> dict:
        return {"ok": False,
                "fehler": "Für die Browser-Steuerung fehlt das Paket playwright. "
                          "Im Terminal: pip3 install playwright, danach "
                          "python3 -m playwright install chromium."}

    # -- Start und Ende -----------------------------------------------------

    def _starten(self):
        """Startet den Browser beim ersten Bedarf.

        Das Profil bleibt auf der Platte, damit eine Anmeldung, die der Nutzer
        selbst vorgenommen hat, beim nächsten Mal noch steht. Sonst müsste er
        sich bei jedem Auftrag neu einloggen - und genau das soll er ja nicht.
        """
        if self._seite is not None:
            return None
        if not self.verfuegbar():
            return self._fehlt()
        try:
            self.profil.mkdir(parents=True, exist_ok=True)
            self._spiel = sync_playwright().start()
            self._browser = self._spiel.chromium.launch_persistent_context(
                user_data_dir=str(self.profil), headless=not self.sichtbar,
                viewport={"width": 1280, "height": 900},
                args=["--disable-blink-features=AutomationControlled"],
                **({"executable_path": self.programm} if self.programm else {}))
            self._seite = (self._browser.pages[0] if self._browser.pages
                           else self._browser.new_page())
            self._seite.set_default_timeout(15000)
            return None
        except Exception as fehler:
            self.schliessen()
            return {"ok": False,
                    "fehler": "Der Browser startet nicht: %s. Fehlt vielleicht "
                              "Chromium? Dann: python3 -m playwright install "
                              "chromium." % str(fehler)[:200]}

    def schliessen(self) -> dict:
        """Macht den Browser zu. Fehler dabei sind egal - Hauptsache zu."""
        for gegenstand, name in ((self._browser, "_browser"), (self._spiel, "_spiel")):
            if gegenstand is None:
                continue
            try:
                (gegenstand.close if name == "_browser" else gegenstand.stop)()
            except Exception:
                pass
        self._spiel = self._browser = self._seite = None
        return {"ok": True, "text": "Der Browser ist zu."}

    # -- Lesen --------------------------------------------------------------

    def oeffnen(self, adresse: str) -> dict:
        """Öffnet eine Adresse und liest die Seite."""
        ziel, fehler = adresse_pruefen(adresse)
        if ziel is None:
            return {"ok": False, "fehler": fehler}
        problem = self._starten()
        if problem:
            return problem
        try:
            self._seite.goto(ziel, wait_until="domcontentloaded", timeout=30000)
        except Exception as fehler:
            return {"ok": False,
                    "fehler": "Die Seite %s lädt nicht: %s" % (ziel, str(fehler)[:200])}
        return self.seite_lesen()

    def seite_lesen(self) -> dict:
        """Liest Titel, Text und alle bedienbaren Elemente der offenen Seite."""
        if self._seite is None:
            return {"ok": False, "fehler": "Es ist keine Seite offen."}
        try:
            titel = self._seite.title()
            text = self._seite.inner_text("body")
            elemente = self._elemente_sammeln()
        except Exception as fehler:
            return {"ok": False,
                    "fehler": "Die Seite lässt sich nicht lesen: %s" % str(fehler)[:200]}
        gekuerzt = re.sub(r"\n{3,}", "\n\n", text or "").strip()
        return {"ok": True, "titel": titel, "adresse": self.adresse(),
                "text": gekuerzt[:MAX_TEXT],
                "gekuerzt": len(gekuerzt) > MAX_TEXT,
                "elemente": elemente,
                "anzahl_elemente": len(elemente)}

    def _elemente_sammeln(self) -> list:
        """Sammelt anklickbare Elemente und Eingabefelder mit Beschriftung.

        Die Auswertung läuft im Browser selbst - ein Aufruf statt hunderter
        einzelner Abfragen über die Prozessgrenze. Sonst dauert allein das
        Lesen einer normalen Seite mehrere Sekunden.
        """
        skript = """() => {
          %s
          return sammeln().map((e) => ({
            art: artVon(e), typ: (e.getAttribute('type') || '').toLowerCase(),
            name: beschriften(e), inhalt: (e.value || '').slice(0, 60)}));
        }""" % SAMMEL_JS
        rohe = self._seite.evaluate(skript) or []
        elemente = []
        for nummer, eintrag in enumerate(rohe[:MAX_ELEMENTE], start=1):
            eintrag["nummer"] = nummer
            elemente.append(eintrag)
        return elemente

    def _handhabe(self, nummer: int):
        """Holt das Element mit dieser Nummer aus der Seite.

        Die Nummerierung muss dieselbe Reihenfolge treffen wie beim Lesen -
        deshalb steht dieselbe Auswahl hier noch einmal, und es wird direkt
        das Element zurückgegeben statt eines Namens, der doppelt vorkommen
        könnte.
        """
        skript = """(n) => {
          %s
          return sammeln()[n - 1] || null;
        }""" % SAMMEL_JS
        return self._seite.evaluate_handle(skript, nummer).as_element()

    # -- Bedienen -----------------------------------------------------------

    def klicken(self, nummer: int) -> dict:
        """Klickt das Element mit dieser Nummer."""
        return self._bedienen(nummer, "klicken", "")

    def tippen(self, nummer: int, text: str) -> dict:
        """Schreibt Text in das Feld mit dieser Nummer."""
        return self._bedienen(nummer, "tippen", text)

    def _bedienen(self, nummer, aktion: str, text: str) -> dict:
        if self._seite is None:
            return {"ok": False, "fehler": "Es ist keine Seite offen."}
        try:
            nummer = int(nummer)
        except (TypeError, ValueError):
            return {"ok": False, "fehler": "'%s' ist keine Elementnummer." % nummer}
        if nummer < 1 or nummer > MAX_ELEMENTE:
            return {"ok": False, "fehler": "Element %d gibt es auf dieser Seite nicht."
                                           % nummer}
        try:
            element = self._handhabe(nummer)
            if element is None:
                return {"ok": False,
                        "fehler": "Element %d ist nicht mehr da - die Seite hat sich "
                                  "geändert. Ich lese sie neu." % nummer}
            if aktion == "klicken":
                element.scroll_into_view_if_needed(timeout=5000)
                element.click(timeout=10000)
            elif aktion == "auswaehlen":
                element.select_option(label=text, timeout=10000)
            else:
                element.fill("", timeout=5000)
                element.type(text, delay=25, timeout=15000)
            # Nach einem Klick lädt die Seite oft nach. Ohne die kurze Pause
            # liest der nächste Schritt noch die alte Seite.
            time.sleep(1.2)
            try:
                self._seite.wait_for_load_state("domcontentloaded", timeout=8000)
            except Exception:
                pass
        except Exception as fehler:
            return {"ok": False,
                    "fehler": "Element %d reagiert nicht: %s" % (nummer, str(fehler)[:180])}
        ergebnis = self.seite_lesen()
        ergebnis["getan"] = aktion
        return ergebnis

    def auswaehlen(self, nummer: int, wert: str) -> dict:
        """Wählt einen Eintrag in einer Auswahlliste."""
        return self._bedienen(nummer, "auswaehlen", wert)

    def bildschirmfoto(self, pfad: str = "") -> dict:
        """Legt ein Bild der Seite ab - für den Nachweis, was passiert ist."""
        if self._seite is None:
            return {"ok": False, "fehler": "Es ist keine Seite offen."}
        ziel = pfad or str(config.BASIS / "browser_aufnahme.png")
        try:
            self._seite.screenshot(path=ziel, full_page=False)
        except Exception as fehler:
            return {"ok": False, "fehler": "Kein Bild möglich: %s" % str(fehler)[:150]}
        return {"ok": True, "pfad": ziel, "text": "Bild liegt unter %s." % ziel}

    # -- Auftrag ------------------------------------------------------------

    def erledigen(self, ziel: str, start: str = "", schritte_max: int = MAX_SCHRITTE,
                  bestaetigen=None) -> dict:
        """Arbeitet einen Auftrag im Browser ab, Schritt für Schritt.

        Vor jedem Schritt sagt der Agent, was er tun will. Bei einem
        Haltepunkt - Bezahlen, Löschen - wird gefragt, egal wie sicher er ist.
        """
        if not self.verfuegbar():
            return self._fehlt()
        if self.agent is None or not getattr(self.agent, "einsatzbereit",
                                             lambda: False)():
            return {"ok": False, "fehler": "Ohne Verbindung zu Claude geht das nicht."}
        auftrag = (ziel or "").strip()
        if not auftrag:
            return {"ok": False, "fehler": "Was soll ich im Browser erledigen?"}

        protokoll = []
        seite = self.oeffnen(start) if start else self.seite_lesen()
        if not seite.get("ok"):
            # Auch der Fehlschlag beim Öffnen kommt in derselben Form zurück -
            # der Aufrufer soll nicht zwei Antwortformen auseinanderhalten müssen.
            return {"ok": False, "fehler": seite.get("fehler", ""), "schritte": protokoll}
        for runde in range(1, max(1, int(schritte_max or MAX_SCHRITTE)) + 1):
            schritt = self._naechster_schritt(auftrag, seite, protokoll)
            if not schritt.get("ok"):
                return {"ok": False, "fehler": schritt.get("fehler", ""),
                        "schritte": protokoll}
            plan = schritt["plan"]
            aktion = (plan.get("aktion") or "").lower()
            gedanke = plan.get("gedanke", "")
            text = plan.get("text", "")

            if aktion == "fertig":
                protokoll.append("fertig: %s" % text)
                return {"ok": True, "text": text or "Erledigt.",
                        "adresse": self.adresse(), "schritte": protokoll,
                        "runden": runde}
            if aktion == "abbruch":
                protokoll.append("abbruch: %s" % text)
                return {"ok": False,
                        "fehler": text or "Der Vorgang wurde abgebrochen.",
                        "schritte": protokoll, "runden": runde}

            beschriftung = self._beschriftung(seite, plan.get("ziel"))
            gefahr = haltepunkt("%s %s %s" % (gedanke, text, beschriftung))
            if gefahr and callable(bestaetigen):
                frage = ("Im Browser: %s (%s). Es geht um '%s'. Weiter?"
                         % (gedanke or aktion, beschriftung or text, gefahr))
                if not bestaetigen(frage):
                    protokoll.append("gestoppt bei '%s'" % gefahr)
                    return {"ok": False,
                            "fehler": "Bei '%s' abgebrochen - ohne dein Ja gehe ich "
                                      "da nicht weiter." % gefahr,
                            "schritte": protokoll}
            elif gefahr:
                protokoll.append("gestoppt bei '%s'" % gefahr)
                return {"ok": False,
                        "fehler": "Hier geht es um '%s'. Das mache ich nicht ohne "
                                  "deine ausdrückliche Freigabe." % gefahr,
                        "schritte": protokoll}

            if aktion == "warten":
                time.sleep(2.0)
                seite = self.seite_lesen()
                protokoll.append("gewartet")
                continue
            if aktion == "oeffnen":
                seite = self.oeffnen(text)
            elif aktion == "klicken":
                seite = self.klicken(plan.get("ziel"))
            elif aktion == "tippen":
                seite = self.tippen(plan.get("ziel"), text)
            elif aktion == "auswaehlen":
                seite = self.auswaehlen(plan.get("ziel"), text)
            else:
                return {"ok": False,
                        "fehler": "'%s' ist keine Aktion, die ich kenne." % aktion,
                        "schritte": protokoll}

            protokoll.append("%s %s%s" % (aktion, beschriftung or text,
                                          "" if seite.get("ok")
                                          else " -> %s" % seite.get("fehler", "")))
            if not seite.get("ok"):
                # Ein einzelner Fehlschlag beendet nichts: die Seite wird neu
                # gelesen, der Agent sieht den Stand und entscheidet neu.
                neu = self.seite_lesen()
                if not neu.get("ok"):
                    return {"ok": False, "fehler": seite.get("fehler", ""),
                            "schritte": protokoll}
                neu["letzter_fehler"] = seite.get("fehler", "")
                seite = neu

        return {"ok": False,
                "fehler": "Nach %d Schritten bin ich nicht fertig geworden. Stand: %s"
                          % (schritte_max, self.adresse()),
                "schritte": protokoll}

    @staticmethod
    def _beschriftung(seite: dict, nummer) -> str:
        """Nennt die Beschriftung zu einer Elementnummer - für Protokoll und Frage."""
        try:
            nummer = int(nummer)
        except (TypeError, ValueError):
            return ""
        for element in seite.get("elemente", []):
            if element.get("nummer") == nummer:
                return element.get("name", "")
        return ""

    def _naechster_schritt(self, auftrag: str, seite: dict, protokoll: list) -> dict:
        """Fragt Claude nach genau einem nächsten Schritt."""
        liste = "\n".join(
            "%d. [%s] %s%s" % (e["nummer"], e["art"], e["name"] or "(ohne Beschriftung)",
                               (" = %s" % e["inhalt"]) if e.get("inhalt") else "")
            for e in seite.get("elemente", []))
        bisher = "\n".join("- %s" % z for z in protokoll[-8:]) or "- noch nichts"
        anfrage = ("Auftrag: %s\n\nBisher:\n%s\n\nAdresse: %s\nTitel: %s\n\n"
                   "Seitentext:\n%s\n\nBedienbare Elemente:\n%s\n\n"
                   "Nenne den nächsten Schritt."
                   % (auftrag, bisher, seite.get("adresse", ""), seite.get("titel", ""),
                      seite.get("text", "")[:MAX_TEXT], liste or "(keine gefunden)"))
        if seite.get("letzter_fehler"):
            anfrage += ("\n\nDer letzte Schritt ist fehlgeschlagen: %s"
                        % seite["letzter_fehler"])
        plan = self.agent.json_anfrage(STEUER_PROMPT, anfrage)
        if not isinstance(plan, dict) or not plan.get("aktion"):
            return {"ok": False,
                    "fehler": "Ich bekomme keinen brauchbaren nächsten Schritt zurück."}
        return {"ok": True, "plan": plan}
