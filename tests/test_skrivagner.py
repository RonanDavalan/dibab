"""Tests du point d'entrée : preuve des coffres et routage en dry-run, sur un arbre factice."""

import json

import pytest

import skrivagner
from tests.textes_factices import CONFIG_CLASSEMENT

CAS = {
    "perso.pdf": {"administratif": True, "domaine": "personnel", "categorie": "CAF", "emetteur": "Organisme"},
    "pro.pdf": {"administratif": True, "domaine": "professionnel", "categorie": "Factures", "emetteur": "Client"},
    "mixte.pdf": {"administratif": True, "domaine": "mixte", "categorie": "Impôts", "emetteur": "Fisc"},
    "incertain_pro.pdf": {"administratif": True, "domaine": "incertain", "categorie": "Factures",
                          "signaux": [{"domaine": "professionnel", "libelle": "SIRET"}]},
    "incertain.pdf": {"administratif": True, "domaine": "incertain", "categorie": "Factures"},
    "loisir.pdf": {"administratif": False, "domaine": "personnel", "categorie": "Loisir"},
    "identite.pdf": {"administratif": True, "domaine": "personnel", "categorie": "Identité",
                     "emetteur": "Prefecture"},
}


@pytest.fixture
def banc(tmp_path, monkeypatch):
    for nom in ("coffre-a", "coffre-b", "source"):
        (tmp_path / nom).mkdir()
    for nom in CAS:
        (tmp_path / "source" / nom).write_bytes(b"factice " + nom.encode())
    configuration = {
        **CONFIG_CLASSEMENT,
        "destinations": {
            "personnel": {"racine": str(tmp_path / "coffre-a"), "sous_repertoire_classement": "Rangement",
                          "sous_repertoire_a_verifier": "Tri"},
            "professionnel": {"racine": str(tmp_path / "coffre-b"), "sous_repertoire_classement": "Dossiers",
                              "sous_repertoire_a_verifier": "Tri"},
        },
        "pieces_communes": ["Identité"],
        "suivi": {"fichier_date": str(tmp_path / "coffre-a" / "logs" / "dernier_scan.json"),
                  "sessions": str(tmp_path / "coffre-a" / "logs" / "sessions")},
        "nommage": {"format": "{date}_{emetteur}_{categorie}{ext}", "date_format": "%Y-%m-%d",
                    "date_inconnue_prefixe": "~", "emetteur_inconnu": "Inconnu", "espaces_vers": "-",
                    "prefixe_a_verifier": "[À_VÉRIFIER]", "suffixe_collision": "_{n}"},
        "ollama": {"url": "http://x", "roles": {"ocr": ["m"], "tri_rapide": ["m"], "classification": ["m"]}, "keep_alive_entre_pages": "2m"},
        "classification": {"temperature": 0, "num_ctx": 8192, "caracteres_max_prompt": 12000, "keep_alive_entre_documents": "2m", "longueur_max_champ": 80, "longueur_max_citation": 120, "marqueurs_mentions": ["TVA", "SIRET"]},
        "categories": ["Factures"], "personnes": ["Personne1"],
        "extraction": {"seuil_caracteres_alphanumeriques": 200, "pages_ocr": 3, "resolution_ocr": 200,
                       "taille_max_texte": 20000, "repertoire_temporaire": "/dev/shm",
                       "timeout_outils_secondes": 60, "consigne_ocr": "Transcris."},
        "extensions_cibles": [".pdf"],
        "sources_locales": [{"id": "source", "chemin": str(tmp_path / "source")}],
    }
    chemin_config = tmp_path / "config.json"
    chemin_config.write_text(json.dumps(configuration), encoding="utf-8")
    verdicts = tmp_path / "verdicts.json"
    verdicts.write_text(json.dumps(CAS), encoding="utf-8")
    monkeypatch.setattr(skrivagner, "CHEMIN_CONFIG", chemin_config)
    monkeypatch.setattr(skrivagner.mod_modeles, "resoudre_modeles", lambda _: {"ocr": "modele-factice", "tri_rapide": "modele-factice", "classification": "modele-factice"})
    monkeypatch.setattr(skrivagner.mod_modeles, "modeles_installes_du_role", lambda *_: ["modele-factice"])
    monkeypatch.setattr(skrivagner.mod_extraction, "extraire", lambda *_, **__: skrivagner.mod_extraction.Extraction(
        "", "echec", 0, 0, None, 0.0, "extraction simulée"))
    return tmp_path, verdicts


