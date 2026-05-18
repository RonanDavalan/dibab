# conftest.py — Configuration partagée pytest
#
# Permet d'importer les modules de skrivagner sans bricolage de PYTHONPATH.

import sys
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE))
