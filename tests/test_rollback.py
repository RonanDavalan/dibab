"""Journal des actions, rapport de session, rollback et rotation, par la ligne de commande sur le lot factice."""

import hashlib
import json
from pathlib import Path

import pytest

import skrivagner
from modules import journal_actions, rotation
from tests.test_classement_execute import LOT, TEXTE_IDENTITE, TEXTES, arbre, banc, lancer  # noqa: F401


def empreintes(racine):
    return {str(p.relative_to(racine)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in racine.rglob("*") if p.is_file() and "logs" not in p.relative_to(racine).parts}


def etat(racine):
    return {nom: empreintes(racine / nom) for nom in ("source", "coffre-a", "coffre-b")}


def lignes_journal(racine):
    return journal_actions.lire_lignes(racine / "coffre-a" / "logs" / "journal.jsonl")


def test_execute_ecrit_une_ligne_par_deplacement_avec_schema_et_empreintes(banc, monkeypatch):
    racine, _ = banc
    lancer(monkeypatch, "--execute")
    actions = [ligne for ligne in lignes_journal(racine) if ligne["evenement"] == "action"]
    assert len(actions) == 7
    assert all(a["schema_version"] == 1 and a["empreinte_avant"] and a["id_action"] for a in actions)
    assert all(d["empreinte_apres"] == a["empreinte_avant"] for a in actions for d in a["destinations"])
    assert sorted(len(a["destinations"]) for a in actions).count(2) == 1  # la pièce commune est une seule action
    assert oct((racine / "coffre-a" / "logs" / "journal.jsonl").stat().st_mode & 0o777) == "0o600"


def test_le_journal_et_le_rapport_ne_portent_ni_texte_ni_nom_de_document(banc, monkeypatch):
    racine, _ = banc
    lancer(monkeypatch, "--execute")
    rapport = next((racine / "coffre-a" / "logs" / "sessions").glob("rapport_*.json"))
    brut = rapport.read_text(encoding="utf-8")
    donnees = json.loads(brut)
    assert donnees["schema_version"] == 1 and donnees["mode"] == "execute" and donnees["duree_secondes"] >= 0
    assert donnees["actions"]["classe"] + donnees["actions"]["a_verifier"] + donnees["actions"]["doublon"] == 7
    assert not any(nom.removesuffix(".pdf") in brut for nom in LOT)
    journal = (racine / "coffre-a" / "logs" / "journal.jsonl").read_text(encoding="utf-8")
    assert TEXTES[0]["reponse"]["destinataire"] not in journal and TEXTE_IDENTITE not in journal


def test_execute_puis_rollback_restitue_l_etat_initial(banc, monkeypatch, capsys):
    racine, _ = banc
    avant = etat(racine)
    lancer(monkeypatch, "--execute")
    assert etat(racine) != avant
    assert lancer(monkeypatch, "--rollback") == 0
    assert etat(racine) == avant
    assert "7 annulée(s), 0 en échec" in capsys.readouterr().out
    assert journal_actions.actions_actives(lignes_journal(racine)) == []
    assert sum(ligne["evenement"] == "annulation" for ligne in lignes_journal(racine)) == 7


def test_une_action_deja_annulee_n_est_pas_rejouee(banc, monkeypatch, capsys):
    racine, _ = banc
    lancer(monkeypatch, "--execute")
    lancer(monkeypatch, "--rollback")
    capsys.readouterr()
    assert lancer(monkeypatch, "--rollback") == 0
    assert "0 annulée(s), 0 en échec" in capsys.readouterr().out


def test_destination_modifiee_rien_n_est_retire(banc, monkeypatch):
    racine, _ = banc
    lancer(monkeypatch, "--execute")
    classe = next(p for p in (racine / "coffre-b").rglob("*Factures*") if p.is_file())
    classe.write_bytes(b"retouche")
    apres_execute = etat(racine)
    assert lancer(monkeypatch, "--rollback") == 1
    restant = etat(racine)
    assert restant["coffre-b"][str(classe.relative_to(racine / "coffre-b"))] == hashlib.sha256(b"retouche").hexdigest()
    assert len(journal_actions.actions_actives(lignes_journal(racine))) == 1
    assert [ligne for ligne in lignes_journal(racine) if ligne["evenement"] == "echec_annulation"][0]["raison"].startswith("destination modifiée")
    assert restant["source"].keys() >= {k for k in apres_execute["source"]}


def test_source_reoccupee_rien_n_est_retire(banc, monkeypatch):
    racine, _ = banc
    lancer(monkeypatch, "--execute")
    (racine / "source" / "pro.pdf").write_text("autre contenu", encoding="utf-8")
    avant = etat(racine)
    assert lancer(monkeypatch, "--rollback") == 1
    assert etat(racine)["source"]["pro.pdf"] == avant["source"]["pro.pdf"]
    assert len(journal_actions.actions_actives(lignes_journal(racine))) == 1


def test_piece_commune_une_copie_modifiee_aucune_n_est_retiree(banc, monkeypatch):
    racine, _ = banc
    lancer(monkeypatch, "--execute")
    copies = sorted(racine.rglob("*Identité.pdf"))
    copies[0].write_bytes(b"retouche")
    assert lancer(monkeypatch, "--rollback") == 1
    assert all(copie.exists() for copie in copies)
    assert not (racine / "source" / "identite.pdf").exists()


def test_rollback_coffre_ferme_ne_touche_a_rien(banc, monkeypatch):
    racine, _ = banc
    lancer(monkeypatch, "--execute")
    monkeypatch.setattr(skrivagner.mod_coffres, "type_systeme_fichiers", lambda racine, executer=None: "ext4")
    avant = etat(racine)
    with pytest.raises(SystemExit) as sortie:
        lancer(monkeypatch, "--rollback")
    assert sortie.value.code == 2 and etat(racine) == avant


def test_rollback_d_une_session_nommee(banc, monkeypatch):
    racine, _ = banc
    lancer(monkeypatch, "--execute")
    session = next(ligne["session"] for ligne in lignes_journal(racine) if ligne["evenement"] == "action")
    avant = etat(racine)
    assert lancer(monkeypatch, "--rollback", "--session", "autre-session") == 0
    assert etat(racine) == avant
    assert lancer(monkeypatch, "--rollback", "--session", session) == 0
    assert len(journal_actions.actions_actives(lignes_journal(racine))) == 0


def test_une_action_archivee_se_relit_et_s_annule(banc, monkeypatch):
    racine, chemin_config = banc
    avant = etat(racine)
    lancer(monkeypatch, "--execute")
    chemin = racine / "coffre-a" / "logs" / "journal.jsonl"
    assert rotation.tourner_journal(chemin, taille_max_mo=0, archives_max=5)
    assert not chemin.exists() and (chemin.parent / "journal.1.jsonl").exists()
    assert lancer(monkeypatch, "--rollback") == 0
    assert etat(racine) == avant


def test_rotation_numerote_les_archives_et_garde_une_action_active(tmp_path):
    chemin = tmp_path / "journal.jsonl"
    journal = journal_actions.JournalActions(chemin, "s1")

    class Faux:
        action, source, empreinte = "classe", tmp_path / "o", "a" * 64
        destinations = ()

    for n in range(3):
        journal.enregistrer_deplacement(Faux, "personnel")
        assert rotation.tourner_journal(chemin, 0, archives_max=2) == (n < 2)
    assert sorted(p.name for p in tmp_path.glob("journal*")) == ["journal.1.jsonl", "journal.2.jsonl", "journal.jsonl"]


def test_purge_des_sessions_garde_les_plus_recentes(tmp_path):
    for n in range(5):
        (tmp_path / f"session_2026-10-0{n}T00:00:00.jsonl").write_text("{}")
        (tmp_path / f"rapport_2026-10-0{n}T00:00:00.json").write_text("{}")
    assert rotation.purger_sessions(tmp_path, 3) == 4
    assert sorted(p.name for p in tmp_path.glob("session_*"))[0].startswith("session_2026-10-02")
