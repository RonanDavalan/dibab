#!/usr/bin/env python3
# dibab.py — Point d'entrée
#
# Modes : --dry-run (défaut, rien ne bouge), --execute, --inventaire, --rollback, --autoriser-google, --diagnose ; --version.
# Sources : répertoires locaux, machines distantes par ssh, boîtes IMAP en lecture seule.

import json
import socket
import sys
import os
from datetime import datetime
from pathlib import Path

from modules import cascade as mod_cascade
from modules import classement as mod_classement
from modules import chemins as mod_chemins
from modules import classification as mod_classification
from modules import coffres as mod_coffres
from modules import diagnostic as mod_diagnostic
from modules import deplacement as mod_deplacement
from modules import domaines as mod_domaines
from modules import extraction as mod_extraction
from modules import installation as mod_installation
from modules import inventaire as mod_inventaire
from modules import journal as mod_journal
from modules import journal_actions as mod_journal_actions
from modules import messages as mod_messages
from modules import modeles as mod_modeles
from modules import oauth2_google as mod_oauth2_google
from modules import rapatriement as mod_rapatriement
from modules import rapport as mod_rapport
from modules import rollback as mod_rollback
from modules import rotation as mod_rotation
from modules import scanner_local
from modules import sources_distantes as mod_sources_distantes
from modules import sources_imap as mod_sources_imap
from modules import suivi as mod_suivi
from modules import tri_decision as mod_tri_decision
from modules import verrou as mod_verrou
from modules.messages import ParseurTraduit, ecrire, texte_de, traduire


VERSION = "0.9.0-alpha"

SUITE = "\n" + " " * 8

# Un vide-poches se relit en entier : tout ce qui s'y trouve attend son classement.
JOURS_SANS_FILTRE_DATE = 36500

CHEMIN_RACINE = Path(__file__).resolve().parent
CHEMIN_CONFIG = CHEMIN_RACINE / "config.json"
DOSSIER_ETAT_PAR_DEFAUT = None


def erreur_console(detail):
    sys.stderr.write(traduire("erreur_prefixe", detail=detail) + "\n")


def message_cles_absentes(absents):
    return traduire("config_cles_absentes", cles=", ".join(absents)) + SUITE + traduire("suite_voir_exemple")


def charger_configuration(option=None, environ=os.environ):
    """Rend (configuration, chemin lu, dossier d'état par défaut ou None) ; arrête avec le code 1 si la configuration manque ou est invalide."""
    try:
        chemin = mod_installation.rechercher_configuration(option, environ, CHEMIN_CONFIG)
        brute = mod_installation.lire_configuration(chemin)
    except mod_installation.ErreurConfiguration as erreur:
        erreur_console(texte_de(erreur))
        sys.exit(1)
    configuration, dossier_etat = mod_installation.appliquer_defauts_suivi(mod_chemins.developper_chemins(brute), environ)
    return configuration, chemin, dossier_etat


def preparer_etat(dossier_etat, configuration):
    """Crée le dossier d'état par défaut en 700 ; `main` ramène ses fichiers à 600 en fin de session."""
    global DOSSIER_ETAT_PAR_DEFAUT
    DOSSIER_ETAT_PAR_DEFAUT = dossier_etat
    if dossier_etat:
        mod_installation.preparer_dossier_etat(dossier_etat, configuration)


def verifier_coffres_ou_sortir(configuration, mode):
    """Prouve chaque coffre de `destinations` ; un coffre non prouvé arrête tout mode qui écrit."""
    destinations = configuration.get("destinations", {})
    manquants = [d for d in mod_domaines.COFFRES if "racine" not in destinations.get(d, {})]
    if manquants:
        erreur_console(traduire("config_destinations_sans_racine", domaines=", ".join(manquants)) + SUITE + traduire("suite_voir_exemple"))
        sys.exit(1)

    etats = mod_coffres.verifier_coffres(destinations)
    defaillants = [etat for etat in etats if not etat.monte]
    if defaillants and mode != "dry-run":
        for etat in defaillants:
            erreur_console(traduire("coffre_defaillant", domaine=etat.domaine, raison=etat.raison, racine=etat.racine))
        ecrire(traduire("suite_rien_touche") + " " + traduire("suite_coffre_non_monte"), 8, sys.stderr)
        sys.exit(2)
    return etats


def resoudre_modeles_ou_sortir(configuration):
    # Avant le journal et tout déplacement : un rôle sans modèle ne laisse aucune trace.
    try:
        return mod_modeles.resoudre_modeles(configuration["ollama"])
    except mod_modeles.ModeleIndisponible as erreur:
        erreur_console(texte_de(erreur))
        sys.exit(3)


def verifier_machine_ou_sortir(configuration, etats_coffres):
    """Refuse `--execute` hors des machines de `executer_sur` : la synchronisation des coffres vient après un seul Dibab."""
    machines = configuration.get("executer_sur", [])
    if machines and socket.gethostname() not in machines:
        journal, _ = initialiser_journal_session(configuration, "execute", etats_coffres)
        journal.ajouter("session_refusee", motif="executer_sur")
        erreur_console(traduire("execute_machine_refusee", machines=", ".join(machines)) + SUITE + traduire("suite_rien_touche"))
        sys.exit(4)


def identifiant_session_unique(sessions_dir, horodatage):
    """Rend `horodatage`, suffixé `-2`, `-3`… tant qu'une session de ce nom existe : deux exécutions d'une même seconde ne partagent ni journal ni rapport."""
    identifiant, numero = horodatage, 1
    while (sessions_dir / f"session_{identifiant}.jsonl").exists() or (sessions_dir / f"rapport_{identifiant}.json").exists():
        numero += 1
        identifiant = f"{horodatage}-{numero}"
    return identifiant


