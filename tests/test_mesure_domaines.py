"""Mesure du domaine : tirage, étiquettes, matrice, seuil de confiance et sortie sans donnée identifiante."""

import io
import json
from types import SimpleNamespace

import pytest

from modules import mesure_domaines, modeles
from tests.test_classification import PARAMETRES as CLASSIFICATION
from tests.test_extraction import PARAMETRES as EXTRACTION
from tests.textes_factices import CATEGORIES, EMETTEURS_CONNUS, PERSONNES, TEXTES

TEXTE_PERSONNEL = TEXTES[0]["texte"]
TEXTE_PROFESSIONNEL = TEXTES[2]["texte"]
REPONSE_PERSONNELLE = TEXTES[0]["reponse"]
REPONSE_PROFESSIONNELLE = TEXTES[2]["reponse"]
REPONSE_FAUSSE = {**REPONSE_PERSONNELLE, "emetteur": "", "nature_destinataire": "entreprise"}
# Sans CAF dans la liste : la liste retrouverait l'émetteur que le faux modèle tait, et il ne se tromperait plus.
EMETTEURS_SANS_CAF = {groupe: entrees for groupe, entrees in EMETTEURS_CONNUS.items() if groupe != "CAF"}


def configuration(racine_a, racine_b):
    return {
        "destination": {"sous_repertoire_logs": "logs", "vide_poches_prefixe": "vide-poches-"},
        "destinations": {
            "personnel": {"racine": str(racine_a), "sous_repertoire_classement": "R", "sous_repertoire_a_verifier": "À_VÉRIFIER"},
            "professionnel": {"racine": str(racine_b), "sous_repertoire_classement": "D", "sous_repertoire_a_verifier": "À_VÉRIFIER"},
        },
        "ollama": {"url": "http://x", "timeout_secondes": 7, "keep_alive_entre_pages": "2m",
                   "roles": {"ocr": ["ocr"], "tri_rapide": ["tri"], "classification": ["bon", "faux"]}},
        "classification": CLASSIFICATION, "extraction": EXTRACTION, "extensions_cibles": [".pdf", ".png"],
        "categories": CATEGORIES, "personnes": PERSONNES, "emetteurs_connus": EMETTEURS_SANS_CAF,
        "mesure": {"graine": 7, "documents_par_coffre": 3, "exclusions": ["Archive", "rebut", "doublon"], "taux_erreur_max": 0.02},
    }


def ecrire(chemin, contenu=b"x"):
    chemin.parent.mkdir(parents=True, exist_ok=True)
    chemin.write_bytes(contenu)
    return chemin


def test_les_dossiers_exclus_ne_sont_pas_tires(tmp_path):
    racine = tmp_path / "coffre"
    gardes = [ecrire(racine / "R" / "a.pdf"), ecrire(racine / "R" / "sous" / "b.PNG")]
    for ecartes in ("Archive/a.pdf", "R/rebut/a.pdf", "R/doublon/a.pdf", "vide-poches-machine1/a.pdf", "À_VÉRIFIER/a.pdf",
                    "logs/a.pdf", "R/.cache/a.pdf", "R/.cache.pdf", "R/note.md"):
        ecrire(racine / ecartes)
    (racine / "R" / "lien.pdf").symlink_to(gardes[0])
    assert mesure_domaines.lister_candidats(racine, configuration(racine, racine)) == sorted(gardes)


def test_une_piece_commune_n_est_pas_tiree(tmp_path):
    commune_a = ecrire(tmp_path / "a" / "commune.pdf", b"meme contenu")
    ecrire(tmp_path / "b" / "autre-nom.pdf", b"meme contenu")
    meme_taille_a = ecrire(tmp_path / "a" / "x.pdf", b"123456")
    meme_taille_b = ecrire(tmp_path / "b" / "y.pdf", b"654321")
    seul = ecrire(tmp_path / "a" / "seul.pdf", b"unique et long")
    reste = mesure_domaines.retirer_pieces_communes({
        "personnel": [commune_a, meme_taille_a, seul],
        "professionnel": [tmp_path / "b" / "autre-nom.pdf", meme_taille_b]})
    assert reste == {"personnel": [meme_taille_a, seul], "professionnel": [meme_taille_b]}


