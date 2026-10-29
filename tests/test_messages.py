"""Messages de l'outil : parité des dictionnaires, clés appelées, choix de la langue, repli, aide, journaux (spécification 29)."""

import ast
import json
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

import pytest

import skrivagner
from modules import diagnostic, messages
from tests.test_classement_execute import banc, lancer  # noqa: F401
from tests.test_rollback import etat, lignes_journal

RACINE = Path(__file__).resolve().parent.parent
LANGUES = messages.LANGUES
LIGNE = re.compile(r"^[a-z][a-z_0-9]*=.+$")
NOM_DE_VALEUR = re.compile(r"\{([a-z][a-z_0-9]*)\}")
FAMILLES_NON_APPELEES_PAR_LITTERAL = ("diagnostic_",)


def lire(langue):
    return messages.lire_dictionnaire(messages.DOSSIER / f"{langue}.txt")


def lignes_de_cles(langue):
    texte = (messages.DOSSIER / f"{langue}.txt").read_text(encoding="utf-8")
    return [ligne for ligne in texte.splitlines() if ligne.strip() and not ligne.startswith("#")]


def cles_appelees():
    """Les clés littérales passées à `traduire` dans le code du produit, lues par l'analyse du code source."""
    cles = {}
    for chemin in [RACINE / "skrivagner.py", *sorted((RACINE / "modules").glob("*.py")), *sorted((RACINE / "_outils").glob("*.py"))]:
        for noeud in ast.walk(ast.parse(chemin.read_text(encoding="utf-8"))):
            if isinstance(noeud, ast.Call) and isinstance(noeud.func, ast.Name) and noeud.func.id == "traduire" \
                    and noeud.args and isinstance(noeud.args[0], ast.Constant):
                cles.setdefault(noeud.args[0].value, []).append(f"{chemin.name}:{noeud.lineno}")
    return cles


@pytest.fixture
def langue_fixee(monkeypatch):
    def fixer(code):
        monkeypatch.setenv("LC_ALL", f"{code}_{code.upper()}.UTF-8")
        messages.initialiser()
    return fixer


@pytest.mark.parametrize("langue", LANGUES)
def test_chaque_ligne_est_cle_egale_valeur_sans_double_ni_accolade_litterale(langue):
    lignes = lignes_de_cles(langue)
    assert all(LIGNE.match(ligne) for ligne in lignes), [ligne for ligne in lignes if not LIGNE.match(ligne)]
    cles = [ligne.split("=", 1)[0] for ligne in lignes]
    assert len(cles) == len(set(cles))
    for ligne in lignes:
        valeur = ligne.split("=", 1)[1]
        assert valeur == valeur.strip(), f"{langue}: espace de bord dans {ligne.split('=')[0]}"
        assert "{" not in NOM_DE_VALEUR.sub("", valeur) and "}" not in NOM_DE_VALEUR.sub("", valeur)


@pytest.mark.parametrize("langue", [langue for langue in LANGUES if langue != "en"])
def test_memes_cles_et_memes_noms_de_valeur_que_l_anglais(langue):
    source, traduit = lire("en"), lire(langue)
    assert set(traduit) == set(source), (sorted(set(source) - set(traduit)), sorted(set(traduit) - set(source)))
    for cle, valeur in source.items():
        assert set(NOM_DE_VALEUR.findall(traduit[cle])) == set(NOM_DE_VALEUR.findall(valeur)), f"{langue}: {cle}"


def test_le_code_n_appelle_que_des_cles_de_l_anglais_et_chaque_cle_est_appelee():
    source, appelees = lire("en"), cles_appelees()
    assert not set(appelees) - set(source), {cle: lieux for cle, lieux in appelees.items() if cle not in source}
    inutiles = [cle for cle in source if cle not in appelees and not cle.startswith(FAMILLES_NON_APPELEES_PAR_LITTERAL)]
    assert inutiles == []


def test_le_diagnostic_porte_les_cles_de_chaque_couple_identifiant_etat():
    permis = diagnostic.etats_permis()
    assert len(permis) == 13
    for langue in LANGUES:
        dictionnaire = lire(langue)
        for identifiant, etats in permis.items():
            for etat_ in etats:
                assert f"diagnostic_{identifiant}_{diagnostic.SUFFIXES_ETAT[etat_]}" in dictionnaire, (langue, identifiant, etat_)
    autorisees = {"diagnostic_bilan", "diagnostic_emplacement_essaye", "diagnostic_complement_consensus"}
    prefixes = tuple(f"diagnostic_{identifiant}_" for identifiant in permis)
    assert all(cle in autorisees or cle.startswith(prefixes) for cle in lire("en") if cle.startswith("diagnostic_"))


