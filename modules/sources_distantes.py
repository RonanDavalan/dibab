"""Sources distantes : listage, rapatriement dans le vide-poches de la machine, dates de scan à faire avancer.

Le dry-run liste seulement. Une fois rapatrié, un fichier est un fichier local du vide-poches, que le
scan local relit sans filtre de date : tout ce qui s'y trouve attend son classement.
"""

from functools import partial
from pathlib import Path

from modules import rapatriement, scanner_ssh

CLES_SSH = ("delai_connexion_secondes", "delai_commande_secondes", "delai_copie_secondes")


def cles_absentes(configuration):
    sources = configuration.get("sources_distantes", [])
    if not sources:
        return []
    absentes = [f"ssh.{cle}" for cle in CLES_SSH if cle not in configuration.get("ssh", {})]
    for source in sources:
        absentes += [f"sources_distantes[{source.get('id', '?')}].{cle}"
                     for cle in ("id", "alias_ssh", "vide_poches_destination", "repertoires") if cle not in source]
        nom = source.get("vide_poches_destination", "")
        if "/" in nom or nom in ("", ".", ".."):
            absentes.append(f"sources_distantes[{source.get('id', '?')}].vide_poches_destination (un nom, sans séparateur)")
    return absentes


def dossier_vide_poches(configuration, source):
    return Path(configuration["destinations"]["personnel"]["racine"]) / source["vide_poches_destination"]


def source_locale_derivee(configuration, source):
    """La source locale que le scan lit pour traiter ce qui a été rapatrié ; None tant que le dossier n'existe pas."""
    dossier = dossier_vide_poches(configuration, source)
    if not dossier.is_dir():
        return None
    return {"id": f"{source['id']}-vide-poches", "chemin": str(dossier), "toujours_complete": True}


def sources_locales_derivees(configuration):
    derivees = (source_locale_derivee(configuration, source) for source in configuration.get("sources_distantes", []))
    return [derivee for derivee in derivees if derivee]


def executeurs(configuration):
    ssh = configuration["ssh"]
    court = partial(scanner_ssh.executer_ssh, delai_connexion=ssh["delai_connexion_secondes"],
                    delai_commande=ssh["delai_commande_secondes"])
    copie = partial(scanner_ssh.executer_ssh, delai_connexion=ssh["delai_connexion_secondes"],
                    delai_commande=ssh["delai_copie_secondes"])
    return court, copie


def lister(configuration, suivi, journal, maintenant, executer):
    """Liste chaque source distante ; rend [(source, candidats, complet, erreurs)]."""
    parametres = configuration["suivi"]
    listages = []
    for source in configuration.get("sources_distantes", []):
        candidats, complet, erreurs = scanner_ssh.scanner_machine(
            source, configuration.get("scan", {}), configuration.get("extensions_cibles", []),
            suivi.get(source["id"]), parametres.get("securite_jours", 1), parametres.get("premier_scan_jours", 90),
            maintenant, executer)
        journal.ajouter("scan_distant", source_id=source["id"], candidats=len(candidats), complet=complet, erreurs=erreurs)
        listages.append((source, candidats, complet, erreurs))
    return listages


def afficher(listages):
    for source, candidats, complet, erreurs in listages:
        print(f"Source distante : {source['id']} (rien n'est rapatrié en dry-run)")
        for candidat in candidats:
            print(f"  - {candidat.nom:<50s} (distant, {candidat.taille_octets} o, mtime {candidat.mtime:%Y-%m-%d})")
        if not candidats and complet:
            print("  (aucun fichier candidat)")
        for erreur in erreurs:
            print(f"  [!] {erreur}")
        print()


def rapatrier(configuration, listages, registre, journal, rapport, maintenant, executeur_court, executeur_copie):
    """Copie les candidats de chaque machine ; rend (dates à faire avancer, sources en échec).

    La date d'une machine n'avance que si son listage est complet et que chaque copie est vérifiée.
    """
    suffixe = configuration["nommage"]["suffixe_collision"]
    dates, en_echec = {}, set()
    for source, candidats, complet, erreurs in listages:
        reussi = complet
        dossier = dossier_vide_poches(configuration, source)
        for candidat in candidats:
            try:
                action, empreinte = rapatriement.rapatrier_fichier(candidat, dossier, registre, suffixe, executeur_court, executeur_copie)
            except (scanner_ssh.ErreurSsh, OSError) as erreur:
                reussi = False
                journal.ajouter("rapatriement_echec", source_id=source["id"], raison=str(erreur))
                print(f"  - {candidat.nom} : ÉCHEC du rapatriement, laissé sur la machine ({erreur})")
                if isinstance(erreur, scanner_ssh.MachineInjoignable):
                    break
                continue
            rapport.rapatries += action == rapatriement.RAPATRIE
            journal.ajouter("rapatriement", source_id=source["id"], action=action, empreinte=empreinte)
        if reussi:
            dates[source["id"]] = maintenant
        else:
            en_echec.add(source["id"])
    return dates, en_echec
