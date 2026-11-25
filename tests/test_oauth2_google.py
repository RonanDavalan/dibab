"""OAuth2 Google par un faux serveur d'autorisation et un faux IMAP : connexion, renouvellement, révocation, consentement, absence de fuite."""

import base64
import hashlib
import http.server
import imaplib
import json
import os
import threading
import urllib.parse
import urllib.request
from datetime import datetime, timedelta

import pytest

import dibab
from modules import oauth2_google, scanner_imap, sources_imap
from tests.faux_imap import UTILISATEUR, Boite, Serveur, message, piece
from tests.test_classement_execute import TEXTES, banc, lancer  # noqa: F401
from tests.test_scanner_imap import JournalMemoire, MAINTENANT, boite_standard, fuseau_utc  # noqa: F401

ACCES_VALIDE = "acces-factice-AAAA1111"
ACCES_RENOUVELE = "acces-renouvele-BBBB2222"
RENOUVELLEMENT = "renouvellement-factice-CCCC3333"
SECRET_CLIENT = "secret-client-factice-DDDD4444"
CODE = "code-factice-EEEE5555"
JETONS_A_CACHER = (ACCES_VALIDE, ACCES_RENOUVELE, RENOUVELLEMENT, SECRET_CLIENT, CODE)


class FauxServeurAutorisation(http.server.HTTPServer):
    """Imite le point d'extrémité de jeton : renouvellement, échange du code, révocation."""

    def __init__(self):
        super().__init__(("127.0.0.1", 0), self.Gestionnaire)
        self.requetes = []
        self.reponse_renouvellement = (200, {"access_token": ACCES_RENOUVELE, "expires_in": 3599, "token_type": "Bearer"})
        self.reponse_code = (200, {"access_token": ACCES_VALIDE, "expires_in": 3599, "refresh_token": RENOUVELLEMENT, "token_type": "Bearer"})
        self.defi_attendu = None

    @property
    def url(self):
        return f"http://127.0.0.1:{self.server_address[1]}/token"

    class Gestionnaire(http.server.BaseHTTPRequestHandler):
        def do_POST(self):
            champs = {c: v[0] for c, v in urllib.parse.parse_qs(self.rfile.read(int(self.headers["Content-Length"])).decode()).items()}
            self.server.requetes.append(champs)
            if champs.get("grant_type") == "refresh_token":
                statut, corps = self.server.reponse_renouvellement if champs.get("refresh_token") == RENOUVELLEMENT \
                    else (400, {"error": "invalid_grant"})
            else:
                verificateur = base64.urlsafe_b64encode(hashlib.sha256(champs.get("code_verifier", "").encode()).digest()).rstrip(b"=").decode()
                statut, corps = self.server.reponse_code if champs.get("code") == CODE and verificateur == self.server.defi_attendu \
                    else (400, {"error": "invalid_grant"})
            donnees = json.dumps(corps).encode()
            self.send_response(statut)
            self.send_header("Content-Length", str(len(donnees)))
            self.end_headers()
            self.wfile.write(donnees)

        def log_message(self, *arguments):
            pass


@pytest.fixture
def autorisation():
    ouvert = FauxServeurAutorisation()
    threading.Thread(target=ouvert.serve_forever, daemon=True).start()
    yield ouvert
    ouvert.shutdown()
    ouvert.server_close()


@pytest.fixture
def imap():
    ouverts = []

    def demarrer(boite, **options):
        ouverts.append(Serveur(boite, **options).demarrer())
        return ouverts[-1]

    yield demarrer
    for ouvert in ouverts:
        ouvert.arreter()


def ecrire_protege(chemin, donnees, mode=0o600):
    chemin.parent.mkdir(parents=True, exist_ok=True)
    chemin.write_text(json.dumps(donnees))
    chemin.chmod(mode)
    return chemin


