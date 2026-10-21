#!/usr/bin/env python3
# skrivagner.py — Point d'entrée
#
# Phases livrées :
# - Phase 1 : squelette, configuration, journal de session, modes CLI
# - Phase 2 : scan local (sources_locales) en dry-run et execute
# - Phase 2 bis : preuve des deux coffres, routage par domaine (dry-run seulement)
# - Phase 3 (extraction) : texte des candidats par couche texte ou OCR, dry-run seulement
# - Phase 3 (classification) : tri rapide, classification fine et domaine, dry-run seulement
#
# - Phase 4 : classement par domaine, déplacement sûr (--execute), inventaire de l'existant (--inventaire)
#
# - Phase 5 : journal des actions, rapport de session, rollback, rotation
# - Phase 6 : sources distantes par ssh (listage, rapatriement dans le vide-poches)
#
# - Phase 7 : sources IMAP en lecture seule (pièces jointes déposées dans le vide-poches)

import argparse
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
from modules import deplacement as mod_deplacement
from modules import domaines as mod_domaines
from modules import extraction as mod_extraction
from modules import inventaire as mod_inventaire
from modules import journal as mod_journal
from modules import journal_actions as mod_journal_actions
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
from modules import verrou as mod_verrou


VERSION = "0.7.0-phase6-sources-distantes"

# Un vide-poches se relit en entier : tout ce qui s'y trouve attend son classement.
JOURS_SANS_FILTRE_DATE = 36500

CHEMIN_RACINE = Path(__file__).resolve().parent
CHEMIN_CONFIG = CHEMIN_RACINE / "config.json"


def charger_configuration():
    if not CHEMIN_CONFIG.exists():
        sys.stderr.write(
            f"ERREUR : configuration introuvable : {CHEMIN_CONFIG}\n"
            f"        Copier config.exemple.json en config.json et l'adapter.\n"
        )
        sys.exit(1)
    try:
        with open(CHEMIN_CONFIG, "r", encoding="utf-8") as f:
            return mod_chemins.developper_chemins(json.load(f))
    except json.JSONDecodeError as erreur:
        sys.stderr.write(f"ERREUR : config.json invalide : {erreur}\n")
        sys.exit(1)


def verifier_coffres_ou_sortir(configuration, mode):
    """Prouve chaque coffre de `destinations` ; un coffre non prouvé arrête tout mode qui écrit."""
    destinations = configuration.get("destinations", {})
    manquants = [d for d in mod_domaines.COFFRES if "racine" not in destinations.get(d, {})]
    if manquants:
        sys.stderr.write(
            f"ERREUR : config.json : `destinations` sans racine pour : {', '.join(manquants)}\n"
            f"        Voir config.exemple.json.\n"
        )
        sys.exit(1)

    etats = mod_coffres.verifier_coffres(destinations)
    defaillants = [etat for etat in etats if not etat.monte]
    if defaillants and mode != "dry-run":
        for etat in defaillants:
            sys.stderr.write(f"ERREUR : coffre {etat.domaine} : {etat.raison} ({etat.racine})\n")
        sys.stderr.write("        Rien n'a été touché. Montez le répertoire de destination, puis relancez.\n")
        sys.exit(2)
    return etats


def resoudre_modeles_ou_sortir(configuration):
    # Avant le journal et tout déplacement : un rôle sans modèle ne laisse aucune trace.
    try:
        return mod_modeles.resoudre_modeles(configuration["ollama"])
    except mod_modeles.ModeleIndisponible as erreur:
        sys.stderr.write(f"ERREUR : {erreur}\n")
        sys.exit(3)


def verifier_machine_ou_sortir(configuration):
    """Refuse `--execute` hors des machines de `executer_sur` : la synchronisation des coffres vient après un seul Skrivagner."""
    machines = configuration.get("executer_sur", [])
    if machines and socket.gethostname() not in machines:
        sys.stderr.write(f"ERREUR : --execute ne tourne que sur : {', '.join(machines)} (config.json : executer_sur).\n"
                         f"        Rien n'a été touché.\n")
        sys.exit(4)