def initialiser_journal_session(configuration, mode, etats_coffres):
    sessions_dir = Path(configuration["suivi"]["sessions"])
    horodatage = identifiant_session_unique(sessions_dir, datetime.now().strftime("%Y-%m-%dT%H:%M:%S"))
    if mod_coffres.coffre_non_monte_contenant(sessions_dir, etats_coffres):
        return mod_journal.JournalAbsent(), horodatage
    chemin_session = sessions_dir / f"session_{horodatage}.jsonl"
    journal = mod_journal.JournalSession(chemin_session, horodatage)
    journal.ajouter("session_demarree", mode=mode, version_dibab=VERSION)
    return journal, horodatage


def cles_absentes_extraction(configuration):
    parametres = configuration.get("extraction")
    requis = ("seuil_caracteres_alphanumeriques", "pages_ocr", "resolution_ocr", "taille_max_texte",
              "repertoire_temporaire", "timeout_outils_secondes", "consigne_ocr")
    absents = [f"extraction.{cle}" for cle in requis if not parametres or cle not in parametres]
    if "keep_alive_entre_pages" not in configuration.get("ollama", {}):
        absents.append("ollama.keep_alive_entre_pages")
    if "ocr" not in configuration.get("ollama", {}).get("roles", {}):
        absents.append("ollama.roles.ocr")
    return absents


def parametres_extraction_ou_sortir(configuration):
    """Rend le bloc `extraction`, ou arrête avec le code 1 si une clé de l'extraction manque."""
    parametres = configuration.get("extraction")
    absents = cles_absentes_extraction(configuration)
    if absents:
        erreur_console(message_cles_absentes(absents))
        sys.exit(1)
    return parametres


def cles_absentes_classification(configuration):
    parametres = configuration.get("classification")
    requis = ("temperature", "num_ctx", "caracteres_max_prompt", "keep_alive_entre_documents",
              "longueur_max_champ", "longueur_max_citation", "marqueurs_mentions")
    absents = [f"classification.{cle}" for cle in requis if not parametres or cle not in parametres]
    absents += [f"ollama.roles.{role}" for role in ("tri_rapide", "classification")
                if role not in configuration.get("ollama", {}).get("roles", {})]
    absents += [cle for cle in ("categories", "personnes", "nommage") if cle not in configuration]
    return absents


def parametres_classification_ou_sortir(configuration):
    """Rend le bloc `classification`, ou arrête avec le code 1 si une clé de la cascade manque."""
    parametres = configuration.get("classification")
    absents = cles_absentes_classification(configuration)
    if absents:
        erreur_console(message_cles_absentes(absents))
        sys.exit(1)
    return parametres


def cles_absentes_classement(configuration):
    requis = [("destination", "repertoire_doublon"), ("destination", "sous_repertoire_logs"),
              ("destination", "vide_poches_prefixe"), ("nommage", "suffixe_collision"),
              ("arborescence", "personne_inconnue"), ("inventaire", "exclusions")]
    absents = [".".join(cle) for cle in requis if cle[1] not in configuration.get(cle[0], {})]
    absents += [f"arborescence.{domaine}" for domaine in mod_domaines.COFFRES
                if domaine not in configuration.get("arborescence", {})]
    return absents


def parametres_classement_ou_sortir(configuration):
    """Arrête avec le code 1 si une clé du classement ou de l'inventaire manque."""
    absents = cles_absentes_classement(configuration)
    if absents:
        erreur_console(message_cles_absentes(absents))
        sys.exit(1)


def cles_absentes_journal(configuration, mode):
    suivi = configuration.get("suivi", {})
    absents = []
    if mode in ("execute", "rollback"):
        absents += [f"suivi.{cle}" for cle in ("journal", "rotation") if cle not in suivi]
        absents += [f"suivi.rotation.{cle}" for cle in ("journal_taille_max_mo", "journal_archives_max", "sessions_max")
                    if cle not in suivi.get("rotation", {})]
    if mode in ("dry-run", "execute"):
        absents += mod_sources_distantes.cles_absentes(configuration)
        absents += mod_sources_imap.cles_absentes(configuration)
    return absents


def parametres_journal_ou_sortir(configuration, mode):
    """Arrête avec le code 1 si une clé du journal des actions, de la rotation, des sources distantes ou IMAP manque."""
    absents = cles_absentes_journal(configuration, mode)
    if absents:
        erreur_console(message_cles_absentes(absents))
        sys.exit(1)


def cles_configuration_absentes(configuration):
    """Les clés qu'un mode, `--execute` compris, exige et que la configuration ne porte pas."""
    absents = [f"destinations.{domaine}.racine" for domaine in mod_domaines.COFFRES
               if "racine" not in configuration.get("destinations", {}).get(domaine, {})]
    return (absents + cles_absentes_extraction(configuration) + cles_absentes_classification(configuration)
            + cles_absentes_classement(configuration) + cles_absentes_journal(configuration, "execute"))


def appliquer_rotation(configuration):
    rotation = configuration["suivi"]["rotation"]
    mod_rotation.tourner_journal(configuration["suivi"]["journal"], rotation["journal_taille_max_mo"], rotation["journal_archives_max"])
    mod_rotation.purger_sessions(configuration["suivi"]["sessions"], rotation["sessions_max"])


