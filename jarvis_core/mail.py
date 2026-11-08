# -*- coding: utf-8 -*-
"""E-Mail über die Mail-App des Macs (Apple Mail) - ohne Passwort in JARVIS.

JARVIS steuert die Mail-App mit ``osascript`` (AppleScript). Die Mail-App ist schon mit den
Postfächern des Nutzers angemeldet; JARVIS speichert keine Zugangsdaten und sieht keine.

Sicherheit:

* Alles, was vom Nutzer oder vom Modell kommt (Empfänger, Betreff, Text, Nummern, Konten, Ordner), geht nur
  als Argument an das Skript (``on run argv``) - nie in den Skripttext. Ein Betreff kann so nie zu
  AppleScript-Code werden. Vor allen Argumenten steht ein festes Wort, damit kein Argument, das mit
  "-" beginnt, als Programmoption von osascript gelesen wird. Die Skripte selbst sind reines ASCII.
* Lesen ist frei, das Ergebnis gilt aber als Außenquelle (E-Mails können Anweisungen enthalten).
* Ein Entwurf öffnet nur ein Fenster in der Mail-App - der Nutzer schickt selbst ab.
* Senden und Verschieben laufen nur nach Freigabe (siehe ``werkzeuge.py``). Gelöscht wird keine E-Mail.
  ``send`` wird nie automatisch wiederholt.
* Beim ersten Zugriff fragt macOS, ob JARVIS (das Terminal) die Mail-App steuern darf.

Was die Mail-App eigen macht (Recherche, auf keinem echten Mac von uns geprüft):

* Nummern (``id``) gelten nur innerhalb eines Postfachs und ändern sich beim Verschieben. Darum wird
  eine E-Mail immer über Konto + Nummer angesprochen, im Posteingang ("INBOX" bzw. "Inbox") dieses Kontos.
* Eigenschaften werden gesammelt gelesen (eine Abfrage für alle Betreffs usw.), nicht Mail für Mail:
  das ist um ein Vielfaches schneller.
* Daten werden über dokumentierte Eigenschaften (Jahr, Monat …) in die Form JJJJ-MM-TTTHH:MM:SS gebracht.
* Neue Nachrichten werden immer sichtbar erzeugt: unsichtbare, nicht gesendete Nachrichten tauchen
  sonst später als Entwurf wieder auf.
"""

import datetime
import os
import re
import shutil
import subprocess
import unicodedata

US, RS = "\x1f", "\x1e"  # Feld- und Satztrenner; werden in den Feldern selbst entfernt (clean)
ANKER = "JARVIS"  # festes erstes Argument (siehe oben)
STANDARD_TAGE, MAX_TAGE = 7, 60
STANDARD_ANZAHL, MAX_ANZAHL = 20, 50
JE_KONTO = 150  # so viele neueste E-Mails je Posteingang schaut das Skript höchstens an
MAX_INHALT = 12000
MAX_EMPFAENGER = 10
MAX_IDS = 50
ADRESSE = re.compile(r"^[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Za-z0-9](?:[A-Za-z0-9-]*[A-Za-z0-9])?"
                     r"(?:\.[A-Za-z0-9](?:[A-Za-z0-9-]*[A-Za-z0-9])?)*\.[A-Za-z]{2,}$")
_STEUERZEICHEN = re.compile(r"[\x00-\x08\x0b-\x1f\x7f]")
_FEHLERNUMMER = re.compile(r"\((-?\d+)\)\s*$")
_ZAHL = re.compile(r"^[0-9]{1,12}$")  # nur ASCII-Ziffern: "²" oder "①" sind keine Nummern

# ------------------------------------------------------------------ Skripte ---
# item 1 of argv ist immer ANKER, die echten Werte folgen ab item 2. Jedes Skript beginnt mit einer Kennzeile.

