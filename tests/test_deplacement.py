"""Déplacement sûr : copie, vérification SHA256, retrait de la source, jamais d'écrasement."""

import shutil
from datetime import date, datetime

import pytest

from modules import classement, deplacement
from modules.domaines import Verdict
from modules.pieces_communes import empreinte_sha256
from tests.test_classement import REPLI, config  # noqa: F401
from tests.textes_factices import TEXTES  # noqa: F401


def piece(tmp_path, contenu=b"contenu factice", nom="scan.pdf"):
    chemin = tmp_path / "source" / nom
    chemin.parent.mkdir(exist_ok=True)
    chemin.write_bytes(contenu)
    return chemin


def plan_de(source, config, domaine="personnel", categorie="CAF", **champs):
    verdict = Verdict(True, domaine, categorie, emetteur="Organisme", personne="Personne1", date=date(2026, 3, 15), **champs)
    return classement.planifier(source, verdict, config, REPLI)


def fichiers(racine):
    return sorted(str(p.relative_to(racine)) for p in racine.rglob("*") if p.is_file())


def test_copie_verifiee_puis_retrait_de_la_source(tmp_path, config):  # noqa: F811
    source = piece(tmp_path)
    plan = plan_de(source, config)
    resultat = deplacement.deplacer(source, plan, config, deplacement.Registre())
    assert resultat.action == deplacement.CLASSE and not source.exists()
    assert plan.chemins[0].read_bytes() == b"contenu factice"
    assert resultat.empreinte == empreinte_sha256(plan.chemins[0])
    assert fichiers(tmp_path / "a") == ["Rangement/Personne1/2026/2026-03-15_Organisme_CAF.pdf"]


def test_copie_interrompue_laisse_la_source_et_aucune_copie(tmp_path, config):  # noqa: F811
    source = piece(tmp_path)

    def copie_coupee(origine, destination):
        destination.write_bytes(b"cont")
        raise OSError("disque plein")

    resultat = deplacement.deplacer(source, plan_de(source, config), config, deplacement.Registre(), copie_coupee)
    assert resultat.action == deplacement.ECHEC and "disque plein" in resultat.raison
    assert source.read_bytes() == b"contenu factice"
    assert fichiers(tmp_path / "a") == []


def test_interruption_clavier_nettoie_la_copie_partielle(tmp_path, config):  # noqa: F811
    source = piece(tmp_path)

    def interrompue(origine, destination):
        destination.write_bytes(b"cont")
        raise KeyboardInterrupt

    with pytest.raises(KeyboardInterrupt):
        deplacement.deplacer(source, plan_de(source, config), config, deplacement.Registre(), interrompue)
    assert source.exists() and fichiers(tmp_path / "a") == []


def test_copie_corrompue_n_est_pas_acceptee(tmp_path, config):  # noqa: F811
    source = piece(tmp_path)

    def copie_fausse(origine, destination):
        destination.write_bytes(b"autre contenu")

    resultat = deplacement.deplacer(source, plan_de(source, config), config, deplacement.Registre(), copie_fausse)
    assert resultat.action == deplacement.ECHEC and "empreinte" in resultat.raison
    assert source.exists() and fichiers(tmp_path / "a") == []


def test_source_modifiee_pendant_la_copie_reste_en_place(tmp_path, config):  # noqa: F811
    source = piece(tmp_path)

    def copie_puis_modification(origine, destination):
        shutil.copy2(origine, destination)
        origine.write_bytes(b"telechargement en cours")

    resultat = deplacement.deplacer(source, plan_de(source, config), config, deplacement.Registre(), copie_puis_modification)
    assert resultat.action == deplacement.ECHEC
    assert source.read_bytes() == b"telechargement en cours" and fichiers(tmp_path / "a") == []


