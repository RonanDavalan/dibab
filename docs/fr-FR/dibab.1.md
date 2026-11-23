% DIBAB(1) dibab | Commandes utilisateur
% Ronan Davalan
% 2026-10-29

# NOM

dibab - collecte, analyse et classe les documents administratifs personnels d'un foyer, sans qu'aucune donnée ne quitte le réseau local

# SYNOPSIS

**dibab** [**\--config** *CHEMIN*] [**\--dry-run** | **\--execute** | **\--inventaire**]

**dibab** **\--dry-run** **\--verdicts-simules** *FICHIER*

**dibab** [**\--config** *CHEMIN*] **\--rollback** [**\--session** *SESSION*]

**dibab** [**\--config** *CHEMIN*] **\--autoriser-google** *ID*

**dibab** [**\--config** *CHEMIN*] **\--diagnose**

**dibab** {**\--version** | **\--help**}

# DESCRIPTION

**dibab** scanne des répertoires locaux, des machines distantes par **ssh**(1) et des boîtes mail par IMAP en lecture seule. Il
extrait le texte de chaque document, écarte ce qui n'est pas administratif, puis classe le reste par catégorie et par domaine,
personnel ou professionnel, par consensus de plusieurs modèles de langage. Chaque document est renommé et déplacé dans le coffre de
son domaine, avec un journal que **\--rollback** peut défaire. Il ne détruit jamais un document : l'original n'est retiré qu'après une
copie vérifiée ; il ne modifie jamais une boîte mail ni une machine distante, et ne déplace rien dont il n'est pas sûr : le doute mène à
un dossier nommé *À_VÉRIFIER*.

Les modèles de langage sont ceux d'Ollama, qui tourne sur la même machine. Ollama et ses modèles s'installent à part, par
l'utilisateur, depuis le site d'Ollama : Dibab ne contient ni l'un ni les autres. Listez les modèles avec **ollama list**, puis
écrivez-les, rôle par rôle, dans la clé **ollama.roles** de la configuration. Seuls les coffres de destination, les machines et les
boîtes que la configuration nomme sont joints.

Le mode par défaut est la simulation. Relisez toujours le résultat de **\--dry-run** avant de lancer **\--execute**.

# OPTIONS

**\--dry-run**
: Simulation, mode par défaut : scanne, extrait et classe, et affiche chaque destination qu'il choisirait. Rien n'est déplacé.

**\--execute**
: Mode réel : chaque document est copié, vérifié par empreinte (SHA256), puis retiré de sa source. Refusé sur une machine que la clé
    **executer_sur** de la configuration ne liste pas.

**\--inventaire**
: Lit l'existant des coffres et écrit un plan de migration pour chacun. Rien n'est déplacé.

**\--rollback**
: Annule la dernière session de classement, ou celle que nomme **\--session**. Le document revient à sa place d'origine, copie
    vérifiée par empreinte ; une action qui ne peut pas être annulée laisse tout en place pour elle.

**\--session** *SESSION*
: Identifiant de la session à annuler, avec **\--rollback**.

**\--autoriser-google** *ID*
: Consentement OAuth2 de la source IMAP Google nommée *ID* dans la configuration. Affiche une adresse à ouvrir dans un navigateur,
    puis écrit le fichier de jeton de la source.

**\--diagnose**
: Vérifie l'installation, la configuration, Ollama et les coffres, une ligne par vérification, et n'écrit rien.

**\--verdicts-simules** *FICHIER*
: Avec **\--dry-run** seulement : un fichier JSON qui associe un nom de fichier à un verdict, dont le routage est affiché.

**\--config** *CHEMIN*
: Fichier de configuration à lire (voir **FICHIERS**).

**\--version**
: Écrit une ligne, **dibab** *version*, et s'arrête.

**\--help**, **-h**
: Liste les options, dans la langue de la session.

# LANGUE

Les messages sont écrits en anglais, en français, en allemand ou en espagnol. La langue se lit une fois au démarrage, dans la première
des variables **LC_ALL**, **LC_MESSAGES** et **LANG** qui n'est pas vide : ce qui précède le premier **\_**, **.** ou **@** donne **en**,
**fr**, **de** ou **es** ; toute autre valeur, **C**, **POSIX** ou aucune variable donne l'anglais. Les noms d'option, les jetons d'état de
**\--diagnose** (**OK**, **AVERTISSEMENT**, **ÉCHEC**, **NON_CONFIGURÉ**, **NON_VÉRIFIÉ**), les identifiants des vérifications et la ligne de
**\--version** ne changent jamais. Les clés et les textes libres écrits sur le disque (journaux, plans, rapports) sont en anglais, quelle
que soit la langue de la session ; les jetons d'action (**classe**, **a_verifier**, **doublon**) et les noms de domaine ne changent jamais.

