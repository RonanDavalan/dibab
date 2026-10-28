"""Mesure du domaine sur des documents réels, sans rien écrire qui les identifie.

Tire des documents au sort dans chaque coffre, les passe dans l'extraction puis dans la cascade en
lecture seule, et ne rend que des agrégats : effectifs, taux, durées moyennes, noms de modèles.
Aucun chemin, nom de fichier ni texte n'entre dans la sortie.
"""

import argparse
import hashlib
import itertools
import json
import math
import os
import random
import sys
from collections import Counter
from pathlib import Path

from modules import appel_ollama, cascade, chemins, classification, coffres, domaines, extraction, modeles

NON_ADMINISTRATIF = "non_administratif"
ECHEC_EXTRACTION = "echec_extraction"
COLONNES = (*domaines.DOMAINES, NON_ADMINISTRATIF, ECHEC_EXTRACTION)
CLES_MESURE = ("graine", "documents_par_coffre", "exclusions", "taux_erreur_max")
CHEMIN_CONFIG = Path(__file__).resolve().parent.parent / "config.json"
Z_95 = 1.96


def cles_absentes(configuration):
    mesure = configuration.get("mesure", {})
    absentes = [f"mesure.{cle}" for cle in CLES_MESURE if cle not in mesure]
    absentes += [f"ollama.roles.{role}" for role in ("ocr", "tri_rapide", "classification")
                 if role not in configuration.get("ollama", {}).get("roles", {})]
    return absentes + [cle for cle in ("extraction", "classification", "extensions_cibles", "destinations")
                       if cle not in configuration]


def dossiers_exclus(configuration):
    """Noms de dossiers (casse ignorée) qu'on ne parcourt pas."""
    noms = {nom.casefold() for nom in configuration["mesure"]["exclusions"]}
    noms |= {destination["sous_repertoire_a_verifier"].casefold()
             for destination in configuration["destinations"].values()}
    sous_logs = configuration.get("destination", {}).get("sous_repertoire_logs")
    return noms | ({sous_logs.casefold()} if sous_logs else set())


def lister_candidats(racine, configuration):
    """Rend, triés, les PDF et images de la zone classée d'un coffre ; vide-poches et exclusions écartés."""
    extensions = {extension.lower() for extension in configuration["extensions_cibles"]}
    prefixe = configuration.get("destination", {}).get("vide_poches_prefixe", "vide-poches-")
    exclus = dossiers_exclus(configuration)
    candidats = []
    for dossier, sous_dossiers, fichiers in os.walk(racine, followlinks=False):
        sous_dossiers[:] = [nom for nom in sous_dossiers
                            if nom.casefold() not in exclus and not nom.startswith((prefixe, "."))]
        for nom in fichiers:
            chemin = Path(dossier) / nom
            if not nom.startswith(".") and chemin.suffix.lower() in extensions and not chemin.is_symlink():
                candidats.append(chemin)
    return sorted(candidats)


def _empreinte(chemin):
    condensat = hashlib.sha256()
    try:
        with open(chemin, "rb") as fichier:
            for bloc in iter(lambda: fichier.read(1 << 20), b""):
                condensat.update(bloc)
    except OSError:
        return None
    return condensat.hexdigest()


def _taille(chemin):
    try:
        return chemin.stat().st_size
    except OSError:
        return None


def retirer_pieces_communes(candidats_par_coffre):
    """Retire les fichiers d'empreinte identique dans deux coffres : les deux étiquettes y sont vraies.

    Seuls les fichiers dont la taille existe dans un autre coffre sont lus pour le calcul.
    """
    tailles = {coffre: {_taille(chemin) for chemin in liste} for coffre, liste in candidats_par_coffre.items()}
    empreintes = {}
    for coffre, liste in candidats_par_coffre.items():
        ailleurs = set().union(*(t for autre, t in tailles.items() if autre != coffre))
        empreintes[coffre] = {chemin: _empreinte(chemin) for chemin in liste if _taille(chemin) in ailleurs}
    communes = set()
    for coffre, valeurs in empreintes.items():
        autres = set().union(*({e for e in v.values() if e} for autre, v in empreintes.items() if autre != coffre))
        communes |= {e for e in valeurs.values() if e in autres}
    return {coffre: [chemin for chemin in liste if empreintes[coffre].get(chemin) not in communes]
            for coffre, liste in candidats_par_coffre.items()}