def simuler_type(monkeypatch, type_rendu):
    monkeypatch.setattr(skrivagner.mod_coffres, "type_systeme_fichiers", lambda racine, executer=None: type_rendu)


def lancer(monkeypatch, *arguments):
    monkeypatch.setattr("sys.argv", ["skrivagner", *arguments])
    return skrivagner.main()


def test_execute_coffre_ferme_s_arrete_code_2_sans_rien_toucher(banc, monkeypatch, capsys):
    racine, _ = banc
    simuler_type(monkeypatch, "ext4")
    avant = sorted(racine.rglob("*"))
    with pytest.raises(SystemExit) as sortie:
        lancer(monkeypatch, "--execute")
    assert sortie.value.code == 2
    assert "coffre personnel" in capsys.readouterr().err
    assert sorted(racine.rglob("*")) == avant


def test_execute_un_seul_coffre_ferme_s_arrete(banc, monkeypatch):
    racine, _ = banc
    monkeypatch.setattr(skrivagner.mod_coffres, "type_systeme_fichiers",
                        lambda r, executer=None: "fuse.gocryptfs" if str(r).endswith("coffre-a") else "ext4")
    with pytest.raises(SystemExit) as sortie:
        lancer(monkeypatch, "--execute")
    assert sortie.value.code == 2
    assert not (racine / "coffre-a" / "logs").exists()


def test_dry_run_coffre_ferme_signale_sans_bloquer_ni_ecrire(banc, monkeypatch, capsys):
    racine, verdicts = banc
    simuler_type(monkeypatch, "ext4")
    assert lancer(monkeypatch, "--dry-run", "--verdicts-simules", str(verdicts)) == 0
    sortie = capsys.readouterr().out
    assert sortie.count("[!] coffre non monté") == 2
    assert "non écrit" in sortie
    assert not (racine / "coffre-a" / "logs").exists()


def test_dry_run_affiche_la_destination_de_chaque_cas(banc, monkeypatch, capsys):
    racine, verdicts = banc
    simuler_type(monkeypatch, "fuse.gocryptfs")
    assert lancer(monkeypatch, "--dry-run", "--verdicts-simules", str(verdicts)) == 0
    sortie = capsys.readouterr().out
    a, b = racine / "coffre-a", racine / "coffre-b"
    attendus = [
        f"perso.pdf : domaine personnel\n      -> coffre personnel, classement : {a}/Rangement/",
        f"pro.pdf : domaine professionnel\n      -> coffre professionnel, classement : {b}/Dossiers/",
        f"mixte.pdf : domaine mixte\n      -> coffre professionnel, a_verifier : {b}/Tri/[À_VÉRIFIER]",
        f"incertain_pro.pdf : domaine incertain\n      -> coffre professionnel, a_verifier : {b}/Tri/[À_VÉRIFIER]",
        f"incertain.pdf : domaine incertain\n      -> coffre personnel, a_verifier : {a}/Tri/[À_VÉRIFIER]",
        "loisir.pdf : non administratif, ne bouge pas",
        f"-> coffre personnel, classement : {a}/Rangement/",
    ]
    for attendu in attendus:
        assert attendu in sortie, attendu
    identite = sortie.split("Routage simulé")[1].split("- identite.pdf")[1]
    assert f"coffre personnel, classement : {a}/Rangement/" in identite
    assert f"coffre professionnel, classement : {b}/Dossiers/" in identite
    assert not list((racine / "coffre-a").glob("Rangement")) and not (racine / "coffre-b" / "Dossiers").exists()
    sessions = list((racine / "coffre-a" / "logs" / "sessions").glob("session_*.jsonl"))
    assert len(sessions) == 1
    evenements = [json.loads(ligne)["evenement"] for ligne in sessions[0].read_text().splitlines()]
    assert evenements.count("routage_simule") == len(CAS)


def test_verdicts_simules_refuses_avec_execute(banc, monkeypatch):
    _, verdicts = banc
    with pytest.raises(SystemExit) as sortie:
        lancer(monkeypatch, "--execute", "--verdicts-simules", str(verdicts))
    assert sortie.value.code == 2


def test_configuration_sans_destinations(banc, monkeypatch):
    racine, _ = banc
    configuration = json.loads((racine / "config.json").read_text())
    del configuration["destinations"]
    (racine / "config.json").write_text(json.dumps(configuration))
    with pytest.raises(SystemExit) as sortie:
        lancer(monkeypatch, "--dry-run")
    assert sortie.value.code == 1
