# -*- coding: utf-8 -*-
"""Werkzeuge für Product- und Sales-Agent.

Grundregeln für alles, was hier entsteht:
- Eingaben werden gesäubert (Steuerzeichen raus, Längen begrenzt) und beim Einbau in HTML
  IMMER mit ``esc`` escaped.
- Dateien entstehen nur im freigegebenen Datenordner (``daten/produkte``) und werden nie
  überschrieben (exklusives Anlegen).
- Erzeugte Seiten brauchen kein JavaScript und laden nichts von fremden Servern.
"""

import html
import json
import os
import re

from .. import konfig
from ..berechtigungen import pfad_erlaubt
from ..db import jetzt

ANGEBOT_NAME = "Webseiten-Paket für kleine Handwerks-, Bau- und Reinigungsbetriebe in NRW"

_UMBRUECHE = re.compile(r"\r\n?")
# Steuerzeichen sowie unsichtbare Richtungs- und Nullbreiten-Zeichen (Schutz vor Täuschung)
_UNSICHTBAR = re.compile(r"[\x00-\x08\x0b-\x1f\x7f​-‏‪-‮⁦-⁩﻿]")
_NAME = re.compile(r"^[A-Za-z0-9_\-][A-Za-z0-9_.\-]{0,79}$")


# ---------------------------------------------------------------- Texte
def bereinigen(wert, laenge, mehrzeilig=False, streng=False, name="Text"):
    """Säubert eine Eingabe (ohne Escaping). Leere Eingabe ergibt ''.

    ``streng=True``: zu lange Eingaben werden abgelehnt statt still gekürzt."""
    if wert is None:
        return ""
    if isinstance(wert, bool) or not isinstance(wert, (str, int, float)):
        raise ValueError("Ungültiger Text (Zeichenkette erwartet).")
    text = _UMBRUECHE.sub("\n", str(wert)).replace("\t", " ")
    text = _UNSICHTBAR.sub("", text)
    if mehrzeilig:
        zeilen = [" ".join(z.split()) for z in text.split("\n")]
        text = re.sub(r"\n{3,}", "\n\n", "\n".join(zeilen)).strip()
    else:
        text = " ".join(text.split())
    if streng and len(text) > laenge:
        raise ValueError("%s ist zu lang (höchstens %d Zeichen, eingegeben %d)." % (name, laenge, len(text)))
    return text[:laenge].rstrip()


def liste_bereinigen(wert, laenge_je_eintrag, maximal, trenner=r"[,;\n]", name="Eintrag"):
    """Liste oder Text (durch Komma, Semikolon oder Zeilen getrennt) → saubere Liste ohne Doppelte."""
    if wert is None:
        teile = []
    elif isinstance(wert, list):
        teile = wert
    elif isinstance(wert, str):
        teile = re.split(trenner, wert)
    else:
        raise ValueError("Liste oder Text erwartet.")
    ergebnis, gesehen = [], set()
    for teil in teile[:50]:
        eintrag = bereinigen(teil, laenge_je_eintrag, streng=True, name=name)
        if eintrag and eintrag.lower() not in gesehen:
            gesehen.add(eintrag.lower())
            ergebnis.append(eintrag)
    if len(ergebnis) > maximal:
        raise ValueError("Zu viele Einträge (höchstens %d)." % maximal)
    return ergebnis


def esc(text):
    return html.escape(str(text), quote=True)


def esc_zeilen(text):
    return "<br>".join(esc(z) for z in str(text).split("\n"))


def telefon_pruefen(wert):
    """Gibt (Anzeige, Link-Ziffern) zurück oder ('', '') wenn leer."""
    t = bereinigen(wert, 30, streng=True, name="Telefonnummer")
    if not t:
        return "", ""
    if not re.fullmatch(r"\+?[0-9(][0-9 ()/\-]{3,28}", t) or len(re.sub(r"\D", "", t)) < 5:
        raise ValueError("Telefonnummer ungültig (erlaubt: Ziffern, Leerzeichen und + - / ( )).")
    return t, ("+" if t.startswith("+") else "") + re.sub(r"\D", "", t)


_EMAIL = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9](?:[A-Za-z0-9\-]*[A-Za-z0-9])?"
                    r"(?:\.[A-Za-z0-9](?:[A-Za-z0-9\-]*[A-Za-z0-9])?)*\.[A-Za-z]{2,24}")