def tirer(candidats, nombre, graine):
    """Tirage reproductible : même graine et mêmes candidats, mêmes documents."""
    return sorted(random.Random(graine).sample(sorted(candidats), min(nombre, len(candidats))))


consensus = domaines.consensus


def borne_haute_wilson(erreurs, total):
    if total == 0:
        return None
    p = erreurs / total
    z2 = Z_95 ** 2
    centre = p + z2 / (2 * total)
    ecart = Z_95 * math.sqrt(p * (1 - p) / total + z2 / (4 * total ** 2))
    return min(1.0, (centre + ecart) / (1 + z2 / total))


def courbe_seuil(observations, plafond):
    """Rend (courbe, seuil) pour des observations (étiquette, colonne consensuelle, confiance).

    Un verdict est retenu s'il désigne un coffre et que sa confiance atteint le seuil ; le seuil
    rendu est la plus petite confiance observée dont le taux d'erreur ne dépasse pas `plafond`.
    """
    courbe, seuil = [], None
    for valeur in sorted({confiance for _, _, confiance in observations}):
        retenus = [(etiquette, colonne) for etiquette, colonne, confiance in observations
                   if colonne in domaines.COFFRES and confiance >= valeur]
        erreurs = sum(1 for etiquette, colonne in retenus if colonne != etiquette)
        taux = erreurs / len(retenus) if retenus else None
        courbe.append({"seuil": round(valeur, 4), "retenus": len(retenus), "erreurs": erreurs,
                       "taux_erreur": None if taux is None else round(taux, 4),
                       "borne_haute_95": None if not retenus else round(borne_haute_wilson(erreurs, len(retenus)), 4)})
        if seuil is None and retenus and taux <= plafond:
            seuil = round(valeur, 4)
    return courbe, seuil


def _moyenne(valeurs):
    return round(sum(valeurs) / len(valeurs), 3) if valeurs else None


def _taux(effectif, total):
    return round(effectif / total, 4) if total else None


def matrice_confusion(paires):
    """Rend {étiquette: {colonne: effectif}} pour des paires (étiquette, colonne)."""
    matrice = {coffre: {colonne: 0 for colonne in COLONNES} for coffre in domaines.COFFRES}
    for etiquette, colonne in paires:
        matrice[etiquette][colonne] += 1
    return matrice


def _resume_domaines(paires):
    """Taux d'une série de (étiquette, colonne) : incertain, mixte, et erreur parmi les verdicts de coffre."""
    total = len(paires)
    colonnes = Counter(colonne for _, colonne in paires)
    decisions = [(e, c) for e, c in paires if c in domaines.COFFRES]
    erreurs = sum(1 for e, c in decisions if e != c)
    return {"matrice": matrice_confusion(paires),
            "taux_incertain": _taux(colonnes[domaines.INCERTAIN], total),
            "taux_mixte": _taux(colonnes[domaines.MIXTE], total),
            "taux_non_administratif": _taux(colonnes[NON_ADMINISTRATIF], total),
            "taux_echec_extraction": _taux(colonnes[ECHEC_EXTRACTION], total),
            "decisions": len(decisions), "erreurs": erreurs,
            "taux_erreur_domaine": _taux(erreurs, len(decisions))}


def _categorie_majoritaire(categories):
    """Catégorie rendue par plus de la moitié des modèles, ou None ; une sortie invalide (None) ne vote pas."""
    comptes = Counter(c for c in categories if c is not None)
    if not comptes:
        return None
    categorie, effectif = comptes.most_common(1)[0]
    return categorie if effectif * 2 > len(categories) else None


def accord_categorie(par_modele):
    """Rend l'accord des modèles sur la catégorie, `par_modele` : {modèle: [catégorie ou None par document]}.

    Seuls comptent les documents classés par au moins un modèle. Aucune catégorie ne sort de ce calcul
    sous forme de valeur : ni effectif par catégorie, ni nom.
    """
    modeles_mesures = list(par_modele)
    lignes = [tuple(par_modele[m][rang] for m in modeles_mesures) for rang in range(len(par_modele[modeles_mesures[0]]))]
    lignes = [ligne for ligne in lignes if any(c is not None for c in ligne)]
    majoritaires = [_categorie_majoritaire(ligne) for ligne in lignes]
    unanimes = sum(1 for ligne in lignes if None not in ligne and len(set(ligne)) == 1)
    avec_majorite = [(ligne, categorie) for ligne, categorie in zip(lignes, majoritaires) if categorie is not None]
    return {
        "documents": len(lignes),
        "taux_unanimite": _taux(unanimes, len(lignes)),
        "taux_majorite": _taux(len(avec_majorite), len(lignes)),
        "accord_avec_majorite": {
            modele: _taux(sum(1 for ligne, categorie in avec_majorite if ligne[rang] == categorie), len(avec_majorite))
            for rang, modele in enumerate(modeles_mesures)},
    }


