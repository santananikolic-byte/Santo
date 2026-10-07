"""Rezept: KI-Telefonagent (Vapi) nur mit ausgehenden Verbindungen.

Nur Standardbibliothek. Kein Webhook, kein Tunnel: der Mac fragt Vapi ab
(GET /call/{id}) und liest - optional - Retells Live-Mitschrift über eine
ausgehende WebSocket-Verbindung.
"""
import base64
import hashlib
import json
import math
import os
import socket
import ssl
import struct
import time
import urllib.error
import urllib.parse
import urllib.request

VAPI_BASIS = os.environ.get("VAPI_BASIS", "https://api.vapi.ai")  # EU-Konto: https://api.eu.vapi.ai
OVERPASS_URL = "https://overpass-api.de/api/interpreter"

# ---------------------------------------------------------------- Restaurant finden
ASIATISCH = ("asian|chinese|japanese|thai|vietnamese|sushi|korean|ramen|"
             "indonesian|malaysian|taiwanese|cantonese|sichuan|nepalese|indian")


def overpass_asiatisch(breite, laenge, radius=2500, anzahl=40):
    """Overpass-QL: asiatische Restaurants mit Namen im Umkreis (Meter)."""
    return ('[out:json][timeout:25];'
            'nwr["amenity"="restaurant"]["cuisine"~"%s",i]["name"](around:%d,%.5f,%.5f);'
            'out center tags %d;' % (ASIATISCH, int(radius), breite, laenge, int(anzahl)))


