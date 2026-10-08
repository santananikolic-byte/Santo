#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""E-Mail - ungelesene Nachrichten holen, vorsortieren, antworten und Entwürfe ablegen.

Die Vorsortierung hier ist grob und arbeitet nur mit Wortlisten. Das ist
Absicht: Sie läuft ohne Netz und ohne Kosten und schafft die Vorauswahl. Die
feine Bewertung übernimmt Claude im Briefing, wo er den Zusammenhang kennt.

Jede Mail in den Listen trägt ``kennung`` (die Message-ID) und ``uid``. Mit der
Kennung antwortet Jarvis im selben Faden (:meth:`Mail.antworten`) oder legt einen
Entwurf an (:meth:`Mail.entwurf_ablegen`). Was Claude liefert (Empfänger,
Betreff, Kennung), landet nie ungeprüft in einer Kopfzeile: Zeilenumbrüche
würden dort weitere Kopfzeilen einschleusen (Bcc, Empfänger), also werden sie
abgelehnt. Was aus fremden Mails kommt, wird einzeilig gemacht.

Für Tests nimmt :class:`Mail` die Netzklassen als Argumente: ``imap_klasse``
(wie ``imaplib.IMAP4_SSL``, Aufruf ``klasse(host, port, ssl_context=...)``),
``smtp_klasse`` (wie ``smtplib.SMTP``) und ``smtp_ssl_klasse`` (wie
``smtplib.SMTP_SSL``). Ohne Angabe werden ``imaplib``/``smtplib`` erst beim
Aufruf nachgeschlagen - Tests dürfen das Modul also auch austauschen.
"""

import base64
import email
import email.header
import email.utils
import imaplib
import re
import smtplib
import ssl
from datetime import datetime, timedelta
from email.headerregistry import Address
from email.message import EmailMessage

import config

IMAP_MONATE = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")

# Grobe Wortlisten für die Vorsortierung.
WICHTIG_WOERTER = ["dringend", "frist", "mahnung", "rechnung", "angebot", "auftrag",
                   "kündigung", "kuendigung", "vertrag", "termin", "zahlung",
                   "überfällig", "ueberfaellig", "reklamation", "beschwerde",
                   "anfrage", "auftragsbestätigung", "letzte erinnerung"]
RAUSCHEN_WOERTER = ["newsletter", "unsubscribe", "abmelden", "no-reply", "noreply",
                    "werbung", "rabatt", "gewinnspiel", "webinar", "sale",
                    "black friday", "prospekt", "marketing", "digest"]


def kopf_dekodieren(roh) -> str:
    """Macht aus einem kodierten Mail-Kopf lesbaren Text."""
    if not roh:
        return ""
    try:
        teile = email.header.decode_header(roh)
    except (ValueError, TypeError):
        return str(roh)
    ergebnis = []
    for inhalt, kodierung in teile:
        if isinstance(inhalt, bytes):
            try:
                ergebnis.append(inhalt.decode(kodierung or "utf-8", errors="replace"))
            except (LookupError, UnicodeDecodeError):
                ergebnis.append(inhalt.decode("utf-8", errors="replace"))
        else:
            ergebnis.append(str(inhalt))
    return "".join(ergebnis).strip()


def klartext_aus_mail(nachricht) -> str:
    """Holt den lesbaren Text aus einer Mail, notfalls aus dem HTML-Teil."""
    if nachricht.is_multipart():
        for teil in nachricht.walk():
            if teil.get_content_type() == "text/plain" and \
                    "attachment" not in str(teil.get("Content-Disposition", "")):
                try:
                    return teil.get_payload(decode=True).decode(
                        teil.get_content_charset() or "utf-8", errors="replace")
                except (AttributeError, LookupError, UnicodeDecodeError):
                    continue
        for teil in nachricht.walk():
            if teil.get_content_type() == "text/html":
                try:
                    roh = teil.get_payload(decode=True).decode(
                        teil.get_content_charset() or "utf-8", errors="replace")
                except (AttributeError, LookupError, UnicodeDecodeError):
                    continue
                import re as _re_html
                return _re_html.sub(r"<[^>]+>", " ", roh)
    else:
        try:
            return nachricht.get_payload(decode=True).decode(
                nachricht.get_content_charset() or "utf-8", errors="replace")
        except (AttributeError, LookupError, UnicodeDecodeError):
            return str(nachricht.get_payload())
    return ""


def triage(betreff: str, absender: str, text: str) -> str:
    """Sortiert eine Mail grob in wichtig, spaeter oder rauschen ein."""
    zusammen = ("%s %s %s" % (betreff or "", absender or "", (text or "")[:800])).lower()
    for wort in RAUSCHEN_WOERTER:
        if wort in zusammen:
            return "rauschen"
    for wort in WICHTIG_WOERTER:
        if wort in zusammen:
            return "wichtig"
    return "spaeter"


# -- Antworten und Entwürfe: Helfer -----------------------------------------

# Wie viele Zeilen der Original-Mail eine Antwort zitiert.
ZITAT_ZEILEN = 20
ZITAT_ZEICHEN = 4000
# Mehr Empfänger als das schickt Jarvis nie in einer Mail.
MAX_EMPFAENGER = 20
# Ältere Bezüge einer Kette werden gekürzt, damit die Kopfzeile nicht ausufert.
MAX_BEZUEGE = 20

# Der Entwürfe-Ordner heißt je nach Anbieter und Sprache anders. Zuerst gilt das
# \Drafts-Merkmal aus LIST, danach diese Namen in dieser Reihenfolge.
ENTWURF_ORDNER_RUECKFALL = ("Drafts", "Entwürfe", "[Gmail]/Entwürfe")
ENTWURF_ORDNER_WEITERE = ("[Gmail]/Drafts", "INBOX.Drafts", "INBOX.Entwürfe", "Entwurf",
                          "Entwürfe und Notizen", "Draft")

_KENNUNG_MUSTER = re.compile(r"<[^<>\s]+>")
_UID_MUSTER = re.compile(rb"\bUID\s+(\d+)", re.IGNORECASE)
_ANTWORT_VORSATZ = re.compile(r"^\s*(re|aw|antw|sv)(\[\d+\])?\s*:", re.IGNORECASE)
_ADRESSE_MUSTER = re.compile(r"^[^@\s<>(),;:\\\"\[\]]+@[^@\s<>(),;:\\\"\[\]]+$")
_LIST_ZEILE = re.compile(r'^\((?P<flags>[^)]*)\)\s+(?P<trenner>"(?:[^"\\]|\\.)*"|NIL)\s+(?P<name>.+)$',
                         re.DOTALL)


def hat_zeilenumbruch(wert) -> bool:
    """Steckt in dem Wert ein Zeilenumbruch (oder Verwandtes) - Angriffsfläche für Kopfzeilen?"""
    text = str(wert if wert is not None else "")
    return any(zeichen in text for zeichen in "\r\n\x00") or len(text.splitlines()) > 1


def _umbruch_fehler(*paare) -> str:
    """Deutscher Fehlertext für das erste Feld mit Zeilenumbruch, sonst ''."""
    for bezeichnung, wert in paare:
        if hat_zeilenumbruch(wert):
            return "%s darf keinen Zeilenumbruch enthalten." % bezeichnung
    return ""


def _einzeilig(wert) -> str:
    """Macht Fremdtext zu einer Zeile - Umbrüche und Steuerzeichen werden zu Leerzeichen."""
    return " ".join(str(wert if wert is not None else "").replace("\x00", "").split())


def kennung_normalisieren(kennung) -> str:
    """Bringt eine Message-ID in die Form ``<id@host>`` - leer, wenn keine zu erkennen ist."""
    text = _einzeilig(kennung)
    if not text:
        return ""
    treffer = _KENNUNG_MUSTER.search(text)
    if treffer:
        return treffer.group(0)[:998]
    if " " in text or "<" in text or ">" in text:
        return ""
    return ("<%s>" % text)[:998]


def kennung_aus_nachricht(nachricht) -> str:
    """Die Message-ID einer eingelesenen Mail, normalisiert - oder ''."""
    return kennung_normalisieren(nachricht.get("Message-ID"))


def _adressen_aus_kopf(wert) -> list:
    """Liest (Name, Adresse)-Paare aus einer Kopfzeile; der Name ist dekodiert."""
    if not wert:
        return []
    ergebnis = []
    for name, adresse in email.utils.getaddresses([_einzeilig(wert)]):
        adresse = adresse.strip()
        if adresse and "@" in adresse:
            ergebnis.append((_einzeilig(kopf_dekodieren(name)), adresse))
    return ergebnis


def _adresse_anzeigen(name: str, adresse: str) -> str:
    """Lesbar, nicht kodiert: ``Anna Weber <anna@weber.at>``."""
    return "%s <%s>" % (name, adresse) if name else adresse


def empfaenger_pruefen(an) -> tuple:
    """Prüft eine Empfängerangabe. Gibt ``(paare, fehler)`` zurück: Paare aus (Name, Adresse).

    Jede Adresse muss genau so in der Angabe stehen, wie sie versendet wird - sonst
    könnte die Freigabe einen anderen Empfänger nennen, als hinterher wirklich eine
    Mail bekommt.
    """
    text = str(an if an is not None else "").strip()
    fehler = "'%s' ist keine gültige Mailadresse." % text[:120]
    if not text or hat_zeilenumbruch(text):
        return [], (fehler if text else "Ich brauche eine Empfängeradresse.")
    paare = []
    for name, adresse in email.utils.getaddresses([text]):
        adresse = adresse.strip()
        if not name.strip() and not adresse:
            continue  # ein überzähliges Komma
        if not _ADRESSE_MUSTER.match(adresse) or adresse.lower() not in text.lower():
            return [], fehler
        paare.append((_einzeilig(kopf_dekodieren(name)), adresse))
    if not paare:
        return [], fehler
    if len(paare) > MAX_EMPFAENGER:
        return [], "Das sind zu viele Empfänger (mehr als %d in einer Mail)." % MAX_EMPFAENGER
    return paare, ""


def _adressliste(paare) -> list:
    """Macht aus (Name, Adresse)-Paaren Adress-Objekte, die der Kopf sauber quotet und kodiert."""
    return [Address(display_name=name, addr_spec=adresse) for name, adresse in paare]


def _eigene_adressen() -> set:
    """Die Adressen des eigenen Postfachs (kleingeschrieben)."""
    eigene = set()
    for wert in (config.SMTP_ABSENDER, config.SMTP_USER,
                 config.IMAP_USER):
        for _name, adresse in email.utils.getaddresses([str(wert or "")]):
            if "@" in adresse:
                eigene.add(adresse.strip().lower())
    return eigene


def _absender_adresse(auch_imap: bool = False) -> str:
    """Absender für ausgehende Mails: SMTP_ABSENDER, sonst SMTP_USER (bei Entwürfen auch IMAP_USER)."""
    erste = config.SMTP_ABSENDER or config.SMTP_USER
    if erste:
        return str(erste)
    return str(config.IMAP_USER or "") if auch_imap else ""


def _nachricht_id(absender: str = "") -> str:
    """Eine neue Message-ID. Die Domain stammt vom Absender, nicht vom Rechnernamen des Macs."""
    domain = None
    for _name, adresse in email.utils.getaddresses([str(absender or "")]):
        if "@" in adresse:
            domain = adresse.rsplit("@", 1)[1].strip() or None
            break
    return email.utils.make_msgid(domain=domain)


def _kopf_wert(kopf: dict, *namen) -> str:
    """Liest ein Feld aus dem Kopf-Dict - Groß-/Kleinschreibung und ``-``/``_`` sind egal."""
    if not isinstance(kopf, dict):
        return ""
    glatt = {}
    for schluessel, wert in kopf.items():
        glatt[str(schluessel).strip().lower().replace("-", "_").replace(" ", "_")] = wert
    for name in namen:
        wert = glatt.get(name)
        if wert not in (None, "", [], ()):
            if isinstance(wert, (list, tuple)):
                wert = " ".join(str(w) for w in wert)
            return str(wert)
    return ""


def antwort_betreff(original) -> str:
    """``Re: <Betreff>`` - ohne ein zweites ``Re:`` (auch ``AW:`` und ``Antw:`` zählen mit)."""
    betreff = _einzeilig(original)
    if not betreff:
        return "Re: (ohne Betreff)"
    if _ANTWORT_VORSATZ.match(betreff):
        return betreff
    return "Re: " + betreff


def zitat_bauen(original_text, datum: str = "", absender: str = "") -> str:
    """Zitiert die ersten Zeilen der Original-Mail mit ``> ``, mit einer Kopfzeile davor."""
    zeilen = str(original_text or "").replace("\r\n", "\n").replace("\r", "\n").split("\n")
    while zeilen and not zeilen[-1].strip():
        zeilen.pop()
    while zeilen and not zeilen[0].strip():
        zeilen.pop(0)
    zeilen = zeilen[:ZITAT_ZEILEN]
    if not zeilen:
        return ""
    gezeigt = []
    for zeile in zeilen:
        zeile = zeile.replace("\x00", "").rstrip()[:1000]
        gezeigt.append("> " + zeile if zeile else ">")
    wer = _einzeilig(absender)
    wann = _einzeilig(datum)
    if wann and wer:
        vorspann = "Am %s schrieb %s:" % (wann, wer)
    elif wer:
        vorspann = "%s schrieb:" % wer
    else:
        vorspann = "Die ursprüngliche Nachricht:"
    return (vorspann + "\n" + "\n".join(gezeigt))[:ZITAT_ZEICHEN]


def bezuege_bauen(alte_bezuege, kennung: str) -> str:
    """Die References-Kette: alte Bezüge plus die Kennung der Mail, auf die geantwortet wird."""
    alte = _einzeilig(alte_bezuege)
    ids = _KENNUNG_MUSTER.findall(alte)
    if not ids and alte:
        ids = [alte]
    if kennung and (not ids or ids[-1] != kennung):
        ids.append(kennung)
    if len(ids) > MAX_BEZUEGE:
        ids = ids[:1] + ids[-(MAX_BEZUEGE - 1):]
    return " ".join(ids)


def antwort_bauen(kopf: dict, text, absender: str = "") -> EmailMessage:
    """Baut die Antwort auf eine Mail im selben Faden.

    ``kopf`` beschreibt die Original-Mail. Gelesen werden (Alternativen in Klammern):
    ``betreff``, ``kennung`` (message_id), ``references`` (referenzen),
    ``antwort_an`` (reply_to, absender, von, an) für den Empfänger, ``datum``,
    ``absender`` für die Zitatzeile und ``text`` (original, auszug) für das Zitat.

    * Betreff ``Re: <Original>`` - ohne zweites ``Re:``,
    * ``In-Reply-To`` = Kennung, ``References`` = alte Bezüge + Kennung,
    * unter dem Antworttext die ersten 20 Zeilen der Original-Mail mit ``> ``.

    Was aus ``kopf`` kommt, gilt als Fremdtext und wird einzeilig gemacht. Der Antworttext
    selbst steht nur im Rumpf. Eine nicht lesbare Empfängerangabe bleibt einfach leer
    (kein ``To``) - geprüft wird sie vor dem Versenden.
    """
    kennung = kennung_normalisieren(_kopf_wert(kopf, "kennung", "message_id", "messageid"))
    betreff = antwort_betreff(_kopf_wert(kopf, "betreff", "subject"))
    ziel = _kopf_wert(kopf, "antwort_an", "reply_to", "absender", "von", "from", "an")
    anzeige_absender = _kopf_wert(kopf, "absender", "von", "from") or ziel
    von = str(absender or "") or _absender_adresse()

    nachricht = EmailMessage()
    if von:
        try:
            nachricht["From"] = von
        except ValueError:
            pass
    paare = [(n, a) for n, a in _adressen_aus_kopf(ziel) if _ADRESSE_MUSTER.match(a)]
    if paare:
        nachricht["To"] = _adressliste(paare[:MAX_EMPFAENGER])
    nachricht["Subject"] = betreff
    nachricht["Date"] = email.utils.formatdate(localtime=True)
    nachricht["Message-ID"] = _nachricht_id(von)
    if kennung:
        nachricht["In-Reply-To"] = kennung
        nachricht["References"] = bezuege_bauen(_kopf_wert(kopf, "references", "referenzen"),
                                                kennung)
    zitat = zitat_bauen(_kopf_wert(kopf, "text", "original", "klartext", "auszug", "body"),
                        _kopf_wert(kopf, "datum", "date"), anzeige_absender)
    rumpf = str(text if text is not None else "").rstrip()
    nachricht.set_content(rumpf + ("\n\n" + zitat if zitat else "") + "\n")
    return nachricht


# -- IMAP-Ordnernamen (modifiziertes UTF-7, RFC 3501) -------------------------

def imap_utf7_kodieren(name: str) -> str:
    """``Entwürfe`` -> ``Entw&APw-rfe`` - so nennen IMAP-Server Ordner mit Umlauten."""
    ergebnis, puffer = [], ""

    def leeren():
        if puffer:
            roh = base64.b64encode(puffer.encode("utf-16-be")).decode("ascii")
            ergebnis.append("&" + roh.rstrip("=").replace("/", ",") + "-")

    for zeichen in str(name):
        if 0x20 <= ord(zeichen) <= 0x7e:
            leeren()
            puffer = ""
            ergebnis.append("&-" if zeichen == "&" else zeichen)
        else:
            puffer += zeichen
    leeren()
    return "".join(ergebnis)


def imap_utf7_dekodieren(name: str) -> str:
    """Umkehrung von :func:`imap_utf7_kodieren`; was sich nicht lesen lässt, bleibt stehen."""
    def ersetzen(treffer):
        innen = treffer.group(1)
        if not innen:
            return "&"
        try:
            roh = innen.replace(",", "/")
            roh += "=" * (-len(roh) % 4)
            return base64.b64decode(roh).decode("utf-16-be")
        except (ValueError, UnicodeDecodeError):
            return treffer.group(0)

    return re.sub(r"&([^-]*)-", ersetzen, str(name))


def _imap_name_quoten(roh: str) -> str:
    """Ein Ordnername als IMAP-Anführungstext (APPEND und SELECT nehmen ihn nicht von allein)."""
    return '"%s"' % str(roh).replace("\\", "\\\\").replace('"', '\\"')


def _ordner_aus_liste(daten) -> list:
    """Liest die Antwort auf LIST: Liste aus ``{'flags', 'roh', 'name'}`` (roh = Name wie vom Server)."""
    eintraege = []
    teile = list(daten or [])
    index = 0
    while index < len(teile):
        stueck = teile[index]
        index += 1
        if isinstance(stueck, tuple):
            # Ein Name als Literal: Kopf in [0], Name in [1].
            zeile = (stueck[0] if isinstance(stueck[0], (bytes, bytearray)) else b"")
            kopf = bytes(zeile).decode("utf-8", errors="replace")
            kopf = re.sub(r"\{\d+\}$", "", kopf).rstrip()
            name = bytes(stueck[1]).decode("utf-8", errors="replace") \
                if isinstance(stueck[1], (bytes, bytearray)) else str(stueck[1])
            zeile_text = kopf + ' "' + name.replace("\\", "\\\\").replace('"', '\\"') + '"'
        elif isinstance(stueck, (bytes, bytearray)):
            zeile_text = bytes(stueck).decode("utf-8", errors="replace")
        elif isinstance(stueck, str):
            zeile_text = stueck
        else:
            continue
        treffer = _LIST_ZEILE.match(zeile_text.strip())
        if not treffer:
            continue
        roh = treffer.group("name").strip()
        if len(roh) >= 2 and roh[0] == '"' and roh[-1] == '"':
            roh = re.sub(r"\\(.)", r"\1", roh[1:-1])
        flags = {f.lower() for f in treffer.group("flags").split()}
        eintraege.append({"flags": flags, "roh": roh, "name": imap_utf7_dekodieren(roh)})
    return eintraege


def entwurf_ordner_kandidaten(daten) -> list:
    """Die Namen (so wie der Server sie kennt), in die ein Entwurf passen könnte - beste zuerst.

    1. Ordner mit dem Merkmal ``\\Drafts`` (der Server sagt selbst, welcher es ist),
    2. Ordner aus LIST, deren Name zu den bekannten passt,
    3. die bekannten Namen blind, falls LIST nichts Brauchbares geliefert hat.
    """
    eintraege = _ordner_aus_liste(daten)
    kandidaten = []

    def vormerken(roh):
        if roh and roh not in kandidaten:
            kandidaten.append(roh)

    for eintrag in eintraege:
        if "\\drafts" in eintrag["flags"] and "\\noselect" not in eintrag["flags"]:
            vormerken(eintrag["roh"])
    bekannt = [n.lower() for n in ENTWURF_ORDNER_RUECKFALL + ENTWURF_ORDNER_WEITERE]
    for gesucht in bekannt:
        for eintrag in eintraege:
            if eintrag["name"].lower() == gesucht and "\\noselect" not in eintrag["flags"]:
                vormerken(eintrag["roh"])
    for name in ENTWURF_ORDNER_RUECKFALL:
        vormerken(imap_utf7_kodieren(name))
    return kandidaten


class Mail:
    """Liest über IMAP und versendet über SMTP.

    Die Netzklassen sind einspeisbar (siehe Modul-Docstring); ohne Angabe nimmt die Klasse
    ``imaplib.IMAP4_SSL``, ``smtplib.SMTP`` und ``smtplib.SMTP_SSL``.
    """

    def __init__(self, imap_klasse=None, smtp_klasse=None, smtp_ssl_klasse=None):
        self.letzter_fehler = ""
        self.imap_klasse = imap_klasse
        self.smtp_klasse = smtp_klasse
        self.smtp_ssl_klasse = smtp_ssl_klasse

    # -- Verfügbarkeit ------------------------------------------------------

    def lesen_moeglich(self) -> bool:
        """Ist der Posteingang eingerichtet?"""
        return bool(config.IMAP_HOST and config.IMAP_USER and config.IMAP_PASSWORT)

    def senden_moeglich(self) -> bool:
        """Ist der Versand eingerichtet?"""
        return bool(config.SMTP_HOST and config.SMTP_USER and config.SMTP_PASSWORT)

    def zustand(self) -> dict:
        """Kurzer Überblick für den Selbsttest."""
        return {"lesen": self.lesen_moeglich(), "senden": self.senden_moeglich(),
                "imap": config.IMAP_HOST or "nicht gesetzt",
                "smtp": config.SMTP_HOST or "nicht gesetzt"}

    # -- Lesen --------------------------------------------------------------

    def _verbinden(self, auswaehlen: bool = True):
        """Meldet sich im Postfach an und öffnet - wenn gewünscht - INBOX nur lesend."""
        klasse = self.imap_klasse or imaplib.IMAP4_SSL
        verbindung = klasse(config.IMAP_HOST, config.IMAP_PORT,
                            ssl_context=ssl.create_default_context())
        try:
            verbindung.login(config.IMAP_USER, config.IMAP_PASSWORT)
            if auswaehlen:
                verbindung.select("INBOX", readonly=True)
        except BaseException:
            self._trennen(verbindung)
            raise
        return verbindung

    @staticmethod
    def _trennen(verbindung):
        if verbindung is None:
            return
        try:
            verbindung.close()
        except (imaplib.IMAP4.error, OSError):
            pass
        try:
            verbindung.logout()
        except (imaplib.IMAP4.error, OSError):
            pass

    @staticmethod
    def _fetch_auswerten(teil) -> tuple:
        """Zerlegt die Antwort auf FETCH: ``(rohe Mail als bytes oder None, uid als Text)``.

        Die UID steht je nach Server vor oder nach dem Rumpf; gesucht wird nur in den
        Kopfstücken der Antwort, nie in der Mail selbst.
        """
        roh, uid = None, ""
        for stueck in teil or []:
            if isinstance(stueck, tuple) and len(stueck) >= 2:
                if roh is None and isinstance(stueck[1], (bytes, bytearray)):
                    roh = bytes(stueck[1])
                kopfstueck = stueck[0]
            else:
                kopfstueck = stueck
            if not uid and isinstance(kopfstueck, (bytes, bytearray)):
                treffer = _UID_MUSTER.search(bytes(kopfstueck))
                if treffer:
                    uid = treffer.group(1).decode("ascii")
        return roh, uid

    @staticmethod
    def _holen(verbindung, nummern) -> list:
        """Holt Mails, neueste zuerst - ohne sie als gelesen zu markieren."""
        mails = []
        for nummer in reversed(nummern):
            # BODY.PEEK lässt die Mail ungelesen - er soll sie selbst noch sehen.
            status, teil = verbindung.fetch(nummer, "(UID BODY.PEEK[])")
            if status != "OK" or not teil or not teil[0]:
                continue
            roh, uid = Mail._fetch_auswerten(teil)
            if roh is None:
                continue
            nachricht = email.message_from_bytes(roh)
            betreff = kopf_dekodieren(nachricht.get("Subject"))
            absender = kopf_dekodieren(nachricht.get("From"))
            text = klartext_aus_mail(nachricht)
            mails.append({
                "id": nummer.decode("ascii", errors="replace"),
                # Die Kennung (Message-ID) trägt eine Mail über Sitzungen hinweg; mit ihr
                # antwortet Jarvis im Faden. Die UID gilt nur im Ordner (und dessen UIDVALIDITY).
                "kennung": kennung_aus_nachricht(nachricht),
                "uid": uid,
                "betreff": betreff or "(ohne Betreff)",
                "absender": absender,
                "datum": kopf_dekodieren(nachricht.get("Date")),
                "auszug": " ".join((text or "").split())[:400],
                "einstufung": triage(betreff, absender, text),
            })
        return mails

    def ungelesene(self, limit: int = 15) -> dict:
        """Holt ungelesene Mails und sortiert sie vor - ohne sie als gelesen zu markieren."""
        if not self.lesen_moeglich():
            return {"ok": False,
                    "fehler": "Der Posteingang ist nicht eingerichtet. Richte ihn ein mit: "
                              "python3 jarvis.py zugang mail"}
        verbindung = None
        try:
            verbindung = self._verbinden()
            status, daten = verbindung.search(None, "UNSEEN")
            if status != "OK":
                return {"ok": False, "fehler": "Der Posteingang antwortet nicht wie erwartet."}
            nummern = daten[0].split()[-limit:] if daten and daten[0] else []
            mails = self._holen(verbindung, nummern)
            return {"ok": True, "anzahl": len(mails), "mails": mails,
                    "wichtig": [m for m in mails if m["einstufung"] == "wichtig"],
                    "spaeter": [m for m in mails if m["einstufung"] == "spaeter"],
                    "rauschen": [m for m in mails if m["einstufung"] == "rauschen"]}
        except (imaplib.IMAP4.error, ssl.SSLError, OSError) as fehler:
            self.letzter_fehler = str(fehler)
            return {"ok": False,
                    "fehler": "Der Posteingang ist nicht erreichbar: %s" % fehler}
        finally:
            self._trennen(verbindung)

    def suchen(self, begriff: str, tage: int = 180, limit: int = 10) -> dict:
        """Sucht im Posteingang nach Absender, Betreff oder Text - auch in gelesenen Mails."""
        if not self.lesen_moeglich():
            return {"ok": False,
                    "fehler": "Der Posteingang ist nicht eingerichtet. Richte ihn ein mit: "
                              "python3 jarvis.py zugang mail"}
        begriff = " ".join(str(begriff or "").split())[:100]
        if len(begriff) < 2:
            return {"ok": False, "fehler": "Wonach soll ich suchen?"}
        tage = max(1, min(int(tage or 180), 3650))
        limit = max(1, min(int(limit or 10), 25))
        # IMAP will englische Monatsnamen, unabhängig von der Spracheinstellung des Macs.
        tag = datetime.now() - timedelta(days=tage)
        seit = "%d-%s-%d" % (tag.day, IMAP_MONATE[tag.month - 1], tag.year)
        verbindung = None
        try:
            verbindung = self._verbinden()
            if begriff.isascii():
                # Anführungszeichen und Rückstriche würden die Suchanfrage aufbrechen.
                sauber = begriff.replace("\\", " ").replace('"', " ")
                status, daten = verbindung.search(None, "SINCE", seit, "TEXT", '"%s"' % sauber)
            else:
                # Umlaute gehen nur als Literal mit Zeichensatz.
                verbindung.literal = begriff.encode("utf-8")
                status, daten = verbindung.search("UTF-8", "SINCE", seit, "TEXT")
            if status != "OK":
                return {"ok": False, "fehler": "Die Suche im Posteingang hat nicht geklappt."}
            nummern = daten[0].split()[-limit:] if daten and daten[0] else []
            mails = self._holen(verbindung, nummern)
            return {"ok": True, "anzahl": len(mails), "begriff": begriff, "tage": tage,
                    "mails": mails}
        except (imaplib.IMAP4.error, ssl.SSLError, OSError) as fehler:
            self.letzter_fehler = str(fehler)
            return {"ok": False,
                    "fehler": "Der Posteingang ist nicht erreichbar: %s" % fehler}
        finally:
            self._trennen(verbindung)

    def zusammenfassung(self, limit: int = 15) -> str:
        """Ein gesprochener Satz über den Posteingang."""
        ergebnis = self.ungelesene(limit)
        if not ergebnis.get("ok"):
            return ergebnis.get("fehler", "Der Posteingang ist nicht erreichbar.")
        if ergebnis["anzahl"] == 0:
            return "Im Posteingang ist nichts Ungelesenes."
        teile = ["%d ungelesene Mails, davon %d wichtig."
                 % (ergebnis["anzahl"], len(ergebnis["wichtig"]))]
        for mail in ergebnis["wichtig"][:4]:
            teile.append("Von %s: %s." % (mail["absender"].split("<")[0].strip(),
                                          mail["betreff"]))
        return " ".join(teile)

    # -- Original-Mail zu einer Kennung ---------------------------------------

    def _original_aus(self, verbindung, kennung: str) -> tuple:
        """Sucht die Mail mit dieser Message-ID im geöffneten Ordner: ``(kopf, fehler)``.

        ``kopf`` ist das Dict für :func:`antwort_bauen` (siehe dort). Gefunden wird per
        ``SEARCH HEADER Message-ID``; weil das eine Teilstring-Suche ist, wird die Kennung
        der gefundenen Mail noch einmal verglichen.
        """
        if kennung.isascii():
            sauber = kennung.replace("\\", "\\\\").replace('"', '\\"')
            status, daten = verbindung.search(None, "HEADER", "Message-ID", '"%s"' % sauber)
        else:
            verbindung.literal = kennung.encode("utf-8")
            status, daten = verbindung.search("UTF-8", "HEADER", "Message-ID")
        if status != "OK":
            return None, "Die Suche nach der Mail im Posteingang hat nicht geklappt."
        nummern = daten[0].split() if daten and daten[0] else []
        for nummer in reversed(nummern[-5:]):
            status, teil = verbindung.fetch(nummer, "(UID BODY.PEEK[])")
            if status != "OK" or not teil or not teil[0]:
                continue
            roh, uid = self._fetch_auswerten(teil)
            if roh is None:
                continue
            nachricht = email.message_from_bytes(roh)
            gefunden = kennung_aus_nachricht(nachricht)
            if gefunden and gefunden.lower() != kennung.lower():
                continue  # nur ein Teilstring-Treffer, nicht diese Mail
            return self._kopf_aus_nachricht(nachricht, kennung, uid), ""
        return None, ("Diese Mail finde ich im Posteingang nicht (mehr). Lies die Mails noch "
                      "einmal, dann nehme ich die Kennung von dort.")

    @staticmethod
    def _kopf_aus_nachricht(nachricht, kennung: str, uid: str = "") -> dict:
        """Das Kopf-Dict einer eingelesenen Original-Mail (alles einzeilig, Adressen geprüft)."""
        absender_paare = _adressen_aus_kopf(nachricht.get("From"))
        antwort_paare = _adressen_aus_kopf(nachricht.get("Reply-To")) or absender_paare
        empfaenger_paare = _adressen_aus_kopf(nachricht.get("To"))
        eigene = _eigene_adressen()
        if antwort_paare and antwort_paare[0][1].lower() in eigene:
            # Die Mail stammt von uns selbst - dann geht die Antwort an den, dem sie galt.
            fremde = [p for p in empfaenger_paare if p[1].lower() not in eigene]
            if fremde:
                antwort_paare = fremde
        absender = ", ".join(_adresse_anzeigen(n, a) for n, a in absender_paare) \
            or _einzeilig(kopf_dekodieren(nachricht.get("From")))
        antwort_an = ", ".join(_adresse_anzeigen(n, a) for n, a in antwort_paare[:1])
        referenzen = nachricht.get("References") or nachricht.get("In-Reply-To") or ""
        return {
            "kennung": kennung,
            "uid": uid,
            "betreff": _einzeilig(kopf_dekodieren(nachricht.get("Subject"))) or "(ohne Betreff)",
            "absender": absender,
            "empfaenger": ", ".join(_adresse_anzeigen(n, a) for n, a in empfaenger_paare)
            or _einzeilig(kopf_dekodieren(nachricht.get("To"))),
            "antwort_an": antwort_an,
            "references": _einzeilig(referenzen),
            "datum": _einzeilig(kopf_dekodieren(nachricht.get("Date"))),
            "text": klartext_aus_mail(nachricht) or "",
        }

    def _original_holen(self, kennung) -> tuple:
        """Öffnet das Postfach und holt die Original-Mail: ``(kopf, fehler)``."""
        kennung = kennung_normalisieren(kennung)
        if not kennung:
            return None, ("Ich brauche die Kennung (Message-ID) der Mail - sie steht in den "
                          "Ergebnissen von mails_lesen und mails_suchen.")
        verbindung = None
        try:
            verbindung = self._verbinden()
            return self._original_aus(verbindung, kennung)
        except (imaplib.IMAP4.error, ssl.SSLError, OSError) as fehler:
            self.letzter_fehler = str(fehler)
            return None, "Der Posteingang ist nicht erreichbar: %s" % fehler
        finally:
            self._trennen(verbindung)

    def kopf_zu_kennung(self, kennung) -> dict:
        """Wer schrieb, an wen, welcher Betreff - für die Freigabe, die nie nur eine Kennung zeigen darf.

        Gibt bei Erfolg ``{"ok": True, "kennung", "absender", "empfaenger", "antwort_an",
        "betreff", "antwort_betreff", "datum", "hinweis"}`` zurück:

        * ``absender`` - von wem die Original-Mail kam (``Name <adresse>``),
        * ``empfaenger`` - an wen sie ging (also meist an das eigene Postfach),
        * ``antwort_an`` - wohin die Antwort wirklich geht (Reply-To, sonst Absender),
        * ``betreff`` - Betreff der Original-Mail, ``antwort_betreff`` - der mit ``Re:``,
        * ``hinweis`` - leer, oder eine Warnung (Antwortadresse weicht vom Absender ab, noreply).

        Sonst ``{"ok": False, "fehler": <deutscher Text>}``. Das Postfach wird nur gelesen.
        """
        fehler = _umbruch_fehler(("Die Kennung", kennung))
        if fehler:
            return {"ok": False, "fehler": fehler}
        if not self.lesen_moeglich():
            return {"ok": False,
                    "fehler": "Die Original-Mail lässt sich nicht nachschlagen: Der Posteingang "
                              "ist nicht eingerichtet. Richte ihn ein mit: "
                              "python3 jarvis.py zugang mail"}
        kopf, fehler = self._original_holen(kennung)
        if fehler:
            return {"ok": False, "fehler": fehler}
        hinweise = []
        absender_adr = {a.lower() for _n, a in _adressen_aus_kopf(kopf["absender"])}
        antwort_adr = [a for _n, a in _adressen_aus_kopf(kopf["antwort_an"])]
        if antwort_adr and absender_adr and antwort_adr[0].lower() not in absender_adr:
            hinweise.append("Die Antwort geht an %s und nicht an den Absender." % antwort_adr[0])
        if antwort_adr and re.search(r"no[-_.]?reply|do[-_.]?not[-_.]?reply", antwort_adr[0], re.I):
            hinweise.append("Diese Adresse nimmt vermutlich keine Antworten an.")
        return {"ok": True, "kennung": kopf["kennung"], "absender": kopf["absender"],
                "empfaenger": kopf["empfaenger"], "antwort_an": kopf["antwort_an"],
                "betreff": kopf["betreff"], "antwort_betreff": antwort_betreff(kopf["betreff"]),
                "datum": kopf["datum"], "hinweis": " ".join(hinweise)}

    # -- Senden -------------------------------------------------------------

    @staticmethod
    def antwort_bauen(kopf: dict, text, absender: str = "") -> EmailMessage:
        """Siehe :func:`antwort_bauen` (gleiche Funktion, hier auch als Methode erreichbar)."""
        return antwort_bauen(kopf, text, absender)

    def _smtp_senden(self, nachricht) -> dict:
        """Schickt eine fertige Nachricht über SMTP: ``{"ok": True}`` oder ``{"ok": False, "fehler"}``."""
        server = None
        try:
            kontext = ssl.create_default_context()
            if int(config.SMTP_PORT) == 465:
                klasse = self.smtp_ssl_klasse or smtplib.SMTP_SSL
                server = klasse(config.SMTP_HOST, config.SMTP_PORT, context=kontext, timeout=30)
            else:
                klasse = self.smtp_klasse or smtplib.SMTP
                server = klasse(config.SMTP_HOST, config.SMTP_PORT, timeout=30)
                server.starttls(context=kontext)
            server.login(config.SMTP_USER, config.SMTP_PASSWORT)
            abgelehnt = server.send_message(nachricht)
        except smtplib.SMTPAuthenticationError:
            return {"ok": False,
                    "fehler": "Der Mailserver lehnt Benutzer oder Passwort ab. Bei Gmail "
                              "und ähnlichen Anbietern braucht es ein App-Passwort."}
        except (smtplib.SMTPException, ssl.SSLError, OSError, ValueError) as fehler:
            return {"ok": False, "fehler": "Die Mail ging nicht raus: %s" % fehler}
        finally:
            self._smtp_schliessen(server)
        if isinstance(abgelehnt, dict) and abgelehnt:
            return {"ok": True, "abgelehnt": sorted(str(a) for a in abgelehnt),
                    "hinweis": "Der Mailserver hat diese Empfänger abgelehnt: %s."
                               % ", ".join(sorted(str(a) for a in abgelehnt))}
        return {"ok": True}

    @staticmethod
    def _smtp_schliessen(server):
        if server is None:
            return
        for name in ("quit", "close"):
            aufruf = getattr(server, name, None)
            if aufruf is None:
                continue
            try:
                aufruf()
                return
            except (smtplib.SMTPException, OSError):
                continue

    def senden(self, an: str, betreff: str, text: str) -> dict:
        """Verschickt eine Mail über SMTP mit STARTTLS.

        Achtung: Die Freigabe wird **nicht** hier eingeholt, sondern im
        Werkzeugkatalog, bevor diese Methode überhaupt aufgerufen wird.
        """
        fehler = _umbruch_fehler(("Der Empfänger", an), ("Der Betreff", betreff))
        if fehler:
            return {"ok": False, "fehler": fehler}
        if not self.senden_moeglich():
            return {"ok": False,
                    "fehler": "Der Mailversand ist nicht eingerichtet. In der Einrichtung "
                              "SMTP-Server, Benutzer und Passwort hinterlegen."}
        an = (an or "").strip()
        if "@" not in an:
            return {"ok": False, "fehler": "'%s' ist keine gültige Mailadresse." % an}
        paare, fehler = empfaenger_pruefen(an)
        if fehler:
            return {"ok": False, "fehler": fehler}

        von = config.SMTP_ABSENDER or config.SMTP_USER
        nachricht = EmailMessage()
        try:
            nachricht["From"] = von
            nachricht["To"] = _adressliste(paare)
            nachricht["Subject"] = betreff or "(ohne Betreff)"
            nachricht["Date"] = email.utils.formatdate(localtime=True)
            nachricht["Message-ID"] = _nachricht_id(von)
            nachricht.set_content(text or "")
        except ValueError as problem:
            return {"ok": False, "fehler": "Die Mail lässt sich so nicht bauen: %s" % problem}

        ergebnis = self._smtp_senden(nachricht)
        if not ergebnis.get("ok"):
            return ergebnis
        antwort = {"ok": True, "text": "Mail an %s ist raus." % an}
        if ergebnis.get("hinweis"):
            antwort["hinweis"] = ergebnis["hinweis"]
        return antwort

    def antworten(self, kennung, text) -> dict:
        """Antwortet auf eine gelesene Mail im selben Faden.

        Sucht die Mail per ``SEARCH HEADER Message-ID``, liest ihre Kopfzeilen und baut mit
        :func:`antwort_bauen` die Antwort (Betreff ``Re:``, ``In-Reply-To``, ``References``,
        Zitat), die dann über SMTP rausgeht. Die Freigabe holt der Werkzeugkatalog vorher
        ein - nicht diese Methode.
        """
        fehler = _umbruch_fehler(("Die Kennung", kennung))
        if fehler:
            return {"ok": False, "fehler": fehler}
        if not self.lesen_moeglich():
            return {"ok": False,
                    "fehler": "Zum Antworten muss ich die Original-Mail im Postfach finden - dafür "
                              "ist der Posteingang nicht eingerichtet. Richte ihn ein mit: "
                              "python3 jarvis.py zugang mail"}
        if not self.senden_moeglich():
            return {"ok": False,
                    "fehler": "Der Mailversand ist nicht eingerichtet. In der Einrichtung "
                              "SMTP-Server, Benutzer und Passwort hinterlegen."}
        kennung = kennung_normalisieren(kennung)
        if not kennung:
            return {"ok": False,
                    "fehler": "Ich brauche die Kennung (Message-ID) der Mail - sie steht in den "
                              "Ergebnissen von mails_lesen und mails_suchen."}
        rumpf = str(text if text is not None else "").strip()
        if not rumpf:
            return {"ok": False, "fehler": "Die Antwort hat keinen Text."}
        kopf, fehler = self._original_holen(kennung)
        if fehler:
            return {"ok": False, "fehler": fehler}
        paare, fehler = empfaenger_pruefen(kopf.get("antwort_an"))
        if fehler:
            return {"ok": False,
                    "fehler": "Auf diese Mail kann ich nicht antworten: Es ist keine "
                              "Antwortadresse zu erkennen."}
        try:
            nachricht = antwort_bauen(kopf, rumpf, config.SMTP_ABSENDER or config.SMTP_USER)
        except ValueError as problem:
            return {"ok": False, "fehler": "Die Antwort lässt sich so nicht bauen: %s" % problem}
        ergebnis = self._smtp_senden(nachricht)
        if not ergebnis.get("ok"):
            return ergebnis
        an = ", ".join(_adresse_anzeigen(n, a) for n, a in paare)
        antwort = {"ok": True, "an": an, "betreff": str(nachricht["Subject"]),
                   "text": "Antwort an %s ist raus." % an}
        if ergebnis.get("hinweis"):
            antwort["hinweis"] = ergebnis["hinweis"]
        return antwort

    # -- Entwürfe -----------------------------------------------------------

    def entwurf_ablegen(self, an, betreff, text, antwort_auf="") -> dict:
        """Legt eine Mail als Entwurf im Entwürfe-Ordner des Postfachs ab. Verschickt wird nichts.

        Der Ordner kommt aus LIST (Merkmal ``\\\\Drafts``), sonst aus bekannten Namen
        (``Drafts``, ``Entwürfe``, ``[Gmail]/Entwürfe`` ...). Mit ``antwort_auf`` (einer
        Message-ID) wird der Entwurf eine Antwort im Faden; leere Felder ``an`` und
        ``betreff`` kommen dann aus der Original-Mail. Ohne ``antwort_auf`` darf ``an`` leer
        bleiben - der Entwurf ist dann ohne Empfänger.
        """
        fehler = _umbruch_fehler(("Der Empfänger", an), ("Der Betreff", betreff),
                                 ("Die Kennung", antwort_auf))
        if fehler:
            return {"ok": False, "fehler": fehler}
        if not self.lesen_moeglich():
            return {"ok": False, "fehler": "Für Entwürfe im Postfach fehlt der IMAP-Zugang."}
        an = str(an if an is not None else "").strip()
        betreff = str(betreff if betreff is not None else "").strip()
        rumpf = str(text if text is not None else "").rstrip()
        if not rumpf:
            return {"ok": False, "fehler": "Der Entwurf braucht einen Text."}
        paare = []
        if an:
            paare, fehler = empfaenger_pruefen(an)
            if fehler:
                return {"ok": False, "fehler": fehler}
        faden = kennung_normalisieren(antwort_auf) if str(antwort_auf or "").strip() else ""
        if str(antwort_auf or "").strip() and not faden:
            return {"ok": False,
                    "fehler": "Die Kennung der Mail, auf die der Entwurf antwortet, ist nicht lesbar."}

        verbindung = None
        try:
            verbindung = self._verbinden(auswaehlen=bool(faden))
            von = _absender_adresse(auch_imap=True)
            if "@" not in von:
                von = str(config.IMAP_USER or "") if "@" in str(config.IMAP_USER or "") else ""
            if faden:
                kopf, fehler = self._original_aus(verbindung, faden)
                if fehler:
                    return {"ok": False, "fehler": fehler}
                nachricht = antwort_bauen(kopf, rumpf, von)
                if paare:
                    del nachricht["To"]
                    nachricht["To"] = _adressliste(paare)
                elif nachricht["To"] is None:
                    return {"ok": False,
                            "fehler": "Auf diese Mail ist keine Antwortadresse zu erkennen - "
                                      "nenne mir den Empfänger."}
                if betreff:
                    del nachricht["Subject"]
                    nachricht["Subject"] = betreff
            else:
                nachricht = EmailMessage()
                if von:
                    nachricht["From"] = von
                if paare:
                    nachricht["To"] = _adressliste(paare)
                nachricht["Subject"] = betreff or "(ohne Betreff)"
                nachricht["Date"] = email.utils.formatdate(localtime=True)
                nachricht["Message-ID"] = _nachricht_id(von)
                nachricht.set_content(rumpf + "\n")
            daten_bytes = nachricht.as_bytes()
            ordner, problem = self._entwurf_ablegen_in(verbindung, daten_bytes)
        except ValueError as problem_wert:
            return {"ok": False, "fehler": "Der Entwurf lässt sich so nicht bauen: %s" % problem_wert}
        except (imaplib.IMAP4.error, ssl.SSLError, OSError) as fehler:
            self.letzter_fehler = str(fehler)
            return {"ok": False, "fehler": "Das Postfach ist nicht erreichbar: %s" % fehler}
        finally:
            self._trennen(verbindung)
        if not ordner:
            self.letzter_fehler = problem
            return {"ok": False, "fehler": problem}
        betreff_gesetzt = str(nachricht["Subject"] or "")
        return {"ok": True, "ordner": imap_utf7_dekodieren(ordner), "betreff": betreff_gesetzt,
                "an": ", ".join(_adresse_anzeigen(n, a) for n, a in paare) if paare
                else _einzeilig(nachricht["To"] or ""),
                "text": "Der Entwurf „%s“ liegt im Ordner %s. Verschickt ist nichts."
                        % (betreff_gesetzt, imap_utf7_dekodieren(ordner))}

    def _entwurf_ablegen_in(self, verbindung, daten_bytes: bytes) -> tuple:
        """Legt die Mail per APPEND mit ``\\\\Draft`` ab: ``(ordnername, fehler)``."""
        try:
            status, daten = verbindung.list()
        except (imaplib.IMAP4.error, OSError):
            status, daten = "NO", []
        kandidaten = entwurf_ordner_kandidaten(daten if status == "OK" else [])
        letzter = "Der Entwürfe-Ordner ließ sich im Postfach nicht finden."
        for roh in kandidaten:
            try:
                status, antwort = verbindung.append(_imap_name_quoten(roh), "(\\Draft)", None,
                                                    daten_bytes)
            except imaplib.IMAP4.abort:
                raise
            except imaplib.IMAP4.error as fehler:
                letzter = "Der Server nimmt keinen Entwurf an: %s" % fehler
                continue
            if status == "OK":
                return roh, ""
            text = " ".join(
                (a.decode("utf-8", errors="replace") if isinstance(a, (bytes, bytearray)) else str(a))
                for a in (antwort or []))[:200]
            letzter = ("Der Entwürfe-Ordner ließ sich nicht beschreiben%s."
                       % (": " + text if text else ""))
        return "", letzter
