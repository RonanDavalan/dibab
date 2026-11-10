"""Scanner IMAP par un faux serveur local : pièces attendues, boîte inchangée, noms piégés, dépôt sans doublon, jusqu'au pipeline."""

import hashlib
import imaplib
import json
import shutil
import ssl
import subprocess
import time
from datetime import datetime, timedelta

import pytest

import dibab
from modules import journal_actions, scanner_imap, sources_imap
from tests.faux_imap import MOT_DE_PASSE, UTILISATEUR, Boite, Serveur, message, piece
from tests.test_classement_execute import TEXTES, arbre, banc, lancer  # noqa: F401

EXTENSIONS = {".pdf", ".jpg"}
MAINTENANT = datetime(2026, 10, 21, 12, 0, 0)
CONTENU_UN = TEXTES[2]["texte"].encode("utf-8")
CONTENU_DEUX = (TEXTES[0]["texte"] + " courriel").encode("utf-8")
NOM_PIEGE_B64 = "=?utf-8?B?Li4vLi4vZXRjL3Bhc3N3ZC5wZGY=?="  # ../../etc/passwd.pdf


@pytest.fixture(autouse=True)
def fuseau_utc(monkeypatch):
    monkeypatch.setenv("TZ", "UTC")
    time.tzset()
    yield
    monkeypatch.delenv("TZ")
    time.tzset()


def boite_standard():
    return Boite([
        message(1, datetime(2026, 10, 20, 9, 0), [piece("facture.pdf", CONTENU_UN)], flags=()),
        message(2, datetime(2026, 10, 20, 10, 0), [
            piece("logo.png", b"png", disposition="INLINE", content_id="<logo>", type_="IMAGE", sous_type="PNG"),
            piece("photo.JPG", b"jpg", type_="IMAGE", sous_type="JPEG"),
            piece("virus.exe", b"exe", type_="APPLICATION", sous_type="OCTET-STREAM"),
            piece("releve.pdf", CONTENU_DEUX, encodage="base64"),
        ], flags=("\\Flagged",)),
        message(3, datetime(2026, 9, 1, 9, 0), [piece("ancien.pdf", b"vieux")], flags=("\\Seen",)),
    ])


@pytest.fixture
def serveur():
    ouverts = []

    def demarrer(boite, **options):
        ouverts.append(Serveur(boite, **options).demarrer())
        return ouverts[-1]

    yield demarrer
    for ouvert in ouverts:
        ouvert.arreter()


def connecter(serveur):
    connexion = imaplib.IMAP4("127.0.0.1", serveur.port)
    scanner_imap.authentifier(connexion, UTILISATEUR, MOT_DE_PASSE)
    return connexion


def lister(serveur, depuis=datetime(2026, 10, 1), taille_max=10_000_000):
    connexion = connecter(serveur)
    try:
        return scanner_imap.lister_dossier(connexion, "imap-test", "INBOX", depuis, EXTENSIONS, taille_max)
    finally:
        scanner_imap.fermer(connexion)


def test_le_faux_serveur_rend_les_pieces_jointes_attendues(serveur):
    pieces, ecartees = lister(serveur(boite_standard()))
    assert [(p.uid, p.partie, p.nom) for p in pieces] == [("1", "2", "facture.pdf"), ("2", "3", "photo.JPG"), ("2", "5", "releve.pdf")]
    assert ecartees == 0 and {p.uidvalidity for p in pieces} == {"1234"}


def test_la_boite_factice_est_inchangee_drapeaux_compris(serveur):
    boite = boite_standard()
    avant = boite.instantane()
    connexion = connecter(serveur(boite))
    pieces, _ = scanner_imap.lister_dossier(connexion, "imap-test", "INBOX", datetime(2026, 10, 1), EXTENSIONS, 10_000_000)
    for une_piece in pieces:
        scanner_imap.telecharger(connexion, une_piece)
    scanner_imap.fermer(connexion)
    assert boite.instantane() == avant
    assert boite.verbes_interdits() == []
    assert boite.parties_demandees and all(peek for _, peek in boite.parties_demandees)
    assert all(numero != "" for numero, _ in boite.parties_demandees)
    assert not any(c.startswith("SELECT") for c in boite.commandes) and any(c.startswith("EXAMINE") for c in boite.commandes)


