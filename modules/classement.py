"""Chemin de destination d'un document : racine du coffre, zone, sous-arborescence du domaine, nom normalisé.

La sous-arborescence de chaque domaine est un gabarit de `arborescence` dans la configuration
(`{personne}`, `{annee}`, `{categorie}`) : elle reprend celle qui existe déjà dans le coffre du
domaine, sans que le code connaisse un nom de personne ou de client. Un document à vérifier reste à
plat dans sa zone : il attend un tri à la main.
"""

import dataclasses
from pathlib import Path

from modules import domaines, pieces_communes

SEGMENT_REPLI = "Divers"


def _segment(valeur, espaces_vers):
    # Un segment vient du texte d'un document ou d'une liste de la configuration : ni séparateur
    # de chemin ni point seul, sinon le chemin sortirait de la destination.
    texte = str(valeur).strip().replace("/", espaces_vers).replace("\\", espaces_vers).replace(" ", espaces_vers)
    return SEGMENT_REPLI if texte.strip(".") == "" else texte


def sous_arborescence(cible, verdict, configuration, date_repli):
    """Rend le chemin relatif (sous la zone) où une cible range le document."""
    if cible.zone != domaines.CLASSEMENT:
        return Path()
    arborescence = configuration["arborescence"]
    espaces_vers = configuration["nommage"].get("espaces_vers", "-")
    annee = verdict.date.year if verdict.date else date_repli.year
    personne = verdict.personne if verdict.personne in configuration.get("personnes", ()) else arborescence["personne_inconnue"]
    gabarit = arborescence[cible.coffre]
    valeurs = {"personne": personne, "annee": annee, "categorie": verdict.categorie}
    return Path(*(_segment(segment.format(**valeurs), espaces_vers) for segment in gabarit.split("/") if segment))


def planifier(source, verdict, configuration, date_repli):
    """Rend le `Plan` complet d'un document (une ou deux cibles), ou None s'il ne bouge pas."""
    plan = pieces_communes.planifier(source, verdict, configuration, date_repli)
    if plan is None:
        return None
    chemins = tuple(
        domaines.dossier_cible(cible, configuration["destinations"])
        / sous_arborescence(cible, verdict, configuration, date_repli) / plan.nom
        for cible in plan.cibles
    )
    return dataclasses.replace(plan, chemins=chemins)
