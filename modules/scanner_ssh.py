"""Listage en lecture seule des répertoires d'une machine distante, par `ssh` (alias de ~/.ssh/config).

Aucun nom de fichier distant n'est jamais placé dans une commande avant d'avoir été cité pour le
shell distant : le listage ne reçoit que des données (`find -printf`, séparées par NUL), et seuls
les répertoires de la configuration entrent dans la commande.
"""

import os
import shlex
import subprocess
from dataclasses import dataclass
from datetime import datetime
from pathlib import PurePosixPath

from modules import scanner_local


class ErreurSsh(Exception):
    """Une commande distante n'a pas abouti."""


class MachineInjoignable(ErreurSsh):
    pass


class DelaiDepasse(ErreurSsh):
    pass


@dataclass(frozen=True)
class FichierDistant:
    source_id: str
    alias: str
    repertoire: str
    relatif: str
    taille_octets: int
    mtime: datetime

    @property
    def nom(self):
        return PurePosixPath(self.relatif).name


def expression_distante(repertoire, relatif=None):
    """Chemin cité pour le shell distant ; `~` y vaut le répertoire personnel de la machine distante."""
    if repertoire == "~":
        base = '"$HOME"'
    elif repertoire.startswith("~/"):
        base = '"$HOME"/' + shlex.quote(repertoire[2:])
    else:
        base = shlex.quote(repertoire)
    return base if relatif is None else f"{base}/{shlex.quote(relatif)}"


def executer_ssh(alias, commande, delai_connexion, delai_commande, stdout=None):
    """Lance `commande` sur la machine nommée par `alias` ; BatchMode interdit toute question interactive."""
    ligne = ["ssh", "-o", "BatchMode=yes", "-o", f"ConnectTimeout={int(delai_connexion)}", "--", alias, commande]
    try:
        retour = subprocess.run(ligne, stdin=subprocess.DEVNULL, stdout=stdout or subprocess.PIPE,
                                stderr=subprocess.PIPE, timeout=delai_commande)
    except FileNotFoundError as erreur:
        raise ErreurSsh("commande ssh introuvable") from erreur
    except subprocess.TimeoutExpired as erreur:
        raise DelaiDepasse(f"délai de {delai_commande} s dépassé") from erreur
    if retour.returncode == 255:
        message = retour.stderr.decode("utf-8", "replace").strip().splitlines()
        raise MachineInjoignable(message[-1] if message else "connexion refusée")
    return retour


def _analyser(sortie):
    for enregistrement in sortie.split(b"\0"):
        if not enregistrement:
            continue
        try:
            mtime, taille, relatif = enregistrement.split(b"\t", 2)
            yield float(mtime), int(taille), os.fsdecode(relatif)
        except ValueError:
            continue


def lister_repertoire(source, repertoire, recursif, executer):
    """Rend (entrées brutes, erreur) pour un répertoire ; l'erreur est None si le listage est complet."""
    profondeur = "" if recursif else "-maxdepth 1 "
    commande = f"find {expression_distante(repertoire)} {profondeur}-type f -printf '%T@\\t%s\\t%P\\0'"
    retour = executer(source["alias_ssh"], commande)
    entrees = list(_analyser(retour.stdout))
    if retour.returncode != 0:
        return entrees, f"répertoire distant partiellement lisible ou absent (code {retour.returncode})"
    return entrees, None


def scanner_machine(source, scan_global, extensions_cibles, derniere_date, securite_jours,
                    premier_scan_jours, maintenant, executer):
    """Liste les fichiers candidats d'une source distante.

    Rend (candidats, complet, erreurs). Après la première panne de connexion, aucun autre répertoire
    n'est tenté : un refus ne s'insiste pas.
    """
    extensions = scanner_local.normaliser_extensions(extensions_cibles)
    seuil = scanner_local.date_seuil(derniere_date, securite_jours, premier_scan_jours, maintenant)
    exclusions = scanner_local.fabriquer_exclusions(scan_global, source)
    recursif = scanner_local.determiner_recursif(scan_global, source)
    ignorer_dotfiles = scan_global.get("ignorer_dotfiles", True)
    candidats, erreurs = [], []
    for repertoire in source["repertoires"]:
        try:
            entrees, erreur = lister_repertoire(source, repertoire, recursif, executer)
        except ErreurSsh as panne:
            erreurs.append(str(panne))
            break
        if erreur:
            erreurs.append(erreur)
        for mtime, taille, relatif in entrees:
            parties = PurePosixPath(relatif).parts
            if ignorer_dotfiles and any(partie.startswith(".") for partie in parties):
                continue
            if any(partie in exclusions for partie in parties[:-1]):
                continue
            if PurePosixPath(relatif).suffix.lower() not in extensions:
                continue
            date = datetime.fromtimestamp(mtime)
            if date < seuil:
                continue
            candidats.append(FichierDistant(source["id"], source["alias_ssh"], repertoire, relatif, taille, date))
    return candidats, not erreurs, erreurs