def sous_ensembles(colonnes, categories, durees_classification, duree_base, etiquettes, seuil):
    """Rend, pour chaque sous-ensemble de modèles de classification, ses verdicts retenus et sa durée.

    `colonnes` et `categories` : {modèle: [valeur par document]} ; un verdict de coffre est retenu si
    sa confiance (part du sous-ensemble d'accord) atteint `seuil`.
    """
    noms = list(colonnes)
    resultats = []
    for taille in range(1, len(noms) + 1):
        for groupe in itertools.combinations(noms, taille):
            decisions = [consensus([colonnes[m][rang] for m in groupe]) for rang in range(len(etiquettes))]
            retenus = [(etiquette, colonne) for etiquette, (colonne, confiance) in zip(etiquettes, decisions)
                       if colonne in domaines.COFFRES and confiance >= seuil]
            classes = [[categories[m][rang] for m in groupe] for rang in range(len(etiquettes))]
            classes = [ligne for ligne in classes if any(c is not None for c in ligne)]
            unanimes = sum(1 for ligne in classes if None not in ligne and len(set(ligne)) == 1)
            resultats.append({
                "modeles": list(groupe),
                "verdicts_retenus": len(retenus),
                "erreurs_retenues": sum(1 for etiquette, colonne in retenus if colonne != etiquette),
                "taux_unanimite_categorie": _taux(unanimes, len(classes)),
                "duree_moyenne_document_s": _moyenne([duree_base + sum(durees_classification[m] for m in groupe)]),
            })
    return resultats


def sous_ensemble_retenu(candidats, reference):
    """Le plus petit sous-ensemble d'au moins deux modèles qui rend autant de verdicts retenus que `reference`, sans erreur.

    Un seul modèle rend toujours l'unanimité de catégorie : la règle des pièces communes n'aurait plus de garde.
    À taille égale : le plus de verdicts retenus, puis la durée la plus courte.
    """
    admis = [c for c in candidats if len(c["modeles"]) >= 2 and c["erreurs_retenues"] == 0
             and c["verdicts_retenus"] >= reference["verdicts_retenus"]]
    return min(admis, key=lambda c: (len(c["modeles"]), -c["verdicts_retenus"],
                                     c["duree_moyenne_document_s"] or 0), default=None)


def _colonne(resultat, extraite):
    if extraite.methode == "echec":
        return ECHEC_EXTRACTION
    if not resultat.verdict.administratif:
        return NON_ADMINISTRATIF
    return resultat.verdict.domaine


def _suivre(message):
    sys.stderr.write(message + "\n")


def _ordre_classification(resume):
    erreur = resume["taux_erreur_domaine"]
    return (1.0 if erreur is None else erreur, resume["taux_incertain"] or 0, resume["duree_moyenne_document_s"] or 0)


def _ordre_tri(resume):
    return (resume["taux_non_administratif"] or 0, resume["taux_incertain"] or 0, resume["duree_moyenne_s"] or 0)


