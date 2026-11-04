"""Tri par décision : un modèle `decision` d'Ollama rend la probabilité qu'un document soit non administratif.

Le verdict sort de seuils mesurés pour ce modèle et écrits dans la configuration. Sans modèle, seuils ou modèle
d'objet utilisables, le tri revient au modèle de génération du rôle `tri_rapide`, avec un motif d'une liste fermée.
"""

import time
from dataclasses import dataclass

from modules import appel_ollama, classification, modeles
from modules.messages import texte_de, traduire

ROLE = "tri_decision"
ROLE_OBJET = "objet"
CAPACITE = "decision"
CLE_QUESTION = "nature"

# Les seuils de production ont été mesurés avec cette question exacte : la changer impose de les remesurer.
QUESTION_TRI = {CLE_QUESTION: {
    "type": "choice",
    "instructions": "Ce document est-il administratif (émis par un organisme ou adressé à une personne ou entreprise, même long) "
                    "ou non administratif (manuel, mode d'emploi, notice, documentation technique, livre, cours, recette, "
                    "publicité, article, texte littéraire, correspondance privée, même de dizaines de pages) ?",
    "criteria": {
        classification.ADMINISTRATIF: "Courrier, facture, avis, attestation, contrat et conditions générales, relevé, justificatif, "
                                      "pièce d'identité, devis, bon de commande, déclaration.",
        classification.NON_ADMINISTRATIF: "Manuel, mode d'emploi, notice, documentation technique d'un logiciel ou d'un appareil, livre, "
                                          "support de cours, recette, publicité, article, texte littéraire, correspondance privée."}}}

MOTIF_MODELE_ABSENT = "modele_absent"
MOTIF_PAS_UN_MODELE_DECISION = "pas_un_modele_decision"
MOTIF_SEUILS_ABSENTS = "seuils_absents"
MOTIF_OBJET_ABSENT = "objet_absent"
MOTIF_OLLAMA_SANS_SYSTEMONE = "ollama_sans_systemone"
MOTIFS_REPLI = (MOTIF_MODELE_ABSENT, MOTIF_PAS_UN_MODELE_DECISION, MOTIF_SEUILS_ABSENTS, MOTIF_OBJET_ABSENT,
                MOTIF_OLLAMA_SANS_SYSTEMONE)


def libelle_repli(motif, modele=None):
    """Le libellé d'un motif de `MOTIFS_REPLI`, qui nomme la clé de configuration à corriger."""
    libelles = {MOTIF_MODELE_ABSENT: traduire("repli_tri_modele_absent"),
                MOTIF_PAS_UN_MODELE_DECISION: traduire("repli_tri_pas_un_modele_decision", modele=modele),
                MOTIF_SEUILS_ABSENTS: traduire("repli_tri_seuils_absents", modele=modele),
                MOTIF_OBJET_ABSENT: traduire("repli_tri_objet_absent"),
                MOTIF_OLLAMA_SANS_SYSTEMONE: traduire("repli_tri_ollama_sans_systemone")}
    return libelles[motif]


@dataclass(frozen=True)
class Choix:
    """Un tri par décision utilisable : le modèle, ses seuils et le modèle qui rend l'objet."""
    modele: str
    non_administratif: float
    administratif: float
    caracteres_min: int
    objet: str


@dataclass(frozen=True)
class Resolution:
    """Ce que la configuration et les modèles installés permettent : un `Choix`, ou le motif du repli."""
    choix: Choix = None
    motif: str = None
    declare: bool = False
    modele: str = None


def _nombre(valeur):
    return isinstance(valeur, (int, float)) and not isinstance(valeur, bool)


def seuils_valides(entree):
    """Rend (non_administratif, administratif, caracteres_min) d'une entrée de `seuils_tri_decision`, ou None si elle est invalide."""
    if not isinstance(entree, dict):
        return None
    haut, bas, minimum = entree.get("non_administratif"), entree.get("administratif"), entree.get("caracteres_min")
    if not (_nombre(haut) and _nombre(bas)) or not isinstance(minimum, int) or isinstance(minimum, bool) or minimum < 0:
        return None
    # Une comparaison avec NaN est toujours fausse : un seuil NaN est refusé ici.
    if not 0 <= bas <= haut <= 1:
        return None
    return float(haut), float(bas), minimum


