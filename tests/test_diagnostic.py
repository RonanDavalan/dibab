"""--diagnose : chaque vérification dans chacun de ses états, le bilan et le code de retour (spécification 28, décision 4)."""

import io
import json
import subprocess
import sys
from pathlib import Path

import pytest

import skrivagner
from modules import coffres, diagnostic, modeles

RACINE = Path(__file__).resolve().parent.parent
IDENTIFIANTS = ["python", "outil_pdftotext", "outil_pdftoppm", "outil_findmnt", "outil_ssh", "configuration",
                "emplacement_etat", "ollama", "modele_ocr", "modele_tri_rapide", "modele_classification",
                "destination_personnel", "destination_professionnel"]
INSTALLES = ["m-ocr:latest", "m-tri:latest", "m-classe-a:latest", "m-classe-b:latest"]


def tous_les_outils(nom):
    return f"/usr/bin/{nom}"


def jamais_appele(*_):
    raise AssertionError("Ollama n'aurait pas dû être interrogé")


def ollama_repond(url, delai):
    return INSTALLES


def ollama_muet(url, delai):
    raise modeles.ModeleIndisponible(f"Ollama ne répond pas à {url}/api/tags : refusé\n        Vérifier ollama.url.")


def coffre_monte(domaine, racine, acceptes=None):
    return coffres.EtatCoffre(domaine, Path(racine), True)


def coffre_ferme(domaine, racine, acceptes=None):
    return coffres.EtatCoffre(domaine, Path(racine), False, "coffre non monté (type ext4, attendu fuse.gocryptfs)")


def aucune_cle_absente(configuration):
    return []


@pytest.fixture
def aire(tmp_path):
    """Un domicile jetable et une configuration valide dont les coffres, l'état et le journal sont dans l'aire."""
    configuration = {
        "destinations": {"personnel": {"racine": str(tmp_path / "coffre-a"), "systemes_fichiers_acceptes": ["fuse.gocryptfs"]},
                         "professionnel": {"racine": str(tmp_path / "coffre-b")}},
        "suivi": {"fichier_date": str(tmp_path / "coffre-a" / "logs" / "dernier_scan.json"),
                  "journal": str(tmp_path / "coffre-a" / "logs" / "journal.jsonl"),
                  "sessions": str(tmp_path / "coffre-a" / "logs" / "sessions")},
        "ollama": {"url": "http://ollama.exemple:11434", "timeout_secondes": 5,
                   "roles": {"ocr": ["m-ocr"], "tri_rapide": ["absent", "m-tri"], "classification": ["m-classe-a", "m-classe-b", "absent"]}},
    }
    chemin = tmp_path / "config.json"
    chemin.write_text(json.dumps(configuration), encoding="utf-8")
    return {"chemin": chemin, "configuration": configuration, "environ": {"HOME": str(tmp_path / "maison")}, "script": tmp_path / "script.json"}


def jouer(aire, option="defaut", lister=ollama_repond, which=tous_les_outils, coffre=coffre_monte, cles=aucune_cle_absente,
          version=(3, 12, 11), environ=None):
    option = aire["chemin"] if option == "defaut" else option
    return {v.identifiant: v for v in diagnostic.diagnostiquer(
        option, aire["environ"] if environ is None else environ, aire["script"], cles, which=which, version_python=version,
        lister=lister, verifier_coffre=coffre)}


def etats(resultats):
    return {identifiant: v.etat for identifiant, v in resultats.items()}


def test_une_configuration_valide_donne_ok_partout_sauf_l_etat_hors_coffre(aire):
    resultats = jouer(aire)
    assert list(resultats) == IDENTIFIANTS
    assert set(etats(resultats).values()) == {"OK"}
    assert resultats["modele_classification"].message == "m-classe-a:latest, 2 modèle(s) au consensus"
    assert resultats["modele_tri_rapide"].message == "m-tri:latest"
    assert resultats["configuration"].message == str(aire["chemin"])


@pytest.mark.parametrize("version, attendu", [((3, 10, 0), "OK"), ((3, 9, 18), "ÉCHEC")])
def test_python(aire, version, attendu):
    assert jouer(aire, version=version)["python"].etat == attendu


