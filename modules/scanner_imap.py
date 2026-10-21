"""Pièces jointes d'une boîte IMAP, lues sans jamais modifier la boîte.

Seules ces commandes partent vers le serveur : EXAMINE (lecture seule), UID SEARCH SINCE, UID FETCH de
INTERNALDATE et BODYSTRUCTURE, puis BODY.PEEK[<partie>] d'une pièce jointe. Le corps du message n'est
jamais demandé et aucun drapeau n'est posé. Le nom d'une pièce jointe est une donnée du message : il
n'est rendu qu'après décodage et nettoyage.
"""

import base64
import imaplib
import itertools
import quopri
import re
import ssl
import unicodedata
from dataclasses import dataclass
from datetime import datetime
from email.header import decode_header, make_header
from email.utils import collapse_rfc2231_value, decode_params, unquote

from modules.rapatriement import nom_local

MOIS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")
ENCODAGES_LISIBLES = ("7bit", "8bit", "binary", "base64", "quoted-printable")
MESSAGES_PAR_LOT = 50
PROFONDEUR_MAX = 30


class ErreurImap(Exception):
    """Une commande IMAP n'a pas abouti."""


class ConnexionImpossible(ErreurImap):
    pass


class AuthentificationRefusee(ErreurImap):
    pass


@dataclass(frozen=True)
class PieceJointe:
    source_id: str
    dossier: str
    uidvalidity: str
    uid: str
    partie: str
    nom: str
    taille_octets: int
    encodage: str
    date: datetime

    @property
    def cle(self):
        return f"{self.dossier}|{self.uidvalidity}|{self.uid}|{self.partie}"


_OUVRE, _FERME = object(), object()
_ATOME = re.compile(r'[^\s()"]+')


def _jetons(texte):
    i, n = 0, len(texte)
    while i < n:
        c = texte[i]
        if c.isspace():
            i += 1
        elif c == "(":
            yield _OUVRE
            i += 1
        elif c == ")":
            yield _FERME
            i += 1
        elif c == '"':
            i += 1
            morceaux = []
            while i < n and texte[i] != '"':
                if texte[i] == "\\" and i + 1 < n:
                    i += 1
                morceaux.append(texte[i])
                i += 1
            i += 1
            yield ("valeur", "".join(morceaux))
        else:
            atome = _ATOME.match(texte, i)
            i = atome.end()
            yield ("valeur", None if atome.group().upper() == "NIL" else atome.group())


def _liste(jetons, profondeur=0):
    if profondeur > PROFONDEUR_MAX:
        raise ErreurImap("structure de message trop imbriquée")
    elements = []
    for jeton in jetons:
        if jeton is _FERME:
            return elements
        elements.append(_liste(jetons, profondeur + 1) if jeton is _OUVRE else jeton[1])
    raise ErreurImap("réponse du serveur tronquée")


def _reconstituer(donnees):
    """Recolle une réponse que `imaplib` a coupée à chaque littéral ; le littéral devient une chaîne citée."""
    texte = []
    for element in donnees:
        if isinstance(element, tuple):
            tete = re.sub(rb"\{\d+\}\s*$", b"", element[0]).decode("utf-8", "replace")
            litteral = element[1].decode("utf-8", "replace").replace("\\", "\\\\").replace('"', '\\"')
            texte.append(f'{tete}"{litteral}"')
        elif isinstance(element, bytes):
            texte.append(element.decode("utf-8", "replace"))
    return " ".join(texte)


def analyser_reponses_fetch(donnees):
    """Rend un dictionnaire par message : les éléments demandés, clés en majuscules."""
    jetons = iter(_jetons(_reconstituer(donnees)))
    messages = []
    for jeton in jetons:
        if jeton in (_OUVRE, _FERME):
            continue
        if next(jetons, None) is not _OUVRE:
            raise ErreurImap("réponse FETCH illisible")
        elements = _liste(jetons)
        messages.append({str(cle).upper(): valeur for cle, valeur in zip(elements[0::2], elements[1::2])})
    return messages


def _est_multipart(structure):
    return bool(structure) and isinstance(structure[0], list)