def test_le_faux_serveur_poserait_seen_sans_peek_ni_lecture_seule(serveur):
    boite = boite_standard()
    connexion = connecter(serveur(boite))
    connexion.select("INBOX")
    connexion.uid("FETCH", "1", "(BODY[2])")
    connexion.logout()
    assert "\\Seen" in boite.messages[0]["flags"]


def test_le_telechargement_decode_la_piece_et_le_corps_n_est_jamais_demande(serveur):
    boite = boite_standard()
    connexion = connecter(serveur(boite))
    pieces, _ = scanner_imap.lister_dossier(connexion, "imap-test", "INBOX", datetime(2026, 10, 1), EXTENSIONS, 10_000_000)
    assert [scanner_imap.telecharger(connexion, p) for p in pieces] == [CONTENU_UN, b"jpg", CONTENU_DEUX]
    scanner_imap.fermer(connexion)
    assert "" not in [numero for numero, _ in boite.parties_demandees]


def test_le_filtre_de_date_ecarte_les_messages_anterieurs(serveur):
    pieces, _ = lister(serveur(boite_standard()), depuis=datetime(2026, 10, 20, 9, 30))
    assert [p.uid for p in pieces] == ["2", "2"]
    tout, _ = lister(serveur(boite_standard()), depuis=datetime(2026, 8, 1))
    assert "ancien.pdf" in [p.nom for p in tout]


def test_une_piece_trop_grosse_est_ecartee_et_comptee(serveur):
    pieces, ecartees = lister(serveur(boite_standard()), taille_max=5)
    assert pieces == [] and ecartees == 3


@pytest.mark.parametrize("brut", [
    "../../etc/passwd.pdf", "..\\..\\windows\\x.pdf", "/etc/cron.d/x.pdf", "facture\x00.pdf", "a\x07b\x1b[31m.pdf",
    ".bashrc.pdf", "facture‮gpj.pdf", "\n.pdf", "x/../y.pdf",
])
def test_un_nom_piege_est_neutralise(brut):
    nom = scanner_imap.nom_de_piece(brut)
    assert "/" not in nom and "\\" not in nom and not nom.startswith(".") and nom not in ("", ".", "..")
    assert all(ord(c) >= 32 and ord(c) != 127 for c in nom) and "‮" not in nom
    assert nom.endswith(".pdf")


def test_un_nom_piege_encode_en_rfc2047_ou_rfc2231_arrive_neutralise(serveur):
    boite = Boite([message(1, datetime(2026, 10, 20, 9, 0), [
        piece(None, CONTENU_UN, nom_brut=f'"{NOM_PIEGE_B64}"'),
        piece(None, CONTENU_DEUX, nom_brut='"facture\x07\x00x.pdf"'),
    ])])
    pieces, _ = lister(serveur(boite))
    assert [p.nom for p in pieces] == [scanner_imap.nom_de_piece("../../etc/passwd.pdf"), scanner_imap.nom_de_piece("facture\x07\x00x.pdf")]
    assert all("/" not in p.nom and not p.nom.startswith(".") for p in pieces)


def test_les_parametres_rfc2231_se_recomposent():
    structure = ["APPLICATION", "PDF", None, None, None, "base64", "12", None,
                 ["ATTACHMENT", ["FILENAME*0*", "utf-8''rel", "FILENAME*1*", "ev%C3%A9.pdf"]], None, None]
    assert scanner_imap.description(structure)[0] == "relevé.pdf"


def test_la_numerotation_des_parties_suit_les_messages_transmis():
    pdf = ["APPLICATION", "PDF", ["NAME", "x.pdf"], None, None, "base64", "4", None, ["ATTACHMENT", ["FILENAME", "x.pdf"]], None, None]
    texte = ["TEXT", "PLAIN", None, None, None, "7bit", "1", "1", None, None, None]
    transmis = ["MESSAGE", "RFC822", None, None, None, "7bit", "9", ["env"], [texte, pdf, "MIXED", None, None, None], "5", None, None, None]
    structure = [texte, transmis, "MIXED", None, None, None]
    assert [numero for numero, _ in scanner_imap.parties(structure)] == ["1", "2", "2.1", "2.2"]
    assert [numero for numero, _ in scanner_imap.parties(pdf)] == ["1"]


