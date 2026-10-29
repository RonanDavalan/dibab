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

OK = "OK"
AVERTISSEMENT = "AVERTISSEMENT"
ECHEC = "ÉCHEC"
NON_CONFIGURE = "NON_CONFIGURÉ"
NON_VERIFIE = "NON_VÉRIFIÉ"

PYTHON_MINIMUM = (3, 10)
OUTILS = ("pdftotext", "pdftoppm", "findmnt")
ROLES = ("ocr", "tri_rapide", "classification")

Verification = namedtuple("Verification", "etat identifiant message")


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
        essayes = " ; ".join(f"{source} : {chemin if chemin else 'non donnée'}" for source, chemin in emplacements)
        return None, Verification(NON_CONFIGURE, "configuration", f"aucune configuration trouvée ({essayes})")
    except installation.ErreurConfiguration as erreur:
        return None, Verification(ECHEC, "configuration", str(erreur))
    configuration, _ = installation.appliquer_defauts_suivi(chemins.developper_chemins(brute), environ)
    absentes = cles_absentes(configuration)
    if absentes:
        return configuration, Verification(ECHEC, "configuration", f"{chemin} : clés absentes : {', '.join(absentes)}")
    sans_variable = [source["mot_de_passe_env"] for source in configuration.get("sources_imap", [])
                     if source.get("authentification") == "login" and not environ.get(source.get("mot_de_passe_env", ""))]
    if sans_variable:
        return configuration, Verification(
            AVERTISSEMENT, "configuration",
            f"{chemin} : variable d'environnement absente pour une source IMAP : {', '.join(sans_variable)}")
    return configuration, Verification(OK, "configuration", str(chemin))


def _verifier_etat(configuration):
    if configuration is None:
        return Verification(NON_VERIFIE, "emplacement_etat", "dépend de la configuration")
    suivi = configuration["suivi"]
    dossiers = sorted({str(Path(suivi["fichier_date"]).parent), str(Path(suivi["journal"]).parent)})
    racines = [destination["racine"] for destination in configuration.get("destinations", {}).values()
               if isinstance(destination.get("racine"), str)]
    hors_coffre = [dossier for dossier in dossiers if not any(_sous(dossier, racine) for racine in racines)]
    if hors_coffre:
        return Verification(AVERTISSEMENT, "emplacement_etat",
                            f"l'état et le journal sont en clair, hors de tout coffre : {', '.join(hors_coffre)}")
    return Verification(OK, "emplacement_etat", ", ".join(dossiers))


def _verifier_ollama(configuration, lister):
    """Rend (modèles installés ou None, vérification `ollama`)."""
    if configuration is None:
        return None, Verification(NON_VERIFIE, "ollama", "dépend de la configuration")
    parametres = configuration.get("ollama", {})
    if not parametres.get("url"):
        return None, Verification(ECHEC, "ollama", "ollama.url absente de la configuration")
    try:
        installes = lister(parametres["url"], parametres.get("timeout_secondes", 120))
    except modeles.ModeleIndisponible as erreur:
        return None, Verification(ECHEC, "ollama", str(erreur).splitlines()[0])
    return installes, Verification(OK, "ollama", f"{parametres['url']} répond, {len(installes)} modèle(s) installé(s)")


def _verifier_modele(role, configuration, installes):
    identifiant = f"modele_{role}"
    if configuration is None:
        return Verification(NON_VERIFIE, identifiant, "dépend de la configuration")
    if installes is None:
        return Verification(NON_VERIFIE, identifiant, "dépend de la vérification ollama")
    retenus = modeles.preferences_installees(configuration.get("ollama", {}).get("roles", {}).get(role) or [], installes)
    if not retenus:
        return Verification(ECHEC, identifiant, f"aucun modèle installé pour ce rôle : corriger ollama.roles.{role}")
    complement = f", {len(retenus)} modèle(s) au consensus" if role == "classification" else ""
    return Verification(OK, identifiant, f"{retenus[0]}{complement}")


def _verifier_destination(domaine, configuration, verifier_coffre):
    identifiant = f"destination_{domaine}"
    if configuration is None:
        return Verification(NON_VERIFIE, identifiant, "dépend de la configuration")
    destination = configuration.get("destinations", {}).get(domaine, {})
    if not destination.get("racine"):
        return Verification(ECHEC, identifiant, f"destinations.{domaine}.racine absente de la configuration")
    etat = verifier_coffre(domaine, destination["racine"],
                           acceptes=tuple(destination.get("systemes_fichiers_acceptes") or (coffres.TYPE_COFFRE,)))
    if not etat.monte:
        return Verification(ECHEC, identifiant, f"{etat.raison} ({etat.racine})")
    return Verification(OK, identifiant, str(etat.racine))


def diagnostiquer(option, environ, chemin_du_script, cles_absentes, which=shutil.which, version_python=None,
                  lister=modeles.lister_modeles_installes, verifier_coffre=coffres.verifier_coffre):
    """Rend les treize vérifications dans l'ordre de la spécification."""
    version = tuple(version_python or sys.version_info[:3])
    configuration, verification_configuration = _verifier_configuration(option, environ, chemin_du_script, cles_absentes)
    verifications = [Verification(
        OK if version >= PYTHON_MINIMUM else ECHEC, "python",
        ".".join(str(partie) for partie in version) + ("" if version >= PYTHON_MINIMUM else " : 3.10 ou plus est exigé"))]
    for outil in OUTILS:
        chemin = which(outil)
        verifications.append(Verification(OK if chemin else ECHEC, f"outil_{outil}", chemin or "absent du PATH"))
    chemin_ssh = which("ssh")
    declare_distantes = bool(configuration and configuration.get("sources_distantes"))
    verifications.append(Verification(
        OK if chemin_ssh else (ECHEC if declare_distantes else AVERTISSEMENT), "outil_ssh",
        chemin_ssh or "absent du PATH" + (" alors que la configuration déclare sources_distantes" if declare_distantes else "")))
    verifications.append(verification_configuration)
    verifications.append(_verifier_etat(configuration))
    installes, verification_ollama = _verifier_ollama(configuration, lister)
    verifications.append(verification_ollama)
    verifications += [_verifier_modele(role, configuration, installes) for role in ROLES]
    verifications += [_verifier_destination(domaine, configuration, verifier_coffre) for domaine in domaines.COFFRES]
    return verifications


def bilan(verifications):
    nombre = {etat: sum(1 for v in verifications if v.etat == etat) for etat in (OK, AVERTISSEMENT, ECHEC, NON_CONFIGURE, NON_VERIFIE)}
    return (f"Diagnostic : {nombre[OK]} OK, {nombre[AVERTISSEMENT]} avertissement(s), {nombre[ECHEC]} échec(s), "
            f"{nombre[NON_CONFIGURE]} non configuré(s), {nombre[NON_VERIFIE]} non vérifié(s)")


def code_de_retour(verifications):
    return 1 if any(v.etat == ECHEC for v in verifications) else 0


def afficher(verifications, sortie=None):
    sortie = sortie or sys.stdout
    for verification in verifications:
        print(f"{verification.etat} {verification.identifiant} : {verification.message}", file=sortie)
    print(bilan(verifications), file=sortie)
