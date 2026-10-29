"""Sources IMAP : lecture des boîtes, dépôt des pièces jointes dans le vide-poches, dates de scan à faire avancer.

Le dry-run liste seulement. Une fois déposée, une pièce jointe est un fichier local du vide-poches, que
le scan local relit sans filtre de date. Ni le sujet, ni l'expéditeur, ni le nom d'origine d'une pièce
n'entrent dans le journal de session ou le rapport.
"""

import hashlib
import os
from dataclasses import dataclass, field
from pathlib import Path

from modules import journal_actions, oauth2_google, scanner_imap, scanner_local
from modules.deplacement import chemin_libre
from modules.pieces_communes import empreinte_sha256
from modules.rapatriement import RegistreRapatries
from modules.messages import ecrire, texte_de, traduire

CLES_IMAP = ("delai_secondes", "taille_max_piece_mo")
CLES_SOURCE = ("id", "serveur", "port", "ssl", "authentification", "utilisateur", "dossiers", "vide_poches_destination")
CLES_SOURCE_PAR_AUTHENTIFICATION = {"login": ("mot_de_passe_env",), "oauth2": ("token_fichier", "client_fichier")}

DEPOSEE = "deposee"
DEJA_DEPOSEE = "deja_deposee"
DOUBLON = "doublon"
REPRISE = "reprise"


@dataclass
class ResultatSource:
    source: dict
    pieces: list = field(default_factory=list)
    ecartees_taille: int = 0
    complet: bool = False
    ignoree: bool = False
    erreurs: list = field(default_factory=list)
    deposees: int = 0


def cles_absentes(configuration):
    sources = configuration.get("sources_imap", [])
    if not sources:
        return []
    absentes = [f"imap.{cle}" for cle in CLES_IMAP if cle not in configuration.get("imap", {})]
    if any(source.get("authentification") == "oauth2" for source in sources):
        absentes += [f"oauth2.{cle}" for cle in oauth2_google.CLES_OAUTH2 if cle not in configuration.get("oauth2", {})]
    for source in sources:
        attendues = CLES_SOURCE + CLES_SOURCE_PAR_AUTHENTIFICATION.get(source.get("authentification"), ("mot_de_passe_env",))
        absentes += [f"sources_imap[{source.get('id', '?')}].{cle}" for cle in attendues if cle not in source]
        nom = source.get("vide_poches_destination", "")
        if "/" in nom or nom in ("", ".", ".."):
            absentes.append(traduire("cle_nom_sans_separateur", cle=f"sources_imap[{source.get('id', '?')}].vide_poches_destination"))
    return absentes


def dossier_vide_poches(configuration, source):
    return Path(configuration["destinations"]["personnel"]["racine"]) / source["vide_poches_destination"]


def sources_locales_derivees(configuration):
    """Les vide-poches des sources IMAP que le scan lit sans filtre de date ; sans dossier, rien à lire."""
    derivees = []
    for source in configuration.get("sources_imap", []):
        dossier = dossier_vide_poches(configuration, source)
        if dossier.is_dir():
            derivees.append({"id": f"{source['id']}-vide-poches", "chemin": str(dossier), "toujours_complete": True})
    return derivees


