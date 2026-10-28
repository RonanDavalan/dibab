# Contribuer à Skrivagner

Merci de l'intérêt. Skrivagner classe des documents administratifs sensibles : la prudence passe avant la vitesse, et chaque contribution est jugée d'abord sur ce qu'elle ne risque pas de casser.

## Avant d'écrire du code

- Ouvrez un ticket qui décrit le besoin avant une grosse modification (nouvelle source, nouveau comportement visible). Une correction de défaut ou de documentation peut arriver directement en demande de fusion.
- Une faille de sécurité ne se signale jamais dans un ticket : voir [SECURITY.md](SECURITY.md).
- Skrivagner reste un outil de foyer et souverain : pas de service tiers, pas de modèle distant, pas de télémétrie, pas de mode « nuage ». Une contribution qui les introduit sera refusée.

## Environnement

```bash
git clone https://github.com/RonanDavalan/skrivagner.git ~/applications/skrivagner
cd ~/applications/skrivagner
python3 -m venv venv
venv/bin/pip install -r requirements-dev.txt
venv/bin/python -m pytest -q tests
```

Les tests ne touchent ni Ollama, ni `ssh`, ni IMAP, ni Google : ils emploient de faux serveurs et des documents factices (`tests/faux_imap.py`, `tests/faux_ssh.py`, `tests/textes_factices.py`). Les tests marqués `ollama_reel` sont sautés tant que `SKRIVAGNER_MODELE_OCR_ESSAI` ne nomme pas un modèle installé.

## Les règles du code

- **Bibliothèque standard seulement** pour le code (`ssh` par `subprocess`, Ollama par `urllib`). Une dépendance nouvelle se justifie dans la demande de fusion.
- **Simulation par défaut** : tout nouveau geste qui écrit ou déplace est inactif en `--dry-run` et laisse une trace au journal des actions, de façon que `--rollback` puisse le défaire.
- **Jamais de suppression**, jamais d'écriture dans une boîte mail ni sur une machine distante.
- **Aucun secret dans un fichier versionné, un journal, un rapport ou une sortie** : mots de passe en variable d'environnement, jetons en fichier `600`. Un test le prouve pour tout nouveau secret.
- **Aucun document réel, aucun nom de personne, d'hôte ou de chemin personnel** dans le code, les tests, les exemples, les tickets et les captures. Les tests emploient des textes factices.
- **Chaque comportement a son test**, y compris le cas d'échec ; un défaut corrigé reçoit le test qui l'aurait attrapé. Les nouveaux tests échouent sans la modification qu'ils couvrent.
- **Commentaires en français, au pourquoi seulement** : l'intention, la contrainte, le piège qui surprendrait un lecteur compétent. Ni évidence, ni historique de l'édition (« ajouté », « corrigé »). Le français est écrit avec ses accents.
- **Les clés de `config.json` ne se renomment pas** : on ajoute une clé, avec une valeur par défaut qui conserve le comportement existant, et on la documente dans `config.exemple.json` et le `README.md`.

## Demande de fusion

1. Une branche par sujet, des commits qui disent ce qu'ils changent.
2. `venv/bin/python -m pytest -q tests` passe en entier.
3. `git grep -nE '/hom[e]/|@gmai[l]|ssh -'` ne trouve rien de personnel dans ce que vous ajoutez.
4. Le `README.md` et `config.exemple.json` sont à jour si le comportement visible ou la configuration change.

En contribuant, vous acceptez que votre apport soit publié sous la licence du projet, la [GNU Affero General Public License version 3](LICENSE). Votre nom et le rôle tenu sont ajoutés à [CONTRIBUTORS.md](CONTRIBUTORS.md) le jour de la fusion.
