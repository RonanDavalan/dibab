"""Résolution des modèles Ollama par rôle.

Le code ne nomme aucun modèle : `config.json` donne, pour chaque rôle, une liste
de préférences ; le premier modèle réellement installé l'emporte.
"""

import json
import urllib.error
import urllib.request


class ModeleIndisponible(Exception):
    """Un rôle n'a aucun modèle installé, ou Ollama ne répond pas."""


def lister_modeles_installes(url, timeout):
    """Rend les noms des modèles installés d'après `GET <url>/api/tags`."""
    requete = f"{url.rstrip('/')}/api/tags"
    try:
        with urllib.request.urlopen(requete, timeout=timeout) as reponse:
            donnees = json.load(reponse)
    except (urllib.error.URLError, OSError, ValueError) as erreur:
        raise ModeleIndisponible(
            f"Ollama ne répond pas à {requete} : {erreur}\n"
            f"        Vérifier `ollama.url` dans config.json et que le service tourne."
        ) from erreur
    return [entree["name"] for entree in donnees.get("models", []) if "name" in entree]


def _est_installe(preference, installes):
    # Ollama range un nom sans étiquette sous `:latest`.
    return preference in installes or f"{preference}:latest" in installes


def choisir_modeles(roles, installes):
    """Rend {rôle: premier modèle préféré installé}.

    Lève ModeleIndisponible en listant les modèles présents et la ligne de
    config.json à corriger pour chaque rôle sans modèle.
    """
    retenus = {}
    manquants = []
    for role, preferences in roles.items():
        choix = next((p for p in preferences if _est_installe(p, installes)), None)
        if choix is None:
            manquants.append(role)
        else:
            retenus[role] = choix if choix in installes else f"{choix}:latest"

    if manquants:
        lignes = [f"Aucun modèle installé pour le rôle : {', '.join(manquants)}."]
        lignes.append("Modèles présents dans Ollama : " + (", ".join(sorted(installes)) or "aucun"))
        for role in manquants:
            lignes.append(
                f"Ligne à corriger dans config.json : ollama.roles.{role} "
                f"(préférences actuelles : {roles[role]})"
            )
        raise ModeleIndisponible("\n".join(lignes))
    return retenus


def resoudre_modeles(configuration_ollama):
    """Interroge Ollama puis rend {rôle: modèle retenu}."""
    roles = configuration_ollama.get("roles")
    if not roles:
        raise ModeleIndisponible(
            "Aucun rôle déclaré.\n        Ligne à corriger dans config.json : ollama.roles"
        )
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
