"""Extraction du texte d'un PDF ou d'une image.

Un PDF passe par `pdftotext` ; sans couche texte suffisante, `pdftoppm` rend des pages que le
modèle d'OCR lit. Une image va directement au modèle. Le texte ne quitte pas la mémoire : les
pages rendues vivent dans un `tmpfs`, jamais sur le disque.
"""

import subprocess
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path

from modules import appel_ollama
from modules import coffres
from modules.messages import texte_de, traduire

EXTENSIONS_IMAGE = {".png", ".jpg", ".jpeg"}
SAUT_DE_PAGE = "\f"


@dataclass(frozen=True)
class Extraction:
    texte: str
    methode: str  # couche_texte, ocr ou echec
    caracteres: int  # alphanumériques, avant troncature
    pages: int
    modele: str | None
    duree_secondes: float
    raison: str = ""


class ErreurExtraction(Exception):
    """Un outil ou le modèle n'a pas rendu de texte."""


def compter_alphanumeriques(texte):
    return sum(1 for caractere in texte if caractere.isalnum())


def _lancer(commande, delai, executer):
    try:
        resultat = executer(commande, capture_output=True, timeout=delai)
    except (OSError, subprocess.TimeoutExpired) as erreur:
        raise ErreurExtraction(traduire("extraction_commande_echec", commande=commande[0], erreur=texte_de(erreur))) from erreur
    if resultat.returncode != 0:
        raise ErreurExtraction(traduire("extraction_commande_code", commande=commande[0], code=resultat.returncode))
    return resultat.stdout


def _texte_pdf(chemin, delai, executer):
    sortie = _lancer(["pdftotext", "-layout", str(chemin), "-"], delai, executer)
    return sortie.decode("utf-8", errors="replace")


def _pages_png(chemin, parametres, repertoire, executer):
    prefixe = Path(repertoire) / "page"
    _lancer(["pdftoppm", "-r", str(parametres["resolution_ocr"]),
             "-f", "1", "-l", str(parametres["pages_ocr"]), "-png", str(chemin), str(prefixe)],
            parametres["timeout_outils_secondes"], executer)
    # La numérotation de pdftoppm est complétée de zéros : l'ordre alphabétique est l'ordre des pages.
    return sorted(Path(repertoire).glob("page-*.png"))


def _ocr(images, configuration_ollama, parametres, modele, generer):
    textes = []
    for rang, image in enumerate(images):
        derniere = rang == len(images) - 1
        textes.append(generer(
            configuration_ollama["url"], modele, parametres["consigne_ocr"], [image],
            configuration_ollama.get("timeout_secondes", 120),
            0 if derniere else configuration_ollama["keep_alive_entre_pages"],
        ))
    return "\n".join(textes)


def _resultat(texte, methode, pages, modele, debut, parametres):
    return Extraction(texte[:parametres["taille_max_texte"]], methode, compter_alphanumeriques(texte),
                      pages, modele, time.perf_counter() - debut)


def extraire(chemin, parametres, configuration_ollama, modele_ocr,
             executer=subprocess.run, generer=appel_ollama.generer):
    """Rend l'`Extraction` de `chemin` ; une panne d'outil ou de modèle rend la méthode `echec`."""
    debut = time.perf_counter()
    chemin = Path(chemin)
    try:
        if chemin.suffix.lower() in EXTENSIONS_IMAGE:
            texte = _ocr([chemin.read_bytes()], configuration_ollama, parametres, modele_ocr, generer)
            return _resultat(texte, "ocr", 1, modele_ocr, debut, parametres)

        texte = ""
        try:
            texte = _texte_pdf(chemin, parametres["timeout_outils_secondes"], executer)
        except ErreurExtraction:
            pass  # un PDF sans texte exploitable passe à l'OCR ; pdftoppm dira s'il est illisible
        if compter_alphanumeriques(texte) >= parametres["seuil_caracteres_alphanumeriques"]:
            return _resultat(texte, "couche_texte", max(1, texte.count(SAUT_DE_PAGE)), None, debut, parametres)

        repertoire = Path(parametres["repertoire_temporaire"])
        if coffres.type_systeme_fichiers(repertoire) != "tmpfs":
            raise ErreurExtraction(traduire("extraction_pas_tmpfs", repertoire=repertoire))
        with tempfile.TemporaryDirectory(dir=repertoire, prefix="skrivagner-") as temporaire:
            pages = _pages_png(chemin, parametres, temporaire, executer)
            if not pages:
                raise ErreurExtraction(traduire("extraction_aucune_page"))
            texte = _ocr([page.read_bytes() for page in pages], configuration_ollama, parametres,
                         modele_ocr, generer)
        return _resultat(texte, "ocr", len(pages), modele_ocr, debut, parametres)
    except (ErreurExtraction, appel_ollama.ErreurOllama, OSError) as erreur:
        return Extraction("", "echec", 0, 0, None, time.perf_counter() - debut, texte_de(erreur))
