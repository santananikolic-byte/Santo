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
  echo " 1) Simulation: 1000 Leben mit Spielgeld"
  echo " 2) Ein Leben Schritt für Schritt ansehen"
  echo " 3) Echt-Modus anlegen"
  echo " 4) Echt-Modus: eine Runde (Claude denkt, kostet Abo-Nutzung)"
  echo " 5) Echt-Modus: Stand ansehen"
  echo " 6) Echt-Modus: Freigaben ansehen"
  echo " 7) Echt-Modus: Freigabe erteilen oder ablehnen"
  echo " 8) Echt-Modus: echte Einnahme buchen"
  echo " 0) Beenden"
  read -r -p "Auswahl: " wahl
  case "$wahl" in
    1) python3 -m ueberleben simulation ;;
    2) python3 -m ueberleben leben | less -R ;;
    3) python3 -m ueberleben echt start ;;
    4) python3 -m ueberleben echt runde ;;
    5) python3 -m ueberleben echt status ;;
    6) python3 -m ueberleben echt freigaben ;;
    7) read -r -p "Nummer: " nr; read -r -p "ja oder nein: " jn
       if [ "$jn" = "ja" ] || [ "$jn" = "nein" ]; then python3 -m ueberleben echt "$jn" "$nr"; else echo "Bitte 'ja' oder 'nein'."; fi ;;
    8) read -r -p "Agent (z. B. A1): " ag; read -r -p "Betrag (z. B. 12,50): " be; read -r -p "Wofür: " wo
       python3 -m ueberleben echt einnahme "$ag" "$be" "$wo" ;;
    0) exit 0 ;;
    *) echo "Bitte eine Zahl von 0 bis 8." ;;
  esac
done
