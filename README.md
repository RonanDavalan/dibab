# Skrivagner

**English** | [Français](docs/fr-FR/README.md) | [Deutsch](docs/de-DE/README.md) | [Español](docs/es-ES/README.md)

Skrivagner ("scribe" in Breton) collects, analyses and files the personal administrative documents of a household (invoices, letters, contracts, notices from public bodies) into a normalised tree, and keeps a journal of everything it does. It runs in sovereign mode: no data leaves the local network, with no third-party service, no remote model and no cloud. The language models are those of [Ollama](https://ollama.com/), on your own machine.

Licence: [GNU Affero General Public License version 3](LICENSE).

## What Skrivagner does, and what it does not

It does:

- scan local directories, remote machines over `ssh` (copy checked by fingerprint, original files left intact) and mailboxes over read-only IMAP (attachments are dropped into a "drop folder"; the mailbox is not modified);
- extract the text (the text layer of the PDF, otherwise a reading by a vision model), sort the administrative documents from the others, then file them by category and by domain (personal or professional) with a consensus of several models;
- rename and move each document into the vault of its domain, with a timestamped journal and the possibility to undo it (`--rollback`).

It does not:

- move a file it is not sure about: doubt leads to a `À_VÉRIFIER/` folder, never to a risky filing;
- delete a document: it moves and copies, it does not erase (it only prunes its own old journals, chapter "Inventory and rotation" of the manual);
- modify a mailbox or a remote machine;
- run in the background: you start it by hand, and the default mode is the simulation (`--dry-run`);
- mount, encrypt or synchronise a vault: that is up to you (see "Limits").

## A tool for a household

Skrivagner is designed for the administrative life of a household, by the household. A machine, a directory or a mail account enters the scope only with the agreement, explicit or implicit, of the person concerned; when in doubt, leave it out. The software cannot guarantee this respect: the administrator of the instance commits to it. The journal holds file names and senders, which already reveal a lot (a letter from a health body is enough): it lives in the vault, not beside it.

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
ollama pull gemma3:4b
ollama pull qwen2.5:3b
ollama pull gemma4:e2b
ollama pull qwen2.5
ollama pull granite4.2:8b-Q5_K_M
ollama pull mistral-nemo:12b-instruct-2407-q6_K
```

These models are those of the reference instance; any others will do, you only have to name them in `ollama.roles` (below). The models of the `classification` role vote: a document is filed only if their agreement reaches `ollama.seuil_confiance`. Ollama is not part of Skrivagner and is never installed by it.

## Installation from the Debian package

On Debian 12 and 13 and on Ubuntu 22.04 and 24.04, one file installs the program and its dependencies (`python3`, `poppler-utils`, `util-linux`, `openssh-client`). It contains neither Ollama, nor a model, nor a configuration. Download `skrivagner_*_all.deb` from the download page of [skrivagner.davalan.fr](https://skrivagner.davalan.fr/), then, from the folder that holds it:

```bash
sudo apt install ./skrivagner_*_all.deb
```

Create the configuration from the example that the package installs, with mode `600`, then follow steps 4 and 5 of the installation from the sources below (the vault of each domain, the keys of the configuration):

```bash
mkdir -p ~/.config/skrivagner
cp /usr/share/doc/skrivagner/examples/config.exemple.json ~/.config/skrivagner/config.json
chmod 600 ~/.config/skrivagner/config.json
```

Check the installation, without writing anything:

```bash
skrivagner --version
skrivagner --diagnose
```

The package puts the command in `/usr/bin/skrivagner`, the program in `/usr/lib/skrivagner/`, and the README files, the example configuration and the manual page (`man skrivagner`, in four languages) under `/usr/share/`. Removing it keeps your data: `sudo apt remove skrivagner` and `sudo apt purge skrivagner` delete the files of the package and never touch your configuration, your state, your journal or your documents; the purge names what it leaves.

Level: installation and diagnostic validated in a container on Debian 12 and 13 and on Ubuntu 22.04 and 24.04 (installation, `--version`, `--diagnose`, the refusal to write without a configuration and the refusal to write into a vault that is not mounted, a simulated filing, removal and purge). A container shows neither the mounting of an encrypted vault nor a run with your own Ollama and your own documents.

## Installation from the sources

Final tree (`~` is your home directory; adapt the paths to your installation):

```
~/applications/skrivagner/               the cloned repository
├── skrivagner.py                        the entry point
├── modules/                             one file per responsibility
│   └── langues/                         the message dictionaries: en, fr, de, es
├── docs/                                the translations of this README and the manual page
├── tests/                               the tests
├── config.exemple.json                  the example configuration, versioned
└── venv/                                the Python environment, created at step 2
~/.config/skrivagner/config.json         your configuration, created at step 3, never versioned
~/.local/state/skrivagner/               the state, the journal and the session reports (default location)
~/Classement/Personnel/                  the vault of the personal domain
~/Classement/Professionnel/              the vault of the professional domain
```

1. Clone the repository:

```bash
mkdir -p ~/applications && git clone https://github.com/RonanDavalan/skrivagner.git ~/applications/skrivagner
cd ~/applications/skrivagner
```

2. Create the Python environment and check the tests (expected: `459 passed, 8 skipped`; the 8 skipped are the trials against a running Ollama):

```bash
python3 -m venv venv
venv/bin/pip install -r requirements-dev.txt
venv/bin/python -m pytest -q tests
```

3. Create the configuration, with mode `600`. Skrivagner reads the first file found among: the `--config <path>` option, the `SKRIVAGNER_CONFIG` environment variable, `~/.config/skrivagner/config.json` (or `$XDG_CONFIG_HOME/skrivagner/config.json`), then `config.json` next to `skrivagner.py`. An option or a variable that names a missing file stops the program: it never falls back on another file.

```bash
mkdir -p ~/.config/skrivagner
cp config.exemple.json ~/.config/skrivagner/config.json
chmod 600 ~/.config/skrivagner/config.json
```

4. Create the vault of each domain and read the type of its file system:

```bash
mkdir -p ~/Classement/Personnel ~/Classement/Professionnel
findmnt -n -T ~/Classement/Personnel -o FSTYPE
```

The command prints for instance `ext4`. Before every write, Skrivagner proves that the root of each vault is mounted, because a closed vault leaves a bare folder on the disk in clear: it compares this type with `systemes_fichiers_acceptes`. The example expects `fuse.gocryptfs`. If you encrypt differently (LUKS, eCryptfs...), open the volume and write the type that `findmnt` returns for it. On an unencrypted volume this check no longer tells an absent mount from a present one: you then give up this protection.

5. Edit `~/.config/skrivagner/config.json`, these keys at least:

| Key | Role |
|---|---|
| `destinations.personnel.racine` and `destinations.professionnel.racine` | the vault of each domain, here `~/Classement/Personnel` and `~/Classement/Professionnel` |
| `destinations.*.systemes_fichiers_acceptes` | the type read at step 4 |
| `personnes` | the first names of the household, which name the folders of the personal domain |
| `sources_locales[].chemin` | the directories to scan |
| `suivi.fichier_date`, `suivi.journal`, `suivi.sessions` | when absent, the state is written in clear under `~/.local/state/skrivagner/` (or `$XDG_STATE_HOME/skrivagner/`); to encrypt it, add these three keys inside the vault (for instance `~/Classement/Personnel/logs/...`): the journal is sensitive data |
| `ollama.roles` | for each role, the preferred models in order; the first one installed is kept |

The complete list of keys and their effect: read `config.exemple.json`, each block of which is a realistic example. Passwords never go in it.

6. Check the installation, without writing anything:

```bash
venv/bin/python skrivagner.py --version
venv/bin/python skrivagner.py --diagnose
```

`--version` prints one line and stops:

```
skrivagner 0.9.0-alpha
```

`--diagnose` prints one line per check, `<STATE> <identifier> : <message>`, then a summary. In a new home directory, with no configuration and no Ollama, the output is the following and the exit code is `0`:

```
OK python : 3.13.5
OK outil_pdftotext : /usr/bin/pdftotext
OK outil_pdftoppm : /usr/bin/pdftoppm
OK outil_findmnt : /usr/bin/findmnt
OK outil_ssh : /usr/bin/ssh
NON_CONFIGURÉ configuration : no configuration found (the --config option: not given; the SKRIVAGNER_CONFIG variable: not given; the XDG location: ~/.config/skrivagner/config.json; the script folder: ~/applications/skrivagner/config.json)
NON_VÉRIFIÉ emplacement_etat : depends on the configuration
NON_VÉRIFIÉ ollama : depends on the configuration
NON_VÉRIFIÉ modele_ocr : depends on the configuration
NON_VÉRIFIÉ modele_tri_rapide : depends on the configuration
NON_VÉRIFIÉ modele_classification : depends on the configuration
NON_VÉRIFIÉ destination_personnel : depends on the configuration
NON_VÉRIFIÉ destination_professionnel : depends on the configuration
Diagnostic: 5 OK, 0 warning(s), 0 failure(s), 1 not configured, 7 not checked
```

The state tokens (`OK`, `AVERTISSEMENT`, `ÉCHEC`, `NON_CONFIGURÉ`, `NON_VÉRIFIÉ`) and the identifiers are the same in every language, so that a script can compare them. Once the configuration is written, everything it declares and the machine does not hold (Ollama off, a model missing, a vault not mounted) is an `ÉCHEC` and the exit code is `1`. With the configuration of step 5 filled in and each vault mounted, the output ends on a summary like this one:

```
Diagnostic: 12 OK, 1 warning(s), 0 failure(s), 0 not configured, 0 not checked
```

The one warning is the state and the journal in clear text under `~/.local/state/skrivagner/`, until you move them into a vault.

## Language of the messages

Skrivagner writes its messages in English, French, German or Spanish. The language is read once at start, in the first of `LC_ALL`, `LC_MESSAGES` and `LANG` that is not empty: `fr_FR.UTF-8` gives French, `de_DE.UTF-8` German, `es_ES.UTF-8` Spanish, `en_US.UTF-8` English, and any other value, or none, English. To read the same check in another language:

```bash
LC_ALL=fr_FR.UTF-8 venv/bin/python skrivagner.py --diagnose
```

The option names, the state tokens, the identifiers, the journals and the plan files never change with the language: what is written on disk is in English, so that a journal written in one language is replayed by `--rollback` in any other. The message dictionaries are the files `modules/langues/en.txt`, `fr.txt`, `de.txt` and `es.txt`.

## Usage

```bash
cd ~/applications/skrivagner
venv/bin/python skrivagner.py --dry-run     # simulation (default): nothing moves
venv/bin/python skrivagner.py --execute     # real filing
venv/bin/python skrivagner.py --rollback    # undoes the last filing session
venv/bin/python skrivagner.py --inventaire  # reads what each vault already holds, nothing is moved
venv/bin/python skrivagner.py --diagnose    # checks the installation, the configuration, Ollama and the vault of each domain, writes nothing
venv/bin/python skrivagner.py --version     # prints one line, `skrivagner <version>`, and stops
venv/bin/python skrivagner.py --dry-run --config ~/other/config.json   # reads that configuration
venv/bin/python skrivagner.py --help        # lists every option, in the language of the session
```

Always start with `--dry-run`, read each proposed destination, then run `--execute`. The first pass is slow (several models read each document); the error output shows the progress, `model i/n, document j/m`. Here is a `--dry-run` on an empty source folder, which needs Ollama and the three models of the roles:

```
Skrivagner 0.9.0-alpha — session 2026-10-29T17:33:28
  Mode               : dry-run
  Configuration      : ~/.config/skrivagner/config.json
  Vault personnel     : ~/Classement/Personnel — mounted
  Vault professionnel : ~/Classement/Professionnel — mounted
  Session journal    : ~/.local/state/skrivagner/sessions/session_2026-10-29T17:33:28.jsonl
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
| `5` | another run holds the lock `skrivagner.verrou` (next to `suivi.fichier_date`) |

Every move is written in the action journal (`suivi.journal`, one JSON line per action, no document text) and every session leaves a report in `suivi.sessions`. `--rollback --session <timestamp>` undoes a given session: the document returns to its original place, the copy checked by fingerprint.

### Manual page

The manual page is written in Markdown in `docs/skrivagner.1.md`, with its translations in `docs/fr-FR/`, `docs/de-DE/` and `docs/es-ES/`. To read it from the sources:

```bash
pandoc --standalone --from markdown-smart --to man docs/skrivagner.1.md | man -l -
```

### Remote machines over ssh

Declare each machine in `sources_distantes` (`ssh` alias, directories, `vide_poches_destination`). `ssh <alias> true` must succeed without a password, and the machine must offer `find`, `sha256sum` and `cat`. In simulation, Skrivagner lists the files without copying anything; in execution, it copies them into the drop folder of the machine, checks their fingerprint, then treats them as local files. The original files stay intact. A refused connection stops the machine concerned: do not retry in a loop.

### Mailboxes over IMAP

Declare each mailbox in `sources_imap`. The password is read from the environment variable named by `mot_de_passe_env`, never from the file:

```bash
read -rs SKRIVAGNER_IMAP_EXEMPLE && export SKRIVAGNER_IMAP_EXEMPLE
```

Skrivagner opens the folders read-only (`EXAMINE`) and reads only the attachment (`BODY.PEEK`): no message is marked as read, no flag is set.

### Google accounts over OAuth2

A Google account is read with an OAuth2 token instead of the password (`AUTHENTICATE XOAUTH2`). In the [Google Cloud console](https://console.cloud.google.com), with the account to read: create a project, enable the Gmail API, configure the OAuth consent screen (external type), then **publish** it (status "In production", because in "Testing" the authorisation expires after seven days), and finally create a "Desktop application" credential and download its JSON. Keep it in the vault, with mode `600`, then declare the source with `"authentification": "oauth2"`, `client_fichier` and `token_fichier` (see the `imap-google-exemple` example) and consent once:

```bash
venv/bin/python skrivagner.py --autoriser-google imap-google-exemple
```

Open the address that is printed in a browser, accept the "unverified application" warning (it is your own application) and the consent. The token is written with mode `600` in the folder of the `token_fichier`, which refuses a git repository and the paths of `oauth2.chemins_interdits`; it renews itself and appears neither in the journal nor on screen. If Google revokes it (access removed, account password changed, six months without a scan), Skrivagner stops with an explicit message: run the command again.

## Sovereignty

- The calls to Ollama are HTTP requests to `ollama.url` (by default `http://localhost:11434`); no document and no file name goes anywhere else.
- The only outside services the code can reach are those you declare: your machines over `ssh`, your IMAP mailboxes and, if you enable OAuth2, the authorisation endpoints of Google.
- No secret is stored in `config.json`: passwords in an environment variable, tokens in `600` files outside any repository.

## Limits

- Linux only. The mount check relies on `findmnt`.
- The filing is worth what your models are worth: on the reference instance, a first trial on 15 real documents filed 2, set 3 aside as not administrative and put 10 in `À_VÉRIFIER/`, as a matter of caution. Measure before trusting: the domain measurement is in `_outils/mesurer_domaines.py`.
- Skrivagner does not mount, encrypt or synchronise any vault, and erases no document: disk space and backups are up to you.
- The categories, the known senders and the naming template of `config.exemple.json` reflect French administrative life (family allowance fund, tax office, insurers); adapt them to your country.
- The steps in the Google console depend on Google's interface, which changes: the notions remain those of its OAuth2 documentation.
- The project is young: version 0.9.0-alpha, no continuous integration.

## Contributing, reporting a vulnerability

See [CONTRIBUTING.md](CONTRIBUTING.md). A vulnerability is reported in private according to [SECURITY.md](SECURITY.md), never in a public issue.

## Credits

Skrivagner is the fruit of a collaboration between a person and language models, with the roles written as they were held. The complete list is in [CONTRIBUTORS.md](CONTRIBUTORS.md).

*   **Ronan Davalan**: architect and arbiter; vision, decisions, scope, validation. Sole git author.
*   **Claude Code (Anthropic)**: implementation engineer; Python code and tests, and the public documents (this README and its translations, the manual page, `CONTRIBUTING.md`, `SECURITY.md`).
*   **Gemini (Google)**: design adviser; proposed the original name "Le Greffier".
*   **Copilot (Microsoft)**: translated that name into Breton, hence "Skrivagner".