def initialiser_journal_session(configuration, mode, etats_coffres):
    sessions_dir = Path(configuration["suivi"]["sessions"])
    horodatage = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
    if mod_coffres.coffre_non_monte_contenant(sessions_dir, etats_coffres):
        return mod_journal.JournalAbsent(), horodatage
    chemin_session = sessions_dir / f"session_{horodatage}.jsonl"
    journal = mod_journal.JournalSession(chemin_session, horodatage)
    journal.ajouter("session_demarree", mode=mode, version_skrivagner=VERSION)
    return journal, horodatage


def parametres_extraction_ou_sortir(configuration):
    """Rend le bloc `extraction`, ou arrête avec le code 1 si une clé de l'extraction manque."""
    parametres = configuration.get("extraction")
    requis = ("seuil_caracteres_alphanumeriques", "pages_ocr", "resolution_ocr", "taille_max_texte",
              "repertoire_temporaire", "timeout_outils_secondes", "consigne_ocr")
    absents = [f"extraction.{cle}" for cle in requis if not parametres or cle not in parametres]
    if "keep_alive_entre_pages" not in configuration["ollama"]:
        absents.append("ollama.keep_alive_entre_pages")
    if "ocr" not in configuration["ollama"].get("roles", {}):
        absents.append("ollama.roles.ocr")
    if absents:
        sys.stderr.write(f"ERREUR : config.json : clés absentes : {', '.join(absents)}\n"
                         f"        Voir config.exemple.json.\n")
        sys.exit(1)
    return parametres


def parametres_classification_ou_sortir(configuration):
    """Rend le bloc `classification`, ou arrête avec le code 1 si une clé de la cascade manque."""
    parametres = configuration.get("classification")
    requis = ("temperature", "num_ctx", "caracteres_max_prompt", "keep_alive_entre_documents",
              "longueur_max_champ", "longueur_max_citation", "marqueurs_mentions")
    absents = [f"classification.{cle}" for cle in requis if not parametres or cle not in parametres]
    absents += [f"ollama.roles.{role}" for role in ("tri_rapide", "classification")
                if role not in configuration["ollama"].get("roles", {})]
    absents += [cle for cle in ("categories", "personnes", "nommage") if cle not in configuration]
    if absents:
        sys.stderr.write(f"ERREUR : config.json : clés absentes : {', '.join(absents)}\n"
                         f"        Voir config.exemple.json.\n")
        sys.exit(1)
    return parametres


def parametres_classement_ou_sortir(configuration):
    """Arrête avec le code 1 si une clé du classement ou de l'inventaire manque."""
    requis = [("destination", "repertoire_doublon"), ("destination", "sous_repertoire_logs"),
              ("destination", "vide_poches_prefixe"), ("nommage", "suffixe_collision"),
              ("arborescence", "personne_inconnue"), ("inventaire", "exclusions")]
    absents = [".".join(cle) for cle in requis if cle[1] not in configuration.get(cle[0], {})]
    absents += [f"arborescence.{domaine}" for domaine in mod_domaines.COFFRES
                if domaine not in configuration.get("arborescence", {})]
    if absents:
        sys.stderr.write(f"ERREUR : config.json : clés absentes : {', '.join(absents)}\n"
                         f"        Voir config.exemple.json.\n")
        sys.exit(1)


def parametres_journal_ou_sortir(configuration, mode):
    """Arrête avec le code 1 si une clé du journal des actions, de la rotation, des sources distantes ou IMAP manque."""
    suivi = configuration.get("suivi", {})
    absents = []
    if mode in ("execute", "rollback"):
        absents += [f"suivi.{cle}" for cle in ("journal", "rotation") if cle not in suivi]
        absents += [f"suivi.rotation.{cle}" for cle in ("journal_taille_max_mo", "journal_archives_max", "sessions_max")
                    if cle not in suivi.get("rotation", {})]
    if mode in ("dry-run", "execute"):
        absents += mod_sources_distantes.cles_absentes(configuration)
        absents += mod_sources_imap.cles_absentes(configuration)
    if absents:
        sys.stderr.write(f"ERREUR : config.json : clés absentes : {', '.join(absents)}\n"
                         f"        Voir config.exemple.json.\n")
        sys.exit(1)


def appliquer_rotation(configuration):
    rotation = configuration["suivi"]["rotation"]
    mod_rotation.tourner_journal(configuration["suivi"]["journal"], rotation["journal_taille_max_mo"], rotation["journal_archives_max"])
    mod_rotation.purger_sessions(configuration["suivi"]["sessions"], rotation["sessions_max"])


