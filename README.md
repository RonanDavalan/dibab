# Dibab

<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="https://dibab.davalan.fr/images/logo-sombre.svg">
    <img src="https://dibab.davalan.fr/images/logo-clair.svg" alt="Dibab logo" width="320">
  </picture>
</p>

<p align="center">
  <a href="LICENSE"><img src="https://img.shields.io/badge/License-AGPL_v3-blue.svg" alt="License: AGPL v3"></a>
  <img src="https://img.shields.io/badge/Version-0.9.1--alpha-yellow.svg" alt="Version: 0.9.1-alpha">
  <img src="https://img.shields.io/badge/python-3.10+-blue.svg" alt="Python 3.10+">
  <img src="https://img.shields.io/badge/Linux-Debian_%C2%B7_Ubuntu-blue.svg" alt="Debian and Ubuntu">
</p>

**English** | [Français](docs/fr-FR/README.md) | [Deutsch](docs/de-DE/README.md) | [Español](docs/es-ES/README.md) | [中文](docs/zh-CN/README.md)

Dibab ("to choose" in Breton) collects, analyses and files the personal administrative documents of a household (invoices, letters, contracts, notices from public bodies) into a normalised tree, and keeps a journal of everything it does. It runs in sovereign mode: no document and no text of a document leaves the local network, with no remote model and no cloud. The only connections to the outside are the ones you declare: the IMAP mailbox that Dibab reads, and Google's OAuth2 consent when that mailbox is a Google account. The language models are those of [Ollama](https://ollama.com/), on your own machine.

Licence: [GNU Affero General Public License version 3](LICENSE).

## What Dibab does, and what it does not

It does:

- scan local directories, remote machines over `ssh` (copy checked by fingerprint, original files left intact) and mailboxes over read-only IMAP (attachments are dropped into a "drop folder"; the mailbox is not modified);
- extract the text (the text layer of the PDF, otherwise a reading by a vision model), sort the administrative documents from the others, then file them by category and by domain (personal or professional) with a consensus of several models;
- rename and move each document into the vault of its domain, with a timestamped journal and the possibility to undo it (`--rollback`).

It does not:

- move a file it is not sure about: doubt leads to a `TO_CHECK/` folder, never to a risky filing;
- delete a document: it moves and copies, it does not erase (it only prunes its own old journals, chapter 8, "Inventory and rotation", of the PDF manual);
- modify a mailbox or a remote machine;
- run in the background: you start it by hand, and the default mode is the simulation (`--dry-run`);
- mount, encrypt or synchronise a vault: that is up to you (see "Limits").

## A tool for a household

Dibab is designed for the administrative life of a household, by the household. A machine, a directory or a mail account enters the scope only with the agreement, explicit or implicit, of the person concerned; when in doubt, leave it out. The software cannot guarantee this respect: the administrator of the instance commits to it. The session journal holds the subject, the sender, the category, the person and the date of each document, which already reveal a lot (a letter from a health body is enough): it belongs in the vault, not beside it: put the three `suivi.*` keys inside the vault to keep it there, otherwise it is written in clear under `~/.local/state/dibab/`.

## Requirements