def test_aucune_valeur_n_egale_une_cle_de_configuration_ni_un_jeton_d_etat():
    configuration = json.loads((RACINE / "config.exemple.json").read_text(encoding="utf-8"))
    interdits = {diagnostic.OK, diagnostic.AVERTISSEMENT, diagnostic.ECHEC, diagnostic.NON_CONFIGURE, diagnostic.NON_VERIFIE}

    def cles(objet):
        if isinstance(objet, dict):
            for cle, valeur in objet.items():
                yield cle
                yield from cles(valeur)
        elif isinstance(objet, list):
            for element in objet:
                yield from cles(element)

    interdits |= set(cles(configuration))
    for langue in LANGUES:
        assert not interdits & set(lire(langue).values()), langue


@pytest.mark.parametrize("environ, attendu", [
    ({"LC_ALL": "fr_FR.UTF-8"}, "fr"),
    ({"LC_ALL": "de_DE@euro"}, "de"),
    ({"LANG": "es_ES.UTF-8"}, "es"),
    ({"LC_ALL": "pt_BR.UTF-8", "LANG": "fr_FR.UTF-8"}, "en"),
    ({"LC_ALL": "", "LANG": "es_ES.UTF-8"}, "es"),
    ({"LC_ALL": "C", "LANG": "fr_FR.UTF-8"}, "en"),
    ({"LC_ALL": "", "LC_MESSAGES": "de_DE.UTF-8", "LANG": "fr_FR.UTF-8"}, "de"),
    ({"LANG": "POSIX"}, "en"),
    ({}, "en"),
])
def test_la_langue_suit_lc_all_lc_messages_puis_lang(environ, attendu):
    assert messages.code_langue(environ) == attendu


def test_le_repli_passe_par_l_anglais_puis_par_la_cle(tmp_path, monkeypatch):
    for langue in LANGUES:
        shutil.copy(messages.DOSSIER / f"{langue}.txt", tmp_path / f"{langue}.txt")
    lignes = [ligne for ligne in (tmp_path / "de.txt").read_text(encoding="utf-8").splitlines() if not ligne.startswith("rapport_session=")]
    (tmp_path / "de.txt").write_text("\n".join(lignes) + "\n", encoding="utf-8")
    (tmp_path / "es.txt").write_bytes(b"\xff\xfe=\x00")
    monkeypatch.setattr(messages, "DOSSIER", tmp_path)
    monkeypatch.setattr(messages, "_dictionnaires", {})
    monkeypatch.setenv("LC_ALL", "de_DE.UTF-8")
    messages.initialiser()
    assert messages.traduire("rapport_session", chemin="/x") == "Session report: /x"
    assert messages.traduire("coffre_monte") == "eingehängt"
    assert messages.traduire("cle_qui_n_existe_pas") == "<cle_qui_n_existe_pas>"
    monkeypatch.setenv("LC_ALL", "es_ES.UTF-8")
    messages.initialiser()
    assert messages.traduire("rapport_session", chemin="/x") == "Session report: /x"


def test_une_taille_s_affiche_dans_l_unite_de_la_langue(langue_fixee):
    langue_fixee("en")
    assert skrivagner.formater_taille(2048) == "2.0 KB" and skrivagner.formater_taille(12) == "12 B"
    langue_fixee("fr")
    assert skrivagner.formater_taille(2048) == "2.0 Ko" and skrivagner.formater_taille(12) == "12 o"
    langue_fixee("de")
    assert skrivagner.formater_taille(3 * 1024 ** 2) == "3.0 MB"


def lancer_processus(arguments, environ, tmp_path):
    base = {"HOME": str(tmp_path), "PATH": "/usr/bin:/bin", "PYTHONDONTWRITEBYTECODE": "1", **environ}
    return subprocess.run([sys.executable, str(RACINE / "skrivagner.py"), *arguments], capture_output=True, text=True, env=base, cwd=tmp_path)


OPTIONS = ("--dry-run", "--execute", "--inventaire", "--rollback", "--autoriser-google", "--session", "--verdicts-simules",
           "--config", "--version", "--diagnose")
MOTS_D_ARGPARSE = ("usage:", "options:", "show this help message and exit")


@pytest.mark.parametrize("environ, langue", [
    ({"LC_ALL": "en_US.UTF-8"}, "en"), ({"LC_ALL": "fr_FR.UTF-8"}, "fr"), ({"LC_ALL": "de_DE.UTF-8"}, "de"),
    ({"LC_ALL": "es_ES.UTF-8"}, "es"), ({"LC_ALL": "C"}, "en"), ({"LC_ALL": "pt_BR.UTF-8"}, "en"), ({}, "en")])
def test_l_aide_et_le_diagnostic_sont_dans_la_langue_choisie(environ, langue, tmp_path):
    aide = lancer_processus(["--help"], environ, tmp_path)
    assert aide.returncode == 0 and all(option in aide.stdout for option in OPTIONS)
    assert aide.stdout.splitlines()[0].startswith(lire(langue)["aide_usage"])
    assert (aide.stdout.count("show this help message and exit") == 0) and ("Show this help message and exit" in aide.stdout) == (langue == "en")
    if langue != "en":
        assert not [mot for mot in MOTS_D_ARGPARSE if mot in aide.stdout.lower()], aide.stdout
    bilan = lancer_processus(["--diagnose"], environ, tmp_path)
    modele = lire(langue)["diagnostic_bilan"]
    assert bilan.stdout.splitlines()[-1].startswith(modele.split("{")[0])
    assert (bilan.stdout.splitlines()[0].split()[0], bilan.returncode) == ("OK", 0) or bilan.returncode in (0, 1)
    assert list(tmp_path.iterdir()) == []


