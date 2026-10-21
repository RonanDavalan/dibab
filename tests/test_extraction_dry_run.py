"""Branchement de l'extraction derrière le scan : méthode affichée, jamais de texte au journal."""

import json
from functools import partial

import pytest

import skrivagner
from tests.textes_factices import CONFIG_CLASSEMENT
from tests.textes_factices import CATEGORIES, EMETTEURS_CONNUS, PERSONNES
from tests.test_extraction import FauxOllama, PARAMETRES, pdf_avec_couche_texte, pdf_sans_couche_texte, png_factice

MOT_SECRET = "Cormoran"


@pytest.fixture
def banc(tmp_path, monkeypatch):
    for nom in ("coffre-a", "coffre-b", "source"):
        (tmp_path / nom).mkdir()
    source = tmp_path / "source"
    pdf_avec_couche_texte(source / "texte.pdf", f"{MOT_SECRET} " * 60)
    pdf_sans_couche_texte(source / "scan.pdf")
    png_factice(source / "photo.png")
    configuration = {
        **CONFIG_CLASSEMENT,
        "destinations": {
            "personnel": {"racine": str(tmp_path / "coffre-a"), "sous_repertoire_classement": "R",
                          "sous_repertoire_a_verifier": "T"},
            "professionnel": {"racine": str(tmp_path / "coffre-b"), "sous_repertoire_classement": "D",
                              "sous_repertoire_a_verifier": "T"},
        },
        "pieces_communes": [],
        "suivi": {"fichier_date": str(tmp_path / "coffre-a" / "logs" / "dernier_scan.json"),
                  "journal": str(tmp_path / "coffre-a" / "logs" / "journal.jsonl"),
                  "sessions": str(tmp_path / "coffre-a" / "logs" / "sessions"),
                  "rotation": {"journal_taille_max_mo": 20, "journal_archives_max": 5, "sessions_max": 100}},
        "ollama": {"url": "http://x", "roles": {"ocr": ["m"], "tri_rapide": ["m"], "classification": ["m"]}, "keep_alive_entre_pages": "2m"},
        "classification": {"temperature": 0, "num_ctx": 8192, "caracteres_max_prompt": 12000, "keep_alive_entre_documents": "2m", "longueur_max_champ": 80, "longueur_max_citation": 120, "marqueurs_mentions": ["TVA", "SIRET"]},
        "categories": CATEGORIES, "personnes": PERSONNES, "emetteurs_connus": EMETTEURS_CONNUS,
        "nommage": {"format": "{date}_{emetteur}_{categorie}{ext}", "date_format": "%Y-%m-%d",
                    "date_inconnue_prefixe": "~", "emetteur_inconnu": "Inconnu", "espaces_vers": "-",
                    "prefixe_a_verifier": "[AV]", "suffixe_collision": "_{n}"},
        "extraction": {k: v for k, v in PARAMETRES.items()},
        "extensions_cibles": [".pdf", ".png"],
        "sources_locales": [{"id": "source", "chemin": str(source)}],
    }
    chemin_config = tmp_path / "config.json"
    chemin_config.write_text(json.dumps(configuration), encoding="utf-8")
    monkeypatch.setattr(skrivagner, "CHEMIN_CONFIG", chemin_config)
    monkeypatch.setattr(skrivagner.mod_modeles, "resoudre_modeles", lambda _: {"ocr": "modele-factice", "tri_rapide": "modele-factice", "classification": "modele-factice"})
    monkeypatch.setattr(skrivagner.mod_modeles, "modeles_installes_du_role", lambda *_: ["modele-factice"])
    monkeypatch.setattr(skrivagner.mod_coffres, "type_systeme_fichiers",
                        lambda racine, executer=None: "tmpfs" if str(racine) == "/dev/shm" else "fuse.gocryptfs")
    return tmp_path, chemin_config


def lancer(monkeypatch, *arguments):
    monkeypatch.setattr("sys.argv", ["skrivagner", *arguments])
    return skrivagner.main()


def brancher_faux_modele(monkeypatch, texte):
    faux = FauxOllama(texte)
    monkeypatch.setattr(skrivagner.mod_extraction, "extraire",
                        partial(skrivagner.mod_extraction.extraire, generer=faux))
    return faux


def test_dry_run_affiche_les_trois_methodes(banc, monkeypatch, capsys):
    brancher_faux_modele(monkeypatch, f"{MOT_SECRET} lu par OCR")
    assert lancer(monkeypatch, "--dry-run") == 0
    sortie = capsys.readouterr().out
    assert "texte.pdf : couche texte," in sortie
    assert "scan.pdf : OCR," in sortie and "photo.png : OCR," in sortie
    assert "modèle modele-factice" in sortie
    assert MOT_SECRET not in sortie


def test_le_journal_ne_contient_aucun_texte(banc, monkeypatch):
    racine, _ = banc
    brancher_faux_modele(monkeypatch, f"{MOT_SECRET} lu par OCR")
    lancer(monkeypatch, "--dry-run")
    journaux = list((racine / "coffre-a" / "logs" / "sessions").glob("session_*.jsonl"))
    assert len(journaux) == 1
    brut = journaux[0].read_text(encoding="utf-8")
    assert brut.count(MOT_SECRET) == 0
    extractions = [json.loads(ligne) for ligne in brut.splitlines() if '"extraction"' in ligne]
    assert sorted(e["methode"] for e in extractions) == ["couche_texte", "ocr", "ocr"]
    assert all({"caracteres", "pages", "modele", "duree_secondes"} <= e.keys() for e in extractions)


def test_execute_extrait_sans_jamais_ecrire_le_texte(banc, monkeypatch, capsys):
    racine, _ = banc
    brancher_faux_modele(monkeypatch, f"{MOT_SECRET} lu par OCR")
    lancer(monkeypatch, "--execute")
    assert MOT_SECRET not in capsys.readouterr().out
    brut = next((racine / "coffre-a" / "logs" / "sessions").glob("session_*.jsonl")).read_text(encoding="utf-8")
    assert brut.count(MOT_SECRET) == 0
    extractions = [json.loads(ligne) for ligne in brut.splitlines() if '"extraction"' in ligne]
    assert extractions and all(e["dry_run"] is False for e in extractions)


def test_configuration_sans_bloc_extraction(banc, monkeypatch, capsys):
    racine, chemin_config = banc
    configuration = json.loads(chemin_config.read_text())
    del configuration["extraction"]
    chemin_config.write_text(json.dumps(configuration))
    with pytest.raises(SystemExit) as sortie:
        lancer(monkeypatch, "--dry-run")
    assert sortie.value.code == 1
    assert "extraction.seuil_caracteres_alphanumeriques" in capsys.readouterr().err
    assert not (racine / "coffre-a" / "logs").exists()
