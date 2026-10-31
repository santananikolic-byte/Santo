# -*- coding: utf-8 -*-
"""Befehle: python3 -m jarvis_core <befehl>

    serve                 Server im Vordergrund (im Alltag: ./jarvis.sh start)
    status                läuft er? seit wann? welche Anbieter?
    stopp                 beendet ihn
    link                  Link zur Oberfläche mit Zugangsschlüssel
    logs [anzahl]         die letzten Log-Einträge
    provider              ist Claude Code bereit? (verbraucht kein Kontingent)
    frage "<text>"        eine Frage stellen (der Server muss laufen)
    notstopp / entsperren Notstopp auslösen oder aufheben
    backup                Sicherung der Datenbank jetzt
    wiederherstellen <f>  Datenbank aus einer Sicherung zurückholen (Server muss gestoppt sein)
    export [datei]        alle gespeicherten Daten als JSON
    lan an|aus            Zugriff aus dem WLAN erlauben oder wieder sperren
    umgebung              was JARVIS über diesen Mac erkennt
"""

import datetime
import json
import os
import shutil
import signal
import socket
import sqlite3
import subprocess
import sys
import time
import urllib.error
import urllib.request

from . import auth, umgebung
from . import konfig as konfig_modul
from .protokoll import Protokoll, letzte_eintraege
from .server import JarvisServer, PidFehler, pid_lesen, primaere_ip, prozess_laeuft
from .speicher import Speicher

WLAN_WARNUNG = """Das macht JARVIS für Geräte in deinem WLAN erreichbar (zum Beispiel dein iPhone).
Wichtig zu wissen:
  - Zugang gibt es nur mit dem geheimen Link (./jarvis.sh link). Wer ihn hat, kann JARVIS bedienen.
  - Die Verbindung ist NICHT verschlüsselt (http). Nur in einem Netz nutzen, dem du vertraust.
  - Nie über den Router ins Internet freigeben (kein Port-Forwarding).
  - Aus der Ferne (unterwegs) wäre ein verschlüsselter Weg nötig, z. B. Tailscale. Das gibt es hier noch nicht."""


def _konfig():
    try:
        return konfig_modul.laden()
    except konfig_modul.KonfigFehler as fehler:
        print("Konfigurationsfehler: %s" % fehler, file=sys.stderr)
        sys.exit(2)


def _lokal_get(k, pfad, timeout=1, kopf=None):
    anfrage = urllib.request.Request(k.adresse + pfad, headers=kopf or {})  # noqa: S310 - immer http://127.0.0.1:<port>
    with urllib.request.urlopen(anfrage, timeout=timeout) as antwort:  # noqa: S310
        return json.loads(antwort.read().decode("utf-8"))


def _status_abfragen(k, timeout=1):
    """Status von JARVIS - None, wenn dort nichts oder ein fremdes Programm antwortet."""
    try:
        daten = _lokal_get(k, "/status", timeout)
    except (urllib.error.URLError, OSError, ValueError):
        return None
    if isinstance(daten, dict) and daten.get("name") == "JARVIS" and "pid" in daten:
        return daten
    return None


def _api(k, methode, pfad, daten=None, timeout=30):
    """Ruft die geschützte Schnittstelle mit dem Zugangsschlüssel auf. Gibt (Code, Antwort) zurück."""
    kopf = {auth.KOPFZEILE: auth.token_holen(k)}
    koerper = None
    if daten is not None:
        koerper = json.dumps(daten).encode("utf-8")
        kopf["Content-Type"] = "application/json"
    anfrage = urllib.request.Request(k.adresse + pfad, data=koerper, method=methode, headers=kopf)  # noqa: S310
    try:
        with urllib.request.urlopen(anfrage, timeout=timeout) as antwort:  # noqa: S310
            return antwort.status, json.loads(antwort.read().decode("utf-8"))
    except urllib.error.HTTPError as fehler:
        try:
            return fehler.code, json.loads(fehler.read().decode("utf-8"))
        except ValueError:
            return fehler.code, {"ok": False, "fehler": "HTTP %s" % fehler.code}


