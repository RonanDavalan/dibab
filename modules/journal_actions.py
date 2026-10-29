"""Journal des actions de classement (`journal.jsonl`) : une ligne par déplacement, relue par le rollback.

Le fichier n'est jamais réécrit : une annulation s'ajoute en fin de journal, ce qui garde la trace
de l'action et rend la rotation sûre. Aucune ligne ne porte de texte de document.
"""

import json
import os
import uuid
from datetime import datetime
from pathlib import Path

from modules.messages import pour_journal
from modules.pieces_communes import empreinte_sha256

SCHEMA_VERSION = 1
ACTION = "action"
ANNULATION = "annulation"
ECHEC_ANNULATION = "echec_annulation"


class JournalActions:
    def __init__(self, chemin, session):
        self.chemin = Path(chemin)
        self.session = session

    def _ecrire(self, enregistrement):
        enregistrement = {"schema_version": SCHEMA_VERSION, "session": self.session,
                          "timestamp": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"), **pour_journal(enregistrement)}
        self.chemin.parent.mkdir(parents=True, exist_ok=True)
        descripteur = os.open(self.chemin, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600)
        with os.fdopen(descripteur, "a", encoding="utf-8") as f:
            f.write(json.dumps(enregistrement, ensure_ascii=False) + "\n")

    def enregistrer_deplacement(self, deplacement, domaine):
        """Inscrit un déplacement réussi ; une pièce commune est une seule action à deux destinations."""
        identifiant = uuid.uuid4().hex
        self._ecrire({
            "evenement": ACTION, "id_action": identifiant, "action": deplacement.action, "domaine": domaine,
            "origine": str(deplacement.source), "empreinte_avant": deplacement.empreinte,
            "destinations": [{"chemin": str(d), "empreinte_apres": empreinte_sha256(d)} for d in deplacement.destinations],
        })
        return identifiant

    def marquer_annulee(self, id_action):
        self._ecrire({"evenement": ANNULATION, "id_action": id_action})

    def marquer_echec_annulation(self, id_action, raison):
        self._ecrire({"evenement": ECHEC_ANNULATION, "id_action": id_action, "raison": raison})


def fichiers_du_journal(chemin):
    """Le journal et ses archives, du plus ancien au plus récent."""
    chemin = Path(chemin)
    archives = []
    for archive in chemin.parent.glob(f"{chemin.stem}.*{chemin.suffix}"):
        numero = archive.name[len(chemin.stem) + 1:-len(chemin.suffix)]
        if numero.isdigit():
            archives.append((int(numero), archive))
    ordonnees = [archive for _, archive in sorted(archives, reverse=True)]
    return ordonnees + ([chemin] if chemin.exists() else [])


def lire_lignes_fichier(fichier):
    lignes = []
    for brut in Path(fichier).read_text(encoding="utf-8").splitlines():
        try:
            ligne = json.loads(brut)
        except ValueError:
            continue
        if isinstance(ligne, dict) and ligne.get("schema_version", 1) <= SCHEMA_VERSION:
            lignes.append(ligne)
    return lignes


def lire_lignes(chemin):
    return [ligne for fichier in fichiers_du_journal(chemin) for ligne in lire_lignes_fichier(fichier)]


def actions_actives(lignes):
    """Les actions que rien n'a annulées, dans l'ordre où elles ont eu lieu."""
    annulees = {ligne["id_action"] for ligne in lignes if ligne.get("evenement") == ANNULATION}
    return [ligne for ligne in lignes if ligne.get("evenement") == ACTION and ligne["id_action"] not in annulees]
