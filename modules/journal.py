# modules/journal.py — Écriture du journal de session JSONL
#
# Un journal de session est un fichier .jsonl créé au démarrage de dibab.py.
# Chaque action (démarrage, scan, candidat, déplacement, etc.) y est consignée
# en une ligne JSON. La rotation est faite par modules/rotation.py.

import json
import os
from datetime import datetime
from pathlib import Path

from modules.deplacement import creer_dossiers_prives
from modules.messages import pour_journal


class JournalSession:
    """Journal d'une session unique. Ouvre le fichier en mode append."""

    def __init__(self, chemin_session, identifiant_session):
        self.chemin = Path(chemin_session)
        self.identifiant_session = identifiant_session
        creer_dossiers_prives(self.chemin.parent)

    def ajouter(self, evenement, **champs):
        """Ajoute un enregistrement au journal de session.

        evenement : nom court de l'événement (str).
        champs    : tout couple clé/valeur sérialisable en JSON.
        """
        enregistrement = {
            "timestamp": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
            "session": self.identifiant_session,
            "evenement": evenement,
        }
        enregistrement.update(pour_journal(champs))
        with os.fdopen(os.open(self.chemin, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600), "a", encoding="utf-8") as f:
            f.write(json.dumps(enregistrement, ensure_ascii=False) + "\n")


class JournalAbsent:
    """Journal qui n'écrit rien : la session continue sans laisser de trace en clair."""

    chemin = None

    def ajouter(self, evenement, **champs):
        pass
