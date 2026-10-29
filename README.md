# Skrivagner

Skrivagner (« scribe » en breton) collecte, analyse et classe les documents administratifs personnels d'un foyer (factures, courriers, contrats, avis d'organismes) dans une arborescence normalisée, et tient un journal de tout ce qu'il fait. Il tourne en mode souverain : aucune donnée ne quitte le réseau local, sans service tiers, sans modèle distant, sans nuage. Les modèles de langage sont ceux d'[Ollama](https://ollama.com/), sur votre machine.

Licence : [GNU Affero General Public License version 3](LICENSE).

## Ce que fait Skrivagner, et ce qu'il ne fait pas

Il fait :

- scanner des répertoires locaux, des machines distantes par `ssh` (copie vérifiée par empreinte, fichiers d'origine intacts) et des boîtes mail par IMAP en lecture seule (les pièces jointes sont déposées dans un « vide-poches » ; la boîte n'est pas modifiée) ;
- extraire le texte (couche texte du PDF, sinon lecture par un modèle de vision), trier les documents administratifs des autres, puis les classer par catégorie et par domaine (personnel ou professionnel) avec un consensus de plusieurs modèles ;
- renommer et déplacer chaque document dans le coffre de son domaine, avec journal horodaté et annulation possible (`--rollback`).

Il ne fait pas :

- bouger un fichier dont il n'est pas sûr : l'incertitude mène à un dossier `À_VÉRIFIER/`, jamais à un classement hasardeux ;
- supprimer quoi que ce soit : il déplace et copie, il n'efface pas ;
- modifier une boîte mail ni une machine distante ;
- tourner en tâche de fond : il se lance à la main, et le mode par défaut est la simulation (`--dry-run`) ;
- monter, chiffrer ou synchroniser un coffre : c'est votre affaire (voir « Limites »).

## Un outil de foyer

Skrivagner est conçu pour la gestion administrative d'un foyer, par le foyer. Une machine, un répertoire ou un compte mail n'entre dans le périmètre qu'avec l'accord, explicite ou implicite, de la personne concernée ; en cas de doute, ne l'incluez pas. Le logiciel ne peut pas garantir ce respect : c'est l'administrateur de l'instance qui s'y engage. Le journal contient des noms de fichiers et des émetteurs, qui révèlent déjà beaucoup (un courrier d'un organisme de santé suffit) : il vit dans le coffre, pas à côté.

## Prérequis