HELFER = """
on iso(d)
	set t to time of d
	return ((year of d) as text) & "-" & my p2((month of d) as integer) & "-" & my p2(day of d) & "T" & my p2(t div 3600) & ":" & my p2((t mod 3600) div 60) & ":" & my p2(t mod 60)
end iso

on p2(x)
	return text -2 thru -1 of ("0" & x)
end p2

on clean(v)
	if v is missing value then return ""
	set alt to AppleScript's text item delimiters
	set AppleScript's text item delimiters to {character id 30, character id 31}
	set teile to text items of (v as text)
	set AppleScript's text item delimiters to " "
	set v to teile as text
	set AppleScript's text item delimiters to alt
	return v
end clean

on verbinden(liste, trenner)
	set alt to AppleScript's text item delimiters
	set AppleScript's text item delimiters to trenner
	set ergebnis to liste as text
	set AppleScript's text item delimiters to alt
	return ergebnis
end verbinden

on posteingang(kontoname)
	tell application "Mail"
		set konto to account kontoname
		repeat with kandidat in {"INBOX", "Inbox", "Posteingang"}
			try
				return mailbox (contents of kandidat) of konto
			end try
		end repeat
	end tell
	error "kein Posteingang" number 9404
end posteingang

on ordner_finden(kontoname, pfad)
	set alt to AppleScript's text item delimiters
	set AppleScript's text item delimiters to "/"
	set teile to text items of pfad
	set AppleScript's text item delimiters to alt
	tell application "Mail"
		set mbx to mailbox (item 1 of teile) of account kontoname
		repeat with i from 2 to count of teile
			set mbx to mailbox (item i of teile) of mbx
		end repeat
	end tell
	return mbx
end ordner_finden
"""

SKRIPT_POSTFACH = """-- JARVIS:postfach
on run argv
	set grenze to (item 2 of argv) as integer
	set seit to (current date) - ((item 3 of argv) as integer) * days
	set US to character id 31
	set zeilen to {}
	with timeout of 60 seconds
		tell application "Mail"
			if (count of accounts) is 0 then error "kein Konto" number 9100
			repeat with konto in (every account whose enabled is true)
				set n to -1
				repeat with kandidat in {"INBOX", "Inbox", "Posteingang"}
					try
						set mb to mailbox (contents of kandidat) of konto
						set n to count of messages of mb
						exit repeat
					end try
				end repeat
				if n is -1 then set end of zeilen to "UEBERSPRUNGEN" & US & my clean(name of konto)
				if n > grenze then set n to grenze
				if n > 0 then
					set ids to id of messages 1 thru n of mb
					set daten to date received of messages 1 thru n of mb
					set absender to sender of messages 1 thru n of mb
					set betreffe to subject of messages 1 thru n of mb
					set gelesen to read status of messages 1 thru n of mb
					if (id of messages 1 thru n of mb) is not ids then error "Posteingang hat sich geaendert" number 9001
					set kontoname to my clean(name of konto)
					repeat with i from 1 to n
						try
							if (item i of daten) is greater than seit then
								set end of zeilen to kontoname & US & ((item i of ids) as text) & US & my clean(item i of absender) & US & my clean(item i of betreffe) & US & my iso(item i of daten) & US & ((item i of gelesen) as text)
							end if
						end try
					end repeat
				end if
			end repeat
		end tell
	end timeout
	return my verbinden(zeilen, character id 30)
end run
""" + HELFER

SKRIPT_LESEN = """-- JARVIS:lesen
on run argv
	set kontoname to item 2 of argv
	set gesucht to (item 3 of argv) as integer
	set hoechstens to (item 4 of argv) as integer
	set US to character id 31
	with timeout of 60 seconds
		tell application "Mail"
			if (count of accounts) is 0 then error "kein Konto" number 9100
			set mb to my posteingang(kontoname)
			set treffer to (messages of mb whose id is gesucht)
			if (count of treffer) is 0 then error "nicht gefunden" number 9404
			set m to item 1 of treffer
			if (id of m) is not gesucht then error "falsche Nummer" number 9409
			set absender to sender of m
			set betreff to subject of m
			set datum to date received of m
			set an to address of every to recipient of m
			set inhalt to content of m
		end tell
	end timeout
	if inhalt is missing value then set inhalt to ""
	if (length of inhalt) > hoechstens then set inhalt to text 1 thru hoechstens of inhalt
	return my clean(absender) & US & my clean(my verbinden(an, ", ")) & US & my clean(betreff) & US & my iso(datum) & US & inhalt
end run
""" + HELFER