def test_le_tirage_est_reproductible_et_borne():
    candidats = [f"d{i}" for i in range(20)]
    assert mesure_domaines.tirer(candidats, 5, 1) == mesure_domaines.tirer(list(reversed(candidats)), 5, 1)
    assert mesure_domaines.tirer(candidats, 5, 1) != mesure_domaines.tirer(candidats, 5, 2)
    assert len(mesure_domaines.tirer(candidats, 5, 1)) == 5
    assert mesure_domaines.tirer(candidats[:2], 5, 1) == candidats[:2]


def test_le_consensus_et_sa_confiance():
    assert mesure_domaines.consensus(["personnel"] * 4) == ("personnel", 1.0)
    assert mesure_domaines.consensus(["personnel", "personnel", "professionnel", "mixte"]) == ("personnel", 0.5)
    assert mesure_domaines.consensus(["personnel", "professionnel"]) == ("incertain", 0.5)


def test_le_seuil_est_la_plus_petite_valeur_sous_le_plafond():
    observations = [("personnel", "personnel", 1.0)] * 60 + [("professionnel", "personnel", 0.5)] * 2 + [("personnel", "personnel", 0.5)] * 2
    courbe, seuil = mesure_domaines.courbe_seuil(observations, 0.02)
    assert seuil == 1.0
    assert [ligne["seuil"] for ligne in courbe] == [0.5, 1.0]
    assert courbe[0]["retenus"] == 64 and courbe[0]["erreurs"] == 2
    assert mesure_domaines.courbe_seuil(observations, 0.05)[1] == 0.5
    assert mesure_domaines.courbe_seuil([("personnel", "professionnel", 1.0)], 0.02)[1] is None


def test_un_mixte_ou_un_incertain_n_est_pas_une_erreur():
    courbe, seuil = mesure_domaines.courbe_seuil([("personnel", "mixte", 1.0), ("personnel", "incertain", 1.0)], 0.02)
    assert seuil is None and courbe[0]["retenus"] == 0


def test_la_borne_de_wilson_encadre_le_taux():
    assert mesure_domaines.borne_haute_wilson(0, 0) is None
    borne = mesure_domaines.borne_haute_wilson(0, 60)
    assert 0.05 < borne < 0.07
    assert mesure_domaines.borne_haute_wilson(60, 60) == pytest.approx(1.0)


def test_la_matrice_compte_les_verdicts_par_etiquette():
    matrice = mesure_domaines.matrice_confusion([("personnel", "personnel"), ("personnel", "mixte"), ("professionnel", "echec_extraction")])
    assert matrice["personnel"]["personnel"] == 1 and matrice["personnel"]["mixte"] == 1
    assert matrice["professionnel"]["echec_extraction"] == 1 and matrice["professionnel"]["personnel"] == 0


@pytest.fixture
def banc(tmp_path, monkeypatch):
    """Deux coffres factices ; le texte de chaque PDF est rendu par un faux `pdftotext`."""
    textes = {}
    for nom, texte in (("p1", TEXTE_PERSONNEL), ("p2", TEXTE_PERSONNEL), ("p3", TEXTE_PERSONNEL),
                       ("q1", TEXTE_PROFESSIONNEL), ("q2", TEXTE_PROFESSIONNEL)):
        coffre = "a" if nom.startswith("p") else "b"
        chemin = ecrire(tmp_path / coffre / "R" / f"{nom}.pdf", nom.encode())
        textes[str(chemin)] = (texte + " ") * 2

    def pdftotext(commande, capture_output, timeout):
        return SimpleNamespace(returncode=0, stdout=textes[commande[2]].encode())

    def modele(url, nom, consigne, images, delai, keep_alive, format=None, options=None):
        if "verdict" in format["properties"]:
            return json.dumps({"verdict": "administratif", "objet": "courrier factice"})
        personnel = "CAF de l'Exemple" in consigne
        if nom == "faux":
            return json.dumps(REPONSE_FAUSSE if personnel else REPONSE_PROFESSIONNELLE)
        return json.dumps(REPONSE_PERSONNELLE if personnel else REPONSE_PROFESSIONNELLE)

    monkeypatch.setattr(modeles, "lister_modeles_installes", lambda url, delai: ["ocr", "tri", "bon", "faux"])
    fichier = tmp_path / "config.json"
    fichier.write_text(json.dumps(configuration(tmp_path / "a", tmp_path / "b")), encoding="utf-8")
    return SimpleNamespace(fichier=fichier, pdftotext=pdftotext, modele=modele, racine=tmp_path)


