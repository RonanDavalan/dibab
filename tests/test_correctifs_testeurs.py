"""Défauts remis par les testeurs-découverte : droits du coffre, identifiant de session, inventaire de À_VÉRIFIER."""

import stat

import dibab
from modules import deplacement, inventaire
from modules.pieces_communes import empreinte_sha256


def _mode(chemin):
    return stat.S_IMODE(chemin.stat().st_mode)


def test_les_dossiers_crees_dans_le_coffre_sont_en_700(tmp_path):
    cible = tmp_path / "coffre" / "Administratif" / "Alice" / "2026"
    deplacement.creer_dossiers_prives(cible)
    for dossier in (cible, cible.parent, cible.parent.parent, tmp_path / "coffre"):
        assert _mode(dossier) == 0o700


def test_un_dossier_existant_n_est_pas_modifie(tmp_path):
    existant = tmp_path / "coffre"
    existant.mkdir(mode=0o750)
    existant.chmod(0o750)
    deplacement.creer_dossiers_prives(existant / "neuf")
    assert _mode(existant) == 0o750
    assert _mode(existant / "neuf") == 0o700


def test_le_document_classe_est_en_600_meme_si_la_source_est_en_664(tmp_path):
    source = tmp_path / "source.pdf"
    source.write_bytes(b"%PDF contenu")
    source.chmod(0o664)
    destination = tmp_path / "coffre" / "Administratif" / "document.pdf"
    deplacement.copier_verifie(source, destination, empreinte_sha256(source))
    assert _mode(destination) == 0o600
    assert _mode(destination.parent) == 0o700


def test_deux_sessions_de_la_meme_seconde_ont_chacune_leur_identifiant(tmp_path):
    horodatage = "2026-11-24T09:21:13"
    premier = dibab.identifiant_session_unique(tmp_path, horodatage)
    assert premier == horodatage
    (tmp_path / f"session_{premier}.jsonl").write_text("{}\n")
    second = dibab.identifiant_session_unique(tmp_path, horodatage)
    assert second == f"{horodatage}-2"
    (tmp_path / f"rapport_{second}.json").write_text("{}")
    assert dibab.identifiant_session_unique(tmp_path, horodatage) == f"{horodatage}-3"


def test_le_plan_compte_les_documents_de_a_verifier(tmp_path):
    a_verifier = tmp_path / "À_VÉRIFIER"
    a_verifier.mkdir()
    (a_verifier / "courrier.pdf").write_bytes(b"x")
    (a_verifier / "notes.txt").write_bytes(b"x")
    (a_verifier / ".cache.pdf").write_bytes(b"x")
    assert inventaire.compter_a_verifier(tmp_path, "À_VÉRIFIER", {".pdf"}) == 1
    assert inventaire.compter_a_verifier(tmp_path, "absent", {".pdf"}) == 0