@pytest.mark.parametrize("outil", ["pdftotext", "pdftoppm", "findmnt"])
def test_un_outil_absent_est_un_echec(aire, outil):
    resultats = jouer(aire, which=lambda nom: None if nom == outil else f"/usr/bin/{nom}")
    assert resultats[f"outil_{outil}"].etat == "ÉCHEC"
    assert [i for i, v in resultats.items() if v.etat == "ÉCHEC"] == [f"outil_{outil}"]


def test_ssh_absent_est_un_avertissement_sans_source_distante(aire):
    sans_ssh = lambda nom: None if nom == "ssh" else f"/usr/bin/{nom}"
    assert jouer(aire, which=sans_ssh)["outil_ssh"].etat == "AVERTISSEMENT"
    assert jouer(aire, which=tous_les_outils)["outil_ssh"].etat == "OK"


def test_ssh_absent_est_un_echec_si_la_configuration_declare_des_sources_distantes(aire):
    aire["chemin"].write_text(json.dumps({**aire["configuration"], "sources_distantes": [{"id": "machine1"}]}), encoding="utf-8")
    sans_ssh = lambda nom: None if nom == "ssh" else f"/usr/bin/{nom}"
    assert jouer(aire, which=sans_ssh)["outil_ssh"].etat == "ÉCHEC"


def test_sans_configuration_ni_ollama_le_bilan_est_celui_de_la_specification(aire):
    sortie = io.StringIO()
    verifications = diagnostic.diagnostiquer(None, aire["environ"], aire["script"], aucune_cle_absente, which=tous_les_outils,
                                             version_python=(3, 12, 11), lister=jamais_appele, verifier_coffre=coffre_monte)
    diagnostic.afficher(verifications, sortie)
    lignes = sortie.getvalue().splitlines()
    assert [ligne.split()[0] for ligne in lignes[:-1]] == ["OK"] * 5 + ["NON_CONFIGURÉ"] + ["NON_VÉRIFIÉ"] * 7
    assert lignes[-1] == "Diagnostic : 5 OK, 0 avertissement(s), 0 échec(s), 1 non configuré(s), 7 non vérifié(s)"
    assert diagnostic.code_de_retour(verifications) == 0


def test_configuration_non_configuree_liste_les_quatre_emplacements(aire):
    message = jouer(aire, option=None)["configuration"].message
    assert jouer(aire, option=None)["configuration"].etat == "NON_CONFIGURÉ"
    assert "--config" in message and "SKRIVAGNER_CONFIG" in message and str(aire["script"]) in message
    assert "/maison/.config/skrivagner/config.json" in message


def test_configuration_invalide_est_un_echec_et_les_dependants_ne_sont_pas_verifies(aire):
    aire["chemin"].write_text("{pas du json", encoding="utf-8")
    resultats = jouer(aire, lister=jamais_appele)
    assert resultats["configuration"].etat == "ÉCHEC" and str(aire["chemin"]) in resultats["configuration"].message
    assert {resultats[i].etat for i in IDENTIFIANTS[6:]} == {"NON_VÉRIFIÉ"}


def test_une_source_explicite_absente_est_un_echec_et_non_un_etat_non_configure(aire, tmp_path):
    resultat = jouer(aire, option=tmp_path / "absent.json")["configuration"]
    assert resultat.etat == "ÉCHEC" and str(tmp_path / "absent.json") in resultat.message


def test_des_cles_absentes_sont_un_echec_qui_les_liste(aire):
    resultat = jouer(aire, cles=lambda configuration: ["extraction.pages_ocr", "categories"])["configuration"]
    assert resultat.etat == "ÉCHEC" and "extraction.pages_ocr, categories" in resultat.message


def test_la_variable_du_mot_de_passe_imap_absente_est_un_avertissement_sans_jamais_etre_ecrite(aire):
    source = {"id": "i", "authentification": "login", "mot_de_passe_env": "SKRIVAGNER_IMAP_EXEMPLE"}
    aire["chemin"].write_text(json.dumps({**aire["configuration"], "sources_imap": [source]}), encoding="utf-8")
    absente = jouer(aire)["configuration"]
    assert absente.etat == "AVERTISSEMENT" and "SKRIVAGNER_IMAP_EXEMPLE" in absente.message
    presente = jouer(aire, environ={**aire["environ"], "SKRIVAGNER_IMAP_EXEMPLE": "valeur-secrete-factice"})
    assert presente["configuration"].etat == "OK"
    assert "valeur-secrete-factice" not in " ".join(v.message for v in presente.values())


