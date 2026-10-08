#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Kleiner WebSocket-Client (RFC 6455) aus der Standardbibliothek.

Jarvis braucht ihn für die Live-Mitschrift beim Telefonassistenten (Retell
schickt sie über eine Verbindung, die der Mac selbst aufmacht). Es gibt keinen
eingehenden Zugang zum Mac - dieser Client wählt sich immer nur aus.

Was er kann:

* ``ws://`` und ``wss://`` (TLS mit geprüftem Zertifikat), Kopfzeilen wie
  ``Authorization`` werden mitgeschickt.
* Handschlag mit Prüfung von ``Sec-WebSocket-Accept`` - ein Server, der nicht
  wirklich WebSocket spricht, wird abgewiesen.
* Alle Client-Rahmen sind maskiert, auch Pong und Close.
* Ping wird mit einem Pong beantwortet, Fragmente werden zusammengesetzt
  (auch wenn ein Ping dazwischenkommt), die erweiterten Längen 126 und 127
  werden gelesen und geschrieben.
* Close beendet den Erzeuger ``nachrichten()``; Code und Grund bleiben in
  ``schliess_code`` und ``schliess_grund`` stehen.
* Zeitgrenzen: ``timeout`` gilt fürs Verbinden, den Handschlag und jedes
  Warten. Bleibt es länger still, schickt der Client einmal einen Ping; kommt
  auch darauf nichts, bricht er mit ``WebSocketFehler`` ab. Zusätzlich gibt es
  eine Gesamtfrist je ``nachrichten(frist=...)``.
* Jeder Fehler kommt als ``WebSocketFehler`` mit deutscher Meldung. Die
  Meldungen nennen nie Kopfzeilen, Schlüssel oder die Parameter der Adresse.
* Die Verbindung ist einspeisbar: ``verbinden(host, port, tls) -> socket``.
  So laufen Prüfungen mit ``socket.socketpair()`` ohne Netz.

Bewusste Nachsicht: Maskierte Rahmen vom Server und nicht minimal kodierte
Längen werden angenommen (der RFC verbietet sie dem Sender, der Empfänger
kann sie aber gefahrlos lesen). Erweiterungsbits, unbekannte Opcodes,
zerrissene Fragmentfolgen, zu große Nachrichten und ungültiges UTF-8 führen
dagegen zum Abbruch mit Close-Code 1002, 1009 bzw. 1007.

