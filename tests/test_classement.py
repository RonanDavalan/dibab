"""Chemin de destination et nom normalisé de chaque domaine : tout est calculé, rien n'est écrit."""

from datetime import date, datetime

import pytest

from modules import classement
from modules.domaines import Verdict
from tests.textes_factices import CONFIG_CLASSEMENT

REPLI = datetime(2024, 7, 9)


@pytest.fixture
def config(tmp_path):
    return {
        **CONFIG_CLASSEMENT,
        "nommage": {"format": "{date}_{emetteur}_{categorie}{ext}", "date_format": "%Y-%m-%d", "date_inconnue_prefixe": "~",
                    "emetteur_inconnu": "Inconnu", "espaces_vers": "-", "prefixe_a_verifier": "[AV]", "suffixe_collision": "_{n}"},
        "pieces_communes": ["Identité"],
        "personnes": ["Personne1", "Personne2"],
        "destinations": {
            "personnel": {"racine": str(tmp_path / "a"), "sous_repertoire_classement": "Rangement", "sous_repertoire_a_verifier": "Tri"},
            "professionnel": {"racine": str(tmp_path / "b"), "sous_repertoire_classement": "Classement", "sous_repertoire_a_verifier": "Tri"},
        },
    }


@pytest.fixture
def source(tmp_path):
    chemin = tmp_path / "scan.PDF"
    chemin.write_bytes(b"contenu")
    return chemin


def planifier(source, config, **verdict):
    return classement.planifier(source, Verdict(True, **verdict), config, REPLI)


def test_personnel_range_par_personne_et_annee(source, config, tmp_path):
    plan = planifier(source, config, domaine="personnel", categorie="CAF", emetteur="Organisme X", personne="Personne1", date=date(2026, 3, 15))
    assert plan.chemins == (tmp_path / "a/Rangement/Personne1/2026/2026-03-15_Organisme-X_CAF.pdf",)


def test_professionnel_range_par_annee_et_categorie(source, config, tmp_path):
    plan = planifier(source, config, domaine="professionnel", categorie="Factures", emetteur="Client", date=date(2025, 12, 31))
    assert plan.chemins == (tmp_path / "b/Classement/2025/Factures/2025-12-31_Client_Factures.pdf",)


def test_mixte_va_a_plat_dans_a_verifier_du_coffre_professionnel(source, config, tmp_path):
    plan = planifier(source, config, domaine="mixte", categorie="Impôts", emetteur="Fisc", date=date(2026, 5, 15))
    assert plan.chemins == (tmp_path / "b/Tri/[AV]scan.PDF",)


def test_incertain_sans_signal_va_a_verifier_du_coffre_personnel(source, config, tmp_path):
    plan = planifier(source, config, domaine="incertain", categorie="Inconnue")
    assert plan.chemins == (tmp_path / "a/Tri/[AV]scan.PDF",)


def test_incertain_avec_signal_professionnel_va_au_coffre_professionnel(source, config, tmp_path):
    plan = planifier(source, config, domaine="incertain", categorie="Inconnue", signaux=({"domaine": "professionnel", "nature": "mention"},))
    assert plan.chemins[0].parent == tmp_path / "b/Tri"


def test_piece_commune_a_deux_chemins_de_meme_nom_et_meme_empreinte(source, config, tmp_path):
    plan = planifier(source, config, domaine="personnel", categorie="Identité", emetteur="Prefecture", personne="Personne2", date=date(2026, 1, 2))
    assert plan.chemins == (tmp_path / "a/Rangement/Personne2/2026/2026-01-02_Prefecture_Identité.pdf",
                            tmp_path / "b/Classement/2026/Identité/2026-01-02_Prefecture_Identité.pdf")
    assert plan.empreinte


def test_non_administratif_ne_bouge_pas(source, config):
    assert classement.planifier(source, Verdict(False, "incertain", "Inconnue"), config, REPLI) is None


def test_personne_inconnue_ou_hors_liste_va_dans_le_dossier_commun(source, config, tmp_path):
    for personne in (None, "Quelqu'un d'autre"):
        plan = planifier(source, config, domaine="personnel", categorie="CAF", personne=personne, date=date(2026, 3, 15))
        assert plan.chemins[0].parent == tmp_path / "a/Rangement/Commun/2026"


def test_date_inconnue_prend_l_annee_du_repli(source, config, tmp_path):
    plan = planifier(source, config, domaine="personnel", categorie="CAF", personne="Personne1")
    assert plan.chemins[0].parent == tmp_path / "a/Rangement/Personne1/2024"
    assert plan.nom.startswith("~2024-07-09_")


@pytest.mark.parametrize("categorie", ["../..", "a/../../b", "..", " "])
def test_une_categorie_ne_sort_pas_de_la_destination(source, config, tmp_path, categorie):
    plan = planifier(source, config, domaine="professionnel", categorie=categorie, date=date(2026, 3, 15))
    assert (tmp_path / "b/Classement") in plan.chemins[0].parents
    assert ".." not in plan.chemins[0].relative_to(tmp_path).parts


def test_un_document_a_verifier_garde_son_nom_d_origine(source, config):
    plan = planifier(source, config, domaine="incertain", categorie="Inconnue")
    assert plan.nom == "[AV]scan.PDF"
