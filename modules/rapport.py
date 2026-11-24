"""Rapport de session : comptes par action, échecs et durée, sans nom de document ni texte."""

import json
import os
import time
from collections import Counter
from pathlib import Path

from modules.deplacement import creer_dossiers_prives

SCHEMA_VERSION = 1


class Rapport:
    def __init__(self, session, mode):
        self.session = session
        self.mode = mode
        self.debut = time.monotonic()
        self.comptes = Counter()
        self.rapatries = 0
        self.deposes_imap = 0

    def compter(self, action):
        self.comptes[action] += 1

    def ecrire(self, dossier_sessions):
        chemin = Path(dossier_sessions) / f"rapport_{self.session}.json"
        creer_dossiers_prives(chemin.parent)
        contenu = {"schema_version": SCHEMA_VERSION, "session": self.session, "mode": self.mode,
                   "duree_secondes": round(time.monotonic() - self.debut, 3), "actions": dict(self.comptes),
                   "echecs": self.comptes.get("echec", 0), "rapatries": self.rapatries,
                   "deposes_imap": self.deposes_imap}
        descripteur = os.open(chemin, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(descripteur, "w", encoding="utf-8") as f:
            json.dump(contenu, f, indent=2, sort_keys=True)
        return chemin
