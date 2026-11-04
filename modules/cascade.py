"""Cascade tri rapide puis classification fine, étape par étape.

Un seul modèle est chargé à la fois : toutes les requêtes d'une étape se suivent, la dernière
décharge le modèle (`keep_alive` à 0) avant l'étape suivante. Le tri passe par un modèle decision
puis par le modèle d'objet quand `modeles["tri_decision"]` est un choix utilisable, sinon par la génération.
"""

import sys
from dataclasses import dataclass, replace

from modules import appel_ollama, classification, domaines, tri_decision
from modules.messages import traduire


MOTIF_AUCUN_TEXTE = "aucun_texte"
MOTIF_TRI_INCERTAIN = "tri_incertain"
MOTIF_PIECE_COMMUNE = "piece_commune_sans_categorie_unanime"
MOTIF_DOMAINES_DIFFERENTS = "domaines_differents"
MOTIF_DESACCORD = "desaccord_ou_sous_le_seuil"
MOTIF_SANS_SIGNAL = "sans_destinataire_ni_emetteur_connu"
MOTIFS = (MOTIF_AUCUN_TEXTE, MOTIF_TRI_INCERTAIN, MOTIF_PIECE_COMMUNE, MOTIF_DOMAINES_DIFFERENTS, MOTIF_DESACCORD,
          MOTIF_SANS_SIGNAL)


@dataclass(frozen=True)
class Resultat:
    chemin: object
    tri: object  # classification.Tri, ou None sans texte
    classification: object  # classification.Classification, ou None
    verdict: domaines.Verdict
    confiance: float = None  # part des modèles de classification d'accord avec le domaine retenu
    categorie_unanime: bool = False  # tous les modèles de classification rendent la même catégorie valide
    classifications: tuple = ()  # une classification.Classification par modèle, dans l'ordre du rôle
    accord: tuple = None  # (modèles qui rendent le domaine affiché, modèles interrogés)


def _domaine_rendu(fine):
    # Une sortie invalide compte comme `incertain`, comme dans le consensus.
    return fine.verdict.domaine if fine.valide else domaines.INCERTAIN


def motif_a_verifier(resultat, pieces_communes=()):
    """Rend, dans la liste fermée `MOTIFS`, la raison pour laquelle un document va en `À_VÉRIFIER/`.

    Le motif ne cite rien du document : la liste est fermée pour que l'écran et le journal ne puissent
    porter ni destinataire ni extrait.
    """
    verdict = resultat.verdict
    if resultat.tri is None:
        return MOTIF_AUCUN_TEXTE
    if resultat.tri.verdict == classification.INCERTAIN:
        return MOTIF_TRI_INCERTAIN
    if verdict.categorie in pieces_communes and not verdict.categorie_unanime:
        return MOTIF_PIECE_COMMUNE
    rendus = [_domaine_rendu(fine) for fine in resultat.classifications]
    if not rendus or len(set(rendus)) > 1 or not all(fine.valide for fine in resultat.classifications) \
            or rendus[0] != verdict.domaine:
        return MOTIF_DESACCORD
    if verdict.domaine == domaines.MIXTE:
        return MOTIF_DOMAINES_DIFFERENTS
    return MOTIF_SANS_SIGNAL


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


def _trier(avec_texte, configuration, modeles, generer, decider):
    """Rend {chemin: Tri} : par décision puis objet si un choix est utilisable, la génération pour le reste, puis le garde-fou.

    Un 404 de `/v1/systemone` fait trier par la génération toutes les pièces que le modèle decision n'a pas triées.
    """
    parametres = configuration["classification"]
    keep_alive = parametres["keep_alive_entre_documents"]
    choix, repli = modeles.get("tri_decision"), modeles.get("repli_tri")
    tris = {}
    if choix is not None:
        for rang, (chemin, texte) in enumerate(avec_texte):
            derniere = rang == len(avec_texte) - 1
            try:
                tris[chemin] = tri_decision.trier(texte, parametres, configuration["ollama"], choix, 0 if derniere else keep_alive, decider)
            except appel_ollama.PointAccesAbsent:
                repli = tri_decision.MOTIF_OLLAMA_SANS_SYSTEMONE
                _signaler(traduire("tri_decision_repli_en_cours", modele=choix.modele))
                break
        decides = [(chemin, texte) for chemin, texte in avec_texte if chemin in tris]
        objets = _etape(decides, lambda doc, ka: classification.rendre_objet(
            doc[1], parametres, configuration["ollama"], choix.objet, ka, generer), keep_alive)
        for (chemin, _), objet in zip(decides, objets):
            tris[chemin] = replace(tris[chemin], objet=objet, modele_objet=choix.objet)
    restants = [(chemin, texte) for chemin, texte in avec_texte if chemin not in tris]
    generes = _etape(restants, lambda doc, ka: classification.tri_rapide(
        doc[1], parametres, configuration["ollama"], modeles["tri_rapide"], ka, generer), keep_alive)
    for (chemin, _), tri in zip(restants, generes):
        tris[chemin] = replace(tri, repli=repli)
    # Le garde-fou lit le texte entier, pas seulement le début que le modèle a lu.
    return {chemin: classification.garder_les_pieces_administratives(tris[chemin], texte, configuration) for chemin, texte in avec_texte}


def executer(documents, configuration, modeles, generer=appel_ollama.generer, decider=appel_ollama.decider):
    """Rend un `Resultat` par document `(chemin, texte)` ; un texte vide (extraction en échec) vaut incertain.

    `modeles["classification"]` est un nom ou une liste de noms : chaque modèle classe tous les
    documents à son tour, puis le consensus décide au `seuil_confiance` de la configuration.
    `modeles["tri_decision"]` (facultatif) est un `tri_decision.Choix`, `modeles["repli_tri"]` le motif d'un repli.
    """
    parametres = configuration["classification"]
    keep_alive = parametres["keep_alive_entre_documents"]
    avec_texte = [(chemin, texte) for chemin, texte in documents if texte.strip()]

    tris = _trier(avec_texte, configuration, modeles, generer, decider)

    a_classer = [(chemin, texte) for chemin, texte in avec_texte if tris[chemin].verdict != classification.NON_ADMINISTRATIF]
    classeurs = [modeles["classification"]] if isinstance(modeles["classification"], str) else list(modeles["classification"])
    seuil = configuration["ollama"].get("seuil_confiance", 0)
    par_modele = []
    for rang, modele in enumerate(classeurs, start=1):
        accords = {}
        for position, (chemin, texte) in enumerate(a_classer, start=1):
            _signaler(traduire("cascade_avancement", rang=rang, total=len(classeurs), position=position, nombre=len(a_classer)))
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
        if tri is not None:
            verdict = replace(verdict, objet=tri.objet)
        accords = tuple(accord[chemin] for accord in par_modele) if chemin in fines else ()
        # L'accord porte sur le domaine affiché : une confiance de 1 sur `incertain` se lisait comme une certitude.
        accord = (sum(_domaine_rendu(f) == verdict.domaine for f in accords), len(accords)) if accords else None
        resultats.append(Resultat(chemin, tri, fine, verdict, confiances.get(chemin), unanimes.get(chemin, False),
                                  accords, accord))
    return resultats
