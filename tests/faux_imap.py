"""Faux serveur IMAP local pour les tests : une boîte factice, ses drapeaux, et la liste des commandes reçues.

Le serveur imite ce qui compte pour la lecture seule : `EXAMINE` ne change rien, `SELECT` expose la boîte
en écriture, et un `FETCH BODY[...]` sans `PEEK` pose `\\Seen`. Les commandes d'écriture sont
enregistrées pour que les tests prouvent qu'aucune n'est partie.
"""

import base64
import re
import socketserver
import threading
from datetime import datetime

MOT_DE_PASSE = "mot-de-passe-factice"
UTILISATEUR = "foyer"
COMMANDES_ADMISES = {"CAPABILITY", "LOGIN", "AUTHENTICATE", "EXAMINE", "UID", "LOGOUT", "NOOP"}


def citer(valeur):
    return '"' + valeur.replace("\\", "\\\\").replace('"', '\\"') + '"'


def piece(nom, donnees, disposition="ATTACHMENT", encodage="base64", content_id=None, type_="APPLICATION", sous_type="PDF",
          nom_brut=None):
    """Une partie de message ; `nom_brut` est la valeur du paramètre telle que le serveur la rend (déjà citée)."""
    return {"nom": nom, "donnees": donnees, "disposition": disposition, "encodage": encodage, "content_id": content_id,
            "type": type_, "sous_type": sous_type, "nom_brut": nom_brut}


def message(uid, date, parties, flags=()):
    return {"uid": uid, "date": date, "parties": parties, "flags": set(flags)}


def _encoder(donnees, encodage):
    if encodage == "base64":
        return base64.encodebytes(donnees).replace(b"\n", b"\r\n")
    return donnees


def _structure_partie(p):
    nom = p["nom_brut"] if p["nom_brut"] is not None else citer(p["nom"]) if p["nom"] else None
    params = f'("NAME" {nom})' if nom else "NIL"
    disposition = f'("{p["disposition"]}" ("FILENAME" {nom}))' if p["disposition"] and nom else "NIL"
    cid = citer(p["content_id"]) if p["content_id"] else "NIL"
    taille = len(_encoder(p["donnees"], p["encodage"]))
    return f'("{p["type"]}" "{p["sous_type"]}" {params} {cid} NIL "{p["encodage"]}" {taille} NIL {disposition} NIL NIL)'


def structure(msg):
    texte = '("TEXT" "PLAIN" ("CHARSET" "utf-8") NIL NIL "7bit" 10 1 NIL NIL NIL NIL)'
    return "(" + texte + "".join(_structure_partie(p) for p in msg["parties"]) + ' "MIXED" ("BOUNDARY" "b") NIL NIL NIL)'


class Boite:
    def __init__(self, messages, uidvalidity=1234):
        self.messages = messages
        self.uidvalidity = uidvalidity
        self.commandes = []
        self.parties_demandees = []

    def instantane(self):
        return [(m["uid"], frozenset(m["flags"])) for m in self.messages]

    def verbes_interdits(self):
        return [c for c in self.commandes if c.split()[0].upper() not in COMMANDES_ADMISES
                or (c.split()[0].upper() == "UID" and c.split()[1].upper() not in ("SEARCH", "FETCH"))]