- Linux with Python 3.10 or later (the tests pass on 3.12 and 3.13); the code uses only the standard library;
- `findmnt` (package `util-linux`) and `git`;
- `pdftotext` and `pdftoppm` (package `poppler-utils`);
- [Ollama](https://ollama.com/) installed and running, with at least one model per role;
- for remote machines: `ssh` with a key that opens a session without a password;
- one destination directory per domain, preferably on an encrypted volume.

On Debian:

```bash
sudo apt install python3 python3-venv git util-linux poppler-utils openssh-client
```

The models, by role (`ocr` reads scanned pages, `tri_rapide` sets aside what is not administrative, `classification` files):

```bash
ollama pull glm-ocr
ollama pull mistral-nemo:12b-instruct-2407-q6_K
ollama pull gemma4
ollama pull gemma3:4b
ollama pull qwen2.5
ollama pull granite4.2:8b-Q5_K_M
```

These models are those of the reference instance; any others will do, you only have to name them in `ollama.roles` (below). The models of the `classification` role vote: a document is filed only if their agreement reaches `ollama.seuil_confiance`. Ollama is not part of Dibab and is never installed by it.

## Installation from the Debian package

On Debian 12 and 13 and on Ubuntu 22.04 and 24.04, one file installs the program and its dependencies (`python3`, `poppler-utils`, `util-linux`, `openssh-client`). It contains neither Ollama, nor a model, nor a configuration. Download `dibab_*_all.deb` from the download page of [dibab.davalan.fr](https://dibab.davalan.fr/), then, from the folder that holds it:

```bash
sudo apt install ./dibab_*_all.deb
```

Write the configuration, in the language of your session, then follow steps 4 and 5 of the installation from the sources below (the vault of each domain, the keys of the configuration):

```bash
dibab --initialiser
```

`--initialiser` writes the configuration in the language of your session: the check folder, its prefix and the duplicate folder take the names of that language. It creates the file with mode `600` in a folder with mode `700` and never rewrites a file that already exists; a later session in another language does not rename them.

Check the installation, without writing anything:

```bash
dibab --version
dibab --diagnose
```

The package puts the command in `/usr/bin/dibab`, the program in `/usr/lib/dibab/`, and the README files, the example configuration and the manual page (`man dibab`, in five languages) under `/usr/share/`. Removing it keeps your data: `sudo apt remove dibab` and `sudo apt purge dibab` delete the files of the package and never touch your configuration, your state, your journal or your documents; the purge names what it leaves.

Level: installation and diagnostic validated in a container on Debian 12 and 13 and on Ubuntu 22.04 and 24.04 (installation, `--version`, `--diagnose`, the refusal to write without a configuration and the refusal to write into a vault that is not mounted, a simulated filing, removal and purge). A container shows neither the mounting of an encrypted vault nor a run with your own Ollama and your own documents.

## Installation from the sources

Final tree (`~` is your home directory; adapt the paths to your installation):

```
~/applications/dibab/               the cloned repository
├── dibab.py                        the entry point
├── modules/                             one file per responsibility
│   └── langues/                         the message dictionaries: en, fr, de, es, zh
├── docs/                                the translations of this README and the manual page
├── tests/                               the tests
├── config.exemple.json                  the example configuration, versioned
└── venv/                                the Python environment, created at step 2
~/.config/dibab/config.json         your configuration, created at step 3, never versioned
~/.local/state/dibab/               the state, the journal and the session reports (default location)
~/Classement/Personnel/                  the vault of the personal domain
~/Classement/Professionnel/              the vault of the professional domain
```

1. Clone the repository:

```bash
mkdir -p ~/applications && git clone https://github.com/RonanDavalan/dibab.git ~/applications/dibab
cd ~/applications/dibab
```

2. Create the Python environment and check the tests (expected: `581 passed, 9 skipped`; the 9 skipped are the trials against a running Ollama):

```bash
python3 -m venv venv
venv/bin/pip install -r requirements-dev.txt
venv/bin/python -m pytest -q tests
```

3. Write the configuration in the language of your session. Dibab reads the first file found among: the `--config <path>` option, the `DIBAB_CONFIG` environment variable, `~/.config/dibab/config.json` (or `$XDG_CONFIG_HOME/dibab/config.json`), then `config.json` next to `dibab.py`. An option or a variable that names a missing file stops the program: it never falls back on another file.

```bash
venv/bin/python dibab.py --initialiser
```

`--initialiser` writes the configuration in the language of your session: the check folder, its prefix and the duplicate folder take the names of that language. It creates the file with mode `600` in a folder with mode `700` and never rewrites a file that already exists; a later session in another language does not rename them.

4. Create the vault of each domain and read the type of its file system:

```bash
mkdir -p ~/Classement/Personnel ~/Classement/Professionnel
findmnt -n -T ~/Classement/Personnel -o FSTYPE
```

The command prints for instance `ext4`. Before every write, Dibab proves that the root of each vault is mounted, because a closed vault leaves a bare folder on the disk in clear: it compares this type with `systemes_fichiers_acceptes`. The example expects `fuse.gocryptfs`. If you encrypt differently (LUKS, eCryptfs...), open the volume and write the type that `findmnt` returns for it. On an unencrypted volume this check no longer tells an absent mount from a present one: you then give up this protection.

5. Edit `~/.config/dibab/config.json`, these keys at least:

| Key | Role |
|---|---|
| `destinations.personnel.racine` and `destinations.professionnel.racine` | the vault of each domain, here `~/Classement/Personnel` and `~/Classement/Professionnel` |
| `destinations.*.systemes_fichiers_acceptes` | the type read at step 4 |
| `personnes` | the first names of the household, which name the folders of the personal domain |
| `sources_locales[].chemin` | the directories to scan |
| `suivi.fichier_date`, `suivi.journal`, `suivi.sessions` | when absent, the state is written in clear under `~/.local/state/dibab/` (or `$XDG_STATE_HOME/dibab/`); to encrypt it, add these three keys inside the vault (for instance `~/Classement/Personnel/logs/...`): the journal is sensitive data |
| `ollama.roles` | for each role, the preferred models in order; the first one installed is kept |

The complete list of keys and their effect: read `config.exemple.json`, each block of which is a realistic example. Passwords never go in it.

6. Check the installation, without writing anything:

```bash
venv/bin/python dibab.py --version
venv/bin/python dibab.py --diagnose
```

`--version` prints one line and stops:

```
dibab 0.9.0-alpha
```

`--diagnose` prints one line per check, `<STATE> <identifier> : <message>`, then a summary. In a new home directory, with no configuration and no Ollama, the output is the following and the exit code is `0`:

```
OK python : 3.13.5
OK outil_pdftotext : /usr/bin/pdftotext
OK outil_pdftoppm : /usr/bin/pdftoppm
OK outil_findmnt : /usr/bin/findmnt
OK outil_ssh : /usr/bin/ssh
NON_CONFIGURÉ configuration : no configuration found (the --config option: not given; the DIBAB_CONFIG variable: not given; the XDG location: ~/.config/dibab/config.json; the script folder: ~/applications/dibab/config.json)
NON_VÉRIFIÉ emplacement_etat : depends on the configuration
NON_VÉRIFIÉ ollama : depends on the configuration
NON_VÉRIFIÉ modele_ocr : depends on the configuration
NON_VÉRIFIÉ modele_tri_rapide : depends on the configuration
NON_VÉRIFIÉ modele_classification : depends on the configuration
NON_VÉRIFIÉ modele_tri_decision : depends on the configuration
NON_VÉRIFIÉ destination_personnel : depends on the configuration
NON_VÉRIFIÉ destination_professionnel : depends on the configuration
Diagnostic: 5 OK, 0 warning(s), 0 failure(s), 1 not configured, 8 not checked
```

The paths in this example are those of an installation from the sources. Installed from the package, the script folder is `/usr/lib/dibab/` and `~` is your own home directory.

The state tokens (`OK`, `AVERTISSEMENT`, `ÉCHEC`, `NON_CONFIGURÉ`, `NON_VÉRIFIÉ`) and the identifiers are the same in every language, so that a script can compare them. Once the configuration is written, everything it declares and the machine does not hold (Ollama off, a model missing, a vault not mounted) is an `ÉCHEC` and the exit code is `1`. With the configuration of step 5 filled in and each vault mounted, the output ends on a summary like this one:

```
Diagnostic: 12 OK, 1 warning(s), 0 failure(s), 1 not configured, 0 not checked
```

With the configuration used here the diagnostic gives one warning: the state and the journal in clear text under `~/.local/state/dibab/`, until you move them into a vault. The decision triage (`ollama.roles.tri_decision`) stays `NON_CONFIGURÉ` as long as you do not declare it and Ollama answers: the triage then goes through `tri_rapide`. When Ollama does not answer, it is `NON_VÉRIFIÉ` like the other models, and the three failures of that run are Ollama and the two vault folders.

## Language of the messages

Dibab writes its messages in English, French, German, Spanish or Simplified Chinese. The language is read once at start, in the first of `LC_ALL`, `LC_MESSAGES` and `LANG` that is not empty: `fr_FR.UTF-8` gives French, `de_DE.UTF-8` German, `es_ES.UTF-8` Spanish, any `zh_*` locale such as `zh_CN.UTF-8` Simplified Chinese, `en_US.UTF-8` English, and any other value, or none, English. To read the same check in another language:

```bash
LC_ALL=fr_FR.UTF-8 venv/bin/python dibab.py --diagnose
```

The option names, the state tokens, the identifiers, the journals and the plan files never change with the language: what is written on disk does not depend on it, so that a journal written in one language is replayed by `--rollback` in any other: the keys of the journals and the plan files (`evenement`, `horodatage`…) and the values that name an event or a category (`session_demarree`, `administratif`…) are fixed technical identifiers, written in French. The message dictionaries are the files `modules/langues/en.txt`, `fr.txt`, `de.txt`, `es.txt` and `zh.txt`.

The names of the check folder, its prefix and the duplicate folder are written at initialisation in the language of the session; `sous_repertoire_a_verifier`, `nommage.prefixe_a_verifier` and `destination.repertoire_doublon` set them, and a later session in another language does not rename them.

## Usage

```bash
cd ~/applications/dibab
venv/bin/python dibab.py --dry-run     # simulation (default): nothing moves
venv/bin/python dibab.py --execute     # real filing
venv/bin/python dibab.py --rollback    # undoes the last filing session
venv/bin/python dibab.py --inventaire  # reads what each vault already holds, nothing is moved
venv/bin/python dibab.py --diagnose    # checks the installation, the configuration, Ollama and the vault of each domain, writes nothing
venv/bin/python dibab.py --version     # prints one line, `dibab <version>`, and stops
venv/bin/python dibab.py --dry-run --config ~/other/config.json   # reads that configuration
venv/bin/python dibab.py --help        # lists every option, in the language of the session
```

Always start with `--dry-run`, read each proposed destination, then run `--execute`. The first pass is slow (several models read each document); the error output shows the progress, `model i/n, document j/m`. Here is a `--dry-run` on an empty source folder, which needs Ollama and the three models of the roles:

```
Dibab 0.9.0-alpha — session 2026-11-25T23:54:23
  Mode               : dry-run
  Configuration      : ~/.config/dibab/config.json
  Vault personnel     : ~/Classement/Personnel — mounted
  Vault professionnel : ~/Classement/Professionnel — mounted
  Session journal    : ~/.local/state/dibab/sessions/session_2026-11-25T23:54:23.jsonl
  Model ocr           : glm-ocr:latest
  Model tri_rapide    : gemma3:4b
  Model classification: granite4.2:8b-Q5_K_M
  Consensus          : 1 classification model(s), threshold 0.4

Source: entrant (~/Classement/Entrant)
  (no candidate file)
  Source total: 0 file(s), 0 B

============================================================
Scan total: 0 candidate file(s), 0 B
============================================================
Text extraction (the text is neither shown nor written)

Classification (dry-run, nothing is moved; the text is neither shown nor written)
```

Exit codes:

| Code | Meaning |
|---|---|
| `0` | success |
| `1` | configuration not found, invalid or missing a key; at least one source or document in failure; rollback only partly done; OAuth2 consent failed; `--diagnose` with at least one `ÉCHEC` |
| `2` | vault not proven mounted before a mode that writes; invalid command line |
| `3` | no model installed for a role (`ollama list`), or Ollama does not answer |
| `4` | `--execute` refused on this machine (key `executer_sur`) |
| `5` | another run holds the lock `dibab.verrou` (next to `suivi.fichier_date`) |

Every move is written in the action journal (`suivi.journal`, one JSON line per action, no document text) and every session leaves a report in `suivi.sessions`. `--rollback --session <timestamp>` undoes a given session: the document returns to its original place, the copy checked by fingerprint.

A document whose fingerprint is already filed is copied to the `duplicate/` folder at the root of the vault, checked, then removed from the source, like a filed document; emptying that folder is up to you. A run refused because another one holds the lock leaves a `session_refusee` line in its session journal.

### Manual page

The manual page is written in Markdown in `docs/dibab.1.md`, with its translations in `docs/fr-FR/`, `docs/de-DE/`, `docs/es-ES/` and `docs/zh-CN/`. To read it from the sources:

```bash
pandoc --standalone --from markdown-smart --to man docs/dibab.1.md | man -l -
```

### Remote machines over ssh

Declare each machine in `sources_distantes` (`ssh` alias, directories, `vide_poches_destination`). `ssh <alias> true` must succeed without a password, and the machine must offer `find`, `sha256sum` and `cat`. In simulation, Dibab lists the files without copying anything; in execution, it copies them into the drop folder of the machine, checks their fingerprint, then treats them as local files. The original files stay intact. A refused connection stops the machine concerned: do not retry in a loop.

### Mailboxes over IMAP

Declare each mailbox in `sources_imap`. The password is read from the environment variable named by `mot_de_passe_env`, never from the file:

```bash
read -rs DIBAB_IMAP_EXEMPLE && export DIBAB_IMAP_EXEMPLE
```

Dibab opens the folders read-only (`EXAMINE`) and reads only the attachment (`BODY.PEEK`): no message is marked as read, no flag is set.

### Google accounts over OAuth2

A Google account is read with an OAuth2 token instead of the password (`AUTHENTICATE XOAUTH2`). In the [Google Cloud console](https://console.cloud.google.com), with the account to read: create a project, enable the Gmail API, configure the OAuth consent screen (external type), then **publish** it (status "In production", because in "Testing" the authorisation expires after seven days), and finally create a "Desktop application" credential and download its JSON. Keep it in the vault, with mode `600`, then declare the source with `"authentification": "oauth2"`, `client_fichier` and `token_fichier` (see the `imap-google-exemple` example) and consent once:

```bash
venv/bin/python dibab.py --autoriser-google imap-google-exemple
```

Open the address that is printed in a browser, accept the "unverified application" warning (it is your own application) and the consent. The token is written with mode `600` in the folder of the `token_fichier`, which refuses a git repository and the paths of `oauth2.chemins_interdits`; it renews itself and appears neither in the journal nor on screen. If Google revokes it (access removed, account password changed, six months without a scan), Dibab stops with an explicit message: run the command again.

## Sovereignty

- The calls to Ollama are HTTP requests to `ollama.url` (by default `http://localhost:11434`); no document and no file name goes anywhere else.
- The only outside services the code can reach are those you declare: your machines over `ssh`, your IMAP mailboxes and, if you enable OAuth2, the authorisation endpoints of Google.
- No secret is stored in `config.json`: passwords in an environment variable, tokens in `600` files outside any repository.

## Limits

- Linux only. The mount check relies on `findmnt`.
- The filing is worth what your models are worth: on the reference instance, a first trial on 15 real documents filed 2, set 3 aside as not administrative and put 10 in `TO_CHECK/`, as a matter of caution. Measure before trusting: the domain measurement is in `_outils/mesurer_domaines.py`.
- Dibab does not mount, encrypt or synchronise any vault, and erases no document: disk space and backups are up to you.
- The categories and the known senders of `config.exemple.json` are generic; adapt them to your country.
- The steps in the Google console depend on Google's interface, which changes: the notions remain those of its OAuth2 documentation.
- The project is young: version 0.9.1-alpha, no continuous integration.

## Contributing, reporting a vulnerability

See [CONTRIBUTING.md](CONTRIBUTING.md). A vulnerability is reported in private according to [SECURITY.md](SECURITY.md), never in a public issue.

## Credits

Dibab is the fruit of a collaboration between a person and language models, with the roles written as they were held. The complete list is in [CONTRIBUTORS.md](CONTRIBUTORS.md).

*   **Ronan Davalan**: architect and arbiter; vision, decisions, scope, validation. Sole git author.
*   **Claude Code (Anthropic)**: implementation engineer; Python code and tests, and the public documents (this README and its translations, the manual page, `CONTRIBUTING.md`, `SECURITY.md`), and the logo and the website (graphic design, layout and texts).
*   **Gemini (Google)**: design adviser; proposed the original name "Le Greffier" and discussed the name Dibab with Ronan Davalan; logo studies.
*   **Muse Spark 1.3 (Meta)**: name ideation; raised the "dibab" axis ("to choose" in Breton), hence the name Dibab; logo studies.
*   **DeepSeek V4.1 Flash (DeepSeek)**: tester and reviewer; discovery testing whose reports led to fixes, checks of the renaming and of the translated website, generic names in the documentation and examples, drafts of the release notes and of the announcement visuals, early icon studies.
*   **GLM-5.3-Flash (Z.ai)**: early icon studies.
