# Acknowledgements and contributors

Dibab would not exist without the people and the models that worked on it. The roles are written as they were held, rather than a vague line about "AI assistance". This list is updated the day someone contributes, not at publication.

## Design and development

*   **Ronan Davalan**: architect and arbiter. Vision, scope, validation; every architecture decision goes through him. Sole git author.
*   **Claude Code (Anthropic)**: implementation engineer. Author of the Python code (entry point, configuration, local, ssh and IMAP scanners, Google OAuth2, extraction and OCR, classification cascade, subject of each document and reason for a document to check, content-based name in the check folder, safe move, journal, rollback, rotation, installation and diagnosis, messages in four languages) and of its tests, and of the public documents (the README and its translations, the manual page, CONTRIBUTING.md, SECURITY.md, the user manual in English, French, German and Spanish) and of the Debian package and of its validation in containers. Models: Opus 4.7, then Sonnet 5.5 and Opus 5.5.
*   **Gemini (Google)**: design adviser. Proposed the original name "Le Greffier" and validated the final name with Ronan, then discussed the name Dibab with him.
*   **Copilot (Microsoft)**: translated "Greffier" into Breton, hence "Skrivagner".
*   **Muse Spark 1.3 (Meta)**: name ideation. Raised the "dibab" axis ("to choose" in Breton), hence the name Dibab.

## Projects and libraries

*   **[Python](https://www.python.org/)**: the standard library alone for the code; **[pytest](https://pytest.org/)** for the tests.
*   **[Ollama](https://ollama.com/)**: local execution of the language models, called over HTTP.
*   **[poppler](https://poppler.freedesktop.org/)** (`pdftotext`, `pdftoppm`): text and images of the PDFs, called as external programs.

## Outside contributions

People who contribute through a pull request or a report are added here with the role they held.

*(No outside contribution so far.)*