def test_un_nom_avec_litteral_est_recompose():
    donnees = [(b'1 (UID 7 INTERNALDATE "20-Oct-2026 09:00:00 +0000" BODYSTRUCTURE (("APPLICATION" "PDF" ("NAME" {10}', b'caf\xc3\xa9"\\ x.pdf'),
               b') NIL NIL "base64" 4 NIL ("ATTACHMENT" ("FILENAME" "a.pdf")) NIL NIL) "MIXED" NIL NIL NIL))']
    message_lu = scanner_imap.analyser_reponses_fetch(donnees)[0]
    assert message_lu["UID"] == "7" and message_lu["BODYSTRUCTURE"][0][2] == ["NAME", 'café"\\ x.pdf']


def test_une_structure_hostile_est_refusee_proprement():
    with pytest.raises(scanner_imap.ErreurImap):
        scanner_imap.analyser_reponses_fetch([("1 (BODYSTRUCTURE " + "(" * 500 + ")").encode()])
    with pytest.raises(scanner_imap.ErreurImap):
        scanner_imap.analyser_reponses_fetch([b"1 (BODYSTRUCTURE (((("])


def test_un_nom_de_dossier_avec_octet_de_controle_est_refuse(serveur):
    connexion = connecter(serveur(boite_standard()))
    with pytest.raises(scanner_imap.ErreurImap):
        scanner_imap.lister_dossier(connexion, "imap-test", "INBOX\r\nA1 DELETE x", datetime(2026, 10, 1), EXTENSIONS, 10)
    scanner_imap.fermer(connexion)


def test_la_date_de_la_commande_search_ne_depend_pas_de_la_langue():
    assert scanner_imap.date_imap(datetime(2026, 2, 3)) == "03-Feb-2026"


def test_authentification_refusee_arrete_la_source(serveur):
    boite = boite_standard()
    ouvert = serveur(boite)
    connexion = imaplib.IMAP4("127.0.0.1", ouvert.port)
    with pytest.raises(scanner_imap.AuthentificationRefusee) as erreur:
        scanner_imap.authentifier(connexion, UTILISATEUR, "mauvais")
    assert "mauvais" not in str(erreur.value)


@pytest.mark.parametrize("mot_de_passe", ["mot-de-passé-ç", 'a"b\\c', "ligne\r\nA2 DELETE INBOX"])
def test_un_mot_de_passe_hors_ascii_imprimable_s_authentifie_sans_injection(serveur, mot_de_passe):
    boite = boite_standard()
    ouvert = serveur(boite, identifiants=(UTILISATEUR, mot_de_passe))
    connexion = imaplib.IMAP4("127.0.0.1", ouvert.port)
    scanner_imap.authentifier(connexion, UTILISATEUR, mot_de_passe)
    scanner_imap.fermer(connexion)
    assert boite.verbes_interdits() == [] and not any("DELETE" in c for c in boite.commandes)


def test_la_connexion_par_defaut_est_tls_avec_verification(monkeypatch):
    appels = {}

    def faux(serveur, port, ssl_context, timeout):
        appels.update(serveur=serveur, port=port, contexte=ssl_context, delai=timeout)
        return object()

    monkeypatch.setattr(scanner_imap.imaplib, "IMAP4_SSL", faux)
    scanner_imap.ouvrir_connexion("imap.exemple.fr", 993, 30)
    assert appels["contexte"].verify_mode == ssl.CERT_REQUIRED and appels["contexte"].check_hostname
    assert (appels["serveur"], appels["port"], appels["delai"]) == ("imap.exemple.fr", 993, 30)


