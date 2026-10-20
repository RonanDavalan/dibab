"""Branchement de la cascade derrière l'extraction : verdict, domaine et destination affichés, rien déplacé."""

import json
from functools import partial

import skrivagner
from tests.test_classification import FauxModele
from tests.test_extraction_dry_run import MOT_SECRET, banc, brancher_faux_modele, lancer  # noqa: F401
from tests.textes_factices import TEXTES


def brancher_cascade(monkeypatch, tri, fine):
    faux = FauxModele(tri=tri, fine=fine)
    monkeypatch.setattr(skrivagner.mod_cascade, "executer", partial(skrivagner.mod_cascade.executer, generer=faux))
    return faux


def test_dry_run_affiche_verdict_domaine_et_destination(banc, monkeypatch, capsys):  # noqa: F811
    # Les deux documents lus par OCR portent le texte factice ; la couche texte de texte.pdf n'a aucun destinataire.
    brancher_faux_modele(monkeypatch, TEXTES[0]["texte"])
    brancher_cascade(monkeypatch, "administratif", TEXTES[0]["reponse"])
    assert lancer(monkeypatch, "--dry-run") == 0
    sortie = capsys.readouterr().out
    assert sortie.count("tri administratif, domaine personnel") == 2
    assert "texte.pdf : tri administratif, domaine incertain" in sortie
    assert sortie.count("-> coffre personnel, classement :") == 2
    assert MOT_SECRET not in sortie


def test_un_incertain_affiche_a_verifier_sans_deplacement(banc, monkeypatch, capsys):  # noqa: F811
    racine, _ = banc
    brancher_faux_modele(monkeypatch, "texte")
    brancher_cascade(monkeypatch, "incertain", TEXTES[8]["reponse"])
    lancer(monkeypatch, "--dry-run")
    sortie = capsys.readouterr().out
    assert "tri incertain, domaine incertain" in sortie
    assert "-> coffre personnel, a_verifier :" in sortie and "(non déplacé)" in sortie
    assert sorted(p.name for p in (racine / "source").iterdir()) == ["photo.png", "scan.pdf", "texte.pdf"]


def test_un_non_administratif_ne_bouge_pas(banc, monkeypatch, capsys):  # noqa: F811
    brancher_faux_modele(monkeypatch, "recette")
    brancher_cascade(monkeypatch, "non_administratif", None)
    lancer(monkeypatch, "--dry-run")
    sortie = capsys.readouterr().out
    assert sortie.count("tri non administratif, domaine sans objet") == 3
    assert sortie.count("-> ne bouge pas (non administratif)") == 3


def test_le_journal_garde_le_verdict_sans_citation_ni_texte(banc, monkeypatch):  # noqa: F811
    racine, _ = banc
    brancher_faux_modele(monkeypatch, TEXTES[2]["texte"])
    brancher_cascade(monkeypatch, "administratif", TEXTES[2]["reponse"])
    lancer(monkeypatch, "--dry-run")
    brut = next((racine / "coffre-a" / "logs" / "sessions").glob("session_*.jsonl")).read_text(encoding="utf-8")
    evenements = [e for e in map(json.loads, brut.splitlines()) if e["evenement"] == "classification"]
    assert len(evenements) == 3 and sorted(e["domaine"] for e in evenements) == ["incertain", "professionnel", "professionnel"]
    assert all(set(s) == {"domaine", "nature"} for e in evenements for s in e["signaux"])
    assert "SIRET 123" not in brut and MOT_SECRET not in brut
