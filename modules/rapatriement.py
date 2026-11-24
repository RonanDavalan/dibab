"""Rapatriement par copie : un fichier distant rejoint le vide-poches de sa machine, vérifié par empreinte.

Rien n'est jamais déplacé ni supprimé côté distant (`cat` et `sha256sum` seulement). Une copie
interrompue ne laisse aucun fichier sous son nom final ; un fichier déjà rapatrié n'est pas recopié.
"""

import json
import os
import re
from pathlib import Path

from modules.deplacement import chemin_libre, creer_dossiers_prives
from modules.pieces_communes import empreinte_sha256
from modules.scanner_ssh import ErreurSsh, expression_distante
from modules.messages import traduire

DEJA_RAPATRIE = "deja_rapatrie"
RAPATRIE = "rapatrie"
REPRISE = "reprise"
OCTETS_NOM_MAX = 200


def nom_local(nom):
    """Nom sûr pour le vide-poches : sans caractère de contrôle, jamais caché (le scanner ignore les points initiaux)."""
    propre = re.sub(r"[\x00-\x1f\x7f/\\]", "_", nom).strip()
    if propre == "" or propre.startswith("."):
        propre = "_" + propre
    racine, point, extension = propre.rpartition(".")
    while len(propre.encode("utf-8")) > OCTETS_NOM_MAX and racine:
        racine = racine[:-1]
        propre = racine + point + extension
    return propre


def cle_du_fichier(fichier):
    return f"{fichier.repertoire}|{fichier.relatif}|{fichier.taille_octets}|{int(fichier.mtime.timestamp())}"


class RegistreRapatries:
    """Fichiers déjà rapatriés, par source : une relecture de la fenêtre de sécurité ne recopie rien."""

    def __init__(self, chemin):
        self.chemin = Path(chemin)
        try:
            self.donnees = json.loads(self.chemin.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            self.donnees = {}

    def connu(self, source_id, cle):
        return cle in self.donnees.get(source_id, {})

    def noter(self, source_id, cle, empreinte):
        self.donnees.setdefault(source_id, {})[cle] = empreinte
        creer_dossiers_prives(self.chemin.parent)
        provisoire = self.chemin.with_suffix(".tmp")
        descripteur = os.open(provisoire, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(descripteur, "w", encoding="utf-8") as f:
            json.dump(self.donnees, f, ensure_ascii=False, indent=2, sort_keys=True)
        provisoire.replace(self.chemin)


def empreinte_distante(fichier, executer):
    commande = f"sha256sum -- {expression_distante(fichier.repertoire, fichier.relatif)}"
    retour = executer(fichier.alias, commande)
    mots = retour.stdout.decode("utf-8", "replace").split()
    if retour.returncode != 0 or not mots or not re.fullmatch(r"[0-9a-f]{64}", mots[0]):
        raise ErreurSsh(traduire("ssh_empreinte_illisible"))
    return mots[0]


def rapatrier_fichier(fichier, dossier, registre, suffixe_collision, executer, executer_copie):
    """Copie `fichier` dans `dossier` ; rend l'action (rapatrié, déjà rapatrié, reprise) et l'empreinte vérifiée."""
    cle = cle_du_fichier(fichier)
    if registre.connu(fichier.source_id, cle):
        return DEJA_RAPATRIE, registre.donnees[fichier.source_id][cle]
    empreinte = empreinte_distante(fichier, executer)
    dossier = Path(dossier)
    creer_dossiers_prives(dossier)
    final = dossier / nom_local(fichier.nom)
    if final.is_file() and empreinte_sha256(final) == empreinte:
        registre.noter(fichier.source_id, cle, empreinte)
        return REPRISE, empreinte
    final = chemin_libre(final, suffixe_collision)
    provisoire = dossier / f".dibab-rapatrie-{os.getpid()}-{final.name}"
    try:
        with open(provisoire, "wb") as f:
            retour = executer_copie(fichier.alias, f"cat -- {expression_distante(fichier.repertoire, fichier.relatif)}", stdout=f)
        if retour.returncode != 0:
            raise ErreurSsh(traduire("ssh_copie_interrompue"))
        if empreinte_sha256(provisoire) != empreinte:
            raise ErreurSsh(traduire("ssh_empreinte_differente"))
        os.utime(provisoire, (fichier.mtime.timestamp(), fichier.mtime.timestamp()))
        os.rename(provisoire, final)
    except BaseException:
        provisoire.unlink(missing_ok=True)
        raise
    registre.noter(fichier.source_id, cle, empreinte)
    return RAPATRIE, empreinte
