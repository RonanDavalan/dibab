"""Diagnostic de l'installation (`--diagnose`) : treize vérifications, cinq états, aucune écriture.

Les jetons d'état ne se traduisent jamais, pour qu'un script les compare d'une langue à l'autre. Le diagnostic
joue toutes ses vérifications jusqu'au bout. Il n'ouvre qu'une connexion, vers Ollama ; aucune vers une source
distante ni une boîte IMAP, et aucune valeur de variable d'environnement n'est lue pour être écrite.
"""

import os
import shutil
import sys
from collections import namedtuple
from pathlib import Path

from modules import chemins, coffres, domaines, installation, modeles
from modules.messages import texte_de, traduire, traduire_compose

OK = "OK"
AVERTISSEMENT = "AVERTISSEMENT"
ECHEC = "ÉCHEC"
NON_CONFIGURE = "NON_CONFIGURÉ"
NON_VERIFIE = "NON_VÉRIFIÉ"

PYTHON_MINIMUM = (3, 10)
OUTILS = ("pdftotext", "pdftoppm", "findmnt")
ROLES = ("ocr", "tri_rapide", "classification")

Verification = namedtuple("Verification", "etat identifiant message")

SUFFIXES_ETAT = {OK: "ok", AVERTISSEMENT: "avertissement", ECHEC: "echec", NON_CONFIGURE: "non_configure", NON_VERIFIE: "non_verifie"}


def etats_permis():
    """Rend {identifiant: états} de chaque vérification ; les messages sont les clés `diagnostic_<identifiant>_<état>`."""
    tableau = {"python": (OK, ECHEC)}
    tableau.update({f"outil_{outil}": (OK, ECHEC) for outil in OUTILS})
    tableau["outil_ssh"] = (OK, AVERTISSEMENT, ECHEC)
    tableau["configuration"] = (OK, AVERTISSEMENT, ECHEC, NON_CONFIGURE)
    tableau["emplacement_etat"] = (OK, AVERTISSEMENT, NON_VERIFIE)
    tableau["ollama"] = (OK, ECHEC, NON_VERIFIE)
    tableau.update({f"modele_{role}": (OK, ECHEC, NON_VERIFIE) for role in ROLES})
    tableau.update({f"destination_{domaine}": (OK, ECHEC, NON_VERIFIE) for domaine in domaines.COFFRES})
    return tableau


def _verification(etat, identifiant, variante="", **valeurs):
    return Verification(etat, identifiant, traduire_compose(f"diagnostic_{identifiant}_{SUFFIXES_ETAT[etat]}{variante}", **valeurs))


def _sous(chemin, racine):
    chemin, racine = Path(os.path.abspath(chemin)), Path(os.path.abspath(racine))
    return chemin == racine or racine in chemin.parents


def _verifier_configuration(option, environ, chemin_du_script, cles_absentes):
    """Rend (configuration développée ou None, vérification `configuration`)."""
    try:
        chemin = installation.rechercher_configuration(option, environ, chemin_du_script)
        brute = installation.lire_configuration(chemin)
    except installation.ConfigurationIntrouvable:
        emplacements = installation.emplacements_de_configuration(option, environ, chemin_du_script)
        essayes = "; ".join(traduire("diagnostic_emplacement_essaye", source=source, chemin=chemin or traduire("config_non_donnee"))
                             for source, chemin in emplacements)
        return None, _verification(NON_CONFIGURE, "configuration", essayes=essayes)
    except installation.ErreurConfiguration as erreur:
        return None, _verification(ECHEC, "configuration", erreur=texte_de(erreur))
    configuration, _ = installation.appliquer_defauts_suivi(chemins.developper_chemins(brute), environ)
    absentes = cles_absentes(configuration)
    if absentes:
        return configuration, _verification(ECHEC, "configuration", "_cles", chemin=chemin, cles=", ".join(absentes))
    sans_variable = [source["mot_de_passe_env"] for source in configuration.get("sources_imap", [])
                     if source.get("authentification") == "login" and not environ.get(source.get("mot_de_passe_env", ""))]
    # Sans gabarit, une pièce à vérifier garde son seul nom d'origine : le produit marche, la simulation se lit moins bien.
    sans_format = isinstance(configuration.get("nommage"), dict) and not configuration["nommage"].get("format_a_verifier")
    if sans_variable and sans_format:
        return configuration, _verification(AVERTISSEMENT, "configuration", "_imap_format", chemin=chemin, variables=", ".join(sans_variable))
    if sans_variable:
        return configuration, _verification(AVERTISSEMENT, "configuration", chemin=chemin, variables=", ".join(sans_variable))
    if sans_format:
        return configuration, _verification(AVERTISSEMENT, "configuration", "_format", chemin=chemin)
    return configuration, _verification(OK, "configuration", chemin=chemin)


