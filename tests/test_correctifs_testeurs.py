"""Défauts remis par les testeurs-découverte : droits du coffre, identifiant de session, inventaire de À_VÉRIFIER."""

import hashlib
import json
import os
import socket
import stat
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

import pytest

import dibab
from modules import deplacement, inventaire, journal_actions, messages, rapatriement, rollback, sources_imap, verrou
from modules.pieces_communes import empreinte_sha256
from tests.test_classement_execute import banc, lancer  # noqa: F401


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


def test_le_verrou_pris_dit_que_le_processus_vit_et_son_nom(tmp_path):
    chemin = tmp_path / "dibab.verrou"
    with verrou.verrou(chemin):
        with pytest.raises(verrou.VerrouPris) as refus:
            with verrou.verrou(chemin):
                pass
    nom = Path("/proc/self/comm").read_text(encoding="utf-8").strip()
    assert str(os.getpid()) in str(refus.value)
    assert nom in str(refus.value)


@pytest.mark.parametrize("langue", messages.LANGUES)
def test_la_ligne_d_inventaire_nomme_a_verifier_et_son_compte(langue):
    ligne = messages.dictionnaire(langue)["inventaire_coffre"].format(
        domaine="personnel", documents=4, conserver=3, a_classer=1, doublons=1, presents=1, a_verifier=7)
    assert "À_VÉRIFIER" in ligne and "7" in ligne


@pytest.mark.parametrize("langue", messages.LANGUES)
def test_le_message_du_doublon_dit_que_la_source_est_retiree(langue):
    texte = messages.dictionnaire(langue)["classement_doublon"].format(nom="facture.pdf")
    assert "doublon/" in texte and "facture.pdf" in texte


def test_le_journal_et_le_suivi_sont_prives(tmp_path):
    from datetime import datetime
    from modules import journal, journal_actions, rapport, suivi

    ancien = os.umask(0o002)
    try:
        etat = tmp_path / "coffre" / "suivi"
        session = etat / "sessions" / "session_a.jsonl"
        journal.JournalSession(session, "a").ajouter("essai")
        suivi.sauvegarder(etat / "dernier_scan.json", {"source": datetime(2026, 11, 24)})
        journal_actions.JournalActions(etat / "journal.jsonl", "a")
        rapport.Rapport("a", "execute").ecrire(etat / "sessions")
    finally:
        os.umask(ancien)
    for dossier in (etat, etat / "sessions"):
        assert _mode(dossier) == 0o700
    for fichier in (session, etat / "dernier_scan.json", etat / "sessions" / "rapport_a.json"):
        assert _mode(fichier) == 0o600


def test_deux_plans_de_la_meme_seconde_ont_deux_fichiers(tmp_path):
    plan = {"horodatage": "2026-11-24T16:44:29", "actions": []}
    dossier = tmp_path / "logs"
    deplacement.creer_dossiers_prives(dossier)
    premier = inventaire._ecrire_sans_ecraser(dossier, "inventaire_2026-11-24T16-44-29", plan)
    second = inventaire._ecrire_sans_ecraser(dossier, "inventaire_2026-11-24T16-44-29", plan)
    assert premier.name == "inventaire_2026-11-24T16-44-29.json"
    assert second.name == "inventaire_2026-11-24T16-44-29_2.json"
    assert _mode(second) == 0o600


def test_le_dossier_d_une_source_ssh_est_en_700_meme_sous_un_umask_ouvert(tmp_path):
    contenu = b"%PDF distant"
    empreinte = hashlib.sha256(contenu).hexdigest()
    fichier = SimpleNamespace(source_id="machine1", alias="machine1", repertoire="/docs", relatif="a.pdf", nom="a.pdf",
                              taille_octets=len(contenu), mtime=datetime(2026, 11, 24, 10, 0, 0))

    def executer(alias, commande):
        return SimpleNamespace(returncode=0, stdout=f"{empreinte}  a.pdf\n".encode())

    def copier(alias, commande, stdout):
        stdout.write(contenu)
        return SimpleNamespace(returncode=0)

    dossier = tmp_path / "coffre" / "vide-poches-machine1"
    ancien = os.umask(0)
    try:
        registre = rapatriement.RegistreRapatries(tmp_path / "rapatries.json")
        action, _ = rapatriement.rapatrier_fichier(fichier, dossier, registre, "_{n}", executer, copier)
    finally:
        os.umask(ancien)
    assert action == rapatriement.RAPATRIE
    assert _mode(dossier) == 0o700 and _mode(tmp_path / "coffre") == 0o700


