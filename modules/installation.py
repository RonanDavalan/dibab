"""Où Dibab cherche sa configuration et où il écrit son état quand il est installé par un paquet.

Ordre de recherche de la configuration : option `--config`, variable `DIBAB_CONFIG`, emplacement XDG,
puis `config.json` à côté du script. Le premier fichier trouvé est le seul lu. Une source explicite
(option, variable) dont le fichier manque arrête la recherche : on ne retombe jamais sur un autre fichier,
qui ferait travailler le produit sur d'autres coffres que ceux désignés.
"""

import json
import os
import tempfile
from pathlib import Path

from modules import defauts_langue
from modules.messages import texte_de, traduire

NOM_DOSSIER = "dibab"
VARIABLE_CONFIGURATION = "DIBAB_CONFIG"
EXEMPLE_PAQUET = Path("/usr/share/doc/dibab/examples/config.exemple.json")
DEFAUTS_SUIVI = {
    "fichier_date": "dernier_scan.json",
    "journal": "journal.jsonl",
    "sessions": "sessions",
    "logs_systeme": "dibab.log",
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
        (traduire("config_source_option"), Path(option) if option else None),
        (traduire("config_source_variable", variable=VARIABLE_CONFIGURATION), Path(variable) if variable else None),
        (traduire("config_source_xdg"), dossier_configuration_xdg(environ) / "config.json"),
        (traduire("config_source_script"), Path(chemin_du_script)),
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
            raise ErreurConfiguration(traduire("config_source_inexistante", source=source, chemin=chemin))
    lignes = [traduire("config_introuvable_entete")]
    for rang, (source, chemin) in enumerate(emplacements, start=1):
        lignes.append("        " + traduire("config_emplacement_essaye", rang=rang, source=source, chemin=chemin or traduire("config_non_donnee")))
    lignes.append("        " + traduire("config_introuvable_conseil"))
    raise ConfigurationIntrouvable("\n".join(lignes))


def lire_configuration(chemin):
    """Rend la configuration JSON de `chemin`, ou lève ErreurConfiguration avec le chemin et la cause."""
    try:
        with open(chemin, "r", encoding="utf-8") as fichier:
            configuration = json.load(fichier)
    except (OSError, ValueError) as erreur:
        raise ErreurConfiguration(traduire("config_illisible", chemin=chemin, erreur=texte_de(erreur))) from erreur
    if not isinstance(configuration, dict):
        raise ErreurConfiguration(traduire("config_objet_absent", chemin=chemin))
    return configuration


def trouver_exemple(chemin_du_script):
    """Rend `config.exemple.json` du dépôt ou du paquet, ou None s'il n'existe à aucun des deux endroits."""
    for candidat in (Path(chemin_du_script).resolve().parent / "config.exemple.json", EXEMPLE_PAQUET):
        if candidat.is_file():
            return candidat
    return None


def destination_initialisation(option, environ):
    """Rend le fichier que `--initialiser` écrit : l'option, puis `DIBAB_CONFIG`, puis l'emplacement XDG."""
    if option:
        return Path(option)
    variable = environ.get(VARIABLE_CONFIGURATION)
    if variable:
        return Path(variable)
    return dossier_configuration_xdg(environ) / "config.json"


def initialiser_configuration(destination, exemple, langue=None):
    """Écrit la configuration initiale de `langue` ; rend True si elle est écrite, False si le fichier existe déjà.

    Le fichier est créé en 600 dans un dossier en 700 ; une configuration existante n'est jamais réécrite.
    """
    configuration = defauts_langue.appliquer(lire_configuration(exemple), langue)
    destination = Path(destination)
    if not destination.parent.exists():
        destination.parent.mkdir(parents=True)
        destination.parent.chmod(0o700)
    descripteur, provisoire = tempfile.mkstemp(dir=destination.parent, prefix=".config-", suffix=".json")
    try:
        with os.fdopen(descripteur, "w", encoding="utf-8") as fichier:
            json.dump(configuration, fichier, ensure_ascii=False, indent=2)
            fichier.write("\n")
            fichier.flush()
            os.fsync(fichier.fileno())
        os.chmod(provisoire, 0o600)
        try:
            os.link(provisoire, destination)
        except FileExistsError:
            return False
        return True
    finally:
        Path(provisoire).unlink(missing_ok=True)


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
