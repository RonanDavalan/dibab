"""Tests de l'extraction et de l'appel Ollama, sur des documents factices générés à la volée."""

import json
import os
import subprocess
import tempfile
import urllib.error
import urllib.request
from pathlib import Path

import pytest

from modules import appel_ollama, coffres, extraction

TEXTE = "Facture Zephyr numero 4815162342 montant total mille deux cent trente quatre euros"
PARAMETRES = {
    "seuil_caracteres_alphanumeriques": 200, "pages_ocr": 3, "resolution_ocr": 200,
    "taille_max_texte": 20000, "repertoire_temporaire": "/dev/shm", "timeout_outils_secondes": 60,
    "consigne_ocr": "Transcris.",
}
OLLAMA = {"url": "http://x", "timeout_secondes": 7, "keep_alive_entre_pages": "2m"}

# magick est la seule dépendance de génération des documents : sans lui, ces tests ne disent rien.
pytestmark = pytest.mark.skipif(
    subprocess.run(["which", "magick"], capture_output=True).returncode != 0, reason="magick absent")


def png_factice(chemin, texte=TEXTE):
    subprocess.run(["magick", "-size", "1400x200", "xc:white", "-pointsize", "28", "-fill", "black",
                    "-annotate", "+20+100", texte, str(chemin)], check=True)
    return chemin


def pdf_sans_couche_texte(chemin, pages=1):
    # ImageMagick écrit un PDF d'image : aucune couche texte.
    with tempfile.TemporaryDirectory() as temporaire:
        sources = [str(png_factice(Path(temporaire) / f"{rang}.png", f"{TEXTE} page {rang + 1}"))
                   for rang in range(pages)]
        subprocess.run(["magick", *sources, str(chemin)], check=True)
    return chemin


def pdf_avec_couche_texte(chemin, texte):
    # ImageMagick ne sait pas écrire de texte dans un PDF : un PDF minimal à la main, police standard.
    # Lignes courtes : le texte qui dépasse la page est rogné par pdftotext.
    lignes = [texte[i:i + 70] for i in range(0, len(texte), 70)]
    flux = ("BT /F1 12 Tf 14 TL 20 780 Td " + " T* ".join(f"({ligne}) Tj" for ligne in lignes) + " ET").encode("latin-1")
    objets = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 600 800] /Contents 4 0 R "
        b"/Resources << /Font << /F1 5 0 R >> >> >>",
        b"<< /Length %d >>\nstream\n" % len(flux) + flux + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    contenu = bytearray(b"%PDF-1.4\n")
    positions = []
    for numero, objet in enumerate(objets, 1):
        positions.append(len(contenu))
        contenu += b"%d 0 obj\n" % numero + objet + b"\nendobj\n"
    debut_xref = len(contenu)
    contenu += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objets) + 1)
    for position in positions:
        contenu += b"%010d 00000 n \n" % position
    contenu += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objets) + 1, debut_xref)
    chemin.write_bytes(bytes(contenu))
    return chemin


class FauxOllama:
    """Enregistre les appels de génération et rend un texte fixe."""

    def __init__(self, texte="texte lu par le modele"):
        self.texte = texte
        self.appels = []

    def __call__(self, url, modele, consigne, images, delai, keep_alive):
        self.appels.append({"url": url, "modele": modele, "images": images, "delai": delai,
                            "keep_alive": keep_alive})
        return self.texte


def test_pdf_avec_couche_texte_sans_modele(tmp_path):
    pdf = pdf_avec_couche_texte(tmp_path / "a.pdf", TEXTE + " et encore des mots pour passer le seuil " * 5)
    faux = FauxOllama()
    resultat = extraction.extraire(pdf, PARAMETRES, OLLAMA, "modele-ocr", generer=faux)
    assert resultat.methode == "couche_texte"
    assert "Zephyr" in resultat.texte
    assert resultat.modele is None and faux.appels == []
    assert resultat.caracteres >= 200 and resultat.pages == 1


def test_pdf_sans_couche_texte_passe_a_l_ocr_en_memoire(tmp_path):
    pdf = pdf_sans_couche_texte(tmp_path / "scan.pdf", pages=2)
    faux = FauxOllama("Zephyr lu")
    avant = set(Path("/dev/shm").iterdir())
    resultat = extraction.extraire(pdf, PARAMETRES, OLLAMA, "modele-ocr", generer=faux)
    assert resultat.methode == "ocr" and resultat.modele == "modele-ocr" and resultat.pages == 2
    assert resultat.texte == "Zephyr lu\nZephyr lu"
    assert [appel["images"][0][:4] for appel in faux.appels] == [b"\x89PNG"] * 2
    assert set(Path("/dev/shm").iterdir()) == avant  # répertoire temporaire supprimé


def test_la_derniere_page_decharge_le_modele(tmp_path):
    faux = FauxOllama()
    extraction.extraire(pdf_sans_couche_texte(tmp_path / "scan.pdf", pages=3), PARAMETRES, OLLAMA, "m", generer=faux)
    assert [appel["keep_alive"] for appel in faux.appels] == ["2m", "2m", 0]
    assert {appel["delai"] for appel in faux.appels} == {7}


