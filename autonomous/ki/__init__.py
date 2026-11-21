# -*- coding: utf-8 -*-
"""KI-Schicht – bewusst getrennt von Agentenlogik, Gedächtnis und Werkzeugsystem (Protokoll Punkt 2).

- anbieter.py  Austauschbare Modell-Anbieter: „keiner“ (Standard) und „ollama“ (nur auf diesem Rechner).
               Ein externer oder kostenpflichtiger Anbieter ist NICHT angebunden und wird nie als Rückfall genutzt.
- vorlagen.py  Prompt-Vorlagen (nur Text). Fremddaten stehen darin als markierte Daten, nie als Anweisung.
- ausgabe.py   Modellausgabe säubern und kennzeichnen. Sie gilt als NICHT vertrauenswürdig: nur Text,
               nie Befehl – sie kann keine Aktion auslösen, keine Rechte ändern und keine Freigabe umgehen.

Agenten sprechen nie direkt mit einem Anbieter, sondern über modell.Modellschicht (Limit, Protokoll).
"""
