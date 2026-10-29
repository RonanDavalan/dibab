# conftest.py — Configuration partagée pytest
#
# Permet d'importer les modules de skrivagner sans bricolage de PYTHONPATH.

import sys
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE))


import pytest


@pytest.fixture(autouse=True)
def environnement_isole(monkeypatch, tmp_path_factory):
    """Aucun essai ne lit la configuration ni n'écrit l'état de l'utilisateur qui lance la suite."""
    monkeypatch.delenv("SKRIVAGNER_CONFIG", raising=False)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path_factory.mktemp("xdg-config")))
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path_factory.mktemp("xdg-etat")))
