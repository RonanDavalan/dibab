"""Faux `ssh` : un exécutable factice qui joue la commande distante dans un répertoire local servant de machine distante."""

import os
import stat

SCRIPT = """#!/bin/sh
while [ $# -gt 0 ]; do
  case "$1" in -o) shift 2;; --) shift; break;; *) break;; esac
done
alias="$1"; shift
case "$FAUX_SSH_MODE" in
  absente) echo "ssh: Could not resolve hostname $alias" >&2; exit 255;;
  lent) exec sleep 30;;
  coupe)
    case "$1" in cat*"$FAUX_SSH_COUPE"*) printf 'par'; exit 255;; esac;;
esac
HOME="$FAUX_SSH_HOME" exec sh -c "$1"
"""


def installer(tmp_path, monkeypatch):
    """Place le faux `ssh` en tête du PATH ; rend le répertoire qui joue la machine distante."""
    binaires = tmp_path / "bin"
    distant = tmp_path / "distant"
    binaires.mkdir()
    distant.mkdir()
    ssh = binaires / "ssh"
    ssh.write_text(SCRIPT, encoding="utf-8")
    ssh.chmod(stat.S_IRWXU)
    monkeypatch.setenv("PATH", f"{binaires}{os.pathsep}{os.environ['PATH']}")
    monkeypatch.setenv("FAUX_SSH_HOME", str(distant))
    monkeypatch.setenv("FAUX_SSH_MODE", "normal")
    return distant