def installer_secrets(dossier, expiration, acces=ACCES_VALIDE, refresh=RENOUVELLEMENT):
    client = ecrire_protege(dossier / "client.json", {"installed": {"client_id": "client-factice.apps.exemple", "client_secret": SECRET_CLIENT}})
    jeton = ecrire_protege(dossier / "jeton.json", {"refresh_token": refresh, "access_token": acces, "expiration": expiration})
    return client, jeton


def parametres_oauth2(autorisation, **ecarts):
    return {"url_autorisation": "http://127.0.0.1:1/auth", "url_jeton": autorisation.url, "portee": "https://mail.google.com/",
            "marge_renouvellement_secondes": 300, "delai_secondes": 5, "delai_consentement_secondes": 5,
            "chemins_interdits": [], **ecarts}


def configuration_oauth2(tmp_path, port, autorisation, client, jeton):
    return {
        "destinations": {"personnel": {"racine": str(tmp_path / "coffre")}},
        "suivi": {"fichier_date": str(tmp_path / "coffre" / "logs" / "dernier_scan.json"),
                  "journal": str(tmp_path / "coffre" / "logs" / "journal.jsonl"), "securite_jours": 1, "premier_scan_jours": 30},
        "nommage": {"suffixe_collision": "_{n}"}, "extensions_cibles": [".pdf", ".jpg"],
        "imap": {"delai_secondes": 5, "taille_max_piece_mo": 1},
        "oauth2": parametres_oauth2(autorisation),
        "sources_imap": [{"id": "imap-google", "serveur": "127.0.0.1", "port": port, "ssl": True, "authentification": "oauth2",
                          "utilisateur": UTILISATEUR, "client_fichier": str(client), "token_fichier": str(jeton),
                          "dossiers": ["INBOX"], "vide_poches_destination": "vide-poches-google"}],
    }


def traiter(configuration, deposer=True, journal=None):
    return sources_imap.traiter(configuration, {}, journal or JournalMemoire(), MAINTENANT, deposer, environ={},
                                ouvrir=lambda serveur, port, delai: imaplib.IMAP4("127.0.0.1", port))


def plus_une_heure():
    return datetime.now().timestamp() + 3600


def test_connexion_par_jeton_valide_liste_les_pieces_sans_toucher_la_boite_ni_google(tmp_path, imap, autorisation):
    boite = boite_standard()
    avant = boite.instantane()
    client, jeton = installer_secrets(tmp_path / "secrets", plus_une_heure())
    octets_avant = jeton.read_bytes()
    resultats, dates, en_echec = traiter(configuration_oauth2(tmp_path, imap(boite, jetons_valides=[ACCES_VALIDE]).port, autorisation, client, jeton),
                                         deposer=False)
    assert [p.nom for p in resultats[0].pieces] == ["facture.pdf", "photo.JPG", "releve.pdf"]
    assert set(dates) == {"imap-google"} and en_echec == set()
    assert autorisation.requetes == [] and jeton.read_bytes() == octets_avant
    assert boite.instantane() == avant and boite.verbes_interdits() == [] and boite.parties_demandees == []


def test_execute_depose_les_pieces_et_la_boite_reste_inchangee(tmp_path, imap, autorisation):
    boite = boite_standard()
    avant = boite.instantane()
    client, jeton = installer_secrets(tmp_path / "secrets", plus_une_heure())
    resultats, dates, en_echec = traiter(configuration_oauth2(tmp_path, imap(boite, jetons_valides=[ACCES_VALIDE]).port, autorisation, client, jeton))
    assert sorted(p.name for p in (tmp_path / "coffre" / "vide-poches-google").iterdir()) == ["facture.pdf", "photo.JPG", "releve.pdf"]
    assert resultats[0].deposees == 3 and not en_echec
    assert boite.instantane() == avant and boite.verbes_interdits() == []
    assert all(utilise for _, utilise in boite.parties_demandees)


