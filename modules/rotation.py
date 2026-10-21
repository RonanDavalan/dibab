"""Rotation du journal des actions et des fichiers de session, selon `suivi.rotation`.

Une archive qui porte encore une action non annulée n'est jamais supprimée : la rotation attend
plutôt que de perdre ce que le rollback doit pouvoir relire.
"""

from pathlib import Path

from modules import journal_actions


def _numero(archive, chemin):
    return int(archive.name[len(chemin.stem) + 1:-len(chemin.suffix)])


def _porte_une_action_active(archive, chemin):
    actives = {a["id_action"] for a in journal_actions.actions_actives(journal_actions.lire_lignes(chemin))}
    return any(ligne.get("id_action") in actives and ligne.get("evenement") == journal_actions.ACTION
               for ligne in journal_actions.lire_lignes_fichier(archive))


def tourner_journal(chemin, taille_max_mo, archives_max):
    """Archive `journal.jsonl` quand il dépasse la taille permise ; rend True si la rotation a eu lieu."""
    chemin = Path(chemin)
    if not chemin.exists() or chemin.stat().st_size <= taille_max_mo * 1024 * 1024:
        return False
    archives = [a for a in journal_actions.fichiers_du_journal(chemin) if a != chemin]
    if len(archives) >= archives_max:
        plus_ancienne = archives[0]
        if _porte_une_action_active(plus_ancienne, chemin):
            return False
        plus_ancienne.unlink()
        archives = archives[1:]
    for archive in reversed(archives):
        archive.rename(archive.with_name(f"{chemin.stem}.{_numero(archive, chemin) + 1}{chemin.suffix}"))
    chemin.rename(chemin.with_name(f"{chemin.stem}.1{chemin.suffix}"))
    return True


def purger_sessions(dossier, sessions_max):
    """Garde les `sessions_max` plus récents journaux et rapports de session ; rend le nombre supprimé."""
    dossier = Path(dossier)
    supprimes = 0
    for motif in ("session_*.jsonl", "rapport_*.json"):
        for ancien in sorted(dossier.glob(motif))[:-sessions_max or None]:
            ancien.unlink()
            supprimes += 1
    return supprimes
