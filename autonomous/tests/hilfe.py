# -*- coding: utf-8 -*-
"""Testhilfe: jeder Test bekommt einen eigenen, leeren Datenordner."""

import os
import shutil
import tempfile
import unittest


class KernTest(unittest.TestCase):
    def setUp(self):
        self._ordner = tempfile.mkdtemp(prefix="autonomous-test-")
        self._alt = os.environ.get("AUTONOMOUS_DATEN")
        os.environ["AUTONOMOUS_DATEN"] = self._ordner
        from autonomous.kern import Kern
        from autonomous.orchestrator import Orchestrator
        self.kern = Kern()
        self.orch = Orchestrator(self.kern)
        self.kern.orchestrator = self.orch

    def neu_starten(self):
        """Simuliert einen Neustart: Kern schließen und mit derselben Datenbank neu öffnen."""
        from autonomous.kern import Kern
        from autonomous.orchestrator import Orchestrator
        self.kern.db.schliessen()
        self.kern = Kern()
        self.orch = Orchestrator(self.kern)
        self.kern.orchestrator = self.orch

    def tearDown(self):
        try:
            self.orch.stoppen(1)
            self.kern.db.schliessen()
        except Exception:
            pass
        if self._alt is None:
            os.environ.pop("AUTONOMOUS_DATEN", None)
        else:
            os.environ["AUTONOMOUS_DATEN"] = self._alt
        shutil.rmtree(self._ordner, ignore_errors=True)

    def api(self, methode, pfad, body=None, query=None):
        from autonomous import api
        try:
            from autonomous import api_vertrieb  # noqa: F401
        except ImportError:
            pass
        funktion, parameter = api.finden(methode, pfad)
        return funktion(self.kern, {"pfad": pfad, "parameter": parameter, "query": query or {}, "body": body or {}})
