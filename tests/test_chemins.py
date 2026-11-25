"""Tests de modules/chemins.py."""


from modules import chemins


def test_tilde_et_variable_sont_developpes(monkeypatch):
    monkeypatch.setenv("HOME", "/maison-factice")
    assert chemins.developper("~/x") == "/maison-factice/x"
    assert chemins.developper("$HOME/x") == "/maison-factice/x"


def test_chaque_chemin_local_est_developpe(monkeypatch):
    monkeypatch.setenv("HOME", "/maison-factice")
    configuration = {
        "destinations": {"personnel": {"racine": "~/coffre"}, "professionnel": {"racine": "$HOME/coffre-pro"}},
        "suivi": {"fichier_date": "$HOME/l/d.json", "journal": "~/l/j.jsonl",
                  "sessions": "~/l/s", "logs_systeme": "$HOME/l/s.log"},
        "sources_locales": [{"id": "a", "chemin": "~/a"}, {"id": "b", "chemin": "$HOME/b"}],
        "sources_imap": [{"id": "m", "token_fichier": "~/t"}],
        "sources_distantes": [{"id": "d", "repertoires": ["~/Téléchargements"]}],
    }
    resultat = chemins.developper_chemins(configuration)
    assert resultat["destinations"]["personnel"]["racine"] == "/maison-factice/coffre"
    assert resultat["destinations"]["professionnel"]["racine"] == "/maison-factice/coffre-pro"
    assert resultat["suivi"]["fichier_date"] == "/maison-factice/l/d.json"
    assert resultat["suivi"]["journal"] == "/maison-factice/l/j.jsonl"
    assert resultat["suivi"]["sessions"] == "/maison-factice/l/s"
    assert resultat["suivi"]["logs_systeme"] == "/maison-factice/l/s.log"
    assert [s["chemin"] for s in resultat["sources_locales"]] == ["/maison-factice/a", "/maison-factice/b"]
    assert resultat["sources_imap"][0]["token_fichier"] == "/maison-factice/t"
    assert resultat["sources_distantes"][0]["repertoires"] == ["~/Téléchargements"]
    assert configuration["destinations"]["personnel"]["racine"] == "~/coffre"


def test_configuration_sans_section_ne_leve_rien():
    assert chemins.developper_chemins({}) == {}