def analyser_arguments():
    parseur = argparse.ArgumentParser(
        prog="skrivagner",
        description="Tri automatisé de documents administratifs personnels.",
    )
    groupe = parseur.add_mutually_exclusive_group()
    groupe.add_argument("--dry-run", action="store_true",
                        help="Mode simulation (défaut) — aucun déplacement réel")
    groupe.add_argument("--execute", action="store_true",
                        help="Mode réel — déplace effectivement les fichiers")
    groupe.add_argument("--inventaire", action="store_true",
                        help="Lit l'existant des coffres et écrit un plan de migration, sans rien déplacer")
    groupe.add_argument("--rollback", action="store_true",
                        help="Annule la dernière session de classement, ou celle de --session")
    groupe.add_argument("--autoriser-google", type=str, default=None, metavar="ID",
                        help="Consentement OAuth2 d'une source IMAP Google (écrit son fichier de jeton)")
    parseur.add_argument("--session", type=str, default=None,
                         help="Identifiant de session à annuler (avec --rollback)")
    parseur.add_argument("--verdicts-simules", type=Path, default=None, metavar="FICHIER",
                         help="Dry-run : JSON {nom de fichier: verdict} dont le routage s'affiche")
    arguments = parseur.parse_args()
    if arguments.verdicts_simules and (arguments.execute or arguments.rollback or arguments.inventaire
                                    or arguments.autoriser_google):
        parseur.error("--verdicts-simules ne s'emploie qu'en dry-run")
    return arguments


def autoriser_google(configuration, identifiant):
    """Consentement d'une source IMAP `oauth2` ; rend 0, ou 1 si la source est mal déclarée ou si le consentement échoue."""
    sources = [s for s in configuration.get("sources_imap", []) if s.get("id") == identifiant and s.get("authentification") == "oauth2"]
    if not sources:
        sys.stderr.write(f"ERREUR : aucune source IMAP « {identifiant} » avec authentification oauth2 dans config.json\n")
        return 1
    absents = mod_sources_imap.cles_absentes({**configuration, "sources_imap": sources})
    if absents:
        sys.stderr.write(f"ERREUR : config.json : clés absentes : {', '.join(absents)}\n        Voir config.exemple.json.\n")
        return 1
    source = sources[0]
    try:
        mod_oauth2_google.autoriser(
            source["client_fichier"], source["token_fichier"], source["utilisateur"], configuration["oauth2"],
            lambda adresse: print(f"Ouvrir cette adresse dans un navigateur, puis accepter le consentement :\n\n{adresse}\n", flush=True))
    except mod_oauth2_google.ErreurOAuth2 as erreur:
        sys.stderr.write(f"ERREUR : {erreur}\n        Rien n'a été écrit.\n")
        return 1
    print(f"Jeton écrit pour la source {identifiant}.")
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
    """Affiche une taille en octets dans une unité lisible (o, Ko, Mo, Go)."""
    valeur = float(octets)
    for unite in ("o", "Ko", "Mo", "Go"):
        if valeur < 1024 or unite == "Go":
            if unite == "o":
                return f"{int(valeur)} {unite}"
            return f"{valeur:.1f} {unite}"
        valeur /= 1024
    return f"{valeur:.1f} Go"


def afficher_scan(stats_par_source, total_candidats, total_octets):
    """Affichage utilisateur structuré par source + récapitulatif global."""
    for entree in stats_par_source:
        source_id = entree["source_id"]
        chemin = entree["chemin"]
        stats = entree["stats"]
        candidats = entree["candidats"]
        accessible = stats["existe"]

        print(f"Source : {source_id} ({chemin})")
        if not accessible:
            print("  [!] Répertoire inaccessible, source ignorée.")
            print()
            continue

        for candidat in candidats:
            taille = formater_taille(candidat.taille_octets)
            mtime_str = candidat.mtime.strftime("%Y-%m-%d")
            nom_relatif = candidat.chemin.name
            print(f"  - {nom_relatif:<50s} ({taille}, mtime {mtime_str})")

        if not candidats:
            print("  (aucun fichier candidat)")
        print(f"  Total source : {stats['candidats']} fichier(s), "
              f"{formater_taille(stats['taille_octets'])}")
        print()

    print("=" * 60)
    print(f"Total scan : {total_candidats} fichier(s) candidat(s), "
          f"{formater_taille(total_octets)}")
    print("=" * 60)


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
        sys.stderr.write(f"ERREUR : verdicts simulés illisibles ({chemin}) : {erreur}\n")
        sys.exit(1)


