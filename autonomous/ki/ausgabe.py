# -*- coding: utf-8 -*-
"""Modellausgabe ist NICHT vertrauenswürdig: nur säubern, kürzen und kennzeichnen – nie auswerten oder ausführen."""

import re

KENNZEICHNUNG = "KI-Entwurf – ungeprüft, lokales Modell %s"
_STEUER = re.compile(r"[\x00-\x08\x0b-\x1f\x7f​-‏‪-‮⁦-⁩﻿]")


def saeubern(text, max_zeichen):
    t = _STEUER.sub("", str(text or "")).replace("\r\n", "\n").replace("\r", "\n").strip()
    t = re.sub(r"\n{3,}", "\n\n", t)
    return t[:max(0, int(max_zeichen))]


def kennzeichnen(text, modell):
    return {"text": text, "kennzeichnung": KENNZEICHNUNG % modell, "ungeprueft": True,
            "quelle": "lokales Modell (%s)" % modell}