class Gestionnaire(socketserver.StreamRequestHandler):
    def ecrire(self, texte):
        self.wfile.write(texte if isinstance(texte, bytes) else texte.encode("utf-8"))

    def handle(self):
        boite = self.server.boite
        self.ecrire(b"* OK faux serveur pret\r\n")
        authentifie, lecture_seule = False, True
        for brut in self.rfile:
            ligne = brut.decode("utf-8", "replace").rstrip("\r\n")
            etiquette, _, reste = ligne.partition(" ")
            verbe = reste.split(" ")[0].upper()
            boite.commandes.append(re.sub(r'(LOGIN \S+ ).*', r'\1***', reste, flags=re.I))
            if verbe == "CAPABILITY":
                self.ecrire(f"* CAPABILITY IMAP4rev1\r\n{etiquette} OK fait\r\n")
            elif verbe == "LOGIN":
                mots = re.findall(r'"((?:[^"\\]|\\.)*)"|(\S+)', reste.split(" ", 1)[1])
                identifiants = [re.sub(r'\\(.)', r'\1', a) if a else b for a, b in mots]
                if identifiants == list(self.server.identifiants):
                    authentifie = True
                    self.ecrire(f"{etiquette} OK connecte\r\n")
                else:
                    self.ecrire(f"{etiquette} NO [AUTHENTICATIONFAILED] refuse\r\n")
            elif verbe == "AUTHENTICATE":
                self.ecrire("+ \r\n")
                reponse = base64.b64decode(self.rfile.readline().strip()).decode("utf-8").split("\0")
                if reponse[1:] == list(self.server.identifiants):
                    authentifie = True
                    self.ecrire(f"{etiquette} OK connecte\r\n")
                else:
                    self.ecrire(f"{etiquette} NO [AUTHENTICATIONFAILED] refuse\r\n")
            elif verbe in ("EXAMINE", "SELECT") and authentifie:
                lecture_seule = verbe == "EXAMINE"
                nom = reste.split(" ", 1)[1].strip('"')
                if nom not in self.server.dossiers:
                    self.ecrire(f"{etiquette} NO dossier inconnu\r\n")
                    continue
                marque = "[READ-ONLY]" if lecture_seule else "[READ-WRITE]"
                self.ecrire(f"* {len(boite.messages)} EXISTS\r\n* OK [UIDVALIDITY {boite.uidvalidity}] ok\r\n{etiquette} OK {marque} fait\r\n")
            elif verbe == "UID" and authentifie:
                self.uid(etiquette, reste, boite, lecture_seule)
            elif verbe == "LOGOUT":
                self.ecrire(f"* BYE au revoir\r\n{etiquette} OK fini\r\n")
                return
            else:
                self.ecrire(f"{etiquette} BAD commande non admise par le faux serveur\r\n")

    def uid(self, etiquette, reste, boite, lecture_seule):
        sous = reste.split(" ")[1].upper()
        if sous == "SEARCH":
            m = re.search(r"SINCE (\d+)-(\w+)-(\d+)", reste)
            jour = datetime.strptime(" ".join(m.groups()), "%d %b %Y") if m else datetime.min
            trouves = [str(msg["uid"]) for msg in boite.messages if msg["date"].replace(hour=0, minute=0, second=0) >= jour]
            self.ecrire(f"* SEARCH {' '.join(trouves)}\r\n{etiquette} OK fait\r\n".replace("* SEARCH \r\n", "* SEARCH\r\n"))
        elif sous == "FETCH":
            _, _, liste, elements = reste.split(" ", 3)
            demandes = set()
            for uid_demande in liste.split(","):
                demandes.add(int(uid_demande))
            for msg in boite.messages:
                if msg["uid"] in demandes:
                    self.repondre_fetch(msg, elements, boite, lecture_seule)
            self.ecrire(f"{etiquette} OK fait\r\n")
        else:
            self.ecrire(f"{etiquette} BAD\r\n")

    def repondre_fetch(self, msg, elements, boite, lecture_seule):
        sequence = boite.messages.index(msg) + 1
        morceaux = [f"UID {msg['uid']}"]
        litteral = None
        if "INTERNALDATE" in elements:
            morceaux.append(f'INTERNALDATE "{msg["date"].strftime("%d-%b-%Y %H:%M:%S")} +0000"')
        if "BODYSTRUCTURE" in elements:
            morceaux.append("BODYSTRUCTURE " + structure(msg))
        demande = re.search(r"BODY(\.PEEK)?\[([\d.]*)\]", elements)
        if demande:
            numero = demande.group(2)
            boite.parties_demandees.append((numero, bool(demande.group(1))))
            if not demande.group(1) and not lecture_seule:
                msg["flags"].add("\\Seen")
            if numero == "":
                contenu = b"Corps entier du message factice"
            else:
                p = msg["parties"][int(numero) - 2]
                contenu = _encoder(p["donnees"], p["encodage"])
            litteral = contenu
            morceaux.append(f"BODY[{numero}] {{{len(contenu)}}}")
        if litteral is None:
            self.ecrire(f"* {sequence} FETCH ({' '.join(morceaux)})\r\n")
        else:
            self.ecrire(f"* {sequence} FETCH ({' '.join(morceaux)}\r\n".encode("utf-8") + litteral + b")\r\n")


class Serveur(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True

    def __init__(self, boite, dossiers=("INBOX",), contexte_tls=None, identifiants=(UTILISATEUR, MOT_DE_PASSE)):
        super().__init__(("127.0.0.1", 0), Gestionnaire)
        self.boite = boite
        self.identifiants = identifiants
        self.dossiers = dossiers
        if contexte_tls:
            self.socket = contexte_tls.wrap_socket(self.socket, server_side=True)

    @property
    def port(self):
        return self.server_address[1]

    def demarrer(self):
        threading.Thread(target=self.serve_forever, daemon=True).start()
        return self

    def arreter(self):
        self.shutdown()
        self.server_close()
