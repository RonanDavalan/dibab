"""Résolution des modèles Ollama par rôle.

Le code ne nomme aucun modèle : `config.json` donne, pour chaque rôle, une liste
de préférences ; le premier modèle réellement installé l'emporte.
"""

import json
import urllib.error
import urllib.request
from modules.messages import texte_de, traduire


# Rôles dont l'absence ne bloque rien : sans eux, le tri passe par le rôle `tri_rapide`.
ROLES_FACULTATIFS = ("tri_decision", "objet")


class ModeleIndisponible(Exception):
    """Un rôle n'a aucun modèle installé, ou Ollama ne répond pas."""


def lister_capacites(url, timeout):
    """Rend {nom: capacités} d'après `GET <url>/api/tags` ; les capacités valent None quand Ollama ne les publie pas."""
    requete = f"{url.rstrip('/')}/api/tags"
    try:
        with urllib.request.urlopen(requete, timeout=timeout) as reponse:
            donnees = json.load(reponse)
    except (urllib.error.URLError, OSError, ValueError) as erreur:
        raise ModeleIndisponible(traduire("modeles_ollama_muet", requete=requete, erreur=texte_de(erreur))) from erreur
    return {entree["name"]: (tuple(entree["capabilities"]) if isinstance(entree.get("capabilities"), list) else None)
            for entree in donnees.get("models", []) if "name" in entree}


def lister_modeles_installes(url, timeout):
    """Rend les noms des modèles installés d'après `GET <url>/api/tags`."""
    return list(lister_capacites(url, timeout))


def _est_installe(preference, installes):
    # Ollama range un nom sans étiquette sous `:latest`.
    return preference in installes or f"{preference}:latest" in installes


def choisir_modeles(roles, installes):
    """Rend {rôle: premier modèle préféré installé}.

    Lève ModeleIndisponible en listant les modèles présents et la ligne de
    config.json à corriger pour chaque rôle sans modèle. Les rôles facultatifs
    se résolvent à part (`tri_decision.resoudre`) et n'arrêtent rien.
    """
    retenus = {}
    manquants = []
    for role, preferences in roles.items():
        if role in ROLES_FACULTATIFS:
            continue
        choix = next((p for p in preferences if _est_installe(p, installes)), None)
        if choix is None:
            manquants.append(role)
        else:
            retenus[role] = choix if choix in installes else f"{choix}:latest"

    if manquants:
        lignes = [traduire("modeles_aucun_pour_roles", roles=", ".join(manquants)),
                  traduire("modeles_presents", modeles=", ".join(sorted(installes)) or traduire("modeles_aucun_present"))]
        for role in manquants:
            lignes.append(traduire("modeles_ligne_a_corriger", role=role, preferences=roles[role]))
        message = "\n".join(lignes)
        raise ModeleIndisponible(message)
    return retenus


def resoudre_modeles(configuration_ollama):
    """Interroge Ollama puis rend {rôle: modèle retenu}."""
    roles = configuration_ollama.get("roles")
    if not roles:
        raise ModeleIndisponible(traduire("modeles_aucun_role_declare"))
    installes = lister_modeles_installes(
        configuration_ollama["url"], configuration_ollama.get("timeout_secondes", 120)
    )
    return choisir_modeles(roles, installes)


def modeles_installes_du_role(configuration_ollama, role):
    """Rend, dans l'ordre des préférences, tous les modèles installés d'un rôle (le consensus les interroge tous)."""
    installes = lister_modeles_installes(
        configuration_ollama["url"], configuration_ollama.get("timeout_secondes", 120)
    )
    preferences = configuration_ollama.get("roles", {}).get(role, [])
    return [p if p in installes else f"{p}:latest" for p in preferences if _est_installe(p, installes)]


def preferences_installees(preferences, installes):
    """Rend, dans l'ordre des préférences, celles qui sont installées (un nom sans étiquette vaut `:latest`)."""
    return [p if p in installes else f"{p}:latest" for p in preferences if _est_installe(p, installes)]