def email_pruefen(wert):
    e = bereinigen(wert, 120, streng=True, name="E-Mail-Adresse")
    if not e:
        return ""
    if not _EMAIL.fullmatch(e):
        raise ValueError("E-Mail-Adresse ungültig.")
    return e


def datum_deutsch(iso):
    return "%s.%s.%s" % (iso[8:10], iso[5:7], iso[0:4])


# ---------------------------------------------------------------- Dateien
def produkte_wurzel():
    return konfig.unterordner("produkte")


def sicherer_pfad(*teile):
    """Pfad unter daten/produkte aus einfachen Namen (keine Schrägstriche, kein '..')."""
    for teil in teile:
        if not isinstance(teil, str) or not _NAME.match(teil) or ".." in teil:
            raise ValueError("Ungültiger Datei- oder Ordnername.")
    pfad = os.path.join(produkte_wurzel(), *teile)
    if not pfad_erlaubt(pfad):
        raise PermissionError("Pfad außerhalb des freigegebenen Bereichs.")
    return pfad


def datei_schreiben(pfad, inhalt):
    """Legt eine neue Datei an. Vorhandene Dateien werden nie überschrieben (FileExistsError)."""
    if not pfad_erlaubt(pfad):
        raise PermissionError("Datei außerhalb des freigegebenen Bereichs.")
    os.makedirs(os.path.dirname(pfad), exist_ok=True)
    if not pfad_erlaubt(pfad):  # erneut nach dem Anlegen der Ordner (Verknüpfungen)
        raise PermissionError("Datei außerhalb des freigegebenen Bereichs.")
    fd = os.open(pfad, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
    with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as f:
        f.write(inhalt)
    return pfad


# ---------------------------------------------------------------- Produkt-Einträge
def _json(wert):
    return json.dumps(wert, ensure_ascii=False, default=str)


def produkt_eintragen(kern, produkt_id, name, typ, dateien, qualitaet, einschraenkungen, aufgabe_id):
    status = "qualitaet_ok" if qualitaet.get("bestanden") else "qualitaet_mangel"
    kern.db.ausfuehren(
        "INSERT INTO produkte (id, name, typ, status, ordner, dateien, qualitaet, einschraenkungen, aufgabe_id,"
        " erstellt) VALUES (?,?,?,?,?,?,?,?,?,?)",
        (produkt_id, name[:200], typ, status, produkt_id, _json(dateien), _json(qualitaet), _json(einschraenkungen),
         aufgabe_id, jetzt()))
    return status


def aufbereiten(zeile):
    p = dict(zeile)
    for feld, standard in (("dateien", []), ("qualitaet", {}), ("einschraenkungen", [])):
        try:
            p[feld] = json.loads(p.get(feld) or "null") or standard
        except ValueError:
            p[feld] = standard
    p["ansehen_url"] = "/produkte/%s/%s" % (p["ordner"], p["dateien"][0]) if p["dateien"] else None
    return p


def produkt_hole(kern, produkt_id):
    zeile = kern.db.eins("SELECT * FROM produkte WHERE id=?", (produkt_id,))
    return aufbereiten(zeile) if zeile else None


def produkte_liste(kern, grenze=200):
    return [aufbereiten(z) for z in kern.db.alle("SELECT * FROM produkte ORDER BY erstellt DESC LIMIT ?",
                                                  (grenze,))]


# ---------------------------------------------------------------- Gestaltung
SYMBOLE = {
    "haken": '<svg class="symbol" viewBox="0 0 24 24" aria-hidden="true"><path d="M5 12.5l4.5 4.5L19 7.5" '
             'fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" '
             'stroke-linejoin="round"/></svg>',
    "kreuz": '<svg class="symbol" viewBox="0 0 24 24" aria-hidden="true"><path d="M7 7l10 10M17 7L7 17" '
             'fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round"/></svg>',
    "telefon": '<svg class="symbol" viewBox="0 0 24 24" aria-hidden="true"><rect x="7" y="2.5" width="10" '
               'height="19" rx="2.5" fill="none" stroke="currentColor" stroke-width="2"/><path d="M11 18h2" '
               'stroke="currentColor" stroke-width="2" stroke-linecap="round"/></svg>',
    "mail": '<svg class="symbol" viewBox="0 0 24 24" aria-hidden="true"><rect x="3" y="5" width="18" height="14" '
            'rx="2.5" fill="none" stroke="currentColor" stroke-width="2"/><path d="M4 7.5l8 5.5 8-5.5" fill="none" '
            'stroke="currentColor" stroke-width="2" stroke-linejoin="round"/></svg>',
    "ort": '<svg class="symbol" viewBox="0 0 24 24" aria-hidden="true"><path d="M12 21s-6.5-5.8-6.5-11.2a6.5 6.5 '
           '0 0 1 13 0C18.5 15.2 12 21 12 21z" fill="none" stroke="currentColor" stroke-width="2"/>'
           '<circle cx="12" cy="9.8" r="2.3" fill="currentColor"/></svg>',
    "uhr": '<svg class="symbol" viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="12" r="9" fill="none" '
           'stroke="currentColor" stroke-width="2"/><path d="M12 7v5.2l3.4 2" fill="none" stroke="currentColor" '
           'stroke-width="2" stroke-linecap="round"/></svg>',
}

THEMEN = {
    "reinigung": {"dunkel": "#083344", "primaer": "#0e7490", "akzent": "#0e7490", "hell": "#ecfeff"},
    "bau": {"dunkel": "#1c1917", "primaer": "#9a3412", "akzent": "#c2410c", "hell": "#fff7ed"},
    "handwerk": {"dunkel": "#172554", "primaer": "#1d4ed8", "akzent": "#1d4ed8", "hell": "#eff6ff"},
    "verkauf": {"dunkel": "#0f172a", "primaer": "#0e7490", "akzent": "#0e7490", "hell": "#f0f9ff"},
}


def css_seite(thema):
    t = THEMEN[thema]
    return (
        ":root{--dunkel:%(dunkel)s;--primaer:%(primaer)s;--akzent:%(akzent)s;--hell:%(hell)s;"
        "--text:#1f2937;--leise:#4b5563;--rand:#e5e7eb}" % t +
        "*{box-sizing:border-box}html{-webkit-text-size-adjust:100%}"
        "body{margin:0;font-family:system-ui,-apple-system,'Segoe UI',Roboto,'Helvetica Neue',Arial,sans-serif;"
        "font-size:17px;line-height:1.6;color:var(--text);background:#fff;overflow-wrap:break-word}"
        "h1,h2,h3{line-height:1.2;margin:0 0 .5em}h2{font-size:clamp(1.5rem,4vw,2rem)}h3{font-size:1.15rem}"
        "p{margin:0 0 1em}a{color:var(--primaer)}"
        "a:focus-visible,summary:focus-visible{outline:3px solid var(--akzent);outline-offset:3px;border-radius:6px}"
        ".wrap{max-width:1040px;margin:0 auto;padding:0 20px}"
        ".entwurf{background:#fef3c7;color:#78350f;border-bottom:1px solid #fcd34d;padding:8px 20px;"
        "text-align:center;font-size:.9rem;font-weight:600}"
        ".kopf{position:sticky;top:0;z-index:5;background:rgba(255,255,255,.96);border-bottom:1px solid var(--rand)}"
        ".kopf-innen{display:flex;align-items:center;justify-content:space-between;gap:12px;min-height:64px}"
        ".marke{font-weight:800;font-size:1.05rem;color:var(--dunkel);text-decoration:none;min-width:0}"
        ".held{background:linear-gradient(135deg,var(--dunkel),var(--primaer));color:#fff;padding:72px 0 80px}"
        ".held h1{font-size:clamp(2rem,7vw,3.4rem);margin-bottom:.35em;letter-spacing:-.01em}"
        ".dachzeile{text-transform:uppercase;letter-spacing:.08em;font-size:.85rem;font-weight:700;opacity:.9;"
        "margin-bottom:.8em}"
        ".slogan{font-size:clamp(1.1rem,3vw,1.3rem);max-width:40em}"
        ".aktionen{display:flex;flex-wrap:wrap;gap:12px;margin-top:28px}"
        ".knopf{display:inline-flex;align-items:center;justify-content:center;gap:10px;min-height:48px;"
        "padding:12px 22px;border-radius:12px;background:var(--akzent);color:#fff;text-decoration:none;"
        "font-weight:700;border:2px solid transparent}"
        ".knopf:hover{filter:brightness(1.08)}.knopf .symbol{color:inherit;width:20px;height:20px}"
        ".knopf.weiss{background:#fff;color:var(--dunkel)}"
        ".knopf.umriss{background:transparent;border-color:rgba(255,255,255,.85);color:#fff}"
        ".knopf.klein{min-height:40px;padding:8px 16px;font-size:.95rem}.kopf .knopf{flex:none;white-space:nowrap}"
        ".abschnitt{padding:64px 0}.abschnitt.alt{background:var(--hell)}"
        ".einleitung{color:var(--leise);max-width:42em}"
        ".karten{list-style:none;margin:28px 0 0;padding:0;display:grid;"
        "grid-template-columns:repeat(auto-fill,minmax(260px,1fr));gap:16px}"
        ".karte{display:flex;gap:12px;align-items:flex-start;background:#fff;border:1px solid var(--rand);"
        "border-radius:16px;padding:18px 20px;box-shadow:0 1px 3px rgba(15,23,42,.06);font-weight:600;"
        "-webkit-hyphens:auto;hyphens:auto;min-width:0}"
        ".karte>span,.liste li>*,.mit-symbol>span{min-width:0}"
        ".knopf,a[href^='mailto:']{overflow-wrap:anywhere;max-width:100%}"
        ".symbol{width:24px;height:24px;flex:none;color:var(--primaer)}"
        ".zwei{display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:32px}"
        ".liste{list-style:none;margin:0;padding:0;display:grid;gap:14px}"
        ".liste li{display:flex;gap:12px;align-items:flex-start}"
        ".mit-symbol{display:flex;gap:12px;align-items:flex-start}"
        ".platzhalter{border:2px dashed #d97706;background:#fffbeb;color:#78350f;border-radius:14px;padding:18px 20px}"
        ".platzhalter p:last-child{margin-bottom:0}"
        ".rechtliches{padding:48px 0;border-top:1px solid var(--rand)}.rechtliches h2{font-size:1.4rem}"
        ".fuss{background:var(--dunkel);color:#e5e7eb;padding:28px 0;font-size:.95rem}"
        ".fuss .wrap{display:flex;flex-wrap:wrap;gap:12px 24px;justify-content:space-between}"
        ".fuss a{color:#fff}.fuss nav{display:flex;gap:18px;flex-wrap:wrap}"
        "@media (max-width:520px){.held{padding:56px 0 64px}.abschnitt{padding:48px 0}"
        ".aktionen .knopf{width:100%}}"
        "@media print{.kopf{position:static}.held{background:none;color:#000}"
        ".knopf{border:1px solid #000;color:#000;background:none}.entwurf{border:1px solid #000}}"
    )


def platzhalter_rechtliches():
    """Impressum- und Datenschutz-Abschnitt als deutlich markierte Platzhalter."""
    return (
        '<section id="impressum" class="rechtliches" aria-labelledby="h-impressum"><div class="wrap">'
        '<h2 id="h-impressum">Impressum</h2>'
        '<div class="platzhalter" data-offen="Impressum ausfüllen (Inhaber) – keine Rechtsberatung">'
        '<p><strong>PLATZHALTER – Vom Inhaber auszufüllen – keine Rechtsberatung.</strong></p>'
        '<p>Hier stehen die gesetzlichen Pflichtangaben des Anbieters (Impressum, z.&nbsp;B. nach §&nbsp;5 DDG), '
        'etwa: vollständiger Name bzw. Firma und Rechtsform, ladungsfähige Anschrift, Kontakt (Telefon, E-Mail), '
        'gegebenenfalls Registereintrag, Umsatzsteuer-Identifikationsnummer sowie Kammer- und Berufsangaben. '
        'Bitte vollständig ausfüllen und prüfen lassen.</p></div></div></section>\n'
        '<section id="datenschutz" class="rechtliches" aria-labelledby="h-datenschutz"><div class="wrap">'
        '<h2 id="h-datenschutz">Datenschutz</h2>'
        '<div class="platzhalter" data-offen="Datenschutzerklärung ausfüllen (Inhaber) – keine Rechtsberatung">'
        '<p><strong>PLATZHALTER – Vom Inhaber auszufüllen – keine Rechtsberatung.</strong></p>'
        '<p>Hier steht die Datenschutzerklärung (Informationen nach Art.&nbsp;13 DSGVO), z.&nbsp;B. Verantwortlicher, '
        'Zwecke und Rechtsgrundlagen, Hosting-Anbieter und Server-Protokolle, Rechte der Betroffenen.</p>'
        '<p>Technischer Hinweis zu dieser Seite: Sie lädt keine externen Dienste (keine fremden Schriftarten, '
        'keine Karten, keine Statistik- oder Werbedienste) und setzt selbst keine Cookies.</p>'
        '</div></div></section>\n'
    )