SKRIPT_KOEPFE = """-- JARVIS:koepfe
on run argv
	set kontoname to item 2 of argv
	set US to character id 31
	set zeilen to {}
	with timeout of 60 seconds
		tell application "Mail"
			set mb to my posteingang(kontoname)
			repeat with i from 3 to count of argv
				set gesucht to (item i of argv) as integer
				try
					set m to item 1 of (messages of mb whose id is gesucht)
					set end of zeilen to (gesucht as text) & US & my clean(sender of m) & US & my clean(subject of m)
				on error
					set end of zeilen to (gesucht as text) & US & "" & US & "(nicht im Posteingang gefunden)"
				end try
			end repeat
		end tell
	end timeout
	return my verbinden(zeilen, character id 30)
end run
""" + HELFER

SKRIPT_ORDNER = """-- JARVIS:ordner
on run argv
	set US to character id 31
	set zeilen to {}
	with timeout of 60 seconds
		tell application "Mail"
			if (count of accounts) is 0 then error "kein Konto" number 9100
			repeat with konto in (every account)
				set kontoname to my clean(name of konto)
				set end of zeilen to "KONTO" & US & kontoname & US & my clean(my verbinden(email addresses of konto, ", "))
				repeat with mbx in (every mailbox of konto)
					set pfad to name of mbx
					set oben to missing value
					try
						set oben to container of mbx
					end try
					repeat while oben is not missing value
						set art to missing value
						try
							set art to class of oben
						end try
						if art is not mailbox then exit repeat
						set pfad to (name of oben) & "/" & pfad
						set naechster to missing value
						try
							set naechster to container of oben
						end try
						set oben to naechster
					end repeat
					set end of zeilen to kontoname & US & my clean(pfad)
				end repeat
			end repeat
		end tell
	end timeout
	return my verbinden(zeilen, character id 30)
end run
""" + HELFER

SKRIPT_NACHRICHT = """-- JARVIS:nachricht
on run argv
	set modus to item 2 of argv
	set betreff to item 3 of argv
	set inhalt to item 4 of argv
	set von to item 5 of argv
	set empfaenger to {}
	if (count of argv) > 5 then set empfaenger to items 6 thru -1 of argv
	set US to character id 31
	with timeout of 60 seconds
		tell application "Mail"
			if (count of accounts) is 0 then error "kein Konto" number 9100
			set nachricht to make new outgoing message with properties {subject:betreff, content:inhalt, visible:true}
			tell nachricht
				repeat with adresse in empfaenger
					make new to recipient at end of to recipients with properties {address:(contents of adresse)}
				end repeat
				if von is not "" then set sender to von
			end tell
			set benutzt to my clean(sender of nachricht)
			if von is not "" and benutzt does not contain von then
				activate
				error "Absender passt nicht: " & benutzt number 9410
			end if
			if modus is "senden" then
				if (send nachricht) is false then error "nicht gesendet" number 9500
				return "gesendet" & US & benutzt
			end if
			activate
			return "entwurf" & US & benutzt
		end tell
	end timeout
end run
""" + HELFER

SKRIPT_VERSCHIEBEN = """-- JARVIS:verschieben
on run argv
	set kontoname to item 2 of argv
	set zielpfad to item 3 of argv
	set US to character id 31
	set zeilen to {}
	with timeout of 60 seconds
		tell application "Mail"
			set quelle to my posteingang(kontoname)
			set ziel to my ordner_finden(kontoname, zielpfad)
			repeat with i from 4 to count of argv
				set gesucht to (item i of argv) as integer
				try
					set treffer to (messages of quelle whose id is gesucht)
					if (count of treffer) is 0 then error "nicht im Posteingang"
					set m to item 1 of treffer
					if (id of m) is not gesucht then error "falsche Nummer"
					move m to ziel
					set end of zeilen to (gesucht as text) & US & "ok"
				on error fehler
					set end of zeilen to (gesucht as text) & US & my clean(fehler)
				end try
			end repeat
		end tell
	end timeout
	return my verbinden(zeilen, character id 30)
end run
""" + HELFER

SKRIPTE = (SKRIPT_POSTFACH, SKRIPT_LESEN, SKRIPT_KOEPFE, SKRIPT_ORDNER, SKRIPT_NACHRICHT, SKRIPT_VERSCHIEBEN)


class MailFehler(Exception):
    """Fehler, den der Nutzer verstehen soll - mit Lösung, wo es eine gibt. ``nummer``: AppleScript-Fehlernummer."""

    def __init__(self, text, nummer=None):
        super().__init__(text)
        self.nummer = nummer