@pytest.mark.skipif(shutil.which("openssl") is None, reason="openssl absent")
def test_une_vraie_connexion_tls_verifie_le_certificat(serveur, tmp_path):
    cle, certificat = tmp_path / "cle.pem", tmp_path / "cert.pem"
    subprocess.run(["openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-keyout", str(cle), "-out", str(certificat),
                    "-days", "1", "-subj", "/CN=localhost", "-addext", "subjectAltName=IP:127.0.0.1"],
                   check=True, capture_output=True)
    serveur_tls = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    serveur_tls.load_cert_chain(certificat, cle)
    ouvert = serveur(boite_standard(), contexte_tls=serveur_tls)
    client = ssl.create_default_context(cafile=str(certificat))
    connexion = scanner_imap.ouvrir_connexion("127.0.0.1", ouvert.port, 10, contexte=client)
    scanner_imap.authentifier(connexion, UTILISATEUR, MOT_DE_PASSE)
    pieces, _ = scanner_imap.lister_dossier(connexion, "imap-test", "INBOX", datetime(2026, 10, 1), EXTENSIONS, 10_000_000)
    assert len(pieces) == 3
    scanner_imap.fermer(connexion)
    with pytest.raises(scanner_imap.ConnexionImpossible):
        scanner_imap.ouvrir_connexion("127.0.0.1", ouvert.port, 10)


def configuration_minimale(tmp_path, port, **source):
    return {
        "destinations": {"personnel": {"racine": str(tmp_path / "coffre")}},
        "suivi": {"fichier_date": str(tmp_path / "coffre" / "logs" / "dernier_scan.json"),
                  "journal": str(tmp_path / "coffre" / "logs" / "journal.jsonl"), "securite_jours": 1, "premier_scan_jours": 30},
        "nommage": {"suffixe_collision": "_{n}"}, "extensions_cibles": [".pdf", ".jpg"],
        "imap": {"delai_secondes": 5, "taille_max_piece_mo": 1},
        "sources_imap": [{"id": "imap-test", "serveur": "127.0.0.1", "port": port, "ssl": True, "authentification": "login",
                          "utilisateur": UTILISATEUR, "mot_de_passe_env": "DIBAB_IMAP_TEST", "dossiers": ["INBOX"],
                          "vide_poches_destination": "vide-poches-imap", **source}],
    }


class JournalMemoire:
    def __init__(self):
        self.lignes = []

    def ajouter(self, evenement, **champs):
        self.lignes.append({"evenement": evenement, **champs})


def ouvrir_clair():
    return lambda serveur, port, delai: imaplib.IMAP4("127.0.0.1", port)


def traiter(configuration, deposer, environ=None, suivi=None, journal=None):
    return sources_imap.traiter(configuration, suivi or {}, journal or JournalMemoire(), MAINTENANT, deposer,
                                environ={"DIBAB_IMAP_TEST": MOT_DE_PASSE} if environ is None else environ, ouvrir=ouvrir_clair())


def test_le_dry_run_liste_sans_rien_telecharger_ni_ecrire(serveur, tmp_path):
    boite = boite_standard()
    configuration = configuration_minimale(tmp_path, serveur(boite).port)
    resultats, dates, en_echec = traiter(configuration, deposer=False)
    assert [p.nom for p in resultats[0].pieces] == ["facture.pdf", "photo.JPG", "releve.pdf"]
    assert boite.parties_demandees == [] and not (tmp_path / "coffre").exists()
    assert en_echec == set() and set(dates) == {"imap-test"}


def test_execute_depose_avec_empreinte_et_le_second_passage_ne_depose_rien(serveur, tmp_path):
    boite = boite_standard()
    avant = boite.instantane()
    configuration = configuration_minimale(tmp_path, serveur(boite).port)
    journal = JournalMemoire()
    resultats, dates, en_echec = traiter(configuration, deposer=True, journal=journal)
    dossier = tmp_path / "coffre" / "vide-poches-imap"
    assert sorted(p.name for p in dossier.iterdir()) == ["facture.pdf", "photo.JPG", "releve.pdf"]
    assert (dossier / "facture.pdf").read_bytes() == CONTENU_UN and oct((dossier / "facture.pdf").stat().st_mode & 0o777) == "0o600"
    assert resultats[0].deposees == 3 and dates and not en_echec
    registre = json.loads((tmp_path / "coffre" / "logs" / "imap_deposes.json").read_text())["imap-test"]
    assert hashlib.sha256(CONTENU_UN).hexdigest() in registre.values()
    assert boite.instantane() == avant and boite.verbes_interdits() == []
    demandes = len(boite.parties_demandees)
    resultats, _, _ = traiter(configuration, deposer=True)
    assert resultats[0].deposees == 0 and len(boite.parties_demandees) == demandes
    assert sorted(p.name for p in dossier.iterdir()) == ["facture.pdf", "photo.JPG", "releve.pdf"]


