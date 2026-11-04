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


def test_le_journal_garde_objet_motif_et_ce_que_chaque_modele_a_rendu_sans_destinataire(banc, monkeypatch):  # noqa: F811
    racine, _ = banc
    brancher_faux_modele(monkeypatch, TEXTES[8]["texte"])
    brancher_cascade(monkeypatch, "administratif", {**TEXTES[0]["reponse"], "emetteur": "", "destinataire": "Madame Personne1"})
    lancer(monkeypatch, "--dry-run")
    brut = next((racine / "coffre-a" / "logs" / "sessions").glob("session_*.jsonl")).read_text(encoding="utf-8")
    evenements = [e for e in map(json.loads, brut.splitlines()) if e["evenement"] == "classification"]
    assert {e["objet"] for e in evenements} == {"courrier factice"}
    assert {e["motif"] for e in evenements} == {"sans_destinataire_ni_emetteur_connu"}
    for evenement in evenements:
        (rendu,) = evenement["par_modele"]
        assert set(rendu) == {"modele", "valide", "domaine", "categorie", "emetteur", "emetteur_cite", "destinataire_cite",
                              "nature_destinataire"}
        assert rendu["destinataire_cite"] is False and rendu["emetteur"] is None and rendu["domaine"] == "incertain"
    assert "Madame Personne1" not in brut and MOT_SECRET not in brut


def test_la_ligne_montre_l_objet_l_accord_et_le_motif(banc, monkeypatch, capsys):  # noqa: F811
    brancher_faux_modele(monkeypatch, "texte")
    brancher_cascade(monkeypatch, "incertain", TEXTES[8]["reponse"])
    lancer(monkeypatch, "--dry-run")
    sortie = capsys.readouterr().out
    assert sortie.count("tri incertain, domaine incertain, accord 1/1") == 3
    assert sortie.count("objet : courrier factice") == 3 and sortie.count("motif : tri incertain") == 3


def _brancher_tri_decision(banc, monkeypatch, seuils):
    racine, chemin_config = banc
    configuration = json.loads(chemin_config.read_text(encoding="utf-8"))
    configuration["ollama"]["roles"].update(tri_decision=["m-decision"], objet=["m-objet"])
    configuration["classification"]["seuils_tri_decision"] = seuils
    chemin_config.write_text(json.dumps(configuration), encoding="utf-8")
    monkeypatch.setattr(skrivagner.mod_modeles, "lister_capacites",
                        lambda url, delai: {"modele-factice": ("completion",), "m-decision:latest": ("decision",), "m-objet:latest": ("completion",)})

    def generer(url, modele, consigne, images, delai, keep_alive, format=None, options=None):
        if "verdict" in format["properties"]:
            return json.dumps({"verdict": "administratif", "objet": "objet du tri par génération"})
        if set(format["properties"]) == {"objet"}:
            return json.dumps({"objet": "objet du modèle d'objet"})
        return json.dumps(TEXTES[0]["reponse"])

    def decider(url, modele, etat, questions, delai, keep_alive):
        return {"nature": {"probabilities": {"administratif": 0.99, "non_administratif": 0.01}}}
    monkeypatch.setattr(skrivagner.mod_cascade, "executer", partial(skrivagner.mod_cascade.executer, generer=generer, decider=decider))
    return racine


def _evenements(racine, nom):
    brut = next((racine / "coffre-a" / "logs" / "sessions").glob("session_*.jsonl")).read_text(encoding="utf-8")
    return [e for e in map(json.loads, brut.splitlines()) if e["evenement"] == nom]


def test_le_dry_run_annonce_le_tri_par_decision_ou_son_repli(banc, monkeypatch, capsys):  # noqa: F811
    seuils = {"m-decision": {"non_administratif": 0.97, "administratif": 0.42, "caracteres_min": 100}}
    racine = _brancher_tri_decision(banc, monkeypatch, seuils)
    brancher_faux_modele(monkeypatch, TEXTES[0]["texte"])
    assert lancer(monkeypatch, "--dry-run") == 0
    sortie = capsys.readouterr().out
    assert "Modèle tri_decision  : m-decision:latest" in sortie and "Modèle objet         : m-objet:latest" in sortie
    assert "Tri par décision   : non administratif à partir de 0.97, administratif sous 0.42, 100 caractères" in sortie
    assert sortie.count("objet : objet du modèle d'objet") == 3
    (retenus,) = _evenements(racine, "modeles_retenus")
    assert (retenus["tri_decision"], retenus["objet"], retenus["repli_tri"]) == ("m-decision:latest", "m-objet:latest", None)
    for evenement in _evenements(racine, "classification"):
        assert (evenement["modele_tri"], evenement["modele_objet"], evenement["p_non_administratif"], evenement["repli_tri"]) == (
            "m-decision:latest", "m-objet:latest", 0.01, None)


def test_le_dry_run_dit_pourquoi_le_tri_par_decision_n_est_pas_utilise(banc, monkeypatch, capsys):  # noqa: F811
    racine = _brancher_tri_decision(banc, monkeypatch, {})
    brancher_faux_modele(monkeypatch, TEXTES[0]["texte"])
    assert lancer(monkeypatch, "--dry-run") == 0
    sortie = capsys.readouterr().out
    assert ("Tri par décision   : non utilisé, pas de seuils valides pour m-decision:latest dans classification.seuils_tri_decision ; "
            "le tri passe par modele-factice") in sortie
    (retenus,) = _evenements(racine, "modeles_retenus")
    assert (retenus["tri_decision"], retenus["objet"], retenus["repli_tri"]) == ("m-decision:latest", None, "seuils_absents")
    for evenement in _evenements(racine, "classification"):
        assert (evenement["modele_tri"], evenement["p_non_administratif"], evenement["repli_tri"]) == ("modele-factice", None, "seuils_absents")


def test_sans_tri_par_decision_l_en_tete_reste_celui_d_avant(banc, monkeypatch, capsys):  # noqa: F811
    brancher_faux_modele(monkeypatch, TEXTES[0]["texte"])
    brancher_cascade(monkeypatch, "administratif", TEXTES[0]["reponse"])
    monkeypatch.setattr(skrivagner.mod_modeles, "lister_capacites", lambda *_: (_ for _ in ()).throw(AssertionError("non déclaré")))
    assert lancer(monkeypatch, "--dry-run") == 0
    sortie = capsys.readouterr().out
    assert "tri_decision" not in sortie and "Tri par décision" not in sortie