def afficher_routage(configuration, candidats, verdicts, journal):
    """Affiche, pour chaque candidat à verdict simulé, la destination que la table de routage lui donne."""
    print("Routage simulé (verdicts fournis, aucun déplacement)")
    for candidat in candidats:
        verdict = verdicts.get(candidat.chemin.name)
        if verdict is None:
            print(f"  - {candidat.chemin.name} : pas de verdict simulé")
            continue
        plan = mod_classement.planifier(candidat.chemin, verdict, configuration, candidat.mtime)
        if plan is None:
            print(f"  - {candidat.chemin.name} : non administratif, ne bouge pas")
        else:
            print(f"  - {candidat.chemin.name} : domaine {verdict.domaine}")
            for cible, chemin in zip(plan.cibles, plan.chemins):
                print(f"      -> coffre {cible.coffre}, {cible.zone} : {chemin}")
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
    print("Extraction du texte (le texte n'est ni affiché ni écrit)")
    extractions = {}
    for candidat in candidats:
        extraction = mod_extraction.extraire(candidat.chemin, parametres, configuration["ollama"], modele_ocr)
        extractions[candidat.chemin] = extraction
        libelles = {"couche_texte": "couche texte", "ocr": "OCR", "echec": "échec"}
        detail = f"{extraction.caracteres} caractère(s), {extraction.pages} page(s)"
        if extraction.modele:
            detail += f", modèle {extraction.modele}"
        detail += f", {extraction.duree_secondes:.2f} s"
        if extraction.raison:
            detail += f" — {extraction.raison}"
        print(f"  - {candidat.chemin.name} : {libelles[extraction.methode]}, {detail}")
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


def classer_candidats(configuration, candidats, extractions, modeles, journal):
    """Fait passer le texte des candidats par la cascade et affiche verdict, domaine et destination, sans rien déplacer."""
    print("Classification (dry-run, aucun déplacement ; le texte n'est ni affiché ni écrit)")
    documents = [(candidat.chemin, extractions[candidat.chemin].texte) for candidat in candidats]
    resultats = mod_cascade.executer(documents, configuration, modeles)
    mtimes = {candidat.chemin: candidat.mtime for candidat in candidats}
    registre = mod_deplacement.Registre()
    libelles_tri = {mod_classification.ADMINISTRATIF: "administratif", mod_classification.NON_ADMINISTRATIF: "non administratif",
                    mod_classification.INCERTAIN: "incertain"}
    for resultat in resultats:
        verdict = resultat.verdict
        libelle_tri = libelles_tri[resultat.tri.verdict] if resultat.tri else "aucun texte"
        plan = mod_classement.planifier(resultat.chemin, verdict, configuration, mtimes[resultat.chemin])
        confiance = f", confiance {resultat.confiance:.2f}" if resultat.confiance is not None else ""
        print(f"  - {resultat.chemin.name} : tri {libelle_tri}, domaine {verdict.domaine if verdict.administratif else 'sans objet'}{confiance}")
        if plan is None:
            print("      -> ne bouge pas (non administratif)")
        for cible, chemin in zip(plan.cibles if plan else (), plan.chemins if plan else ()):
            suite = " (non déplacé)" if cible.zone == mod_domaines.A_VERIFIER else ""
            if mod_deplacement.prevoir(resultat.chemin, plan, configuration, registre) == mod_deplacement.DOUBLON:
                suite += " (doublon : irait dans doublon/)"
            print(f"      -> coffre {cible.coffre}, {cible.zone} : {chemin}{suite}")
        fine = resultat.classification
        journal.ajouter(
            "classification",
            chemin=str(resultat.chemin),
            tri=resultat.tri.verdict if resultat.tri else None,
            modele_tri=resultat.tri.modele if resultat.tri else None,
            modele_classification=fine.modele if fine else None,
            domaine=verdict.domaine if verdict.administratif else None,
            categorie=verdict.categorie,
            emetteur=verdict.emetteur,
            date=verdict.date.isoformat() if verdict.date else None,
            personne=verdict.personne,
            signaux=[{"domaine": s["domaine"], "nature": s["nature"]} for s in verdict.signaux],
            valide=(fine.valide if fine else None),
            raison=(fine.raison if fine and not fine.valide else resultat.tri.raison if resultat.tri else ""),
            confiance=resultat.confiance,
            destinations=[str(chemin) for chemin in plan.chemins] if plan else [],
            dry_run=True,
        )
    print()


