# -*- coding: utf-8 -*-
"""Ersatz-Ollama für Tests: ein kleiner HTTP-Server nach der dokumentierten Ollama-Schnittstelle.

- GET  /api/tags  → {"models": [{"name": ..., "model": ...}]}
- POST /api/chat  → {"model": ..., "message": {"role": "assistant", "content": ...}, "done": true}
  (bei "stream": false eine einzige JSON-Antwort)

Verhalten ist pro Test einstellbar (Antworttext, Statuscode, kaputtes JSON, Verzögerung).
Kein echtes Modell – nur die Schnittstelle. Echte Modellnutzung bleibt NICHT VERIFIZIERT.
"""

import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


class ErsatzOllama:
    def __init__(self, modelle=("gemma3:4b",), antwort="Kurze Zusammenfassung.", status=200, kaputt=False,
                 verzoegerung=0.0, umleiten=None):
        self.modelle = list(modelle)
        self.antwort = antwort
        self.status = status
        self.kaputt = kaputt
        self.verzoegerung = verzoegerung
        self.umleiten = umleiten  # z. B. "http://angreifer.example/" – Ollama leitet nie um
        self.anfragen = []
        ersatz = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def _senden(self, code, daten):
                roh = daten if isinstance(daten, bytes) else json.dumps(daten).encode("utf-8")
                self.send_response(code)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(roh)))
                self.end_headers()
                self.wfile.write(roh)

            def _umleiten(self):
                self.send_response(302)
                self.send_header("Location", ersatz.umleiten)
                self.send_header("Content-Length", "0")
                self.end_headers()

            def do_GET(self):
                ersatz.anfragen.append(("GET", self.path, None))
                if ersatz.umleiten:
                    return self._umleiten()
                if self.path == "/api/tags":
                    return self._senden(200, {"models": [{"name": m, "model": m, "size": 1} for m in ersatz.modelle]})
                return self._senden(404, {"error": "not found"})

            def do_POST(self):
                laenge = int(self.headers.get("Content-Length") or 0)
                koerper = json.loads(self.rfile.read(laenge) or b"{}")
                ersatz.anfragen.append(("POST", self.path, koerper))
                if ersatz.umleiten:
                    return self._umleiten()
                if ersatz.verzoegerung:
                    time.sleep(ersatz.verzoegerung)
                if self.path != "/api/chat":
                    return self._senden(404, {"error": "not found"})
                if ersatz.status != 200:
                    return self._senden(ersatz.status, {"error": "interner Fehler"})
                if ersatz.kaputt:
                    return self._senden(200, b"{kein json")
                if koerper.get("model") not in ersatz.modelle:
                    return self._senden(404, {"error": "model '%s' not found" % koerper.get("model")})
                return self._senden(200, {"model": koerper.get("model"), "created_at": "2026-11-21T00:00:00Z",
                                          "message": {"role": "assistant", "content": ersatz.antwort},
                                          "done": True})

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.server.daemon_threads = True
        self.adresse = "http://127.0.0.1:%d" % self.server.server_address[1]
        self._faden = threading.Thread(target=self.server.serve_forever, daemon=True)

    def __enter__(self):
        self._faden.start()
        return self

    def __exit__(self, *a):
        self.server.shutdown()
        self.server.server_close()
        return False


def freie_adresse_ohne_server():
    """Eine lokale Adresse, auf der garantiert niemand lauscht (Port wird geöffnet und sofort geschlossen)."""
    import socket
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return "http://127.0.0.1:%d" % port
