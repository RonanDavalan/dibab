# modules/scanner_local.py — Découverte des fichiers candidats sur le système local
#
# Une source locale est un répertoire (config sources_locales[].chemin) que l'on
# parcourt pour trouver les fichiers candidats au tri. Le scanner ne fait aucun
# jugement métier (administratif ou pas) : il ne fait que produire la liste des
# fichiers qui méritent qu'on les regarde.
#
# Critères de filtrage Phase 2 :
# - extension dans config.extensions_cibles (comparaison insensible à la casse)
# - mtime postérieur à (derniere_date - securite_jours), ou si pas de dernière
#   date, postérieur à (maintenant - premier_scan_jours)
# - sous-dossiers exclus : scan.exclusions_automatiques + source.exclusions
# - dotfiles ignorés si scan.ignorer_dotfiles
# - symlinks non suivis si scan.suivre_symlinks est False

from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path


@dataclass
class FichierCandidat:
    """Un fichier découvert pendant le scan, candidat au traitement."""
    chemin: Path
    source_id: str
    taille_octets: int
    mtime: datetime


def normaliser_extensions(extensions):
    """Retourne un set d'extensions en minuscules (avec le point initial)."""
    return {ext.lower() for ext in extensions}


def extension_acceptee(chemin, extensions_normalisees):
    """Compare l'extension du fichier (en minuscules) au set d'extensions cibles."""
    return chemin.suffix.lower() in extensions_normalisees


def date_seuil(derniere_date, securite_jours, premier_scan_jours, maintenant=None):
    """Calcule la date à partir de laquelle un fichier est candidat.

    - Si derniere_date est fournie : retourne derniere_date - securite_jours
    - Sinon (premier scan) : retourne maintenant - premier_scan_jours
    """
    if maintenant is None:
        maintenant = datetime.now()
    if derniere_date is None:
        return maintenant - timedelta(days=premier_scan_jours)
    return derniere_date - timedelta(days=securite_jours)


def fabriquer_exclusions(scan_global, source):
    """Combine les exclusions automatiques globales et celles de la source."""
    automatiques = set(scan_global.get("exclusions_automatiques", []))
    specifiques = set(source.get("exclusions", []))
    return automatiques | specifiques


def determiner_recursif(scan_global, source):
    """Retourne True si la source doit être scannée récursivement."""
    par_defaut = scan_global.get("recursif_par_defaut", True)
    return source.get("recursif", par_defaut)


def parcourir(racine, recursif, exclusions, ignorer_dotfiles, suivre_symlinks):
    """Itère sur les fichiers d'un répertoire en appliquant les filtres structurels.

    Yield des Path. Ne filtre ni sur l'extension ni sur la date — c'est fait
    en amont par l'appelant pour garder cette fonction simple et testable.
    """
    racine = Path(racine)
    if not racine.exists() or not racine.is_dir():
        return

    if recursif:
        iterateur = _parcours_recursif(racine, exclusions, ignorer_dotfiles, suivre_symlinks)
    else:
        iterateur = _parcours_plat(racine, ignorer_dotfiles, suivre_symlinks)

    for chemin in iterateur:
        yield chemin


def _parcours_recursif(racine, exclusions, ignorer_dotfiles, suivre_symlinks):
    for chemin_courant in racine.rglob("*"):
        if not suivre_symlinks and chemin_courant.is_symlink():
            continue
        if ignorer_dotfiles and any(part.startswith(".") for part in chemin_courant.relative_to(racine).parts):
            continue
        parties = chemin_courant.relative_to(racine).parts
        if any(part in exclusions for part in parties[:-1]):
            continue
        if chemin_courant.is_file():
            yield chemin_courant


def _parcours_plat(racine, ignorer_dotfiles, suivre_symlinks):
    for chemin_courant in racine.iterdir():
        if not suivre_symlinks and chemin_courant.is_symlink():
            continue
        if ignorer_dotfiles and chemin_courant.name.startswith("."):
            continue
        if chemin_courant.is_file():
            yield chemin_courant


def scanner_source(source, scan_global, extensions_cibles, derniere_date,
                   securite_jours, premier_scan_jours, maintenant=None):
    """Scanne une source locale et retourne la liste des FichierCandidat.

    Retourne aussi un dict de statistiques pour le rapport et le journal :
    {"existe": bool, "lus": int, "candidats": int, "taille_octets": int}.

    Si la source n'existe pas, retourne une liste vide et existe=False
    (warning à émettre par l'appelant, pas d'échec).
    """
    extensions = normaliser_extensions(extensions_cibles)
    exclusions = fabriquer_exclusions(scan_global, source)
    seuil = date_seuil(derniere_date, securite_jours, premier_scan_jours, maintenant)
    recursif = determiner_recursif(scan_global, source)
    ignorer_dotfiles = scan_global.get("ignorer_dotfiles", True)
    suivre_symlinks = scan_global.get("suivre_symlinks", False)

    racine = Path(source["chemin"])
    stats = {"existe": racine.exists() and racine.is_dir(),
             "lus": 0, "candidats": 0, "taille_octets": 0}

    if not stats["existe"]:
        return [], stats

    candidats = []
    for chemin in parcourir(racine, recursif, exclusions, ignorer_dotfiles, suivre_symlinks):
        stats["lus"] += 1
        if not extension_acceptee(chemin, extensions):
            continue
        try:
            info = chemin.stat()
        except OSError:
            continue
        mtime = datetime.fromtimestamp(info.st_mtime)
        if mtime < seuil:
            continue
        candidats.append(FichierCandidat(
            chemin=chemin,
            source_id=source["id"],
            taille_octets=info.st_size,
            mtime=mtime,
        ))
        stats["candidats"] += 1
        stats["taille_octets"] += info.st_size

    return candidats, stats