def lancer(banc, *arguments):
    sortie = io.StringIO()
    code = mesure_domaines.main(["--configuration", str(banc.fichier), *arguments], generer=banc.modele,
                                executer=banc.pdftotext, sortie=sortie)
    return code, sortie.getvalue()


def test_une_execution_a_blanc_rend_les_agregats(banc, capsys):
    code, sortie = lancer(banc, "--a-blanc")
    assert code == 0
    agregats = json.loads(sortie)
    assert agregats["echantillon"] == {"personnel": 3, "professionnel": 2}
    assert agregats["extraction"]["couche_texte"]["documents"] == 5
    assert agregats["classification"]["bon"]["erreurs"] == 0
    assert agregats["classification"]["bon"]["matrice"]["personnel"]["personnel"] == 3
    assert agregats["classification"]["faux"]["taux_erreur_domaine"] == 0.6
    assert agregats["preferences"]["classification"] == ["bon", "faux"]
    assert agregats["modeles"] == {"ocr": "ocr", "tri_rapide": ["tri"], "classification": ["bon", "faux"]}
    consensus = agregats["consensus"]
    assert consensus["matrice"]["personnel"]["incertain"] == 3 and consensus["matrice"]["professionnel"]["professionnel"] == 2
    assert consensus["seuil_confiance"] == 0.5 and consensus["verdicts_retenus"] == 2 and consensus["erreurs_retenues"] == 0
    assert "tri" in agregats["tri_rapide"] and agregats["tri_rapide"]["tri"]["documents"] == 5
    assert "extraction" in capsys.readouterr().err


def test_la_sortie_ne_contient_ni_chemin_ni_nom_ni_texte(banc):
    code, sortie = lancer(banc, "--a-blanc")
    assert code == 0
    for interdit in (str(banc.racine), "p1", "q2", ".pdf", "Personne1", "Atelier Exemple", "SIRET", "allocation",
                     *CATEGORIES):
        assert interdit not in sortie


def test_un_seul_modele_donne_confiance_pleine(banc):
    code, sortie = lancer(banc, "--a-blanc", "--classification", "bon")
    agregats = json.loads(sortie)
    assert code == 0 and agregats["consensus"]["seuil_confiance"] == 1.0
    assert agregats["consensus"]["verdicts_retenus"] == 5 and agregats["consensus"]["erreurs_retenues"] == 0


def test_un_coffre_non_prouve_arrete_avant_toute_lecture(banc, capsys):
    code, sortie = lancer(banc)
    assert code == 2 and sortie == ""
    assert "coffre non prouvé" in capsys.readouterr().err


def test_une_cle_absente_arrete_avec_le_code_1(banc, capsys):
    configuration_lue = json.loads(banc.fichier.read_text(encoding="utf-8"))
    del configuration_lue["mesure"]["graine"]
    banc.fichier.write_text(json.dumps(configuration_lue), encoding="utf-8")
    code, sortie = lancer(banc, "--a-blanc")
    assert code == 1 and sortie == ""
    assert "mesure.graine" in capsys.readouterr().err


def test_un_role_sans_modele_installe_arrete_avec_le_code_3(banc, monkeypatch, capsys):
    monkeypatch.setattr(modeles, "lister_modeles_installes", lambda url, delai: ["ocr", "tri"])
    code, sortie = lancer(banc, "--a-blanc")
    assert code == 3 and sortie == ""
    assert "classification" in capsys.readouterr().err


def test_l_accord_sur_la_categorie_compte_unanimite_majorite_et_accord_par_modele():
    accord = mesure_domaines.accord_categorie({
        "a": ["X", "X", "X", None], "b": ["X", "X", "Y", None], "c": ["X", "Y", "Z", "Z"]})
    assert accord["documents"] == 4
    assert accord["taux_unanimite"] == 0.25
    assert accord["taux_majorite"] == 0.5
    assert accord["accord_avec_majorite"] == {"a": 1.0, "b": 1.0, "c": 0.5}


