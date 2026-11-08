# -*- coding: utf-8 -*-
"""Die Spielregeln des Überlebens-Agenten - an einer Stelle, damit Simulation und Echt-Modus gleich rechnen.

Alle Beträge sind ganze Cent (int), nie Kommazahlen: so verschwindet kein Cent durch Rundung.

Vom Besitzer festgelegt (so gewünscht):
- Startbudget 10 Euro.
- Jeder Schritt ist eine Stunde Arbeit und kostet 1 Euro.
- Fällt das Guthaben auf 0 oder darunter, ist der Agent tot. Tot bleibt tot.
- Er muss dem Besitzer Miete zahlen (das Handy ist seine Wohnung).
- Er darf sich kopieren. Die Kopie bekommt dieselben Regeln und dieselben 10 Euro Start - bezahlt vom Elternteil.
- Auch jede Kopie zahlt Miete an den Besitzer.

Annahmen von Claude (nicht vom Besitzer festgelegt, darum hier änderbar):
- Höhe der Miete pro Tag, Anteil an jeder Einnahme, Reserve beim Kopieren, Höchstzahl an Agenten.
"""

import re
from dataclasses import dataclass, asdict, field

EURO = 100  # Cent


def euro(cent):
    """Cent als lesbarer Text, z. B. 1050 -> '10,50 €'."""
    vorzeichen = "-" if cent < 0 else ""
    cent = abs(int(cent))
    return f"{vorzeichen}{cent // 100},{cent % 100:02d} €"


def cent_aus_text(text):
    """'5', '5,50', '5.50' -> Cent. Wirft ValueError bei Unsinn oder negativen Beträgen."""
    t = str(text).strip().removesuffix("€").strip().replace(",", ".")
    # Nur ASCII-Ziffern, keine Leerzeichen mitten in der Zahl ('1 000' ist eher ein Tippfehler als 1000 €).
    if not re.fullmatch(r"[0-9]+(\.[0-9]{1,2})?", t):
        raise ValueError(f"Kein Betrag: {text!r} (so schreiben: 12,50)")
    ganz, _, rest = t.partition(".")
    cent = int(ganz) * 100 + int((rest + "00")[:2])
    if cent <= 0:
        raise ValueError("Betrag muss größer als 0 sein.")
    return cent


@dataclass(frozen=True)
class Regeln:
    # --- vom Besitzer festgelegt ---
    startbudget: int = 10 * EURO           # 10 €
    kosten_pro_schritt: int = 1 * EURO     # 1 € pro Schritt
    stunden_pro_schritt: int = 1           # ein Schritt = eine Stunde
    # --- Annahmen (änderbar) ---
    miete_pro_tag: int = 1 * EURO          # 1 € Miete pro Tag (24 Schritte) an den Besitzer
    besitzer_anteil_prozent: int = 20      # 20 % jeder Einnahme gehen sofort an den Besitzer
    kopie_reserve: int = 5 * EURO          # nach dem Kopieren müssen mindestens 5 € übrig bleiben
    max_agenten: int = 10                  # Notbremse: nie mehr als 10 lebende Agenten gleichzeitig
    max_generation: int = 5                # Kopie einer Kopie ... höchstens 5 Ebenen tief

    def als_dict(self):
        return asdict(self)

    @classmethod
    def aus_dict(cls, d):
        bekannt = {k: int(v) for k, v in (d or {}).items() if k in cls.__dataclass_fields__}
        r = cls(**bekannt)
        r.pruefen()
        return r

    def pruefen(self):
        if self.startbudget <= 0 or self.kosten_pro_schritt <= 0:
            raise ValueError("Startbudget und Schrittkosten müssen größer als 0 sein.")
        if self.stunden_pro_schritt <= 0 or 24 % self.stunden_pro_schritt:
            raise ValueError("Stunden pro Schritt müssen 24 teilen (1, 2, 3, 4, 6, 8, 12, 24).")
        if not 0 <= self.besitzer_anteil_prozent <= 100:
            raise ValueError("Besitzer-Anteil muss zwischen 0 und 100 % liegen.")
        if self.miete_pro_tag < 0 or self.kopie_reserve < 0:
            raise ValueError("Miete und Reserve dürfen nicht negativ sein.")
        if self.max_agenten < 1 or self.max_generation < 0:
            raise ValueError("Mindestens ein Agent, Generation ab 0.")
        return self

    @property
    def schritte_pro_tag(self):
        return 24 // self.stunden_pro_schritt


STANDARD = Regeln()

# Was ein Agent tun kann. "nach_aussen": berührt echte Menschen, Plattformen oder echtes Geld.
AKTIONEN = {
    "idee":      {"nach_aussen": False, "text": "Geschäftsidee ausdenken oder verbessern"},
    "bauen":     {"nach_aussen": False, "text": "Am Angebot arbeiten (Text, Produkt, Seite)"},
    "verkaufen": {"nach_aussen": True,  "text": "Kunden ansprechen, Angebot veröffentlichen"},
    "kopieren":  {"nach_aussen": True,  "text": "Sich kopieren (Kopie bekommt das Startbudget)"},
    "auszahlen": {"nach_aussen": True,  "text": "Zusätzlich Geld an den Besitzer überweisen"},
    "warten":    {"nach_aussen": False, "text": "Nichts tun (die Stunde kostet trotzdem)"},
}


@dataclass
class Entscheidung:
    aktion: str
    begruendung: str = ""
    details: dict = field(default_factory=dict)
    ausfall: bool = False   # das Gehirn konnte nicht denken (z. B. Claude nicht erreichbar): Stunde wird nicht berechnet