def mesurer(documents, configuration, candidats, modele_ocr, generer=appel_ollama.generer,
            executer=None, suivre=_suivre):
    """Rend les agrégats de la mesure.

    `documents` : liste de (étiquette, chemin) ; `candidats` : {"tri_rapide": [...], "classification": [...]}.
    Chaque modèle de classification passe la cascade complète avec le premier modèle de tri.
    """
    parametres = configuration["extraction"]
    ollama = configuration["ollama"]
    options = {} if executer is None else {"executer": executer}
    extractions = []
    for rang, (_, chemin) in enumerate(documents, 1):
        extractions.append(extraction.extraire(chemin, parametres, ollama, modele_ocr, generer=generer, **options))
        suivre(f"extraction {rang}/{len(documents)}")
    textes = [(chemin, extraite.texte) for (_, chemin), extraite in zip(documents, extractions)]
    etiquettes = [etiquette for etiquette, _ in documents]

    par_methode = {}
    for extraite in extractions:
        par_methode.setdefault(extraite.methode, []).append(extraite.duree_secondes)
    duree_extraction = [extraite.duree_secondes for extraite in extractions]

    tris = {}
    classifications = {}
    categories = {}
    modele_tri = candidats["tri_rapide"][0]
    for modele in candidats["classification"]:
        suivre(f"cascade, classification : {modele}")
        resultats = cascade.executer(textes, configuration, {"tri_rapide": modele_tri, "classification": modele}, generer)
        colonnes = [_colonne(resultat, extraite) for resultat, extraite in zip(resultats, extractions)]
        durees = [(resultat.tri.duree_secondes if resultat.tri else 0)
                  + (resultat.classification.duree_secondes if resultat.classification else 0) + base
                  for resultat, base in zip(resultats, duree_extraction)]
        resume = _resume_domaines(list(zip(etiquettes, colonnes)))
        resume["duree_moyenne_classification_s"] = _moyenne(
            [r.classification.duree_secondes for r in resultats if r.classification])
        resume["duree_moyenne_document_s"] = _moyenne(durees)
        categories[modele] = [r.classification.verdict.categorie if r.classification and r.classification.valide else None
                              for r in resultats]
        classifications[modele] = resume
        classifications[modele]["_colonnes"] = colonnes
        if modele_tri not in tris:
            tris[modele_tri] = ([r.tri.verdict if r.tri else classification.INCERTAIN for r in resultats],
                                [r.tri.duree_secondes for r in resultats if r.tri])

    for modele in candidats["tri_rapide"][1:]:
        suivre(f"tri : {modele}")
        verdicts, durees = [], []
        for rang, (_, texte) in enumerate(textes):
            if not texte.strip():
                verdicts.append(classification.INCERTAIN)
                continue
            tri = classification.tri_rapide(texte, configuration["classification"], ollama, modele,
                                            0 if rang == len(textes) - 1 else configuration["classification"]["keep_alive_entre_documents"],
                                            generer)
            verdicts.append(tri.verdict)
            durees.append(tri.duree_secondes)
        tris[modele] = (verdicts, durees)

    resume_tri = {}
    for modele, (verdicts, durees) in tris.items():
        comptes = Counter(verdicts)
        resume_tri[modele] = {"documents": len(verdicts),
                              "taux_non_administratif": _taux(comptes[classification.NON_ADMINISTRATIF], len(verdicts)),
                              "taux_incertain": _taux(comptes[classification.INCERTAIN], len(verdicts)),
                              "duree_moyenne_s": _moyenne(durees)}

    votes = [[classifications[modele]["_colonnes"][rang] for modele in classifications] for rang in range(len(documents))]
    consensuels = [consensus(vote) for vote in votes]
    courbe, seuil = courbe_seuil([(etiquette, colonne, confiance)
                                  for etiquette, (colonne, confiance) in zip(etiquettes, consensuels)],
                                 configuration["mesure"]["taux_erreur_max"])
    retenu = next((ligne for ligne in courbe if ligne["seuil"] == seuil), None)
    colonnes_par_modele = {modele: resume.pop("_colonnes") for modele, resume in classifications.items()}
    base = (_moyenne(duree_extraction) or 0) + (_moyenne(tris[modele_tri][1]) or 0)
    candidats_sous_ensembles = sous_ensembles(
        colonnes_par_modele, categories,
        {modele: resume["duree_moyenne_classification_s"] or 0 for modele, resume in classifications.items()},
        base, etiquettes, configuration["ollama"].get("seuil_confiance", 0))
    reference = next(c for c in candidats_sous_ensembles if len(c["modeles"]) == len(classifications))

    return {
        "echantillon": {coffre: etiquettes.count(coffre) for coffre in domaines.COFFRES},
        "graine": configuration["mesure"]["graine"],
        "modeles": {"ocr": modele_ocr, **candidats},
        "extraction": {methode: {"documents": len(valeurs), "duree_moyenne_s": _moyenne(valeurs)}
                       for methode, valeurs in sorted(par_methode.items())},
        "tri_rapide": resume_tri,
        "classification": classifications,
        "accord_categorie": accord_categorie(categories),
        "sous_ensembles": candidats_sous_ensembles,
        "sous_ensemble_retenu": sous_ensemble_retenu(candidats_sous_ensembles, reference),
        "consensus": {**_resume_domaines(list(zip(etiquettes, (colonne for colonne, _ in consensuels)))),
                      "courbe_seuil": courbe, "seuil_confiance": seuil,
                      "plafond_erreur": configuration["mesure"]["taux_erreur_max"],
                      "verdicts_retenus": retenu["retenus"] if retenu else 0,
                      "erreurs_retenues": retenu["erreurs"] if retenu else 0},
        "preferences": {
            "tri_rapide": sorted(resume_tri, key=lambda m: _ordre_tri(resume_tri[m])),
            "classification": sorted(classifications, key=lambda m: _ordre_classification(classifications[m])),
        },
    }


