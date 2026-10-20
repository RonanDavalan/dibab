"""Tests de modules/nommage.py et modules/pieces_communes.py sur des fichiers factices."""

import hashlib
from datetime import date, datetime

import pytest

from modules import pieces_communes
from modules.domaines import Verdict
from modules.nommage import nommer

NOMMAGE = {
    "format": "{date}_{emetteur}_{categorie}{ext}",
    "date_format": "%Y-%m-%d",
    "date_inconnue_prefixe": "~",
    "emetteur_inconnu": "Inconnu",
    "espaces_vers": "-",
    "prefixe_a_verifier": "[À_VÉRIFIER]",
}


def configuration(tmp_path):
    return {
        "nommage": NOMMAGE,
        "pieces_communes": ["Identité"],
        "destinations": {
            "personnel": {"racine": str(tmp_path / "coffre-a"), "sous_repertoire_classement": "Rangement",
                          "sous_repertoire_a_verifier": "Tri"},
            "professionnel": {"racine": str(tmp_path / "coffre-b"), "sous_repertoire_classement": "Dossiers",
                              "sous_repertoire_a_verifier": "Tri"},
        },
    }


def piece(tmp_path, contenu=b"contenu factice", nom="scan.PDF"):
    source = tmp_path / "source" / nom
    source.parent.mkdir(exist_ok=True)
    source.write_bytes(contenu)
    return source


def test_nom_normalise():
    verdict = Verdict(True, "personnel", "Factures", emetteur="Fournisseur X", date=date(2026, 5, 15))
    assert nommer(NOMMAGE, verdict, ".PDF", datetime(2020, 1, 1)) == "2026-05-15_Fournisseur-X_Factures.pdf"


def test_nom_date_inconnue_et_emetteur_inconnu():
    verdict = Verdict(True, "personnel", "CAF")
    assert nommer(NOMMAGE, verdict, ".pdf", datetime(2026, 3, 2)) == "~2026-03-02_Inconnu_CAF.pdf"


def test_nom_a_verifier_porte_le_prefixe():
    verdict = Verdict(True, "mixte", "Impôts", emetteur="Fisc", date=date(2026, 5, 15))
    assert nommer(NOMMAGE, verdict, ".pdf", None, a_verifier=True).startswith("[À_VÉRIFIER]2026-05-15_")


def test_nom_sans_separateur_de_chemin():
    verdict = Verdict(True, "personnel", "Factures", emetteur="../../x/y", date=date(2026, 5, 15))
    assert "/" not in nommer(NOMMAGE, verdict, ".pdf", None)


def test_piece_commune_deux_chemins_meme_nom_meme_empreinte(tmp_path):
    source = piece(tmp_path)
    verdict = Verdict(True, "incertain", "Identité", emetteur="Prefecture", date=date(2026, 1, 9))
    plan = pieces_communes.planifier(source, verdict, configuration(tmp_path), datetime.now())

    assert plan.nom == "2026-01-09_Prefecture_Identité.pdf"
    assert plan.chemins == (tmp_path / "coffre-a" / "Rangement" / plan.nom,
                            tmp_path / "coffre-b" / "Dossiers" / plan.nom)
    attendue = hashlib.sha256(b"contenu factice").hexdigest()
    assert plan.empreinte == attendue

    pieces_communes.copier_verifier(source, plan)
    empreintes = {hashlib.sha256(chemin.read_bytes()).hexdigest() for chemin in plan.chemins}
    assert empreintes == {attendue}
    assert source.read_bytes() == b"contenu factice"


def test_document_ordinaire_un_seul_chemin_sans_empreinte(tmp_path):
    source = piece(tmp_path)
    verdict = Verdict(True, "professionnel", "Factures", emetteur="Client", date=date(2026, 2, 1))
    plan = pieces_communes.planifier(source, verdict, configuration(tmp_path), datetime.now())
    assert plan.chemins == (tmp_path / "coffre-b" / "Dossiers" / "2026-02-01_Client_Factures.pdf",)
    assert plan.empreinte is None


def test_document_a_verifier_va_dans_le_dossier_a_verifier(tmp_path):
    source = piece(tmp_path)
    verdict = Verdict(True, "mixte", "Impôts", emetteur="Fisc", date=date(2026, 2, 1))
    plan = pieces_communes.planifier(source, verdict, configuration(tmp_path), datetime.now())
    assert plan.chemins == (tmp_path / "coffre-b" / "Tri" / "[À_VÉRIFIER]2026-02-01_Fisc_Impôts.pdf",)


def test_non_administratif_sans_plan(tmp_path):
    verdict = Verdict(False, "personnel", "Loisir")
    assert pieces_communes.planifier(piece(tmp_path), verdict, configuration(tmp_path), datetime.now()) is None


def test_copie_n_ecrase_rien(tmp_path):
    source = piece(tmp_path)
    verdict = Verdict(True, "personnel", "Identité", emetteur="Prefecture", date=date(2026, 1, 9))
    plan = pieces_communes.planifier(source, verdict, configuration(tmp_path), datetime.now())
    plan.chemins[1].parent.mkdir(parents=True)
    plan.chemins[1].write_bytes(b"existant")

    with pytest.raises(pieces_communes.ErreurCopie):
        pieces_communes.copier_verifier(source, plan)
    assert plan.chemins[1].read_bytes() == b"existant"
    assert not plan.chemins[0].exists()


def test_copie_corrompue_retiree_et_source_intacte(tmp_path, monkeypatch):
    source = piece(tmp_path)
    verdict = Verdict(True, "personnel", "Identité", emetteur="Prefecture", date=date(2026, 1, 9))
    plan = pieces_communes.planifier(source, verdict, configuration(tmp_path), datetime.now())

    def copie_tronquee(origine, destination):
        destination.write_bytes(b"tronque")

    monkeypatch.setattr(pieces_communes.shutil, "copy2", copie_tronquee)
    with pytest.raises(pieces_communes.ErreurCopie):
        pieces_communes.copier_verifier(source, plan)
    assert not any(chemin.exists() for chemin in plan.chemins)
    assert source.read_bytes() == b"contenu factice"
