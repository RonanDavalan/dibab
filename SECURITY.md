# Security policy

Skrivagner handles administrative documents (health, bank, tax, inheritance) and access to mailboxes: a flaw has a real cost for third parties. This policy says how to report one and what you can expect in return.

## Supported versions

Only the latest published version receives security fixes. The project has no maintenance branch: the fix appears on `main` and in a new version.

## Reporting a vulnerability

Use the private reporting of GitHub: the "Security" tab of the repository, then "Report a vulnerability" (GitHub Security Advisories). **Never open a public issue** for a flaw: publishing it before the fix exposes the people who already use Skrivagner.

State the version (`venv/bin/python skrivagner.py --version` prints it), what you observed, the steps to reproduce it and, if possible, what you judge to be in danger. Do not send any real document and no secret: a fictitious text is enough.

## Delays

- acknowledgement within 72 hours;
- first assessment (flaw confirmed or not, severity) within 7 days;
- fix aimed at within 30 days for a confirmed flaw; if this delay cannot be kept, you are told so with the reason.

The project is held by one person: these delays are those of a good-faith commitment, not of an on-call service.

## Coordinated disclosure

Please leave time to fix before any publication; once the fix is published, you can describe the flaw, and you are credited if you wish. Good-faith research, carried out on your own installation and within this framework, will not give rise to any prosecution by the project.

## What counts as a flaw

For instance: a write or a deletion outside the declared scope, a modification of a mailbox or of a remote machine, a secret (password, token, secret of the OAuth2 client) that reaches a journal, a report, the output or a file readable by others, a file name or an attachment name that makes a command run or leaves a directory, a document written into a vault that is not mounted.

## Out of scope

- unofficial forks and copies;
- versions older than the latest published;
- the configuration of the user: an unencrypted vault, a `config.json` readable by everyone, an `ssh` access opened to too many keys;
- Ollama, the language models, `ssh`, the IMAP servers and the services of Google, which have their own reporting channels;
- a wrong classification by a model: it is a known limit (the document goes to `À_VÉRIFIER/` and `--rollback` puts it back), not a flaw.