ERKLAERUNG = {
    -1743: ("JARVIS darf die Mail-App noch nicht steuern. Lösung: Systemeinstellungen → Datenschutz & Sicherheit → "
            "Automation → beim Terminal „Mail“ einschalten. Wurde die Frage einmal mit „Nicht erlauben“ beantwortet, "
            "fragt macOS nie wieder - dann dort einschalten."),
    -1728: "Das gibt es in der Mail-App nicht (Konto, Ordner oder E-Mail nicht gefunden).",
    -1719: "Das gibt es in der Mail-App nicht (Konto, Ordner oder E-Mail nicht gefunden).",
    9404: "Diese E-Mail ist nicht (mehr) im Posteingang dieses Kontos - vielleicht verschoben. Bitte das Postfach neu ansehen.",
    9409: "Diese E-Mail ist nicht (mehr) im Posteingang dieses Kontos - vielleicht verschoben. Bitte das Postfach neu ansehen.",
    -600: "Die Mail-App läuft nicht oder ließ sich nicht starten. Bitte die Mail-App einmal öffnen.",
    -609: "Die Mail-App läuft nicht oder ließ sich nicht starten. Bitte die Mail-App einmal öffnen.",
    -1712: ("Die Mail-App hat nicht rechtzeitig geantwortet. Steht auf dem Mac gerade eine Frage von macOS offen "
            "(„… möchte Mail steuern“)? Dann erst beantworten und nochmal versuchen."),
    9100: "In der Mail-App ist noch kein Postfach eingerichtet (Mail öffnen → Mail → Account hinzufügen).",
    9001: "Der Posteingang hat sich beim Lesen geändert (neue E-Mail). Bitte gleich nochmal versuchen.",
    9500: "Die Mail-App hat das Senden nicht bestätigt. Bitte in der Mail-App nachsehen (Postausgang).",
    9410: ("Dieser Absender ist in der Mail-App nicht eingerichtet - es wurde nichts gesendet. Das Fenster ist offen; "
           "die eingerichteten Adressen zeigt mail_ordner."),
}
# Beim Senden ist nach einer Zeitüberschreitung unklar, ob die Mail-App schon verschickt hat: nie einfach wiederholen.
UNKLAR_GESENDET = ("Unklar, ob die E-Mail verschickt wurde (die Mail-App hat nicht rechtzeitig geantwortet). Bitte NICHT "
                   "einfach nochmal senden, sondern erst in der Mail-App unter „Gesendet“ und „Postausgang“ nachsehen.")
# In diese Ordner verschiebt JARVIS nicht: Papierkorb und Spam werden von der Mail-App geleert - das wäre Löschen.
# Verglichen wird klein geschrieben, mit Leerzeichen statt "-" und "_" ("Junk-E-Mail" -> "junk e mail").
PAPIERKORB = re.compile(r"^(papierkorb|trash|bin|m(ü|ue)ll|deleted( items| messages)?|gel(ö|oe)schte?( objekte| elemente| "
                        r"e ?mails?| nachrichten)?|junk( e ?mail)?|spam|unerw(ü|ue)nscht)$")


def _fehler(stderr):
    text = (stderr or "").strip()
    treffer = _FEHLERNUMMER.search(text)
    nummer = int(treffer.group(1)) if treffer else None
    if nummer in ERKLAERUNG:
        return MailFehler(ERKLAERUNG[nummer], nummer)
    return MailFehler("Die Mail-App meldet: %s" % (text[-300:] or "unbekannter Fehler"), nummer)


def text_vorbereiten(text, mehrzeilig=True):
    """Einheitliche Unicode-Form (NFC), Zeilenenden als LF, keine Steuerzeichen; der Text beginnt ohne Leerzeilen."""
    text = unicodedata.normalize("NFC", text or "").replace("\r\n", "\n").replace("\r", "\n")
    if not mehrzeilig:
        text = " ".join(text.split())
    return _STEUERZEICHEN.sub("", text).lstrip("\n")


