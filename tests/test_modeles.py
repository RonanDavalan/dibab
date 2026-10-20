"""Tests de modules/modeles.py sur une réponse simulée d'Ollama."""

import io
import json
import urllib.error

import pytest

from modules import modeles

INSTALLES = ["modele-a:7b", "modele-b:latest", "modele-c:3b"]


class FausseReponse(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *exception):
        return False


def simuler_ollama(monkeypatch, noms):
    corps = json.dumps({"models": [{"name": n} for n in noms]}).encode()
    appels = []

    def faux_urlopen(requete, timeout=None):
        appels.append((requete, timeout))
        return FausseReponse(corps)

    monkeypatch.setattr(modeles.urllib.request, "urlopen", faux_urlopen)
    return appels


def test_premiere_preference_installee(monkeypatch):
    simuler_ollama(monkeypatch, INSTALLES)
    retenus = modeles.resoudre_modeles({
        "url": "http://hote-test:1234/",
        "timeout_secondes": 7,
        "roles": {"ocr": ["absent:1b", "modele-c:3b"], "classification": ["modele-a:7b", "modele-c:3b"]},
    })
    assert retenus == {"ocr": "modele-c:3b", "classification": "modele-a:7b"}


def test_interroge_api_tags_avec_delai(monkeypatch):
    appels = simuler_ollama(monkeypatch, INSTALLES)
    modeles.resoudre_modeles({"url": "http://hote-test:1234/", "timeout_secondes": 7,
                              "roles": {"ocr": ["modele-a:7b"]}})
    assert appels == [("http://hote-test:1234/api/tags", 7)]


def test_nom_sans_etiquette_correspond_a_latest(monkeypatch):
    simuler_ollama(monkeypatch, INSTALLES)
    retenus = modeles.resoudre_modeles({"url": "http://x", "roles": {"ocr": ["modele-b"]}})
    assert retenus == {"ocr": "modele-b:latest"}


def test_role_sans_modele_nomme_modeles_presents_et_ligne_a_corriger(monkeypatch):
    simuler_ollama(monkeypatch, INSTALLES)
    with pytest.raises(modeles.ModeleIndisponible) as erreur:
        modeles.resoudre_modeles({"url": "http://x", "roles": {
            "ocr": ["modele-a:7b"], "tri_rapide": ["absent:1b"]}})
    message = str(erreur.value)
    assert "tri_rapide" in message
    assert "ollama.roles.tri_rapide" in message
    assert "modele-a:7b" in message and "modele-c:3b" in message
    assert "ollama.roles.ocr" not in message


def test_role_sans_preference(monkeypatch):
    simuler_ollama(monkeypatch, INSTALLES)
    with pytest.raises(modeles.ModeleIndisponible) as erreur:
        modeles.resoudre_modeles({"url": "http://x", "roles": {"ocr": []}})
    assert "ollama.roles.ocr" in str(erreur.value)


def test_aucun_role_declare():
    with pytest.raises(modeles.ModeleIndisponible) as erreur:
        modeles.resoudre_modeles({"url": "http://x"})
    assert "ollama.roles" in str(erreur.value)


def test_ollama_injoignable(monkeypatch):
    def echec(requete, timeout=None):
        raise urllib.error.URLError("refusé")

    monkeypatch.setattr(modeles.urllib.request, "urlopen", echec)
    with pytest.raises(modeles.ModeleIndisponible) as erreur:
        modeles.resoudre_modeles({"url": "http://x", "roles": {"ocr": ["modele-a:7b"]}})
    assert "ollama.url" in str(erreur.value)