def serve():
    k = _konfig()
    log = Protokoll(k)
    try:
        JarvisServer(k, log).starten()
    except PidFehler as fehler:
        print(str(fehler), file=sys.stderr)
        return 1
    except OSError as fehler:
        print("Der Server konnte nicht starten: %s" % fehler, file=sys.stderr)
        return 1
    finally:
        log.schliessen()
    return 0


def status():
    k = _konfig()
    s = _status_abfragen(k)
    if not s:
        pid = pid_lesen(k.pid_datei)
        if pid and prozess_laeuft(pid):
            print("JARVIS-Prozess %d läuft, antwortet aber nicht unter %s." % (pid, k.adresse))
        else:
            print("JARVIS läuft nicht.")
        return 1
    print("JARVIS läuft  –  %s%s" % (s["adresse"], "   [NOTSTOPP AKTIV]" if s.get("gesperrt") else ""))
    print("  seit         %s (%s Sekunden)" % (s["seit"], s["laufzeit_sekunden"]))
    print("  Anfragen     %s" % s["anfragen"])
    print("  Version      %s, Python %s, Prozess %s%s" % (s["version"], s["python"], s["pid"], ", WLAN offen" if s.get("lan") else ""))
    try:
        code, z = _api(k, "GET", "/api/zustand", timeout=5)
        if code == 200:
            for p in z["system"]["provider"].values():
                print("  %-12s %s %s" % (p.get("anzeige", p["name"]), "●" if p.get("nutzbar") else "○", p.get("hinweis", "")))
            print("  Offen        %d Freigaben, %d Aufgaben, %d Aufträge in Arbeit" % (
                z["zaehler"]["freigaben_offen"], z["zaehler"]["todos_offen"],
                sum(n for st, n in z["zaehler"]["auftraege"].items() if st in ("laeuft", "wartend", "wartet_auf_freigabe"))))
    except (urllib.error.URLError, OSError, ValueError, KeyError):
        pass
    return 0


def _ist_jarvis(pid, k):
    """Gehört die Prozessnummer wirklich zu JARVIS? Nach einem Absturz kann macOS sie neu vergeben haben."""
    s = _status_abfragen(k)
    if s and s.get("pid") == pid:
        return True
    try:
        befehl = subprocess.run(["ps", "-p", str(pid), "-o", "command="], capture_output=True, text=True, timeout=5).stdout
    except (OSError, subprocess.SubprocessError):
        return False
    return "jarvis_core" in befehl


def stopp():
    k = _konfig()
    pid = pid_lesen(k.pid_datei)
    if not pid or not prozess_laeuft(pid) or not _ist_jarvis(pid, k):
        print("JARVIS läuft nicht.")
        if pid:
            try:
                os.remove(k.pid_datei)  # veraltete Datei nach einem Absturz
            except OSError:
                pass
        return 0
    os.kill(pid, signal.SIGTERM)
    for _ in range(150):
        if not prozess_laeuft(pid):
            print("JARVIS ist gestoppt.")
            return 0
        time.sleep(0.1)
    print("JARVIS (Prozess %d) reagiert nicht auf das Stoppsignal. Notfalls: kill -9 %d" % (pid, pid))
    return 1


def link():
    k = _konfig()
    zugang = auth.Zugang(k)
    print(zugang.link(k))
    if k.lan:
        rechner = socket.gethostname().lower()
        for host in (primaere_ip(), rechner if rechner.endswith(".local") else rechner + ".local"):
            if host:
                print("WLAN:  " + zugang.link(k, host))
    return 0


