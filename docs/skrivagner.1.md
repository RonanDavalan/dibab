% SKRIVAGNER(1) skrivagner | User Commands
% Ronan Davalan
% 2026-10-29

# NAME

skrivagner - collects, analyses and files the personal administrative documents of a household, without any data leaving the local network

# SYNOPSIS

**skrivagner** [**\--config** *PATH*] [**\--dry-run** | **\--execute** | **\--inventaire**]

**skrivagner** **\--dry-run** **\--verdicts-simules** *FILE*

**skrivagner** [**\--config** *PATH*] **\--rollback** [**\--session** *SESSION*]

**skrivagner** [**\--config** *PATH*] **\--autoriser-google** *ID*

**skrivagner** [**\--config** *PATH*] **\--diagnose**

**skrivagner** {**\--version** | **\--help**}

# DESCRIPTION

**skrivagner** scans local directories, remote machines over **ssh**(1) and mailboxes over read-only IMAP. It extracts the text of
each document, sets aside what is not administrative, then files the rest by category and by domain, personal or professional,
by the consensus of several language models. Each document is renamed and moved into the vault of its domain, with a journal that
**\--rollback** can undo. It never deletes a file, never modifies a mailbox or a remote machine, and moves nothing it is not sure
about: doubt leads to a folder named *À_VÉRIFIER*.

The language models are those of Ollama, which runs on the same machine. Ollama and its models are installed separately, by the
user, from the Ollama website: Skrivagner contains neither. List the models with **ollama list**, then write them, role by role,
in the key **ollama.roles** of the configuration. Only the destination vault of each domain, the machines and the mailboxes that the configuration
names are ever reached.

The default mode is the simulation. Always read the result of **\--dry-run** before running **\--execute**.

# OPTIONS

**\--dry-run**
:   Simulation, the default mode: scans, extracts and classifies, and prints each destination it would choose. Nothing is moved.

**\--execute**
:   Real mode: each document is copied, checked by fingerprint (SHA256), then removed from its source. Refused on a machine that
    the key **executer_sur** of the configuration does not list.

**\--inventaire**
:   Reads what each vault already holds and writes a migration plan for each of them. Nothing is moved.

**\--rollback**
:   Undoes the last filing session, or the one named by **\--session**. The document returns to its original place, the copy checked
    by fingerprint; an action that cannot be undone leaves everything in place for it.

**\--session** *SESSION*
:   Identifier of the session to undo, with **\--rollback**.

**\--autoriser-google** *ID*
:   OAuth2 consent for the Google IMAP source named *ID* in the configuration. Prints an address to open in a browser, then writes
    the token file of the source.

**\--diagnose**
:   Checks the installation, the configuration, Ollama and the vault of each domain, one line per check, and writes nothing.

**\--verdicts-simules** *FILE*
:   With **\--dry-run** only: a JSON file that maps a file name to a verdict, whose routing is printed.

**\--config** *PATH*
:   Configuration file to read (see **FILES**).

**\--version**
:   Prints one line, **skrivagner** *version*, and stops.

**\--help**, **-h**
:   Lists the options, in the language of the session.

# LANGUAGE

Messages are written in English, French, German or Spanish. The language is read once at start, in the first of **LC_ALL**,
**LC_MESSAGES** and **LANG** that is not empty: the part before the first **\_**, **.** or **@** gives **en**, **fr**, **de** or **es**;
any other value, **C**, **POSIX** or no variable gives English. The option names, the state tokens of **\--diagnose** (**OK**,
**AVERTISSEMENT**, **ÉCHEC**, **NON_CONFIGURÉ**, **NON_VÉRIFIÉ**), the identifiers of the checks and the **\--version** line never change.
What is written on disk (journals, plans, reports) is in English, whatever the language of the session.

# INSTALLATION

On Debian 12 and 13 and on Ubuntu 22.04 and 24.04, the Debian package installs the program, its dependencies, the four manual pages and the example configuration *config.exemple.json* in */usr/share/doc/skrivagner/examples/*:

    sudo apt install ./skrivagner_*_all.deb

**sudo apt remove skrivagner** and **sudo apt purge skrivagner** delete the files of the package and never touch the configuration, the state, the journal or the documents; the purge names what it leaves. Level: installation and diagnostic validated in a container on these four versions; a container shows neither the mounting of an encrypted vault nor a run with your own Ollama.

# FILES

The configuration is the first existing file among, in this order, and only that one is read:

1.  the file named by **\--config**;
2.  the file named by the variable **SKRIVAGNER_CONFIG**, when it is not empty;
3.  *$XDG_CONFIG_HOME/skrivagner/config.json*, or *~/.config/skrivagner/config.json* when **XDG_CONFIG_HOME** is empty or unset;
4.  *config.json* in the folder of *skrivagner.py*.

An option or a variable that names a missing file stops the program with the exit status 1: it never falls back on another file.
*config.exemple.json* is the example, in the folder of the program; copy it to one of these places, with mode 600.

When the configuration does not give the keys of **suivi**, the state is written under *$XDG_STATE_HOME/skrivagner/*, or
*~/.local/state/skrivagner/*: *dernier_scan.json*, *journal.jsonl* (the action journal), *sessions/* (one journal and one report per
session) and *skrivagner.log*. *rapatries.json*, *imap_deposes.json* and the lock *skrivagner.verrou* sit next to *dernier_scan.json*.
The folders are created with mode 700 and the files with mode 600. The state is then in clear text on the disk: to keep it in a
vault, give the keys **suivi.fichier_date**, **suivi.journal** and **suivi.sessions**.

The message dictionaries are *modules/langues/en.txt*, *fr.txt*, *de.txt* and *es.txt*, in the folder of the program.

# ENVIRONMENT

**SKRIVAGNER_CONFIG**
:   Path of the configuration file.

**XDG_CONFIG_HOME**, **XDG_STATE_HOME**
:   Base folders of the configuration and of the default state.

**LC_ALL**, **LC_MESSAGES**, **LANG**
:   Language of the messages (see **LANGUAGE**).

The password of an IMAP mailbox is read from the variable that the key **mot_de_passe_env** of its source names, never from the
configuration file.

# EXIT STATUS

**0**
:   Success.

**1**
:   Configuration not found, invalid or missing a key; at least one source or document in failure; rollback only partly done; OAuth2
    consent failed; **\--diagnose** with at least one **ÉCHEC**.

**2**
:   A vault not proven mounted, before a mode that writes; invalid command line.

**3**
:   No model installed for a role, or Ollama does not answer.

**4**
:   **\--execute** refused on this machine (key **executer_sur**).

**5**
:   Another run holds the lock *skrivagner.verrou*.

# EXAMPLES

Check the installation, then simulate, then file for real:

    skrivagner --diagnose
    skrivagner --dry-run
    skrivagner --execute

Read the same check in French, then undo the last session:

    LC_ALL=fr_FR.UTF-8 skrivagner --diagnose
    skrivagner --rollback

# SEE ALSO

**ollama**(1), **ssh**(1), **findmnt**(8), **pdftotext**(1), **pdftoppm**(1)

The README of the project describes the installation from the Debian package and from the sources, the configuration, the sources over **ssh**, IMAP and OAuth2
for Google, and the limits.

# LICENSE

GNU Affero General Public License version 3.
