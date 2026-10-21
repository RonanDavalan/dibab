"""Cascade tri rapide puis classification fine, étape par étape.

Un seul modèle est chargé à la fois : toutes les requêtes d'une étape se suivent, la dernière
décharge le modèle (`keep_alive` à 0) avant l'étape suivante.
"""

import sys
from dataclasses import dataclass, replace

from modules import appel_ollama, classification, domaines


@dataclass(frozen=True)
class Resultat:
    chemin: object
    tri: object  # classification.Tri, ou None sans texte
    classification: object  # classification.Classification, ou None
    verdict: domaines.Verdict
    confiance: float = None  # part des modèles de classification d'accord avec le domaine retenu
    categorie_unanime: bool = False  # tous les modèles de classification rendent la même catégorie valide


def _verdict_incertain(signaux=()):
    # Une catégorie vide écarte la règle des pièces communes : un document non confirmé n'entre pas dans Classement/.
    return domaines.Verdict(administratif=True, domaine=domaines.INCERTAIN,
                            categorie=classification.CATEGORIE_INCONNUE, signaux=tuple(signaux))


def _etape(elements, appliquer, keep_alive):
    """Applique `appliquer(element, keep_alive)` en suivant ; le dernier élément décharge le modèle."""
    resultats = []
    for rang, element in enumerate(elements):
        derniere = rang == len(elements) - 1
        resultats.append(appliquer(element, 0 if derniere else keep_alive))
    return resultats


def _signaler(message):
    # La classification dure plusieurs dizaines de minutes : sans ligne d'avancement, la sortie paraît figée.
    print(message, file=sys.stderr, flush=True)


def _choisir_classification(fines, seuil):
    """Rend (classification retenue, confiance) d'après l'accord des modèles de classification.

    Un domaine sous le seuil, une égalité ou une sortie invalide valent incertain : le signal reste
    visible pour orienter l'`À_VÉRIFIER/`, le document n'entre jamais dans `Classement/`.
    """
    domaine, confiance = domaines.consensus([f.verdict.domaine if f.valide else domaines.INCERTAIN for f in fines])
    if domaine in domaines.DOMAINES and domaine != domaines.INCERTAIN and confiance >= seuil:
        return next(f for f in fines if f.valide and f.verdict.domaine == domaine), confiance
    premier = fines[0]
    return replace(premier, verdict=replace(premier.verdict, domaine=domaines.INCERTAIN)), confiance


def executer(documents, configuration, modeles, generer=appel_ollama.generer):
    """Rend un `Resultat` par document `(chemin, texte)` ; un texte vide (extraction en échec) vaut incertain.

    `modeles["classification"]` est un nom ou une liste de noms : chaque modèle classe tous les
    documents à son tour, puis le consensus décide au `seuil_confiance` de la configuration.
    """
    parametres = configuration["classification"]
    keep_alive = parametres["keep_alive_entre_documents"]
    avec_texte = [(chemin, texte) for chemin, texte in documents if texte.strip()]

    tris = dict(zip(
        [chemin for chemin, _ in avec_texte],
        _etape(avec_texte, lambda doc, ka: classification.tri_rapide(
            doc[1], parametres, configuration["ollama"], modeles["tri_rapide"], ka, generer), keep_alive)))

    a_classer = [(chemin, texte) for chemin, texte in avec_texte if tris[chemin].verdict != classification.NON_ADMINISTRATIF]
    classeurs = [modeles["classification"]] if isinstance(modeles["classification"], str) else list(modeles["classification"])
    seuil = configuration["ollama"].get("seuil_confiance", 0)
    par_modele = []
    for rang, modele in enumerate(classeurs, start=1):
        accords = {}
        for position, (chemin, texte) in enumerate(a_classer, start=1):
            _signaler(f"modèle {rang}/{len(classeurs)}, document {position}/{len(a_classer)}")
            derniere = position == len(a_classer)
            accords[chemin] = classification.classifier(texte, configuration, parametres, modele, 0 if derniere else keep_alive, generer)
        par_modele.append(accords)
    fines, confiances, unanimes = {}, {}, {}
    for chemin, _ in a_classer:
        accords = [accord[chemin] for accord in par_modele]
        fines[chemin], confiances[chemin] = _choisir_classification(accords, seuil)
        categories = {accord.verdict.categorie if accord.valide else None for accord in accords}
        unanimes[chemin] = len(categories) == 1 and None not in categories

    resultats = []
    for chemin, _ in documents:
        tri, fine = tris.get(chemin), fines.get(chemin)
        if tri is None:
            verdict = _verdict_incertain()
        elif tri.verdict == classification.NON_ADMINISTRATIF:
            verdict = domaines.Verdict(administratif=False, domaine=domaines.INCERTAIN,
                                       categorie=classification.CATEGORIE_INCONNUE)
        elif tri.verdict == classification.INCERTAIN:
            verdict = _verdict_incertain(fine.verdict.signaux)
        else:
            verdict = replace(fine.verdict, categorie_unanime=unanimes[chemin])
        resultats.append(Resultat(chemin, tri, fine, verdict, confiances.get(chemin), unanimes.get(chemin, False)))
    return resultats
