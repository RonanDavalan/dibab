"""Preuve qu'un coffre est monté avant d'y écrire.

Un coffre fermé laisse un dossier de montage nu sur le disque en clair : y écrire
déposerait des documents administratifs non chiffrés. La preuve est le type du
système de fichiers que `findmnt` rend pour la racine exacte du coffre.
"""

import os
import subprocess
from dataclasses import dataclass
from pathlib import Path

TYPE_COFFRE = "fuse.gocryptfs"


@dataclass(frozen=True)
class EtatCoffre:
    domaine: str
    racine: Path
    monte: bool
    raison: str = ""


def type_systeme_fichiers(racine, executer=subprocess.run):
    """Rend le type de système de fichiers de `racine`, ou None si `findmnt` n'en rend pas."""
    try:
        resultat = executer(["findmnt", "-n", "-T", str(racine), "-o", "FSTYPE"],
                            capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.TimeoutExpired):
        return None
    if resultat.returncode != 0:
        return None
    return resultat.stdout.strip() or None


def verifier_coffre(domaine, racine, executer=subprocess.run):
    racine = Path(racine)
    if not racine.is_dir():
        return EtatCoffre(domaine, racine, False, "répertoire introuvable")
    type_trouve = type_systeme_fichiers(racine, executer)
    if type_trouve != TYPE_COFFRE:
        return EtatCoffre(domaine, racine, False,
                          f"coffre non monté (type {type_trouve or 'inconnu'}, attendu {TYPE_COFFRE})")
    if not os.access(racine, os.W_OK):
        return EtatCoffre(domaine, racine, False, "non accessible en écriture")
    return EtatCoffre(domaine, racine, True)


def verifier_coffres(destinations, executer=subprocess.run):
    """Rend un EtatCoffre par domaine de la table `destinations`."""
    return [verifier_coffre(domaine, destination["racine"], executer)
            for domaine, destination in destinations.items()]


def coffre_non_monte_contenant(chemin, etats):
    """Rend l'état du coffre non prouvé qui contient `chemin`, ou None."""
    chemin = Path(chemin)
    for etat in etats:
        if not etat.monte and (chemin == etat.racine or etat.racine in chemin.parents):
            return etat
    return None
