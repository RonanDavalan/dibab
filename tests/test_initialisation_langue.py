"""Initialisation de la configuration dans la langue de la session, et dry-run par le chemin de l'utilisateur."""

import json
import stat
import subprocess
import sys
from pathlib import Path

import pytest

from modules import coffres, messages
from tests.faux_ollama import FauxOllama
from tests.test_defauts_langue import ATTENDUS, LOCALES
from tests.test_extraction import pdf_avec_couche_texte
from tests.textes_factices import TEXTES

RACINE = Path(__file__).resolve().parent.parent


def environnement(tmp_path, langue):
    return {
        "HOME": str(tmp_path / "maison"),
        "XDG_CONFIG_HOME": str(tmp_path / "xdg"),
        "XDG_STATE_HOME": str(tmp_path / "etat"),
        "LC_ALL": LOCALES[langue],
        "PATH": "/usr/bin:/bin",
        "PYTHONDONTWRITEBYTECODE": "1",
    }


def lancer(tmp_path, langue, *arguments):
    return subprocess.run([sys.executable, str(RACINE / "dibab.py"), *arguments],
                          capture_output=True, text=True, env=environnement(tmp_path, langue), cwd=RACINE)


def chemin_configuration(tmp_path):
    return tmp_path / "xdg" / "dibab" / "config.json"


def preparer_dry_run(tmp_path, langue, faux):
    """Initialise, puis adapte la configuration au bac : faux Ollama, coffres et source locaux."""
    resultat = lancer(tmp_path, langue, "--initialiser")
    assert resultat.returncode == 0, resultat.stderr
    chemin = chemin_configuration(tmp_path)
    configuration = json.loads(chemin.read_text(encoding="utf-8"))
    coffre_a, coffre_b, source, temporaire = (tmp_path / nom for nom in ("coffre-a", "coffre-b", "source", "tmp"))
    for dossier in (coffre_a, coffre_b, source, temporaire):
        dossier.mkdir()
    type_systeme = coffres.type_systeme_fichiers(tmp_path)
    assert type_systeme, "findmnt ne rend pas le type du bac"
    configuration["ollama"].update(url=faux.url, timeout_secondes=5,
                                   roles={"ocr": ["m-tri"], "tri_rapide": ["m-tri"], "classification": ["m-fin"],
                                          "tri_decision": [], "objet": []})
    for domaine, racine in (("personnel", coffre_a), ("professionnel", coffre_b)):
        configuration["destinations"][domaine].update(racine=str(racine), systemes_fichiers_acceptes=[type_systeme])
    configuration["suivi"] = {
        "fichier_date": str(coffre_a / "logs" / "dernier_scan.json"),
        "journal": str(coffre_a / "logs" / "journal.jsonl"),
        "sessions": str(coffre_a / "logs" / "sessions"),
        "rotation": {"journal_taille_max_mo": 20, "journal_archives_max": 5, "sessions_max": 100},
    }
    configuration["sources_locales"] = [{"id": "source", "chemin": str(source), "date_reference": "modification",
                                         "recursif": True, "exclusions": []}]
    configuration["sources_distantes"] = []
    configuration["sources_imap"] = []
    configuration["extraction"]["repertoire_temporaire"] = str(temporaire)
    chemin.write_text(json.dumps(configuration, ensure_ascii=False), encoding="utf-8")
    texte = " ".join([TEXTES[8]["texte"]] * 3)
    pdf_avec_couche_texte(source / "courrier.pdf", texte)
    return chemin, coffre_a


@pytest.mark.parametrize("langue", messages.LANGUES)
def test_initialiser_ecrit_la_configuration_de_la_langue(tmp_path, langue):
    resultat = lancer(tmp_path, langue, "--initialiser")
    assert resultat.returncode == 0, resultat.stderr
    assert resultat.stderr == ""
    chemin = chemin_configuration(tmp_path)
    assert str(chemin) in resultat.stdout
    assert stat.S_IMODE(chemin.stat().st_mode) == 0o600
    configuration = json.loads(chemin.read_text(encoding="utf-8"))
    dossier, prefixe, doublon = ATTENDUS[langue]
    assert configuration["destination"]["repertoire_doublon"] == doublon
    assert configuration["nommage"]["prefixe_a_verifier"] == prefixe
    for destination in configuration["destinations"].values():
        assert destination["sous_repertoire_a_verifier"] == dossier
    assert doublon in configuration["scan"]["exclusions_automatiques"]
    assert doublon in configuration["inventaire"]["exclusions"]
    assert doublon in configuration["mesure"]["exclusions"]


@pytest.mark.parametrize("langue", messages.LANGUES)
def test_le_dry_run_montre_le_dossier_et_le_prefixe_de_la_langue(tmp_path, langue):
    with FauxOllama(tri="incertain", fine=TEXTES[8]["reponse"]) as faux:
        chemin, coffre = preparer_dry_run(tmp_path, langue, faux)
        avant = chemin.read_bytes()
        resultat = lancer(tmp_path, langue, "--dry-run")
    assert resultat.returncode == 0, resultat.stderr
    dossier, prefixe, _ = ATTENDUS[langue]
    assert f"{coffre}/{dossier}/{prefixe}" in resultat.stdout and "a_verifier" in resultat.stdout
    for autre_langue, (autre_dossier, autre_prefixe, _) in ATTENDUS.items():
        if autre_langue != langue:
            assert f"{coffre}/{autre_dossier}/" not in resultat.stdout
            assert autre_prefixe not in resultat.stdout
    assert chemin.read_bytes() == avant


def test_une_configuration_francaise_garde_ses_noms_sous_une_interface_anglaise(tmp_path):
    with FauxOllama(tri="incertain", fine=TEXTES[8]["reponse"]) as faux:
        chemin, coffre = preparer_dry_run(tmp_path, "fr", faux)
        avant = chemin.read_bytes()
        resultat_initialisation = lancer(tmp_path, "en", "--initialiser")
        assert resultat_initialisation.returncode == 0
        assert chemin.read_bytes() == avant
        resultat = lancer(tmp_path, "en", "--dry-run")
    assert resultat.returncode == 0, resultat.stderr
    assert f"{coffre}/À_VÉRIFIER/[À_VÉRIFIER]" in resultat.stdout and "a_verifier" in resultat.stdout
    assert "TO_CHECK" not in resultat.stdout and "[TO_CHECK]" not in resultat.stdout
