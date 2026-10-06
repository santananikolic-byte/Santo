#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Telegram - senden, empfangen und Freigaben einholen.

Der wichtigste Teil ist :meth:`Telegram.freigabe_einholen`. Dort gilt eine
Regel ohne Ausnahme: **Timeout, Netzwerkfehler oder ausbleibende Antwort
gelten als Ablehnung.** Nie als Zustimmung. Wer sich nicht meldet, hat nicht
zugestimmt - sonst würde ein Ausfall der Verbindung zum Freibrief.
"""

import json
import os
import select
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

import config

TELEGRAM_BASIS = "https://api.telegram.org"

JA_WOERTER = {"ja", "j", "ok", "okay", "yes", "y", "passt", "mach", "machen",
              "los", "freigabe", "erlaubt", "einverstanden", "jo", "jup", "sicher"}
NEIN_WOERTER = {"nein", "n", "no", "stop", "stopp", "abbrechen", "abbruch",
                "nicht", "lass", "niemals", "nope"}


class Telegram:
    """Anbindung an einen Telegram-Bot. Ohne Token meldet sich alles sauber ab."""

    def __init__(self, token: str = None, chat_id: str = None):
        self.token = (token if token is not None else config.TELEGRAM_BOT_TOKEN) or ""
        self.chat_id = (chat_id if chat_id is not None else config.TELEGRAM_CHAT_ID) or ""
        self._letzte_update_id = 0

    def verfuegbar(self) -> bool:
        """Ist Telegram überhaupt eingerichtet?"""
        return bool(self.token and self.chat_id)

    # -- HTTP-Grundlage -----------------------------------------------------

    def _aufruf(self, methode: str, daten: dict = None, timeout: int = 20) -> dict:
        """Ruft eine Bot-API-Methode auf. Fehler werden als Wörterbuch gemeldet."""
        if not self.token:
            return {"ok": False, "fehler": "Kein Telegram-Token hinterlegt."}
        ziel = "%s/bot%s/%s" % (TELEGRAM_BASIS, self.token, methode)
        koerper = json.dumps(daten or {}).encode("utf-8")
        anfrage = urllib.request.Request(
            ziel, data=koerper, method="POST",
            headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(anfrage, timeout=timeout) as antwort:
                return json.loads(antwort.read().decode("utf-8"))
        except urllib.error.HTTPError as fehler:
            try:
                inhalt = json.loads(fehler.read().decode("utf-8"))
                text = inhalt.get("description", str(fehler))
            except (ValueError, OSError):
                text = str(fehler)
            return {"ok": False, "fehler": "Telegram meldet: %s" % text}
        except (urllib.error.URLError, OSError, ValueError) as fehler:
            return {"ok": False, "fehler": "Telegram nicht erreichbar: %s" % fehler}

    # -- Senden -------------------------------------------------------------

    def senden(self, text: str, chat_id: str = "") -> dict:
        """Schickt eine Textnachricht."""
        ziel_chat = chat_id or self.chat_id
        if not self.verfuegbar() and not chat_id:
            return {"ok": False, "fehler": "Telegram ist nicht eingerichtet."}
        antwort = self._aufruf("sendMessage",
                               {"chat_id": ziel_chat, "text": (text or "")[:4000]})
        if antwort.get("ok"):
            return {"ok": True, "text": "Nachricht ist raus."}
        return {"ok": False, "fehler": antwort.get("fehler", "Senden fehlgeschlagen.")}

    def datei_senden(self, pfad: str, methode: str = "sendVoice",
                     feld: str = "voice", chat_id: str = "") -> dict:
        """Schickt eine Datei (Sprachnachricht, Bild, Dokument) als multipart."""
        ziel_chat = chat_id or self.chat_id
        if not self.token or not ziel_chat:
            return {"ok": False, "fehler": "Telegram ist nicht eingerichtet."}
        if not os.path.exists(pfad):
            return {"ok": False, "fehler": "Die Datei %s gibt es nicht." % pfad}
        grenze = "----jarvis%d" % int(time.time() * 1000)
        try:
            with open(pfad, "rb") as datei:
                inhalt = datei.read()
        except OSError as fehler:
            return {"ok": False, "fehler": "Datei nicht lesbar: %s" % fehler}

        teile = []
        teile.append(("--%s\r\nContent-Disposition: form-data; name=\"chat_id\"\r\n\r\n%s\r\n"
                      % (grenze, ziel_chat)).encode("utf-8"))
        teile.append(("--%s\r\nContent-Disposition: form-data; name=\"%s\"; filename=\"%s\"\r\n"
                      "Content-Type: application/octet-stream\r\n\r\n"
                      % (grenze, feld, os.path.basename(pfad))).encode("utf-8"))
        teile.append(inhalt)
        teile.append(("\r\n--%s--\r\n" % grenze).encode("utf-8"))
        koerper = b"".join(teile)

        anfrage = urllib.request.Request(
            "%s/bot%s/%s" % (TELEGRAM_BASIS, self.token, methode), data=koerper,
            method="POST",
            headers={"Content-Type": "multipart/form-data; boundary=%s" % grenze})
        try:
            with urllib.request.urlopen(anfrage, timeout=60) as antwort:
                ergebnis = json.loads(antwort.read().decode("utf-8"))
            if ergebnis.get("ok"):
                return {"ok": True, "text": "Datei ist raus."}
            return {"ok": False, "fehler": str(ergebnis.get("description", "unbekannt"))}
        except (urllib.error.URLError, OSError, ValueError) as fehler:
            return {"ok": False, "fehler": "Senden fehlgeschlagen: %s" % fehler}

    # -- Empfangen ----------------------------------------------------------

    def nachrichten_holen(self, timeout: int = 25, ziel_verzeichnis: str = "") -> list:
        """Holt neue Nachrichten. Sprachnachrichten werden heruntergeladen."""
        if not self.verfuegbar():
            return []
        antwort = self._aufruf("getUpdates",
                               {"offset": self._letzte_update_id + 1,
                                "timeout": timeout, "allowed_updates": ["message"]},
                               timeout=timeout + 10)
        if not antwort.get("ok"):
            return []
        gesammelt = []
        for eintrag in antwort.get("result", []):
            self._letzte_update_id = max(self._letzte_update_id, eintrag.get("update_id", 0))
            nachricht = eintrag.get("message") or {}
            if not nachricht:
                continue
            chat = str((nachricht.get("chat") or {}).get("id", ""))
            if self.chat_id and chat != str(self.chat_id):
                continue  # Fremde Chats werden ignoriert.
            datensatz = {"update_id": eintrag.get("update_id"), "chat_id": chat,
                         "text": nachricht.get("text", ""), "sprachdatei": ""}
            sprache = nachricht.get("voice") or nachricht.get("audio")
            if sprache and sprache.get("file_id"):
                datensatz["sprachdatei"] = self.datei_herunterladen(
                    sprache["file_id"], ziel_verzeichnis)
            gesammelt.append(datensatz)
        return gesammelt

    def datei_herunterladen(self, file_id: str, ziel_verzeichnis: str = "") -> str:
        """Lädt eine Telegram-Datei herunter und gibt den lokalen Pfad zurück."""
        antwort = self._aufruf("getFile", {"file_id": file_id})
        if not antwort.get("ok"):
            return ""
        pfad = (antwort.get("result") or {}).get("file_path", "")
        if not pfad:
            return ""
        verzeichnis = ziel_verzeichnis or str(config.BASIS / "sprachnachrichten")
        try:
            os.makedirs(verzeichnis, exist_ok=True)
            ziel = os.path.join(verzeichnis, os.path.basename(pfad))
            quelle = "%s/file/bot%s/%s" % (TELEGRAM_BASIS, self.token, pfad)
            with urllib.request.urlopen(quelle, timeout=60) as antwort_datei:
                with open(ziel, "wb") as datei:
                    datei.write(antwort_datei.read())
            return ziel
        except (urllib.error.URLError, OSError) as fehler:
            print("[telegram] Download fehlgeschlagen: %s" % fehler)
            return ""

    # -- Freigaben ----------------------------------------------------------

    def freigabe_einholen(self, aktion: str, details: str = "", timeout: int = None) -> dict:
        """Fragt vor einer Aktion mit Außenwirkung nach ausdrücklicher Zustimmung.

        Rückgabe enthält ``erlaubt``. Ohne klares Ja ist ``erlaubt`` False -
        auch bei Timeout, Netzwerkfehler oder unverständlicher Antwort.
        """
        timeout = int(timeout if timeout is not None else config.FREIGABE_TIMEOUT)
        frage = ("Jarvis fragt um Freigabe.\n\nAktion: %s\n%s\n\n"
                 "Antworte mit JA oder NEIN. Ohne Antwort in %d Sekunden "
                 "führe ich nichts aus." % (aktion, details or "", timeout))

        if self.verfuegbar():
            ergebnis = self._freigabe_ueber_telegram(frage, timeout)
            if ergebnis is not None:
                return ergebnis
            # Telegram ausgefallen - das Terminal übernimmt, statt einfach
            # durchzuwinken.
            print("[freigabe] Telegram nicht erreichbar, ich frage im Terminal.")

        return self._freigabe_im_terminal(aktion, details, timeout)

    def _freigabe_ueber_telegram(self, frage: str, timeout: int):
        """Freigabe per Telegram. ``None`` heißt: Kanal fällt aus, bitte Terminal."""
        gesendet = self.senden(frage)
        if not gesendet.get("ok"):
            return None

        ende = time.time() + timeout
        while time.time() < ende:
            rest = max(1, min(20, int(ende - time.time())))
            antwort = self._aufruf(
                "getUpdates",
                {"offset": self._letzte_update_id + 1, "timeout": rest,
                 "allowed_updates": ["message"]},
                timeout=rest + 10)
            if not antwort.get("ok"):
                time.sleep(1)
                continue
            for eintrag in antwort.get("result", []):
                self._letzte_update_id = max(self._letzte_update_id,
                                             eintrag.get("update_id", 0))
                nachricht = eintrag.get("message") or {}
                chat = str((nachricht.get("chat") or {}).get("id", ""))
                if self.chat_id and chat != str(self.chat_id):
                    continue
                wort = (nachricht.get("text") or "").strip().lower().strip(".!? ")
                if wort in JA_WOERTER:
                    self.senden("Verstanden, ich mache es.")
                    return {"erlaubt": True, "kanal": "telegram", "grund": "Freigabe erteilt"}
                if wort in NEIN_WOERTER:
                    self.senden("Alles klar, ich lasse es.")
                    return {"erlaubt": False, "kanal": "telegram", "grund": "abgelehnt"}
                if wort:
                    self.senden("Bitte nur JA oder NEIN.")
        self.senden("Keine Antwort bekommen - ich habe nichts ausgeführt.")
        return {"erlaubt": False, "kanal": "telegram",
                "grund": "keine Antwort innerhalb von %d Sekunden" % timeout}

    def _freigabe_im_terminal(self, aktion: str, details: str, timeout: int) -> dict:
        """Rückfallebene: Nachfrage im Terminal, ebenfalls mit Zeitgrenze."""
        if not sys.stdin or not sys.stdin.isatty():
            return {"erlaubt": False, "kanal": "keiner",
                    "grund": "Kein Freigabekanal verfügbar - deshalb nicht ausgeführt."}
        print("\n--- FREIGABE NÖTIG ---")
        print("Aktion : %s" % aktion)
        if details:
            print("Details: %s" % details)
        print("Mit ja bestätigen, alles andere bricht ab (%d Sekunden Zeit)." % timeout)
        sys.stdout.write("> ")
        sys.stdout.flush()
        try:
            bereit, _, _ = select.select([sys.stdin], [], [], timeout)
        except (OSError, ValueError):
            bereit = []
        if not bereit:
            print("\nKeine Antwort - ich führe nichts aus.")
            return {"erlaubt": False, "kanal": "terminal",
                    "grund": "keine Antwort innerhalb von %d Sekunden" % timeout}
        eingabe = sys.stdin.readline().strip().lower().strip(".!? ")
        if eingabe in JA_WOERTER:
            return {"erlaubt": True, "kanal": "terminal", "grund": "Freigabe erteilt"}
        return {"erlaubt": False, "kanal": "terminal", "grund": "abgelehnt"}


class TelegramFreigabe:
    """Freigabeweg über Telegram - für Bitten, die vom Handy kommen."""

    def __init__(self, telegram):
        self.telegram = telegram

    def anfordern(self, aktion: str, details: str = "") -> dict:
        return self.telegram.freigabe_einholen(aktion, details)
