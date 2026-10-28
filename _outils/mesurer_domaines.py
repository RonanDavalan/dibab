#!/usr/bin/env python3
"""Mesure du domaine sur les documents réels des coffres : agrégats seuls."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from modules import mesure_domaines  # noqa: E402

if __name__ == "__main__":
    sys.exit(mesure_domaines.main())
