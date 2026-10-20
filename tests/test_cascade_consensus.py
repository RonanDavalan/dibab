"""Consensus des modèles de classification et seuil de confiance dans la cascade."""

import json
from pathlib import Path

import pytest

from modules import cascade
from tests.textes_factices import CATEGORIES, EMETTEURS_CONNUS, PERSONNES, TEXTES

PERSONNEL, PROFESSIONNEL = TEXTES[0], TEXTES[2]
TEXTE = PERSONNEL["texte"] + "\n" + PROFESSIONNEL["texte"]  # les citations des deux réponses y figurent


def configuration(seuil):
    return {
        "ollama": {"url": "http://x", "timeout_secondes": 5, "seuil_confiance": seuil},
        "classification": {"temperature": 0, "num_ctx": 8192, "caracteres_max_prompt": 12000, "keep_alive_entre_documents": "2m",
                           "longueur_max_champ": 80, "longueur_max_citation": 120, "marqueurs_mentions": ["TVA"]},
        "categories": CATEGORIES, "personnes": PERSONNES, "emetteurs_connus": EMETTEURS_CONNUS,
    }


def faux(reponses):
    """`reponses` : {modèle: texte factice dont il rend la réponse} ; un modèle absent donne le texte personnel."""
    def generer(url, modele, consigne, images, delai, keep_alive, format=None, options=None):
        if "verdict" in format["properties"]:
            return json.dumps({"verdict": "administratif"})
        return json.dumps(reponses.get(modele, PERSONNEL)["reponse"])
    return generer


def executer(modeles, reponses, seuil):
    return cascade.executer([(Path("doc.pdf"), TEXTE)], configuration(seuil),
                            {"tri_rapide": "tri", "classification": modeles}, faux(reponses))[0]


def test_un_modele_seul_garde_son_verdict():
    resultat = executer("m1", {}, 0.4)
    assert resultat.verdict.domaine == "personnel" and resultat.confiance == 1.0


def test_verdict_au_dessus_du_seuil_est_retenu():
    resultat = executer(["m1", "m2", "m3"], {"m3": PROFESSIONNEL}, 0.6)
    assert resultat.verdict.domaine == "personnel" and resultat.confiance == pytest.approx(2 / 3)


def test_verdict_sous_le_seuil_devient_incertain():
    resultat = executer(["m1", "m2", "m3"], {"m3": PROFESSIONNEL}, 0.8)
    assert resultat.verdict.domaine == "incertain" and resultat.confiance == pytest.approx(2 / 3)


def test_egalite_entre_modeles_vaut_incertain():
    assert executer(["m1", "m2"], {"m2": PROFESSIONNEL}, 0.4).verdict.domaine == "incertain"


def test_le_seuil_se_lit_dans_la_configuration():
    assert executer(["m1", "m2", "m3"], {"m2": PROFESSIONNEL, "m3": PROFESSIONNEL}, 0.4).verdict.domaine == "professionnel"
