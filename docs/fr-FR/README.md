# Skrivagner

[English](../../README.md) | **Français** | [Deutsch](../de-DE/README.md) | [Español](../es-ES/README.md)

Skrivagner (« scribe » en breton) collecte, analyse et classe les documents administratifs personnels d'un foyer (factures, courriers, contrats, avis d'organismes) dans une arborescence normalisée, et tient un journal de tout ce qu'il fait. Il tourne en mode souverain : aucune donnée ne quitte le réseau local, sans service tiers, sans modèle distant, sans nuage. Les modèles de langage sont ceux d'[Ollama](https://ollama.com/), sur votre machine.

Licence : [GNU Affero General Public License version 3](../../LICENSE).

## Ce que fait Skrivagner, et ce qu'il ne fait pas

Il fait :

- scanner des répertoires locaux, des machines distantes par `ssh` (copie vérifiée par empreinte, fichiers d'origine intacts) et des boîtes mail par IMAP en lecture seule (les pièces jointes sont déposées dans un « vide-poches » ; la boîte n'est pas modifiée) ;
- extraire le texte (couche texte du PDF, sinon lecture par un modèle de vision), trier les documents administratifs des autres, puis les classer par catégorie et par domaine (personnel ou professionnel) avec un consensus de plusieurs modèles ;
- renommer et déplacer chaque document dans le coffre de son domaine, avec journal horodaté et annulation possible (`--rollback`).

Il ne fait pas :

- bouger un fichier dont il n'est pas sûr : l'incertitude mène à un dossier `À_VÉRIFIER/`, jamais à un classement hasardeux ;
- supprimer un document : il déplace et copie, il n'efface pas (il ne retire que ses propres vieux journaux, chapitre « Inventaire et rotation » du manuel) ;
- modifier une boîte mail ni une machine distante ;
- tourner en tâche de fond : il se lance à la main, et le mode par défaut est la simulation (`--dry-run`) ;
- monter, chiffrer ou synchroniser un coffre : c'est votre affaire (voir « Limites »).

## Un outil de foyer

Skrivagner est conçu pour la gestion administrative d'un foyer, par le foyer. Une machine, un répertoire ou un compte mail n'entre dans le périmètre qu'avec l'accord, explicite ou implicite, de la personne concernée ; en cas de doute, ne l'incluez pas. Le logiciel ne peut pas garantir ce respect : c'est l'administrateur de l'instance qui s'y engage. Le journal contient des noms de fichiers et des émetteurs, qui révèlent déjà beaucoup (un courrier d'un organisme de santé suffit) : il vit dans le coffre, pas à côté.

## Prérequis

