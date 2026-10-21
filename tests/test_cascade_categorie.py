"""Accord des modèles sur la catégorie, routage des pièces communes et progression de la cascade."""

import json
from pathlib import Path

from modules import cascade, domaines
from modules.domaines import A_VERIFIER, CLASSEMENT, PERSONNEL, PROFESSIONNEL, Cible, router
from tests.textes_factices import CATEGORIES, EMETTEURS_CONNUS, PERSONNES, TEXTES

PIECES_COMMUNES = ["Identité", "Domicile", "RIB"]
TEXTE_PERSONNEL = TEXTES[0]["texte"]


def configuration():
    return {
        "ollama": {"url": "http://x", "timeout_secondes": 5, "seuil_confiance": 0.4},
        "classification": {"temperature": 0, "num_ctx": 8192, "caracteres_max_prompt": 12000, "keep_alive_entre_documents": "2m",
                           "longueur_max_champ": 80, "longueur_max_citation": 120, "marqueurs_mentions": ["TVA"]},
        "categories": CATEGORIES + ["Emploi"], "personnes": PERSONNES, "emetteurs_connus": EMETTEURS_CONNUS,
    }


def generer_par_modele(categories):
    """`categories` : {modèle: catégorie rendue} ; le domaine reste celui du texte, personnel."""
    def generer(url, modele, consigne, images, delai, keep_alive, format=None, options=None):
        if "verdict" in format["properties"]:
            return json.dumps({"verdict": "administratif"})
        return json.dumps(dict(TEXTES[0]["reponse"], categorie=categories[modele]))
    return generer


def executer(categories, documents=None):
    documents = documents or [(Path("doc.pdf"), TEXTE_PERSONNEL)]
    modeles = {"tri_rapide": "tri", "classification": list(categories)}
    return cascade.executer(documents, configuration(), modeles, generer_par_modele(categories))


def test_texte_d_emploi_reste_hors_piece_commune():
    resultat = executer({"m1": "Emploi", "m2": "Emploi"})[0]
    assert resultat.categorie_unanime is True
    assert router(resultat.verdict, PIECES_COMMUNES) == [Cible(PERSONNEL, CLASSEMENT)]


def test_categorie_non_unanime_va_en_a_verifier():
    resultat = executer({"m1": "Identité", "m2": "Emploi"})[0]
    assert resultat.categorie_unanime is False
    assert router(resultat.verdict, PIECES_COMMUNES) == [Cible(PERSONNEL, A_VERIFIER)]


def test_piece_commune_unanime_copiee_dans_les_deux_coffres():
    resultat = executer({"m1": "Identité", "m2": "Identité"})[0]
    assert resultat.categorie_unanime is True
    assert router(resultat.verdict, PIECES_COMMUNES) == [Cible(PERSONNEL, CLASSEMENT), Cible(PROFESSIONNEL, CLASSEMENT)]


def test_une_sortie_invalide_empeche_l_accord_sur_la_categorie():
    def generer(url, modele, consigne, images, delai, keep_alive, format=None, options=None):
        if "verdict" in format["properties"]:
            return json.dumps({"verdict": "administratif"})
        if modele == "m2":
            return "pas du json"
        return json.dumps(dict(TEXTES[0]["reponse"], categorie="Identité"))

    resultat = cascade.executer([(Path("doc.pdf"), TEXTE_PERSONNEL)], configuration(),
                                {"tri_rapide": "tri", "classification": ["m1", "m2"]}, generer)[0]
    assert resultat.categorie_unanime is False
    assert router(resultat.verdict, PIECES_COMMUNES) == [Cible(PERSONNEL, A_VERIFIER)]


def test_progression_une_ligne_par_document_et_par_modele(capsys):
    documents = [(Path(f"doc{rang}.pdf"), TEXTE_PERSONNEL) for rang in range(3)]
    executer({"m1": "Emploi", "m2": "Emploi"}, documents)
    captures = capsys.readouterr()
    assert captures.out == ""
    assert captures.err.splitlines() == [
        f"modèle {modele}/2, document {document}/3" for modele in (1, 2) for document in (1, 2, 3)
    ]

