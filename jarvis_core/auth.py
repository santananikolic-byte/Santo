# -*- coding: utf-8 -*-
"""Zugang - wer darf mit JARVIS sprechen? Schlüssel, Cookie und Ratenbegrenzung.

Beim ersten Start entsteht ein zufälliger Zugangsschlüssel in ``~/.jarvis/token``
(nur für den eigenen Benutzer lesbar). Alle Schnittstellen unter ``/api/`` verlangen
ihn - als Cookie (der Browser bekommt ihn über den Link von ``./jarvis.sh link``)
oder als Kopfzeile ``X-Jarvis-Token`` (für das Terminal). Das Cookie ist
``HttpOnly`` und ``SameSite=Strict``: Fremde Webseiten können es weder lesen noch
mitschicken. Die Oberfläche selbst enthält keine Daten.
"""

import collections
import hmac
import os
import secrets
import threading
import time
from http.cookies import CookieError, SimpleCookie

COOKIE = "jv_token"
KOPFZEILE = "X-Jarvis-Token"
JAHR = 365 * 24 * 3600


def token_holen(konfig):
    """Liest den Zugangsschlüssel oder legt ihn neu an (Datei mit Rechten 600)."""
    try:
        with open(konfig.token_datei, "r", encoding="utf-8") as f:
            token = f.read().strip()
        if len(token) >= 20:
            return token
    except OSError:
        pass
    token = secrets.token_urlsafe(32)
    os.makedirs(os.path.dirname(konfig.token_datei), exist_ok=True)
    fd = os.open(konfig.token_datei, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(token)
    os.chmod(konfig.token_datei, 0o600)
    return token


class Zugang:
    def __init__(self, konfig):
        self.token = token_holen(konfig)

    def pruefen(self, kopfzeilen):
        """Stimmt der Schlüssel (Kopfzeile oder Cookie)? Vergleich in konstanter Zeit."""
        kandidaten = [kopfzeilen.get(KOPFZEILE) or ""]
        roh = kopfzeilen.get("Cookie")
        if roh:
            try:
                cookie = SimpleCookie()
                cookie.load(roh)
                if COOKIE in cookie:
                    kandidaten.append(cookie[COOKIE].value)
            except CookieError:  # ein kaputtes Cookie ist einfach kein Zugang
                kandidaten.append("")
        return any(k and hmac.compare_digest(k, self.token) for k in kandidaten)

    def passt(self, wert):
        return bool(wert) and hmac.compare_digest(wert, self.token)

    def cookie_kopf(self):
        return "%s=%s; Path=/; HttpOnly; SameSite=Strict; Max-Age=%d" % (COOKIE, self.token, JAHR)

    def link(self, konfig, host=None):
        return "http://%s:%d/?t=%s" % (host or konfig.host, konfig.port, self.token)


class Ratenbegrenzer:
    """Höchstens ``maximum`` Aufrufe je ``sekunden`` und Schlüssel (gleitendes Fenster)."""

    def __init__(self):
        self._fenster = {}
        self._sperre = threading.Lock()

    def erlauben(self, schluessel, maximum, sekunden=60.0):
        """Gibt (erlaubt, Sekunden bis zum nächsten möglichen Aufruf) zurück."""
        jetzt = time.time()
        with self._sperre:
            zeiten = self._fenster.setdefault(schluessel, collections.deque())
            while zeiten and zeiten[0] <= jetzt - sekunden:
                zeiten.popleft()
            if len(zeiten) >= maximum:
                return False, max(1, int(zeiten[0] + sekunden - jetzt) + 1)
            zeiten.append(jetzt)
            return True, 0
