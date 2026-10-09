#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""E-Mail - ungelesene Nachrichten holen, vorsortieren und antworten.

Die Vorsortierung hier ist grob und arbeitet nur mit Wortlisten. Das ist
Absicht: Sie läuft ohne Netz und ohne Kosten und schafft die Vorauswahl. Die
feine Bewertung übernimmt Claude im Briefing, wo er den Zusammenhang kennt.
"""

import email
import email.header
import email.utils
import imaplib
import mimetypes
import os
import smtplib
import ssl
from email.message import EmailMessage

import config

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


class Mail:
    """Liest über IMAP und versendet über SMTP."""

    def __init__(self):
        self.letzter_fehler = ""

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

    def ungelesene(self, limit: int = 15) -> dict:
        """Holt ungelesene Mails und sortiert sie vor - ohne sie als gelesen zu markieren."""
        if not self.lesen_moeglich():
            return {"ok": False,
                    "fehler": "Der Posteingang ist nicht eingerichtet. In der Einrichtung "
                              "IMAP-Server, Benutzer und Passwort hinterlegen."}
        verbindung = None
        try:
            kontext = ssl.create_default_context()
            verbindung = imaplib.IMAP4_SSL(config.IMAP_HOST, config.IMAP_PORT,
                                           ssl_context=kontext)
            verbindung.login(config.IMAP_USER, config.IMAP_PASSWORT)
            verbindung.select("INBOX")
            status, daten = verbindung.search(None, "UNSEEN")
            if status != "OK":
                return {"ok": False, "fehler": "Der Posteingang antwortet nicht wie erwartet."}
            nummern = daten[0].split()[-limit:] if daten and daten[0] else []
            mails = []
            for nummer in reversed(nummern):
                # BODY.PEEK lässt die Mail ungelesen - er soll sie selbst noch sehen.
                status, teil = verbindung.fetch(nummer, "(BODY.PEEK[])")
                if status != "OK" or not teil or not teil[0]:
                    continue
                nachricht = email.message_from_bytes(teil[0][1])
                betreff = kopf_dekodieren(nachricht.get("Subject"))
                absender = kopf_dekodieren(nachricht.get("From"))
                text = klartext_aus_mail(nachricht)
                mails.append({
                    "id": nummer.decode("ascii", errors="replace"),
                    "betreff": betreff or "(ohne Betreff)",
                    "absender": absender,
                    "datum": kopf_dekodieren(nachricht.get("Date")),
                    "auszug": " ".join((text or "").split())[:400],
                    "einstufung": triage(betreff, absender, text),
                })
            return {"ok": True, "anzahl": len(mails), "mails": mails,
                    "wichtig": [m for m in mails if m["einstufung"] == "wichtig"],
                    "spaeter": [m for m in mails if m["einstufung"] == "spaeter"],
                    "rauschen": [m for m in mails if m["einstufung"] == "rauschen"]}
        except (imaplib.IMAP4.error, ssl.SSLError, OSError) as fehler:
            self.letzter_fehler = str(fehler)
            return {"ok": False,
                    "fehler": "Der Posteingang ist nicht erreichbar: %s" % fehler}
        finally:
            if verbindung is not None:
                try:
                    verbindung.close()
                except (imaplib.IMAP4.error, OSError):
                    pass
                try:
                    verbindung.logout()
                except (imaplib.IMAP4.error, OSError):
                    pass

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

    # -- Senden -------------------------------------------------------------

    def senden(self, an: str, betreff: str, text: str, anhaenge=None) -> dict:
        """Verschickt eine Mail über SMTP mit STARTTLS.

        Achtung: Die Freigabe wird **nicht** hier eingeholt, sondern im
        Werkzeugkatalog, bevor diese Methode überhaupt aufgerufen wird.

        ``anhaenge`` ist eine Liste von Dateipfaden. Fehlt eine Datei, geht
        die Mail gar nicht erst raus - eine Rechnungsmail ohne Rechnung wäre
        schlimmer als keine.
        """
        if not self.senden_moeglich():
            return {"ok": False,
                    "fehler": "Der Mailversand ist nicht eingerichtet. In der Einrichtung "
                              "SMTP-Server, Benutzer und Passwort hinterlegen."}
        an = (an or "").strip()
        if "@" not in an:
            return {"ok": False, "fehler": "'%s' ist keine gültige Mailadresse." % an}

        nachricht = EmailMessage()
        nachricht["From"] = config.SMTP_ABSENDER or config.SMTP_USER
        nachricht["To"] = an
        nachricht["Subject"] = betreff or "(ohne Betreff)"
        nachricht["Date"] = email.utils.formatdate(localtime=True)
        nachricht["Message-ID"] = email.utils.make_msgid()
        nachricht.set_content(text or "")

        for anhang in ([anhaenge] if isinstance(anhaenge, str) else (anhaenge or [])):
            anhang = str(anhang)
            try:
                with open(anhang, "rb") as datei:
                    inhalt = datei.read()
            except OSError:
                return {"ok": False,
                        "fehler": "Den Anhang %s finde ich nicht - die Mail ist "
                                  "nicht raus." % os.path.basename(anhang)}
            art = mimetypes.guess_type(anhang)[0] or "application/octet-stream"
            haupttyp, _, untertyp = art.partition("/")
            nachricht.add_attachment(inhalt, maintype=haupttyp, subtype=untertyp,
                                     filename=os.path.basename(anhang))

        try:
            kontext = ssl.create_default_context()
            if int(config.SMTP_PORT) == 465:
                server = smtplib.SMTP_SSL(config.SMTP_HOST, config.SMTP_PORT,
                                          context=kontext, timeout=30)
            else:
                server = smtplib.SMTP(config.SMTP_HOST, config.SMTP_PORT, timeout=30)
                server.starttls(context=kontext)
            with server:
                server.login(config.SMTP_USER, config.SMTP_PASSWORT)
                server.send_message(nachricht)
        except smtplib.SMTPAuthenticationError:
            return {"ok": False,
                    "fehler": "Der Mailserver lehnt Benutzer oder Passwort ab. Bei Gmail "
                              "und ähnlichen Anbietern braucht es ein App-Passwort."}
        except (smtplib.SMTPException, ssl.SSLError, OSError) as fehler:
            return {"ok": False, "fehler": "Die Mail ging nicht raus: %s" % fehler}
        return {"ok": True, "text": "Mail an %s ist raus." % an}
