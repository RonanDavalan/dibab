"""Plan de destination d'un document, et copie des pièces communes dans les deux coffres.

Une pièce commune (identité, domicile, RIB) est copiée, jamais liée : un lien d'un
coffre à l'autre casse dès que l'un des deux est fermé. Les deux copies portent le
même nom normalisé et la même empreinte SHA256.
"""

import hashlib
import shutil
from dataclasses import dataclass
from pathlib import Path

from modules import domaines, nommage
from modules.messages import texte_de, traduire


class ErreurCopie(Exception):
    """Une copie n'a pas pu être faite ou vérifiée ; la source n'est jamais touchée."""


@dataclass(frozen=True)
class Plan:
    nom: str
    cibles: tuple
    chemins: tuple
    empreinte: str = None


def empreinte_sha256(chemin):
    condense = hashlib.sha256()
    with open(chemin, "rb") as f:
        for bloc in iter(lambda: f.read(1024 * 1024), b""):
            condense.update(bloc)
    return condense.hexdigest()


def planifier(source, verdict, configuration, date_repli):
    """Rend le Plan d'un document, ou None s'il ne bouge pas (non administratif).

    L'empreinte n'est calculée que pour une pièce commune, la seule dont le plan
    la garantit identique sur deux chemins.
    """
    cibles = domaines.router(verdict, configuration.get("pieces_communes", ()))
    if not cibles:
        return None
    a_verifier = cibles[0].zone == domaines.A_VERIFIER
    nom = nommage.nommer(configuration["nommage"], verdict, Path(source).suffix, date_repli, a_verifier, Path(source).name)
    chemins = tuple(domaines.dossier_cible(cible, configuration["destinations"]) / nom for cible in cibles)
    commune = len(cibles) > 1
    return Plan(nom, tuple(cibles), chemins, empreinte_sha256(source) if commune else None)


def copier_verifier(source, plan):
    """Copie `source` vers chaque chemin du plan et vérifie l'empreinte de chaque copie.

    N'écrase rien : si un chemin existe déjà, rien n'est copié. Sur échec de
    vérification, les copies faites par cet appel sont retirées, pour ne pas
    laisser une pièce corrompue dans un coffre ; la source reste intacte.
    """
    existants = [str(chemin) for chemin in plan.chemins if chemin.exists()]
    if existants:
        raise ErreurCopie(traduire("pieces_destination_occupee", chemins=", ".join(existants)))
    attendue = plan.empreinte or empreinte_sha256(source)
    faites = []
    try:
        for chemin in plan.chemins:
            chemin.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, chemin)
            faites.append(chemin)
            if empreinte_sha256(chemin) != attendue:
                raise ErreurCopie(traduire("pieces_empreinte_differente", chemin=chemin))
    except (OSError, ErreurCopie) as erreur:
        for chemin in faites:
            chemin.unlink(missing_ok=True)
        if isinstance(erreur, ErreurCopie):
            raise
        raise ErreurCopie(traduire("pieces_copie_impossible", erreur=texte_de(erreur))) from erreur
    return attendue