def adressen_pruefen(angabe):
    """"a@b.de, c@d.de" -> ["a@b.de", "c@d.de"]. Wirft MailFehler bei ungültigen oder zu vielen Adressen."""
    teile = [t.strip().strip("<>") for t in re.split(r"[,;\s]+", angabe or "") if t.strip()]
    if not teile:
        raise MailFehler("Es fehlt eine Empfängeradresse.")
    falsch = [t for t in teile if not ADRESSE.match(t)]
    if falsch:
        raise MailFehler("Keine gültige E-Mail-Adresse: %s" % ", ".join(falsch[:3]))
    eindeutig = []
    for t in teile:
        if t.lower() not in [e.lower() for e in eindeutig]:
            eindeutig.append(t)
    if len(eindeutig) > MAX_EMPFAENGER:
        raise MailFehler("Höchstens %d Empfänger auf einmal." % MAX_EMPFAENGER)
    return eindeutig


def ids_pruefen(angabe):
    """"12, 13 14" -> [12, 13, 14]."""
    teile = [t for t in re.split(r"[,;\s]+", str(angabe or "")) if t]
    if not teile or not all(_ZAHL.match(t) for t in teile):
        raise MailFehler("Die E-Mail-Nummern müssen Zahlen sein, z. B. 4711 oder 4711, 4712.")
    ids = []
    for t in teile:
        if int(t) not in ids:
            ids.append(int(t))
    if len(ids) > MAX_IDS:
        raise MailFehler("Höchstens %d E-Mails auf einmal." % MAX_IDS)
    return ids


def ordner_pruefen(pfad):
    """Zielordner zum Verschieben: "Kunden" oder "Kunden/2026". Papierkorb und Spam sind ausgeschlossen."""
    teile = [t.strip() for t in (pfad or "").strip().strip("/").split("/")]
    if not teile or any(not t for t in teile):
        raise MailFehler("Bitte einen Ordner angeben, verschachtelt als Oben/Unten (mail_ordner zeigt alle).")
    for teil in teile:
        vergleich = " ".join(re.sub(r"[-_]", " ", re.sub(r"^\[[^\]]*\]\s*", "", teil)).lower().split())
        if PAPIERKORB.match(vergleich):
            raise MailFehler("In Papierkorb oder Spam verschiebt JARVIS nicht - die Mail-App leert diese Ordner, das wäre "
                             "Löschen. Das machst du bitte selbst in der Mail-App.")
    return "/".join(teile)


def datum_kurz(iso):
    try:
        return datetime.datetime.strptime(iso[:19], "%Y-%m-%dT%H:%M:%S").strftime("%d.%m. %H:%M")
    except ValueError:
        return iso or "?"


