"""Verrou d'exécution : un seul Skrivagner à la fois déplace des documents.

Deux exécutions simultanées se disputeraient les mêmes sources et les mêmes noms de destination,
et la synchronisation des coffres propagerait le résultat de l'une et de l'autre.
"""

import os
from contextlib import contextmanager
from pathlib import Path
from modules.messages import traduire


class VerrouPris(Exception):
    """Une autre exécution tient le verrou."""


def _processus_vivant(pid):
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


@contextmanager
def verrou(chemin):
    """Pose le verrou `chemin` ; un verrou laissé par un processus mort est repris."""
    chemin = Path(chemin)
    chemin.parent.mkdir(parents=True, exist_ok=True)
    for _ in range(2):
        try:
            descripteur = os.open(chemin, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        except FileExistsError:
            try:
                pid = int(chemin.read_text(encoding="utf-8").strip())
            except (OSError, ValueError):
                pid = None
            if pid is not None and _processus_vivant(pid):
                raise VerrouPris(traduire("verrou_pris", pid=pid, chemin=chemin))
            chemin.unlink(missing_ok=True)
            continue
        with os.fdopen(descripteur, "w", encoding="utf-8") as f:
            f.write(str(os.getpid()))
        break
    else:
        raise VerrouPris(traduire("verrou_illisible", chemin=chemin))
    try:
        yield
    finally:
        chemin.unlink(missing_ok=True)
