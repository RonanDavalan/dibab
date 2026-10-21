"""Listage distant par un faux `ssh` : listage attendu, machine absente, délai dépassé, noms piégés, filtre par date."""

import os
import time
from datetime import datetime, timedelta
from functools import partial

import pytest

from modules import scanner_ssh
from tests.faux_ssh import installer

SOURCE = {"id": "ssh-test", "alias_ssh": "machine-factice", "repertoires": ["~/Téléchargements"], "exclusions": []}
NOMS_PIEGES = ["x; touch PIEGE1.pdf", "$(touch PIEGE2).pdf", "`touch PIEGE3`.pdf", "saut\nde ligne.pdf", "tab\tici.pdf", "'guillemet\".pdf"]


@pytest.fixture
def distant(tmp_path, monkeypatch):
    racine = installer(tmp_path, monkeypatch)
    dossier = racine / "Téléchargements"
    (dossier / "sous").mkdir(parents=True)
    (dossier / ".cache").mkdir()
    (dossier / "rebut").mkdir()
    for nom in ("a.pdf", "sous/b.PNG", "c.txt", ".cache/d.pdf", "rebut/e.pdf", ".cache.pdf", *NOMS_PIEGES):
        (dossier / nom).write_bytes(b"contenu " + nom.encode())
    return racine


def lister(source=SOURCE, derniere=None, maintenant=None, delai=5, **extra):
    executer = partial(scanner_ssh.executer_ssh, delai_connexion=5, delai_commande=delai)
    return scanner_ssh.scanner_machine(source, {"exclusions_automatiques": ["rebut", "doublon"]}, [".pdf", ".png"], derniere, 0,
                                       90, maintenant or datetime.now(), executer)


def test_le_listage_rend_les_fichiers_attendus_sans_executer_un_nom(distant):
    candidats, complet, erreurs = lister()
    assert complet and erreurs == []
    assert {c.relatif for c in candidats} == {"a.pdf", "sous/b.PNG", *NOMS_PIEGES}
    assert not list(distant.rglob("PIEGE*"))
    assert all(c.source_id == "ssh-test" and c.alias == "machine-factice" for c in candidats)


def test_machine_absente_est_explicite_et_n_insiste_pas(distant, monkeypatch):
    monkeypatch.setenv("FAUX_SSH_MODE", "absente")
    candidats, complet, erreurs = lister({**SOURCE, "repertoires": ["~/Téléchargements", "~/Autre"]})
    assert candidats == [] and not complet and len(erreurs) == 1 and "Could not resolve" in erreurs[0]


def test_delai_depasse(distant, monkeypatch):
    monkeypatch.setenv("FAUX_SSH_MODE", "lent")
    debut = time.monotonic()
    candidats, complet, erreurs = lister(delai=1)
    assert candidats == [] and not complet and "délai" in erreurs[0] and time.monotonic() - debut < 10


def test_repertoire_distant_absent_rend_un_listage_incomplet(distant):
    candidats, complet, erreurs = lister({**SOURCE, "repertoires": ["~/Inexistant"]})
    assert candidats == [] and not complet and erreurs


def test_deux_listages_successifs_ne_rendent_que_les_nouveaux(distant):
    premier, complet, _ = lister()
    assert complet and len(premier) == 2 + len(NOMS_PIEGES)
    vu_a = datetime.now()
    for fichier in (distant / "Téléchargements").rglob("*"):
        if fichier.is_file():
            os.utime(fichier, (vu_a.timestamp() - 3600, vu_a.timestamp() - 3600))
    time.sleep(0.05)
    (distant / "Téléchargements" / "nouveau.pdf").write_bytes(b"neuf")
    second, _, _ = lister(derniere=vu_a)
    assert [c.relatif for c in second] == ["nouveau.pdf"]


def test_un_vieux_fichier_est_filtre_par_la_date(distant):
    ancien = time.time() - 400 * 86400
    os.utime(distant / "Téléchargements" / "a.pdf", (ancien, ancien))
    assert "a.pdf" not in {c.relatif for c in lister()[0]}


def test_expression_distante_cite_le_repertoire():
    assert scanner_ssh.expression_distante("~/a b") == '"$HOME"/\'a b\''
    assert scanner_ssh.expression_distante("/x y; z", "i'l.pdf") == "'/x y; z'/'i'\"'\"'l.pdf'"