``netzsocket_selbsttest()`` spielt alle Fälle gegen einen kleinen Server auf
127.0.0.1 durch (ohne Internet).
"""

import base64
import hashlib
import os
import re
import socket
import ssl
import struct
import threading
import time
import urllib.parse

# Feste Zeichenfolge aus RFC 6455, Abschnitt 1.3 (gehört in die Accept-Berechnung).
NETZSOCKET_GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"
# Größte Nachricht (alle Fragmente zusammen), die der Client annimmt.
NETZSOCKET_MAX_NACHRICHT = 8 * 1024 * 1024
# Größter Antwortkopf beim Handschlag.
NETZSOCKET_MAX_KOPF = 65536
# So lange wartet schliessen() höchstens auf die Antwort des Servers (Sekunden).
NETZSOCKET_SCHLIESSWARTE = 2.0
# Kopfzeilen, die der Client selbst setzt und die der Aufrufer nicht ändern darf.
NETZSOCKET_RESERVIERT = ("host", "upgrade", "connection", "sec-websocket-key",
                         "sec-websocket-version", "sec-websocket-extensions",
                         "sec-websocket-protocol")
_NETZSOCKET_NAME = re.compile(r"^[!#$%&'*+.^_`|~0-9A-Za-z-]+$")
_NETZSOCKET_ZIEL_SICHER = "/%:@!$&'()*+,;=-._~"


class WebSocketFehler(Exception):
    """Alles, was beim WebSocket schiefgehen kann - die Meldung ist deutsch."""


class WebSocketLeser:
    """Eine WebSocket-Verbindung zum Lesen (und bei Bedarf Schreiben).

    ``WebSocketLeser(url, kopfzeilen=None, timeout=30, verbinden=None)`` baut die
    Verbindung auf und macht den Handschlag; Fehler dabei sind ``WebSocketFehler``.
    ``timeout`` gilt für Verbinden, Handschlag und jedes Warten (``None`` = ohne
    Grenze). ``verbinden(host, port, tls)`` liefert einen verbundenen Socket und
    ist für Prüfungen austauschbar; bei ``tls`` muss er selbst verschlüsseln.
    ``max_nachricht`` begrenzt die Größe einer Nachricht in Bytes.

        ws = WebSocketLeser("wss://host/pfad", {"Authorization": "Bearer ..."})
        for text in ws.nachrichten():
            ...
        ws.schliessen()
    """

    def __init__(self, url, kopfzeilen=None, timeout=30, verbinden=None, max_nachricht=None):
        if timeout is not None and not timeout > 0:
            raise WebSocketFehler("Die Zeitgrenze muss größer als 0 Sekunden sein.")
        self.timeout = timeout
        self.max_nachricht = int(max_nachricht or NETZSOCKET_MAX_NACHRICHT)
        self.schliess_code = None
        self.schliess_grund = ""
        self._sock = None
        self._puffer = bytearray()
        self._fertig = threading.Event()
        self._sende_sperre = threading.Lock()
        self._lese_sperre = threading.Lock()
        self._close_gesendet = False
        self._ich_schliesse = False
        host, port, tls, ziel, host_kopf = self._adresse_zerlegen(url)
        zeilen = self._kopfzeilen_pruefen(kopfzeilen)
        self._host = host
        sock = self._verbindung_aufbauen(verbinden or self._verbinden_standard, host, port, tls)
        self._sock = sock
        try:
            self._handschlag(ziel, host_kopf, zeilen)
        except BaseException:
            self._zumachen()
            raise

    # ------------------------------------------------------------ Aufbau
    @staticmethod
    def _adresse_zerlegen(url):
        """Zerlegt die Adresse in (host, port, tls, anfrageziel, host-kopf)."""
        if not isinstance(url, str) or not url.strip():
            raise WebSocketFehler("Es fehlt die Adresse der WebSocket-Verbindung.")
        try:
            teile = urllib.parse.urlsplit(url.strip())
            port = teile.port
            host = teile.hostname
        except ValueError:
            raise WebSocketFehler("Die Adresse der WebSocket-Verbindung ist ungültig.")
        if teile.scheme not in ("ws", "wss"):
            raise WebSocketFehler("Die Adresse muss mit ws:// oder wss:// beginnen.")
        if not host:
            raise WebSocketFehler("In der Adresse fehlt der Rechnername.")
        tls = teile.scheme == "wss"
        standard = 443 if tls else 80
        ziel = urllib.parse.quote(teile.path or "/", safe=_NETZSOCKET_ZIEL_SICHER)
        if teile.query:
            ziel += "?" + urllib.parse.quote(teile.query, safe=_NETZSOCKET_ZIEL_SICHER + "?")
        host_kopf = "[%s]" % host if ":" in host else host
        if port is not None and port != standard:
            host_kopf += ":%d" % port
        return host, port or standard, tls, ziel, host_kopf

    @staticmethod
    def _kopfzeilen_pruefen(kopfzeilen):
        """Prüft die Kopfzeilen des Aufrufers und liefert fertige Zeilen."""
        zeilen = []
        gesehen = set()
        for name, wert in (kopfzeilen or {}).items():
            name, wert = str(name), str(wert)
            if not _NETZSOCKET_NAME.match(name):
                raise WebSocketFehler("Der Name einer Kopfzeile ist ungültig.")
            if name.lower() in NETZSOCKET_RESERVIERT:
                raise WebSocketFehler("Die Kopfzeile %s setzt der Client selbst." % name)
            if (not wert.isascii()) or any(z in wert for z in "\r\n\x00"):
                raise WebSocketFehler("Der Wert der Kopfzeile %s ist ungültig." % name)
            gesehen.add(name.lower())
            zeilen.append("%s: %s" % (name, wert))
        if "user-agent" not in gesehen:  # manche Vorschaltdienste weisen Anfragen ohne Kennung ab
            zeilen.append("User-Agent: Jarvis-Netzsocket/1.0")
        return zeilen

    def _verbinden_standard(self, host, port, tls):
        """Echte Verbindung (mit TLS bei wss)."""
        try:
            roh = socket.create_connection((host, port), timeout=self.timeout)
        except socket.gaierror:
            raise WebSocketFehler("Den Rechnernamen %s finde ich nicht." % host)
        except socket.timeout:
            raise WebSocketFehler("Zeitüberschreitung beim Verbinden mit %s." % host)
        except OSError as fehler:
            raise WebSocketFehler("Die Verbindung zu %s ist nicht möglich (%s)."
                                  % (host, fehler.strerror or type(fehler).__name__))
        if not tls:
            return roh
        try:
            return ssl.create_default_context().wrap_socket(roh, server_hostname=host)
        except ssl.SSLCertVerificationError:
            roh.close()
            raise WebSocketFehler("Dem Zertifikat von %s traue ich nicht." % host)
        except socket.timeout:
            roh.close()
            raise WebSocketFehler("Zeitüberschreitung bei der verschlüsselten Verbindung mit %s." % host)
        except (ssl.SSLError, OSError):
            roh.close()
            raise WebSocketFehler("Die verschlüsselte Verbindung zu %s kommt nicht zustande." % host)

    @staticmethod
    def _verbindung_aufbauen(verbinden, host, port, tls):
        try:
            sock = verbinden(host, port, tls)
        except WebSocketFehler:
            raise
        except socket.timeout:
            raise WebSocketFehler("Zeitüberschreitung beim Verbinden mit %s." % host)
        except OSError as fehler:
            raise WebSocketFehler("Die Verbindung zu %s ist nicht möglich (%s)."
                                  % (host, getattr(fehler, "strerror", None) or type(fehler).__name__))
        if sock is None:
            raise WebSocketFehler("Die Verbindung zu %s ist nicht möglich." % host)
        return sock

    def _handschlag(self, ziel, host_kopf, zeilen):
        schluessel = base64.b64encode(os.urandom(16)).decode("ascii")
        anfrage = ["GET %s HTTP/1.1" % ziel, "Host: %s" % host_kopf, "Upgrade: websocket",
                   "Connection: Upgrade", "Sec-WebSocket-Key: " + schluessel,
                   "Sec-WebSocket-Version: 13"] + zeilen
        frist = None if self.timeout is None else time.monotonic() + self.timeout
        try:
            self._sock.sendall(("\r\n".join(anfrage) + "\r\n\r\n").encode("ascii"))
        except socket.timeout:
            raise WebSocketFehler("Zeitüberschreitung beim Handschlag.")
        except OSError:
            raise WebSocketFehler("Handschlag nicht möglich: Die Verbindung ist abgebrochen.")
        kopf = bytearray()
        while b"\r\n\r\n" not in kopf:
            if len(kopf) > NETZSOCKET_MAX_KOPF:
                raise WebSocketFehler("Handschlag abgelehnt: Die Antwort des Servers ist zu lang.")
            try:
                stueck = self._empfangen(4096, frist)
            except socket.timeout:
                raise WebSocketFehler("Zeitüberschreitung beim Handschlag.")
            kopf += stueck
        kopf, _, rest = bytes(kopf).partition(b"\r\n\r\n")
        self._puffer += rest  # was nach dem Kopf schon da ist, gehört zu den Rahmen
        zeilen = kopf.decode("latin-1").split("\r\n")
        status = zeilen[0].split(" ", 2)
        if len(status) < 2 or not status[0].startswith("HTTP/1.") or not status[1].isdigit():
            raise WebSocketFehler("Handschlag abgelehnt: Das ist keine gültige HTTP-Antwort.")
        code = int(status[1])
        if code != 101:
            raise WebSocketFehler(self._handschlag_meldung(code))
        antwort = {}
        for zeile in zeilen[1:]:
            name, doppelpunkt, wert = zeile.partition(":")
            if doppelpunkt:
                name = name.strip().lower()
                antwort[name] = (antwort[name] + ", " if name in antwort else "") + wert.strip()
        if antwort.get("upgrade", "").lower() != "websocket":
            raise WebSocketFehler("Handschlag abgelehnt: Der Server wechselt nicht zu WebSocket.")
        if "upgrade" not in [t.strip().lower() for t in antwort.get("connection", "").split(",")]:
            raise WebSocketFehler("Handschlag abgelehnt: Der Server bestätigt den Wechsel nicht.")
        erwartet = base64.b64encode(hashlib.sha1(
            (schluessel + NETZSOCKET_GUID).encode("ascii")).digest()).decode("ascii")
        if antwort.get("sec-websocket-accept", "") != erwartet:
            raise WebSocketFehler("Handschlag abgelehnt: Sec-WebSocket-Accept stimmt nicht - "
                                  "das ist kein gültiger WebSocket-Server.")
        if "sec-websocket-extensions" in antwort or "sec-websocket-protocol" in antwort:
            raise WebSocketFehler("Handschlag abgelehnt: Der Server will eine Erweiterung, "
                                  "die nicht vereinbart wurde.")

    @staticmethod
    def _handschlag_meldung(code):
        if code in (401, 403):
            return ("Handschlag abgelehnt: Der Server verweigert den Zugang (HTTP %d) - "
                    "Schlüssel und Berechtigung prüfen." % code)
        if code == 404:
            return "Handschlag abgelehnt: Diese Adresse gibt es dort nicht (HTTP 404)."
        if code == 429:
            return "Handschlag abgelehnt: Zu viele Anfragen (HTTP 429)."
        if 300 <= code < 400:
            return "Handschlag abgelehnt: Der Server leitet um (HTTP %d); Umleitungen folge ich nicht." % code
        if code >= 500:
            return "Handschlag abgelehnt: Der Server hat einen Fehler (HTTP %d)." % code
        return "Handschlag abgelehnt: Der Server antwortet mit HTTP %d statt 101." % code

    # ------------------------------------------------------------ Lesen
    @property
    def offen(self):
        return not self._fertig.is_set()

    def _empfangen(self, groesse, frist):
        """Ein Stück vom Socket. ``socket.timeout`` bei Stille, sonst WebSocketFehler."""
        grenze = self.timeout
        if frist is not None:
            rest = frist - time.monotonic()
            if rest <= 0:
                raise socket.timeout()
            grenze = rest if grenze is None else min(grenze, rest)
        try:
            self._sock.settimeout(grenze)
        except (OSError, AttributeError):
            pass
        try:
            stueck = self._sock.recv(groesse)
        except socket.timeout:
            raise
        except OSError:
            raise WebSocketFehler("Die Verbindung ist abgebrochen.")
        if not stueck:
            raise WebSocketFehler("Der Server hat die Verbindung beendet, ohne sich zu verabschieden.")
        return stueck

    def _bytes_holen(self, n, frist):
        """Genau ``n`` Bytes. Bei Stille bleibt das Gelesene im Puffer (Wiederaufnahme möglich)."""
        while len(self._puffer) < n:
            fehlt = n - len(self._puffer)
            self._puffer += self._empfangen(min(max(fehlt, 4096), 1 << 20), frist)
        daten = bytes(self._puffer[:n])
        del self._puffer[:n]
        return daten

    def _kopf_holen(self, frist):
        """Die ersten zwei Bytes eines Rahmens. Bei Stille: einmal anpingen, dann aufgeben."""
        stille = 0
        while True:
            try:
                return self._bytes_holen(2, frist)
            except socket.timeout:
                if frist is not None and time.monotonic() >= frist:
                    raise WebSocketFehler("Die Zeitgrenze für das Warten auf Nachrichten ist erreicht.")
                if stille or self._close_gesendet:
                    raise WebSocketFehler("Der Server antwortet nicht mehr (Zeitüberschreitung).")
                stille += 1
                self.ping(b"jarvis")

    def _rahmen_lesen(self, frist):
        """Ein Rahmen als (fin, opcode, nutzlast), oder ``None`` wenn schon zu."""
        with self._lese_sperre:
            if self._fertig.is_set():
                return None
            b1, b2 = self._kopf_holen(frist)
            try:
                fin, opcode, laenge = bool(b1 & 0x80), b1 & 0x0F, b2 & 0x7F
                if b1 & 0x70:
                    self._protokollfehler("Der Server benutzt Erweiterungen, die nicht vereinbart wurden.")
                if laenge == 126:
                    laenge = struct.unpack("!H", self._bytes_holen(2, frist))[0]
                elif laenge == 127:
                    laenge = struct.unpack("!Q", self._bytes_holen(8, frist))[0]
                    if laenge >> 63:
                        self._protokollfehler("Der Server schickt eine ungültige Rahmenlänge.")
                if opcode & 0x8 and (not fin or laenge > 125):
                    self._protokollfehler("Der Server schickt einen ungültigen Steuerrahmen.")
                if laenge > self.max_nachricht:
                    self._protokollfehler("Der Server schickt eine zu große Nachricht.", 1009)
                maske = self._bytes_holen(4, frist) if b2 & 0x80 else None
                nutzlast = self._bytes_holen(laenge, frist)
            except socket.timeout:
                if frist is not None and time.monotonic() >= frist:
                    raise WebSocketFehler("Die Zeitgrenze für das Warten auf Nachrichten ist erreicht.")
                raise WebSocketFehler("Der Server hat einen Rahmen nicht zu Ende gesendet (Zeitüberschreitung).")
            if maske:
                nutzlast = self._maskieren(nutzlast, maske)
            return fin, opcode, nutzlast

    def nachrichten_roh(self, frist=None):
        """Erzeugt ``(art, daten)``: ``'text'`` mit str oder ``'binaer'`` mit bytes.

        Beantwortet Ping, setzt Fragmente zusammen und endet beim Close des Servers.
        ``frist`` ist die Gesamtdauer in Sekunden; danach ``WebSocketFehler``.
        """
        ende = None if frist is None else time.monotonic() + frist
        art, teile, gesamt = None, [], 0
        while True:
            try:
                rahmen = self._rahmen_lesen(ende)
            except WebSocketFehler:
                self._zumachen()
                if self._ich_schliesse:
                    return  # selbst geschlossen: kein Fehler
                raise
            if rahmen is None:
                return
            fin, opcode, nutzlast = rahmen
            if opcode == 0x8:  # Close
                self._close_empfangen(nutzlast)
                return
            if opcode == 0x9:  # Ping -> maskiertes Pong mit denselben Daten
                if not self._close_gesendet:
                    self._senden(0xA, nutzlast)
                continue
            if opcode == 0xA:  # Pong: nichts zu tun
                continue
            if opcode not in (0x0, 0x1, 0x2):
                self._protokollfehler("Der Server benutzt einen unbekannten Rahmentyp.")
            if self._close_gesendet:
                continue  # wir haben schon Close geschickt: Nachrichten verfallen
            if opcode == 0x0:
                if art is None:
                    self._protokollfehler("Der Server schickt ein Fragment ohne Anfang.")
            elif art is not None:
                self._protokollfehler("Der Server fängt eine neue Nachricht an, obwohl die alte nicht zu Ende ist.")
            else:
                art, teile, gesamt = ("text" if opcode == 0x1 else "binaer"), [], 0
            gesamt += len(nutzlast)
            if gesamt > self.max_nachricht:
                self._protokollfehler("Der Server schickt eine zu große Nachricht.", 1009)
            teile.append(nutzlast)
            if not fin:
                continue
            daten = b"".join(teile)
            fertig_art, art, teile, gesamt = art, None, [], 0
            if fertig_art == "text":
                try:
                    daten = daten.decode("utf-8")
                except UnicodeDecodeError:
                    self._protokollfehler("Der Server schickt Text, der kein gültiges UTF-8 ist.", 1007)
            yield fertig_art, daten

    def nachrichten(self, frist=None):
        """Erzeugt die Textnachrichten (str). Binärrahmen werden übersprungen.

        Beantwortet Ping, setzt Fragmente zusammen und endet beim Close des Servers.
        ``frist`` ist die Gesamtdauer in Sekunden; danach ``WebSocketFehler``.
        """
        for art, daten in self.nachrichten_roh(frist):
            if art == "text":
                yield daten

    # ------------------------------------------------------------ Schreiben
    @staticmethod
    def _maskieren(daten, maske):
        """XOR mit der 4-Byte-Maske (gilt zum Maskieren wie zum Entmaskieren)."""
        n = len(daten)
        if not n:
            return b""
        schluessel = (maske * (n // 4 + 1))[:n]
        return (int.from_bytes(daten, "big") ^ int.from_bytes(schluessel, "big")).to_bytes(n, "big")

    def _senden(self, opcode, nutzlast=b""):
        """Schickt einen vollständigen, MASKIERTEN Rahmen."""
        n = len(nutzlast)
        kopf = bytearray([0x80 | opcode])
        if n < 126:
            kopf.append(0x80 | n)
        elif n < 65536:
            kopf.append(0x80 | 126)
            kopf += struct.pack("!H", n)
        else:
            kopf.append(0x80 | 127)
            kopf += struct.pack("!Q", n)
        maske = os.urandom(4)
        rahmen = bytes(kopf) + maske + self._maskieren(nutzlast, maske)
        with self._sende_sperre:
            if self._fertig.is_set():
                raise WebSocketFehler("Die Verbindung ist schon geschlossen.")
            try:
                self._sock.sendall(rahmen)
            except socket.timeout:
                raise WebSocketFehler("Zeitüberschreitung beim Senden.")
            except OSError:
                raise WebSocketFehler("Senden nicht möglich: Die Verbindung ist abgebrochen.")

    def senden(self, daten):
        """Schickt eine Nachricht: ``str`` als Text, ``bytes`` als Binärrahmen."""
        if isinstance(daten, str):
            self._senden(0x1, daten.encode("utf-8"))
        else:
            self._senden(0x2, bytes(daten))

    def ping(self, daten=b""):
        """Schickt einen Ping (höchstens 125 Bytes); der Server muss mit Pong antworten."""
        daten = bytes(daten)
        if len(daten) > 125:
            raise WebSocketFehler("Die Daten eines Pings dürfen höchstens 125 Bytes lang sein.")
        self._senden(0x9, daten)

    # ------------------------------------------------------------ Ende
    def _close_senden(self, code=1000, grund=""):
        """Schickt Close (einmal). Fehler dabei sind egal - wir wollen ja ohnehin zu."""
        if self._close_gesendet or self._fertig.is_set():
            return
        self._close_gesendet = True
        nutzlast = b"" if code is None else struct.pack("!H", int(code)) + str(grund).encode("utf-8")[:123]
        try:
            self._senden(0x8, nutzlast)
        except WebSocketFehler:
            pass

    def _close_empfangen(self, nutzlast):
        """Der Server hat Close geschickt: merken, bestätigen, zumachen."""
        if len(nutzlast) >= 2:
            self.schliess_code = struct.unpack("!H", nutzlast[:2])[0]
            self.schliess_grund = nutzlast[2:].decode("utf-8", "replace")
        if not self._close_gesendet:
            self._close_senden(self.schliess_code if len(nutzlast) >= 2 and 1000 <= self.schliess_code < 5000
                               and self.schliess_code not in (1004, 1005, 1006, 1015) else None)
        self._zumachen()

    def _protokollfehler(self, text, code=1002):
        """Der Server verstößt gegen das Protokoll: Close mit Code schicken, zumachen, melden."""
        self._close_senden(code)
        self._zumachen()
        raise WebSocketFehler(text)

    def _zumachen(self):
        """Socket zu und alle Wartenden wecken (mehrfach aufrufbar)."""
        if self._fertig.is_set():
            return
        self._fertig.set()
        sock = self._sock
        if sock is None:
            return
        for aktion in (lambda: sock.shutdown(socket.SHUT_RDWR), sock.close):
            try:
                aktion()
            except Exception:
                pass

    def _auf_close_warten(self):
        """Liest und verwirft Rahmen, bis der Server Close bestätigt oder die Wartezeit um ist."""
        warte = NETZSOCKET_SCHLIESSWARTE if self.timeout is None else min(self.timeout, NETZSOCKET_SCHLIESSWARTE)
        frist = time.monotonic() + warte
        try:
            while True:
                rahmen = self._rahmen_lesen(frist)
                if rahmen is None or rahmen[1] == 0x8:
                    if rahmen is not None and len(rahmen[2]) >= 2:
                        self.schliess_code = struct.unpack("!H", rahmen[2][:2])[0]
                        self.schliess_grund = rahmen[2][2:].decode("utf-8", "replace")
                    return
        except (WebSocketFehler, OSError):
            return

    def schliessen(self, code=1000, grund=""):
        """Schickt einen maskierten Close-Rahmen, wartet kurz auf die Antwort und macht zu.

        Darf auch aus einem anderen Faden kommen, während ``nachrichten()`` liest:
        dann beendet sich der Erzeuger ohne Fehler.
        """
        if self._fertig.is_set():
            return
        self._ich_schliesse = True
        self._close_senden(code, grund)
        if self._lese_sperre.acquire(False):  # niemand liest gerade: Antwort selbst abwarten
            try:
                self._auf_close_warten()
            finally:
                self._lese_sperre.release()
        else:  # ein Leser läuft: er sieht die Antwort und meldet sich über _fertig
            self._fertig.wait(NETZSOCKET_SCHLIESSWARTE)
        self._zumachen()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.schliessen()
        return False


def netzsocket_selbsttest():
    """Spielt alle Fälle gegen einen kleinen WebSocket-Server auf 127.0.0.1 durch.

    Kein Internet nötig, dauert unter zwei Sekunden. Liefert eine Liste von
    ``(Fall, bestanden, Einzelheit)``; alles bestanden, wenn jedes ``bestanden`` wahr ist.
    """
    ergebnisse = []

    class Gegenstelle:
        """Die Serverseite eines Falls: liest Client-Rahmen, schreibt Server-Rahmen."""

        def __init__(self, conn):
            self.conn = conn
            self.puffer = b""
            self.kopf = {}

        def genau(self, n):
            while len(self.puffer) < n:
                stueck = self.conn.recv(65536)
                if not stueck:
                    raise EOFError("Client weg")
                self.puffer += stueck
            daten, self.puffer = self.puffer[:n], self.puffer[n:]
            return daten

        def begruessen(self, accept_falsch=False, status="101 Switching Protocols"):
            while b"\r\n\r\n" not in self.puffer:
                stueck = self.conn.recv(4096)
                if not stueck:
                    raise EOFError("Client weg")
                self.puffer += stueck
            kopf, _, self.puffer = self.puffer.partition(b"\r\n\r\n")
            zeilen = kopf.decode("latin-1").split("\r\n")
            self.kopf = {"_anfrage": zeilen[0]}
            for zeile in zeilen[1:]:
                name, _, wert = zeile.partition(":")
                self.kopf[name.strip().lower()] = wert.strip()
            accept = base64.b64encode(hashlib.sha1(
                (self.kopf.get("sec-websocket-key", "") + NETZSOCKET_GUID).encode()).digest())
            if accept_falsch:
                accept = base64.b64encode(hashlib.sha1(b"falsch").digest())
            self.conn.sendall(b"HTTP/1.1 " + status.encode() + b"\r\nUpgrade: websocket\r\n"
                              b"Connection: Upgrade\r\nSec-WebSocket-Accept: " + accept + b"\r\n\r\n")

        def senden(self, opcode, daten=b"", fin=True, rsv=0):
            n = len(daten)
            kopf = bytes([(0x80 if fin else 0) | rsv | opcode])
            if n < 126:
                kopf += bytes([n])
            elif n < 65536:
                kopf += bytes([126]) + struct.pack("!H", n)
            else:
                kopf += bytes([127]) + struct.pack("!Q", n)
            self.conn.sendall(kopf + daten)

        def lesen(self):
            """Ein Client-Rahmen: (opcode, maskiert, nutzlast, fin)."""
            b1, b2 = self.genau(2)
            n = b2 & 0x7F
            if n == 126:
                n = struct.unpack("!H", self.genau(2))[0]
            elif n == 127:
                n = struct.unpack("!Q", self.genau(8))[0]
            maske = self.genau(4) if b2 & 0x80 else None
            daten = self.genau(n)
            if maske:
                daten = WebSocketLeser._maskieren(daten, maske)
            return b1 & 0x0F, bool(b2 & 0x80), daten, bool(b1 & 0x80)

    def fall(name, server, client, **optionen):
        """Startet den Server-Teil in einem Faden und führt den Client-Teil aus."""
        lauscher = socket.socket()
        lauscher.bind(("127.0.0.1", 0))
        lauscher.listen(1)
        notiz = {}

        def dienst():
            try:
                conn, _ = lauscher.accept()
                conn.settimeout(5)
                try:
                    server(Gegenstelle(conn), notiz)
                finally:
                    conn.close()
            except Exception as fehler:
                notiz["serverfehler"] = "%s: %s" % (type(fehler).__name__, fehler)
            finally:
                lauscher.close()

        faden = threading.Thread(target=dienst, daemon=True)
        faden.start()
        url = "ws://127.0.0.1:%d/ws?x=1" % lauscher.getsockname()[1]
        try:
            ok, detail = client(url, notiz, lambda: faden.join(5), optionen)
        except Exception as fehler:
            ok, detail = False, "%s: %s" % (type(fehler).__name__, fehler)
        faden.join(5)
        if "serverfehler" in notiz:
            ok, detail = False, "Server: " + notiz["serverfehler"]
        ergebnisse.append((name, bool(ok), detail or ""))

    def fehler_von(url, **kw):
        """Baut die Verbindung und liest alles; liefert den WebSocketFehler oder None."""
        try:
            ws = WebSocketLeser(url, **kw)
            list(ws.nachrichten())
        except WebSocketFehler as fehler:
            return fehler
        return None

    gross = bytes(i % 251 for i in range(70000))

    # 1. Handschlag, Kopfzeilen, Text, Close
    def s1(g, n):
        g.begruessen()
        g.senden(0x1, '{"a": "Grüße"}'.encode())
        g.senden(0x8, struct.pack("!H", 1000) + b"fertig")
        n["echo"] = g.lesen()

    def c1(url, n, warten, o):
        ws = WebSocketLeser(url, {"Authorization": "Bearer geheim"})
        texte = list(ws.nachrichten())
        warten()
        return (texte == ['{"a": "Grüße"}'] and ws.schliess_code == 1000 and ws.schliess_grund == "fertig"
                and not ws.offen and n["echo"][0] == 0x8 and n["echo"][1] and n["echo"][2][:2] == b"\x03\xe8"), \
            "Text %r, Close %s %r" % (texte, ws.schliess_code, ws.schliess_grund)

    fall("Handschlag, Text, Close mit Antwort", s1, c1)

    # 2. Kopf des Handschlags
    def s2(g, n):
        g.begruessen()
        n["kopf"] = g.kopf
        g.senden(0x8, struct.pack("!H", 1000))

    def c2(url, n, warten, o):
        WebSocketLeser(url, {"Authorization": "Bearer geheim"}).schliessen()
        warten()
        k = n["kopf"]
        ok = (k["_anfrage"] == "GET /ws?x=1 HTTP/1.1" and k["upgrade"] == "websocket"
              and k["sec-websocket-version"] == "13" and k["authorization"] == "Bearer geheim"
              and len(base64.b64decode(k["sec-websocket-key"])) == 16 and k["host"].startswith("127.0.0.1:"))
        return ok, k["_anfrage"]

    fall("Handschlag-Kopf (Schlüssel, Version, Kopfzeile)", s2, c2)

    # 3. Ping -> maskiertes Pong; Fragmente mit Ping dazwischen; 126- und 127-Länge
    def s3(g, n):
        g.begruessen()
        g.senden(0x9, b"hallo")
        n["pong"] = g.lesen()
        text = ("x" * 40 + "ä" * 30).encode()
        g.senden(0x1, text[:20], fin=False)
        g.senden(0x9, b"mitten")
        g.senden(0x0, text[20:61], fin=False)
        g.senden(0x0, text[61:])
        n["pong2"] = g.lesen()
        g.senden(0x1, b"y" * 200)
        g.senden(0x1, gross.hex().encode()[:70000])
        g.senden(0x2, b"\x00\x01\xff")  # Binärrahmen wird übersprungen
        g.senden(0x8, struct.pack("!H", 1001))
        n["close"] = g.lesen()

    def c3(url, n, warten, o):
        ws = WebSocketLeser(url)
        texte = list(ws.nachrichten())
        warten()
        erwartet = ["x" * 40 + "ä" * 30, "y" * 200, gross.hex()[:70000]]
        ok = (texte == erwartet and n["pong"][0] == 0xA and n["pong"][1] and n["pong"][2] == b"hallo"
              and n["pong2"][0] == 0xA and n["pong2"][2] == b"mitten" and n["close"][1]
              and ws.schliess_code == 1001)
        return ok, "%d Nachrichten (%s Zeichen)" % (len(texte), ", ".join(str(len(t)) for t in texte))

    fall("Ping/Pong, Fragmente, Länge 126 und 127", s3, c3)

    # 4. Der Client schickt große Nachrichten maskiert (126 und 127)
    def s4(g, n):
        g.begruessen()
        n["rahmen"] = [g.lesen(), g.lesen(), g.lesen()]
        g.senden(0x8, struct.pack("!H", 1000))
        n["close"] = g.lesen()

    def c4(url, n, warten, o):
        ws = WebSocketLeser(url)
        ws.senden("k" * 5)
        ws.senden("b" * 300)
        ws.senden(gross)
        list(ws.nachrichten())
        warten()
        r = n["rahmen"]
        ok = (all(x[1] for x in r) and r[0][2] == b"kkkkk" and r[1][2] == b"b" * 300
              and r[1][0] == 0x1 and r[2][0] == 0x2 and r[2][2] == gross)
        return ok, "Client-Rahmen alle maskiert: %s" % [len(x[2]) for x in r]

    fall("Client-Rahmen maskiert (125, 126, 127)", s4, c4)

    # 5. schliessen() schickt einen maskierten Close und wartet auf die Antwort
    def s5(g, n):
        g.begruessen()
        n["close"] = g.lesen()
        g.senden(0x8, struct.pack("!H", 1000))

    def c5(url, n, warten, o):
        ws = WebSocketLeser(url)
        ws.schliessen()
        warten()
        c = n["close"]
        return (c[0] == 0x8 and c[1] and c[2][:2] == b"\x03\xe8" and not ws.offen), "Close-Code %s" % c[2][:2].hex()

    fall("schliessen() schickt maskiertes Close", s5, c5)

    # 6. falscher Accept, falscher Status
    def s6(g, n):
        g.begruessen(accept_falsch=True)

    def c6(url, n, warten, o):
        f = fehler_von(url)
        return f is not None and "Handschlag abgelehnt" in str(f), str(f)

    fall("Falscher Accept wird abgewiesen", s6, c6)

    def s7(g, n):
        g.begruessen(status="403 Forbidden")

    def c7(url, n, warten, o):
        f = fehler_von(url)
        return f is not None and "403" in str(f) and "geheim" not in str(f), str(f)

    fall("HTTP 403 beim Handschlag", s7, c7)

    # 8. Stille: erst Ping, dann Abbruch
    def s8(g, n):
        g.begruessen()
        n["ping"] = g.lesen()
        time.sleep(0.6)

    def c8(url, n, warten, o):
        t0 = time.monotonic()
        f = fehler_von(url, timeout=0.25)
        dauer = time.monotonic() - t0
        warten()
        return (f is not None and "antwortet nicht mehr" in str(f) and n["ping"][0] == 0x9 and n["ping"][1]
                and dauer < 2), "%s nach %.2f s" % (f, dauer)

    fall("Stille: Ping, dann Abbruch", s8, c8)

    # 9. Gesamtfrist
    def s9(g, n):
        g.begruessen()
        for _ in range(8):
            time.sleep(0.1)
            g.senden(0xA)  # Pong hält die Verbindung am Leben, bringt aber keine Nachricht

    def c9(url, n, warten, o):
        ws = WebSocketLeser(url, timeout=5)
        t0 = time.monotonic()
        try:
            list(ws.nachrichten(frist=0.4))
        except WebSocketFehler as fehler:
            dauer = time.monotonic() - t0
            return "Zeitgrenze" in str(fehler) and dauer < 1.5, "%s nach %.2f s" % (fehler, dauer)
        return False, "kein Fehler"

    fall("Gesamtfrist nachrichten(frist=…)", s9, c9)

    # 10. Verbindung ohne Close abgerissen
    def s10(g, n):
        g.begruessen()
        g.conn.sendall(b"\x81\x05ab")  # halber Rahmen, dann Ende

    def c10(url, n, warten, o):
        f = fehler_von(url)
        return f is not None, str(f)

    fall("Abbruch mitten im Rahmen", s10, c10)

    # 11. Protokollverstöße: Erweiterungsbit, unbekannter Opcode, Fragment ohne Anfang, ungültiges UTF-8
    for name, rahmenfolge, wort in (
            ("Erweiterungsbit", lambda g: g.senden(0x1, b"x", rsv=0x40), "Erweiterungen"),
            ("unbekannter Opcode", lambda g: g.senden(0x3, b"x"), "unbekannten"),
            ("Fragment ohne Anfang", lambda g: g.senden(0x0, b"x"), "ohne Anfang"),
            ("ungültiges UTF-8", lambda g: g.senden(0x1, b"\xff\xfe"), "UTF-8"),
            ("zerrissener Ping", lambda g: g.senden(0x9, b"x", fin=False), "Steuerrahmen")):
        def sv(g, n, rahmenfolge=rahmenfolge):
            g.begruessen()
            rahmenfolge(g)
            try:
                n["close"] = g.lesen()
            except EOFError:
                pass

        def cv(url, n, warten, o, wort=wort):
            f = fehler_von(url)
            warten()
            code = n.get("close", (0, 0, b"\0\0"))[2][:2]
            return f is not None and wort in str(f) and code in (b"\x03\xea", b"\x03\xef"), \
                "%s / Close-Code %s" % (f, code.hex())

        fall("Protokollverstoß: " + name, sv, cv)

    # 12. zu große Nachricht
    def s12(g, n):
        g.begruessen()
        g.senden(0x1, b"z" * 5000)
        try:
            n["close"] = g.lesen()
        except EOFError:
            pass

    def c12(url, n, warten, o):
        f = fehler_von(url, max_nachricht=1000)
        warten()
        return f is not None and "zu große" in str(f) and n.get("close", (0, 0, b""))[2][:2] == b"\x03\xf1", str(f)

    fall("zu große Nachricht (Close 1009)", s12, c12)

    # 13. schliessen() aus einem zweiten Faden beendet den Leser ohne Fehler
    def s13(g, n):
        g.begruessen()
        n["close"] = g.lesen()
        g.senden(0x8, struct.pack("!H", 1000))

    def c13(url, n, warten, o):
        ws = WebSocketLeser(url)
        ergebnis = {}

        def lesen():
            try:
                ergebnis["texte"] = list(ws.nachrichten())
            except Exception as fehler:
                ergebnis["fehler"] = fehler

        leser = threading.Thread(target=lesen, daemon=True)
        leser.start()
        time.sleep(0.15)
        ws.schliessen()
        leser.join(3)
        warten()
        return ("texte" in ergebnis and not leser.is_alive() and n["close"][0] == 0x8), str(ergebnis)

    fall("schliessen() aus anderem Faden", s13, c13)

    # 14. eingespeiste Verbindung (socketpair), kein Netz
    paar_server, paar_client = socket.socketpair()
    notiz14 = {}

    def s14():
        try:
            paar_server.settimeout(5)
            g = Gegenstelle(paar_server)
            g.begruessen()
            g.senden(0x1, b"eins")
            g.senden(0x8, struct.pack("!H", 1000))
            notiz14["close"] = g.lesen()
        except Exception as fehler:
            notiz14["serverfehler"] = repr(fehler)

    faden14 = threading.Thread(target=s14, daemon=True)
    faden14.start()
    aufrufe = []
    try:
        ws14 = WebSocketLeser("wss://beispiel.test:8443/live", verbinden=lambda h, p, t: (aufrufe.append((h, p, t)),
                                                                                         paar_client)[1])
        texte14 = list(ws14.nachrichten())
        faden14.join(5)
        ergebnisse.append(("Eingespeiste Verbindung (socketpair)",
                           texte14 == ["eins"] and aufrufe == [("beispiel.test", 8443, True)]
                           and notiz14.get("close", (0, 0))[1] is True and "serverfehler" not in notiz14,
                           "aufgerufen mit %s" % (aufrufe,)))
    except Exception as fehler:
        ergebnisse.append(("Eingespeiste Verbindung (socketpair)", False, repr(fehler)))
    finally:
        paar_server.close()
        paar_client.close()

    # 15. Adressen und Kopfzeilen werden geprüft
    schlecht = []
    for url, kopf in (("http://x.test/", None), ("wss://", None), ("", None), ("ws://x.test:abc/", None),
                      ("ws://x.test/", {"Host": "a"}), ("ws://x.test/", {"X": "a\r\nB: c"})):
        try:
            WebSocketLeser(url, kopf, verbinden=lambda h, p, t: (_ for _ in ()).throw(AssertionError("verbunden")))
            schlecht.append(url)
        except WebSocketFehler:
            pass
        except Exception as fehler:
            schlecht.append("%s -> %r" % (url, fehler))
    ergebnisse.append(("Ungültige Adressen und Kopfzeilen", not schlecht, ", ".join(schlecht) or "alle abgewiesen"))
    return ergebnisse


if __name__ == "__main__":
    import sys
    _ergebnisse = netzsocket_selbsttest()
    for _fall, _ok, _detail in _ergebnisse:
        print("%s  %s  %s" % ("OK    " if _ok else "FEHLER", _fall, _detail))
    print("%d von %d Fällen bestanden" % (sum(1 for e in _ergebnisse if e[1]), len(_ergebnisse)))
    sys.exit(0 if all(e[1] for e in _ergebnisse) else 1)
