"""Inventaire de l'existant des coffres : lecture seule, plan de migration écrit dans chaque coffre.

L'inventaire ne déplace, ne renomme et ne supprime rien. Le plan de chaque coffre ne nomme que ses
propres fichiers ; de l'autre coffre il ne retient que l'information « cette empreinte s'y trouve
aussi », pour que le plan d'un coffre ne contienne jamais le chemin d'un fichier de l'autre.
"""

import hashlib
import json
import os
from datetime import datetime
from pathlib import Path

from modules import domaines
from modules.deplacement import creer_dossiers_prives
from modules.pieces_communes import empreinte_sha256
from modules.messages import traduire

SCHEMA_VERSION = 1
CONSERVER = "conserver"
A_CLASSER = "a_classer"


def empreinte_arbre(racine, ignorer=()):
    """Empreinte d'un arbre (chemins, tailles, dates) : prouve qu'une lecture n'a rien changé."""
    ignorer = {Path(chemin) for chemin in ignorer}
    condense = hashlib.sha256()
    for dossier, sous_dossiers, noms in os.walk(racine):
        sous_dossiers.sort()
        for nom in sorted(noms):
            chemin = Path(dossier) / nom
            if chemin in ignorer:
                continue
            info = chemin.stat()
            condense.update(f"{chemin.relative_to(racine)}|{info.st_size}|{info.st_mtime_ns}\n".encode("utf-8"))
    return condense.hexdigest()


def _dossiers_ignores(domaine, configuration):
    destination = configuration["destinations"][domaine]
    return set(configuration["inventaire"]["exclusions"]) | {destination["sous_repertoire_a_verifier"],
                                                              configuration["destination"]["repertoire_doublon"]}


def lister(domaine, configuration):
    """Rend les documents à inventorier d'un coffre : (chemin relatif, taille, zone classée ?)."""
    destination = configuration["destinations"][domaine]
    racine = Path(destination["racine"])
    prefixe_vide_poches = configuration["destination"]["vide_poches_prefixe"]
    extensions = {extension.lower() for extension in configuration["extensions_cibles"]}
    ignores = _dossiers_ignores(domaine, configuration)
    documents = []
    for dossier, sous_dossiers, noms in os.walk(racine):
        sous_dossiers[:] = sorted(nom for nom in sous_dossiers
                                  if not nom.startswith(".") and nom not in ignores and not nom.startswith(prefixe_vide_poches))
        for nom in sorted(noms):
            chemin = Path(dossier) / nom
            if nom.startswith(".") or chemin.suffix.lower() not in extensions:
                continue
            relatif = chemin.relative_to(racine)
            classe = relatif.parts[0] == destination["sous_repertoire_classement"]
            documents.append((relatif, chemin.stat().st_size, classe))
    return documents


def compter_a_verifier(racine, sous_repertoire, extensions):
    """Compte les documents du dossier À_VÉRIFIER, que l'inventaire ne liste pas : ils attendent un verdict, pas une migration."""
    dossier = Path(racine) / sous_repertoire
    if not dossier.is_dir():
        return 0
    return sum(1 for chemin in dossier.rglob("*")
               if chemin.is_file() and not chemin.name.startswith(".") and chemin.suffix.lower() in extensions)


def _empreintes(documents_par_coffre, configuration):
    """Hache les seuls fichiers dont la taille se retrouve ailleurs : sans autre fichier de même taille, pas de doublon possible."""
    tailles = {}
    for domaine, documents in documents_par_coffre.items():
        for relatif, taille, _ in documents:
            tailles.setdefault(taille, []).append((domaine, relatif))
    empreintes = {}
    for taille, membres in tailles.items():
        if len(membres) > 1:
            for domaine, relatif in membres:
                racine = Path(configuration["destinations"][domaine]["racine"])
                empreintes[(domaine, relatif)] = empreinte_sha256(racine / relatif)
    return empreintes


def construire_plans(configuration, maintenant=None):
    """Rend {domaine: plan} sans rien écrire : un plan par coffre, avec ses actions proposées."""
    maintenant = maintenant or datetime.now()
    documents_par_coffre = {domaine: lister(domaine, configuration) for domaine in domaines.COFFRES}
    empreintes = _empreintes(documents_par_coffre, configuration)
    plans = {}
    for domaine, documents in documents_par_coffre.items():
        autre = {empreinte for (cle, _), empreinte in empreintes.items() if cle != domaine}
        premiers, actions, dossiers = {}, [], {}
        for relatif, taille, classe in documents:
            empreinte = empreintes.get((domaine, relatif))
            action = {"chemin": str(relatif), "taille_octets": taille,
                      "action": CONSERVER if classe else A_CLASSER, "empreinte": empreinte,
                      "doublon_de": None, "present_dans_autre_coffre": empreinte in autre}
            if empreinte in premiers:
                action["doublon_de"] = premiers[empreinte]
            elif empreinte:
                premiers[empreinte] = str(relatif)
            if action["doublon_de"]:
                proposition = traduire("inventaire_proposition_doublon", doublon_de=action["doublon_de"])
            elif classe:
                proposition = traduire("inventaire_proposition_conserver")
            else:
                proposition = traduire("inventaire_proposition_a_classer")
            action["proposition"] = proposition.en()
            actions.append(action)
            dossier = dossiers.setdefault(relatif.parts[0] if len(relatif.parts) > 1 else ".", {"fichiers": 0, "octets": 0})
            dossier["fichiers"] += 1
            dossier["octets"] += taille
        plans[domaine] = {
            "schema_version": SCHEMA_VERSION,
            "horodatage": maintenant.strftime("%Y-%m-%dT%H:%M:%S"),
            "coffre": domaine,
            "resume": {
                "documents": len(actions),
                CONSERVER: sum(a["action"] == CONSERVER for a in actions),
                A_CLASSER: sum(a["action"] == A_CLASSER for a in actions),
                "doublons_internes": sum(a["doublon_de"] is not None for a in actions),
                "presents_dans_autre_coffre": sum(a["present_dans_autre_coffre"] for a in actions),
                "a_verifier_non_listes": compter_a_verifier(
                    configuration["destinations"][domaine]["racine"],
                    configuration["destinations"][domaine]["sous_repertoire_a_verifier"],
                    {extension.lower() for extension in configuration["extensions_cibles"]}),
            },
            "dossiers": [{"dossier": nom, **valeurs} for nom, valeurs in sorted(dossiers.items())],
            "actions": actions,
        }
    return plans


def ecrire_plans(plans, configuration):
    """Écrit le plan de chaque coffre dans ce coffre ; rend {domaine: chemin du fichier}."""
    ecrits = {}
    for domaine, plan in plans.items():
        racine = Path(configuration["destinations"][domaine]["racine"])
        dossier = racine / configuration["destination"]["sous_repertoire_logs"]
        base = f"inventaire_{plan['horodatage'].replace(':', '-')}"
        creer_dossiers_prives(dossier)
        ecrits[domaine] = _ecrire_sans_ecraser(dossier, base, plan)
    return ecrits


def _ecrire_sans_ecraser(dossier, base, plan):
    """Écrit le plan sous `base.json`, ou `base_2.json`, `base_3.json`… si le nom est déjà pris ; `O_EXCL` garde la course sûre."""
    numero = 1
    while True:
        chemin = dossier / (f"{base}.json" if numero == 1 else f"{base}_{numero}.json")
        try:
            descripteur = os.open(chemin, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError:
            numero += 1
            continue
        with os.fdopen(descripteur, "w", encoding="utf-8") as f:
            json.dump(plan, f, ensure_ascii=False, indent=1)
        return chemin