def provider():
    from .provider import ProviderManager

    class _StillesLog:
        def ereignis(self, *args, **kwargs):
            pass

    ergebnis = ProviderManager(_konfig(), _StillesLog()).pruefen()
    for p in ergebnis.values():
        print("%-12s %s %s" % (p["anzeige"], "●" if p["nutzbar"] else "○", p["hinweis"]))
        if p.get("version"):
            print("             Version %s" % p["version"])
    return 0 if ergebnis["claude_code"]["nutzbar"] else 1


def frage(text):
    k = _konfig()
    if not _status_abfragen(k):
        print("JARVIS läuft nicht. Zuerst: ./jarvis.sh start")
        return 1
    try:
        code, antwort = _api(k, "POST", "/api/anfrage", {"text": text}, timeout=k.provider_timeout + 60)
    except (urllib.error.URLError, OSError, ValueError) as fehler:
        print("Keine Antwort vom Server: %s" % fehler)
        return 1
    if antwort.get("ok"):
        print(antwort["antwort"])
        for a in antwort.get("aktionen") or []:
            print("  [%s] %s" % (a["status"], a["kurz"]))
        if antwort.get("freigaben"):
            print("  → %d Freigabe(n) warten in der Oberfläche (./jarvis.sh oeffnen)." % len(antwort["freigaben"]))
        return 0
    print("Fehler: %s" % antwort.get("fehler"))
    return 1


def _einfach(pfad, text_ok):
    k = _konfig()
    if not _status_abfragen(k):
        print("JARVIS läuft nicht.")
        return 1
    code, antwort = _api(k, "POST", pfad, {})
    print(text_ok if antwort.get("ok") else "Fehler: %s" % antwort.get("fehler"))
    return 0 if antwort.get("ok") else 1


def logs(anzahl=20):
    k = _konfig()
    eintraege = letzte_eintraege(k.log_datei, anzahl)
    if not eintraege:
        print("Noch keine Logs in %s." % k.log_datei)
        return 0
    for e in eintraege:
        rest = {x: y for x, y in e.items() if x not in ("zeit", "stufe", "ereignis")}
        zusatz = "  " + json.dumps(rest, ensure_ascii=False) if rest else ""
        print("%s  %-7s %s%s" % (e.get("zeit", "?"), e.get("stufe", "?"), e.get("ereignis", "?"), zusatz))
    return 0