def parties(structure, numero="", profondeur=0):
    """Rend (numéro de partie, partie simple) pour chaque partie non composite, dans l'ordre du message."""
    if profondeur > PROFONDEUR_MAX:
        raise ErreurImap("structure de message trop imbriquée")
    if _est_multipart(structure):
        enfants = list(itertools.takewhile(lambda element: isinstance(element, list), structure))
        for rang, enfant in enumerate(enfants, 1):
            yield from parties(enfant, f"{numero}.{rang}" if numero else str(rang), profondeur + 1)
        return
    numero = numero or "1"
    yield numero, structure
    if str(structure[0]).upper() == "MESSAGE" and str(structure[1]).upper() == "RFC822" and len(structure) > 8 \
            and isinstance(structure[8], list):
        interne = structure[8]
        yield from parties(interne, numero if _est_multipart(interne) else f"{numero}.1", profondeur + 1)


def _parametres(liste):
    if not isinstance(liste, list):
        return []
    return [(str(cle).lower(), valeur) for cle, valeur in zip(liste[0::2], liste[1::2]) if valeur is not None]


def _decoder(parametres, cle):
    decodes = dict(decode_params([("x", "x"), *parametres])[1:])
    valeur = decodes.get(cle)
    if valeur is None:
        return None
    valeur = unquote(collapse_rfc2231_value(valeur))
    try:
        return str(make_header(decode_header(valeur)))
    except Exception:  # un en-tête mal formé reste une donnée : on garde la valeur brute
        return valeur


def description(partie):
    """Rend (nom brut décodé ou None, disposition, a un Content-ID, encodage, taille annoncée) d'une partie simple."""
    type_, sous_type = str(partie[0]).upper(), str(partie[1]).upper()
    base = 7 + (1 if type_ == "TEXT" else 3 if (type_, sous_type) == ("MESSAGE", "RFC822") else 0)
    disposition = partie[base + 1] if len(partie) > base + 1 else None
    nom_disposition = nom_type = None
    nature = None
    if isinstance(disposition, list) and disposition and disposition[0]:
        nature = str(disposition[0]).lower()
        nom_disposition = _decoder(_parametres(disposition[1] if len(disposition) > 1 else None), "filename")
    nom_type = _decoder(_parametres(partie[2]), "name")
    taille = int(partie[6]) if str(partie[6]).isdigit() else 0
    return nom_disposition or nom_type, nature, partie[3] is not None, str(partie[5] or "7bit").lower(), taille


def nom_de_piece(nom):
    """Nom sûr pour un fichier du vide-poches ; une donnée du message ne devient jamais un chemin."""
    sans_format = "".join(c for c in nom if unicodedata.category(c) != "Cf")
    return nom_local(sans_format)


def pieces_du_message(structure, source_id, dossier, uidvalidity, uid, date, extensions, taille_max_octets):
    """Les pièces jointes retenues d'un message, et le nombre de celles écartées pour leur taille."""
    retenues, trop_grosses = [], 0
    for numero, partie in parties(structure):
        nom, nature, a_content_id, encodage, taille = description(partie)
        if not nom or str(partie[0]).upper() == "MULTIPART":
            continue
        if nature != "attachment" and not (nature == "inline" and not a_content_id):
            continue
        propre = nom_de_piece(nom)
        if "." + propre.rpartition(".")[2].lower() not in extensions:
            continue
        if taille > taille_max_octets:
            trop_grosses += 1
            continue
        retenues.append(PieceJointe(source_id, dossier, uidvalidity, uid, numero, propre, taille, encodage, date))
    return retenues, trop_grosses


def date_imap(date):
    """Date de la commande SEARCH, avec le nom anglais du mois quelle que soit la langue du système."""
    return f"{date.day:02d}-{MOIS[date.month - 1]}-{date.year}"


def ouvrir_connexion(serveur, port, delai_secondes, contexte=None):
    """Connexion TLS, certificat et nom d'hôte vérifiés ; aucune connexion en clair n'existe dans ce module."""
    try:
        return imaplib.IMAP4_SSL(serveur, port, ssl_context=contexte or ssl.create_default_context(), timeout=delai_secondes)
    except (OSError, imaplib.IMAP4.error) as erreur:
        raise ConnexionImpossible(f"connexion impossible ({type(erreur).__name__})") from erreur


