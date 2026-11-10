"""Recherche de la configuration, emplacements par défaut de l'état et --version (spécification 28, décisions 1 à 3)."""

import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

import dibab
from modules import installation

RACINE = Path(__file__).resolve().parent.parent


def ecrire(chemin, contenu="{}"):
    chemin.parent.mkdir(parents=True, exist_ok=True)
    chemin.write_text(contenu, encoding="utf-8")
    return chemin


@pytest.fixture
def lieux(tmp_path):
    """Les quatre emplacements, chacun portant un fichier distinct, et l'environnement qui les désigne."""
    environ = {"HOME": str(tmp_path / "maison"), "XDG_CONFIG_HOME": str(tmp_path / "xdg"),
               "DIBAB_CONFIG": str(tmp_path / "variable.json")}
    return {"option": tmp_path / "option.json", "variable": tmp_path / "variable.json",
            "xdg": tmp_path / "xdg" / "dibab" / "config.json", "script": tmp_path / "script" / "config.json",
            "environ": environ, "maison": tmp_path / "maison" / ".config" / "dibab" / "config.json"}


def chercher(lieux, option=None, environ=None):
    return installation.rechercher_configuration(option, lieux["environ"] if environ is None else environ, lieux["script"])


def test_l_option_prime_sur_les_trois_autres(lieux):
    for cle in ("option", "variable", "xdg", "script"):
        ecrire(lieux[cle])
    assert chercher(lieux, option=lieux["option"]) == lieux["option"]


def test_la_variable_prime_sur_xdg_et_sur_le_script(lieux):
    for cle in ("variable", "xdg", "script"):
        ecrire(lieux[cle])
    assert chercher(lieux) == lieux["variable"]


def test_une_variable_vide_est_ignoree(lieux):
    ecrire(lieux["xdg"])
    assert chercher(lieux, environ={**lieux["environ"], "DIBAB_CONFIG": ""}) == lieux["xdg"]


def test_xdg_prime_sur_le_script(lieux):
    ecrire(lieux["xdg"])
    ecrire(lieux["script"])
    assert chercher(lieux, environ={**lieux["environ"], "DIBAB_CONFIG": ""}) == lieux["xdg"]


def test_sans_xdg_config_home_l_emplacement_est_sous_le_domicile(lieux):
    ecrire(lieux["maison"])
    environ = {"HOME": lieux["environ"]["HOME"]}
    assert chercher(lieux, environ=environ) == lieux["maison"]
    assert chercher(lieux, environ={**environ, "XDG_CONFIG_HOME": ""}) == lieux["maison"]


def test_le_dossier_du_script_est_le_dernier_recours(lieux):
    ecrire(lieux["script"])
    assert chercher(lieux, environ={"HOME": lieux["environ"]["HOME"]}) == lieux["script"]


def test_une_option_dont_le_fichier_manque_arrete_sans_essayer_les_suivantes(lieux):
    for cle in ("variable", "xdg", "script"):
        ecrire(lieux[cle])
    with pytest.raises(installation.ErreurConfiguration) as erreur:
        chercher(lieux, option=lieux["option"])
    assert "l'option --config" in str(erreur.value) and str(lieux["option"]) in str(erreur.value)
    assert not isinstance(erreur.value, installation.ConfigurationIntrouvable)


def test_une_variable_dont_le_fichier_manque_arrete_sans_lire_xdg(lieux):
    ecrire(lieux["xdg"])
    ecrire(lieux["script"])
    with pytest.raises(installation.ErreurConfiguration) as erreur:
        chercher(lieux)
    assert "DIBAB_CONFIG" in str(erreur.value) and str(lieux["variable"]) in str(erreur.value)
    assert not isinstance(erreur.value, installation.ConfigurationIntrouvable)