def analyser_arguments():
    parseur = ParseurTraduit(prog="dibab", description=traduire("aide_description"))
    groupe = parseur.add_mutually_exclusive_group()
    groupe.add_argument("--dry-run", action="store_true",
                        help=traduire("aide_dry_run"))
    groupe.add_argument("--execute", action="store_true",
                        help=traduire("aide_execute"))
    groupe.add_argument("--inventaire", action="store_true",
                        help=traduire("aide_inventaire"))
    groupe.add_argument("--rollback", action="store_true",
                        help=traduire("aide_rollback"))
    groupe.add_argument("--autoriser-google", type=str, default=None, metavar=traduire("aide_meta_id"),
                        help=traduire("aide_autoriser_google"))
    groupe.add_argument("--diagnose", action="store_true",
                        help=traduire("aide_diagnose"))
    groupe.add_argument("--initialiser", action="store_true",
                        help=traduire("aide_initialiser"))
    parseur.add_argument("--version", action="version", version=f"dibab {VERSION}",
                         help=traduire("aide_version"))
    parseur.add_argument("--config", type=Path, default=None, metavar=traduire("aide_meta_chemin"),
                         help=traduire("aide_config"))
    parseur.add_argument("--session", type=str, default=None, metavar=traduire("aide_meta_session"),
                         help=traduire("aide_session"))
    parseur.add_argument("--verdicts-simules", type=Path, default=None, metavar=traduire("aide_meta_fichier"),
                         help=traduire("aide_verdicts_simules"))
    arguments = parseur.parse_args()
    if arguments.verdicts_simules and (arguments.execute or arguments.rollback or arguments.inventaire
                                    or arguments.autoriser_google or arguments.diagnose):
        erreur_console(traduire("erreur_verdicts_simules"))
        sys.exit(2)
    return arguments


def autoriser_google(configuration, identifiant):
    """Consentement d'une source IMAP `oauth2` ; rend 0, ou 1 si la source est mal déclarée ou si le consentement échoue."""
    sources = [s for s in configuration.get("sources_imap", []) if s.get("id") == identifiant and s.get("authentification") == "oauth2"]
    if not sources:
        erreur_console(traduire("autoriser_source_absente", identifiant=identifiant))
        return 1
    absents = mod_sources_imap.cles_absentes({**configuration, "sources_imap": sources})
    if absents:
        erreur_console(message_cles_absentes(absents))
        return 1
    source = sources[0]
    try:
        mod_oauth2_google.autoriser(
            source["client_fichier"], source["token_fichier"], source["utilisateur"], configuration["oauth2"],
            lambda adresse: ecrire(traduire("autoriser_ouvrir_adresse", adresse=adresse)))
    except mod_oauth2_google.ErreurOAuth2 as erreur:
        erreur_console(texte_de(erreur) + SUITE + traduire("suite_rien_ecrit"))
        return 1
    ecrire(traduire("autoriser_jeton_ecrit", identifiant=identifiant))
    return 0


def determiner_mode(arguments):
    if arguments.execute:
        return "execute"
    if arguments.rollback:
        return "rollback"
    if arguments.inventaire:
        return "inventaire"
    return "dry-run"


def formater_taille(octets):
    """Affiche une taille en octets dans l'unité lisible de la langue (unite_octet, unite_kilo, unite_mega, unite_giga)."""
    valeur = float(octets)
    unites = (traduire("unite_octet"), traduire("unite_kilo"), traduire("unite_mega"), traduire("unite_giga"))
    for rang, unite in enumerate(unites):
        if valeur < 1024 or rang == len(unites) - 1:
            return f"{int(valeur)} {unite}" if rang == 0 else f"{valeur:.1f} {unite}"
        valeur /= 1024


def afficher_scan(stats_par_source, total_candidats, total_octets):
    """Affichage utilisateur structuré par source + récapitulatif global."""
    for entree in stats_par_source:
        source_id = entree["source_id"]
        chemin = entree["chemin"]
        stats = entree["stats"]
        candidats = entree["candidats"]
        accessible = stats["existe"]

        ecrire(traduire("scan_source", identifiant=source_id, chemin=chemin))
        if not accessible:
            ecrire(traduire("scan_repertoire_inaccessible"), 2)
            print()
            continue

        for candidat in candidats:
            taille = formater_taille(candidat.taille_octets)
            mtime_str = candidat.mtime.strftime("%Y-%m-%d")
            nom_relatif = candidat.chemin.name
            ecrire(traduire("scan_candidat", nom=f"{nom_relatif:<50s}", taille=taille, date=mtime_str), 2)

        if not candidats:
            ecrire(traduire("aucun_fichier_candidat"), 2)
        ecrire(traduire("scan_total_source", nombre=stats["candidats"], taille=formater_taille(stats["taille_octets"])), 2)
        print()

    ecrire("=" * 60)
    ecrire(traduire("scan_total", nombre=total_candidats, taille=formater_taille(total_octets)))
    ecrire("=" * 60)


def dedoublonner_dossiers(sources_locales, sources_supplementaires):
    """Un dossier n'est lu qu'une fois : la source dérivée d'un vide-poches (sans filtre de date) prime sur une source locale ou une autre dérivée du même dossier."""
    vus = set()
    retenues = []
    for source in sources_supplementaires:
        chemin = os.path.realpath(source["chemin"])
        if chemin not in vus:
            vus.add(chemin)
            retenues.append(source)
    locales = [source for source in sources_locales if os.path.realpath(source["chemin"]) not in vus]
    return [*locales, *retenues]


