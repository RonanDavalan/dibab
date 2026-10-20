"""Expansion des chemins lus dans config.json (`~` et variables d'environnement)."""

import copy
import os

# Chemins de cette machine ; les `repertoires` des sources distantes sont
# résolus par la machine distante, pas ici.
CHEMINS_SIMPLES = (
    ("destination", "racine"),
    ("suivi", "fichier_date"),
    ("suivi", "journal"),
    ("suivi", "sessions"),
    ("suivi", "logs_systeme"),
)
LISTES_DE_SOURCES = (
    ("sources_locales", "chemin"),
    ("sources_imap", "token_fichier"),
)


def developper(valeur):
    return os.path.expandvars(os.path.expanduser(valeur))


def developper_chemins(configuration):
    """Rend une copie de la configuration dont chaque chemin local est développé."""
    resultat = copy.deepcopy(configuration)
    for section, cle in CHEMINS_SIMPLES:
        if isinstance(resultat.get(section, {}).get(cle), str):
            resultat[section][cle] = developper(resultat[section][cle])
    for section, cle in LISTES_DE_SOURCES:
        for entree in resultat.get(section, []):
            if isinstance(entree.get(cle), str):
                entree[cle] = developper(entree[cle])
    return resultat
