"""Rapatriement par un faux `ssh` : copie vérifiée, reprise sans doublon, dates qui n'avancent qu'après vérification, jusqu'au pipeline."""

import hashlib
import json
from datetime import datetime
from pathlib import Path

import pytest

import dibab
from modules import journal_actions, rapatriement, rapport, sources_distantes
from tests.faux_ssh import installer
from tests.test_classement_execute import LOT, TEXTES, arbre, banc, lancer  # noqa: F401

SSH = {"delai_connexion_secondes": 5, "delai_commande_secondes": 10, "delai_copie_secondes": 20}
SOURCE = {"id": "ssh-test", "alias_ssh": "machine-factice", "vide_poches_destination": "vide-poches-test",
          "repertoires": ["~/Téléchargements"], "exclusions": []}
DISTANTS = {"un.pdf": TEXTES[2]["texte"], "deux.pdf": TEXTES[0]["texte"] + " distant", "x; touch PIEGE.pdf": TEXTES[4]["texte"]}


def empreinte(texte):
    return hashlib.sha256(texte.encode("utf-8")).hexdigest()


@pytest.fixture
def machine(banc, monkeypatch):
    racine, chemin_config = banc
    distant = installer(racine, monkeypatch)
    (distant / "Téléchargements").mkdir()
    for nom, texte in DISTANTS.items():
        (distant / "Téléchargements" / nom).write_text(texte, encoding="utf-8")
    configuration = json.loads(chemin_config.read_text())
    configuration.update(ssh=SSH, sources_distantes=[SOURCE])
    chemin_config.write_text(json.dumps(configuration))
    return racine, distant, configuration


def vide_poches(racine):
    return racine / "coffre-a" / "vide-poches-test"


def tout_rapatrier(configuration, suivi=None):
    court, copie = sources_distantes.executeurs(configuration)
    journal = dibab.mod_journal.JournalAbsent()
    maintenant = datetime.now()
    listages = sources_distantes.lister(configuration, suivi or {}, journal, maintenant, court)
    registre = rapatriement.RegistreRapatries(Path(configuration["suivi"]["fichier_date"]).parent / "rapatries.json")
    resultat = sources_distantes.rapatrier(configuration, listages, registre, journal, rapport.Rapport("s", "execute"), maintenant, court, copie)
    return resultat, maintenant


def test_le_lot_est_rapatrie_avec_les_memes_empreintes_sans_toucher_au_distant(machine):
    racine, distant, configuration = machine
    avant = {p.name: p.read_bytes() for p in (distant / "Téléchargements").iterdir()}
    (dates, en_echec), maintenant = tout_rapatrier(configuration)
    assert en_echec == set() and dates == {"ssh-test": maintenant}
    copies = {p.name: empreinte(p.read_text(encoding="utf-8")) for p in vide_poches(racine).iterdir()}
    assert len(copies) == 3 and sorted(copies.values()) == sorted(empreinte(t) for t in DISTANTS.values())
    assert {p.name: p.read_bytes() for p in (distant / "Téléchargements").iterdir()} == avant
    assert sorted(p.name for p in (distant / "Téléchargements").iterdir()) == sorted(DISTANTS) and not Path("PIEGE.pdf").exists()


def test_une_copie_interrompue_puis_reprise_ne_laisse_ni_reste_ni_doublon(machine, monkeypatch):
    racine, distant, configuration = machine
    monkeypatch.setenv("FAUX_SSH_MODE", "coupe")
    monkeypatch.setenv("FAUX_SSH_COUPE", "deux.pdf")
    (dates, en_echec), _ = tout_rapatrier(configuration)
    assert dates == {} and en_echec == {"ssh-test"}
    assert not [p for p in vide_poches(racine).iterdir() if p.name.startswith(".")]
    assert "deux.pdf" not in {p.name for p in vide_poches(racine).iterdir()}
    monkeypatch.setenv("FAUX_SSH_MODE", "normal")
    (dates, en_echec), maintenant = tout_rapatrier(configuration)
    assert en_echec == set() and dates == {"ssh-test": maintenant}
    copies = sorted(p.name for p in vide_poches(racine).iterdir())
    assert copies == sorted(DISTANTS) and sum(n.startswith("un") for n in copies) == 1
    assert {p.name: empreinte(p.read_text(encoding="utf-8")) for p in vide_poches(racine).iterdir()} == \
        {nom: empreinte(texte) for nom, texte in DISTANTS.items()}