def executer_phase2(configuration, mode, journal, suivi_a_ecrire=None, sources_supplementaires=()):
    """Orchestre le scan des sources_locales et retourne la liste des candidats.

    En exécution, `suivi_a_ecrire` reçoit la date du scan de chaque source au lieu de l'écrire :
    la date n'avance qu'une fois les documents de la source traités, pour qu'un document resté en
    place après une erreur soit relu au scan suivant.
    """
    chemin_suivi = Path(configuration["suivi"]["fichier_date"])
    suivi = mod_suivi.charger(chemin_suivi)
    suivi_maj = dict(suivi)

    scan_global = configuration.get("scan", {})
    extensions = configuration.get("extensions_cibles", [])
    securite_jours = configuration["suivi"].get("securite_jours", 1)
    premier_scan_jours = configuration["suivi"].get("premier_scan_jours", 90)

    sources = dedoublonner_dossiers(configuration.get("sources_locales", []), sources_supplementaires)
    total_candidats = 0
    total_octets = 0
    stats_par_source = []
    tous_candidats = []
    horodatage_debut = datetime.now()

    for source in sources:
        sans_filtre = source.get("toujours_complete", False)
        derniere = None if sans_filtre else mod_suivi.derniere_date(suivi, source["id"])
        candidats, stats = scanner_local.scanner_source(
            source=source,
            scan_global=scan_global,
            extensions_cibles=extensions,
            derniere_date=derniere,
            securite_jours=securite_jours,
            premier_scan_jours=JOURS_SANS_FILTRE_DATE if sans_filtre else premier_scan_jours,
            maintenant=horodatage_debut,
        )

        journal.ajouter(
            "scan_source",
            source_id=source["id"],
            chemin=source["chemin"],
            existe=stats["existe"],
            fichiers_lus=stats["lus"],
            candidats=stats["candidats"],
            taille_octets=stats["taille_octets"],
            derniere_date=derniere.strftime("%Y-%m-%dT%H:%M:%S") if derniere else None,
        )

        for candidat in candidats:
            journal.ajouter(
                "candidat_scan",
                source_id=source["id"],
                chemin=str(candidat.chemin),
                taille_octets=candidat.taille_octets,
                mtime=candidat.mtime.strftime("%Y-%m-%dT%H:%M:%S"),
                dry_run=(mode != "execute"),
            )

        stats_par_source.append({
            "source_id": source["id"],
            "chemin": source["chemin"],
            "stats": stats,
            "candidats": candidats,
        })
        total_candidats += stats["candidats"]
        total_octets += stats["taille_octets"]
        tous_candidats.extend(candidats)

        if stats["existe"] and not sans_filtre:
            suivi_maj[source["id"]] = horodatage_debut
            if suivi_a_ecrire is not None:
                suivi_a_ecrire[source["id"]] = horodatage_debut

    afficher_scan(stats_par_source, total_candidats, total_octets)

    if mode == "execute" and suivi_a_ecrire is None:
        mod_suivi.sauvegarder(chemin_suivi, suivi_maj)
        journal.ajouter("suivi_sauvegarde", chemin=str(chemin_suivi))

    return tous_candidats


def charger_verdicts_simules(chemin):
    try:
        with open(chemin, "r", encoding="utf-8") as f:
            bruts = json.load(f)
        return {nom: mod_domaines.verdict_depuis_dict(donnees) for nom, donnees in bruts.items()}
    except (OSError, ValueError, AttributeError) as erreur:
        erreur_console(traduire("verdicts_illisibles", chemin=chemin, erreur=texte_de(erreur)))
        sys.exit(1)


def afficher_routage(configuration, candidats, verdicts, journal):
    """Affiche, pour chaque candidat à verdict simulé, la destination que la table de routage lui donne."""
    ecrire(traduire("routage_entete"))
    for candidat in candidats:
        verdict = verdicts.get(candidat.chemin.name)
        if verdict is None:
            ecrire(traduire("routage_pas_de_verdict", nom=candidat.chemin.name), 2)
            continue
        plan = mod_classement.planifier(candidat.chemin, verdict, configuration, candidat.mtime)
        if plan is None:
            ecrire(traduire("non_administratif_ne_bouge_pas", nom=candidat.chemin.name), 2)
        else:
            ecrire(traduire("routage_domaine", nom=candidat.chemin.name, domaine=verdict.domaine), 2)
            for cible, chemin in zip(plan.cibles, plan.chemins):
                ecrire(traduire("routage_destination", coffre=cible.coffre, zone=cible.zone, chemin=chemin, suite=""), 6)
        journal.ajouter(
            "routage_simule",
            chemin=str(candidat.chemin),
            domaine=verdict.domaine,
            destinations=[str(chemin) for chemin in plan.chemins] if plan else [],
            dry_run=True,
        )
    print()


def extraire_candidats(configuration, parametres, candidats, modele_ocr, journal, dry_run=True):
    """Extrait le texte de chaque candidat ; affiche et journalise méthode, volume et modèle, jamais le texte."""
    ecrire(traduire("extraction_entete"))
    extractions = {}
    for candidat in candidats:
        extraction = mod_extraction.extraire(candidat.chemin, parametres, configuration["ollama"], modele_ocr)
        extractions[candidat.chemin] = extraction
        libelles = {"couche_texte": traduire("extraction_methode_couche_texte"), "ocr": "OCR", "echec": traduire("extraction_methode_echec")}
        detail = traduire("extraction_detail", caracteres=extraction.caracteres, pages=extraction.pages)
        if extraction.modele:
            detail += ", " + traduire("extraction_detail_modele", modele=extraction.modele)
        detail += ", " + traduire("extraction_detail_duree", duree=f"{extraction.duree_secondes:.2f}")
        if extraction.raison:
            detail += " — " + extraction.raison
        ecrire(traduire("extraction_ligne", nom=candidat.chemin.name, methode=libelles[extraction.methode], detail=detail), 2)
        journal.ajouter(
            "extraction",
            chemin=str(candidat.chemin),
            methode=extraction.methode,
            caracteres=extraction.caracteres,
            pages=extraction.pages,
            modele=extraction.modele,
            duree_secondes=round(extraction.duree_secondes, 3),
            raison=extraction.raison,
            dry_run=dry_run,
        )
    print()
    return extractions


