"""Tests de modules/coffres.py sur un `findmnt` simulé."""

import os
import subprocess

from modules import coffres


def faux_findmnt(type_rendu, code=0):
    appels = []

    def executer(commande, **options):
        appels.append(commande)
        return subprocess.CompletedProcess(commande, code, stdout=f"{type_rendu}\n", stderr="")

    executer.appels = appels
    return executer


def test_coffre_monte(tmp_path):
    executer = faux_findmnt("fuse.gocryptfs")
    etat = coffres.verifier_coffre("personnel", tmp_path, executer)
    assert etat.monte and etat.raison == ""
    assert executer.appels == [["findmnt", "-n", "-T", str(tmp_path), "-o", "FSTYPE"]]


def test_coffre_ferme_est_un_autre_type(tmp_path):
    etat = coffres.verifier_coffre("personnel", tmp_path, faux_findmnt("ext4"))
    assert not etat.monte
    assert "ext4" in etat.raison and "fuse.gocryptfs" in etat.raison


def test_findmnt_en_echec(tmp_path):
    etat = coffres.verifier_coffre("personnel", tmp_path, faux_findmnt("", code=1))
    assert not etat.monte and "inconnu" in etat.raison


def test_findmnt_absent(tmp_path):
    def absent(commande, **options):
        raise FileNotFoundError("findmnt")

    assert not coffres.verifier_coffre("personnel", tmp_path, absent).monte


def test_racine_introuvable(tmp_path):
    executer = faux_findmnt("fuse.gocryptfs")
    etat = coffres.verifier_coffre("personnel", tmp_path / "absent", executer)
    assert not etat.monte and "introuvable" in etat.raison
    assert executer.appels == []


def test_racine_non_inscriptible(tmp_path):
    tmp_path.chmod(0o500)
    try:
        if os.access(tmp_path, os.W_OK):
            return  # exécuté en superutilisateur : la permission ne retient rien
        etat = coffres.verifier_coffre("personnel", tmp_path, faux_findmnt("fuse.gocryptfs"))
    finally:
        tmp_path.chmod(0o700)
    assert not etat.monte and "écriture" in etat.raison


def test_verifier_coffres_rend_un_etat_par_domaine(tmp_path):
    (tmp_path / "a").mkdir()
    (tmp_path / "b").mkdir()
    etats = coffres.verifier_coffres(
        {"personnel": {"racine": str(tmp_path / "a")}, "professionnel": {"racine": str(tmp_path / "b")}},
        faux_findmnt("fuse.gocryptfs"))
    assert [(e.domaine, e.monte) for e in etats] == [("personnel", True), ("professionnel", True)]


def test_coffre_non_monte_contenant(tmp_path):
    ferme = coffres.EtatCoffre("personnel", tmp_path / "a", False, "fermé")
    ouvert = coffres.EtatCoffre("professionnel", tmp_path / "b", True)
    etats = [ferme, ouvert]
    assert coffres.coffre_non_monte_contenant(tmp_path / "a" / "logs" / "s.jsonl", etats) is ferme
    assert coffres.coffre_non_monte_contenant(tmp_path / "b" / "logs", etats) is None
    assert coffres.coffre_non_monte_contenant(tmp_path / "ailleurs", etats) is None
    assert coffres.coffre_non_monte_contenant(tmp_path / "a-voisin", etats) is None
