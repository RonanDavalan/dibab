"""Cascade tri rapide puis classification fine, étape par étape.

Un seul modèle est chargé à la fois : toutes les requêtes d'une étape se suivent, la dernière
décharge le modèle (`keep_alive` à 0) avant l'étape suivante.
"""

from dataclasses import dataclass

from modules import appel_ollama, classification, domaines


@dataclass(frozen=True)
class Resultat:
    chemin: object
    tri: object  # classification.Tri, ou None sans texte
    classification: object  # classification.Classification, ou None
    verdict: domaines.Verdict


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


def executer(documents, configuration, modeles, generer=appel_ollama.generer):
    """Rend un `Resultat` par document `(chemin, texte)` ; un texte vide (extraction en échec) vaut incertain."""
    parametres = configuration["classification"]
    keep_alive = parametres["keep_alive_entre_documents"]
    avec_texte = [(chemin, texte) for chemin, texte in documents if texte.strip()]

    tris = dict(zip(
        [chemin for chemin, _ in avec_texte],
        _etape(avec_texte, lambda doc, ka: classification.tri_rapide(
            doc[1], parametres, configuration["ollama"], modeles["tri_rapide"], ka, generer), keep_alive)))

    a_classer = [(chemin, texte) for chemin, texte in avec_texte if tris[chemin].verdict != classification.NON_ADMINISTRATIF]
    fines = dict(zip(
        [chemin for chemin, _ in a_classer],
        _etape(a_classer, lambda doc, ka: classification.classifier(
            doc[1], configuration, parametres, modeles["classification"], ka, generer), keep_alive)))

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
            verdict = fine.verdict
        resultats.append(Resultat(chemin, tri, fine, verdict))
    return resultats