def test_la_version_ne_se_traduit_pas(tmp_path):
    sorties = {lancer_processus(["--version"], {"LC_ALL": code}, tmp_path).stdout for code in ("fr_FR.UTF-8", "de_DE.UTF-8", "C")}
    assert sorties == {f"skrivagner {skrivagner.VERSION}\n"}


@pytest.mark.parametrize("environ, langue", [({"LC_ALL": "fr_FR.UTF-8"}, "fr"), ({"LC_ALL": "de_DE.UTF-8"}, "de"), ({"LC_ALL": "C"}, "en")])
def test_une_option_inconnue_donne_le_message_du_dictionnaire_et_le_code_2(environ, langue, tmp_path):
    resultat = lancer_processus(["--inexistant"], environ, tmp_path)
    assert resultat.returncode == 2 and resultat.stdout == ""
    assert resultat.stderr.strip() == lire(langue)["erreur_ligne_de_commande"].format(programme="skrivagner")
    assert "unrecognized" not in resultat.stderr


def test_deux_modes_exclusifs_donnent_le_meme_message(tmp_path):
    resultat = lancer_processus(["--execute", "--rollback"], {"LC_ALL": "es_ES.UTF-8"}, tmp_path)
    assert resultat.returncode == 2 and "not allowed" not in resultat.stderr
    assert resultat.stderr.strip() == lire("es")["erreur_ligne_de_commande"].format(programme="skrivagner")


def sans_horodatage(chemin):
    lignes = [json.loads(ligne) for ligne in chemin.read_text(encoding="utf-8").splitlines()]
    return [{cle: valeur for cle, valeur in ligne.items() if cle not in ("timestamp", "session")} for ligne in lignes]


def test_deux_sessions_en_deux_langues_ecrivent_le_meme_journal_et_une_console_differente(banc, monkeypatch, capsys, langue_fixee):  # noqa: F811
    racine, _ = banc
    sessions = racine / "coffre-a" / "logs" / "sessions"
    sorties = {}
    for code in ("fr", "de"):
        langue_fixee(code)
        capsys.readouterr()
        assert lancer(monkeypatch, "--dry-run") == 0
        sorties[code] = capsys.readouterr().out
        time.sleep(1.1)  # le nom d'un journal de session porte l'heure à la seconde
    fr, de = sorted(sessions.glob("session_*.jsonl"), key=lambda p: p.stat().st_mtime_ns)[-2:]
    journaux = [sans_horodatage(fr), sans_horodatage(de)]
    for journal in journaux:
        for ligne in journal:
            ligne.pop("duree_secondes", None)
    assert journaux[0] == journaux[1] and journaux[0]
    assert sorties["fr"] != sorties["de"] and "Mode" in sorties["fr"] and "Modus" in sorties["de"]


def test_un_journal_ecrit_dans_une_langue_se_rejoue_par_rollback_dans_une_autre(banc, monkeypatch, capsys, langue_fixee):  # noqa: F811
    racine, _ = banc
    avant = etat(racine)
    langue_fixee("fr")
    assert lancer(monkeypatch, "--execute") == 0
    brut = (racine / "coffre-a" / "logs" / "journal.jsonl").read_text(encoding="utf-8")
    assert etat(racine) != avant
    langue_fixee("de")
    capsys.readouterr()
    assert lancer(monkeypatch, "--rollback") == 0
    assert etat(racine) == avant
    assert "7 rückgängig gemacht, 0 fehlgeschlagen" in capsys.readouterr().out
    assert all(ligne["evenement"] != "echec_annulation" for ligne in lignes_journal(racine))
    assert brut and not re.search(r"[À-ÿ]", "".join(ligne.get("raison", "") for ligne in lignes_journal(racine)))


def test_un_message_du_produit_part_dans_le_journal_en_anglais(langue_fixee):
    langue_fixee("de")
    message = messages.traduire("rollback_destination_introuvable")
    assert str(message) == "Ziel nicht gefunden"
    assert messages.pour_journal({"raison": message, "liste": [message], "nombre": 3}) == {
        "raison": "destination not found", "liste": ["destination not found"], "nombre": 3}


def test_un_message_imbrique_est_recompose_en_anglais(langue_fixee):
    langue_fixee("fr")
    interne = messages.traduire("rollback_destination_introuvable")
    externe = messages.traduire("rollback_restitution_impossible", erreur=interne)
    assert str(externe) == "restitution impossible : destination introuvable"
    assert externe.en() == "cannot restore: destination not found"
