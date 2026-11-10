"""Un dry-run puis un --execute sur un lot factice mixte, par la ligne de commande : arborescence attendue, rien d'écrasé."""

import json
import socket
from datetime import datetime
from functools import partial

import pytest

import dibab
from modules import classification, verrou
from modules.extraction import Extraction
from tests.textes_factices import CATEGORIES, CONFIG_CLASSEMENT, EMETTEURS_CONNUS, PERSONNES, TEXTES

TEXTE_IDENTITE = TEXTES[0]["texte"] + " Pièce d'identité."
REPONSE_IDENTITE = {**TEXTES[0]["reponse"], "categorie": "Identité"}

LOT = {
    "perso.pdf": TEXTES[0]["texte"],
    "perso-copie.pdf": TEXTES[0]["texte"],
    "pro.pdf": TEXTES[2]["texte"],
    "mixte.pdf": TEXTES[4]["texte"],
    "incertain-pro.pdf": TEXTES[6]["texte"],
    "incertain.pdf": TEXTES[8]["texte"],
    "loisir.pdf": TEXTES[10]["texte"],
    "identite.pdf": TEXTE_IDENTITE,
}


def faux_modeles(url, modele, consigne, images, delai, keep_alive, format=None, options=None):
    if TEXTE_IDENTITE in consigne:
        return json.dumps({"verdict": "administratif", "objet": "courrier factice"} if "verdict" in format["properties"] else REPONSE_IDENTITE)
    document = next(t for t in reversed(TEXTES) if t["texte"] in consigne)
    return json.dumps({"verdict": document["tri"], "objet": document["objet"]} if "verdict" in format["properties"] else document["reponse"])


@pytest.fixture
def banc(tmp_path, monkeypatch):
    source = tmp_path / "source"
    for nom in ("coffre-a", "coffre-b", "source"):
        (tmp_path / nom).mkdir()
    for nom, texte in LOT.items():
        (source / nom).write_text(texte, encoding="utf-8")
    configuration = {
        **CONFIG_CLASSEMENT,
        "destinations": {
            "personnel": {"racine": str(tmp_path / "coffre-a"), "sous_repertoire_classement": "Rangement", "sous_repertoire_a_verifier": "Tri"},
            "professionnel": {"racine": str(tmp_path / "coffre-b"), "sous_repertoire_classement": "Classement", "sous_repertoire_a_verifier": "Tri"},
        },
        "pieces_communes": ["Identité"],
        "suivi": {"fichier_date": str(tmp_path / "coffre-a" / "logs" / "dernier_scan.json"),
                  "journal": str(tmp_path / "coffre-a" / "logs" / "journal.jsonl"),
                  "sessions": str(tmp_path / "coffre-a" / "logs" / "sessions"),
                  "rotation": {"journal_taille_max_mo": 20, "journal_archives_max": 5, "sessions_max": 100}},
        "ollama": {"url": "http://x", "seuil_confiance": 0.4, "keep_alive_entre_pages": "2m",
                   "roles": {"ocr": ["m"], "tri_rapide": ["m"], "classification": ["m1", "m2"]}},
        "classification": {"temperature": 0, "num_ctx": 8192, "caracteres_max_prompt": 12000, "keep_alive_entre_documents": "2m",
                           "longueur_max_champ": 80, "longueur_max_citation": 120, "marqueurs_mentions": ["TVA", "SIRET"]},
        "categories": CATEGORIES, "personnes": PERSONNES, "emetteurs_connus": EMETTEURS_CONNUS,
        "nommage": {"format": "{date}_{emetteur}_{categorie}{ext}", "date_format": "%Y-%m-%d", "date_inconnue_prefixe": "~",
                    "emetteur_inconnu": "Inconnu", "espaces_vers": "-", "prefixe_a_verifier": "[AV]", "suffixe_collision": "_{n}"},
        "extraction": {"seuil_caracteres_alphanumeriques": 200, "pages_ocr": 3, "resolution_ocr": 200, "taille_max_texte": 20000,
                       "repertoire_temporaire": "/dev/shm", "timeout_outils_secondes": 60, "consigne_ocr": "Transcris."},
        "extensions_cibles": [".pdf"],
        "sources_locales": [{"id": "source", "chemin": str(source)}],
    }
    chemin_config = tmp_path / "config.json"
    chemin_config.write_text(json.dumps(configuration), encoding="utf-8")
    monkeypatch.setattr(dibab, "CHEMIN_CONFIG", chemin_config)
    monkeypatch.setattr(dibab.mod_modeles, "resoudre_modeles", lambda _: {"ocr": "m", "tri_rapide": "m", "classification": "m1"})
    monkeypatch.setattr(dibab.mod_modeles, "modeles_installes_du_role", lambda *_: ["m1", "m2"])
    monkeypatch.setattr(dibab.mod_extraction, "extraire", lambda chemin, *_, **__: Extraction(
        chemin.read_text(encoding="utf-8"), "couche_texte", 999, 1, None, 0.0))
    monkeypatch.setattr(dibab.mod_cascade, "executer", partial(dibab.mod_cascade.executer, generer=faux_modeles))
    monkeypatch.setattr(dibab.mod_coffres, "type_systeme_fichiers", lambda racine, executer=None: "fuse.gocryptfs")
    return tmp_path, chemin_config