def test_jeton_expire_renouvele_avant_la_connexion(tmp_path, imap, autorisation):
    boite = boite_standard()
    client, jeton = installer_secrets(tmp_path / "secrets", datetime.now().timestamp() - 10)
    resultats, dates, en_echec = traiter(configuration_oauth2(tmp_path, imap(boite, jetons_valides=[ACCES_RENOUVELE]).port, autorisation,
                                                              client, jeton), deposer=False)
    assert len(resultats[0].pieces) == 3 and not en_echec
    assert len(autorisation.requetes) == 1 and autorisation.requetes[0]["grant_type"] == "refresh_token"
    assert autorisation.requetes[0]["client_secret"] == SECRET_CLIENT
    ecrit = json.loads(jeton.read_text())
    assert ecrit["access_token"] == ACCES_RENOUVELE and ecrit["refresh_token"] == RENOUVELLEMENT
    assert ecrit["expiration"] > datetime.now().timestamp() + 3000 and oct(jeton.stat().st_mode & 0o777) == "0o600"


def test_jeton_bientot_expire_est_renouvele_dans_la_marge(tmp_path, autorisation):
    client, jeton = installer_secrets(tmp_path / "secrets", datetime.now().timestamp() + 100)
    assert oauth2_google.jeton_d_acces(client, jeton, parametres_oauth2(autorisation)) == ACCES_RENOUVELE


def test_un_nouveau_jeton_de_renouvellement_remplace_l_ancien(tmp_path, autorisation):
    autorisation.reponse_renouvellement = (200, {"access_token": ACCES_RENOUVELE, "expires_in": 3599, "refresh_token": "renouvellement-tourne"})
    client, jeton = installer_secrets(tmp_path / "secrets", 0)
    oauth2_google.jeton_d_acces(client, jeton, parametres_oauth2(autorisation))
    assert json.loads(jeton.read_text())["refresh_token"] == "renouvellement-tourne"


def test_jeton_revoque_echoue_explicitement_sans_rien_ecrire(tmp_path, imap, autorisation):
    boite = boite_standard()
    client, jeton = installer_secrets(tmp_path / "secrets", 0, refresh="renouvellement-revoque")
    octets_avant = jeton.read_bytes()
    resultats, dates, en_echec = traiter(configuration_oauth2(tmp_path, imap(boite, jetons_valides=[ACCES_RENOUVELE]).port, autorisation,
                                                              client, jeton))
    assert en_echec == {"imap-google"} and dates == {} and not resultats[0].ignoree
    assert resultats[0].erreurs == ["autorisation révoquée ou expirée : refaire --autoriser-google"]
    assert jeton.read_bytes() == octets_avant and boite.commandes == []
    assert not (tmp_path / "coffre" / "vide-poches-google").exists()


def test_reponse_invalide_du_serveur_d_autorisation_ne_modifie_pas_le_jeton(tmp_path, autorisation):
    autorisation.reponse_renouvellement = (200, {"expires_in": 3599})
    client, jeton = installer_secrets(tmp_path / "secrets", 0)
    octets_avant = jeton.read_bytes()
    with pytest.raises(oauth2_google.ErreurOAuth2, match="invalide"):
        oauth2_google.jeton_d_acces(client, jeton, parametres_oauth2(autorisation))
    assert jeton.read_bytes() == octets_avant


def test_refus_du_serveur_d_autorisation_ne_cite_que_le_statut_et_le_code(tmp_path, autorisation):
    autorisation.reponse_renouvellement = (401, {"error": "invalid_client", "error_description": ACCES_VALIDE})
    client, jeton = installer_secrets(tmp_path / "secrets", 0)
    with pytest.raises(oauth2_google.ErreurOAuth2) as erreur:
        oauth2_google.jeton_d_acces(client, jeton, parametres_oauth2(autorisation))
    assert str(erreur.value) == "serveur d'autorisation : refus (HTTP 401, erreur invalid_client)"