def test_une_categorie_a_egalite_n_a_pas_de_majorite():
    accord = mesure_domaines.accord_categorie({"a": ["X"], "b": ["Y"]})
    assert accord["taux_majorite"] == 0.0 and accord["accord_avec_majorite"] == {"a": None, "b": None}


def test_le_sous_ensemble_retenu_est_le_plus_petit_d_au_moins_deux_modeles_sans_erreur():
    def ligne(modeles, retenus, erreurs, unanimite, duree):
        return {"modeles": modeles, "verdicts_retenus": retenus, "erreurs_retenues": erreurs,
                "taux_unanimite_categorie": unanimite, "duree_moyenne_document_s": duree}
    candidats = [ligne(["a"], 11, 0, 1.0, 5), ligne(["a", "b"], 11, 0, 0.7, 20), ligne(["a", "c"], 11, 0, 0.8, 22),
                 ligne(["b", "c"], 9, 0, 0.9, 10), ligne(["a", "d"], 11, 1, 0.9, 10), ligne(["a", "b", "c"], 11, 0, 0.6, 30)]
    assert mesure_domaines.sous_ensemble_retenu(candidats, candidats[5])["modeles"] == ["a", "b"]
    assert mesure_domaines.sous_ensemble_retenu(candidats[:1], candidats[0]) is None


def test_les_sous_ensembles_rendent_verdicts_retenus_et_duree(banc):
    code, sortie = lancer(banc, "--a-blanc")
    agregats = json.loads(sortie)
    assert code == 0
    par_modeles = {tuple(ligne["modeles"]): ligne for ligne in agregats["sous_ensembles"]}
    assert set(par_modeles) == {("bon",), ("faux",), ("bon", "faux")}
    assert par_modeles[("bon",)]["erreurs_retenues"] == 0 and par_modeles[("bon",)]["verdicts_retenus"] == 5
    assert agregats["accord_categorie"]["taux_unanimite"] == 1.0
    assert agregats["sous_ensemble_retenu"] is None or len(agregats["sous_ensemble_retenu"]["modeles"]) >= 2


def lancer_sans_option(banc, *arguments):
    sortie = io.StringIO()
    code = mesure_domaines.main(list(arguments), generer=banc.modele, executer=banc.pdftotext, sortie=sortie)
    return code, sortie.getvalue()


def test_la_mesure_suit_la_recherche_de_la_configuration_variable_puis_xdg_puis_le_module(banc, monkeypatch, tmp_path_factory):
    monkeypatch.setattr(mesure_domaines, "CHEMIN_CONFIG", banc.racine / "absente.json")
    code, _ = lancer_sans_option(banc, "--a-blanc")
    assert code == 1
    xdg = tmp_path_factory.mktemp("xdg-mesure")
    monkeypatch.setenv("XDG_CONFIG_HOME", str(xdg))
    (xdg / "dibab").mkdir()
    (xdg / "dibab" / "config.json").write_text(banc.fichier.read_text(encoding="utf-8"), encoding="utf-8")
    assert lancer_sans_option(banc, "--a-blanc")[0] == 0
    (xdg / "dibab" / "config.json").unlink()
    monkeypatch.setenv("DIBAB_CONFIG", str(banc.fichier))
    assert lancer_sans_option(banc, "--a-blanc")[0] == 0
    monkeypatch.delenv("DIBAB_CONFIG")
    monkeypatch.setattr(mesure_domaines, "CHEMIN_CONFIG", banc.fichier)
    assert lancer_sans_option(banc, "--a-blanc")[0] == 0


def test_la_mesure_n_essaie_pas_les_autres_emplacements_quand_la_variable_designe_un_fichier_absent(banc, monkeypatch, capsys):
    monkeypatch.setattr(mesure_domaines, "CHEMIN_CONFIG", banc.fichier)
    monkeypatch.setenv("DIBAB_CONFIG", str(banc.racine / "absent.json"))
    assert lancer_sans_option(banc, "--a-blanc")[0] == 1
    assert "DIBAB_CONFIG" in capsys.readouterr().err