def lancer(monkeypatch, *arguments):
    monkeypatch.setattr("sys.argv", ["dibab", *arguments])
    return dibab.main()


def arbre(racine, sans_logs=True):
    return sorted(str(p.relative_to(racine)) for p in racine.rglob("*")
                  if p.is_file() and not (sans_logs and "logs" in p.relative_to(racine).parts))


def test_dry_run_puis_execute_sur_un_lot_mixte(banc, monkeypatch, capsys):
    racine, _ = banc
    avant = arbre(racine / "source")
    assert lancer(monkeypatch, "--dry-run") == 0
    sortie = capsys.readouterr().out
    assert arbre(racine / "source") == avant and arbre(racine / "coffre-a") == arbre(racine / "coffre-b") == []
    assert "accord 2/2" in sortie and "confiance" not in sortie and sortie.count("(non déplacé)") == 3
    assert sortie.count("motif : ") == 3 and sortie.count("      objet : ") == len(LOT)

    assert lancer(monkeypatch, "--execute") == 0
    capsys.readouterr()
    assert arbre(racine / "source") == ["loisir.pdf"]
    perso, pro = arbre(racine / "coffre-a"), arbre(racine / "coffre-b")
    assert sum(chemin.startswith("Rangement/Personne1/2026/") and chemin.endswith("_CAF.pdf") for chemin in perso) == 1
    assert sum(chemin.startswith("doublon/") for chemin in perso) == 1
    assert sum(chemin.startswith("Rangement/Personne1/2026/") and chemin.endswith("_Identité.pdf") for chemin in perso) == 1
    assert sum(chemin.startswith("Tri/[AV]") for chemin in perso) == 1
    assert sum(chemin.startswith("Classement/2026/Factures/") for chemin in pro) == 1
    assert sum(chemin.startswith("Classement/2026/Identité/") for chemin in pro) == 1
    assert sum(chemin.startswith("Tri/[AV]") for chemin in pro) == 2
    assert len(perso) == 4 and len(pro) == 4


def test_la_piece_commune_a_la_meme_empreinte_dans_les_deux_coffres(banc, monkeypatch):
    racine, _ = banc
    lancer(monkeypatch, "--execute")
    copies = [p for p in racine.rglob("*Identité.pdf")]
    assert len(copies) == 2 and {p.read_bytes() for p in copies} == {TEXTE_IDENTITE.encode("utf-8")}


def test_un_second_execute_ne_ecrase_rien_et_classe_les_doublons(banc, monkeypatch):
    racine, _ = banc
    lancer(monkeypatch, "--execute")
    premier = {p: p.read_bytes() for p in racine.rglob("*") if p.is_file() and "logs" not in p.parts}
    for nom, texte in LOT.items():
        (racine / "source" / nom).write_text(texte, encoding="utf-8")
    lancer(monkeypatch, "--execute")
    second = {p: p.read_bytes() for p in racine.rglob("*") if p.is_file() and "logs" not in p.parts}
    assert all(second[p] == contenu for p, contenu in premier.items() if p in second)
    assert set(premier) <= set(second)