def libelles_motifs():
    """Le libellé de chaque motif de la zone à vérifier, liste fermée de la cascade."""
    return {mod_cascade.MOTIF_AUCUN_TEXTE: traduire("motif_aucun_texte"),
            mod_cascade.MOTIF_TRI_INCERTAIN: traduire("motif_tri_incertain"),
            mod_cascade.MOTIF_PIECE_COMMUNE: traduire("motif_piece_commune"),
            mod_cascade.MOTIF_DOMAINES_DIFFERENTS: traduire("motif_domaines_differents"),
            mod_cascade.MOTIF_DESACCORD: traduire("motif_desaccord"),
            mod_cascade.MOTIF_SANS_SIGNAL: traduire("motif_sans_signal")}


def releves_par_modele(resultat):
    """Ce que chaque modèle de classification a rendu, en champs fermés : ni destinataire ni texte."""
    return [{"modele": fine.modele, "valide": fine.valide,
             "domaine": fine.verdict.domaine if fine.valide else None,
             "categorie": fine.verdict.categorie if fine.valide else None,
             "emetteur": fine.releve.emetteur_rendu, "emetteur_cite": fine.releve.emetteur_cite,
             "destinataire_cite": fine.releve.destinataire_cite,
             "nature_destinataire": fine.releve.nature_destinataire}
            for fine in resultat.classifications]


def classer_candidats(configuration, candidats, extractions, modeles, journal):
    """Fait passer le texte des candidats par la cascade et affiche objet, verdict, accord, motif et destination, sans rien déplacer."""
    ecrire(traduire("classification_entete"))
    documents = [(candidat.chemin, extractions[candidat.chemin].texte) for candidat in candidats]
    resultats = mod_cascade.executer(documents, configuration, modeles)
    mtimes = {candidat.chemin: candidat.mtime for candidat in candidats}
    registre = mod_deplacement.Registre()
    libelles_tri = {mod_classification.ADMINISTRATIF: traduire("tri_administratif"),
                    mod_classification.NON_ADMINISTRATIF: traduire("tri_non_administratif"),
                    mod_classification.INCERTAIN: traduire("tri_incertain")}
    motifs = libelles_motifs()
    for resultat in resultats:
        verdict = resultat.verdict
        libelle_tri = libelles_tri[resultat.tri.verdict] if resultat.tri else traduire("tri_aucun_texte")
        plan = mod_classement.planifier(resultat.chemin, verdict, configuration, mtimes[resultat.chemin])
        accord = ", " + traduire("classification_accord", accord=f"{resultat.accord[0]}/{resultat.accord[1]}") if resultat.accord else ""
        domaine = verdict.domaine if verdict.administratif else traduire("domaine_sans_objet")
        ecrire(traduire("classification_ligne_accord", nom=resultat.chemin.name, tri=libelle_tri, domaine=domaine, accord=accord), 2)
        if resultat.tri is not None:
            ecrire(traduire("classification_objet", objet=verdict.objet) if verdict.objet else traduire("classification_objet_absent"), 6)
        a_verifier = bool(plan) and any(cible.zone == mod_domaines.A_VERIFIER for cible in plan.cibles)
        motif = mod_cascade.motif_a_verifier(resultat, configuration.get("pieces_communes", ())) if a_verifier else None
        if motif:
            ecrire(traduire("classification_motif", motif=motifs[motif]), 6)
        if plan is None:
            ecrire(traduire("classification_ne_bouge_pas"), 6)
        for cible, chemin in zip(plan.cibles if plan else (), plan.chemins if plan else ()):
            suite = " " + traduire("suite_non_deplace") if cible.zone == mod_domaines.A_VERIFIER else ""
            if mod_deplacement.prevoir(resultat.chemin, plan, configuration, registre) == mod_deplacement.DOUBLON:
                suite += " " + traduire("suite_doublon", repertoire=configuration["destination"]["repertoire_doublon"])
            ecrire(traduire("routage_destination", coffre=cible.coffre, zone=cible.zone, chemin=chemin, suite=suite), 6)
        fine = resultat.classification
        journal.ajouter(
            "classification",
            chemin=str(resultat.chemin),
            tri=resultat.tri.verdict if resultat.tri else None,
            objet=verdict.objet,
            modele_tri=resultat.tri.modele if resultat.tri else None,
            modele_objet=resultat.tri.modele_objet if resultat.tri else None,
            p_non_administratif=resultat.tri.p_non_administratif if resultat.tri else None,
            repli_tri=resultat.tri.repli if resultat.tri else None,
            modele_classification=fine.modele if fine else None,
            domaine=verdict.domaine if verdict.administratif else None,
            categorie=verdict.categorie,
            emetteur=verdict.emetteur,
            origine_emetteur=fine.releve.origine_emetteur if fine and verdict.emetteur else None,
            date=verdict.date.isoformat() if verdict.date else None,
            personne=verdict.personne,
            signaux=[{"domaine": s["domaine"], "nature": s["nature"]} for s in verdict.signaux],
            valide=(fine.valide if fine else None),
            raison=(fine.raison if fine and not fine.valide else resultat.tri.raison if resultat.tri else ""),
            confiance=resultat.confiance,
            motif=motif,
            par_modele=releves_par_modele(resultat),
            destinations=[str(chemin) for chemin in plan.chemins] if plan else [],
            dry_run=True,
        )
    print()