def test_le_dossier_d_un_depot_imap_est_en_700(tmp_path):
    dossier = tmp_path / "coffre" / "vide-poches-boite"
    ancien = os.umask(0)
    try:
        sources_imap.deposer(b"piece", "p.pdf", dossier, datetime(2026, 11, 24), "_{n}")
    finally:
        os.umask(ancien)
    assert _mode(dossier) == 0o700 and _mode(tmp_path / "coffre") == 0o700


def test_le_journal_d_une_execution_porte_objet_emetteur_categorie_personne_et_date(banc, monkeypatch):
    racine, _ = banc
    lancer(monkeypatch, "--execute")
    session = next((racine / "coffre-a" / "logs" / "sessions").glob("session_*.jsonl"))
    deplacements = [json.loads(ligne) for ligne in session.read_text(encoding="utf-8").splitlines()
                    if json.loads(ligne).get("evenement") == "deplacement"]
    assert deplacements
    for ligne in deplacements:
        assert {"objet", "categorie", "emetteur", "personne", "date"} <= ligne.keys()
    assert any(ligne["categorie"] and ligne["date"] for ligne in deplacements)


def test_le_refus_par_executer_sur_laisse_une_ligne_session_refusee(banc, monkeypatch):
    racine, chemin_config = banc
    configuration = json.loads(chemin_config.read_text())
    configuration["executer_sur"] = ["une-autre-machine"]
    chemin_config.write_text(json.dumps(configuration))
    assert socket.gethostname() != "une-autre-machine"
    avant = sorted(p.name for p in (racine / "source").iterdir())
    with pytest.raises(SystemExit) as sortie:
        lancer(monkeypatch, "--execute")
    assert sortie.value.code == 4
    assert sorted(p.name for p in (racine / "source").iterdir()) == avant
    session = next((racine / "coffre-a" / "logs" / "sessions").glob("session_*.jsonl"))
    lignes = [json.loads(ligne) for ligne in session.read_text(encoding="utf-8").splitlines()]
    assert {"evenement": "session_refusee", "motif": "executer_sur"}.items() <= next(
        ligne for ligne in lignes if ligne["evenement"] == "session_refusee").items()


@pytest.mark.parametrize("forme", ["{id}", "session_{id}", "session_{id}.jsonl", "/un/dossier/session_{id}.jsonl"])
def test_session_se_donne_par_l_identifiant_ou_par_le_nom_du_fichier(forme):
    assert rollback.identifiant_de_session(forme.format(id="2026-11-24T19:32:08")) == "2026-11-24T19:32:08"
    assert rollback.identifiant_de_session(None) is None


def test_rollback_d_un_identifiant_inconnu_s_arrete_avec_un_message(banc, monkeypatch, capsys):
    racine, _ = banc
    lancer(monkeypatch, "--execute")
    capsys.readouterr()
    assert lancer(monkeypatch, "--rollback", "--session", "session_2000-01-01T00:00:00.jsonl") == 1
    erreur = capsys.readouterr().err
    assert "2000-01-01T00:00:00" in erreur


def test_rollback_par_le_nom_du_fichier_annule_la_session_puis_ne_rejoue_rien(banc, monkeypatch, capsys):
    racine, _ = banc
    lancer(monkeypatch, "--execute")
    session = next(ligne["session"] for ligne in journal_actions.lire_lignes(racine / "coffre-a" / "logs" / "journal.jsonl")
                   if ligne["evenement"] == "action")
    assert lancer(monkeypatch, "--rollback", "--session", f"session_{session}.jsonl") == 0
    assert journal_actions.actions_actives(journal_actions.lire_lignes(racine / "coffre-a" / "logs" / "journal.jsonl")) == []
    assert lancer(monkeypatch, "--rollback", "--session", session) == 0