def test_une_piece_deja_classee_n_est_pas_redeposee(serveur, tmp_path):
    configuration = configuration_minimale(tmp_path, serveur(boite_standard()).port)
    chemin_journal = tmp_path / "coffre" / "logs" / "journal.jsonl"
    chemin_journal.parent.mkdir(parents=True)
    chemin_journal.write_text(json.dumps({"evenement": "action", "id_action": "a1", "empreinte_avant": hashlib.sha256(CONTENU_UN).hexdigest()}) + "\n")
    resultats, _, _ = traiter(configuration, deposer=True)
    assert resultats[0].deposees == 2 and "facture.pdf" not in [p.name for p in (tmp_path / "coffre" / "vide-poches-imap").iterdir()]


def test_une_annulation_du_classement_remet_la_piece_dans_les_candidates(serveur, tmp_path):
    configuration = configuration_minimale(tmp_path, serveur(boite_standard()).port)
    chemin_journal = tmp_path / "coffre" / "logs" / "journal.jsonl"
    chemin_journal.parent.mkdir(parents=True)
    empreinte = hashlib.sha256(CONTENU_UN).hexdigest()
    chemin_journal.write_text(json.dumps({"evenement": "action", "id_action": "a1", "empreinte_avant": empreinte}) + "\n"
                              + json.dumps({"evenement": "annulation", "id_action": "a1"}) + "\n")
    assert sources_imap.empreintes_classees(configuration) == set()


def test_deux_pieces_de_meme_nom_et_de_contenu_different_ne_s_ecrasent_pas(serveur, tmp_path):
    boite = Boite([message(1, datetime(2026, 10, 20, 9, 0), [piece("a.pdf", CONTENU_UN)]),
                   message(2, datetime(2026, 10, 20, 9, 5), [piece("a.pdf", CONTENU_DEUX)])])
    configuration = configuration_minimale(tmp_path, serveur(boite).port)
    traiter(configuration, deposer=True)
    dossier = tmp_path / "coffre" / "vide-poches-imap"
    assert sorted(p.name for p in dossier.iterdir()) == ["a.pdf", "a_2.pdf"]


def test_un_nom_piege_ne_sort_pas_du_vide_poches(serveur, tmp_path):
    boite = Boite([message(1, datetime(2026, 10, 20, 9, 0), [piece("../../evasion.pdf", CONTENU_UN)])])
    configuration = configuration_minimale(tmp_path, serveur(boite).port)
    traiter(configuration, deposer=True)
    fichiers = [p for p in tmp_path.rglob("*") if p.is_file() and p.parent.name != "logs"]
    assert len(fichiers) == 1 and fichiers[0].parent == tmp_path / "coffre" / "vide-poches-imap"
    assert not (tmp_path / "evasion.pdf").exists() and not (tmp_path.parent / "evasion.pdf").exists()


def test_variable_absente_ignore_la_source_sans_connexion(serveur, tmp_path):
    boite = boite_standard()
    configuration = configuration_minimale(tmp_path, serveur(boite).port)
    resultats, dates, en_echec = traiter(configuration, deposer=True, environ={})
    assert resultats[0].ignoree and "DIBAB_IMAP_TEST" in resultats[0].erreurs[0]
    assert boite.commandes == [] and dates == {} and en_echec == set()


