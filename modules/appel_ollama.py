"""Génération et décision Ollama par HTTP brut (`urllib`), sans bibliothèque cliente."""

import base64
import json
import urllib.error
import urllib.request
from modules.messages import texte_de, traduire


class ErreurOllama(Exception):
    """Ollama ne répond pas, répond en erreur ou rend une réponse inexploitable."""


class PointAccesAbsent(ErreurOllama):
    """HTTP 404 : Ollama ne connaît pas le point d'accès (version trop ancienne) ou le modèle demandé."""


def generer(url, modele, consigne, images, delai, keep_alive, ouvrir=urllib.request.urlopen,
            format=None, options=None):
    """Rend le texte généré par `modele` pour `consigne` et une liste d'images (octets).

    `keep_alive` pilote le déchargement : 0 décharge le modèle dès la réponse.
    `format` (schéma JSON) contraint la sortie ; `options` règle le contexte et la température.
    """
    corps = {
        "model": modele,
        "prompt": consigne,
        "images": [base64.b64encode(image).decode("ascii") for image in images],
        "stream": False,
        "keep_alive": keep_alive,
    }
    if format is not None:
        corps["format"] = format
    if options is not None:
        corps["options"] = options
    requete = urllib.request.Request(
        f"{url.rstrip('/')}/api/generate",
        data=json.dumps(corps).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with ouvrir(requete, timeout=delai) as reponse:
            donnees = json.load(reponse)
    except (urllib.error.URLError, OSError, ValueError) as erreur:
        raise ErreurOllama(traduire("ollama_ne_repond_pas", url=requete.full_url, erreur=texte_de(erreur))) from erreur
    if not isinstance(donnees, dict) or not isinstance(donnees.get("response"), str):
        raise ErreurOllama(traduire("ollama_reponse_sans_champ", modele=modele))
    return donnees["response"]


def decider(url, modele, etat, questions, delai, keep_alive, ouvrir=urllib.request.urlopen):
    """Rend le champ `answers` de `POST <url>/v1/systemone` : les réponses typées d'un modèle decision à `questions`.

    Un 404 lève `PointAccesAbsent`, que l'appelant traite pour toute l'étape : il ne dépend pas du document.
    """
    corps = {"model": modele, "state": etat, "questions": questions, "keep_alive": keep_alive}
    requete = urllib.request.Request(
        f"{url.rstrip('/')}/v1/systemone",
        data=json.dumps(corps).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with ouvrir(requete, timeout=delai) as reponse:
            donnees = json.load(reponse)
    except urllib.error.HTTPError as erreur:
        if erreur.code == 404:
            raise PointAccesAbsent(traduire("ollama_point_acces_absent", url=requete.full_url, modele=modele)) from erreur
        raise ErreurOllama(traduire("ollama_ne_repond_pas", url=requete.full_url, erreur=texte_de(erreur))) from erreur
    except (urllib.error.URLError, OSError, ValueError) as erreur:
        raise ErreurOllama(traduire("ollama_ne_repond_pas", url=requete.full_url, erreur=texte_de(erreur))) from erreur
    if not isinstance(donnees, dict) or not isinstance(donnees.get("answers"), dict):
        raise ErreurOllama(traduire("ollama_reponse_sans_champ_answers", modele=modele))
    return donnees["answers"]