def test_serveur_d_autorisation_injoignable_est_une_erreur_sans_adresse(tmp_path, autorisation):
    client, jeton = installer_secrets(tmp_path / "secrets", 0)
    parametres = parametres_oauth2(autorisation, url_jeton="http://127.0.0.1:1/token")
    with pytest.raises(oauth2_google.ErreurOAuth2) as erreur:
        oauth2_google.jeton_d_acces(client, jeton, parametres)
    assert "127.0.0.1" not in str(erreur.value) and "injoignable" in str(erreur.value)


def test_le_serveur_imap_refuse_le_jeton_une_seule_tentative_et_repond_au_defi_par_une_ligne_vide(tmp_path, imap, autorisation):
    boite = boite_standard()
    client, jeton = installer_secrets(tmp_path / "secrets", plus_une_heure())
    resultats, dates, en_echec = traiter(configuration_oauth2(tmp_path, imap(boite, jetons_valides=["autre-jeton"]).port, autorisation,
                                                              client, jeton))
    assert en_echec == {"imap-google"} and dates == {}
    assert resultats[0].erreurs == ["authentification refusée par le serveur"]
    assert [c for c in boite.commandes if c.upper().startswith("AUTHENTICATE")] == ["AUTHENTICATE XOAUTH2"]
    assert boite.reponses_au_defi == [b""] and autorisation.requetes == []


def test_chaine_xoauth2_avec_caractere_de_controle_refusee_sans_connexion():
    class Connexion:
        def authenticate(self, *_):
            raise AssertionError("aucune commande ne doit partir")

    with pytest.raises(scanner_imap.AuthentificationRefusee):
        scanner_imap.authentifier_xoauth2(Connexion(), UTILISATEUR, "jeton\x01auth=Bearer autre")


def test_fichier_de_jeton_absent_ignore_la_source_sans_connexion(tmp_path, imap, autorisation):
    boite = boite_standard()
    client, jeton = installer_secrets(tmp_path / "secrets", 0)
    jeton.unlink()
    resultats, dates, en_echec = traiter(configuration_oauth2(tmp_path, imap(boite).port, autorisation, client, jeton))
    assert resultats[0].ignoree and "--autoriser-google imap-google" in resultats[0].erreurs[0]
    assert boite.commandes == [] and dates == {} and en_echec == set() and autorisation.requetes == []


def test_un_jeton_lisible_par_d_autres_est_refuse(tmp_path, imap, autorisation):
    boite = boite_standard()
    client, jeton = installer_secrets(tmp_path / "secrets", plus_une_heure())
    jeton.chmod(0o644)
    resultats, _, en_echec = traiter(configuration_oauth2(tmp_path, imap(boite, jetons_valides=[ACCES_VALIDE]).port, autorisation, client, jeton))
    assert en_echec == {"imap-google"} and "chmod 600" in resultats[0].erreurs[0] and boite.commandes == []


def test_un_fichier_client_lisible_par_d_autres_est_refuse(tmp_path, autorisation):
    client, jeton = installer_secrets(tmp_path / "secrets", 0)
    client.chmod(0o640)
    with pytest.raises(oauth2_google.ErreurOAuth2, match="chmod 600"):
        oauth2_google.jeton_d_acces(client, jeton, parametres_oauth2(autorisation))


def test_un_jeton_dans_un_depot_ou_un_chemin_interdit_est_refuse(tmp_path, autorisation):
    client, jeton = installer_secrets(tmp_path / "depot" / "secrets", plus_une_heure())
    (tmp_path / "depot" / ".git").mkdir()
    with pytest.raises(oauth2_google.ErreurOAuth2, match="dépôt git"):
        oauth2_google.jeton_d_acces(client, jeton, parametres_oauth2(autorisation))
    client, jeton = installer_secrets(tmp_path / "gestion" / "secrets", plus_une_heure())
    with pytest.raises(oauth2_google.ErreurOAuth2, match="chemin interdit"):
        oauth2_google.jeton_d_acces(client, jeton, parametres_oauth2(autorisation, chemins_interdits=[str(tmp_path / "gestion")]))