def test_ssl_faux_ou_authentification_inconnue_ignore_la_source(serveur, tmp_path):
    boite = boite_standard()
    port = serveur(boite).port
    assert traiter(configuration_minimale(tmp_path, port, ssl=False), deposer=True)[0][0].ignoree
    assert traiter(configuration_minimale(tmp_path, port, authentification="kerberos"), deposer=True)[0][0].ignoree
    assert boite.commandes == []


def test_mauvais_mot_de_passe_echoue_sans_nouvelle_tentative_et_sans_fuite(serveur, tmp_path, capsys):
    boite = boite_standard()
    configuration = configuration_minimale(tmp_path, serveur(boite).port)
    journal = JournalMemoire()
    resultats, dates, en_echec = traiter(configuration, deposer=True, environ={"DIBAB_IMAP_TEST": "secret-erroné-42"}, journal=journal)
    sources_imap.afficher(resultats, True)
    assert en_echec == {"imap-test"} and dates == {}
    assert len([c for c in boite.commandes if c.startswith(("LOGIN", "AUTHENTICATE"))]) == 1
    tout = capsys.readouterr().out + json.dumps(journal.lignes) + "\n".join(boite.commandes)
    assert "secret-erroné-42" not in tout and MOT_DE_PASSE not in tout


def test_le_mot_de_passe_n_apparait_ni_au_journal_ni_a_l_ecran_ni_dans_les_fichiers(serveur, tmp_path, capsys):
    configuration = configuration_minimale(tmp_path, serveur(boite_standard()).port)
    journal = JournalMemoire()
    resultats, _, _ = traiter(configuration, deposer=True, journal=journal)
    sources_imap.afficher(resultats, True)
    contenu = capsys.readouterr().out + json.dumps(journal.lignes, default=str)
    contenu += "".join(p.read_text(errors="ignore") for p in (tmp_path / "coffre" / "logs").rglob("*.json"))
    assert MOT_DE_PASSE not in contenu
    assert "facture.pdf" not in json.dumps(journal.lignes)


def test_un_dossier_absent_n_avance_pas_la_date(serveur, tmp_path):
    configuration = configuration_minimale(tmp_path, serveur(boite_standard()).port, dossiers=["INBOX", "Absent"])
    resultats, dates, en_echec = traiter(configuration, deposer=True)
    assert en_echec == {"imap-test"} and dates == {} and resultats[0].deposees == 3


def test_une_piece_au_dela_de_la_taille_max_n_avance_pas_la_date(serveur, tmp_path):
    gros = Boite([message(1, datetime(2026, 10, 20, 9, 0), [piece("gros.pdf", b"x" * 2_000_000)])])
    configuration = configuration_minimale(tmp_path, serveur(gros).port)
    resultats, dates, en_echec = traiter(configuration, deposer=True)
    assert en_echec == {"imap-test"} and "taille_max_piece_mo" in resultats[0].erreurs[-1]


def test_la_date_du_dernier_scan_filtre_les_messages(serveur, tmp_path):
    configuration = configuration_minimale(tmp_path, serveur(boite_standard()).port)
    resultats, _, _ = traiter(configuration, deposer=False, suivi={"imap-test": datetime(2026, 10, 20, 12, 0)})
    assert [p.uid for p in resultats[0].pieces] == ["1", "2", "2"]
    resultats, _, _ = traiter(configuration, deposer=False, suivi={"imap-test": datetime(2026, 10, 21, 11, 0)})
    assert resultats[0].pieces == []


def test_cles_absentes_de_la_configuration(tmp_path):
    configuration = configuration_minimale(tmp_path, 1)
    assert sources_imap.cles_absentes(configuration) == []
    del configuration["imap"]["taille_max_piece_mo"]
    del configuration["sources_imap"][0]["mot_de_passe_env"]
    configuration["sources_imap"][0]["vide_poches_destination"] = "a/b"
    assert sources_imap.cles_absentes(configuration) == ["imap.taille_max_piece_mo", "sources_imap[imap-test].mot_de_passe_env",
                                                         "sources_imap[imap-test].vide_poches_destination (un nom, sans séparateur)"]
    assert sources_imap.cles_absentes({}) == []


