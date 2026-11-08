#!/bin/bash
# Doppelklick auf dem Mac: zeigt ein Menü für den Überlebens-Agenten.
# Nur Python 3 nötig (auf dem Mac meist schon da). Nichts wird gesendet oder bezahlt.
cd "$(dirname "$0")" || exit 1

if ! command -v python3 >/dev/null 2>&1; then
  echo "Python 3 fehlt. Am einfachsten: im Terminal 'xcode-select --install' eingeben."
  read -r -p "Enter zum Schließen." _
  exit 1
fi

while true; do
  echo
  echo "=== Überlebens-Agent ==="
  echo " 1) Stand ansehen (Geld, nächste Wochenmiete)"
  echo " 2) Agent arbeiten lassen (Claude denkt, einmal pro Stunde, kostet Abo-Nutzung)"
  echo " 3) Anträge des Agenten ansehen"
  echo " 4) Antrag erteilen oder ablehnen"
  echo " 5) Echte Einnahme buchen (Betrag in Euro, wie auf dem Konto)"
  echo " 6) Agent anlegen (nur einmal - stirbt er, gibt es keinen neuen)"
  echo " 0) Beenden"
  read -r -p "Auswahl: " wahl
  case "$wahl" in
    1) python3 -m ueberleben echt status ;;
    2) python3 -m ueberleben echt runde ;;
    3) python3 -m ueberleben echt freigaben ;;
    4) read -r -p "Nummer: " nr; read -r -p "ja oder nein: " jn
       if [ "$jn" = "ja" ] || [ "$jn" = "nein" ]; then python3 -m ueberleben echt "$jn" "$nr"; else echo "Bitte 'ja' oder 'nein'."; fi ;;
    5) read -r -p "Agent (z. B. A1): " ag; read -r -p "Betrag in Euro (z. B. 12,50): " be; read -r -p "Wofür: " wo
       read -r -p "Fremdwährung? (z. B. 13,40 USD, sonst leer): " orig
       if [ -n "$orig" ]; then python3 -m ueberleben echt einnahme "$ag" "$be" "$wo" --original "$orig"
       else python3 -m ueberleben echt einnahme "$ag" "$be" "$wo"; fi ;;
    6) python3 -m ueberleben echt start ;;
    0) exit 0 ;;
    *) echo "Bitte eine Zahl von 0 bis 6." ;;
  esac
done
