"""Verrou d'exécution : un seul Dibab à la fois."""

import os

import pytest

from modules import verrou


def test_un_second_verrou_est_refuse_puis_libere(tmp_path):
    chemin = tmp_path / "logs" / "dibab.verrou"
    with verrou.verrou(chemin):
        with pytest.raises(verrou.VerrouPris):
            with verrou.verrou(chemin):
                pass
    assert not chemin.exists()
    with verrou.verrou(chemin):
        pass


def test_un_verrou_de_processus_mort_est_repris(tmp_path):
    chemin = tmp_path / "dibab.verrou"
    chemin.write_text("2147483646")
    with verrou.verrou(chemin):
        assert chemin.read_text() == str(os.getpid())


def test_le_verrou_est_libere_apres_une_erreur(tmp_path):
    chemin = tmp_path / "dibab.verrou"
    with pytest.raises(RuntimeError):
        with verrou.verrou(chemin):
            raise RuntimeError
    assert not chemin.exists()