@pytest.fixture
def boite_pipeline(banc, serveur, monkeypatch):
    racine, chemin_config = banc
    boite = Boite([message(1, datetime.now() - timedelta(days=1), [piece("un.pdf", TEXTES[2]["texte"].encode()),
                                                                     piece("deux.pdf", (TEXTES[0]["texte"] + " courriel").encode())])])
    ouvert = serveur(boite)
    configuration = json.loads(chemin_config.read_text())
    configuration.update(imap={"delai_secondes": 5, "taille_max_piece_mo": 5}, sources_imap=[{
        "id": "imap-test", "serveur": "127.0.0.1", "port": ouvert.port, "ssl": True, "authentification": "login",
        "utilisateur": UTILISATEUR, "mot_de_passe_env": "DIBAB_IMAP_TEST", "dossiers": ["INBOX"],
        "vide_poches_destination": "vide-poches-imap"}])
    chemin_config.write_text(json.dumps(configuration))
    monkeypatch.setenv("DIBAB_IMAP_TEST", MOT_DE_PASSE)
    monkeypatch.setattr(scanner_imap, "ouvrir_connexion", lambda serveur, port, delai: imaplib.IMAP4("127.0.0.1", port))
    return racine, boite


def test_execute_depose_classe_et_le_second_passage_ne_fait_rien(boite_pipeline, monkeypatch):
    racine, boite = boite_pipeline
    avant = boite.instantane()
    assert lancer(monkeypatch, "--execute") == 0
    journal = racine / "coffre-a" / "logs" / "journal.jsonl"
    actions = [a for a in journal_actions.lire_lignes(journal) if a["evenement"] == "action" and "vide-poches-imap" in a["origine"]]
    assert len(actions) == 2
    assert list((racine / "coffre-a" / "vide-poches-imap").iterdir()) == []
    assert "imap-test" in json.loads((racine / "coffre-a" / "logs" / "dernier_scan.json").read_text())
    rapport = next((racine / "coffre-a" / "logs" / "sessions").glob("rapport_*.json"))
    assert json.loads(rapport.read_text())["deposes_imap"] == 2
    assert boite.instantane() == avant and boite.verbes_interdits() == []
    assert lancer(monkeypatch, "--execute") == 0
    apres = [a for a in journal_actions.lire_lignes(journal) if a["evenement"] == "action" and "vide-poches-imap" in a["origine"]]
    assert apres == actions


def test_le_dry_run_du_pipeline_liste_les_pieces_sans_rien_deposer(boite_pipeline, monkeypatch, capsys):
    racine, boite = boite_pipeline
    assert lancer(monkeypatch, "--dry-run") == 0
    sortie = capsys.readouterr().out
    assert "Source IMAP : imap-test (rien n'est téléchargé en dry-run)" in sortie and "un.pdf" in sortie
    assert not (racine / "coffre-a" / "vide-poches-imap").exists() and boite.parties_demandees == []


def test_le_vide_poches_aussi_declare_en_source_locale_n_est_lu_qu_une_fois(boite_pipeline, monkeypatch):
    racine, _ = boite_pipeline
    chemin = dibab.CHEMIN_CONFIG
    configuration = json.loads(chemin.read_text())
    configuration["sources_locales"].append({"id": "vide-poches-local", "chemin": str(racine / "coffre-a" / "vide-poches-imap")})
    chemin.write_text(json.dumps(configuration))
    assert lancer(monkeypatch, "--execute") == 0
    journal = racine / "coffre-a" / "logs" / "journal.jsonl"
    actions = [a for a in journal_actions.lire_lignes(journal) if a["evenement"] == "action" and "vide-poches-imap" in a["origine"]]
    assert len(actions) == 2 and {a["action"] for a in actions} <= {"classe", "a_verifier", "doublon"}


def test_config_sans_bloc_imap_arrete_avec_le_code_1(boite_pipeline, monkeypatch):
    chemin = dibab.CHEMIN_CONFIG
    configuration = json.loads(chemin.read_text())
    del configuration["imap"]
    chemin.write_text(json.dumps(configuration))
    with pytest.raises(SystemExit) as sortie:
        lancer(monkeypatch, "--dry-run")
    assert sortie.value.code == 1
