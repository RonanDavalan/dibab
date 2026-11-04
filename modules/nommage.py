"""Nom normalisé d'un document d'après `nommage` de la configuration."""

import re
import unicodedata
from datetime import date
from pathlib import Path

from modules.classification import CATEGORIE_INCONNUE

# Un nom à vérifier se lit en entier dans un gestionnaire de fichiers et reste sous la limite de 255 octets d'ext4.
LONGUEUR_MAX_A_VERIFIER = 180
OCTETS_MAX_NOM = 255
# Le nom d'origine n'est raccourci sous cette longueur qu'en dernier recours : c'est lui qui fait reconnaître la pièce.
LONGUEUR_MIN_ORIGINE = 20
_VIDE = "\x00"


def _assainir(valeur, espaces_vers):
    # Une valeur vient du texte d'un document : un séparateur de chemin y fabriquerait un répertoire hors de
    # la destination, un caractère de contrôle un nom que le système refuse.
    propre = "".join(c for c in str(valeur) if not unicodedata.category(c).startswith("C")).strip()
    return propre.replace("/", espaces_vers).replace("\\", espaces_vers).replace(" ", espaces_vers)


def _retirer_segments_vides(nom, separateur):
    """Retire chaque segment marqué vide avec le séparateur qui le précède, ou à défaut celui qui le suit."""
    sep = re.escape(separateur)
    return re.sub(f"{sep}{_VIDE}|{_VIDE}{sep}|{_VIDE}", "", nom)


def _tient(nom, longueur_max):
    return len(nom) <= longueur_max and len(nom.encode("utf-8")) <= OCTETS_MAX_NOM


def _raccourcir(valeur, nombre):
    return valeur[:max(0, len(valeur) - nombre)].rstrip("-_. ")


def nommer_a_verifier(nommage, verdict, extension, nom_origine):
    """Rend le nom d'une pièce à vérifier d'après `nommage.format_a_verifier`.

    Seul ce que le document a dit entre dans le nom : un segment vide ou inconnu (date absente, émetteur, catégorie
    « Inconnue ») est retiré avec son séparateur. Le nom d'origine y reste, pour qu'un verdict douteux se reconnaisse.
    Au-delà de `LONGUEUR_MAX_A_VERIFIER`, l'origine est raccourcie d'abord, puis l'objet.
    """
    espaces_vers = nommage.get("espaces_vers", "-")
    separateur = nommage.get("separateur", "_")
    prefixe = nommage["prefixe_a_verifier"]

    def valeur(texte):
        return _assainir(texte, espaces_vers) if texte else ""

    valeurs = {
        "date": verdict.date.strftime(nommage["date_format"]) if isinstance(verdict.date, date) else "",
        "emetteur": valeur(verdict.emetteur),
        "categorie": valeur(verdict.categorie if verdict.categorie != CATEGORIE_INCONNUE else ""),
        "personne": valeur(verdict.personne),
        "objet": valeur(verdict.objet),
        "origine": valeur(Path(nom_origine).stem),
        "ext": extension.lower(),
    }

    def composer():
        bruts = {cle: texte or _VIDE for cle, texte in valeurs.items()}
        return prefixe + _retirer_segments_vides(nommage["format_a_verifier"].format(**bruts), separateur)

    nom = composer()
    for cle, plancher in (("origine", LONGUEUR_MIN_ORIGINE), ("objet", 0), ("origine", 0)):
        while not _tient(nom, LONGUEUR_MAX_A_VERIFIER) and len(valeurs[cle]) > plancher:
            exces = max(len(nom) - LONGUEUR_MAX_A_VERIFIER, 1)
            valeurs[cle] = _raccourcir(valeurs[cle], min(exces, len(valeurs[cle]) - plancher))
            nom = composer()
    if not _tient(nom, LONGUEUR_MAX_A_VERIFIER):
        # Un gabarit personnel peut dépasser même sans origine ni objet : le nom est coupé avant l'extension.
        coupe = len(prefixe)
        corps = nom[coupe:len(nom) - len(valeurs["ext"])]
        while corps and not _tient(prefixe + corps + valeurs["ext"], LONGUEUR_MAX_A_VERIFIER):
            corps = corps[:-1]
        nom = prefixe + corps.rstrip("-_. ") + valeurs["ext"]
    return nom


def nommer(nommage, verdict, extension, date_repli, a_verifier=False, nom_origine=None):
    """Rend le nom normalisé ; `date_repli` (datetime ou date) sert quand le verdict n'a pas de date.

    Un document à vérifier prend le nom de `nommage.format_a_verifier`, qui garde son nom d'origine ; sans cette
    clé, il garde son nom d'origine seul, précédé du préfixe.
    """
    if a_verifier and nom_origine:
        if nommage.get("format_a_verifier"):
            return nommer_a_verifier(nommage, verdict, extension, nom_origine)
        return nommage["prefixe_a_verifier"] + nom_origine
    espaces_vers = nommage.get("espaces_vers", "-")
    if isinstance(verdict.date, date):
        texte_date = verdict.date.strftime(nommage["date_format"])
    else:
        texte_date = nommage["date_inconnue_prefixe"] + date_repli.strftime(nommage["date_format"])
    nom = nommage["format"].format(
        date=texte_date,
        emetteur=_assainir(verdict.emetteur or nommage["emetteur_inconnu"], espaces_vers),
        categorie=_assainir(verdict.categorie, espaces_vers),
        personne=_assainir(verdict.personne or "", espaces_vers),
        objet=(_assainir(verdict.objet, espaces_vers) if verdict.objet else "") or _VIDE,
        ext=extension.lower(),
    )
    nom = _retirer_segments_vides(nom, nommage.get("separateur", "_"))
    return nommage["prefixe_a_verifier"] + nom if a_verifier else nom
