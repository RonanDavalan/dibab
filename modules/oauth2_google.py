"""Jeton OAuth2 d'un compte Google : consentement, lecture, renouvellement, écriture protégée.

Le jeton ne sort jamais de ce module que par `jeton_d_acces`, pour `scanner_imap.authentifier_xoauth2`.
Aucun message d'erreur ne le reproduit : les erreurs ne portent que des phrases fixes, le code d'état HTTP
et le code d'erreur OAuth2.
"""

import base64
import hashlib
import http.server
import json
import os
import secrets
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

CLES_OAUTH2 = ("url_autorisation", "url_jeton", "portee", "marge_renouvellement_secondes", "delai_secondes",
               "delai_consentement_secondes", "chemins_interdits")
HOTES_BOUCLE_LOCALE = ("127.0.0.1", "::1")


class ErreurOAuth2(Exception):
    """Le jeton n'a pas pu être obtenu, lu ou écrit."""


class JetonAbsent(ErreurOAuth2):
    pass


class AutorisationRevoquee(ErreurOAuth2):
    pass


def verifier_point_d_extremite(url):
    analyse = urllib.parse.urlparse(url)
    if analyse.scheme != "https" and not (analyse.scheme == "http" and analyse.hostname in HOTES_BOUCLE_LOCALE):
        raise ErreurOAuth2("point d'extrémité OAuth2 refusé : https exigé")


def verifier_emplacement(chemin, chemins_interdits):
    """Refuse un jeton dans un dépôt git ou sous un chemin interdit."""
    reel = Path(os.path.realpath(os.path.expanduser(chemin)))
    for interdit in chemins_interdits:
        racine = Path(os.path.realpath(os.path.expanduser(interdit)))
        if reel == racine or racine in reel.parents:
            raise ErreurOAuth2("le fichier de jeton est dans un chemin interdit (oauth2.chemins_interdits)")
    for parent in (reel.parent, *reel.parent.parents):
        if (parent / ".git").exists():
            raise ErreurOAuth2("le fichier de jeton est dans un dépôt git")


def _lire_json_protege(chemin, nom):
    chemin = Path(chemin)
    try:
        etat = chemin.stat()
    except FileNotFoundError as erreur:
        raise JetonAbsent(f"{nom} absent") from erreur
    except OSError as erreur:
        raise ErreurOAuth2(f"{nom} illisible ({type(erreur).__name__})") from erreur
    if etat.st_mode & 0o077:
        raise ErreurOAuth2(f"{nom} lisible par d'autres que son propriétaire : chmod 600")
    try:
        donnees = json.loads(chemin.read_text(encoding="utf-8"))
    except (OSError, ValueError) as erreur:
        raise ErreurOAuth2(f"{nom} illisible ({type(erreur).__name__})") from erreur
    if not isinstance(donnees, dict):
        raise ErreurOAuth2(f"{nom} mal formé")
    return donnees


def lire_client(chemin):
    """Rend (client_id, client_secret ou None) du JSON téléchargé de la console Google."""
    installe = _lire_json_protege(chemin, "fichier du client").get("installed")
    if not isinstance(installe, dict) or not isinstance(installe.get("client_id"), str) or not installe["client_id"]:
        raise ErreurOAuth2("fichier du client mal formé : clé « installed » avec client_id attendue")
    secret = installe.get("client_secret")
    return installe["client_id"], secret if isinstance(secret, str) and secret else None


def lire_jeton(chemin):
    donnees = _lire_json_protege(chemin, "fichier de jeton")
    if not isinstance(donnees.get("refresh_token"), str) or not donnees["refresh_token"]:
        raise ErreurOAuth2("fichier de jeton sans refresh_token")
    return donnees


def ecrire_jeton(chemin, donnees):
    """Écriture atomique en `600` : jamais de fichier de jeton à moitié écrit, ni lisible par d'autres, même un instant."""
    chemin = Path(chemin)
    chemin.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    provisoire = chemin.with_name(f".{chemin.name}.{os.getpid()}.provisoire")
    try:
        descripteur = os.open(provisoire, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descripteur, "w", encoding="utf-8") as f:
            json.dump(donnees, f)
            f.flush()
            os.fsync(f.fileno())
        os.rename(provisoire, chemin)
    except BaseException:
        provisoire.unlink(missing_ok=True)
        raise


def _demander(url, champs, delai):
    """POST d'un formulaire ; rend (statut HTTP, objet JSON). Un échec réseau ne cite pas l'adresse."""
    requete = urllib.request.Request(url, data=urllib.parse.urlencode(champs).encode("ascii"), method="POST",
                                     headers={"Content-Type": "application/x-www-form-urlencoded"})
    try:
        with urllib.request.urlopen(requete, timeout=delai) as reponse:
            statut, corps = reponse.status, reponse.read()
    except urllib.error.HTTPError as erreur:
        statut, corps = erreur.code, erreur.read()
    except (OSError, ValueError) as erreur:
        raise ErreurOAuth2(f"serveur d'autorisation injoignable ({type(erreur).__name__})") from erreur
    try:
        objet = json.loads(corps)
    except ValueError:
        objet = {}
    return statut, objet if isinstance(objet, dict) else {}


def _champs_client(client_id, client_secret):
    champs = {"client_id": client_id}
    if client_secret:
        champs["client_secret"] = client_secret
    return champs


