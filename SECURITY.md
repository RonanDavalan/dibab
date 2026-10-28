# Politique de sécurité

Skrivagner manipule des documents administratifs (santé, banque, impôts, succession) et des accès à des boîtes mail : une faille y a un coût réel pour des tiers. Cette politique dit comment la signaler et ce que vous pouvez attendre en retour.

## Versions prises en charge

Seule la dernière version publiée reçoit des correctifs de sécurité. Le projet n'a pas de branche de maintenance : la correction paraît sur `main` et dans une nouvelle version.

## Signaler une faille

Passez par le signalement privé de GitHub : onglet « Security » du dépôt, puis « Report a vulnerability » (GitHub Security Advisories). **N'ouvrez jamais de ticket public** pour une faille : la publier avant le correctif expose les personnes qui utilisent déjà Skrivagner.

Indiquez la version (`venv/bin/python skrivagner.py --dry-run` l'affiche en tête), ce que vous avez observé, les étapes pour le reproduire et, si possible, ce que vous jugez en danger. N'envoyez aucun document réel ni aucun secret : un texte factice suffit.

## Délais

- accusé de réception sous 72 heures ;
- première évaluation (faille confirmée ou non, gravité) sous 7 jours ;
- correctif visé sous 30 jours pour une faille confirmée ; si ce délai ne peut pas être tenu, vous en êtes informé avec la raison.

Le projet est tenu par une personne : ces délais sont ceux d'un engagement de bonne foi, pas d'un service d'astreinte.

## Divulgation coordonnée

Merci de laisser le temps de corriger avant toute publication ; une fois le correctif publié, vous pouvez décrire la faille, et vous êtes crédité si vous le souhaitez. Une recherche de bonne foi, menée sur votre propre installation et dans ce cadre, ne donnera lieu à aucune poursuite de la part du projet.

## Ce qui compte comme faille

Par exemple : une écriture ou une suppression hors du périmètre déclaré, une modification de boîte mail ou de machine distante, un secret (mot de passe, jeton, secret du client OAuth2) qui atteint un journal, un rapport, la sortie ou un fichier lisible par d'autres, un nom de fichier ou de pièce jointe qui fait exécuter une commande ou sortir d'un répertoire, un document écrit dans un coffre non monté.

## Hors périmètre

- les forks et copies non officiels ;
- les versions antérieures à la dernière publiée ;
- la configuration de l'utilisateur : un coffre non chiffré, un `config.json` lisible par tous, un accès `ssh` ouvert par trop de clés ;
- Ollama, les modèles de langage, `ssh`, les serveurs IMAP et les services de Google, qui ont leurs propres canaux de signalement ;
- une mauvaise classification par un modèle : c'est une limite connue (le document va en `À_VÉRIFIER/` et `--rollback` le remet en place), pas une faille.
