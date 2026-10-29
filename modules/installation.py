"""Où Skrivagner cherche sa configuration et où il écrit son état quand il est installé par un paquet.

Ordre de recherche de la configuration : option `--config`, variable `SKRIVAGNER_CONFIG`, emplacement XDG,
puis `config.json` à côté du script. Le premier fichier trouvé est le seul lu. Une source explicite
(option, variable) dont le fichier manque arrête la recherche : on ne retombe jamais sur un autre fichier,
qui ferait travailler le produit sur d'autres coffres que ceux désignés.
"""

import json
import os
from pathlib import Path

NOM_DOSSIER = "skrivagner"
VARIABLE_CONFIGURATION = "SKRIVAGNER_CONFIG"
DEFAUTS_SUIVI = {
    "fichier_date": "dernier_scan.json",
    "journal": "journal.jsonl",
    "sessions": "sessions",
    "logs_systeme": "skrivagner.log",
}


CLES_ECRITES = ("fichier_date", "journal", "sessions")


class ErreurConfiguration(Exception):
    """La configuration est illisible ou invalide, ou une source explicite désigne un fichier absent ; le message dit où."""


class ConfigurationIntrouvable(ErreurConfiguration):
    """Aucun des quatre emplacements ne porte de fichier et aucune source explicite n'a été donnée."""


def _domicile(environ):
    return Path(environ.get("HOME") or Path.home())


def dossier_configuration_xdg(environ):
    base = environ.get("XDG_CONFIG_HOME")
    return Path(base) / NOM_DOSSIER if base else _domicile(environ) / ".config" / NOM_DOSSIER


def dossier_etat_par_defaut(environ):
    base = environ.get("XDG_STATE_HOME")
    return Path(base) / NOM_DOSSIER if base else _domicile(environ) / ".local" / "state" / NOM_DOSSIER


def emplacements_de_configuration(option, environ, chemin_du_script):
    """Rend les quatre emplacements dans l'ordre : (libellé de la source, chemin ou None si la source n'est pas donnée)."""
    variable = environ.get(VARIABLE_CONFIGURATION)
    return [
        ("l'option --config", Path(option) if option else None),
        (f"la variable {VARIABLE_CONFIGURATION}", Path(variable) if variable else None),
        ("l'emplacement XDG", dossier_configuration_xdg(environ) / "config.json"),
        ("le dossier du script", Path(chemin_du_script)),
    ]


def rechercher_configuration(option, environ, chemin_du_script):
    """Rend le chemin de la configuration à lire, ou lève ErreurConfiguration."""
    emplacements = emplacements_de_configuration(option, environ, chemin_du_script)
    for rang, (source, chemin) in enumerate(emplacements):
        if chemin is None:
            continue
        if chemin.is_file():
            return chemin
        if rang < 2:
            raise ErreurConfiguration(f"{source} désigne {chemin}, qui n'existe pas.")
    lignes = ["configuration introuvable. Emplacements essayés, dans l'ordre :"]
    for rang, (source, chemin) in enumerate(emplacements, start=1):
        lignes.append(f"        {rang}. {source} : {chemin if chemin else 'non donnée'}")
    lignes.append("        Copier config.exemple.json en config.json à l'un de ces emplacements et l'adapter.")
    raise ConfigurationIntrouvable("\n".join(lignes))


def lire_configuration(chemin):
    """Rend la configuration JSON de `chemin`, ou lève ErreurConfiguration avec le chemin et la cause."""
    try:
        with open(chemin, "r", encoding="utf-8") as fichier:
            configuration = json.load(fichier)
    except (OSError, ValueError) as erreur:
        raise ErreurConfiguration(f"configuration illisible ou invalide : {chemin} : {erreur}") from erreur
    if not isinstance(configuration, dict):
        raise ErreurConfiguration(f"configuration invalide : {chemin} : l'objet JSON attendu est absent")
    return configuration


def appliquer_defauts_suivi(configuration, environ):
    """Rend (configuration, dossier d'état par défaut ou None) : chaque clé de chemin de `suivi` absente prend son défaut XDG.

    Une clé donnée par la configuration l'emporte toujours. Le dossier n'est rendu que si le défaut d'une clé que la session
    écrit a servi : `logs_systeme` reçoit son défaut sans qu'aucun module n'y écrive.
    """
    dossier = dossier_etat_par_defaut(environ)
    suivi = dict(configuration.get("suivi") or {})
    ecrit_par_defaut = False
    for cle, nom in DEFAUTS_SUIVI.items():
        if not suivi.get(cle):
            suivi[cle] = str(dossier / nom)
            ecrit_par_defaut = ecrit_par_defaut or cle in CLES_ECRITES
    return {**configuration, "suivi": suivi}, (dossier if ecrit_par_defaut else None)


def preparer_dossier_etat(dossier, configuration=None):
    """Crée le dossier d'état en 700, et celui des sessions s'il est le défaut de la configuration (ou si elle n'est pas donnée)."""
    chemins = [dossier]
    if configuration is None or Path(configuration["suivi"]["sessions"]) == dossier / DEFAUTS_SUIVI["sessions"]:
        chemins.append(dossier / DEFAUTS_SUIVI["sessions"])
    for chemin in chemins:
        chemin.mkdir(parents=True, exist_ok=True)
        chemin.chmod(0o700)


def durcir_dossier_etat(dossier):
    """Ramène à 700 les dossiers et à 600 les fichiers que la session a écrits sous le dossier d'état par défaut."""
    if not dossier.is_dir():
        return
    dossier.chmod(0o700)
    for racine, sous_dossiers, fichiers in os.walk(dossier):
        for nom in sous_dossiers:
            (Path(racine) / nom).chmod(0o700)
        for nom in fichiers:
            (Path(racine) / nom).chmod(0o600)