def test_execute_journalise_chaque_deplacement_sans_texte(banc, monkeypatch):
    racine, _ = banc
    lancer(monkeypatch, "--execute")
    brut = next((racine / "coffre-a" / "logs" / "sessions").glob("session_*.jsonl")).read_text(encoding="utf-8")
    evenements = [json.loads(ligne) for ligne in brut.splitlines()]
    deplacements = [e for e in evenements if e["evenement"] == "deplacement"]
    assert len(deplacements) == 7 and all(e["empreinte"] and e["dry_run"] is False for e in deplacements)
    assert TEXTES[0]["reponse"]["destinataire"] not in brut


def test_execute_coffre_ferme_ne_touche_a_rien(banc, monkeypatch, capsys):
    racine, _ = banc
    monkeypatch.setattr(dibab.mod_coffres, "type_systeme_fichiers", lambda racine, executer=None: "ext4")
    avant = arbre(racine / "source")
    with pytest.raises(SystemExit) as sortie:
        lancer(monkeypatch, "--execute")
    assert sortie.value.code == 2
    assert arbre(racine / "source") == avant and arbre(racine / "coffre-a", False) == arbre(racine / "coffre-b", False) == []
    assert not (racine / "coffre-a" / "logs").exists()


def test_inventaire_coffre_ferme_ne_touche_a_rien(banc, monkeypatch):
    racine, _ = banc
    monkeypatch.setattr(dibab.mod_coffres, "type_systeme_fichiers", lambda racine, executer=None: "ext4")
    with pytest.raises(SystemExit) as sortie:
        lancer(monkeypatch, "--inventaire")
    assert sortie.value.code == 2
    assert not (racine / "coffre-a" / "logs").exists()


def test_inventaire_par_la_ligne_de_commande(banc, monkeypatch, capsys):
    racine, _ = banc
    lancer(monkeypatch, "--execute")
    capsys.readouterr()
    sessions = lambda d: [p for p in (racine / d / "logs" / "sessions").glob("*")]  # noqa: E731
    avant = {d: dibab.mod_inventaire.empreinte_arbre(racine / d, ignorer=sessions(d)) for d in ("coffre-a", "coffre-b")}
    assert lancer(monkeypatch, "--inventaire") == 0
    plans = sorted((racine / "coffre-a" / "logs").glob("inventaire_*.json")) + sorted((racine / "coffre-b" / "logs").glob("inventaire_*.json"))
    assert len(plans) == 2
    # Le journal de session est le seul autre écrit de la commande : il vit déjà dans logs/sessions.
    ignores = plans + [p for d in ("coffre-a", "coffre-b") for p in (racine / d / "logs" / "sessions").glob("*")]
    apres = {d: dibab.mod_inventaire.empreinte_arbre(racine / d, ignorer=ignores) for d in ("coffre-a", "coffre-b")}
    assert avant == apres
    assert "plan écrit" in capsys.readouterr().out


def test_execute_refuse_hors_des_machines_autorisees(banc, monkeypatch):
    racine, chemin_config = banc
    configuration = json.loads(chemin_config.read_text())
    configuration["executer_sur"] = ["une-autre-machine"]
    chemin_config.write_text(json.dumps(configuration))
    assert socket.gethostname() != "une-autre-machine"
    with pytest.raises(SystemExit) as sortie:
        lancer(monkeypatch, "--execute")
    assert sortie.value.code == 4 and arbre(racine / "coffre-a", False) == []


def test_execute_refuse_quand_un_autre_tient_le_verrou(banc, monkeypatch):
    racine, _ = banc
    avant = arbre(racine / "source")
    with verrou.verrou(racine / "coffre-a" / "logs" / "dibab.verrou"):
        assert lancer(monkeypatch, "--execute") == 5
    assert arbre(racine / "source") == avant


def test_un_echec_de_deplacement_laisse_le_document_et_n_avance_pas_la_date_du_scan(banc, monkeypatch):
    racine, _ = banc

    def copie_en_panne(origine, destination):
        raise OSError("coffre plein")

    monkeypatch.setattr(dibab.mod_deplacement, "deplacer", partial(dibab.mod_deplacement.deplacer, copier=copie_en_panne))
    assert lancer(monkeypatch, "--execute") == 1
    assert len(arbre(racine / "source")) == len(LOT)
    assert "source" not in json.loads((racine / "coffre-a" / "logs" / "dernier_scan.json").read_text())


def sans_cles_de_chemin(chemin_config):
    configuration = json.loads(chemin_config.read_text())
    for cle in ("fichier_date", "journal", "sessions", "logs_systeme"):
        configuration["suivi"].pop(cle, None)
    chemin_config.write_text(json.dumps(configuration))


