"""Table des noms de dossiers et de préfixes par défaut selon la langue."""

import json
import unicodedata
from pathlib import Path

from modules import defauts_langue, domaines, mesure_domaines, messages, nommage

RACINE = Path(__file__).resolve().parent.parent
ATTENDUS = {
    "fr": ("À_VÉRIFIER", "[À_VÉRIFIER]", "doublon"),
    "en": ("TO_CHECK", "[TO_CHECK]", "duplicate"),
    "de": ("ZU_PRÜFEN", "[ZU_PRÜFEN]", "Duplikat"),
    "es": ("POR_VERIFICAR", "[POR_VERIFICAR]", "duplicado"),
    "zh": ("待核实", "[待核实]", "重复"),
}
LOCALES = {"fr": "fr_FR.UTF-8", "en": "en_US.UTF-8", "de": "de_DE.UTF-8", "es": "es_ES.UTF-8", "zh": "zh_CN.UTF-8"}


def exemple():
    return json.loads((RACINE / "config.exemple.json").read_text(encoding="utf-8"))


def test_la_table_porte_les_cinq_langues_et_les_valeurs_decidees():
    for langue, attendu in ATTENDUS.items():
        valeurs = defauts_langue.valeurs(langue)
        assert (valeurs["sous_repertoire_a_verifier"], valeurs["prefixe_a_verifier"],
                valeurs["repertoire_doublon"]) == attendu


def test_les_valeurs_sont_des_noms_de_fichier_admis_sous_linux(tmp_path):
    for langue in messages.LANGUES:
        for valeur in defauts_langue.valeurs(langue).values():
            assert valeur and valeur not in (".", "..")
            assert "/" not in valeur and "\x00" not in valeur and "\n" not in valeur and "\r" not in valeur
            assert unicodedata.is_normalized("NFC", valeur), valeur
            assert len(valeur.encode("utf-8")) <= 255, valeur
            dossier = tmp_path / langue / valeur
            dossier.mkdir(parents=True)
            assert dossier.is_dir()


def test_la_casse_et_les_accents_suivent_la_configuration():
    for langue in messages.LANGUES:
        configuration = defauts_langue.appliquer(exemple(), langue)
        valeurs = defauts_langue.valeurs(langue)
        exclus = mesure_domaines.dossiers_exclus(configuration)
        assert valeurs["sous_repertoire_a_verifier"].casefold() in exclus
        assert valeurs["repertoire_doublon"].casefold() in exclus
        verdict = domaines.Verdict(administratif=True, domaine=domaines.PERSONNEL, categorie="Factures")
        nom = nommage.nommer_a_verifier({"prefixe_a_verifier": valeurs["prefixe_a_verifier"],
                                         "format_a_verifier": "{origine}{ext}", "separateur": "_",
                                         "espaces_vers": "-"}, verdict, ".pdf", "courrier.pdf")
        assert nom == valeurs["prefixe_a_verifier"] + "courrier.pdf"


def test_appliquer_ne_modifie_pas_la_configuration_d_origine():
    source = exemple()
    avant = json.dumps(source, sort_keys=True)
    configuration = defauts_langue.appliquer(source, "de")
    assert json.dumps(source, sort_keys=True) == avant
    assert configuration["destination"]["repertoire_doublon"] == "Duplikat"
    assert configuration["nommage"]["prefixe_a_verifier"] == "[ZU_PRÜFEN]"
    assert configuration["destinations"]["personnel"]["sous_repertoire_a_verifier"] == "ZU_PRÜFEN"
    assert "duplicate" not in configuration["scan"]["exclusions_automatiques"]
    assert "Duplikat" in configuration["scan"]["exclusions_automatiques"]


def test_l_exemple_reste_neutre():
    configuration = exemple()
    assert configuration["destination"]["repertoire_doublon"] == "duplicate"
    assert configuration["nommage"]["prefixe_a_verifier"] == "[TO_CHECK]"
    for destination in configuration["destinations"].values():
        assert destination["sous_repertoire_a_verifier"] == "TO_CHECK"
    assert "À_VÉRIFIER" not in json.dumps(configuration, ensure_ascii=False)


def test_le_diagnostic_voit_le_dossier_et_le_prefixe_a_verifier_manquants():
    import dibab

    configuration = exemple()
    assert dibab.cles_absentes_classement(configuration) == []
    del configuration["nommage"]["prefixe_a_verifier"]
    del configuration["destinations"]["personnel"]["sous_repertoire_a_verifier"]
    absentes = dibab.cles_absentes_classement(configuration)
    assert "nommage.prefixe_a_verifier" in absentes
    assert "destinations.personnel.sous_repertoire_a_verifier" in absentes
    assert dibab.cles_configuration_absentes(configuration).count("nommage.prefixe_a_verifier") == 1
