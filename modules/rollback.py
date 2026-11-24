"""Annulation d'une session : chaque source revient à sa place par copie vérifiée, puis la destination est retirée.

Rien n'est retiré tant que toutes les destinations de l'action ne sont pas intactes et que la source
n'est pas restituée avec la bonne empreinte : une action en échec laisse tout en place.
"""

from dataclasses import dataclass
from pathlib import Path

from modules import journal_actions
from modules.deplacement import copier_verifie
from modules.pieces_communes import empreinte_sha256
from modules.messages import texte_de, traduire


@dataclass(frozen=True)
class Annulation:
    id_action: str
    annulee: bool
    raison: str = ""


def derniere_session(actions):
    return actions[-1]["session"] if actions else None


def _annuler_une(action):
    destinations = [Path(d["chemin"]) for d in action["destinations"]]
    for destination, attendue in zip(destinations, (d["empreinte_apres"] for d in action["destinations"])):
        if not destination.is_file():
            return traduire("rollback_destination_introuvable")
        if empreinte_sha256(destination) != attendue:
            return traduire("rollback_destination_modifiee")
    origine = Path(action["origine"])
    if origine.exists():
        return traduire("rollback_source_reoccupee")
    try:
        copier_verifie(destinations[0], origine, action["empreinte_avant"])
        for destination in destinations:
            destination.unlink()
    except OSError as erreur:
        return traduire("rollback_restitution_impossible", erreur=texte_de(erreur))
    return ""


def identifiant_de_session(valeur):
    """Rend l'identifiant nu d'une session, que l'on ait donné cet identifiant ou le nom (ou le chemin) de son fichier."""
    if not valeur:
        return valeur
    nom = Path(valeur).name
    return nom.removeprefix("session_").removesuffix(".jsonl")


def session_connue(journal, session):
    """Vrai si une action du journal porte cette session, annulée ou non."""
    return any(ligne.get("session") == session and ligne.get("evenement") == journal_actions.ACTION
               for ligne in journal_actions.lire_lignes(journal.chemin))


def annuler_session(journal, session=None):
    """Annule, de la plus récente à la plus ancienne, les actions actives de `session` (la dernière par défaut)."""
    actions = journal_actions.actions_actives(journal_actions.lire_lignes(journal.chemin))
    session = session or derniere_session(actions)
    resultats = []
    for action in reversed([a for a in actions if a["session"] == session]):
        raison = _annuler_une(action)
        if raison:
            journal.marquer_echec_annulation(action["id_action"], raison)
        else:
            journal.marquer_annulee(action["id_action"])
        resultats.append(Annulation(action["id_action"], not raison, raison))
    return session, resultats