- Linux avec Python 3.12 ou 3.13 (les tests y passent) ; le code n'utilise que la bibliothèque standard ;
- `findmnt` (paquet `util-linux`) et `git` ;
- `pdftotext` et `pdftoppm` (paquet `poppler-utils`) ;
- [Ollama](https://ollama.com/) installé et en marche, avec au moins un modèle par rôle ;
- pour les machines distantes : `ssh` avec une clé qui ouvre une session sans mot de passe ;
- un répertoire de destination par domaine, sur un volume chiffré de préférence.

Sur Debian :

```bash
sudo apt install python3 python3-venv git util-linux poppler-utils openssh-client
```

Les modèles, par rôle (`ocr` lit les pages numérisées, `tri_rapide` écarte ce qui n'est pas administratif, `classification` classe) :

```bash
ollama pull glm-ocr
ollama pull gemma3:4b
ollama pull qwen2.5:3b
ollama pull gemma4:e2b
ollama pull qwen2.5
ollama pull granite4.2:8b-Q5_K_M
ollama pull mistral-nemo:12b-instruct-2407-q6_K
```

Ces modèles sont ceux de l'instance de référence ; n'importe quels autres conviennent, il suffit de les nommer dans `ollama.roles` (plus bas). Les trois modèles de `classification` votent : un document n'est classé que si leur accord atteint `ollama.seuil_confiance`.

## Installation

Arborescence finale (`~` est votre répertoire personnel ; adaptez les chemins à votre installation) :

```
~/applications/skrivagner/               le dépôt cloné
├── skrivagner.py                        le point d'entrée
├── modules/                             un fichier par responsabilité
├── tests/                               les tests
├── config.exemple.json                  la configuration d'exemple, versionnée
├── config.json                          votre configuration, créée à l'étape 3, jamais versionnée
└── venv/                                l'environnement Python, créé à l'étape 2
~/Classement/Personnel/                  le coffre du domaine personnel
~/Classement/Professionnel/              le coffre du domaine professionnel
```

1. Cloner le dépôt :

```bash
mkdir -p ~/applications && git clone https://github.com/RonanDavalan/skrivagner.git ~/applications/skrivagner
cd ~/applications/skrivagner
```

2. Créer l'environnement Python et vérifier les tests (attendu : `312 passed, 6 skipped` ; les 6 sautés sont les essais contre un Ollama qui répond) :

```bash
python3 -m venv venv
venv/bin/pip install -r requirements-dev.txt
venv/bin/python -m pytest -q tests
```

3. Créer la configuration, en `600` :

```bash
cp config.exemple.json config.json
chmod 600 config.json
```

4. Créer les deux coffres et lire le type de leur système de fichiers :

```bash
mkdir -p ~/Classement/Personnel ~/Classement/Professionnel
findmnt -n -T ~/Classement/Personnel -o FSTYPE
```

La commande affiche par exemple `ext4`. Avant chaque écriture, Skrivagner prouve que la racine de chaque coffre est montée, parce qu'un coffre fermé laisse un dossier nu sur le disque en clair : il compare ce type à `systemes_fichiers_acceptes`. L'exemple attend `fuse.gocryptfs`. Si vous chiffrez autrement (LUKS, eCryptfs…), ouvrez le volume et écrivez le type que `findmnt` rend pour lui. Sur un volume non chiffré, ce contrôle ne distingue plus un montage absent d'un montage présent : vous renoncez alors à cette protection.

5. Éditer `config.json`, ces clés au minimum :

| Clé | Rôle |
|---|---|
| `destinations.personnel.racine` et `destinations.professionnel.racine` | les deux coffres, ici `~/Classement/Personnel` et `~/Classement/Professionnel` |
| `destinations.*.systemes_fichiers_acceptes` | le type lu à l'étape 4 |
| `personnes` | les prénoms du foyer, qui nomment les dossiers du domaine personnel |
| `sources_locales[].chemin` | les répertoires à scanner |
| `suivi.fichier_date`, `suivi.journal`, `suivi.sessions` | à placer dans le coffre (par exemple `~/Classement/Personnel/logs/…`) : le journal est une donnée sensible |
| `ollama.roles` | pour chaque rôle, les modèles préférés dans l'ordre ; le premier installé est retenu |

La liste complète des clés et leur effet : lire `config.exemple.json`, dont chaque bloc est un exemple réaliste. Les mots de passe n'y entrent jamais.

6. Créer le dossier des journaux :

```bash
mkdir -p ~/Classement/Personnel/logs/sessions
```

## Usage

```bash
cd ~/applications/skrivagner
venv/bin/python skrivagner.py --dry-run     # simulation (défaut) : rien ne bouge
venv/bin/python skrivagner.py --execute     # classement réel
venv/bin/python skrivagner.py --rollback    # annule la dernière session de classement
venv/bin/python skrivagner.py --inventaire  # lit l'existant des coffres, rien n'est déplacé
```

Commencez toujours par `--dry-run`, relisez chaque destination proposée, puis lancez `--execute`. Le premier passage est lent (trois modèles lisent chaque document) ; la sortie d'erreur affiche l'avancement, `modèle i/n, document j/m`.

Codes de sortie : `0` réussi ; `1` configuration invalide, clé absente ou document resté en place ; `2` coffre non prouvé monté ; `3` aucun modèle installé pour un rôle (`ollama list`) ; `4` `--execute` refusé sur cette machine (clé `executer_sur`) ; `5` une autre exécution tient le verrou `logs/skrivagner.verrou`.

Chaque déplacement s'inscrit dans le journal des actions (`suivi.journal`, une ligne JSON par action, sans texte de document) et chaque session laisse un rapport dans `suivi.sessions`. `--rollback --session <horodatage>` annule une session précise : le document revient à sa place d'origine, copie vérifiée par empreinte.

### Machines distantes par ssh

Déclarez chaque machine dans `sources_distantes` (alias `ssh`, répertoires, `vide_poches_destination`). `ssh <alias> true` doit réussir sans mot de passe, et la machine doit offrir `find`, `sha256sum` et `cat`. En simulation, Skrivagner liste les fichiers sans rien copier ; en exécution, il les copie dans le vide-poches de la machine, vérifie leur empreinte, puis les traite comme des fichiers locaux. Les fichiers d'origine restent intacts. Un refus de connexion arrête la machine concernée : ne relancez pas en boucle.

### Boîtes mail par IMAP

Déclarez chaque boîte dans `sources_imap`. Le mot de passe se lit dans la variable d'environnement nommée par `mot_de_passe_env`, jamais dans le fichier :

```bash
read -rs SKRIVAGNER_IMAP_EXEMPLE && export SKRIVAGNER_IMAP_EXEMPLE
```

Skrivagner ouvre les dossiers en lecture seule (`EXAMINE`) et ne lit que la pièce jointe (`BODY.PEEK`) : aucun message n'est marqué lu, aucun drapeau n'est posé.

### Comptes Google par OAuth2

Un compte Google se relève avec un jeton OAuth2 à la place du mot de passe (`AUTHENTICATE XOAUTH2`). Dans la [console Google Cloud](https://console.cloud.google.com), avec le compte à relever : créer un projet, activer l'API Gmail, configurer l'écran de consentement OAuth (type externe), puis le **publier** (statut « In production », car en « Testing » l'autorisation expire au bout de sept jours), enfin créer un identifiant « Application de bureau » et télécharger son JSON. Rangez-le dans le coffre, en `600`, puis déclarez la source avec `"authentification": "oauth2"`, `client_fichier` et `token_fichier` (voir l'exemple `imap-google-exemple`) et consentez une seule fois :

```bash
venv/bin/python skrivagner.py --autoriser-google imap-google-exemple
```

Ouvrez l'adresse affichée dans un navigateur, acceptez l'avertissement « application non vérifiée » (c'est votre propre application) et le consentement. Le jeton est écrit en `600` dans le dossier du `token_fichier`, qui refuse un dépôt git et les chemins de `oauth2.chemins_interdits` ; il se renouvelle seul et n'apparaît ni au journal ni à l'écran. Si Google le révoque (accès retiré, mot de passe du compte changé, six mois sans scan), Skrivagner s'arrête avec un message explicite : refaites la commande.

## Souveraineté

- Les appels à Ollama sont des requêtes HTTP vers `ollama.url` (par défaut `http://localhost:11434`) ; aucun document ni nom de fichier ne part ailleurs.
- Les seuls services extérieurs que le code peut joindre sont ceux que vous déclarez : vos machines par `ssh`, vos boîtes IMAP, et, si vous activez OAuth2, les points d'extrémité d'autorisation de Google.
- Aucun secret n'est stocké dans `config.json` : mots de passe en variable d'environnement, jetons en fichiers `600` hors de tout dépôt.

## Limites

- Linux seulement. Le contrôle de montage repose sur `findmnt`.
- Le classement vaut ce que valent vos modèles : sur l'instance de référence, un premier essai sur 15 documents réels en a classé 2, écarté 3 comme non administratifs et mis 10 en `À_VÉRIFIER/`, par choix de prudence. Mesurez avant de faire confiance : la mesure du domaine est dans `_outils/mesurer_domaines.py`.
- Skrivagner ne monte, ne chiffre et ne synchronise aucun coffre, et n'efface rien : l'espace disque et les sauvegardes sont à votre charge.
- Les catégories, les émetteurs connus et le gabarit de nommage de `config.exemple.json` reflètent la vie administrative française (CAF, impôts, assurances) ; adaptez-les à votre pays.
- Les gestes sur la console Google dépendent de l'interface de Google, qui change : les notions restent celles de sa documentation OAuth2.
- Le projet est jeune : aucune version publiée avant la 0.8.0, pas de paquet, pas d'intégration continue.

## Contribuer, signaler une faille

Voir [CONTRIBUTING.md](CONTRIBUTING.md). Une faille se signale en privé selon [SECURITY.md](SECURITY.md), jamais dans un ticket public.

## Credits

Skrivagner est le fruit d'une collaboration entre une personne et des modèles de langage, avec les rôles écrits tels qu'ils ont été tenus. La liste complète est dans [CONTRIBUTORS.md](CONTRIBUTORS.md).

*   **Ronan Davalan** : architecte et arbitre ; vision, décisions, périmètre, validation. Seul auteur git.
*   **Claude Code (Anthropic)** : ingénieur de réalisation ; code Python et tests.
*   **Gemini (Google)** : conseiller de conception ; a proposé le nom d'origine « Le Greffier ».
*   **Copilot (Microsoft)** : a traduit ce nom en breton, d'où « Skrivagner ».
