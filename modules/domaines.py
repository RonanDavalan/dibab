"""Table de routage des documents vers le coffre de leur domaine.

La classification rend un verdict ; la destination se décide ici par une règle
déterministe sur le domaine et les signaux cités, jamais par le seul jugement
du modèle.
"""

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

PERSONNEL = "personnel"
PROFESSIONNEL = "professionnel"
MIXTE = "mixte"
INCERTAIN = "incertain"
DOMAINES = (PERSONNEL, PROFESSIONNEL, MIXTE, INCERTAIN)

COFFRES = (PERSONNEL, PROFESSIONNEL)

CLASSEMENT = "classement"
A_VERIFIER = "a_verifier"


@dataclass(frozen=True)
class Verdict:
    """Ce que la classification rend d'un document."""
    administratif: bool
    domaine: str
    categorie: str
    signaux: tuple = ()
    date: object = None
    emetteur: str = None
    personne: str = None
    destinataire: str = None


@dataclass(frozen=True)
class Cible:
    """Un coffre et la zone (classement ou à vérifier) où le document est rangé."""
    coffre: str
    zone: str


def a_signal_professionnel(signaux):
    return any(signal.get("domaine") == PROFESSIONNEL for signal in signaux)


def router(verdict, pieces_communes=()):
    """Rend la liste des cibles d'un document : vide, une, ou deux pour une pièce commune.

    Un domaine hors de DOMAINES vaut incertain : le texte d'un document ne doit
    pas pouvoir fabriquer une destination.
    """
    if not verdict.administratif:
        return []
    if verdict.categorie in pieces_communes:
        return [Cible(coffre, CLASSEMENT) for coffre in COFFRES]

    domaine = verdict.domaine if verdict.domaine in DOMAINES else INCERTAIN
    if domaine in (PERSONNEL, PROFESSIONNEL):
        return [Cible(domaine, CLASSEMENT)]
    if domaine == MIXTE or a_signal_professionnel(verdict.signaux):
        return [Cible(PROFESSIONNEL, A_VERIFIER)]
    return [Cible(PERSONNEL, A_VERIFIER)]


def dossier_cible(cible, destinations):
    """Rend le répertoire d'une cible d'après la table `destinations` de la configuration."""
    destination = destinations[cible.coffre]
    cle = "sous_repertoire_classement" if cible.zone == CLASSEMENT else "sous_repertoire_a_verifier"
    return Path(destination["racine"]) / destination[cle]


def domaine_emetteur(emetteurs_connus, emetteur):
    """Rend le domaine déclaré d'un émetteur connu, ou None."""
    for entrees in emetteurs_connus.values():
        for entree in entrees:
            if str(entree.get("nom", "")).casefold() == emetteur.casefold():
                return entree.get("domaine")
    return None


NATURES_FORTES = ("destinataire", "emetteur", "emetteur_connu")
NATURE_MENTION = "mention"


def decider_domaine(signaux, domaine_connu=None):
    """Rend le domaine d'un document d'après ses signaux et le domaine déclaré de son émetteur.

    Seuls les signaux forts (destinataire, émetteur) décident ; une mention (TVA, SIRET) figure
    sur les factures de n'importe quel fournisseur et ne dit rien du destinataire. Deux domaines
    en désaccord donnent `mixte`. Sans signal fort, un émetteur déclaré `mixte` donne `mixte`,
    sinon `incertain` : la mention seule reste visible de `router` par `a_signal_professionnel`.
    """
    votes = {signal.get("domaine") for signal in signaux if signal.get("nature") in NATURES_FORTES}
    if domaine_connu in (PERSONNEL, PROFESSIONNEL):
        votes.add(domaine_connu)
    votes &= {PERSONNEL, PROFESSIONNEL}
    if len(votes) == 2:
        return MIXTE
    if votes:
        return votes.pop()
    return MIXTE if domaine_connu == MIXTE else INCERTAIN


def verdict_depuis_dict(donnees):
    """Construit un Verdict depuis un dict à champs fermés ; ValueError si un champ manque ou n'est pas valide."""
    for champ in ("administratif", "categorie"):
        if champ not in donnees:
            raise ValueError(f"champ absent du verdict : {champ}")
    if not isinstance(donnees["administratif"], bool):
        raise ValueError("`administratif` doit valoir true ou false")
    signaux = donnees.get("signaux", ())
    if not all(isinstance(signal, dict) for signal in signaux):
        raise ValueError("chaque signal doit être un objet {domaine, libelle}")
    date = donnees.get("date")
    if date is not None:
        date = datetime.strptime(date, "%Y-%m-%d").date()
    return Verdict(
        administratif=donnees["administratif"],
        domaine=donnees.get("domaine", INCERTAIN),
        categorie=donnees["categorie"],
        signaux=tuple(signaux),
        date=date,
        emetteur=donnees.get("emetteur"),
        personne=donnees.get("personne"),
    )
