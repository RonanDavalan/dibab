# Tests du module scanner_local — fonctions critiques de filtrage.

import os
from datetime import datetime, timedelta
from pathlib import Path

from modules import scanner_local


def test_normaliser_extensions_minuscule():
    assert scanner_local.normaliser_extensions([".PDF", ".Jpg", ".png"]) == {".pdf", ".jpg", ".png"}


def test_extension_acceptee_insensible_casse():
    extensions = scanner_local.normaliser_extensions([".pdf", ".png"])
    assert scanner_local.extension_acceptee(Path("doc.PDF"), extensions)
    assert scanner_local.extension_acceptee(Path("img.png"), extensions)
    assert not scanner_local.extension_acceptee(Path("note.txt"), extensions)


def test_date_seuil_premier_scan():
    maintenant = datetime(2026, 5, 18, 12, 0, 0)
    seuil = scanner_local.date_seuil(None, 1, 90, maintenant)
    assert seuil == maintenant - timedelta(days=90)


def test_date_seuil_avec_derniere_date():
    maintenant = datetime(2026, 5, 18, 12, 0, 0)
    derniere = datetime(2026, 5, 15, 8, 0, 0)
    seuil = scanner_local.date_seuil(derniere, 1, 90, maintenant)
    assert seuil == derniere - timedelta(days=1)


def test_fabriquer_exclusions_combine():
    scan_global = {"exclusions_automatiques": ["rebut", "doublon"]}
    source = {"exclusions": ["archives"]}
    exclusions = scanner_local.fabriquer_exclusions(scan_global, source)
    assert exclusions == {"rebut", "doublon", "archives"}


def test_determiner_recursif_defaut_global():
    scan_global = {"recursif_par_defaut": True}
    source = {}
    assert scanner_local.determiner_recursif(scan_global, source) is True


def test_determiner_recursif_surcharge_source():
    scan_global = {"recursif_par_defaut": True}
    source = {"recursif": False}
    assert scanner_local.determiner_recursif(scan_global, source) is False


def test_parcours_recursif_exclut_dossiers(tmp_path):
    (tmp_path / "ok.pdf").write_text("a")
    (tmp_path / "rebut").mkdir()
    (tmp_path / "rebut" / "ignore.pdf").write_text("b")
    (tmp_path / "sous_dossier").mkdir()
    (tmp_path / "sous_dossier" / "garde.pdf").write_text("c")

    fichiers = list(scanner_local.parcourir(
        racine=tmp_path,
        recursif=True,
        exclusions={"rebut", "doublon"},
        ignorer_dotfiles=True,
        suivre_symlinks=False,
    ))
    noms = {f.name for f in fichiers}
    assert "ok.pdf" in noms
    assert "garde.pdf" in noms
    assert "ignore.pdf" not in noms


def test_parcours_ignore_dotfiles(tmp_path):
    (tmp_path / "ok.pdf").write_text("a")
    (tmp_path / ".cache").mkdir()
    (tmp_path / ".cache" / "ignore.pdf").write_text("b")
    (tmp_path / ".fichier_cache.pdf").write_text("c")

    fichiers = list(scanner_local.parcourir(
        racine=tmp_path,
        recursif=True,
        exclusions=set(),
        ignorer_dotfiles=True,
        suivre_symlinks=False,
    ))
    noms = {f.name for f in fichiers}
    assert noms == {"ok.pdf"}


def test_parcours_plat_n_explore_pas_sous_dossiers(tmp_path):
    (tmp_path / "ok.pdf").write_text("a")
    (tmp_path / "sous").mkdir()
    (tmp_path / "sous" / "ignore.pdf").write_text("b")

    fichiers = list(scanner_local.parcourir(
        racine=tmp_path,
        recursif=False,
        exclusions=set(),
        ignorer_dotfiles=True,
        suivre_symlinks=False,
    ))
    noms = {f.name for f in fichiers}
    assert noms == {"ok.pdf"}


def test_scanner_source_source_inexistante(tmp_path):
    source = {"id": "test", "chemin": str(tmp_path / "inexistant")}
    scan_global = {}
    candidats, stats = scanner_local.scanner_source(
        source=source,
        scan_global=scan_global,
        extensions_cibles=[".pdf"],
        derniere_date=None,
        securite_jours=1,
        premier_scan_jours=90,
    )
    assert candidats == []
    assert stats["existe"] is False
    assert stats["candidats"] == 0


def test_scanner_source_filtre_par_date_et_extension(tmp_path):
    # Fichier récent .pdf : doit être inclus
    recent_pdf = tmp_path / "recent.pdf"
    recent_pdf.write_text("a")
    # Fichier récent .txt : doit être exclu (extension)
    recent_txt = tmp_path / "recent.txt"
    recent_txt.write_text("b")
    # Fichier ancien .pdf : doit être exclu (date)
    ancien_pdf = tmp_path / "ancien.pdf"
    ancien_pdf.write_text("c")
    vieux_ts = (datetime.now() - timedelta(days=200)).timestamp()
    os.utime(ancien_pdf, (vieux_ts, vieux_ts))

    source = {"id": "test", "chemin": str(tmp_path)}
    scan_global = {
        "recursif_par_defaut": True,
        "exclusions_automatiques": ["rebut", "doublon"],
        "ignorer_dotfiles": True,
        "suivre_symlinks": False,
    }
    candidats, stats = scanner_local.scanner_source(
        source=source,
        scan_global=scan_global,
        extensions_cibles=[".pdf"],
        derniere_date=None,
        securite_jours=1,
        premier_scan_jours=90,
    )
    noms = {c.chemin.name for c in candidats}
    assert noms == {"recent.pdf"}
    assert stats["candidats"] == 1