def classer_et_deplacer(configuration, candidats, extractions, modeles, journal, journal_actions=None, rapport=None):
    """Classe les candidats puis déplace chacun vers sa destination ; rend les sources dont un document a échoué."""
    ecrire(traduire("classement_entete"))
    documents = [(candidat.chemin, extractions[candidat.chemin].texte) for candidat in candidats]
    resultats = mod_cascade.executer(documents, configuration, modeles)
    par_chemin = {candidat.chemin: candidat for candidat in candidats}
    registre = mod_deplacement.Registre()
    sources_en_echec = set()
    for resultat in resultats:
        candidat = par_chemin[resultat.chemin]
        plan = mod_classement.planifier(resultat.chemin, resultat.verdict, configuration, candidat.mtime)
        if plan is None:
            ecrire(traduire("non_administratif_ne_bouge_pas", nom=resultat.chemin.name), 2)
            journal.ajouter("non_deplace", chemin=str(resultat.chemin), raison=traduire("raison_non_administratif"), dry_run=False)
            if rapport:
                rapport.compter("non_deplace")
            continue
        deplacement = mod_deplacement.deplacer(resultat.chemin, plan, configuration, registre)
        if rapport:
            rapport.compter(deplacement.action)
        if journal_actions and deplacement.action != mod_deplacement.ECHEC:
            journal_actions.enregistrer_deplacement(deplacement, resultat.verdict.domaine)
        if deplacement.action == mod_deplacement.ECHEC:
            sources_en_echec.add(candidat.source_id)
            ecrire(traduire("classement_echec", nom=resultat.chemin.name, raison=deplacement.raison), 2)
        else:
            if deplacement.action == mod_deplacement.DOUBLON:
                ecrire(traduire("classement_doublon", nom=resultat.chemin.name,
                                repertoire=configuration["destination"]["repertoire_doublon"]), 2)
            else:
                ecrire(traduire("classement_action", nom=resultat.chemin.name, action=deplacement.action), 2)
            for destination in deplacement.destinations:
                ecrire(traduire("fleche_destination", destination=destination), 6)
        journal.ajouter(
            "deplacement",
            chemin=str(resultat.chemin),
            action=deplacement.action,
            domaine=resultat.verdict.domaine,
            objet=resultat.verdict.objet,
            categorie=resultat.verdict.categorie,
            emetteur=resultat.verdict.emetteur,
            date=resultat.verdict.date.isoformat() if resultat.verdict.date else None,
            personne=resultat.verdict.personne,
            confiance=resultat.confiance,
            destinations=[str(destination) for destination in deplacement.destinations],
            empreinte=deplacement.empreinte,
            raison=deplacement.raison,
            dry_run=False,
        )
    print()
    return sources_en_echec


def executer_inventaire(configuration, journal):
    """Écrit le plan de migration de chaque coffre ; rend 0."""
    plans = mod_inventaire.construire_plans(configuration)
    ecrits = mod_inventaire.ecrire_plans(plans, configuration)
    ecrire(traduire("inventaire_entete"))
    for domaine, plan in plans.items():
        resume = plan["resume"]
        ecrire(traduire("inventaire_coffre", domaine=f"{domaine:<14s}", documents=resume["documents"], conserver=resume["conserver"],
                        a_classer=resume["a_classer"], doublons=resume["doublons_internes"],
                        presents=resume["presents_dans_autre_coffre"], a_verifier=resume["a_verifier_non_listes"],
                        sous_repertoire=configuration["destinations"][domaine]["sous_repertoire_a_verifier"]), 2)
        ecrire(traduire("inventaire_plan_ecrit", chemin=ecrits[domaine]), 6)
        journal.ajouter("inventaire", coffre=domaine, **resume)
    print()
    return 0


def modeles_de_la_cascade(configuration, modeles_retenus):
    """Les modèles retenus, avec tous ceux du rôle `classification` (le consensus les interroge ensemble) et le tri par décision.

    Rend (modèles de la cascade, `tri_decision.Resolution`).
    """
    try:
        classeurs = mod_modeles.modeles_installes_du_role(configuration["ollama"], "classification")
        resolution = mod_tri_decision.Resolution()
        if mod_tri_decision.declare(configuration):
            resolution = mod_tri_decision.resoudre(configuration, mod_modeles.lister_capacites(
                configuration["ollama"]["url"], configuration["ollama"].get("timeout_secondes", 120)))
    except mod_modeles.ModeleIndisponible as erreur:
        erreur_console(texte_de(erreur))
        sys.exit(3)
    return dict(modeles_retenus, classification=classeurs, tri_decision=resolution.choix, repli_tri=resolution.motif), resolution


def annoncer_tri_decision(resolution, modele_tri):
    """Une ligne d'en-tête quand le rôle `tri_decision` est déclaré : le choix utilisé, ou le motif du repli."""
    if not resolution.declare:
        return
    choix = resolution.choix
    if choix:
        ecrire(traduire("session_modele", role=f"{mod_tri_decision.ROLE:<14s}", modele=choix.modele), 2)
        ecrire(traduire("session_modele", role=f"{mod_tri_decision.ROLE_OBJET:<14s}", modele=choix.objet), 2)
        ecrire(traduire("session_tri_decision_seuils", seuil_non=choix.non_administratif, seuil_admin=choix.administratif,
                        minimum=choix.caracteres_min), 2)
    else:
        ecrire(traduire("session_tri_decision_repli", motif=mod_tri_decision.libelle_repli(resolution.motif, resolution.modele),
                        modele=modele_tri), 2)


def diagnostiquer_installation(option):
    """`--diagnose` : écrit le bilan des vérifications ; rend 1 au moindre échec, sinon 0."""
    verifications = mod_diagnostic.diagnostiquer(option, os.environ, CHEMIN_CONFIG, cles_configuration_absentes)
    mod_diagnostic.afficher(verifications)
    return mod_diagnostic.code_de_retour(verifications)