def test_collision_de_nom_suffixe_sans_ecraser(tmp_path, config):  # noqa: F811
    premier, second, troisieme = (piece(tmp_path, contenu=c, nom=n) for c, n in ((b"un", "1.pdf"), (b"deux", "2.pdf"), (b"trois", "3.pdf")))
    registre = deplacement.Registre()
    for source in (premier, second, troisieme):
        assert deplacement.deplacer(source, plan_de(source, config), config, registre).action == deplacement.CLASSE
    zone = tmp_path / "a/Rangement/Personne1/2026"
    assert (zone / "2026-03-15_Organisme_CAF.pdf").read_bytes() == b"un"
    assert (zone / "2026-03-15_Organisme_CAF_2.pdf").read_bytes() == b"deux"
    assert (zone / "2026-03-15_Organisme_CAF_3.pdf").read_bytes() == b"trois"


def test_doublon_d_une_empreinte_deja_classee_part_dans_doublon(tmp_path, config):  # noqa: F811
    existant = tmp_path / "a/Rangement/Ancien/2019/ancien.pdf"
    existant.parent.mkdir(parents=True)
    existant.write_bytes(b"contenu factice")
    source = piece(tmp_path)
    resultat = deplacement.deplacer(source, plan_de(source, config), config, deplacement.Registre())
    assert resultat.action == deplacement.DOUBLON and not source.exists()
    assert fichiers(tmp_path / "a") == ["Rangement/Ancien/2019/ancien.pdf", "doublon/2026-03-15_Organisme_CAF.pdf"]
    assert existant.read_bytes() == b"contenu factice"


def test_doublon_dans_le_meme_lot(tmp_path, config):  # noqa: F811
    registre = deplacement.Registre()
    premier, copie = piece(tmp_path, nom="1.pdf"), piece(tmp_path, nom="2.pdf")
    assert deplacement.deplacer(premier, plan_de(premier, config), config, registre).action == deplacement.CLASSE
    assert deplacement.deplacer(copie, plan_de(copie, config), config, registre).action == deplacement.DOUBLON


def test_doublon_en_collision_de_nom_est_suffixe_aussi(tmp_path, config):  # noqa: F811
    registre = deplacement.Registre()
    premier = piece(tmp_path, nom="1.pdf")
    deplacement.deplacer(premier, plan_de(premier, config), config, registre)
    for nom in ("2.pdf", "3.pdf"):
        copie = piece(tmp_path, nom=nom)
        assert deplacement.deplacer(copie, plan_de(copie, config), config, registre).action == deplacement.DOUBLON
    assert fichiers(tmp_path / "a/doublon") == ["2026-03-15_Organisme_CAF.pdf", "2026-03-15_Organisme_CAF_2.pdf"]


def test_piece_commune_est_copiee_dans_les_deux_coffres(tmp_path, config):  # noqa: F811
    source = piece(tmp_path, nom="identite.pdf")
    plan = plan_de(source, config, categorie="Identité")
    resultat = deplacement.deplacer(source, plan, config, deplacement.Registre())
    assert resultat.action == deplacement.CLASSE and len(resultat.destinations) == 2 and not source.exists()
    assert {empreinte_sha256(chemin) for chemin in plan.chemins} == {resultat.empreinte}


def test_piece_commune_deja_presente_d_un_cote_n_est_copiee_que_de_l_autre(tmp_path, config):  # noqa: F811
    source = piece(tmp_path, nom="identite.pdf")
    plan = plan_de(source, config, categorie="Identité")
    plan.chemins[0].parent.mkdir(parents=True)
    plan.chemins[0].write_bytes(source.read_bytes())
    resultat = deplacement.deplacer(source, plan, config, deplacement.Registre())
    assert resultat.destinations == (plan.chemins[1],) and not source.exists()


def test_a_verifier_garde_son_prefixe_et_reste_a_plat(tmp_path, config):  # noqa: F811
    source = piece(tmp_path)
    verdict = Verdict(True, "incertain", "Inconnue")
    plan = classement.planifier(source, verdict, config, datetime(2024, 7, 9))
    resultat = deplacement.deplacer(source, plan, config, deplacement.Registre())
    assert resultat.action == deplacement.A_VERIFIER
    assert fichiers(tmp_path / "a") == ["Tri/[AV]scan.pdf"]


def test_prevoir_ne_touche_a_rien(tmp_path, config):  # noqa: F811
    source = piece(tmp_path)
    assert deplacement.prevoir(source, plan_de(source, config), config, deplacement.Registre()) == deplacement.CLASSE
    assert source.exists() and fichiers(tmp_path / "a") == []
