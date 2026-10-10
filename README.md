# Skrivagner

Skrivagner (Breton for "scribe") is a sovereign tool that collects, analyses and
sorts personal administrative documents (invoices, letters, contracts, notices)
from local and remote directories into a normalised tree, and keeps a traceable
journal of everything it does. No data leaves the machines: no third-party
service, no remote model, no cloud.

Status: early development. The entry point, the configuration and the local
scanner are in place (`skrivagner.py`, `modules/`, `tests/`).

## Credits

Skrivagner is the result of a human-LLM collaboration, with the roles written
down as they were actually played. The full list is in [CONTRIBUTORS.md](CONTRIBUTORS.md).

*   **Ronan Davalan** — Architect and arbiter: vision, decisions, scope, validation. Sole git author.
*   **Claude Code (Anthropic)** — Implementation engineer: Python code of the first two phases and its tests, project framework and documentation.
*   **Gemini (Google)** — Design advisor: proposed the original name "Le Greffier".
*   **Copilot (Microsoft)** — Translated that name into Breton, giving "Skrivagner".
