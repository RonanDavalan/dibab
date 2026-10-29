"""Messages de l'outil : un dictionnaire plat par langue, choisi dans l'environnement (spécification 29).

Un dictionnaire est un fichier UTF-8 `modules/langues/<langue>.txt`, une entrée `clé=valeur` par ligne ; `\\n` y écrit
un retour à la ligne et `\\\\` une barre oblique inverse. La langue est fixée au démarrage, dans l'ordre LC_ALL,
LC_MESSAGES, LANG. Un journal reçoit toujours l'anglais : `Texte.en` recompose le message dans la langue source.
"""
import argparse
import os
import re
import sys
from pathlib import Path

LANGUES = ("en", "fr", "de", "es")
LANGUE_SOURCE = "en"
DOSSIER = Path(__file__).resolve().parent / "langues"

_VARIABLES_LANGUE = ("LC_ALL", "LC_MESSAGES", "LANG")
_ECHAPPEMENT = re.compile(r"\\(n|\\)")
_langue_choisie = None
_dictionnaires = {}


def code_langue(environ):
    """Rend la langue des messages d'après l'environnement : `en` hors des quatre langues et pour C ou POSIX."""
    for variable in _VARIABLES_LANGUE:
        valeur = environ.get(variable, "")
        if valeur:
            code = re.split(r"[_.@]", valeur, maxsplit=1)[0].lower()
            return code if code in LANGUES else LANGUE_SOURCE
    return LANGUE_SOURCE


def initialiser(environ=None):
    """Fixe la langue des messages ; sans argument, lit l'environnement du processus."""
    global _langue_choisie
    _langue_choisie = code_langue(os.environ if environ is None else environ)
    return _langue_choisie


def langue():
    return _langue_choisie or initialiser()


def lire_dictionnaire(chemin):
    """Rend {clé: valeur} du fichier `chemin`, ou {} s'il est illisible."""
    entrees = {}
    try:
        lignes = Path(chemin).read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeDecodeError):
        return {}
    for ligne in lignes:
        if not ligne.strip() or ligne.startswith("#") or "=" not in ligne:
            continue
        cle, valeur = ligne.split("=", 1)
        entrees[cle] = _ECHAPPEMENT.sub(lambda m: "\n" if m.group(1) == "n" else "\\", valeur)
    return entrees


def dictionnaire(code):
    if code not in _dictionnaires:
        _dictionnaires[code] = lire_dictionnaire(DOSSIER / f"{code}.txt")
    return _dictionnaires[code]


class Texte(str):
    """Message déjà composé dans la langue courante, qui garde sa clé et ses valeurs pour être recomposé."""

    def __new__(cls, texte, cle, valeurs):
        objet = super().__new__(cls, texte)
        objet.cle = cle
        objet.valeurs = valeurs
        return objet

    def en(self, code=LANGUE_SOURCE):
        return _composer(self.cle, self.valeurs, code)


def _composer(cle, valeurs, code):
    valeurs = {nom: valeur.en(code) if isinstance(valeur, Texte) else valeur for nom, valeur in valeurs.items()}
    for essai in dict.fromkeys((code, LANGUE_SOURCE)):
        modele = dictionnaire(essai).get(cle)
        if modele is None:
            continue
        try:
            return modele.format(**valeurs)
        except (KeyError, IndexError, ValueError):
            continue
    return f"<{cle}>"


def _produire(cle, valeurs):
    return Texte(_composer(cle, valeurs, langue()), cle, valeurs)


def traduire(_cle, /, **valeurs):
    """Rend le message de la clé dans la langue courante ; l'anglais si la clé y manque, puis `<clé>`."""
    return _produire(_cle, valeurs)


def traduire_compose(cle, /, **valeurs):
    """Comme `traduire`, pour la seule famille `diagnostic_<identifiant>_<état>` dont la clé est composée ; un test énumère ces clés."""
    return _produire(cle, valeurs)


def texte_de(erreur):
    """Rend le message d'une exception en gardant sa clé quand l'erreur du produit en porte une."""
    if erreur.args and isinstance(erreur.args[0], Texte):
        return erreur.args[0]
    return str(erreur)


def pour_journal(valeur):
    """Rend `valeur` prête pour un journal : chaque message du produit y est écrit en anglais, jamais dans la langue de la session."""
    if isinstance(valeur, Texte):
        return valeur.en()
    if isinstance(valeur, dict):
        return {cle: pour_journal(element) for cle, element in valeur.items()}
    if isinstance(valeur, (list, tuple, set)):
        return [pour_journal(element) for element in valeur]
    return valeur


class _Formateur(argparse.HelpFormatter):
    def add_usage(self, usage, actions, groups, prefix=None):
        super().add_usage(usage, actions, groups, prefix if prefix is not None else traduire("aide_usage") + " ")


class ParseurTraduit(argparse.ArgumentParser):
    """Analyseur dont l'aide et l'erreur de ligne de commande sont celles du dictionnaire, jamais les mots d'`argparse`."""

    def __init__(self, **options):
        super().__init__(add_help=False, formatter_class=_Formateur, **options)
        self._titre_options = traduire("aide_titre_options")
        self._optionals.title = self._titre_options
        self.add_argument("-h", "--help", action="help", help=traduire("aide_option_aide"))

    def format_help(self):
        # argparse ajoute lui-même deux-points au titre d'une section ; le dictionnaire porte le titre complet.
        return super().format_help().replace(self._titre_options + ":", self._titre_options)

    def error(self, message):
        sys.stderr.write(traduire("erreur_ligne_de_commande", programme=self.prog) + "\n")
        sys.exit(2)


def ecrire(texte, retrait=0, sortie=None):
    """Écrit une ligne de sortie, décalée de `retrait` espaces."""
    ligne = " " * retrait + texte
    print(ligne, file=sortie or sys.stdout, flush=True)
