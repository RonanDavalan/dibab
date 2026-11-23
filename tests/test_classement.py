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
    plan = planifier(source, config, domaine="personnel", categorie="Aides", emetteur="Organisme X", personne="Personne1", date=date(2026, 3, 15))
    assert plan.chemins == (tmp_path / "a/Rangement/Personne1/2026/2026-03-15_Organisme-X_Aides.pdf",)


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
    plan = planifier(source, config, domaine="personnel", categorie="Identité", emetteur="Prefecture", personne="Personne2", date=date(2026, 1, 2),
                   categorie_unanime=True)
    assert plan.chemins == (tmp_path / "a/Rangement/Personne2/2026/2026-01-02_Prefecture_Identité.pdf",
                            tmp_path / "b/Classement/2026/Identité/2026-01-02_Prefecture_Identité.pdf")
    assert plan.empreinte


def test_non_administratif_ne_bouge_pas(source, config):
    assert classement.planifier(source, Verdict(False, "incertain", "Inconnue"), config, REPLI) is None


def test_personne_inconnue_ou_hors_liste_va_dans_le_dossier_commun(source, config, tmp_path):
    for personne in (None, "Quelqu'un d'autre"):
        plan = planifier(source, config, domaine="personnel", categorie="Aides", personne=personne, date=date(2026, 3, 15))
        assert plan.chemins[0].parent == tmp_path / "a/Rangement/Commun/2026"


def test_date_inconnue_prend_l_annee_du_repli(source, config, tmp_path):
    plan = planifier(source, config, domaine="personnel", categorie="Aides", personne="Personne1")
    assert plan.chemins[0].parent == tmp_path / "a/Rangement/Personne1/2024"
    assert plan.nom.startswith("~2024-07-09_")


@pytest.mark.parametrize("categorie", ["../..", "a/../../b", "..", " "])
def test_une_categorie_ne_sort_pas_de_la_destination(source, config, tmp_path, categorie):
    plan = planifier(source, config, domaine="professionnel", categorie=categorie, date=date(2026, 3, 15))
    assert (tmp_path / "b/Classement") in plan.chemins[0].parents
    assert ".." not in plan.chemins[0].relative_to(tmp_path).parts


def test_un_document_a_verifier_garde_son_nom_d_origine(source, config):
    # Sans `nommage.format_a_verifier`, même avec un objet, le nom d'origine seul suit le préfixe.
    plan = planifier(source, config, domaine="incertain", categorie="Inconnue", objet="attestation", emetteur="Organisme public")
    assert plan.nom == "[AV]scan.PDF"


FORMAT_A_VERIFIER = "{date}_{emetteur}_{objet}_{origine}{ext}"


@pytest.fixture
def config_a_verifier(config):
    return {**config, "nommage": {**config["nommage"], "separateur": "_", "format_a_verifier": FORMAT_A_VERIFIER}}


def test_un_document_a_verifier_prend_date_emetteur_objet_et_nom_d_origine(source, config_a_verifier):
    plan = planifier(source, config_a_verifier, domaine="incertain", categorie="Aides", date=date(2026, 3, 15),
                     emetteur="Caisse Exemple", objet="attestation de paiement")
    assert plan.nom == "[AV]2026-03-15_Caisse-Exemple_attestation-de-paiement_scan.pdf"


@pytest.mark.parametrize("champs, attendu", [
    ({}, "[AV]scan.pdf"),
    ({"objet": "relevé de compte"}, "[AV]relevé-de-compte_scan.pdf"),
    ({"emetteur": "Banque Exemple"}, "[AV]Banque-Exemple_scan.pdf"),
    ({"date": date(2026, 1, 2)}, "[AV]2026-01-02_scan.pdf"),
])
def test_un_segment_vide_ou_inconnu_est_retire_avec_son_separateur(source, config_a_verifier, champs, attendu):
    plan = planifier(source, config_a_verifier, domaine="incertain", categorie="Inconnue", **champs)
    assert plan.nom == attendu and "Inconnu" not in plan.nom and "__" not in plan.nom


def test_une_categorie_inconnue_ne_s_ecrit_pas_dans_un_nom_a_verifier(source, config_a_verifier):
    config_a_verifier["nommage"]["format_a_verifier"] = "{categorie}_{objet}_{origine}{ext}"
    assert planifier(source, config_a_verifier, domaine="incertain", categorie="Inconnue", objet="avis").nom == "[AV]avis_scan.pdf"


def test_le_nom_a_verifier_tient_en_180_caracteres_en_raccourcissant_l_origine_puis_l_objet(tmp_path, config_a_verifier):
    source = tmp_path / ("origine-" + "o" * 150 + ".pdf")
    source.write_bytes(b"x")
    objet = "objet " * 12
    plan = planifier(source, config_a_verifier, domaine="incertain", categorie="Inconnue", date=date(2026, 3, 15),
                     emetteur="E" * 80, objet=objet)
    assert len(plan.nom) <= 180 and plan.nom.endswith(".pdf")
    debut_origine = plan.nom.rindex("_") + 1
    assert plan.nom[debut_origine:-4] == "origine-" + "o" * 12
    assert "E" * 80 in plan.nom and "objet" in plan.nom


def test_une_origine_seule_trop_longue_est_raccourcie_sans_toucher_l_objet(tmp_path, config_a_verifier):
    source = tmp_path / ("x" * 200 + ".pdf")
    source.write_bytes(b"x")
    plan = planifier(source, config_a_verifier, domaine="incertain", categorie="Inconnue", objet="facture")
    assert len(plan.nom) == 180 and plan.nom.startswith("[AV]facture_xxx")


def test_le_nom_a_verifier_reste_sous_255_octets(tmp_path, config_a_verifier):
    source = tmp_path / ("é" * 120 + ".pdf")
    source.write_bytes(b"x")
    plan = planifier(source, config_a_verifier, domaine="incertain", categorie="Inconnue", objet="à" * 80)
    assert len(plan.nom.encode("utf-8")) <= 255


def test_l_objet_ne_fabrique_ni_chemin_ni_caractere_de_controle(source, config_a_verifier):
    plan = planifier(source, config_a_verifier, domaine="incertain", categorie="Inconnue", objet="../a\\b\x07c")
    assert "/" not in plan.nom and "\\" not in plan.nom and "\x07" not in plan.nom


def test_objet_est_permis_dans_le_format_d_un_document_classe(source, config):
    config["nommage"]["format"] = "{date}_{emetteur}_{objet}_{categorie}{ext}"
    avec = planifier(source, config, domaine="personnel", categorie="Aides", personne="Personne1", date=date(2026, 3, 15),
                     emetteur="Organisme public", objet="notification")
    sans = planifier(source, config, domaine="personnel", categorie="Aides", personne="Personne1", date=date(2026, 3, 15), emetteur="Organisme public")
    assert (avec.nom, sans.nom) == ("2026-03-15_Organisme-public_notification_Aides.pdf", "2026-03-15_Organisme-public_Aides.pdf")


def test_le_format_par_defaut_d_un_document_classe_ne_change_pas(source, config_a_verifier):
    plan = planifier(source, config_a_verifier, domaine="personnel", categorie="Aides", personne="Personne1",
                     date=date(2026, 3, 15), emetteur="Organisme public", objet="notification")
    assert plan.nom == "2026-03-15_Organisme-public_Aides.pdf"