def test_seules_les_premieres_pages_sont_lues(tmp_path):
    faux = FauxOllama()
    pdf = pdf_sans_couche_texte(tmp_path / "long.pdf", pages=5)
    extraction.extraire(pdf, {**PARAMETRES, "pages_ocr": 2}, OLLAMA, "m", generer=faux)
    assert len(faux.appels) == 2


def test_image_va_directement_au_modele(tmp_path):
    png = png_factice(tmp_path / "photo.png")
    faux = FauxOllama("lu")
    resultat = extraction.extraire(png, PARAMETRES, OLLAMA, "modele-ocr", generer=faux)
    assert (resultat.methode, resultat.pages, resultat.texte) == ("ocr", 1, "lu")
    assert faux.appels[0]["images"] == [png.read_bytes()] and faux.appels[0]["keep_alive"] == 0


def test_texte_tronque_a_la_taille_configuree(tmp_path):
    resultat = extraction.extraire(png_factice(tmp_path / "p.png"), {**PARAMETRES, "taille_max_texte": 10}, OLLAMA,
                                   "m", generer=FauxOllama("x" * 50))
    assert resultat.texte == "x" * 10 and resultat.caracteres == 50


def test_ocr_pdf_refuse_un_repertoire_temporaire_hors_memoire(tmp_path, monkeypatch):
    monkeypatch.setattr(coffres, "type_systeme_fichiers", lambda racine, executer=None: "ext4")
    faux = FauxOllama()
    resultat = extraction.extraire(pdf_sans_couche_texte(tmp_path / "scan.pdf"), PARAMETRES, OLLAMA, "m", generer=faux)
    assert resultat.methode == "echec" and "tmpfs" in resultat.raison and faux.appels == []


def test_fichier_illisible_est_un_echec_sans_exception(tmp_path):
    faux = tmp_path / "casse.pdf"
    faux.write_bytes(b"pas un pdf")
    resultat = extraction.extraire(faux, PARAMETRES, OLLAMA, "m", generer=FauxOllama())
    assert resultat.methode == "echec" and resultat.texte == "" and resultat.raison


def test_panne_ollama_est_un_echec(tmp_path):
    def en_panne(*_, **__):
        raise appel_ollama.ErreurOllama("délai dépassé")
    resultat = extraction.extraire(png_factice(tmp_path / "p.png"), PARAMETRES, OLLAMA, "m", generer=en_panne)
    assert resultat.methode == "echec" and "délai dépassé" in resultat.raison


def test_outils_appeles_sans_shell(tmp_path):
    appels = []

    def espion(commande, **options):
        appels.append((commande, options))
        return subprocess.CompletedProcess(commande, 1, b"", b"")
    extraction.extraire(tmp_path / "x.pdf", PARAMETRES, OLLAMA, "m", executer=espion, generer=FauxOllama())
    assert appels[0][0][0] == "pdftotext" and isinstance(appels[0][0], list)
    assert all(not options.get("shell") for _, options in appels)


class ReponseSimulee:
    def __init__(self, contenu):
        self.contenu = contenu

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def read(self, *_):
        return json.dumps(self.contenu).encode("utf-8")


def test_appel_ollama_construit_la_requete_attendue():
    vu = {}

    def ouvrir(requete, timeout):
        vu["requete"], vu["timeout"] = requete, timeout
        return ReponseSimulee({"response": "texte"})
    rendu = appel_ollama.generer("http://h:1/", "modele", "consigne", [b"\x89PNG"], 9, 0, ouvrir=ouvrir)
    corps = json.loads(vu["requete"].data)
    assert rendu == "texte" and vu["timeout"] == 9
    assert vu["requete"].full_url == "http://h:1/api/generate" and vu["requete"].get_method() == "POST"
    assert corps == {"model": "modele", "prompt": "consigne", "images": ["iVBORw=="], "stream": False,
                     "keep_alive": 0}


def test_appel_ollama_erreurs():
    def refuse(requete, timeout):
        raise urllib.error.URLError("refusé")
    with pytest.raises(appel_ollama.ErreurOllama):
        appel_ollama.generer("http://h", "m", "c", [], 1, 0, ouvrir=refuse)
    with pytest.raises(appel_ollama.ErreurOllama, match="response"):
        appel_ollama.generer("http://h", "m", "c", [], 1, 0, ouvrir=lambda r, timeout: ReponseSimulee({"x": 1}))


@pytest.mark.ollama_reel
def test_ocr_reel_sur_le_png_factice(tmp_path):
    """Ne tourne que si Ollama répond et que DIBAB_MODELE_OCR_ESSAI nomme un modèle installé."""
    url = os.environ.get("DIBAB_OLLAMA_URL_ESSAI", "http://localhost:11434")
    modele = os.environ.get("DIBAB_MODELE_OCR_ESSAI")
    try:
        from modules import modeles
        installes = modeles.lister_modeles_installes(url, 3)
    except modeles.ModeleIndisponible:
        pytest.skip("Ollama ne répond pas")
    if not modele or modele not in installes:
        pytest.skip("DIBAB_MODELE_OCR_ESSAI absent ou non installé")
    png = png_factice(tmp_path / "reel.png")
    resultat = extraction.extraire(png, PARAMETRES, {**OLLAMA, "url": url, "timeout_secondes": 120}, modele)
    assert resultat.methode == "ocr", resultat.raison
    assert "4815162342" in resultat.texte.replace(" ", "")
