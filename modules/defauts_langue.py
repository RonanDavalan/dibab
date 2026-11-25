"""Valeurs par défaut des noms de dossiers et de préfixes, selon la langue choisie.

Une seule table porte ces valeurs : l'initialisation y prend celles de la langue de la session, et aucun
autre module ne les écrit en dur. Les clés de configuration, elles, ne changent jamais (loi « Immuabilité
des identifiants techniques ») ; une configuration existante n'est jamais réécrite.
"""

import copy

from modules.messages import LANGUE_SOURCE

DEFAUTS = {
    "en": {
        "sous_repertoire_a_verifier": "TO_CHECK",
        "prefixe_a_verifier": "[TO_CHECK]",
        "repertoire_doublon": "duplicate",
    },
    "fr": {
        "sous_repertoire_a_verifier": "À_VÉRIFIER",
        "prefixe_a_verifier": "[À_VÉRIFIER]",
        "repertoire_doublon": "doublon",
    },
    "de": {
        "sous_repertoire_a_verifier": "ZU_PRÜFEN",
        "prefixe_a_verifier": "[ZU_PRÜFEN]",
        "repertoire_doublon": "Duplikat",
    },
    "es": {
        "sous_repertoire_a_verifier": "POR_VERIFICAR",
        "prefixe_a_verifier": "[POR_VERIFICAR]",
        "repertoire_doublon": "duplicado",
    },
}

# Les listes qui doivent exclure le dossier des doublons : le nom est une donnée de l'utilisateur, donc
# il suit la valeur de `destination.repertoire_doublon` au lieu d'être écrit une seconde fois.
_LISTES_EXCLUSIONS = (
    ("inventaire", "exclusions"),
    ("scan", "exclusions_automatiques"),
    ("mesure", "exclusions"),
)


def valeurs(langue=None):
    """Rend les valeurs par défaut de `langue`, ou celles de l'anglais pour une langue inconnue."""
    return dict(DEFAUTS.get(langue or LANGUE_SOURCE, DEFAUTS[LANGUE_SOURCE]))


def _remplacer_doublon(configuration, ancien, nouveau):
    """Remplace `ancien` par `nouveau` dans chaque liste d'exclusions, et ajoute `nouveau` s'il manque."""
    for bloc, cle in _LISTES_EXCLUSIONS:
        section = configuration.get(bloc)
        if not isinstance(section, dict):
            continue
        liste = section.get(cle)
        if not isinstance(liste, list):
            continue
        remplaces = []
        for element in liste:
            valeur = nouveau if element == ancien else element
            if valeur not in remplaces:
                remplaces.append(valeur)
        if nouveau not in remplaces:
            remplaces.append(nouveau)
        configuration[bloc][cle] = remplaces


def appliquer(configuration, langue=None):
    """Rend une copie de `configuration` dont les noms de dossiers et le préfixe sont ceux de `langue`."""
    valeurs_langue = valeurs(langue)
    resultat = copy.deepcopy(configuration)
    destination = resultat.setdefault("destination", {})
    ancien_doublon = destination.get("repertoire_doublon")
    destination["repertoire_doublon"] = valeurs_langue["repertoire_doublon"]
    resultat.setdefault("nommage", {})["prefixe_a_verifier"] = valeurs_langue["prefixe_a_verifier"]
    for coffre in resultat.setdefault("destinations", {}).values():
        coffre["sous_repertoire_a_verifier"] = valeurs_langue["sous_repertoire_a_verifier"]
    _remplacer_doublon(resultat, ancien_doublon, valeurs_langue["repertoire_doublon"])
    return resultat
