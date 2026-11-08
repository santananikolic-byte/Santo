#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Prüfungen am Code selbst.

    python3 -m unittest tests.test_code -v
"""

import ast
import collections
import os
import unittest

from tests.hilfen import WURZEL


class CodeTest(unittest.TestCase):
    def test_keine_doppelten_namen_auf_oberster_ebene(self):
        """Eine zweite Funktion gleichen Namens überschreibt still die erste - so geschehen mit _loeschen_vorschau
        (Termine) und datei_loeschen. Der Linter hat es nicht gemeldet, darum dieser Test."""
        ordner = os.path.join(WURZEL, "jarvis_core")
        for name in sorted(os.listdir(ordner)):
            if not name.endswith(".py"):
                continue
            with open(os.path.join(ordner, name), encoding="utf-8") as f:
                baum = ast.parse(f.read(), name)
            namen = [k.name for k in baum.body if isinstance(k, (ast.FunctionDef, ast.ClassDef))]
            doppelt = [n for n, anzahl in collections.Counter(namen).items() if anzahl > 1]
            with self.subTest(datei=name):
                self.assertEqual(doppelt, [])


if __name__ == "__main__":
    unittest.main()