def test_un_fichier_de_jeton_sans_refresh_token_ou_mal_forme_est_refuse(tmp_path, autorisation):
    client, jeton = installer_secrets(tmp_path / "secrets", plus_une_heure())
    ecrire_protege(jeton, {"access_token": ACCES_VALIDE})
    with pytest.raises(oauth2_google.ErreurOAuth2, match="sans refresh_token"):
        oauth2_google.jeton_d_acces(client, jeton, parametres_oauth2(autorisation))
    jeton.write_text("pas du json")
    with pytest.raises(oauth2_google.ErreurOAuth2, match="illisible"):
        oauth2_google.jeton_d_acces(client, jeton, parametres_oauth2(autorisation))


def test_un_point_d_extremite_hors_boucle_locale_exige_https(tmp_path, autorisation):
    client, jeton = installer_secrets(tmp_path / "secrets", 0)
    with pytest.raises(oauth2_google.ErreurOAuth2, match="https exigé"):
        oauth2_google.jeton_d_acces(client, jeton, parametres_oauth2(autorisation, url_jeton="http://exemple.fr/token"))
    oauth2_google.verifier_point_d_extremite("https://oauth2.googleapis.com/token")


def test_le_jeton_est_ecrit_en_600_dans_un_dossier_700(tmp_path):
    chemin = tmp_path / "neuf" / "jeton.json"
    oauth2_google.ecrire_jeton(chemin, {"refresh_token": "r"})
    assert oct(chemin.stat().st_mode & 0o777) == "0o600" and oct(chemin.parent.stat().st_mode & 0o777) == "0o700"
    assert os.listdir(chemin.parent) == ["jeton.json"]


def test_l_ecriture_du_jeton_qui_echoue_ne_laisse_ni_provisoire_ni_perte(tmp_path):
    chemin = tmp_path / "jeton.json"
    oauth2_google.ecrire_jeton(chemin, {"refresh_token": "ancien"})
    with pytest.raises(TypeError):
        oauth2_google.ecrire_jeton(chemin, {"refresh_token": object()})
    assert json.loads(chemin.read_text()) == {"refresh_token": "ancien"} and os.listdir(tmp_path) == ["jeton.json"]


def consentir(autorisation, defi_recu, etat_force=None, parametres_reponse=None):
    """Navigateur factice : lit l'adresse affichée et rejoint la redirection de la boucle locale."""
    def afficher(adresse):
        requete = {c: v[0] for c, v in urllib.parse.parse_qs(urllib.parse.urlparse(adresse).query).items()}
        assert requete["code_challenge_method"] == "S256" and requete["response_type"] == "code"
        assert requete["scope"] == "https://mail.google.com/" and requete["login_hint"] == UTILISATEUR
        assert requete["redirect_uri"].startswith("http://127.0.0.1:") and SECRET_CLIENT not in adresse
        defi_recu.append(requete["code_challenge"])
        autorisation.defi_attendu = requete["code_challenge"]
        reponse = parametres_reponse if parametres_reponse is not None else {"code": CODE}
        lien = requete["redirect_uri"] + "/?" + urllib.parse.urlencode({**reponse, "state": etat_force or requete["state"]})
        threading.Thread(target=lambda: urllib.request.urlopen(lien, timeout=5).read(), daemon=True).start()
    return afficher


def test_le_consentement_ecrit_le_jeton_apres_verification_du_pkce(tmp_path, autorisation):
    client, _ = installer_secrets(tmp_path / "secrets", 0)
    jeton = tmp_path / "secrets" / "nouveau.json"
    oauth2_google.autoriser(client, jeton, UTILISATEUR, parametres_oauth2(autorisation), consentir(autorisation, []))
    ecrit = json.loads(jeton.read_text())
    assert ecrit["refresh_token"] == RENOUVELLEMENT and ecrit["access_token"] == ACCES_VALIDE
    assert oct(jeton.stat().st_mode & 0o777) == "0o600"
    echange = autorisation.requetes[0]
    assert echange["grant_type"] == "authorization_code" and echange["code"] == CODE and echange["client_secret"] == SECRET_CLIENT
    assert echange["redirect_uri"].startswith("http://127.0.0.1:") and 43 <= len(echange["code_verifier"]) <= 128