def _verifier_etat(configuration):
    if configuration is None:
        return _verification(NON_VERIFIE, "emplacement_etat")
    suivi = configuration["suivi"]
    dossiers = sorted({str(Path(suivi["fichier_date"]).parent), str(Path(suivi["journal"]).parent)})
    racines = [destination["racine"] for destination in configuration.get("destinations", {}).values()
               if isinstance(destination.get("racine"), str)]
    hors_coffre = [dossier for dossier in dossiers if not any(_sous(dossier, racine) for racine in racines)]
    if hors_coffre:
        return _verification(AVERTISSEMENT, "emplacement_etat", dossiers=", ".join(hors_coffre))
    return _verification(OK, "emplacement_etat", dossiers=", ".join(dossiers))


def _verifier_ollama(configuration, lister):
    """Rend (modèles installés ou None, vérification `ollama`)."""
    if configuration is None:
        return None, _verification(NON_VERIFIE, "ollama")
    parametres = configuration.get("ollama", {})
    if not parametres.get("url"):
        return None, _verification(ECHEC, "ollama", "_url")
    try:
        installes = lister(parametres["url"], parametres.get("timeout_secondes", 120))
    except modeles.ModeleIndisponible as erreur:
        return None, _verification(ECHEC, "ollama", detail=str(erreur).splitlines()[0])
    return installes, _verification(OK, "ollama", url=parametres["url"], nombre=len(installes))


def _verifier_modele(role, configuration, installes):
    identifiant = f"modele_{role}"
    if configuration is None:
        return _verification(NON_VERIFIE, identifiant)
    if installes is None:
        return _verification(NON_VERIFIE, identifiant, "_ollama")
    retenus = modeles.preferences_installees(configuration.get("ollama", {}).get("roles", {}).get(role) or [], installes)
    if not retenus:
        return _verification(ECHEC, identifiant, role=role)
    complement = traduire("diagnostic_complement_consensus", nombre=len(retenus)) if role == "classification" else ""
    return _verification(OK, identifiant, modele=retenus[0], complement=complement)


def _verifier_destination(domaine, configuration, verifier_coffre):
    identifiant = f"destination_{domaine}"
    if configuration is None:
        return _verification(NON_VERIFIE, identifiant)
    destination = configuration.get("destinations", {}).get(domaine, {})
    if not destination.get("racine"):
        return _verification(ECHEC, identifiant, "_racine", domaine=domaine)
    etat = verifier_coffre(domaine, destination["racine"],
                           acceptes=tuple(destination.get("systemes_fichiers_acceptes") or (coffres.TYPE_COFFRE,)))
    if not etat.monte:
        return _verification(ECHEC, identifiant, raison=etat.raison, racine=etat.racine)
    return _verification(OK, identifiant, racine=etat.racine)


def diagnostiquer(option, environ, chemin_du_script, cles_absentes, which=shutil.which, version_python=None,
                  lister=modeles.lister_modeles_installes, verifier_coffre=coffres.verifier_coffre):
    """Rend les treize vérifications dans l'ordre de la spécification."""
    version = tuple(version_python or sys.version_info[:3])
    configuration, verification_configuration = _verifier_configuration(option, environ, chemin_du_script, cles_absentes)
    verifications = [_verification(OK if version >= PYTHON_MINIMUM else ECHEC, "python", version=".".join(str(partie) for partie in version))]
    for outil in OUTILS:
        chemin = which(outil)
        verifications.append(_verification(OK if chemin else ECHEC, f"outil_{outil}", chemin=chemin))
    chemin_ssh = which("ssh")
    declare_distantes = bool(configuration and configuration.get("sources_distantes"))
    verifications.append(_verification(OK if chemin_ssh else (ECHEC if declare_distantes else AVERTISSEMENT), "outil_ssh", chemin=chemin_ssh))
    verifications.append(verification_configuration)
    verifications.append(_verifier_etat(configuration))
    installes, verification_ollama = _verifier_ollama(configuration, lister)
    verifications.append(verification_ollama)
    verifications += [_verifier_modele(role, configuration, installes) for role in ROLES]
    verifications += [_verifier_destination(domaine, configuration, verifier_coffre) for domaine in domaines.COFFRES]
    return verifications


def bilan(verifications):
    nombre = {etat: sum(1 for v in verifications if v.etat == etat) for etat in (OK, AVERTISSEMENT, ECHEC, NON_CONFIGURE, NON_VERIFIE)}
    return traduire("diagnostic_bilan", ok=nombre[OK], avertissements=nombre[AVERTISSEMENT], echecs=nombre[ECHEC],
                    non_configures=nombre[NON_CONFIGURE], non_verifies=nombre[NON_VERIFIE])


def code_de_retour(verifications):
    return 1 if any(v.etat == ECHEC for v in verifications) else 0


def afficher(verifications, sortie=None):
    sortie = sortie or sys.stdout
    for verification in verifications:
        ligne = f"{verification.etat} {verification.identifiant} : {verification.message}"
        print(ligne, file=sortie)
    print(bilan(verifications), file=sortie)