@pytest.mark.parametrize("nommage, etat", [({"prefixe_a_verifier": "[AV]"}, "AVERTISSEMENT"),
                                            ({"prefixe_a_verifier": "[AV]", "format_a_verifier": "{origine}{ext}"}, "OK")])
def test_sans_format_a_verifier_le_diagnostic_avertit(aire, nommage, etat):
    aire["chemin"].write_text(json.dumps({**aire["configuration"], "nommage": nommage}), encoding="utf-8")
    resultat = jouer(aire)["configuration"]
    assert resultat.etat == etat
    assert ("nommage.format_a_verifier" in resultat.message) is (etat == "AVERTISSEMENT")


def test_les_deux_avertissements_de_configuration_se_cumulent(aire):
    source = {"id": "i", "authentification": "login", "mot_de_passe_env": "SKRIVAGNER_IMAP_EXEMPLE"}
    aire["chemin"].write_text(json.dumps({**aire["configuration"], "sources_imap": [source], "nommage": {}}), encoding="utf-8")
    message = jouer(aire)["configuration"].message
    assert "SKRIVAGNER_IMAP_EXEMPLE" in message and "nommage.format_a_verifier" in message


def test_l_etat_hors_de_tout_coffre_est_un_avertissement(aire):
    configuration = json.loads(aire["chemin"].read_text(encoding="utf-8"))
    del configuration["suivi"]
    aire["chemin"].write_text(json.dumps(configuration), encoding="utf-8")
    resultat = jouer(aire)["emplacement_etat"]
    assert resultat.etat == "AVERTISSEMENT" and "en clair" in resultat.message and "/maison/.local/state/skrivagner" in resultat.message


def test_l_etat_sous_un_coffre_est_ok_et_donne_le_dossier(aire, tmp_path):
    resultat = jouer(aire)["emplacement_etat"]
    assert resultat.etat == "OK" and resultat.message == str(tmp_path / "coffre-a" / "logs")


def test_ollama_muet_est_un_echec_et_les_modeles_ne_sont_pas_verifies(aire):
    resultats = jouer(aire, lister=ollama_muet)
    assert resultats["ollama"].etat == "ÉCHEC" and "ne répond pas" in resultats["ollama"].message and "\n" not in resultats["ollama"].message
    assert [resultats[f"modele_{role}"].etat for role in ("ocr", "tri_rapide", "classification")] == ["NON_VÉRIFIÉ"] * 3
    assert diagnostic.code_de_retour(list(resultats.values())) == 1


def test_une_configuration_sans_url_ollama_est_un_echec(aire):
    configuration = json.loads(aire["chemin"].read_text(encoding="utf-8"))
    del configuration["ollama"]["url"]
    aire["chemin"].write_text(json.dumps(configuration), encoding="utf-8")
    assert jouer(aire, lister=jamais_appele)["ollama"].etat == "ÉCHEC"


@pytest.mark.parametrize("preferences", [["introuvable"], []])
def test_un_role_sans_modele_installe_ou_sans_preference_est_un_echec_qui_nomme_la_cle(aire, preferences):
    configuration = json.loads(aire["chemin"].read_text(encoding="utf-8"))
    configuration["ollama"]["roles"]["ocr"] = preferences
    aire["chemin"].write_text(json.dumps(configuration), encoding="utf-8")
    resultat = jouer(aire)["modele_ocr"]
    assert resultat.etat == "ÉCHEC" and "ollama.roles.ocr" in resultat.message


def test_un_nom_sans_etiquette_vaut_latest(aire):
    assert jouer(aire)["modele_ocr"].message == "m-ocr:latest"


def test_un_coffre_non_prouve_est_un_echec_avec_la_raison(aire):
    resultats = jouer(aire, coffre=coffre_ferme)
    for domaine in ("personnel", "professionnel"):
        assert resultats[f"destination_{domaine}"].etat == "ÉCHEC" and "coffre non monté" in resultats[f"destination_{domaine}"].message