def _abstand_m(b1, l1, b2, l2):
    r = 6371000.0
    p1, p2 = math.radians(b1), math.radians(b2)
    db, dl = p2 - p1, math.radians(l2 - l1)
    a = math.sin(db / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def restaurants_lesen(daten, breite, laenge):
    """Overpass-Antwort -> Liste, nächstes zuerst; nur Einträge MIT Telefonnummer."""
    liste = []
    for el in (daten or {}).get("elements", []):
        t = el.get("tags") or {}
        tel = (t.get("phone") or t.get("contact:phone") or "").split(";")[0].strip()
        if not tel:
            continue
        pos = el.get("center") or {"lat": el.get("lat"), "lon": el.get("lon")}
        if pos.get("lat") is None:
            continue
        liste.append({
            "name": t.get("name", ""), "kueche": t.get("cuisine", ""),
            "telefon": tel, "oeffnungszeiten": t.get("opening_hours", ""),
            "adresse": " ".join(x for x in (t.get("addr:street", ""), t.get("addr:housenumber", ""),
                                            t.get("addr:postcode", ""), t.get("addr:city", "")) if x),
            "abstand_m": round(_abstand_m(breite, laenge, pos["lat"], pos["lon"])),
            "osm": "%s/%s" % (el.get("type"), el.get("id")),
        })
    return sorted(liste, key=lambda r: r["abstand_m"])


def restaurants_suchen(breite, laenge, radius=2500):
    daten = urllib.parse.urlencode({"data": overpass_asiatisch(breite, laenge, radius)}).encode()
    anfrage = urllib.request.Request(OVERPASS_URL, data=daten,
                                     headers={"User-Agent": "Jarvis/1.0 (privater Assistent)"})
    with urllib.request.urlopen(anfrage, timeout=40) as antwort:
        return restaurants_lesen(json.load(antwort), breite, laenge)


# ---------------------------------------------------------------- Vapi-Aufrufe
def _vapi(methode, pfad, schluessel, koerper=None, timeout=30):
    anfrage = urllib.request.Request(
        VAPI_BASIS + pfad, method=methode,
        data=json.dumps(koerper).encode("utf-8") if koerper is not None else None,
        headers={"Authorization": "Bearer " + schluessel,
                 "Content-Type": "application/json", "Accept": "application/json"})
    try:
        with urllib.request.urlopen(anfrage, timeout=timeout) as antwort:
            return json.loads(antwort.read().decode("utf-8") or "{}"), ""
    except urllib.error.HTTPError as fehler:
        text = fehler.read().decode("utf-8", "replace")[:600]
        return None, "Vapi meldet HTTP %s: %s" % (fehler.code, text)
    except (urllib.error.URLError, OSError, ValueError) as fehler:
        return None, "Vapi nicht erreichbar: %s" % fehler


RESERVIERUNG_SCHEMA = {
    "type": "object",
    "properties": {
        "reserviert": {"type": "boolean", "description": "Hat das Restaurant die Reservierung fest bestätigt?"},
        "datum": {"type": "string", "description": "Bestätigtes Datum, Format JJJJ-MM-TT"},
        "uhrzeit": {"type": "string", "description": "Bestätigte Uhrzeit, Format HH:MM"},
        "personen": {"type": "integer"},
        "name_der_reservierung": {"type": "string", "description": "Auf welchen Namen reserviert wurde"},
        "gegenvorschlag": {"type": "string", "description": "Alternative des Restaurants, falls nicht wie gewünscht"},
        "hinweise": {"type": "string", "description": "z. B. Tisch nur bis 21 Uhr, Anzahlung, Rückrufnummer"},
    },
    "required": ["reserviert"],
}


def anruf_koerper(telefon_id, ziel_nummer, restaurant, auftraggeber, datum, uhrzeit, personen,
                  stimme=None):
    """JSON für POST /call mit transientem (inline) Assistenten auf Deutsch."""
    auftrag = ("Du bist der KI-Telefonassistent von %s. Du rufst beim Restaurant '%s' an, "
               "um einen Tisch für %d Personen am %s um %s Uhr auf den Namen %s zu reservieren. "
               "Sprich kurz, höflich, natürlich, auf Deutsch, Sie-Form. Erfinde nichts. "
               "Wenn die Zeit nicht geht: frage nach der nächstmöglichen Zeit zwischen %s und "
               "eine Stunde später, nimm sie an, wenn sie in diesem Fenster liegt; sonst bedanke "
               "dich und beende das Gespräch ohne Zusage. Gib außer dem Namen keine persönlichen "
               "Daten heraus. Fragt jemand, ob du eine KI bist: ja, ehrlich. Wiederhole am Ende "
               "Datum, Uhrzeit, Personenzahl und Namen, verabschiede dich und beende den Anruf mit "
               "dem Werkzeug endCall. Bei Anrufbeantworter oder Warteschleife: auflegen."
               % (auftraggeber, restaurant, personen, datum, uhrzeit, auftraggeber, uhrzeit))
    erster_satz = ("Guten Tag, hier spricht der digitale Assistent von %s - ich bin eine "
                   "künstliche Intelligenz und rufe in seinem Auftrag an. Ich würde gern einen "
                   "Tisch reservieren. Passt das gerade kurz?" % auftraggeber)
    return {
        "name": "Jarvis: Tisch bei %s" % restaurant[:40],
        "phoneNumberId": telefon_id,
        "customer": {"number": ziel_nummer, "name": restaurant[:40]},
        "assistant": {
            "name": "Jarvis Reservierung",
            "firstMessage": erster_satz,
            "firstMessageMode": "assistant-speaks-first",
            "model": {
                "provider": "anthropic", "model": "claude-haiku-4-5-20251001",
                "temperature": 0.3, "maxTokens": 200,
                "messages": [{"role": "system", "content": auftrag}],
                "tools": [{"type": "endCall"}],
            },
            "voice": stimme or {"provider": "azure", "voiceId": "de-DE-KatjaNeural"},
            "transcriber": {"provider": "deepgram", "model": "nova-3", "language": "de"},
            "voicemailDetection": {"provider": "vapi"},
            "maxDurationSeconds": 240,
            "endCallMessage": "Vielen Dank und auf Wiederhören!",
            "backgroundSound": "off",
            "artifactPlan": {
                "recordingEnabled": False,  # § 201 StGB: keine Tonaufnahme ohne Einwilligung
                "transcriptPlan": {"enabled": True, "assistantName": "Jarvis", "userName": "Restaurant"},
                "structuredOutputs": [{"name": "reservierung", "type": "ai",
                                       "schema": RESERVIERUNG_SCHEMA}],
            },
            "monitorPlan": {"listenEnabled": False, "controlEnabled": True},
            "metadata": {"quelle": "jarvis", "zweck": "tischreservierung"},
        },
    }


def anruf_starten(schluessel, koerper):
    return _vapi("POST", "/call", schluessel, koerper)


def anruf_holen(schluessel, kennung):
    return _vapi("GET", "/call/" + urllib.parse.quote(kennung), schluessel)


def anruf_beenden(control_url):
    """Live-Steuerung: Auflegen-Knopf im HUD (controlUrl kommt in call.monitor)."""
    anfrage = urllib.request.Request(control_url, method="POST",
                                     data=json.dumps({"type": "end-call"}).encode(),
                                     headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(anfrage, timeout=15) as antwort:
        return antwort.status


def _zeilen(anruf):
    """Gesprochene Zeilen beider Seiten, egal ob in artifact.messages oder messages."""
    quelle = ((anruf.get("artifact") or {}).get("messages") or anruf.get("messages") or [])
    zeilen = []
    for m in quelle:
        rolle = m.get("role")
        if rolle not in ("bot", "assistant", "user"):
            continue  # system, tool_calls, tool_call_result weglassen
        text = (m.get("message") or m.get("content") or "").strip()
        if text:
            zeilen.append({"wer": "Jarvis" if rolle in ("bot", "assistant") else "Restaurant",
                           "sekunde": m.get("secondsFromStart", 0), "text": text})
    return zeilen


def ergebnis_lesen(anruf):
    """Strukturiertes Ergebnis: neue structuredOutputs, sonst (veraltet) analysis.structuredData."""
    for eintrag in ((anruf.get("artifact") or {}).get("structuredOutputs") or {}).values():
        if isinstance(eintrag, dict) and eintrag.get("name") == "reservierung":
            return eintrag.get("result")
    return (anruf.get("analysis") or {}).get("structuredData")


def anruf_verfolgen(schluessel, kennung, melden, takt=1.5, nachlauf=60, max_dauer=240):
    """Fragt Vapi ab, bis der Anruf vorbei UND das Ergebnis da ist.

    melden(art, daten) bekommt: ("status", s), ("zeile", z), ("ende", anruf).
    """
    letzter_status, gesehen, ende_seit = None, set(), None
    frist = time.time() + max_dauer + 180  # harte Obergrenze: Klingeln + Gespräch + Auswertung
    anruf = {}
    while time.time() < frist:
        daten, fehler = anruf_holen(schluessel, kennung)
        if fehler:
            melden("fehler", fehler)
            time.sleep(min(10, takt * 3))
            continue
        anruf = daten
        status = anruf.get("status")
        if status != letzter_status:
            letzter_status = status
            melden("status", status)
        for z in _zeilen(anruf):
            schluessel_z = (z["wer"], z["sekunde"], z["text"])
            if schluessel_z not in gesehen:
                gesehen.add(schluessel_z)
                melden("zeile", z)
        if status in ("ended", "not-found"):
            ende_seit = ende_seit or time.time()
            fertig = ergebnis_lesen(anruf) is not None
            if fertig or time.time() - ende_seit > nachlauf:
                melden("ende", anruf)
                return anruf
        time.sleep(takt)
    melden("fehler", "Zeitlimit: Anruf %s nicht abgeschlossen" % kennung)
    return anruf


ENDE_DEUTSCH = {
    "assistant-ended-call": "Jarvis hat nach dem Gespräch aufgelegt.",
    "customer-ended-call": "Das Restaurant hat aufgelegt.",
    "customer-busy": "Besetzt.",
    "customer-did-not-answer": "Niemand ist rangegangen.",
    "voicemail": "Nur Anrufbeantworter - aufgelegt, nichts hinterlassen.",
    "exceeded-max-duration": "Zeitlimit erreicht.",
    "silence-timed-out": "Zu lange Stille.",
    "manually-canceled": "Von dir abgebrochen.",
    "twilio-failed-to-connect-call": "Twilio konnte nicht verbinden (Geo-Freigabe/Nummer prüfen).",
}


# ---------------------------------------------------------------- WebSocket (ausgehend)
class WebSocketLeser:
    """Minimaler RFC-6455-Client: nur lesen (Text/Binär), Ping beantworten. Ausgehend."""

    def __init__(self, url, kopfzeilen=None, timeout=30):
        teile = urllib.parse.urlsplit(url)
        sicher = teile.scheme == "wss"
        port = teile.port or (443 if sicher else 80)
        roh = socket.create_connection((teile.hostname, port), timeout=timeout)
        self.sock = ssl.create_default_context().wrap_socket(
            roh, server_hostname=teile.hostname) if sicher else roh
        schluessel = base64.b64encode(os.urandom(16)).decode()
        pfad = (teile.path or "/") + ("?" + teile.query if teile.query else "")
        zeilen = ["GET %s HTTP/1.1" % pfad, "Host: %s" % teile.netloc, "Upgrade: websocket",
                  "Connection: Upgrade", "Sec-WebSocket-Key: " + schluessel,
                  "Sec-WebSocket-Version: 13"]
        zeilen += ["%s: %s" % kv for kv in (kopfzeilen or {}).items()]
        self.sock.sendall(("\r\n".join(zeilen) + "\r\n\r\n").encode())
        kopf = b""
        while b"\r\n\r\n" not in kopf:
            stueck = self.sock.recv(1024)
            if not stueck:
                raise ConnectionError("Server hat beim Handshake getrennt")
            kopf += stueck
        kopf, self._rest = kopf.split(b"\r\n\r\n", 1)
        if b" 101 " not in kopf.split(b"\r\n", 1)[0]:
            raise ConnectionError("Kein WebSocket-Upgrade: %r" % kopf[:200])
        erwartet = base64.b64encode(hashlib.sha1(
            (schluessel + "258EAFA5-E914-47DA-95CA-C5AB0DC85B11").encode()).digest())
        if erwartet not in kopf:
            raise ConnectionError("Sec-WebSocket-Accept passt nicht")

    def _lesen(self, n):
        while len(self._rest) < n:
            stueck = self.sock.recv(65536)
            if not stueck:
                raise ConnectionError("Verbindung zu")
            self._rest += stueck
        daten, self._rest = self._rest[:n], self._rest[n:]
        return daten

    def _senden(self, opcode, nutzlast=b""):
        maske = os.urandom(4)  # Client-Frames MÜSSEN maskiert sein
        kopf = bytes([0x80 | opcode])
        n = len(nutzlast)
        if n < 126:
            kopf += bytes([0x80 | n])
        elif n < 65536:
            kopf += bytes([0x80 | 126]) + struct.pack("!H", n)
        else:
            kopf += bytes([0x80 | 127]) + struct.pack("!Q", n)
        self.sock.sendall(kopf + maske + bytes(b ^ maske[i % 4] for i, b in enumerate(nutzlast)))

    def nachrichten(self):
        """Erzeugt (art, daten): art = 'text' | 'binaer'. Endet beim Close-Frame."""
        teile, art = [], None
        while True:
            b1, b2 = self._lesen(2)
            fin, opcode = b1 & 0x80, b1 & 0x0F
            n = b2 & 0x7F
            if n == 126:
                n = struct.unpack("!H", self._lesen(2))[0]
            elif n == 127:
                n = struct.unpack("!Q", self._lesen(8))[0]
            maske = self._lesen(4) if b2 & 0x80 else None
            nutzlast = self._lesen(n)
            if maske:
                nutzlast = bytes(b ^ maske[i % 4] for i, b in enumerate(nutzlast))
            if opcode == 0x8:  # Close
                try:
                    self._senden(0x8, nutzlast[:2])
                finally:
                    self.sock.close()
                return
            if opcode == 0x9:  # Ping -> Pong
                self._senden(0xA, nutzlast)
                continue
            if opcode == 0xA:
                continue
            if opcode in (0x1, 0x2):
                art, teile = ("text" if opcode == 0x1 else "binaer"), [nutzlast]
            elif opcode == 0x0:
                teile.append(nutzlast)
            if fin and art:
                daten = b"".join(teile)
                yield art, (daten.decode("utf-8") if art == "text" else daten)
                art, teile = None, []


def retell_live_mitschrift(retell_schluessel, call_id, melden):
    """Retell: wss://api.retellai.com/v2/monitor-call/{call_id} - Mitschrift live, ausgehend."""
    ws = WebSocketLeser("wss://api.retellai.com/v2/monitor-call/" + call_id,
                        {"Authorization": "Bearer " + retell_schluessel})
    zeilen = {}
    for art, text in ws.nachrichten():
        if art != "text":
            continue
        ereignis = json.loads(text)
        if ereignis.get("type") in ("transcript_snapshot", "transcript_updated"):
            for item in ereignis.get("transcripts") or []:
                if item.get("role") in ("agent", "user"):
                    zeilen[item["id"]] = item  # gleiche id ersetzt: Zeile wächst beim Sprechen
            melden("mitschrift", sorted(zeilen.values(), key=lambda i: i.get("time_sec", 0)))
        elif ereignis.get("type") == "call_ended":
            melden("ende", ereignis.get("disconnection_reason"))