def test_execute_sans_cles_de_chemin_ecrit_l_etat_sous_xdg_state_home_en_700_et_600(banc, monkeypatch, tmp_path_factory):
    racine, chemin_config = banc
    etat = tmp_path_factory.mktemp("etat") / "xdg"
    monkeypatch.setenv("XDG_STATE_HOME", str(etat))
    sans_cles_de_chemin(chemin_config)
    assert lancer(monkeypatch, "--execute") == 0
    dossier = etat / "dibab"
    assert not (racine / "coffre-a" / "logs").exists()
    assert sorted(p.name for p in dossier.iterdir() if p.is_file()) == ["dernier_scan.json", "journal.jsonl"]
    sessions = [p for p in (dossier / "sessions").iterdir()]
    assert any(p.name.startswith("session_") for p in sessions)
    assert oct(dossier.stat().st_mode & 0o777) == oct(0o700) and oct((dossier / "sessions").stat().st_mode & 0o777) == oct(0o700)
    assert {oct(p.stat().st_mode & 0o777) for p in dossier.rglob("*") if p.is_file()} == {oct(0o600)}


def test_une_cle_de_chemin_donnee_l_emporte_sur_le_defaut(banc, monkeypatch, tmp_path_factory):
    racine, _ = banc
    etat = tmp_path_factory.mktemp("etat") / "xdg"
    monkeypatch.setenv("XDG_STATE_HOME", str(etat))
    assert lancer(monkeypatch, "--execute") == 0
    assert (racine / "coffre-a" / "logs" / "journal.jsonl").exists() and not etat.exists()


def test_execute_sans_modele_installe_rend_3(banc, monkeypatch):
    racine, _ = banc

    def aucun_modele(_):
        raise dibab.mod_modeles.ModeleIndisponible("Aucun modèle installé pour le rôle : ocr.")

    monkeypatch.setattr(dibab.mod_modeles, "resoudre_modeles", aucun_modele)
    with pytest.raises(SystemExit) as sortie:
        lancer(monkeypatch, "--execute")
    assert sortie.value.code == 3 and arbre(racine / "source") != []


def test_l_en_tete_de_session_nomme_la_configuration_lue(banc, monkeypatch, capsys):
    _, chemin_config = banc
    assert lancer(monkeypatch, "--dry-run") == 0
    assert f"Configuration      : {chemin_config}" in capsys.readouterr().out


def test_la_configuration_xdg_est_trouvee_avant_celle_du_script(banc, monkeypatch, capsys, tmp_path_factory):
    _, chemin_config = banc
    xdg = tmp_path_factory.mktemp("xdg-config-essai")
    monkeypatch.setenv("XDG_CONFIG_HOME", str(xdg))
    (xdg / "dibab").mkdir()
    copie = xdg / "dibab" / "config.json"
    copie.write_text(chemin_config.read_text())
    assert lancer(monkeypatch, "--dry-run") == 0
    assert f"Configuration      : {copie}" in capsys.readouterr().out


def test_avec_format_a_verifier_le_nom_porte_l_objet_et_le_nom_d_origine(banc, monkeypatch, capsys):
    racine, chemin_config = banc
    configuration = json.loads(chemin_config.read_text(encoding="utf-8"))
    configuration["nommage"]["format_a_verifier"] = "{date}_{emetteur}_{objet}_{origine}{ext}"
    chemin_config.write_text(json.dumps(configuration), encoding="utf-8")
    assert lancer(monkeypatch, "--dry-run") == 0
    sortie = capsys.readouterr().out
    assert "Tri/[AV]accusé-de-réception-d'un-courrier_incertain.pdf (non déplacé)" in sortie
    assert "Tri/[AV]2026-03-15_DGFiP_avis-d'impôt-sur-le-revenu_mixte.pdf (non déplacé)" in sortie
    assert "Inconnu" not in "".join(ligne for ligne in sortie.splitlines() if "[AV]" in ligne)
    assert lancer(monkeypatch, "--execute") == 0
    assert "Tri/[AV]accusé-de-réception-d'un-courrier_incertain.pdf" in arbre(racine / "coffre-a")
    assert "Tri/[AV]conditions-générales-de-vente_incertain-pro.pdf" in arbre(racine / "coffre-b")
