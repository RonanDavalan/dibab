# Tests du module journal — écriture JSONL de session.

import json

from modules import journal


def test_journal_ajout_simple(tmp_path):
    chemin = tmp_path / "session_test.jsonl"
    j = journal.JournalSession(chemin, "2026-05-18T22:00:00")
    j.ajouter("evenement_test", cle1="valeur1", cle2=42)

    lignes = chemin.read_text(encoding="utf-8").strip().split("\n")
    assert len(lignes) == 1
    enregistrement = json.loads(lignes[0])
    assert enregistrement["session"] == "2026-05-18T22:00:00"
    assert enregistrement["evenement"] == "evenement_test"
    assert enregistrement["cle1"] == "valeur1"
    assert enregistrement["cle2"] == 42
    assert "timestamp" in enregistrement


def test_journal_plusieurs_ajouts(tmp_path):
    chemin = tmp_path / "session_test.jsonl"
    j = journal.JournalSession(chemin, "id-session")
    j.ajouter("a")
    j.ajouter("b")
    j.ajouter("c")
    lignes = chemin.read_text(encoding="utf-8").strip().split("\n")
    assert len(lignes) == 3


def test_journal_cree_dossier_parent(tmp_path):
    chemin = tmp_path / "sous" / "dossier" / "session.jsonl"
    j = journal.JournalSession(chemin, "id")
    j.ajouter("ok")
    assert chemin.exists()


def test_journal_supporte_accents(tmp_path):
    chemin = tmp_path / "s.jsonl"
    j = journal.JournalSession(chemin, "id")
    j.ajouter("evenement", chemin="Téléchargements/résumé.pdf")
    contenu = chemin.read_text(encoding="utf-8")
    assert "Téléchargements" in contenu
    assert "résumé" in contenu
