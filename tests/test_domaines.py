"""Tests de modules/domaines.py sur des verdicts simulés."""

from pathlib import Path

import pytest

from modules.domaines import (
    A_VERIFIER, CLASSEMENT, PERSONNEL, PROFESSIONNEL, Cible, Verdict,
    dossier_cible, domaine_emetteur, router, verdict_depuis_dict,
)

SIGNAL_PRO = {"domaine": "professionnel", "libelle": "numéro de SIRET"}
SIGNAL_PERSO = {"domaine": "personnel", "libelle": "allocations"}

DESTINATIONS = {
    "personnel": {"racine": "/coffre-a", "sous_repertoire_classement": "Rangement",
                  "sous_repertoire_a_verifier": "Tri"},
    "professionnel": {"racine": "/coffre-b", "sous_repertoire_classement": "Dossiers",
                      "sous_repertoire_a_verifier": "Tri"},
}


def verdict(domaine, signaux=(), administratif=True, categorie="Factures"):
    return Verdict(administratif=administratif, domaine=domaine, categorie=categorie, signaux=tuple(signaux))


def test_personnel():
    assert router(verdict("personnel")) == [Cible(PERSONNEL, CLASSEMENT)]


def test_professionnel():
    assert router(verdict("professionnel")) == [Cible(PROFESSIONNEL, CLASSEMENT)]


def test_mixte_va_a_verifier_dans_le_coffre_professionnel():
    assert router(verdict("mixte")) == [Cible(PROFESSIONNEL, A_VERIFIER)]


def test_mixte_avec_signal_personnel_reste_a_verifier_professionnel():
    assert router(verdict("mixte", [SIGNAL_PERSO])) == [Cible(PROFESSIONNEL, A_VERIFIER)]


def test_incertain_avec_signal_professionnel():
    assert router(verdict("incertain", [SIGNAL_PERSO, SIGNAL_PRO])) == [Cible(PROFESSIONNEL, A_VERIFIER)]


def test_incertain_sans_signal_professionnel():
    assert router(verdict("incertain")) == [Cible(PERSONNEL, A_VERIFIER)]
    assert router(verdict("incertain", [SIGNAL_PERSO])) == [Cible(PERSONNEL, A_VERIFIER)]


def test_non_administratif_ne_bouge_pas():
    assert router(verdict("professionnel", [SIGNAL_PRO], administratif=False)) == []


def test_domaine_inconnu_vaut_incertain():
    assert router(verdict("coffre-secret")) == [Cible(PERSONNEL, A_VERIFIER)]
    assert router(verdict("coffre-secret", [SIGNAL_PRO])) == [Cible(PROFESSIONNEL, A_VERIFIER)]


def test_piece_commune_recoit_les_deux_coffres_quel_que_soit_le_domaine():
    cibles = router(verdict("incertain", categorie="Identité"), pieces_communes=("Identité",))
    assert cibles == [Cible(PERSONNEL, CLASSEMENT), Cible(PROFESSIONNEL, CLASSEMENT)]


def test_piece_commune_non_administrative_ne_bouge_pas():
    assert router(verdict("personnel", administratif=False, categorie="Identité"), ("Identité",)) == []


def test_dossier_cible_suit_la_table_destinations():
    assert dossier_cible(Cible(PERSONNEL, CLASSEMENT), DESTINATIONS) == Path("/coffre-a/Rangement")
    assert dossier_cible(Cible(PROFESSIONNEL, A_VERIFIER), DESTINATIONS) == Path("/coffre-b/Tri")


def test_domaine_emetteur():
    connus = {"Factures": [{"nom": "Fournisseur-X", "domaine": "professionnel"}]}
    assert domaine_emetteur(connus, "Fournisseur-X") == "professionnel"
    assert domaine_emetteur(connus, "Inconnu") is None


def test_verdict_depuis_dict():
    resultat = verdict_depuis_dict({"administratif": True, "categorie": "CAF", "domaine": "personnel",
                                    "date": "2026-05-15", "signaux": [SIGNAL_PERSO]})
    assert resultat.date.isoformat() == "2026-05-15"
    assert resultat.signaux == (SIGNAL_PERSO,)


@pytest.mark.parametrize("donnees", [
    {"categorie": "CAF"},
    {"administratif": "oui", "categorie": "CAF"},
    {"administratif": True, "categorie": "CAF", "date": "15/05/2026"},
])
def test_verdict_invalide(donnees):
    with pytest.raises(ValueError):
        verdict_depuis_dict(donnees)