def deposer(octets, nom, dossier, date, suffixe_collision):
    """Écrit `octets` sous `nom` dans `dossier` ; rend (action, empreinte). Jamais de fichier à moitié écrit sous son nom final."""
    empreinte = hashlib.sha256(octets).hexdigest()
    dossier.mkdir(parents=True, exist_ok=True, mode=0o700)
    final = dossier / nom
    if final.is_file() and empreinte_sha256(final) == empreinte:
        return REPRISE, empreinte
    final = chemin_libre(final, suffixe_collision)
    provisoire = dossier / f".skrivagner-imap-{os.getpid()}-{final.name}"
    try:
        descripteur = os.open(provisoire, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(descripteur, "wb") as f:
            f.write(octets)
        if empreinte_sha256(provisoire) != empreinte:
            raise OSError(traduire("depot_empreinte_differente"))
        os.utime(provisoire, (date.timestamp(), date.timestamp()))
        os.rename(provisoire, final)
    except BaseException:
        provisoire.unlink(missing_ok=True)
        raise
    return DEPOSEE, empreinte


def empreintes_classees(configuration):
    """Empreintes des documents que le journal des actions dit classés et non annulés."""
    chemin = configuration["suivi"].get("journal")
    if not chemin:
        return set()
    lignes = journal_actions.lire_lignes(chemin)
    return {ligne["empreinte_avant"] for ligne in journal_actions.actions_actives(lignes) if ligne.get("empreinte_avant")}


def _deposer_pieces(connexion, resultat, pieces, dossier, registre, connues, suffixe, journal):
    source_id = resultat.source["id"]
    for piece in pieces:
        if registre.connu(source_id, piece.cle):
            continue
        try:
            octets = scanner_imap.telecharger(connexion, piece)
            empreinte = hashlib.sha256(octets).hexdigest()
            if empreinte in connues:
                action = DOUBLON
            else:
                action, empreinte = deposer(octets, piece.nom, dossier, piece.date, suffixe)
        except (scanner_imap.ErreurImap, OSError, ValueError) as erreur:
            resultat.complet = False
            resultat.erreurs.append(traduire("imap_depot_impossible", type=type(erreur).__name__))
            journal.ajouter("depot_imap_echec", source_id=source_id, raison=type(erreur).__name__)
            if isinstance(erreur, scanner_imap.ConnexionImpossible):
                return
            continue
        registre.noter(source_id, piece.cle, empreinte)
        connues.add(empreinte)
        resultat.deposees += action == DEPOSEE
        journal.ajouter("depot_imap", source_id=source_id, action=action, empreinte=empreinte)


def traiter_source(configuration, source, suivi, maintenant, deposer_les_pieces, registre, connues, journal, environ, ouvrir):
    resultat = ResultatSource(source)
    if source["authentification"] not in ("login", "oauth2"):
        resultat.ignoree = True
        resultat.erreurs.append(traduire("imap_authentification_non_prise_en_charge", mode=source['authentification']))
        return resultat
    if source["ssl"] is not True:
        resultat.ignoree = True
        resultat.erreurs.append(traduire("imap_tls_exige"))
        return resultat
    if source["authentification"] == "login":
        mot_de_passe = environ.get(source["mot_de_passe_env"])
        if not mot_de_passe:
            resultat.ignoree = True
            resultat.erreurs.append(traduire("imap_variable_non_definie", variable=source['mot_de_passe_env']))
            return resultat
        authentifier = lambda connexion: scanner_imap.authentifier(connexion, source["utilisateur"], mot_de_passe)  # noqa: E731
    else:
        if not os.path.exists(source["token_fichier"]):
            resultat.ignoree = True
            resultat.erreurs.append(traduire("imap_jeton_absent", identifiant=source['id']))
            return resultat
        try:
            jeton = oauth2_google.jeton_d_acces(source["client_fichier"], source["token_fichier"], configuration["oauth2"])
        except oauth2_google.ErreurOAuth2 as erreur:
            resultat.erreurs.append(texte_de(erreur))
            journal.ajouter("scan_imap", source_id=source["id"], pieces=0, ecartees_taille=0, complet=False, erreurs=1,
                            dry_run=not deposer_les_pieces)
            return resultat
        authentifier = lambda connexion: scanner_imap.authentifier_xoauth2(connexion, source["utilisateur"], jeton)  # noqa: E731

    imap = configuration["imap"]
    parametres = configuration["suivi"]
    depuis = scanner_local.date_seuil(suivi.get(source["id"]), parametres.get("securite_jours", 1),
                                      parametres.get("premier_scan_jours", 90), maintenant)
    extensions = scanner_local.normaliser_extensions(configuration.get("extensions_cibles", []))
    taille_max = int(imap["taille_max_piece_mo"] * 1024 * 1024)
    dossier = dossier_vide_poches(configuration, source)
    suffixe = configuration["nommage"]["suffixe_collision"]
    connexion = None
    try:
        connexion = ouvrir(source["serveur"], source["port"], imap["delai_secondes"])
        authentifier(connexion)
        resultat.complet = True
        for nom_dossier in source["dossiers"]:
            try:
                pieces, ecartees = scanner_imap.lister_dossier(connexion, source["id"], nom_dossier, depuis, extensions, taille_max)
            except scanner_imap.ConnexionImpossible:
                raise
            except scanner_imap.ErreurImap as erreur:
                resultat.complet = False
                resultat.erreurs.append(traduire("imap_dossier_erreur", dossier=nom_dossier, erreur=texte_de(erreur)))
                continue
            resultat.pieces += pieces
            resultat.ecartees_taille += ecartees
            if deposer_les_pieces:
                _deposer_pieces(connexion, resultat, pieces, dossier, registre, connues, suffixe, journal)
    except scanner_imap.ErreurImap as erreur:
        resultat.complet = False
        resultat.erreurs.append(texte_de(erreur))
    finally:
        if connexion is not None:
            scanner_imap.fermer(connexion)
    if resultat.ecartees_taille:
        resultat.complet = False
        resultat.erreurs.append(traduire("imap_pieces_ecartees", nombre=resultat.ecartees_taille))
    journal.ajouter("scan_imap", source_id=source["id"], pieces=len(resultat.pieces), ecartees_taille=resultat.ecartees_taille,
                    complet=resultat.complet, erreurs=len(resultat.erreurs), dry_run=not deposer_les_pieces)
    return resultat


def traiter(configuration, suivi, journal, maintenant, deposer_les_pieces, environ=None, ouvrir=None):
    """Lit chaque source IMAP ; rend (résultats, dates à faire avancer, sources en échec).

    Une source sans mot de passe défini, ou sans fichier de jeton, est ignorée sans connexion et sans échec. La date d'une
    source n'avance que si chaque dossier a été lu en entier et chaque pièce déposée ou connue.
    """
    environ = os.environ if environ is None else environ
    ouvrir = ouvrir or scanner_imap.ouvrir_connexion
    chemin_registre = Path(configuration["suivi"]["fichier_date"]).parent / "imap_deposes.json"
    registre = RegistreRapatries(chemin_registre)
    connues = empreintes_classees(configuration) | {e for source in registre.donnees.values() for e in source.values()}
    resultats, dates, en_echec = [], {}, set()
    for source in configuration.get("sources_imap", []):
        resultat = traiter_source(configuration, source, suivi, maintenant, deposer_les_pieces, registre, connues,
                                  journal, environ, ouvrir)
        resultats.append(resultat)
        if resultat.ignoree:
            continue
        if resultat.complet:
            dates[source["id"]] = maintenant
        else:
            en_echec.add(source["id"])
    return resultats, dates, en_echec


def afficher(resultats, deposer_les_pieces):
    for resultat in resultats:
        mention = "" if deposer_les_pieces else " " + traduire("imap_mention_dry_run")
        ecrire(traduire("imap_source", identifiant=resultat.source['id'], mention=mention))
        for piece in resultat.pieces:
            ecrire(traduire("imap_piece", nom=f"{piece.nom:<50s}", taille=piece.taille_octets, unite=traduire("unite_octet"), date=f"{piece.date:%Y-%m-%d}"), 2)
        if not resultat.pieces and resultat.complet:
            ecrire(traduire("imap_aucune_piece"), 2)
        for erreur in resultat.erreurs:
            ecrire(traduire("avertissement_ligne", detail=erreur), 2)
        print()