@pytest.mark.parametrize("cas, motif", [
    ({"etat_force": "autre-state"}, "state différent"),
    ({"etat_force": "état-é"}, "state différent"),
    ({"parametres_reponse": {"error": "access_denied"}}, "consentement refusé"),
    ({"parametres_reponse": {}}, "sans code"),
])
def test_un_consentement_refuse_ou_detourne_n_ecrit_rien(tmp_path, autorisation, cas, motif):
    client, _ = installer_secrets(tmp_path / "secrets", 0)
    jeton = tmp_path / "secrets" / "nouveau.json"
    with pytest.raises(oauth2_google.ErreurOAuth2, match=motif):
        oauth2_google.autoriser(client, jeton, UTILISATEUR, parametres_oauth2(autorisation), consentir(autorisation, [], **cas))
    assert not jeton.exists() and autorisation.requetes == []


def test_un_consentement_sans_jeton_de_renouvellement_n_ecrit_rien(tmp_path, autorisation):
    autorisation.reponse_code = (200, {"access_token": ACCES_VALIDE, "expires_in": 3599})
    client, _ = installer_secrets(tmp_path / "secrets", 0)
    jeton = tmp_path / "secrets" / "nouveau.json"
    with pytest.raises(oauth2_google.ErreurOAuth2, match="jeton de renouvellement"):
        oauth2_google.autoriser(client, jeton, UTILISATEUR, parametres_oauth2(autorisation), consentir(autorisation, []))
    assert not jeton.exists()


def test_un_consentement_sans_reponse_expire_sans_rien_ecrire(tmp_path, autorisation):
    client, _ = installer_secrets(tmp_path / "secrets", 0)
    jeton = tmp_path / "secrets" / "nouveau.json"
    with pytest.raises(oauth2_google.ErreurOAuth2, match="aucune réponse"):
        oauth2_google.autoriser(client, jeton, UTILISATEUR, parametres_oauth2(autorisation, delai_consentement_secondes=1), lambda _: None)
    assert not jeton.exists()


def test_cles_absentes_exige_le_bloc_oauth2_et_les_fichiers_de_la_source(tmp_path, autorisation):
    configuration = configuration_oauth2(tmp_path, 1, autorisation, tmp_path / "c", tmp_path / "t")
    assert sources_imap.cles_absentes(configuration) == []
    del configuration["oauth2"]["portee"]
    del configuration["sources_imap"][0]["client_fichier"]
    assert sources_imap.cles_absentes(configuration) == ["oauth2.portee", "sources_imap[imap-google].client_fichier"]


@pytest.fixture
def pipeline_google(banc, imap, autorisation, monkeypatch):
    racine, chemin_config = banc
    boite = Boite([message(1, datetime.now() - timedelta(days=1), [piece("un.pdf", TEXTES[2]["texte"].encode()),
                                                                     piece("deux.pdf", (TEXTES[0]["texte"] + " courriel").encode())])])
    ouvert = imap(boite, jetons_valides=[ACCES_RENOUVELE])
    client, jeton = installer_secrets(racine / "secrets", 0)
    configuration = json.loads(chemin_config.read_text())
    configuration.update(imap={"delai_secondes": 5, "taille_max_piece_mo": 5}, oauth2=parametres_oauth2(autorisation), sources_imap=[{
        "id": "imap-google", "serveur": "127.0.0.1", "port": ouvert.port, "ssl": True, "authentification": "oauth2",
        "utilisateur": UTILISATEUR, "client_fichier": str(client), "token_fichier": str(jeton), "dossiers": ["INBOX"],
        "vide_poches_destination": "vide-poches-google"}])
    chemin_config.write_text(json.dumps(configuration))
    monkeypatch.setattr(scanner_imap, "ouvrir_connexion", lambda serveur, port, delai: imaplib.IMAP4("127.0.0.1", port))
    return racine, boite, jeton


