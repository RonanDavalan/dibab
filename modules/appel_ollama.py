"""Génération Ollama par HTTP brut (`urllib`), sans bibliothèque cliente."""

import base64
import json
import urllib.error
import urllib.request


class ErreurOllama(Exception):
    """Ollama ne répond pas, répond en erreur ou rend une réponse inexploitable."""


def generer(url, modele, consigne, images, delai, keep_alive, ouvrir=urllib.request.urlopen):
    """Rend le texte généré par `modele` pour `consigne` et une liste d'images (octets).

    `keep_alive` pilote le déchargement : 0 décharge le modèle dès la réponse.
    """
    corps = {
        "model": modele,
        "prompt": consigne,
        "images": [base64.b64encode(image).decode("ascii") for image in images],
        "stream": False,
        "keep_alive": keep_alive,
    }
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
        raise ErreurOllama(f"Ollama ne répond pas à {requete.full_url} : {erreur}") from erreur
    if not isinstance(donnees, dict) or not isinstance(donnees.get("response"), str):
        raise ErreurOllama(f"réponse d'Ollama sans champ `response` (modèle {modele})")
    return donnees["response"]
