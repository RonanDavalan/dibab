# Contributing to Dibab

Thank you for your interest. Dibab files sensitive administrative documents: caution comes before speed, and every contribution is judged first on what it must not risk breaking.

## Before writing code

- Open an issue that describes the need before a large change (a new source, a new visible behaviour). A defect fix or a documentation fix can arrive directly as a pull request.
- A security flaw is never reported in an issue: see [SECURITY.md](SECURITY.md).
- Dibab stays a sovereign household tool: no third-party service, no remote model, no telemetry, no "cloud" mode. A contribution that introduces them will be refused.

## Environment

```bash
git clone https://github.com/RonanDavalan/dibab.git ~/applications/dibab
cd ~/applications/dibab
python3 -m venv venv
venv/bin/pip install -r requirements-dev.txt
venv/bin/python -m pytest -q tests
```

The tests touch neither Ollama, nor `ssh`, nor IMAP, nor Google: they use fake servers and fictitious documents (`tests/faux_imap.py`, `tests/faux_ssh.py`, `tests/textes_factices.py`). The tests marked `ollama_reel` are skipped as long as `DIBAB_MODELE_OCR_ESSAI` does not name an installed model.

## The rules of the code

- **Standard library only** for the code (`ssh` through `subprocess`, Ollama through `urllib`). A new dependency is justified in the pull request.
- **Simulation by default**: every new gesture that writes or moves is inactive in `--dry-run` and leaves a trace in the action journal, so that `--rollback` can undo it.
- **Never any deletion**, never any write into a mailbox or onto a remote machine.
- **No secret in a versioned file, a journal, a report or an output**: passwords in an environment variable, tokens in a `600` file. A test proves it for every new secret.
- **No real document, no name of a person, of a host or of a personal path** in the code, the tests, the examples, the issues and the screenshots. The tests use fictitious texts.
- **Every behaviour has its test**, the failure case included; a fixed defect gets the test that would have caught it. The new tests fail without the change they cover.
- **Every text the tool shows lives in the message dictionaries** (`modules/langues/en.txt`, `fr.txt`, `de.txt` and `es.txt`), read through `traduire("key", name=value)`, never written in the code. A new message is added to the four dictionaries, with the same names between braces in each; `tests/test_messages.py` fails otherwise. English is the source, the other three are translated from it. What is written in a journal or a plan is composed in English.
- **Comments in French, about the why only**: the intention, the constraint, the trap that would surprise a competent reader. Neither the obvious, nor the history of the edit ("added", "fixed"). French is written with its accents.
- **The keys of `config.json` are never renamed**: add a key, with a default value that keeps the existing behaviour, and document it in `config.exemple.json` and the `README.md`.

## Pull request

1. One branch per subject, commits that say what they change.
2. `venv/bin/python -m pytest -q tests` passes in full.
3. `git grep -nE '/hom[e]/|@gmai[l]|ssh -'` finds nothing personal in what you add.
4. The `README.md` (and its translations in `docs/`) and `config.exemple.json` are up to date if the visible behaviour or the configuration changes.

By contributing, you agree that your contribution is published under the licence of the project, the [GNU Affero General Public License version 3](LICENSE). Your name and the role you held are added to [CONTRIBUTORS.md](CONTRIBUTORS.md) on the day of the merge.