def test_le_jeton_n_apparait_ni_au_journal_ni_au_rapport_ni_a_la_sortie(pipeline_google, autorisation, monkeypatch, capsys):
    racine, boite, jeton = pipeline_google
    avant = boite.instantane()
    assert lancer(monkeypatch, "--dry-run") == 0
    assert lancer(monkeypatch, "--execute") == 0
    assert lancer(monkeypatch, "--execute") == 0
    sortie = capsys.readouterr()
    assert json.loads(jeton.read_text())["access_token"] == ACCES_RENOUVELE
    for secret in JETONS_A_CACHER:
        assert secret not in sortie.out and secret not in sortie.err
        for fichier in racine.rglob("*"):
            if fichier.is_file() and racine / "secrets" not in fichier.parents:
                assert secret.encode() not in fichier.read_bytes(), (secret, fichier.name)
    assert list((racine / "coffre-a" / "logs" / "sessions").glob("rapport_*.json")) and len(autorisation.requetes) == 1
    assert boite.instantane() == avant and boite.verbes_interdits() == []


def test_le_pipeline_oauth2_depose_classe_et_le_second_passage_ne_fait_rien(pipeline_google, monkeypatch):
    racine, boite, _ = pipeline_google
    journal = racine / "coffre-a" / "logs" / "journal.jsonl"
    assert lancer(monkeypatch, "--execute") == 0
    def actions():
        return [ligne for ligne in journal.read_text().splitlines() if '"evenement": "action"' in ligne]

    assert lancer(monkeypatch, "--execute") == 0
    deposees = [ligne for ligne in actions() if "vide-poches-google" in ligne]
    assert len(deposees) == 2
    tout = actions()
    assert lancer(monkeypatch, "--execute") == 0
    assert actions() == tout


def test_le_pipeline_avec_autorisation_revoquee_rend_le_code_1_et_n_avance_pas_la_date(pipeline_google, monkeypatch, capsys):
    racine, boite, jeton = pipeline_google
    ecrire_protege(jeton, {"refresh_token": "revoque", "access_token": "x", "expiration": 0})
    octets = jeton.read_bytes()
    assert lancer(monkeypatch, "--execute") == 1
    assert "autorisation révoquée ou expirée" in capsys.readouterr().out
    assert jeton.read_bytes() == octets and boite.commandes == []
    assert "imap-google" not in (racine / "coffre-a" / "logs" / "dernier_scan.json").read_text()


def test_la_commande_autoriser_google_appelle_le_consentement_de_la_source(pipeline_google, monkeypatch, capsys):
    appels = []
    monkeypatch.setattr(dibab.mod_oauth2_google, "autoriser", lambda *arguments: appels.append(arguments))
    assert lancer(monkeypatch, "--autoriser-google", "imap-google") == 0
    client, jeton, utilisateur, parametres, _ = appels[0]
    assert (client.endswith("client.json"), jeton.endswith("jeton.json"), utilisateur) == (True, True, UTILISATEUR)
    assert parametres["portee"] == "https://mail.google.com/" and "Jeton écrit" in capsys.readouterr().out


def test_la_commande_autoriser_google_refuse_une_source_inconnue_ou_en_login(pipeline_google, monkeypatch, capsys):
    assert lancer(monkeypatch, "--autoriser-google", "inconnue") == 1
    assert "aucune source IMAP" in capsys.readouterr().err


def test_la_commande_autoriser_google_signale_l_echec_sans_rien_ecrire(pipeline_google, monkeypatch, capsys):
    def echec(*_):
        raise oauth2_google.ErreurOAuth2("consentement refusé")

    monkeypatch.setattr(dibab.mod_oauth2_google, "autoriser", echec)
    assert lancer(monkeypatch, "--autoriser-google", "imap-google") == 1
    assert "consentement refusé" in capsys.readouterr().err