def authentifier(connexion, utilisateur, mot_de_passe):
    """Un refus arrête la source : aucune nouvelle tentative.

    `LOGIN` ne transporte que de l'ASCII imprimable ; tout autre identifiant ou mot de passe passe par
    `AUTHENTICATE PLAIN`, en UTF-8 et sans caractère de contrôle dans la commande.
    """
    try:
        if re.fullmatch(r"[\x20-\x7e]*", utilisateur + mot_de_passe):
            etat, _ = connexion.login(utilisateur, mot_de_passe)
        else:
            etat, _ = connexion.authenticate("PLAIN", lambda _: f"\0{utilisateur}\0{mot_de_passe}".encode("utf-8"))
    except imaplib.IMAP4.error as erreur:
        raise AuthentificationRefusee("authentification refusée par le serveur") from erreur
    except OSError as erreur:
        raise ConnexionImpossible(f"connexion perdue ({type(erreur).__name__})") from erreur
    if etat != "OK":
        raise AuthentificationRefusee("authentification refusée par le serveur")


def fermer(connexion):
    try:
        connexion.logout()
    except (OSError, imaplib.IMAP4.error):
        pass


def _nom_de_boite(dossier):
    if re.search(r"[\x00-\x1f\x7f]", dossier) or not dossier:
        raise ErreurImap("nom de dossier IMAP invalide")
    return '"' + dossier.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _commande(connexion, *arguments):
    try:
        etat, donnees = connexion.uid(*arguments)
    except (OSError, imaplib.IMAP4.error) as erreur:
        raise ErreurImap(f"commande IMAP interrompue ({type(erreur).__name__})") from erreur
    if etat != "OK":
        raise ErreurImap("le serveur a refusé une commande de lecture")
    return donnees


def lister_dossier(connexion, source_id, dossier, depuis, extensions, taille_max_octets):
    """Rend (pièces jointes reçues depuis `depuis`, nombre écarté pour la taille) ; la boîte est ouverte en lecture seule."""
    try:
        etat, _ = connexion.select(_nom_de_boite(dossier), readonly=True)
        _, validite = connexion.response("UIDVALIDITY")
    except (OSError, imaplib.IMAP4.error) as erreur:
        raise ErreurImap(f"dossier illisible ({type(erreur).__name__})") from erreur
    if etat != "OK":
        raise ErreurImap("dossier introuvable ou refusé")
    uidvalidity = validite[0].decode("ascii", "replace") if validite and validite[0] else "0"
    identifiants = (_commande(connexion, "SEARCH", None, "SINCE", date_imap(depuis))[0] or b"").split()
    pieces, ecartees = [], 0
    for debut in range(0, len(identifiants), MESSAGES_PAR_LOT):
        lot = b",".join(identifiants[debut:debut + MESSAGES_PAR_LOT]).decode("ascii")
        for message in analyser_reponses_fetch(_commande(connexion, "FETCH", lot, "(INTERNALDATE BODYSTRUCTURE)")):
            reception = imaplib.Internaldate2tuple(f'INTERNALDATE "{message.get("INTERNALDATE", "")}"'.encode())
            structure = message.get("BODYSTRUCTURE")
            if not reception or not message.get("UID") or not isinstance(structure, list):
                continue
            date = datetime(*reception[:6])
            if date < depuis:
                continue
            retenues, trop_grosses = pieces_du_message(structure, source_id, dossier, uidvalidity, message["UID"],
                                                       date, extensions, taille_max_octets)
            pieces += retenues
            ecartees += trop_grosses
    return pieces, ecartees


def telecharger(connexion, piece):
    """Octets d'une pièce jointe décodés ; `BODY.PEEK` ne pose aucun drapeau et ne demande que cette partie."""
    donnees = _commande(connexion, "FETCH", piece.uid, f"(BODY.PEEK[{piece.partie}])")
    brut = next((element[1] for element in donnees if isinstance(element, tuple)), None)
    if brut is None:
        raise ErreurImap("pièce jointe absente de la réponse")
    if piece.encodage == "base64":
        return base64.b64decode(brut)
    if piece.encodage == "quoted-printable":
        return quopri.decodestring(brut)
    if piece.encodage in ENCODAGES_LISIBLES:
        return brut
    raise ErreurImap("encodage de pièce jointe non pris en charge")
