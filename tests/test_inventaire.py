"""Inventaire : lecture seule des deux coffres, plan écrit dans chaque coffre, arbre inchangé."""

import json

import pytest

from modules import inventaire
from tests.test_classement import config  # noqa: F401


def ecrire(chemin, contenu):
    chemin.parent.mkdir(parents=True, exist_ok=True)
    chemin.write_bytes(contenu)


@pytest.fixture
def coffres(tmp_path, config):  # noqa: F811
    config["extensions_cibles"] = [".pdf", ".png"]
    a, b = tmp_path / "a", tmp_path / "b"
    ecrire(a / "Rangement/Personne1/2025/facture.pdf", b"facture")
    ecrire(a / "Rangement/Personne1/2025/facture-bis.pdf", b"facture")
    ecrire(a / "Ancien_vrac/releve.pdf", b"releve")
    ecrire(a / "Ancien_vrac/notes.txt", b"pas un document cible")
    ecrire(a / "vide-poches-x/attente.pdf", b"en attente")
    ecrire(a / "logs/sessions/s.pdf", b"journal")
    ecrire(a / ".cache/cache.pdf", b"cache")
    ecrire(b / "Classement/2025/Factures/facture-pro.pdf", b"commune")
    ecrire(a / "Rangement/Personne1/2025/identite.pdf", b"commune")
    ecrire(b / "Clients/devis.png", b"devis")
    return config


def test_le_plan_est_ecrit_et_le_coffre_reste_inchange(tmp_path, coffres):
    avant = {d: inventaire.empreinte_arbre(tmp_path / d) for d in ("a", "b")}
    ecrits = inventaire.ecrire_plans(inventaire.construire_plans(coffres), coffres)
    assert all(chemin.is_file() and tmp_path / d in chemin.parents for d, chemin in zip(("a", "b"), ecrits.values()))
    apres = {d: inventaire.empreinte_arbre(tmp_path / d, ignorer=[ecrits[c] for c in ecrits]) for d in ("a", "b")}
    assert avant == apres


def test_le_plan_classe_chaque_document(tmp_path, coffres):
    plans = inventaire.construire_plans(coffres)
    perso = {a["chemin"]: a for a in plans["personnel"]["actions"]}
    assert set(perso) == {"Rangement/Personne1/2025/facture.pdf", "Rangement/Personne1/2025/facture-bis.pdf",
                          "Rangement/Personne1/2025/identite.pdf", "Ancien_vrac/releve.pdf"}
    assert perso["Ancien_vrac/releve.pdf"]["action"] == "a_classer"
    assert perso["Rangement/Personne1/2025/facture.pdf"]["action"] == "conserver"
    assert perso["Rangement/Personne1/2025/facture.pdf"]["doublon_de"] == "Rangement/Personne1/2025/facture-bis.pdf"
    assert perso["Rangement/Personne1/2025/facture-bis.pdf"]["doublon_de"] is None
    assert perso["Rangement/Personne1/2025/identite.pdf"]["present_dans_autre_coffre"] is True
    assert plans["personnel"]["resume"] == {"documents": 4, "conserver": 3, "a_classer": 1, "doublons_internes": 1, "presents_dans_autre_coffre": 1, "a_verifier_non_listes": 0}
    assert plans["professionnel"]["resume"]["a_classer"] == 1


def test_un_plan_ne_nomme_aucun_fichier_de_l_autre_coffre(coffres):
    plans = inventaire.construire_plans(coffres)
    assert "facture-pro" not in json.dumps(plans["personnel"]) and "identite" not in json.dumps(plans["professionnel"])


def test_un_second_inventaire_n_ecrase_pas_le_premier(coffres):
    plans = inventaire.construire_plans(coffres)
    inventaire.ecrire_plans(plans, coffres)
    with pytest.raises(FileExistsError):
        inventaire.ecrire_plans(plans, coffres)