def test_sans_aucune_source_le_message_liste_les_quatre_emplacements_et_nomme_l_exemple(lieux):
    with pytest.raises(installation.ConfigurationIntrouvable) as erreur:
        chercher(lieux, environ={"HOME": lieux["environ"]["HOME"], "XDG_CONFIG_HOME": lieux["environ"]["XDG_CONFIG_HOME"]})
    message = str(erreur.value)
    assert [ligne.strip()[:2] for ligne in message.splitlines()[1:5]] == ["1.", "2.", "3.", "4."]
    assert str(lieux["xdg"]) in message and str(lieux["script"]) in message
    assert "non donnée" in message and "config.exemple.json" in message


def test_le_premier_fichier_trouve_est_le_seul_lu(lieux):
    ecrire(lieux["xdg"], json.dumps({"origine": "xdg"}))
    ecrire(lieux["script"], json.dumps({"origine": "script", "en_plus": 1}))
    chemin = chercher(lieux, environ={"HOME": lieux["environ"]["HOME"], "XDG_CONFIG_HOME": lieux["environ"]["XDG_CONFIG_HOME"]})
    assert installation.lire_configuration(chemin) == {"origine": "xdg"}


@pytest.mark.parametrize("contenu", ["{pas du json", "[1, 2]"])
def test_un_fichier_illisible_ou_invalide_rend_le_chemin_et_la_cause(tmp_path, contenu):
    chemin = ecrire(tmp_path / "config.json", contenu)
    with pytest.raises(installation.ErreurConfiguration) as erreur:
        installation.lire_configuration(chemin)
    assert str(chemin) in str(erreur.value)


