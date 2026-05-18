#!/usr/bin/env python3
# skrivagner.py — Point d'entrée
#
# Phase 1 — squelette opérationnel :
# - Vérifie l'accessibilité du répertoire de destination
# - Charge config.json
# - Gère les modes --dry-run (défaut), --execute, --rollback
# - Initialise le journal de session
# - Délègue aux modules de scan/classement (à implémenter en phases ultérieures)

import argparse
import json
import sys
import os
from datetime import datetime
from pathlib import Path


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
            return json.load(f)
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


def initialiser_journal_session(configuration, mode):
    sessions_dir = Path(configuration["suivi"]["sessions"])
    sessions_dir.mkdir(parents=True, exist_ok=True)

    horodatage = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
    chemin_session = sessions_dir / f"session_{horodatage}.jsonl"

    enregistrement = {
        "timestamp": horodatage,
        "evenement": "session_demarree",
        "mode": mode,
        "version_skrivagner": "0.1.0-phase1",
    }
    with open(chemin_session, "a", encoding="utf-8") as f:
        f.write(json.dumps(enregistrement, ensure_ascii=False) + "\n")

    return chemin_session, horodatage


def analyser_arguments():
    parseur = argparse.ArgumentParser(
        prog="skrivagner",
        description="Tri automatisé de documents administratifs personnels.",
    )
    groupe = parseur.add_mutually_exclusive_group()
    groupe.add_argument(
        "--dry-run",
        action="store_true",
        help="Mode simulation (défaut) — aucun déplacement réel",
    )
    groupe.add_argument(
        "--execute",
        action="store_true",
        help="Mode réel — déplace effectivement les fichiers",
    )
    groupe.add_argument(
        "--rollback",
        action="store_true",
        help="Annule la dernière session (ou celle indiquée par --session)",
    )
    parseur.add_argument(
        "--session",
        type=str,
        default=None,
        help="Identifiant de session à annuler (utilisé avec --rollback)",
    )
    return parseur.parse_args()


def determiner_mode(arguments):
    if arguments.execute:
        return "execute"
    if arguments.rollback:
        return "rollback"
    return "dry-run"


def main():
    arguments = analyser_arguments()
    mode = determiner_mode(arguments)

    configuration = charger_configuration()
    racine_destination = verifier_destination(configuration)
    chemin_session, horodatage = initialiser_journal_session(configuration, mode)

    print(f"Skrivagner — session {horodatage}")
    print(f"  Mode               : {mode}")
    print(f"  Destination        : {racine_destination}")
    print(f"  Journal de session : {chemin_session}")
    print()

    if mode == "rollback":
        print("Phase 5 (rollback) non encore implémentée.")
        print("Le rollback sera disponible une fois la Phase 5 livrée.")
        return 0

    print("Phases 2 à 7 (scan, OCR, classification, classement, journal)")
    print("non encore implémentées — squelette Phase 1.")
    print()
    print("Le script s'est lancé correctement, la configuration est valide,")
    print("le répertoire de destination est accessible en écriture.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