def classer_et_deplacer(configuration, candidats, extractions, modeles, journal, journal_actions=None, rapport=None):
    """Classe les candidats puis déplace chacun vers sa destination ; rend les sources dont un document a échoué."""
    print("Classement (exécution : chaque document est copié, vérifié par SHA256, puis retiré de sa source)")
    documents = [(candidat.chemin, extractions[candidat.chemin].texte) for candidat in candidats]
    resultats = mod_cascade.executer(documents, configuration, modeles)
    par_chemin = {candidat.chemin: candidat for candidat in candidats}
    registre = mod_deplacement.Registre()
    sources_en_echec = set()
    for resultat in resultats:
        candidat = par_chemin[resultat.chemin]
        plan = mod_classement.planifier(resultat.chemin, resultat.verdict, configuration, candidat.mtime)
        if plan is None:
            print(f"  - {resultat.chemin.name} : non administratif, ne bouge pas")
            journal.ajouter("non_deplace", chemin=str(resultat.chemin), raison="non administratif", dry_run=False)
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
            print(f"  - {resultat.chemin.name} : ÉCHEC, laissé en place ({deplacement.raison})")
        else:
            print(f"  - {resultat.chemin.name} : {deplacement.action}")
            for destination in deplacement.destinations:
                print(f"      -> {destination}")
        journal.ajouter(
            "deplacement",
            chemin=str(resultat.chemin),
            action=deplacement.action,
            domaine=resultat.verdict.domaine,
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
    print("Inventaire de l'existant (lecture seule, rien n'est déplacé)")
    for domaine, plan in plans.items():
        resume = plan["resume"]
        print(f"  Coffre {domaine:<14s}: {resume['documents']} document(s), {resume['conserver']} dans la zone classée, "
              f"{resume['a_classer']} à classer, {resume['doublons_internes']} doublon(s), "
              f"{resume['presents_dans_autre_coffre']} présent(s) dans l'autre coffre")
        print(f"      plan écrit : {ecrits[domaine]}")
        journal.ajouter("inventaire", coffre=domaine, **resume)
    print()
    return 0


def modeles_de_la_cascade(configuration, modeles_retenus):
    """Les modèles retenus, avec tous ceux du rôle `classification` : le consensus les interroge ensemble."""
    try:
        classeurs = mod_modeles.modeles_installes_du_role(configuration["ollama"], "classification")
    except mod_modeles.ModeleIndisponible as erreur:
        sys.stderr.write(f"ERREUR : {erreur}\n")
        sys.exit(3)
    return dict(modeles_retenus, classification=classeurs)


def main():
    arguments = analyser_arguments()
    if arguments.autoriser_google:
        configuration = charger_configuration()
        verifier_coffres_ou_sortir(configuration, "execute")
        return autoriser_google(configuration, arguments.autoriser_google)
    mode = determiner_mode(arguments)

    configuration = charger_configuration()
    etats_coffres = verifier_coffres_ou_sortir(configuration, mode)
    if mode == "execute":
        verifier_machine_ou_sortir(configuration)
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

    print(f"Skrivagner {VERSION} — session {horodatage}")
    print(f"  Mode               : {mode}")
    for etat in etats_coffres:
        diagnostic = "monté" if etat.monte else f"[!] {etat.raison}"
        print(f"  Coffre {etat.domaine:<14s}: {etat.racine} — {diagnostic}")
    if journal.chemin:
        print(f"  Journal de session : {journal.chemin}")
    else:
        print("  Journal de session : non écrit (coffre non monté, rien ne se dépose en clair)")
    modeles_cascade = None
    if modeles_retenus:
        modeles_cascade = modeles_de_la_cascade(configuration, modeles_retenus)
        for role, modele in modeles_retenus.items():
            print(f"  Modèle {role:<14s}: {modele}")
        print(f"  Consensus          : {len(modeles_cascade['classification'])} modèle(s) de classification, "
              f"seuil {configuration['ollama'].get('seuil_confiance', 0)}")
        journal.ajouter("modeles_retenus", **modeles_retenus, classification_consensus=modeles_cascade["classification"])
    print()

    if mode == "rollback":
        return executer_rollback(configuration, arguments.session, journal, horodatage)

    if mode == "inventaire":
        code = executer_inventaire(configuration, journal)
        journal.ajouter("session_terminee", mode=mode)
        return code

    if mode == "execute":
        chemin_verrou = Path(configuration["suivi"]["fichier_date"]).parent / "skrivagner.verrou"
        try:
            with mod_verrou.verrou(chemin_verrou):
                return executer_session(configuration, parametres, modeles_cascade, journal, horodatage)
        except mod_verrou.VerrouPris as erreur:
            sys.stderr.write(f"ERREUR : {erreur}\n        Rien n'a été touché.\n")
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

    journal.ajouter("session_terminee", mode=mode)
    return 0


def rapatrier_sources_distantes(configuration, suivi, journal, rapport):
    """Rapatrie chaque source distante ; rend les sources locales à scanner, les dates à avancer et les sources en échec."""
    if not configuration.get("sources_distantes"):
        return [], {}, set()
    maintenant = datetime.now()
    court, copie = mod_sources_distantes.executeurs(configuration)
    listages = mod_sources_distantes.lister(configuration, suivi, journal, maintenant, court)
    print("Rapatriement des sources distantes (copie vérifiée par empreinte, rien n'est retiré côté distant)")
    registre = mod_rapatriement.RegistreRapatries(Path(configuration["suivi"]["fichier_date"]).parent / "rapatries.json")
    dates, en_echec = mod_sources_distantes.rapatrier(configuration, listages, registre, journal, rapport, maintenant, court, copie)
    for source, candidats, complet, erreurs in listages:
        print(f"  {source['id']} : {len(candidats)} candidat(s)" + ("" if complet else f", listage incomplet : {'; '.join(erreurs)}"))
    print()
    return mod_sources_distantes.sources_locales_derivees(configuration), dates, en_echec


def deposer_sources_imap(configuration, suivi, journal, rapport):
    """Dépose les pièces jointes de chaque source IMAP ; rend les sources locales à scanner, les dates à avancer et les sources en échec."""
    if not configuration.get("sources_imap"):
        return [], {}, set()
    print("Sources IMAP (lecture seule : rien n'est modifié ni supprimé dans la boîte)")
    resultats, dates, en_echec = mod_sources_imap.traiter(configuration, suivi, journal, datetime.now(), deposer_les_pieces=True)
    mod_sources_imap.afficher(resultats, deposer_les_pieces=True)
    rapport.deposes_imap += sum(resultat.deposees for resultat in resultats)
    return mod_sources_imap.sources_locales_derivees(configuration), dates, en_echec


def executer_rollback(configuration, session, journal, horodatage):
    """Annule une session de classement ; rend 1 si une action n'a pas pu être annulée, rien n'étant alors retiré pour elle."""
    chemin_verrou = Path(configuration["suivi"]["fichier_date"]).parent / "skrivagner.verrou"
    try:
        with mod_verrou.verrou(chemin_verrou):
            actions = mod_journal_actions.JournalActions(configuration["suivi"]["journal"], horodatage)
            session, resultats = mod_rollback.annuler_session(actions, session)
    except mod_verrou.VerrouPris as erreur:
        sys.stderr.write(f"ERREUR : {erreur}\n        Rien n'a été touché.\n")
        return 5
    echecs = [resultat for resultat in resultats if not resultat.annulee]
    print(f"Rollback de la session {session or '(aucune action à annuler)'} : "
          f"{len(resultats) - len(echecs)} annulée(s), {len(echecs)} en échec")
    for resultat in echecs:
        print(f"  - action {resultat.id_action} : {resultat.raison} (rien n'a été retiré)")
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
    print(f"Rapport de session : {chemin_rapport}")
    return 1 if sources_en_echec or distantes_en_echec else 0


if __name__ == "__main__":
    sys.exit(main())