def test_main_sans_configuration_rend_1_et_liste_les_emplacements(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(dibab, "CHEMIN_CONFIG", tmp_path / "absente.json")
    monkeypatch.setattr("sys.argv", ["dibab", "--dry-run"])
    with pytest.raises(SystemExit) as sortie:
        dibab.main()
    assert sortie.value.code == 1
    erreur = capsys.readouterr().err
    assert "configuration introuvable" in erreur and str(tmp_path / "absente.json") in erreur


def test_main_avec_une_option_explicite_absente_rend_1_sans_lire_le_script(tmp_path, monkeypatch, capsys):
    ecrire(tmp_path / "config.json")
    monkeypatch.setattr(dibab, "CHEMIN_CONFIG", tmp_path / "config.json")
    monkeypatch.setattr("sys.argv", ["dibab", "--config", str(tmp_path / "autre.json")])
    with pytest.raises(SystemExit) as sortie:
        dibab.main()
    assert sortie.value.code == 1
    assert str(tmp_path / "autre.json") in capsys.readouterr().err


def test_main_avec_une_configuration_invalide_rend_1(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr("sys.argv", ["dibab", "--config", str(ecrire(tmp_path / "x.json", "{pas du json"))])
    with pytest.raises(SystemExit) as sortie:
        dibab.main()
    assert sortie.value.code == 1
    assert str(tmp_path / "x.json") in capsys.readouterr().err


# Emplacements par défaut de l'état (décision 2)

def test_les_quatre_cles_absentes_prennent_leur_defaut_sous_xdg_state_home(tmp_path):
    configuration, dossier = installation.appliquer_defauts_suivi({"suivi": {"securite_jours": 1}}, {"XDG_STATE_HOME": str(tmp_path)})
    base = tmp_path / "dibab"
    assert dossier == base
    assert configuration["suivi"] == {"securite_jours": 1, "fichier_date": str(base / "dernier_scan.json"),
                                      "journal": str(base / "journal.jsonl"), "sessions": str(base / "sessions"),
                                      "logs_systeme": str(base / "dibab.log")}


def test_sans_xdg_state_home_le_defaut_est_sous_local_state(tmp_path):
    for environ in ({"HOME": str(tmp_path)}, {"HOME": str(tmp_path), "XDG_STATE_HOME": ""}):
        configuration, dossier = installation.appliquer_defauts_suivi({}, environ)
        assert dossier == tmp_path / ".local" / "state" / "dibab"
        assert configuration["suivi"]["journal"] == str(dossier / "journal.jsonl")


def test_une_cle_donnee_l_emporte_et_sans_defaut_aucun_dossier_n_est_rendu(tmp_path):
    suivi = {"fichier_date": "/c/a.json", "journal": "/c/j.jsonl", "sessions": "/c/s", "logs_systeme": "/c/l.log"}
    configuration, dossier = installation.appliquer_defauts_suivi({"suivi": suivi}, {"XDG_STATE_HOME": str(tmp_path)})
    assert configuration["suivi"] == suivi and dossier is None
    mixte, dossier = installation.appliquer_defauts_suivi({"suivi": {**suivi, "journal": ""}}, {"XDG_STATE_HOME": str(tmp_path)})
    assert mixte["suivi"]["fichier_date"] == "/c/a.json" and mixte["suivi"]["journal"].startswith(str(tmp_path)) and dossier


def test_les_dossiers_d_etat_se_creent_en_700_et_les_fichiers_se_durcissent_en_600(tmp_path):
    dossier = tmp_path / "etat" / "dibab"
    installation.preparer_dossier_etat(dossier)
    (dossier / "sessions" / "session.jsonl").write_text("{}", encoding="utf-8")
    (dossier / "journal.jsonl").write_text("{}", encoding="utf-8")
    installation.durcir_dossier_etat(dossier)
    assert oct(dossier.stat().st_mode & 0o777) == oct(0o700)
    assert oct((dossier / "sessions").stat().st_mode & 0o777) == oct(0o700)
    assert oct((dossier / "journal.jsonl").stat().st_mode & 0o777) == oct(0o600)
    assert oct((dossier / "sessions" / "session.jsonl").stat().st_mode & 0o777) == oct(0o600)


# --version (décision 3)

def test_version_ecrit_une_ligne_exacte_et_rend_0_sans_lire_de_configuration(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(dibab, "CHEMIN_CONFIG", tmp_path / "absente.json")
    monkeypatch.setattr("sys.argv", ["dibab", "--version"])
    with pytest.raises(SystemExit) as sortie:
        dibab.main()
    assert sortie.value.code == 0
    sortie = capsys.readouterr()
    assert sortie.out == f"dibab {dibab.VERSION}\n" and sortie.err == ""
    assert re.fullmatch(r"dibab \d+\.\d+\.\d+-alpha\n", sortie.out)
    assert list(tmp_path.iterdir()) == []


def test_version_par_la_ligne_de_commande_dans_un_domicile_vide(tmp_path):
    resultat = subprocess.run([sys.executable, str(RACINE / "dibab.py"), "--version"], capture_output=True,
                              text=True, env={"HOME": str(tmp_path), "PATH": "/usr/bin:/bin", "PYTHONDONTWRITEBYTECODE": "1"}, cwd=tmp_path)
    assert (resultat.returncode, resultat.stdout, resultat.stderr) == (0, f"dibab {dibab.VERSION}\n", "")
    assert list(tmp_path.iterdir()) == []


def test_une_ligne_de_commande_invalide_rend_2(monkeypatch):
    for arguments in (["--inconnue"], ["--diagnose", "--execute"], ["--config"]):
        monkeypatch.setattr("sys.argv", ["dibab", *arguments])
        with pytest.raises(SystemExit) as sortie:
            dibab.main()
        assert sortie.value.code == 2


def test_seul_le_defaut_d_une_cle_ecrite_cree_le_dossier_d_etat(tmp_path):
    suivi = {"fichier_date": "/c/a.json", "journal": "/c/j.jsonl", "sessions": "/c/s"}
    configuration, dossier = installation.appliquer_defauts_suivi({"suivi": suivi}, {"XDG_STATE_HOME": str(tmp_path)})
    assert configuration["suivi"]["logs_systeme"] == str(tmp_path / "dibab" / "dibab.log") and dossier is None


def test_le_dossier_des_sessions_n_est_cree_que_s_il_est_le_defaut(tmp_path):
    dossier = tmp_path / "dibab"
    installation.preparer_dossier_etat(dossier, {"suivi": {"sessions": "/ailleurs/sessions"}})
    assert dossier.is_dir() and not (dossier / "sessions").exists()
