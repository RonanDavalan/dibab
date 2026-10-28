# Remerciements et contributeurs

Skrivagner n'existerait pas sans les personnes et les modèles qui y ont travaillé. Les rôles sont écrits tels qu'ils ont été tenus, plutôt qu'une ligne vague sur une « assistance par IA ». Cette liste se met à jour le jour où quelqu'un contribue, pas à la publication.

## Conception et développement

*   **Ronan Davalan** : architecte et arbitre. Vision, périmètre, validation ; toutes les décisions d'architecture passent par lui. Seul auteur git.
*   **Claude Code (Anthropic)** : ingénieur de réalisation. Auteur du code Python (point d'entrée, configuration, scanners local, ssh et IMAP, OAuth2 Google, extraction et OCR, cascade de classification, déplacement sûr, journal, rollback, rotation) et de ses tests. Modèles : Opus 4.7 puis Sonnet 5.5.
*   **Gemini (Google)** : conseiller de conception. A proposé le nom d'origine « Le Greffier » et validé le nom définitif avec Ronan.
*   **Copilot (Microsoft)** : a traduit « Greffier » en breton, d'où « Skrivagner ».

## Projets et bibliothèques

*   **[Python](https://www.python.org/)** : bibliothèque standard seule pour le code ; **[pytest](https://pytest.org/)** pour les tests.
*   **[Ollama](https://ollama.com/)** : exécution locale des modèles de langage, appelée en HTTP.
*   **[poppler](https://poppler.freedesktop.org/)** (`pdftotext`, `pdftoppm`) : texte et images des PDF, appelés comme programmes externes.

## Contributions extérieures

Les personnes qui contribuent par une demande de fusion ou un signalement sont ajoutées ici avec le rôle qu'elles ont tenu.

*(Aucune contribution extérieure pour l'instant.)*