def _installes_parmi(preferences, installes):
    return [p for p in preferences if p in installes or f"{p}:latest" in installes]


def _liste(texte):
    return [element.strip() for element in texte.split(",") if element.strip()] if texte else None


def analyser_arguments(argv=None):
    parseur = argparse.ArgumentParser(description="Mesure du domaine sur les documents réels des coffres (agrégats seuls).")
    parseur.add_argument("--configuration", type=Path, default=CHEMIN_CONFIG, help="config.json à lire")
    parseur.add_argument("--tri", help="modèles de tri à mesurer, séparés par des virgules (défaut : ollama.roles.tri_rapide)")
    parseur.add_argument("--classification",
                         help="modèles de classification à mesurer (défaut : ollama.roles.classification)")
    parseur.add_argument("--a-blanc", action="store_true",
                         help="ne prouve pas les coffres : pour une configuration qui pointe un répertoire factice")
    return parseur.parse_args(argv)


def main(argv=None, generer=appel_ollama.generer, executer=None, sortie=sys.stdout):
    arguments = analyser_arguments(argv)
    try:
        configuration = chemins.developper_chemins(json.loads(arguments.configuration.read_text(encoding="utf-8")))
    except (OSError, ValueError):
        sys.stderr.write("ERREUR : configuration illisible ou invalide.\n")
        return 1
    absentes = cles_absentes(configuration)
    if absentes:
        sys.stderr.write(f"ERREUR : config.json : clés absentes : {', '.join(absentes)}\n        Voir config.exemple.json.\n")
        return 1
    if not arguments.a_blanc:
        defaillants = [etat for etat in coffres.verifier_coffres(configuration["destinations"]) if not etat.monte]
        if defaillants:
            sys.stderr.write(f"ERREUR : coffre non prouvé : {', '.join(etat.domaine for etat in defaillants)}. Rien n'a été lu.\n")
            return 2
    try:
        installes = modeles.lister_modeles_installes(configuration["ollama"]["url"], configuration["ollama"].get("timeout_secondes", 120))
    except modeles.ModeleIndisponible as erreur:
        sys.stderr.write(f"ERREUR : {erreur}\n")
        return 3
    roles = configuration["ollama"]["roles"]
    candidats = {"tri_rapide": _installes_parmi(_liste(arguments.tri) or roles["tri_rapide"], installes),
                 "classification": _installes_parmi(_liste(arguments.classification) or roles["classification"], installes)}
    ocr = _installes_parmi(roles["ocr"], installes)
    manquants = [role for role, liste in (("ocr", ocr), *candidats.items()) if not liste]
    if manquants:
        sys.stderr.write(f"ERREUR : aucun modèle installé pour : {', '.join(manquants)}\n")
        return 3

    mesure = configuration["mesure"]
    candidats_par_coffre = {coffre: lister_candidats(configuration["destinations"][coffre]["racine"], configuration)
                            for coffre in domaines.COFFRES}
    uniques = retirer_pieces_communes(candidats_par_coffre)
    documents = [(coffre, chemin) for coffre in domaines.COFFRES
                 for chemin in tirer(uniques[coffre], mesure["documents_par_coffre"], mesure["graine"])]
    if not documents:
        sys.stderr.write("ERREUR : aucun document à mesurer.\n")
        return 4

    agregats = mesurer(documents, configuration, candidats, ocr[0], generer, executer)
    agregats["population"] = {coffre: len(uniques[coffre]) for coffre in domaines.COFFRES}
    json.dump(agregats, sortie, ensure_ascii=False, indent=2)
    sortie.write("\n")
    return 0