def _echec(statut, reponse):
    if reponse.get("error") == "invalid_grant":
        return AutorisationRevoquee("autorisation révoquée ou expirée : refaire --autoriser-google")
    code = reponse.get("error")
    code = code if isinstance(code, str) and code.replace("_", "").isalnum() else "inconnue"
    return ErreurOAuth2(f"serveur d'autorisation : refus (HTTP {statut}, erreur {code})")


def jeton_d_acces(client_fichier, token_fichier, parametres, maintenant=None):
    """Jeton d'accès valide ; renouvelé et écrit s'il reste moins de `marge_renouvellement_secondes`.

    Une autorisation révoquée ou une réponse invalide ne modifie pas le fichier de jeton.
    """
    maintenant = time.time() if maintenant is None else maintenant
    verifier_emplacement(token_fichier, parametres["chemins_interdits"])
    verifier_point_d_extremite(parametres["url_jeton"])
    jeton = lire_jeton(token_fichier)
    acces, expiration = jeton.get("access_token"), jeton.get("expiration")
    if isinstance(acces, str) and acces and isinstance(expiration, (int, float)) \
            and expiration - maintenant > parametres["marge_renouvellement_secondes"]:
        return acces
    client_id, client_secret = lire_client(client_fichier)
    statut, reponse = _demander(parametres["url_jeton"], {**_champs_client(client_id, client_secret), "grant_type": "refresh_token",
                                                          "refresh_token": jeton["refresh_token"]}, parametres["delai_secondes"])
    if statut != 200:
        raise _echec(statut, reponse)
    acces, duree = reponse.get("access_token"), reponse.get("expires_in")
    if not isinstance(acces, str) or not acces or not isinstance(duree, (int, float)) or duree <= 0:
        raise ErreurOAuth2("réponse du serveur d'autorisation invalide")
    renouvele = reponse.get("refresh_token")
    ecrire_jeton(token_fichier, {"refresh_token": renouvele if isinstance(renouvele, str) and renouvele else jeton["refresh_token"],
                                 "access_token": acces, "expiration": maintenant + duree})
    return acces


class _Recepteur(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        requete = urllib.parse.urlparse(self.path)
        if requete.path != "/":
            self.send_error(404)
            return
        self.server.reponse = {cle: valeurs[0] for cle, valeurs in urllib.parse.parse_qs(requete.query).items()}
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.end_headers()
        self.wfile.write("Skrivagner a reçu la réponse de Google. Cette page peut être fermée.".encode("utf-8"))

    def log_message(self, *arguments):
        pass


def autoriser(client_fichier, token_fichier, utilisateur, parametres, afficher_adresse, maintenant=None):
    """Consentement d'une application de bureau (PKCE, boucle locale) ; écrit `token_fichier`.

    `afficher_adresse` reçoit l'adresse à ouvrir dans un navigateur. Rien n'est écrit si le consentement échoue.
    """
    maintenant = time.time() if maintenant is None else maintenant
    verifier_emplacement(token_fichier, parametres["chemins_interdits"])
    verifier_point_d_extremite(parametres["url_autorisation"])
    verifier_point_d_extremite(parametres["url_jeton"])
    client_id, client_secret = lire_client(client_fichier)
    verificateur = secrets.token_urlsafe(64)
    defi = base64.urlsafe_b64encode(hashlib.sha256(verificateur.encode("ascii")).digest()).rstrip(b"=").decode("ascii")
    etat = secrets.token_urlsafe(24)
    with http.server.HTTPServer(("127.0.0.1", 0), _Recepteur) as recepteur:
        recepteur.reponse = None
        recepteur.timeout = 1
        redirection = f"http://127.0.0.1:{recepteur.server_address[1]}"
        afficher_adresse(parametres["url_autorisation"] + "?" + urllib.parse.urlencode({
            "client_id": client_id, "redirect_uri": redirection, "response_type": "code", "scope": parametres["portee"],
            "code_challenge": defi, "code_challenge_method": "S256", "state": etat, "login_hint": utilisateur}))
        limite = time.monotonic() + parametres["delai_consentement_secondes"]
        while recepteur.reponse is None and time.monotonic() < limite:
            recepteur.handle_request()
        reponse = recepteur.reponse
    if reponse is None:
        raise ErreurOAuth2("aucune réponse de Google dans le délai du consentement")
    if not secrets.compare_digest(reponse.get("state", ""), etat):
        raise ErreurOAuth2("réponse de consentement refusée : state différent")
    if reponse.get("error") or not reponse.get("code"):
        raise ErreurOAuth2("consentement refusé" if reponse.get("error") == "access_denied" else "consentement sans code d'autorisation")
    statut, resultat = _demander(parametres["url_jeton"], {**_champs_client(client_id, client_secret), "grant_type": "authorization_code",
                                                           "code": reponse["code"], "code_verifier": verificateur,
                                                           "redirect_uri": redirection}, parametres["delai_secondes"])
    if statut != 200:
        raise _echec(statut, resultat)
    acces, duree, renouvellement = resultat.get("access_token"), resultat.get("expires_in"), resultat.get("refresh_token")
    if not isinstance(renouvellement, str) or not renouvellement:
        raise ErreurOAuth2("Google n'a pas rendu de jeton de renouvellement : rien n'est écrit")
    if not isinstance(acces, str) or not acces or not isinstance(duree, (int, float)) or duree <= 0:
        raise ErreurOAuth2("réponse du serveur d'autorisation invalide")
    ecrire_jeton(token_fichier, {"refresh_token": renouvellement, "access_token": acces, "expiration": maintenant + duree})
