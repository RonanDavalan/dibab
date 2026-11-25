# Tests du module suivi — persistance de dernier_scan.json.

from datetime import datetime

from modules import suivi


def test_charger_fichier_inexistant(tmp_path):
    chemin = tmp_path / "absent.json"
    assert suivi.charger(chemin) == {}


def test_charger_fichier_invalide(tmp_path):
    chemin = tmp_path / "casse.json"
    chemin.write_text("ceci n'est pas du JSON")
    assert suivi.charger(chemin) == {}


def test_sauvegarder_puis_recharger(tmp_path):
    chemin = tmp_path / "dernier_scan.json"
    donnees = {
        "source-a": datetime(2026, 5, 15, 14, 22, 0),
        "source-b": datetime(2026, 5, 17, 9, 0, 0),
    }
    suivi.sauvegarder(chemin, donnees)

    rechargees = suivi.charger(chemin)
    assert rechargees == donnees


def test_charger_ignore_entrees_invalides(tmp_path):
    chemin = tmp_path / "mixte.json"
    chemin.write_text('{"valide": "2026-05-15T14:22:00", '
                      '"mauvais_format": "2026/05/15", '
                      '"pas_str": 12345}')
    resultat = suivi.charger(chemin)
    assert "valide" in resultat
    assert "mauvais_format" not in resultat
    assert "pas_str" not in resultat


def test_derniere_date_retourne_none_si_absent(tmp_path):
    chemin = tmp_path / "vide.json"
    suivi_charge = suivi.charger(chemin)
    assert suivi.derniere_date(suivi_charge, "n_existe_pas") is None


def test_sauvegarde_atomique_pas_de_fichier_temp(tmp_path):
    chemin = tmp_path / "dernier_scan.json"
    suivi.sauvegarder(chemin, {"s": datetime(2026, 5, 15, 0, 0, 0)})
    assert chemin.exists()
    fichiers_temp = list(tmp_path.glob("*.tmp"))
    assert fichiers_temp == []
