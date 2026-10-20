"""Nom normalisé d'un document d'après `nommage` de la configuration."""

from datetime import date


def _assainir(valeur, espaces_vers):
    # Un émetteur vient du texte d'un document : un séparateur de chemin
    # y fabriquerait un répertoire hors de la destination.
    return str(valeur).strip().replace("/", espaces_vers).replace("\\", espaces_vers).replace(" ", espaces_vers)


def nommer(nommage, verdict, extension, date_repli, a_verifier=False):
    """Rend le nom normalisé ; `date_repli` (datetime ou date) sert quand le verdict n'a pas de date."""
    espaces_vers = nommage.get("espaces_vers", "-")
    if isinstance(verdict.date, date):
        texte_date = verdict.date.strftime(nommage["date_format"])
    else:
        texte_date = nommage["date_inconnue_prefixe"] + date_repli.strftime(nommage["date_format"])
    nom = nommage["format"].format(
        date=texte_date,
        emetteur=_assainir(verdict.emetteur or nommage["emetteur_inconnu"], espaces_vers),
        categorie=_assainir(verdict.categorie, espaces_vers),
        personne=_assainir(verdict.personne or "", espaces_vers),
        ext=extension.lower(),
    )
    return nommage["prefixe_a_verifier"] + nom if a_verifier else nom
