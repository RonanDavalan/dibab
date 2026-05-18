# modules/suivi.py — Lecture et écriture de dernier_scan.json
#
# Le fichier dernier_scan.json contient, par identifiant de source, la date
# du dernier scan exécuté avec succès. Il sert à filtrer les fichiers récents
# lors du prochain scan (depuis dernier_scan - securite_jours).
#
# Politique :
# - Si le fichier n'existe pas, première exécution : retourner None pour
#   chaque source, le scanner appliquera premier_scan_jours.
# - Le fichier n'est écrit que par la fonction sauvegarder(), appelée en
#   fin de session --execute uniquement (jamais en dry-run).

import json
from datetime import datetime
from pathlib import Path


FORMAT_DATE = "%Y-%m-%dT%H:%M:%S"


def charger(chemin_fichier):
    """Charge dernier_scan.json et retourne un dict {id_source: datetime}.

    Si le fichier n'existe pas, retourne un dict vide.
    Une entrée invalide (format incorrect) est ignorée silencieusement.
    """
    chemin = Path(chemin_fichier)
    if not chemin.exists():
        return {}

    try:
        with open(chemin, "r", encoding="utf-8") as f:
            donnees_brutes = json.load(f)
    except json.JSONDecodeError:
        return {}

    resultat = {}
    for id_source, valeur in donnees_brutes.items():
        if not isinstance(valeur, str):
            continue
        try:
            resultat[id_source] = datetime.strptime(valeur, FORMAT_DATE)
        except ValueError:
            continue
    return resultat


def derniere_date(suivi, id_source):
    """Retourne la date du dernier scan pour cette source, ou None."""
    return suivi.get(id_source)


def sauvegarder(chemin_fichier, suivi):
    """Écrit le suivi dans dernier_scan.json.

    Le suivi est un dict {id_source: datetime}. L'écriture est atomique :
    on écrit dans un fichier temporaire puis on rename.
    """
    chemin = Path(chemin_fichier)
    chemin.parent.mkdir(parents=True, exist_ok=True)

    donnees_serialisables = {
        id_source: date.strftime(FORMAT_DATE)
        for id_source, date in suivi.items()
    }

    chemin_temp = chemin.with_suffix(chemin.suffix + ".tmp")
    with open(chemin_temp, "w", encoding="utf-8") as f:
        json.dump(donnees_serialisables, f, ensure_ascii=False, indent=2, sort_keys=True)
    chemin_temp.replace(chemin)