def initialiser_installation(option):
    """`--initialiser` : écrit la configuration de la langue de la session, sans jamais réécrire un fichier existant."""
    destination = mod_installation.destination_initialisation(option, os.environ)
    exemple = mod_installation.trouver_exemple(__file__)
    if exemple is None:
        erreur_console(traduire("initialiser_exemple_absent"))
        return 1
    try:
        ecrit = mod_installation.initialiser_configuration(destination, exemple, mod_messages.langue())
    except (OSError, mod_installation.ErreurConfiguration) as erreur:
        erreur_console(traduire("initialiser_echec", chemin=destination, erreur=texte_de(erreur)))
        return 1
    if ecrit:
        ecrire(traduire("initialiser_ecrit", chemin=destination))
    else:
        ecrire(traduire("initialiser_existante", chemin=destination))
    return 0


def main():
    """Lance la session, puis ramène les modes de l'état par défaut quelle qu'en soit l'issue."""
    global DOSSIER_ETAT_PAR_DEFAUT
    DOSSIER_ETAT_PAR_DEFAUT = None
    mod_messages.initialiser()
    try:
        return principal()
    finally:
        if DOSSIER_ETAT_PAR_DEFAUT:
            mod_installation.durcir_dossier_etat(DOSSIER_ETAT_PAR_DEFAUT)


def principal():
    arguments = analyser_arguments()
    if arguments.initialiser:
        return initialiser_installation(arguments.config)
    if arguments.diagnose:
        return diagnostiquer_installation(arguments.config)
    if arguments.autoriser_google:
        configuration, _, _ = charger_configuration(arguments.config)
        verifier_coffres_ou_sortir(configuration, "execute")
        return autoriser_google(configuration, arguments.autoriser_google)
    mode = determiner_mode(arguments)

    configuration, chemin_configuration, dossier_etat = charger_configuration(arguments.config)
    preparer_etat(dossier_etat, configuration)
    etats_coffres = verifier_coffres_ou_sortir(configuration, mode)
    if mode == "execute":
        verifier_machine_ou_sortir(configuration, etats_coffres)
    parametres = None
    if mode in ("dry-run", "execute"):
        parametres = parametres_extraction_ou_sortir(configuration)
        parametres_classification_ou_sortir(configuration)
    if mode in ("dry-run", "execute", "inventaire"):
        parametres_classement_ou_sortir(configuration)
    parametres_journal_ou_sortir(configuration, mode)
    modeles_retenus = None
    if mode in ("dry-run", "execute"):
        modeles_retenus = resoudre_modeles_ou_sortir(configuration)
    if mode in ("execute", "rollback"):
        appliquer_rotation(configuration)
    journal, horodatage = initialiser_journal_session(configuration, mode, etats_coffres)

    ecrire(traduire("session_entete", version=VERSION, horodatage=horodatage))
    ecrire(traduire("session_mode", mode=mode), 2)
    ecrire(traduire("session_configuration", chemin=chemin_configuration), 2)
    for etat in etats_coffres:
        diagnostic = traduire("coffre_monte") if etat.monte else "[!] " + etat.raison
        ecrire(traduire("session_coffre", domaine=f"{etat.domaine:<14s}", racine=etat.racine, diagnostic=diagnostic), 2)
    if journal.chemin:
        ecrire(traduire("session_journal", chemin=journal.chemin), 2)
    else:
        ecrire(traduire("session_journal_absent"), 2)
    modeles_cascade = None
    if modeles_retenus:
        modeles_cascade, resolution = modeles_de_la_cascade(configuration, modeles_retenus)
        for role, modele in modeles_retenus.items():
            ecrire(traduire("session_modele", role=f"{role:<14s}", modele=modele), 2)
        annoncer_tri_decision(resolution, modeles_retenus["tri_rapide"])
        ecrire(traduire("session_consensus", nombre=len(modeles_cascade["classification"]),
                        seuil=configuration["ollama"].get("seuil_confiance", 0)), 2)
        journal.ajouter("modeles_retenus", **modeles_retenus, classification_consensus=modeles_cascade["classification"],
                        tri_decision=resolution.choix.modele if resolution.choix else resolution.modele,
                        objet=resolution.choix.objet if resolution.choix else None, repli_tri=resolution.motif)
    print()

    if mode == "rollback":
        return executer_rollback(configuration, arguments.session, journal, horodatage)

    if mode == "inventaire":
        code = executer_inventaire(configuration, journal)
        journal.ajouter("session_terminee", mode=mode)
        return code

    if mode == "execute":
        chemin_verrou = Path(configuration["suivi"]["fichier_date"]).parent / "dibab.verrou"
        try:
            with mod_verrou.verrou(chemin_verrou):
                return executer_session(configuration, parametres, modeles_cascade, journal, horodatage)
        except mod_verrou.VerrouPris as erreur:
            journal.ajouter("session_refusee", motif="verrou")
            erreur_console(texte_de(erreur) + SUITE + traduire("suite_rien_touche"))
            return 5

    derivees = []
    if configuration.get("sources_distantes"):
        court, _ = mod_sources_distantes.executeurs(configuration)
        listages = mod_sources_distantes.lister(configuration, mod_suivi.charger(configuration["suivi"]["fichier_date"]),
                                                journal, datetime.now(), court)
        mod_sources_distantes.afficher(listages)
        derivees = mod_sources_distantes.sources_locales_derivees(configuration)
    if configuration.get("sources_imap"):
        resultats, _, _ = mod_sources_imap.traiter(configuration, mod_suivi.charger(configuration["suivi"]["fichier_date"]),
                                                   journal, datetime.now(), deposer_les_pieces=False)
        mod_sources_imap.afficher(resultats, deposer_les_pieces=False)
    derivees += mod_sources_imap.sources_locales_derivees(configuration)
    candidats = executer_phase2(configuration, mode, journal, sources_supplementaires=derivees)
    extractions = extraire_candidats(configuration, parametres, candidats, modeles_retenus["ocr"], journal)
    classer_candidats(configuration, candidats, extractions, modeles_cascade, journal)
    if arguments.verdicts_simules:
        verdicts = charger_verdicts_simules(arguments.verdicts_simules)
        afficher_routage(configuration, candidats, verdicts, journal)

    if any(not etat.monte for etat in etats_coffres):
        ecrire(traduire("dry_run_coffre_non_monte"))
    journal.ajouter("session_terminee", mode=mode)
    return 0