# INSTALLATION

Sur Debian 12 et 13 et sur Ubuntu 22.04 et 24.04, le paquet Debian installe le programme, ses dépendances, les quatre pages de manuel et la configuration d'exemple *config.exemple.json* dans */usr/share/doc/dibab/examples/* :

    sudo apt install ./dibab_*_all.deb

**sudo apt remove dibab** et **sudo apt purge dibab** suppriment les fichiers du paquet et ne touchent jamais à la configuration, à l'état, au journal ni aux documents ; la purge nomme ce qu'elle laisse. Niveau : installation et diagnostic validés en conteneur sur ces quatre versions ; un conteneur ne montre ni le montage d'un coffre chiffré, ni un passage avec votre propre Ollama.

# FICHIERS

La configuration est le premier fichier existant parmi, dans cet ordre, et c'est le seul qui est lu :

1. le fichier que nomme **\--config** ;
2. le fichier que nomme la variable **DIBAB_CONFIG**, quand elle n'est pas vide ;
3. *$XDG_CONFIG_HOME/dibab/config.json*, ou *~/.config/dibab/config.json* quand **XDG_CONFIG_HOME** est vide ou absente ;
4. *config.json* dans le dossier de *dibab.py*.

Une option ou une variable qui désigne un fichier absent arrête le programme avec le code 1 : il ne retombe jamais sur un autre
fichier. *config.exemple.json* est l'exemple, dans le dossier du programme ; copiez-le à l'un de ces emplacements, en mode 600.

Quand la configuration ne donne pas les clés de **suivi**, l'état s'écrit sous *$XDG_STATE_HOME/dibab/*, ou
*~/.local/state/dibab/* : *dernier_scan.json*, *journal.jsonl* (le journal des actions), *sessions/* (un journal et un rapport par
session) et *dibab.log*. *rapatries.json*, *imap_deposes.json* et le verrou *dibab.verrou* se trouvent à côté de
*dernier_scan.json*. Les dossiers se créent en mode 700 et les fichiers en mode 600. L'état est alors en clair sur le disque : pour
le garder dans un coffre, donnez les clés **suivi.fichier_date**, **suivi.journal** et **suivi.sessions**.

Les dictionnaires de messages sont *modules/langues/en.txt*, *fr.txt*, *de.txt* et *es.txt*, dans le dossier du programme.

# ENVIRONNEMENT

**DIBAB_CONFIG**
: Chemin du fichier de configuration.

**XDG_CONFIG_HOME**, **XDG_STATE_HOME**
: Dossiers de base de la configuration et de l'état par défaut.

**LC_ALL**, **LC_MESSAGES**, **LANG**
: Langue des messages (voir **LANGUE**).

Le mot de passe d'une boîte IMAP se lit dans la variable que nomme la clé **mot_de_passe_env** de sa source, jamais dans le fichier de
configuration.

# CODE DE RETOUR

**0**
: Réussite.

**1**
: Configuration introuvable, invalide ou à clé absente ; au moins une source ou un document en échec ; annulation partielle ;
    consentement OAuth2 en échec ; **\--diagnose** avec au moins un **ÉCHEC**.

**2**
: Montage du coffre non établi, avant un mode qui écrit ; ligne de commande invalide.

**3**
: Aucun modèle installé pour un rôle, ou Ollama sans réponse.

**4**
: **\--execute** refusé sur cette machine (clé **executer_sur**).

**5**
: Une autre exécution tient le verrou *dibab.verrou*.

# EXEMPLES

Vérifier l'installation, puis simuler, puis classer pour de bon :

    dibab --diagnose
    dibab --dry-run
    dibab --execute

Lire le même contrôle en anglais, puis annuler la dernière session :

    LC_ALL=en_US.UTF-8 dibab --diagnose
    dibab --rollback

# VOIR AUSSI

**ollama**(1), **ssh**(1), **findmnt**(8), **pdftotext**(1), **pdftoppm**(1)

Le README du projet décrit l'installation depuis le paquet Debian et depuis les sources, la configuration, les sources par **ssh**, IMAP et OAuth2 pour Google,
et les limites.

# LICENCE

GNU Affero General Public License version 3.