class MacMail:
    """Dünne Schicht über die Mail-App. Jede Methode ist ein osascript-Aufruf."""

    def __init__(self, timeout=90):
        self.timeout = timeout

    @staticmethod
    def programm():
        fest = os.environ.get("JARVIS_OSASCRIPT")  # nur für Tests
        if fest:
            return fest if os.path.isfile(fest) and os.access(fest, os.X_OK) else None
        return shutil.which("osascript")

    def verfuegbar(self):
        return self.programm() is not None

    def _lauf(self, skript, *argumente):
        programm = self.programm()
        if not programm:
            raise MailFehler("Die E-Mail-Anbindung gibt es nur auf dem Mac (osascript fehlt hier).")
        befehl = [programm, "-e", skript, ANKER] + [str(a) for a in argumente]
        try:
            lauf = subprocess.run(befehl, capture_output=True, text=True, encoding="utf-8", errors="replace",  # noqa: S603
                                  timeout=self.timeout)
        except subprocess.TimeoutExpired:
            raise MailFehler(ERKLAERUNG[-1712], -1712) from None
        except OSError as fehler:
            raise MailFehler("osascript ließ sich nicht starten: %s" % fehler) from None
        if lauf.returncode != 0:
            raise _fehler(lauf.stderr)
        return lauf.stdout.rstrip("\r\n")

    # ------------------------------------------------------------ Lesen ---

    def postfach(self, tage=STANDARD_TAGE, anzahl=STANDARD_ANZAHL):
        """Neueste E-Mails aller Posteingänge: (Liste neueste zuerst, Anzahl im Zeitraum, übersprungene Konten)."""
        tage = max(1, min(MAX_TAGE, int(tage)))
        anzahl = max(1, min(MAX_ANZAHL, int(anzahl)))
        try:
            roh = self._lauf(SKRIPT_POSTFACH, JE_KONTO, tage)
        except MailFehler as fehler:
            if fehler.nummer != 9001:
                raise
            roh = self._lauf(SKRIPT_POSTFACH, JE_KONTO, tage)  # Lesen ist harmlos: einmal neu versuchen
        mails, uebersprungen = [], []
        for satz in roh.split(RS):
            felder = satz.split(US)
            if len(felder) == 2 and felder[0] == "UEBERSPRUNGEN":
                uebersprungen.append(felder[1].strip())
            elif len(felder) == 6 and _ZAHL.match(felder[1].strip()):
                mails.append({"konto": felder[0].strip(), "id": int(felder[1]), "absender": felder[2].strip(),
                              "betreff": felder[3].strip(), "datum": felder[4].strip(),
                              "gelesen": felder[5].strip().lower() == "true"})
        mails.sort(key=lambda m: m["datum"], reverse=True)
        return mails[:anzahl], len(mails), uebersprungen

    def lesen(self, konto, mail_id):
        felder = self._lauf(SKRIPT_LESEN, konto, int(mail_id), MAX_INHALT).split(US, 4)
        if len(felder) != 5:
            raise MailFehler("Die Mail-App hat eine unerwartete Antwort geliefert.")
        absender, an, betreff, datum, inhalt = felder
        return {"konto": konto, "id": int(mail_id), "absender": absender.strip(), "an": an.strip(),
                "betreff": betreff.strip(), "datum": datum.strip(), "inhalt": inhalt}

    def koepfe(self, konto, ids):
        """Absender und Betreff zu E-Mail-Nummern eines Kontos (für die Vorschau beim Verschieben)."""
        ergebnis = []
        for satz in self._lauf(SKRIPT_KOEPFE, konto, *ids).split(RS):
            felder = satz.split(US)
            if len(felder) == 3 and _ZAHL.match(felder[0].strip()):
                ergebnis.append({"id": int(felder[0]), "absender": felder[1].strip(), "betreff": felder[2].strip()})
        return ergebnis

    def ordner(self):
        """([(Konto, Ordnerpfad)], {Konto: "Adressen"}) - verschachtelte Ordner als "Oben/Unten"."""
        ergebnis, adressen = [], {}
        for satz in self._lauf(SKRIPT_ORDNER).split(RS):
            felder = satz.split(US)
            if len(felder) == 3 and felder[0] == "KONTO":
                adressen[felder[1].strip()] = felder[2].strip()
            elif len(felder) == 2 and felder[1].strip():
                ergebnis.append((felder[0].strip(), felder[1].strip()))
        return ergebnis, adressen

    # ---------------------------------------------------------- Schreiben ---

    def nachricht(self, modus, empfaenger, betreff, inhalt, von=""):
        """modus "entwurf": öffnet ein Fenster zum Prüfen; "senden": schickt ab (nur nach Freigabe aufrufen).

        ``von``: Absenderadresse; leer = Standard-Absender der Mail-App. Gibt {"status", "absender"} zurück."""
        if modus not in ("entwurf", "senden"):
            raise ValueError(modus)
        von = adressen_pruefen(von)[0] if von else ""
        try:
            antwort = self._lauf(SKRIPT_NACHRICHT, modus, text_vorbereiten(betreff, mehrzeilig=False),
                                 text_vorbereiten(inhalt), von, *adressen_pruefen(", ".join(empfaenger)))
        except MailFehler as fehler:
            if modus == "senden" and fehler.nummer == -1712:
                raise MailFehler(UNKLAR_GESENDET, -1712) from None  # nie zum Wiederholen auffordern
            raise
        status, _, absender = antwort.strip().partition(US)
        if status != ("gesendet" if modus == "senden" else "entwurf"):
            raise MailFehler("Die Mail-App hat das nicht bestätigt (Antwort: %r)." % antwort[:100])
        return {"status": status, "absender": absender.strip()}

    def verschieben(self, konto, ordner, ids):
        ergebnis = []
        for satz in self._lauf(SKRIPT_VERSCHIEBEN, konto, ordner, *ids).split(RS):
            felder = satz.split(US)
            if len(felder) == 2 and _ZAHL.match(felder[0].strip()):
                ergebnis.append((int(felder[0]), felder[1].strip()))
        return ergebnis