def test_un_fichier_deja_rapatrie_n_est_pas_recopie(machine):
    racine, _, configuration = machine
    tout_rapatrier(configuration)
    (vide_poches(racine) / "un.pdf").unlink()
    tout_rapatrier(configuration)
    assert "un.pdf" not in {p.name for p in vide_poches(racine).iterdir()}


def test_un_fichier_complet_sans_trace_au_registre_est_repris_sans_doublon(machine):
    racine, _, configuration = machine
    tout_rapatrier(configuration)
    (Path(configuration["suivi"]["fichier_date"]).parent / "rapatries.json").unlink()
    tout_rapatrier(configuration)
    assert len(list(vide_poches(racine).iterdir())) == 3


def test_machine_absente_la_date_reste_en_place(machine, monkeypatch):
    racine, _, configuration = machine
    monkeypatch.setenv("FAUX_SSH_MODE", "absente")
    (dates, en_echec), _ = tout_rapatrier(configuration)
    assert dates == {} and en_echec == {"ssh-test"} and not vide_poches(racine).exists()


def test_nom_local_est_sur():
    assert rapatriement.nom_local("a\nb\x00c.pdf") == "a_b_c.pdf"
    assert rapatriement.nom_local(".cache.pdf") == "_.cache.pdf"
    assert len(rapatriement.nom_local("é" * 300 + ".pdf").encode("utf-8")) <= 200


def test_dry_run_liste_sans_rien_rapatrier(machine, monkeypatch, capsys):
    racine, _, _ = machine
    assert lancer(monkeypatch, "--dry-run") == 0
    sortie = capsys.readouterr().out
    assert "Source distante : ssh-test" in sortie and "un.pdf" in sortie and "distant" in sortie
    assert not vide_poches(racine).exists()


def test_execute_rapatrie_classe_et_le_second_passage_ne_fait_rien(machine, monkeypatch):
    racine, distant, _ = machine
    assert lancer(monkeypatch, "--execute") == 0
    assert "ssh-test" in json.loads((racine / "coffre-a" / "logs" / "dernier_scan.json").read_text())
    assert [p.name for p in vide_poches(racine).iterdir()] == []
    actions = [a for a in journal_actions.lire_lignes(racine / "coffre-a" / "logs" / "journal.jsonl") if a["evenement"] == "action"]
    distants = [a for a in actions if "vide-poches-test" in a["origine"]]
    assert len(distants) == 3
    assert len(list((distant / "Téléchargements").iterdir())) == 3
    assert lancer(monkeypatch, "--execute") == 0
    apres = [a for a in journal_actions.lire_lignes(racine / "coffre-a" / "logs" / "journal.jsonl") if a["evenement"] == "action"]
    assert apres == actions


def test_un_scan_distant_puis_local_du_meme_fichier_ne_classe_qu_une_piece(machine, monkeypatch):
    racine, _, _ = machine
    lancer(monkeypatch, "--execute")
    avant = arbre(racine / "coffre-b")
    (racine / "source" / "meme.pdf").write_text(DISTANTS["un.pdf"], encoding="utf-8")
    lancer(monkeypatch, "--execute")
    lignes = [a for a in journal_actions.lire_lignes(racine / "coffre-a" / "logs" / "journal.jsonl") if a["evenement"] == "action"]
    meme = [a for a in lignes if a["origine"].endswith("meme.pdf")]
    assert len(meme) == 1 and meme[0]["action"] == "doublon"
    assert [c for c in arbre(racine / "coffre-b") if not c.startswith("doublon/")] == [c for c in avant if not c.startswith("doublon/")]


def test_execute_machine_absente_n_avance_pas_la_date_et_rend_1(machine, monkeypatch):
    racine, _, _ = machine
    monkeypatch.setenv("FAUX_SSH_MODE", "absente")
    assert lancer(monkeypatch, "--execute") == 1
    assert "ssh-test" not in json.loads((racine / "coffre-a" / "logs" / "dernier_scan.json").read_text())


def test_config_sans_bloc_ssh_arrete_avec_le_code_1(machine, monkeypatch):
    racine, _, _ = machine
    chemin = dibab.CHEMIN_CONFIG
    configuration = json.loads(chemin.read_text())
    del configuration["ssh"]
    chemin.write_text(json.dumps(configuration))
    with pytest.raises(SystemExit) as sortie:
        lancer(monkeypatch, "--dry-run")
    assert sortie.value.code == 1