def rapatrier_sources_distantes(configuration, suivi, journal, rapport):
    """Rapatrie chaque source distante ; rend les sources locales à scanner, les dates à avancer et les sources en échec."""
    if not configuration.get("sources_distantes"):
        return [], {}, set()
    maintenant = datetime.now()
    court, copie = mod_sources_distantes.executeurs(configuration)
    listages = mod_sources_distantes.lister(configuration, suivi, journal, maintenant, court)
    ecrire(traduire("rapatriement_entete"))
    registre = mod_rapatriement.RegistreRapatries(Path(configuration["suivi"]["fichier_date"]).parent / "rapatries.json")
    dates, en_echec = mod_sources_distantes.rapatrier(configuration, listages, registre, journal, rapport, maintenant, court, copie)
    for source, candidats, complet, erreurs in listages:
        ligne = traduire("rapatriement_source", identifiant=source["id"], nombre=len(candidats))
        if not complet:
            ligne += ", " + traduire("rapatriement_listage_incomplet", erreurs="; ".join(erreurs))
        ecrire(ligne, 2)
    print()
    return mod_sources_distantes.sources_locales_derivees(configuration), dates, en_echec


def deposer_sources_imap(configuration, suivi, journal, rapport):
    """Dépose les pièces jointes de chaque source IMAP ; rend les sources locales à scanner, les dates à avancer et les sources en échec."""
    if not configuration.get("sources_imap"):
        return [], {}, set()
    ecrire(traduire("imap_entete"))
    resultats, dates, en_echec = mod_sources_imap.traiter(configuration, suivi, journal, datetime.now(), deposer_les_pieces=True)
    mod_sources_imap.afficher(resultats, deposer_les_pieces=True)
    rapport.deposes_imap += sum(resultat.deposees for resultat in resultats)
    return mod_sources_imap.sources_locales_derivees(configuration), dates, en_echec


def executer_rollback(configuration, session, journal, horodatage):
    """Annule une session de classement ; rend 1 si une action n'a pas pu être annulée, rien n'étant alors retiré pour elle."""
    chemin_verrou = Path(configuration["suivi"]["fichier_date"]).parent / "dibab.verrou"
    session = mod_rollback.identifiant_de_session(session)
    try:
        with mod_verrou.verrou(chemin_verrou):
            actions = mod_journal_actions.JournalActions(configuration["suivi"]["journal"], horodatage)
            if session and not mod_rollback.session_connue(actions, session):
                erreur_console(traduire("rollback_session_inconnue", session=session) + SUITE + traduire("suite_rien_touche"))
                journal.ajouter("rollback", session_annulee=session, annulees=0, echecs=0, motif="session_inconnue")
                journal.ajouter("session_terminee", mode="rollback")
                return 1
            session, resultats = mod_rollback.annuler_session(actions, session)
    except mod_verrou.VerrouPris as erreur:
        erreur_console(texte_de(erreur) + SUITE + traduire("suite_rien_touche"))
        return 5
    echecs = [resultat for resultat in resultats if not resultat.annulee]
    ecrire(traduire("rollback_bilan", session=session or traduire("rollback_aucune_action"),
                    annulees=len(resultats) - len(echecs), echecs=len(echecs)))
    for resultat in echecs:
        ecrire(traduire("rollback_echec_action", identifiant=resultat.id_action, raison=resultat.raison), 2)
    journal.ajouter("rollback", session_annulee=session, annulees=len(resultats) - len(echecs), echecs=len(echecs))
    journal.ajouter("session_terminee", mode="rollback")
    return 1 if echecs else 0


def executer_session(configuration, parametres, modeles, journal, horodatage):
    """Rapatriement, scan, extraction, classement et déplacement ; la date du scan n'avance que pour les sources sans échec."""
    rapport = mod_rapport.Rapport(horodatage, "execute")
    actions = mod_journal_actions.JournalActions(configuration["suivi"]["journal"], horodatage)
    chemin_suivi = Path(configuration["suivi"]["fichier_date"])
    suivi = mod_suivi.charger(chemin_suivi)
    derivees, dates_distantes, distantes_en_echec = rapatrier_sources_distantes(configuration, suivi, journal, rapport)
    derivees_imap, dates_imap, imap_en_echec = deposer_sources_imap(configuration, suivi, journal, rapport)
    derivees += derivees_imap
    distantes_en_echec |= imap_en_echec
    dates_de_scan = {}
    candidats = executer_phase2(configuration, "execute", journal, suivi_a_ecrire=dates_de_scan, sources_supplementaires=derivees)
    extractions = extraire_candidats(configuration, parametres, candidats, modeles["ocr"], journal, dry_run=False)
    sources_en_echec = classer_et_deplacer(configuration, candidats, extractions, modeles, journal, actions, rapport)
    suivi.update({source: date for source, date in dates_de_scan.items() if source not in sources_en_echec})
    suivi.update(dates_distantes)
    suivi.update(dates_imap)
    mod_suivi.sauvegarder(chemin_suivi, suivi)
    journal.ajouter("suivi_sauvegarde", chemin=str(chemin_suivi), sources_non_avancees=sorted(sources_en_echec | distantes_en_echec))
    journal.ajouter("session_terminee", mode="execute")
    chemin_rapport = rapport.ecrire(configuration["suivi"]["sessions"])
    ecrire(traduire("rapport_session", chemin=chemin_rapport))
    return 1 if sources_en_echec or distantes_en_echec else 0


if __name__ == "__main__":
    sys.exit(main())
