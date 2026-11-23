# -*- coding: utf-8 -*-
"""iPhone im eigenen WLAN: private Adressen dieses Rechners ermitteln und den Anmeldelink als QR-Code liefern.

- Nur private IPv4-Adressen (z. B. 192.168.x.x, 10.x.x.x, 172.16–31.x.x) – nie öffentliche, nie Loopback,
  nie Link-Local (169.254.x.x, das bedeutet „kein richtiges Netz“).
- Ohne Zusatzpakete: Adresse über die Standardbibliothek; QR-Code mit qrcodegen.py von Project Nayuki
  (MIT-Lizenz, unverändert übernommen aus dem Paket qrcodegen 1.8.0, Lizenzkopf in der Datei).
- AUTONOMOUS_WLAN_ADRESSE (kommagetrennt) gibt die Adresse(n) fest vor – auch diese werden gefiltert.
"""

import ipaddress
import os
import re
import socket

from . import qrcodegen

QR_RAND = 4  # vorgeschriebene helle Ruhezone in Modulen


def ist_nutzbar(adresse):
    try:
        ip = ipaddress.ip_address(str(adresse).strip())
    except ValueError:
        return False
    return ip.version == 4 and ip.is_private and not ip.is_loopback and not ip.is_link_local


def _kandidaten():
    vorgabe = os.environ.get("AUTONOMOUS_WLAN_ADRESSE", "").strip()
    if vorgabe:
        return [a.strip() for a in vorgabe.split(",") if a.strip()]
    kandidaten = []
    try:  # Adresse, über die dieser Rechner ins Netz geht – es wird dabei nichts gesendet (UDP ohne Daten)
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            s.connect(("8.8.8.8", 80))
            kandidaten.append(s.getsockname()[0])
        finally:
            s.close()
    except OSError:
        pass
    try:
        kandidaten += socket.gethostbyname_ex(socket.gethostname())[2]
    except OSError:
        pass
    return kandidaten


def private_adressen():
    ergebnis = []
    for adresse in _kandidaten():
        if ist_nutzbar(adresse) and adresse not in ergebnis:
            ergebnis.append(adresse)
    return ergebnis


def lokaler_name():
    """Bonjour-Name wie „macbook-air.local“ (das iPhone findet ihn im selben WLAN), sonst None."""
    kurz = (socket.gethostname() or "").strip().lower().split(".")[0]
    if not re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", kurz):
        return None
    return kurz + ".local"


def qr_matrix(text):
    qr = qrcodegen.QrCode.encode_text(text, qrcodegen.QrCode.Ecc.MEDIUM)
    n = qr.get_size()
    return [[qr.get_module(x, y) for x in range(n)] for y in range(n)]


def qr_daten(text):
    """QR-Code als SVG-Pfad (je dunkles Modul ein 1×1-Quadrat, Ruhezone eingerechnet).
    Die Oberfläche zeichnet daraus ein SVG nur mit Attributen – ohne Inline-Stile (strenge CSP)."""
    matrix = qr_matrix(text)
    teile = []
    for y, zeile in enumerate(matrix):
        for x, dunkel in enumerate(zeile):
            if dunkel:
                teile.append("M%d %dh1v1h-1z" % (x + QR_RAND, y + QR_RAND))
    return {"groesse": len(matrix), "rand": QR_RAND, "pfad": "".join(teile)}
