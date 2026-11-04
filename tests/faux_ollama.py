"""Faux serveur Ollama local, en HTTP réel : `/api/tags`, `/api/generate` et `/v1/systemone`.

Il enregistre chaque requête (chemin, modèle, `keep_alive`, corps) pour vérifier l'ordre de chargement des modèles,
et rend des réponses réglées par le test : probabilité de non administratif par texte, réponse brute, code HTTP.
"""

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


class FauxOllama:
    """`probabilite(etat)` rend la probabilité de non administratif d'un texte ; `systemone` remplace la réponse entière.

    `systemone` vaut None (réponse normale), un dict ou une chaîne (corps rendu tel quel), ou un entier (code HTTP d'erreur,
    corps texte comme celui d'un Ollama qui ne connaît pas le point d'accès).
    """

    def __init__(self, probabilite=lambda etat: 0.01, systemone=None, objet="objet factice", objet_brut=None, tri="administratif",
                 fine=None, modeles=None, capacites=True):
        self.probabilite, self.systemone, self.objet, self.tri, self.fine = probabilite, systemone, objet, tri, fine
        self.objet_brut = objet_brut
        self.modeles = modeles if modeles is not None else {"m-decision:latest": ["decision"], "m-objet:latest": ["completion"],
                                                            "m-tri:latest": ["completion"], "m-fin:latest": ["completion"]}
        self.capacites = capacites
        self.requetes = []
        faux = self

        class Gestionnaire(BaseHTTPRequestHandler):
            def log_message(self, *_):
                pass

            def _repondre(self, code, corps, type_contenu="application/json"):
                donnees = corps if isinstance(corps, bytes) else (corps if isinstance(corps, str) else json.dumps(corps)).encode("utf-8")
                self.send_response(code)
                self.send_header("Content-Type", type_contenu)
                self.send_header("Content-Length", str(len(donnees)))
                self.end_headers()
                self.wfile.write(donnees)

            def do_GET(self):
                if self.path != "/api/tags":
                    return self._repondre(404, b"404 page not found", "text/plain")
                modeles = [{"name": nom, **({"capabilities": capacites} if faux.capacites else {})}
                           for nom, capacites in faux.modeles.items()]
                return self._repondre(200, {"models": modeles})

            def do_POST(self):
                corps = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                faux.requetes.append({"chemin": self.path, "modele": corps.get("model"), "keep_alive": corps.get("keep_alive"),
                                      "corps": corps})
                if self.path == "/v1/systemone":
                    return self._systemone(corps)
                if self.path == "/api/generate":
                    return self._repondre(200, {"response": faux.generer(corps)})
                return self._repondre(404, b"404 page not found", "text/plain")

            def _systemone(self, corps):
                reglage = faux.systemone
                if isinstance(reglage, int):
                    return self._repondre(reglage, b"404 page not found" if reglage == 404 else b"erreur", "text/plain")
                if reglage is not None:
                    return self._repondre(200, reglage)
                p = faux.probabilite(corps["state"])
                return self._repondre(200, {"model": corps["model"], "answers": {"nature": {
                    "type": "choice", "choice": "non_administratif" if p >= 0.5 else "administratif",
                    "probabilities": {"administratif": 1 - p, "non_administratif": p}, "confidence": abs(2 * p - 1)}}})

        self.serveur = ThreadingHTTPServer(("127.0.0.1", 0), Gestionnaire)
        self.url = f"http://127.0.0.1:{self.serveur.server_address[1]}"
        self.fil = threading.Thread(target=self.serveur.serve_forever, daemon=True)

    def generer(self, corps):
        proprietes = corps["format"]["properties"]
        if "verdict" in proprietes:
            return json.dumps({"verdict": self.tri, "objet": "objet du tri par génération"})
        if set(proprietes) == {"objet"}:
            return self.objet_brut if self.objet_brut is not None else json.dumps({"objet": self.objet})
        return json.dumps(self.fine)

    def __enter__(self):
        self.fil.start()
        return self

    def __exit__(self, *_):
        self.serveur.shutdown()
        self.serveur.server_close()

    def chemins(self):
        return [(requete["chemin"], requete["modele"]) for requete in self.requetes]