- Linux avec Python 3.10 ou plus (les tests passent en 3.12 et 3.13) ; le code n'utilise que la bibliothèque standard ;
- `findmnt` (paquet `util-linux`) et `git` ;
- `pdftotext` et `pdftoppm` (paquet `poppler-utils`) ;
- [Ollama](https://ollama.com/) installé et en marche, avec au moins un modèle par rôle ;
- pour les machines distantes : `ssh` avec une clé qui ouvre une session sans mot de passe ;
- un répertoire de destination par domaine, sur un volume chiffré de préférence.

Sur Debian :

```bash
sudo apt install python3 python3-venv git util-linux poppler-utils openssh-client
```

Les modèles, par rôle (`ocr` lit les pages numérisées, `tri_rapide` écarte ce qui n'est pas administratif, `classification` classe) :

```bash
ollama pull glm-ocr
ollama pull mistral-nemo:12b-instruct-2407-q6_K
ollama pull gemma4
ollama pull gemma3:4b
ollama pull qwen2.5
ollama pull granite4.2:8b-Q5_K_M
```

Ces modèles sont ceux de l'instance de référence ; n'importe quels autres conviennent, il suffit de les nommer dans `ollama.roles` (plus bas). Les modèles du rôle `classification` votent : un document n'est classé que si leur accord atteint `ollama.seuil_confiance`. Ollama ne fait pas partie de Skrivagner et celui-ci ne l'installe jamais.

## Installation depuis le paquet Debian

Sur Debian 12 et 13 et sur Ubuntu 22.04 et 24.04, un seul fichier installe le programme et ses dépendances (`python3`, `poppler-utils`, `util-linux`, `openssh-client`). Il ne contient ni Ollama, ni modèle, ni configuration. Téléchargez `skrivagner_*_all.deb` depuis la page de téléchargement de [skrivagner.davalan.fr](https://skrivagner.davalan.fr/), puis, depuis le dossier qui le contient :

```bash
sudo apt install ./skrivagner_*_all.deb
```

Créez la configuration à partir de l'exemple que le paquet installe, avec le mode `600`, puis suivez les étapes 4 et 5 de l'installation depuis les sources ci-dessous (le coffre de chaque domaine, les clés de la configuration) :

```bash
mkdir -p ~/.config/skrivagner
cp /usr/share/doc/skrivagner/examples/config.exemple.json ~/.config/skrivagner/config.json
chmod 600 ~/.config/skrivagner/config.json
```

Vérifiez l'installation, sans rien écrire :

```bash
skrivagner --version
skrivagner --diagnose
```

Le paquet place la commande dans `/usr/bin/skrivagner`, le programme dans `/usr/lib/skrivagner/`, et les README, la configuration d'exemple et la page de manuel (`man skrivagner`, en quatre langues) sous `/usr/share/`. Le retrait garde vos données : `sudo apt remove skrivagner` et `sudo apt purge skrivagner` suppriment les fichiers du paquet et ne touchent jamais à votre configuration, à votre état, à votre journal ni à vos documents ; la purge nomme ce qu'elle laisse.

Niveau : installation et diagnostic validés en conteneur sur Debian 12 et 13 et sur Ubuntu 22.04 et 24.04 (installation, `--version`, `--diagnose`, le refus d'écrire sans configuration et celui d'écrire dans un coffre non monté, un classement simulé, retrait et purge). Un conteneur ne montre ni le montage d'un coffre chiffré, ni un passage avec votre propre Ollama et vos propres documents.

## Installation depuis les sources

Arborescence finale (`~` est votre répertoire personnel ; adaptez les chemins à votre installation) :

```
~/applications/skrivagner/               le dépôt cloné
├── skrivagner.py                        le point d'entrée
├── modules/                             un fichier par responsabilité
│   └── langues/                         les dictionnaires de messages : en, fr, de, es
├── docs/                                les traductions de ce README et la page de manuel
├── tests/                               les tests
├── config.exemple.json                  la configuration d'exemple, versionnée
└── venv/                                l'environnement Python, créé à l'étape 2
~/.config/skrivagner/config.json         votre configuration, créée à l'étape 3, jamais versionnée
~/.local/state/skrivagner/               l'état, le journal et les rapports de session (emplacement par défaut)
~/Classement/Personnel/                  le coffre du domaine personnel
~/Classement/Professionnel/              le coffre du domaine professionnel
```

1. Cloner le dépôt :

```bash
mkdir -p ~/applications && git clone https://github.com/RonanDavalan/skrivagner.git ~/applications/skrivagner
cd ~/applications/skrivagner
```

2. Créer l'environnement Python et vérifier les tests (attendu : `466 passed, 8 skipped` ; les 8 sautés sont les essais contre un Ollama qui répond) :

```bash
python3 -m venv venv
venv/bin/pip install -r requirements-dev.txt
venv/bin/python -m pytest -q tests
```

3. Créer la configuration, en `600`. Skrivagner lit le premier fichier trouvé parmi : l'option `--config <chemin>`, la variable d'environnement `SKRIVAGNER_CONFIG`, `~/.config/skrivagner/config.json` (ou `$XDG_CONFIG_HOME/skrivagner/config.json`), puis `config.json` à côté de `skrivagner.py`. Une option ou une variable qui désigne un fichier absent arrête le programme : il ne retombe jamais sur un autre fichier.

```bash
mkdir -p ~/.config/skrivagner
cp config.exemple.json ~/.config/skrivagner/config.json
chmod 600 ~/.config/skrivagner/config.json
```

4. Créer les deux coffres et lire le type de leur système de fichiers :

```bash
mkdir -p ~/Classement/Personnel ~/Classement/Professionnel
findmnt -n -T ~/Classement/Personnel -o FSTYPE
```

La commande affiche par exemple `ext4`. Avant chaque écriture, Skrivagner établit que la racine de chaque coffre est montée, parce qu'un coffre fermé laisse un dossier nu sur le disque en clair : il compare ce type à `systemes_fichiers_acceptes`. L'exemple attend `fuse.gocryptfs`. Si vous chiffrez autrement (LUKS, eCryptfs…), ouvrez le volume et écrivez le type que `findmnt` rend pour lui. Sur un volume non chiffré, ce contrôle ne distingue plus un montage absent d'un montage présent : vous renoncez alors à cette protection.

5. Éditer `~/.config/skrivagner/config.json`, ces clés au minimum :

| Clé | Rôle |
|---|---|
| `destinations.personnel.racine` et `destinations.professionnel.racine` | les deux coffres, ici `~/Classement/Personnel` et `~/Classement/Professionnel` |
| `destinations.*.systemes_fichiers_acceptes` | le type lu à l'étape 4 |
| `personnes` | les prénoms du foyer, qui nomment les dossiers du domaine personnel |
| `sources_locales[].chemin` | les répertoires à scanner |
| `suivi.fichier_date`, `suivi.journal`, `suivi.sessions` | absentes, l'état s'écrit en clair sous `~/.local/state/skrivagner/` (ou `$XDG_STATE_HOME/skrivagner/`) ; pour le chiffrer, ajoutez ces trois clés dans le coffre (par exemple `~/Classement/Personnel/logs/…`) : le journal est une donnée sensible |
| `ollama.roles` | pour chaque rôle, les modèles préférés dans l'ordre ; le premier installé est retenu |

La liste complète des clés et leur effet : lire `config.exemple.json`, dont chaque bloc est un exemple réaliste. Les mots de passe n'y entrent jamais.

6. Vérifier l'installation, sans rien écrire :

```bash
venv/bin/python skrivagner.py --version
venv/bin/python skrivagner.py --diagnose
```

`--version` écrit une ligne et s'arrête :

```
skrivagner 0.9.0-alpha
```

`--diagnose` écrit une ligne par vérification, `<ÉTAT> <identifiant> : <message>`, puis un bilan. Dans un domicile neuf, sans configuration ni Ollama, la sortie est la suivante et le code de sortie `0` :

```
OK python : 3.13.5
OK outil_pdftotext : /usr/bin/pdftotext
OK outil_pdftoppm : /usr/bin/pdftoppm
OK outil_findmnt : /usr/bin/findmnt
OK outil_ssh : /usr/bin/ssh
NON_CONFIGURÉ configuration : aucune configuration trouvée (l'option --config : non donnée; la variable SKRIVAGNER_CONFIG : non donnée; l'emplacement XDG : ~/.config/skrivagner/config.json; le dossier du script : ~/applications/skrivagner/config.json)
NON_VÉRIFIÉ emplacement_etat : dépend de la configuration
NON_VÉRIFIÉ ollama : dépend de la configuration
NON_VÉRIFIÉ modele_ocr : dépend de la configuration
NON_VÉRIFIÉ modele_tri_rapide : dépend de la configuration
NON_VÉRIFIÉ modele_classification : dépend de la configuration
NON_VÉRIFIÉ destination_personnel : dépend de la configuration
NON_VÉRIFIÉ destination_professionnel : dépend de la configuration
Diagnostic : 5 OK, 0 avertissement(s), 0 échec(s), 1 non configuré(s), 7 non vérifié(s)
```

Les jetons d'état (`OK`, `AVERTISSEMENT`, `ÉCHEC`, `NON_CONFIGURÉ`, `NON_VÉRIFIÉ`) et les identifiants sont les mêmes dans toutes les langues, pour qu'un script puisse les comparer. Une fois la configuration écrite, tout ce qu'elle déclare et que la machine ne tient pas (Ollama éteint, modèle absent, coffre non monté) est un `ÉCHEC` et le code de sortie vaut `1`. Avec la configuration de l'étape 5 remplie et les coffres montés, la sortie se termine par un bilan comme celui-ci :

```
Diagnostic : 12 OK, 1 avertissement(s), 0 échec(s), 0 non configuré(s), 0 non vérifié(s)
```

Le seul avertissement est l'état et le journal en clair sous `~/.local/state/skrivagner/`, tant que vous ne les déplacez pas dans un coffre.

## Langue des messages

Skrivagner écrit ses messages en anglais, en français, en allemand ou en espagnol. La langue se lit une fois au démarrage, dans la première des variables `LC_ALL`, `LC_MESSAGES` et `LANG` qui n'est pas vide : `fr_FR.UTF-8` donne le français, `de_DE.UTF-8` l'allemand, `es_ES.UTF-8` l'espagnol, `en_US.UTF-8` l'anglais, et toute autre valeur, ou aucune, l'anglais. Pour lire le même contrôle dans une autre langue :

```bash
LC_ALL=de_DE.UTF-8 venv/bin/python skrivagner.py --diagnose
```

Les noms d'option, les jetons d'état, les identifiants, les journaux et les fichiers de plan ne changent jamais avec la langue : ce qui s'écrit sur le disque est en anglais, pour qu'un journal écrit dans une langue se rejoue par `--rollback` dans n'importe quelle autre. Les dictionnaires de messages sont les fichiers `modules/langues/en.txt`, `fr.txt`, `de.txt` et `es.txt`.

## Usage

```bash
cd ~/applications/skrivagner
venv/bin/python skrivagner.py --dry-run     # simulation (défaut) : rien ne bouge
venv/bin/python skrivagner.py --execute     # classement réel
venv/bin/python skrivagner.py --rollback    # annule la dernière session de classement
venv/bin/python skrivagner.py --inventaire  # lit l'existant des coffres, rien n'est déplacé
venv/bin/python skrivagner.py --diagnose    # vérifie l'installation, la configuration, Ollama et les coffres, sans rien écrire
venv/bin/python skrivagner.py --version     # écrit une ligne, `skrivagner <version>`, et s'arrête
venv/bin/python skrivagner.py --dry-run --config ~/autre/config.json   # lit cette configuration-là
venv/bin/python skrivagner.py --help        # liste toutes les options, dans la langue de la session
```

Commencez toujours par `--dry-run`, relisez chaque destination proposée, puis lancez `--execute`. Le premier passage est lent (plusieurs modèles lisent chaque document) ; la sortie d'erreur affiche l'avancement, `modèle i/n, document j/m`. Voici un `--dry-run` sur un dossier source vide, qui demande Ollama et les trois modèles des rôles :

```
Skrivagner 0.9.0-alpha — session 2026-10-29T17:33:29
  Mode               : dry-run
  Configuration      : ~/.config/skrivagner/config.json
  Coffre personnel     : ~/Classement/Personnel — monté
  Coffre professionnel : ~/Classement/Professionnel — monté
  Journal de session : ~/.local/state/skrivagner/sessions/session_2026-10-29T17:33:29.jsonl
  Modèle ocr           : glm-ocr:latest
  Modèle tri_rapide    : gemma3:4b
  Modèle classification: granite4.2:8b-Q5_K_M
  Consensus          : 1 modèle(s) de classification, seuil 0.4

Source : entrant (~/Classement/Entrant)
  (aucun fichier candidat)
  Total source : 0 fichier(s), 0 o

============================================================
Total scan : 0 fichier(s) candidat(s), 0 o
============================================================
Extraction du texte (le texte n'est ni affiché ni écrit)

Classification (dry-run, aucun déplacement ; le texte n'est ni affiché ni écrit)
```

Codes de sortie :

| Code | Sens |
|---|---|
| `0` | réussite |
| `1` | configuration introuvable, invalide ou à clé absente ; au moins une source ou un document en échec ; annulation partielle ; consentement OAuth2 en échec ; `--diagnose` avec au moins un `ÉCHEC` |
| `2` | montage du coffre non établi avant un mode qui écrit ; ligne de commande invalide |
| `3` | aucun modèle installé pour un rôle (`ollama list`), ou Ollama sans réponse |
| `4` | `--execute` refusé sur cette machine (clé `executer_sur`) |
| `5` | une autre exécution tient le verrou `skrivagner.verrou` (à côté de `suivi.fichier_date`) |

Chaque déplacement s'inscrit dans le journal des actions (`suivi.journal`, une ligne JSON par action, sans texte de document) et chaque session laisse un rapport dans `suivi.sessions`. `--rollback --session <horodatage>` annule une session précise : le document revient à sa place d'origine, copie vérifiée par empreinte.

### Page de manuel

La page de manuel est écrite en Markdown dans `docs/skrivagner.1.md`, avec ses traductions dans `docs/fr-FR/`, `docs/de-DE/` et `docs/es-ES/`. Pour la lire depuis les sources :

```bash
pandoc --standalone --from markdown-smart --to man docs/fr-FR/skrivagner.1.md | man -l -
```

### Machines distantes par ssh

Déclarez chaque machine dans `sources_distantes` (alias `ssh`, répertoires, `vide_poches_destination`). `ssh <alias> true` doit réussir sans mot de passe, et la machine doit offrir `find`, `sha256sum` et `cat`. En simulation, Skrivagner liste les fichiers sans rien copier ; en exécution, il les copie dans le vide-poches de la machine, vérifie leur empreinte, puis les traite comme des fichiers locaux. Les fichiers d'origine restent intacts. Un refus de connexion arrête la machine concernée : ne relancez pas en boucle.

### Boîtes mail par IMAP

Déclarez chaque boîte dans `sources_imap`. Le mot de passe se lit dans la variable d'environnement nommée par `mot_de_passe_env`, jamais dans le fichier :

```bash
read -rs SKRIVAGNER_IMAP_EXEMPLE && export SKRIVAGNER_IMAP_EXEMPLE
```

Skrivagner ouvre les dossiers en lecture seule (`EXAMINE`) et ne lit que la pièce jointe (`BODY.PEEK`) : aucun message n'est marqué lu, aucun drapeau n'est posé.

### Comptes Google par OAuth2

Un compte Google se relève avec un jeton OAuth2 à la place du mot de passe (`AUTHENTICATE XOAUTH2`). Dans la [console Google Cloud](https://console.cloud.google.com), avec le compte à relever : créer un projet, activer l'API Gmail, configurer l'écran de consentement OAuth (type externe), puis le **publier** (statut « In production », car en « Testing » l'autorisation expire au bout de sept jours), enfin créer un identifiant « Application de bureau » et télécharger son JSON. Rangez-le dans le coffre, en `600`, puis déclarez la source avec `"authentification": "oauth2"`, `client_fichier` et `token_fichier` (voir l'exemple `imap-google-exemple`) et consentez une seule fois :

```bash
venv/bin/python skrivagner.py --autoriser-google imap-google-exemple
```

Ouvrez l'adresse affichée dans un navigateur, acceptez l'avertissement « application non vérifiée » (c'est votre propre application) et le consentement. Le jeton est écrit en `600` dans le dossier du `token_fichier`, qui refuse un dépôt git et les chemins de `oauth2.chemins_interdits` ; il se renouvelle seul et n'apparaît ni au journal ni à l'écran. Si Google le révoque (accès retiré, mot de passe du compte changé, six mois sans scan), Skrivagner s'arrête avec un message explicite : refaites la commande.

## Souveraineté

- Les appels à Ollama sont des requêtes HTTP vers `ollama.url` (par défaut `http://localhost:11434`) ; aucun document ni nom de fichier ne part ailleurs.
- Les seuls services extérieurs que le code peut joindre sont ceux que vous déclarez : vos machines par `ssh`, vos boîtes IMAP et, si vous activez OAuth2, les points d'extrémité d'autorisation de Google.
- Aucun secret n'est stocké dans `config.json` : mots de passe en variable d'environnement, jetons en fichiers `600` hors de tout dépôt.

## Limites

- Linux seulement. Le contrôle de montage repose sur `findmnt`.
- Le classement vaut ce que valent vos modèles : sur l'instance de référence, un premier essai sur 15 documents réels en a classé 2, écarté 3 comme non administratifs et mis 10 en `À_VÉRIFIER/`, par choix de prudence. Mesurez avant de faire confiance : la mesure du domaine est dans `_outils/mesurer_domaines.py`.
- Skrivagner ne monte, ne chiffre et ne synchronise aucun coffre, et n'efface aucun document : l'espace disque et les sauvegardes sont à votre charge.
- Les catégories, les émetteurs connus et le gabarit de nommage de `config.exemple.json` reflètent la vie administrative française (CAF, impôts, assurances) ; adaptez-les à votre pays.
- Les gestes sur la console Google dépendent de l'interface de Google, qui change : les notions restent celles de sa documentation OAuth2.
- Le projet est jeune : version 0.9.0-alpha, pas d'intégration continue.

## Contribuer, signaler une faille

Voir [CONTRIBUTING.md](../../CONTRIBUTING.md). Une faille se signale en privé selon [SECURITY.md](../../SECURITY.md), jamais dans un ticket public.

## Crédits

Skrivagner est le fruit d'une collaboration entre une personne et des modèles de langage, avec les rôles écrits tels qu'ils ont été tenus. La liste complète est dans [CONTRIBUTORS.md](../../CONTRIBUTORS.md).

* **Ronan Davalan** : architecte et arbitre ; vision, décisions, périmètre, validation. Seul auteur git.
* **Claude Code (Anthropic)** : ingénieur de réalisation ; code Python et tests, et documents publics (ce README et ses traductions, la page de manuel, `CONTRIBUTING.md`, `SECURITY.md`).
* **Gemini (Google)** : conseiller de conception ; a proposé le nom d'origine « Le Greffier ».
* **Copilot (Microsoft)** : a traduit ce nom en breton, d'où « Skrivagner ».
