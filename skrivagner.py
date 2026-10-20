#!/usr/bin/env python3
# skrivagner.py — Point d'entrée
#
# Phases livrées :
# - Phase 1 : squelette, configuration, journal de session, modes CLI
# - Phase 2 : scan local (sources_locales) en dry-run et execute
#
# Phases à venir : OCR (3), classement (4), rollback (5), SSH (6), IMAP (7).

import argparse
import json
import sys
import os
from datetime import datetime
from pathlib import Path

from modules import chemins as mod_chemins
from modules import journal as mod_journal
from modules import modeles as mod_modeles
from modules import scanner_local
from modules import suivi as mod_suivi


VERSION = "0.3.0-phase2bis"

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


def verifier_destination(configuration):
    racine = Path(configuration["destination"]["racine"])
    if not racine.exists():
        sys.stderr.write(
            f"ERREUR : répertoire de destination introuvable : {racine}\n"
            f"        Si tu utilises un coffre chiffré, vérifie qu'il est ouvert.\n"
        )
        sys.exit(2)
    if not os.access(racine, os.W_OK):
        sys.stderr.write(
            f"ERREUR : répertoire de destination non accessible en écriture : {racine}\n"
        )
        sys.exit(2)
    return racine


def resoudre_modeles_ou_sortir(configuration):
    # Avant le journal et tout déplacement : un rôle sans modèle ne laisse aucune trace.
    try:
        return mod_modeles.resoudre_modeles(configuration["ollama"])
    except mod_modeles.ModeleIndisponible as erreur:
        sys.stderr.write(f"ERREUR : {erreur}\n")
        sys.exit(3)


def initialiser_journal_session(configuration, mode):
    sessions_dir = Path(configuration["suivi"]["sessions"])
    horodatage = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
    chemin_session = sessions_dir / f"session_{horodatage}.jsonl"
    journal = mod_journal.JournalSession(chemin_session, horodatage)
    journal.ajouter("session_demarree", mode=mode, version_skrivagner=VERSION)
    return journal, horodatage


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
    return parseur.parse_args()


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
    """Orchestre le scan des sources_locales et retourne (candidats, suivi_maj)."""
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

        if stats["existe"]:
            suivi_maj[source["id"]] = horodatage_debut

    afficher_scan(stats_par_source, total_candidats, total_octets)

    if mode == "execute":
        mod_suivi.sauvegarder(chemin_suivi, suivi_maj)
        journal.ajouter("suivi_sauvegarde", chemin=str(chemin_suivi))

    return total_candidats


def main():
    arguments = analyser_arguments()
    mode = determiner_mode(arguments)

    configuration = charger_configuration()
    racine_destination = verifier_destination(configuration)
    modeles_retenus = None
    if mode != "rollback":
        modeles_retenus = resoudre_modeles_ou_sortir(configuration)
    journal, horodatage = initialiser_journal_session(configuration, mode)

    print(f"Skrivagner {VERSION} — session {horodatage}")
    print(f"  Mode               : {mode}")
    print(f"  Destination        : {racine_destination}")
    print(f"  Journal de session : {journal.chemin}")
    if modeles_retenus:
        for role, modele in modeles_retenus.items():
            print(f"  Modèle {role:<14s}: {modele}")
        journal.ajouter("modeles_retenus", **modeles_retenus)
    print()

    if mode == "rollback":
        print("Phase 5 (rollback) non encore implémentée.")
        journal.ajouter("phase_non_implementee", phase=5)
        return 0

    executer_phase2(configuration, mode, journal)

    print()
    print("Phases 3 à 7 (OCR, classification, classement, rollback,")
    print("SSH, IMAP) non encore implémentées.")
    journal.ajouter("session_terminee", mode=mode)
    return 0


if __name__ == "__main__":
    sys.exit(main())