def test_une_racine_absente_de_la_configuration_est_un_echec(aire):
    configuration = json.loads(aire["chemin"].read_text(encoding="utf-8"))
    del configuration["destinations"]["professionnel"]
    aire["chemin"].write_text(json.dumps(configuration), encoding="utf-8")
    resultat = jouer(aire)["destination_professionnel"]
    assert resultat.etat == "ÉCHEC" and "destinations.professionnel.racine" in resultat.message


def test_le_type_de_systeme_de_fichiers_accepte_vient_de_la_configuration(aire):
    demandes = {}
    def espion(domaine, racine, acceptes=None):
        demandes[domaine] = acceptes
        return coffre_monte(domaine, racine)
    jouer(aire, coffre=espion)
    assert demandes == {"personnel": ("fuse.gocryptfs",), "professionnel": (coffres.TYPE_COFFRE,)}


def test_avertissements_et_non_verifies_ne_changent_pas_le_code(aire):
    resultats = diagnostic.diagnostiquer(None, aire["environ"], aire["script"], aucune_cle_absente, which=lambda nom: None if nom == "ssh" else "/x",
                                         version_python=(3, 12, 0), lister=jamais_appele, verifier_coffre=coffre_monte)
    assert {v.etat for v in resultats} >= {"AVERTISSEMENT", "NON_VÉRIFIÉ", "NON_CONFIGURÉ"}
    assert diagnostic.code_de_retour(resultats) == 0


def test_main_diagnose_sans_configuration_rend_0_et_ne_cree_aucun_fichier(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(skrivagner, "CHEMIN_CONFIG", tmp_path / "absente.json")
    monkeypatch.setenv("HOME", str(tmp_path / "maison"))
    monkeypatch.setattr("sys.argv", ["skrivagner", "--diagnose"])
    avant = sorted(tmp_path.rglob("*"))
    code = skrivagner.main()
    lignes = capsys.readouterr().out.splitlines()
    assert [ligne.split()[0] for ligne in lignes[5:-1]] == ["NON_CONFIGURÉ"] + ["NON_VÉRIFIÉ"] * 7
    assert lignes[-1].endswith("1 non configuré(s), 7 non vérifié(s)")
    assert code == (1 if any(ligne.startswith("ÉCHEC ") for ligne in lignes) else 0)
    assert sorted(tmp_path.rglob("*")) == avant


def test_main_diagnose_avec_une_configuration_valide_et_ollama_eteint_rend_1(tmp_path, monkeypatch, capsys):
    configuration = json.loads((RACINE / "config.exemple.json").read_text(encoding="utf-8"))
    configuration["ollama"]["url"] = "http://127.0.0.1:9"
    configuration["ollama"]["timeout_secondes"] = 2
    chemin = tmp_path / "config.json"
    chemin.write_text(json.dumps(configuration), encoding="utf-8")
    monkeypatch.setenv("SKRIVAGNER_IMAP_EXEMPLE", "valeur-factice")
    monkeypatch.setattr("sys.argv", ["skrivagner", "--diagnose", "--config", str(chemin)])
    assert skrivagner.main() == 1
    lignes = {ligne.split()[1]: ligne.split()[0] for ligne in capsys.readouterr().out.splitlines()[:-1]}
    assert lignes["configuration"] == "OK"
    assert lignes["ollama"] == "ÉCHEC"
    assert [lignes[f"modele_{role}"] for role in ("ocr", "tri_rapide", "classification")] == ["NON_VÉRIFIÉ"] * 3


def test_diagnose_par_la_ligne_de_commande_dans_un_domicile_vide(tmp_path):
    resultat = subprocess.run([sys.executable, str(RACINE / "skrivagner.py"), "--diagnose"], capture_output=True, text=True,
                              env={"HOME": str(tmp_path), "PATH": "/usr/bin:/bin", "PYTHONDONTWRITEBYTECODE": "1", "LC_ALL": "fr_FR.UTF-8"}, cwd=tmp_path)
    lignes = resultat.stdout.splitlines()
    assert any(ligne.startswith("NON_CONFIGURÉ configuration : ") for ligne in lignes)
    assert lignes[-1].startswith("Diagnostic : ")
    assert resultat.returncode == (1 if any(ligne.startswith("ÉCHEC ") for ligne in lignes) else 0)
    assert list(tmp_path.iterdir()) == []
