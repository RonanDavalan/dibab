"""Expansion des chemins lus dans config.json (`~` et variables d'environnement)."""

import copy
import os

# Chemins de cette machine ; les `repertoires` des sources distantes sont
# résolus par la machine distante, pas ici.
CHEMINS_SIMPLES = (
    ("suivi", "fichier_date"),
    ("suivi", "journal"),
    ("suivi", "sessions"),
    ("suivi", "logs_systeme"),
)
LISTES_DE_SOURCES = (
    ("sources_locales", "chemin"),
    ("sources_imap", "token_fichier"),
    ("sources_imap", "client_fichier"),
)


def developper(valeur):
    return os.path.expandvars(os.path.expanduser(valeur))


def developper_chemins(configuration):
    """Rend une copie de la configuration dont chaque chemin local est développé."""
    resultat = copy.deepcopy(configuration)
    for section, cle in CHEMINS_SIMPLES:
        if isinstance(resultat.get(section, {}).get(cle), str):
            resultat[section][cle] = developper(resultat[section][cle])
    for destination in resultat.get("destinations", {}).values():
        if isinstance(destination.get("racine"), str):
            destination["racine"] = developper(destination["racine"])
    interdits = resultat.get("oauth2", {}).get("chemins_interdits")
    if isinstance(interdits, list):
        resultat["oauth2"]["chemins_interdits"] = [developper(c) if isinstance(c, str) else c for c in interdits]
    for section, cle in LISTES_DE_SOURCES:
        for entree in resultat.get(section, []):
            if isinstance(entree.get(cle), str):
                entree[cle] = developper(entree[cle])
    return resultat
