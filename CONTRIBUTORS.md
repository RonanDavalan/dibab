# Acknowledgements and contributors

Dibab would not exist without the people and the models that worked on it. The roles are written as they were held, rather than a vague line about "AI assistance". This list is updated the day someone contributes, not at publication.

## Design and development

*   **Ronan Davalan**: architect and arbiter. Vision, scope, validation; every architecture decision goes through him. Sole git author.
*   **Claude Code (Anthropic)**: implementation engineer. Author of the Python code (entry point, configuration, local, ssh and IMAP scanners, Google OAuth2, extraction and OCR, classification cascade, subject of each document and reason for a document to check, content-based name in the check folder, safe move, journal, rollback, rotation, installation and diagnosis, messages in four languages) and of its tests, and of the public documents (the README and its translations, the manual page, CONTRIBUTING.md, SECURITY.md, the user manual in English, French, German and Spanish) and of the Debian package `dibab` (`dibab_0.9.0-alpha_all.deb`) and of its validation in containers on Debian 12 and 13 and on Ubuntu 22.04 and 24.04, and of the logo, its favicon and its variants, and of the website (theme, layout and texts). Models: Opus 4.7, then Sonnet 5.5 and Opus 5.5.
*   **Gemini (Google)**: design adviser. Proposed the original name "Le Greffier" and validated the final name with Ronan Davalan, then discussed the name Dibab with him. Logo studies (Gemini 4 Hydrogen) that preceded the adopted drawing.
*   **Copilot (Microsoft)**: translated "Greffier" into Breton, hence "Skrivagner".
*   **Muse Spark 1.3 (Meta)**: name ideation. Raised the "dibab" axis ("to choose" in Breton), hence the name Dibab. Logo studies that preceded the adopted drawing.
*   **DeepSeek V4.1 Flash (DeepSeek)**: tester and reviewer. Discovery testing of the installation, the documentation, the daily use and the website, whose reports led to fixes; checks of the change of name and of the translated website; generic names in the documentation, the website, the README and the tests; drafts of the release notes and of the announcement visuals; early icon studies.
*   **GLM-5.3-Flash (Z.ai)**: early icon studies.

## Projects and libraries

*   **[Python](https://www.python.org/)**: the standard library alone for the code; **[pytest](https://pytest.org/)** for the tests.
*   **[Ollama](https://ollama.com/)**: local execution of the language models, called over HTTP.
*   **[poppler](https://poppler.freedesktop.org/)** (`pdftotext`, `pdftoppm`): text and images of the PDFs, called as external programs.

## Outside contributions

People who contribute through a pull request or a report are added here with the role they held.

*(No outside contribution so far.)*
