#!/usr/bin/env python3
# skrivagner.py — Point d'entrée
#
# Phases livrées :
# - Phase 1 : squelette, configuration, journal de session, modes CLI
# - Phase 2 : scan local (sources_locales) en dry-run et execute
# - Phase 2 bis : preuve des deux coffres, routage par domaine (dry-run seulement)
# - Phase 3 (extraction) : texte des candidats par couche texte ou OCR, dry-run seulement
#
# Phases à venir : classification (3), classement (4), rollback (5), SSH (6), IMAP (7).

import argparse
import json
import sys
import os
from datetime import datetime
from pathlib import Path

from modules import chemins as mod_chemins
from modules import coffres as mod_coffres
from modules import domaines as mod_domaines
from modules import extraction as mod_extraction
from modules import journal as mod_journal
from modules import modeles as mod_modeles
from modules import pieces_communes as mod_pieces_communes
from modules import scanner_local
from modules import suivi as mod_suivi


VERSION = "0.4.0-phase3-extraction"

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
    groupe.add_argument("--rollback", action="store_true",
                        help="Annule la dernière session (Phase 5)")
    parseur.add_argument("--session", type=str, default=None,
                         help="Identifiant de session à annuler (avec --rollback)")
    parseur.add_argument("--verdicts-simules", type=Path, default=None, metavar="FICHIER",
                         help="Dry-run : JSON {nom de fichier: verdict} dont le routage s'affiche")
    arguments = parseur.parse_args()
    if arguments.verdicts_simules and (arguments.execute or arguments.rollback):
        parseur.error("--verdicts-simules ne s'emploie qu'en dry-run")
    return arguments


def determiner_mode(arguments):
    if arguments.execute:
        return "execute"
    if arguments.rollback:
        return "rollback"
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


def executer_phase2(configuration, mode, journal):
    """Orchestre le scan des sources_locales et retourne la liste des candidats."""
    chemin_suivi = Path(configuration["suivi"]["fichier_date"])
    suivi = mod_suivi.charger(chemin_suivi)
    suivi_maj = dict(suivi)

    scan_global = configuration.get("scan", {})
    extensions = configuration.get("extensions_cibles", [])
    securite_jours = configuration["suivi"].get("securite_jours", 1)
    premier_scan_jours = configuration["suivi"].get("premier_scan_jours", 90)

    sources = configuration.get("sources_locales", [])
    total_candidats = 0
    total_octets = 0
    stats_par_source = []
    tous_candidats = []
    horodatage_debut = datetime.now()

    for source in sources:
        derniere = mod_suivi.derniere_date(suivi, source["id"])
        candidats, stats = scanner_local.scanner_source(
            source=source,
            scan_global=scan_global,
            extensions_cibles=extensions,
            derniere_date=derniere,
            securite_jours=securite_jours,
            premier_scan_jours=premier_scan_jours,
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

        if stats["existe"]:
            suivi_maj[source["id"]] = horodatage_debut

    afficher_scan(stats_par_source, total_candidats, total_octets)

    if mode == "execute":
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
        plan = mod_pieces_communes.planifier(candidat.chemin, verdict, configuration, candidat.mtime)
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


def extraire_candidats(configuration, parametres, candidats, modele_ocr, journal):
    """Extrait le texte de chaque candidat ; affiche et journalise méthode, volume et modèle, jamais le texte."""
    print("Extraction du texte (dry-run, le texte n'est ni affiché ni écrit)")
    for candidat in candidats:
        extraction = mod_extraction.extraire(candidat.chemin, parametres, configuration["ollama"], modele_ocr)
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
            dry_run=True,
        )
    print()


def main():
    arguments = analyser_arguments()
    mode = determiner_mode(arguments)

    configuration = charger_configuration()
    etats_coffres = verifier_coffres_ou_sortir(configuration, mode)
    parametres = parametres_extraction_ou_sortir(configuration) if mode == "dry-run" else None
    modeles_retenus = None
    if mode != "rollback":
        modeles_retenus = resoudre_modeles_ou_sortir(configuration)
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
    if modeles_retenus:
        for role, modele in modeles_retenus.items():
            print(f"  Modèle {role:<14s}: {modele}")
        journal.ajouter("modeles_retenus", **modeles_retenus)
    print()

    if mode == "rollback":
        print("Phase 5 (rollback) non encore implémentée.")
        journal.ajouter("phase_non_implementee", phase=5)
        return 0

    candidats = executer_phase2(configuration, mode, journal)
    if mode == "dry-run":
        extraire_candidats(configuration, parametres, candidats, modeles_retenus["ocr"], journal)
    if arguments.verdicts_simules:
        verdicts = charger_verdicts_simules(arguments.verdicts_simules)
        afficher_routage(configuration, candidats, verdicts, journal)

    print()
    print("Classification (phase 3), classement, rollback, SSH et IMAP (phases 4 à 7)")
    print("non encore implémentés.")
    journal.ajouter("session_terminee", mode=mode)
    return 0


if __name__ == "__main__":
    sys.exit(main())