def backup():
    k = _konfig()
    sp = Speicher(k.db_datei)
    try:
        ziel = os.path.join(k.backup_ordner, "jarvis-%s.db" % datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%d-%H%M%S"))
        sp.sichern(ziel)
        print("Gesichert: %s (Prüfung: %s)" % (ziel, sp.integritaet()))
    finally:
        sp.schliessen()
    return 0


def wiederherstellen(datei):
    k = _konfig()
    pid = pid_lesen(k.pid_datei)
    if pid and prozess_laeuft(pid) and _ist_jarvis(pid, k):
        print("JARVIS läuft noch. Erst stoppen: ./jarvis.sh stopp")
        return 1
    if not os.path.isfile(datei):
        print("Diese Sicherung gibt es nicht: %s" % datei)
        return 1
    try:
        verbindung = sqlite3.connect("file:%s?mode=ro" % os.path.abspath(datei), uri=True)
        ergebnis = verbindung.execute("PRAGMA integrity_check").fetchone()[0]
        verbindung.execute("SELECT COUNT(*) FROM fakten")
        verbindung.close()
    except sqlite3.Error as fehler:
        print("Das ist keine brauchbare JARVIS-Sicherung: %s" % fehler)
        return 1
    if ergebnis != "ok":
        print("Die Sicherung ist beschädigt (%s). Es wurde nichts verändert." % ergebnis)
        return 1
    os.makedirs(k.backup_ordner, exist_ok=True)
    if os.path.exists(k.db_datei):
        vorher = os.path.join(k.backup_ordner, "vor-wiederherstellung-%s.db" % datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%d-%H%M%S"))
        sp = Speicher(k.db_datei)
        sp.sichern(vorher)
        sp.schliessen()
        print("Der bisherige Stand liegt sicher in %s" % vorher)
    for endung in ("-wal", "-shm"):
        try:
            os.remove(k.db_datei + endung)
        except OSError:
            pass
    shutil.copyfile(datei, k.db_datei)
    print("Wiederhergestellt aus %s. Jetzt wieder: ./jarvis.sh start" % datei)
    return 0


def export(ziel=None):
    k = _konfig()
    sp = Speicher(k.db_datei)
    try:
        daten = sp.exportieren()
    finally:
        sp.schliessen()
    ziel = ziel or os.path.join(os.path.expanduser("~"), "jarvis-export-%s.json" % datetime.date.today().isoformat())
    fd = os.open(ziel, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(daten, f, ensure_ascii=False, indent=2)
    print("Exportiert: %s (%d Fakten, %d Aufgaben, %d Aufträge). Die Datei enthält persönliche Daten - sicher aufbewahren." % (
        ziel, len(daten["fakten"]), len(daten["aufgaben"]), len(daten["auftraege"])))
    return 0


def lan(wert, eingabe=input):
    k = _konfig()
    if wert == "aus":
        k.aktualisieren({"lan": False})
        print("WLAN-Zugriff ist aus. Wirksam nach: ./jarvis.sh stopp && ./jarvis.sh start")
        return 0
    if wert != "an":
        print("So: ./jarvis.sh lan an  oder  ./jarvis.sh lan aus", file=sys.stderr)
        return 2
    print(WLAN_WARNUNG)
    if eingabe("\nWirklich erlauben? Tippe „ja“: ").strip().lower() != "ja":
        print("Abgebrochen. Nichts wurde geändert.")
        return 1
    k.aktualisieren({"lan": True})
    print("WLAN-Zugriff ist an. Wirksam nach: ./jarvis.sh stopp && ./jarvis.sh start")
    print("Den Link fürs iPhone zeigt dann: ./jarvis.sh link")
    return 0


def umgebung_zeigen():
    for zeile in umgebung.zeilen(umgebung.sammeln(_konfig())):
        print(zeile)
    return 0


def main(argumente):
    befehl = argumente[0] if argumente else "status"
    if befehl == "serve":
        return serve()
    if befehl == "status":
        return status()
    if befehl in ("stopp", "stop"):
        return stopp()
    if befehl == "link":
        return link()
    if befehl == "provider":
        return provider()
    if befehl == "frage":
        if len(argumente) < 2 or not " ".join(argumente[1:]).strip():
            print('So: python3 -m jarvis_core frage "Was steht heute an?"', file=sys.stderr)
            return 2
        return frage(" ".join(argumente[1:]))
    if befehl == "notstopp":
        return _einfach("/api/notstopp", "NOTSTOPP aktiv. Nichts läuft mehr, offene Freigaben sind abgelehnt. Aufheben: ./jarvis.sh entsperren")
    if befehl == "entsperren":
        return _einfach("/api/entsperren", "Entsperrt. JARVIS arbeitet wieder.")
    if befehl == "logs":
        try:
            return logs(int(argumente[1]) if len(argumente) > 1 else 20)
        except ValueError:
            print("So: python3 -m jarvis_core logs 50", file=sys.stderr)
            return 2
    if befehl == "backup":
        return backup()
    if befehl == "wiederherstellen":
        if len(argumente) < 2:
            print("So: ./jarvis.sh wiederherstellen ~/.jarvis/backups/jarvis-….db", file=sys.stderr)
            return 2
        return wiederherstellen(os.path.expanduser(argumente[1]))
    if befehl == "export":
        return export(os.path.expanduser(argumente[1]) if len(argumente) > 1 else None)
    if befehl == "lan":
        return lan(argumente[1] if len(argumente) > 1 else "")
    if befehl == "umgebung":
        return umgebung_zeigen()
    print(__doc__, file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
