"""Déplacement sûr d'un document vers son plan : copie, vérification SHA256, retrait de la source.

Un coffre est un autre système de fichiers : un document ne bouge jamais par `rename`. La source
n'est retirée que lorsque chaque copie a la même empreinte qu'elle, et rien n'est jamais écrasé.
Une copie interrompue laisse la source intacte et ne laisse aucune copie dans la destination.
"""

import os
import shutil
from dataclasses import dataclass
from pathlib import Path

from modules import domaines
from modules.pieces_communes import empreinte_sha256
from modules.messages import texte_de, traduire

CLASSE = "classe"
A_VERIFIER = "a_verifier"
DOUBLON = "doublon"
ECHEC = "echec"


@dataclass(frozen=True)
class Deplacement:
    action: str
    source: Path
    destinations: tuple = ()
    empreinte: str = None
    raison: str = ""


class IndexEmpreintes:
    """Empreintes des fichiers d'une zone d'un coffre, calculées à la demande.

    Seuls les fichiers de même taille que le document sont hachés : une zone de plusieurs
    milliers de pièces ne se relit pas en entier pour chaque document.
    """

    def __init__(self, dossier):
        self.tailles = {}
        self.empreintes = {}
        for racine, _, noms in os.walk(dossier):
            for nom in noms:
                chemin = Path(racine) / nom
                try:
                    self.tailles.setdefault(chemin.stat().st_size, []).append(chemin)
                except OSError:
                    continue

    def trouver(self, empreinte, taille):
        """Rend le chemin d'un fichier déjà présent de même empreinte, ou None."""
        for chemin in self.tailles.get(taille, ()):
            if chemin not in self.empreintes:
                try:
                    self.empreintes[chemin] = empreinte_sha256(chemin)
                except OSError:
                    continue
            if self.empreintes[chemin] == empreinte:
                return chemin
        return None

    def ajouter(self, chemin, empreinte, taille):
        self.tailles.setdefault(taille, []).append(chemin)
        self.empreintes[chemin] = empreinte


class Registre:
    """Un index d'empreintes par zone, construit au premier besoin et tenu à jour pendant la session."""

    def __init__(self):
        self.index = {}

    def de(self, dossier):
        if dossier not in self.index:
            self.index[dossier] = IndexEmpreintes(dossier)
        return self.index[dossier]


def chemin_libre(chemin, modele_suffixe):
    """Rend `chemin`, ou sa variante suffixée la plus petite qui n'existe pas encore."""
    if not chemin.exists():
        return chemin
    n = 2
    while True:
        variante = chemin.with_name(f"{chemin.stem}{modele_suffixe.format(n=n)}{chemin.suffix}")
        if not variante.exists():
            return variante
        n += 1


def copier_verifie(source, destination, empreinte, copier=shutil.copy2):
    """Copie `source` sous un nom provisoire, vérifie l'empreinte, puis donne son nom à la copie.

    Le nom provisoire commence par un point : le scanner l'ignore si le processus meurt entre les deux.
    """
    provisoire = destination.with_name(f".dibab-partiel-{os.getpid()}-{destination.name}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    try:
        copier(source, provisoire)
        if empreinte_sha256(provisoire) != empreinte:
            raise OSError(traduire("copie_empreinte_differente", cible=destination.name))
        if destination.exists():
            raise OSError(traduire("copie_destination_occupee", cible=destination.name))
        os.rename(provisoire, destination)
    except BaseException:
        provisoire.unlink(missing_ok=True)
        raise


def _poser(source, destination, empreinte, taille, index, copier):
    copier_verifie(source, destination, empreinte, copier)
    index.ajouter(destination, empreinte, taille)


def prevoir(source, plan, configuration, registre):
    """Rend l'action que `deplacer` entreprendrait, sans rien écrire : classé, à vérifier ou doublon."""
    empreinte = plan.empreinte or empreinte_sha256(source)
    taille = Path(source).stat().st_size
    zones = [domaines.dossier_cible(cible, configuration["destinations"]) for cible in plan.cibles]
    if all(registre.de(zone).trouver(empreinte, taille) for zone in zones):
        return DOUBLON
    return A_VERIFIER if plan.cibles[0].zone == domaines.A_VERIFIER else CLASSE


def deplacer(source, plan, configuration, registre, copier=shutil.copy2):
    """Déplace `source` selon `plan` et rend un `Deplacement` ; la source n'est retirée qu'après vérification."""
    source = Path(source)
    modele_suffixe = configuration["nommage"]["suffixe_collision"]
    try:
        empreinte = plan.empreinte or empreinte_sha256(source)
        taille = source.stat().st_size
        zones = [domaines.dossier_cible(cible, configuration["destinations"]) for cible in plan.cibles]
        manquantes = [(zone, chemin) for zone, chemin in zip(zones, plan.chemins)
                      if registre.de(zone).trouver(empreinte, taille) is None]
        faites = []
        try:
            if manquantes:
                for zone, chemin in manquantes:
                    cible_libre = chemin_libre(chemin, modele_suffixe)
                    _poser(source, cible_libre, empreinte, taille, registre.de(zone), copier)
                    faites.append(cible_libre)
                action = A_VERIFIER if plan.cibles[0].zone == domaines.A_VERIFIER else CLASSE
            else:
                racine = Path(configuration["destinations"][plan.cibles[0].coffre]["racine"])
                doublon = chemin_libre(racine / configuration["destination"]["repertoire_doublon"] / plan.nom, modele_suffixe)
                copier_verifie(source, doublon, empreinte, copier)
                faites.append(doublon)
                action = DOUBLON
            if empreinte_sha256(source) != empreinte:
                raise OSError(traduire("copie_source_changee"))
            source.unlink()
        except BaseException:
            for chemin in faites:
                chemin.unlink(missing_ok=True)
            raise
        return Deplacement(action, source, tuple(faites), empreinte)
    except OSError as erreur:
        return Deplacement(ECHEC, source, raison=texte_de(erreur))