def _entree_du_modele(table, modele):
    if not isinstance(table, dict):
        return None
    for cle in (modele, modele[:-len(":latest")] if modele.endswith(":latest") else None):
        if cle is not None and cle in table:
            return table[cle]
    return None


def declare(configuration):
    """Vrai si la configuration déclare au moins une préférence pour le rôle `tri_decision`."""
    return bool(configuration.get("ollama", {}).get("roles", {}).get(ROLE))


def resoudre(configuration, capacites):
    """Rend la `Resolution` du rôle `tri_decision` d'après `capacites`, {nom installé: capacités ou None}."""
    roles = configuration.get("ollama", {}).get("roles", {})
    preferences = roles.get(ROLE) or []
    if not preferences:
        return Resolution()
    retenus = modeles.preferences_installees(preferences, capacites)
    if not retenus:
        return Resolution(motif=MOTIF_MODELE_ABSENT, declare=True)
    modele = retenus[0]
    # Une capacité inconnue (Ollama qui ne la publie pas) ne décide rien : l'appel tranche, un 404 fait revenir à la génération.
    capacites_du_modele = capacites.get(modele)
    if capacites_du_modele is not None and CAPACITE not in capacites_du_modele:
        return Resolution(motif=MOTIF_PAS_UN_MODELE_DECISION, declare=True, modele=modele)
    seuils = seuils_valides(_entree_du_modele(configuration.get("classification", {}).get("seuils_tri_decision"), modele))
    if seuils is None:
        return Resolution(motif=MOTIF_SEUILS_ABSENTS, declare=True, modele=modele)
    objets = modeles.preferences_installees(roles.get(ROLE_OBJET) or [], capacites)
    if not objets:
        return Resolution(motif=MOTIF_OBJET_ABSENT, declare=True, modele=modele)
    return Resolution(Choix(modele, *seuils, objets[0]), declare=True, modele=modele)


def verdict_par_seuils(p, choix):
    """`p` à partir du seuil haut vaut non administratif, sous le seuil bas administratif, entre les deux incertain."""
    if p >= choix.non_administratif:
        return classification.NON_ADMINISTRATIF
    if p < choix.administratif:
        return classification.ADMINISTRATIF
    return classification.INCERTAIN


def probabilite_non_administratif(reponses):
    """Rend la probabilité de non administratif, arrondie comme au banc des seuils ; ValueError si la réponse sort de la forme attendue."""
    question = reponses.get(CLE_QUESTION) if isinstance(reponses, dict) else None
    probabilites = question.get("probabilities") if isinstance(question, dict) else None
    if not isinstance(probabilites, dict) or not {classification.ADMINISTRATIF, classification.NON_ADMINISTRATIF} <= set(probabilites):
        raise ValueError(traduire("tri_decision_reponse_invalide"))
    p = probabilites[classification.NON_ADMINISTRATIF]
    if not _nombre(p) or not 0 <= p <= 1:
        raise ValueError(traduire("tri_decision_probabilite_invalide"))
    return round(float(p), 4)


def caracteres_alphanumeriques(texte):
    return sum(1 for caractere in texte if caractere.isalnum())


def trier(texte, parametres, configuration_ollama, choix, keep_alive, decider=appel_ollama.decider):
    """Rend le `Tri` d'un texte par le modèle decision de `choix`, sans objet.

    Une réponse invalide ou une erreur d'appel vaut `incertain` avec sa raison ; `PointAccesAbsent` remonte à la cascade.
    """
    debut = time.perf_counter()
    if caracteres_alphanumeriques(texte) < choix.caracteres_min:
        return classification.Tri(classification.INCERTAIN, choix.modele, time.perf_counter() - debut,
                                  traduire("tri_decision_texte_court", minimum=choix.caracteres_min))
    etat = texte[:parametres.get("caracteres_max_tri", parametres["caracteres_max_prompt"])]
    try:
        reponses = decider(configuration_ollama["url"], choix.modele, etat, QUESTION_TRI,
                           configuration_ollama.get("timeout_secondes", 120), keep_alive)
        p = probabilite_non_administratif(reponses)
    except appel_ollama.PointAccesAbsent:
        raise
    except (ValueError, appel_ollama.ErreurOllama) as erreur:
        return classification.Tri(classification.INCERTAIN, choix.modele, time.perf_counter() - debut, texte_de(erreur))
    return classification.Tri(verdict_par_seuils(p, choix), choix.modele, time.perf_counter() - debut, p_non_administratif=p)
