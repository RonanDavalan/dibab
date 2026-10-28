"""config.exemple.json : se charge, ses clés sont complètes et il ne porte aucune donnée de foyer."""

import json
import re
from pathlib import Path

from modules import chemins, mesure_domaines, sources_distantes, sources_imap

RACINE = Path(__file__).resolve().parent.parent
EXEMPLE = RACINE / "config.exemple.json"


def charger():
    return json.loads(EXEMPLE.read_text(encoding="utf-8"))


def test_l_exemple_se_charge_et_ses_chemins_se_developpent(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    configuration = chemins.developper_chemins(charger())
    assert configuration["suivi"]["journal"] == f"{tmp_path}/Documents/skrivagner/personnel/logs/journal.jsonl"
    assert all("~" not in source["chemin"] for source in configuration["sources_locales"])


def test_l_exemple_porte_toutes_les_cles_exigees_par_les_modules():
    configuration = charger()
    assert sources_imap.cles_absentes(configuration) == []
    assert sources_distantes.cles_absentes(configuration) == []
    assert mesure_domaines.cles_absentes(configuration) == []


def test_chaque_domaine_a_une_racine_et_un_type_de_systeme_de_fichiers():
    destinations = charger()["destinations"]
    assert set(destinations) == {"personnel", "professionnel"}
    for destination in destinations.values():
        assert destination["racine"] and destination["systemes_fichiers_acceptes"]


def test_l_exemple_ne_contient_ni_chemin_personnel_ni_secret():
    texte = EXEMPLE.read_text(encoding="utf-8")
    assert not re.search(r"/hom[e]/|/Users/|ada\.local", texte)
    assert not re.search(r'"(mot_de_passe|password|secret|access_token|refresh_token)"\s*:', texte)
    assert "mot_de_passe_env" in texte
