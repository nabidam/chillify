"""Enumerating and reclaiming the task workspaces reconciliation cannot trust.

A workspace under `.chillify/work/{job-id}` is the scratch space one acquisition
owns while it runs. When a worker dies mid-download the directory outlives the
run that created it, so recovery has to look at the tree on disk rather than at
what any single process remembers.

Creation, the safe-name rule, and single-workspace removal all live in
`storage`; this module is only the enumeration and the bulk reclaim that
reconciliation drives. Nothing here trusts a directory name as a path: a job ID
is compared as an opaque string, never joined back onto the filesystem.
"""

from __future__ import annotations

import logging
from pathlib import Path

from chillify.infrastructure.media.storage import (
    INTERNAL_DIRECTORY,
    WORK_DIRECTORY,
    remove_workspace,
)

logger = logging.getLogger(__name__)


def _work_root(music_root: Path) -> Path:
    return music_root / INTERNAL_DIRECTORY / WORK_DIRECTORY


def existing_workspaces(music_root: Path) -> dict[str, Path]:
    """Map every job ID that currently owns a workspace to its directory.

    The directory name is the job ID the workspace was created for. An entry
    that is not a directory is ignored rather than reported: only a directory
    is a workspace, and a stray file under `work/` is somebody else's problem.
    """
    root = _work_root(music_root)
    if not root.is_dir():
        return {}
    return {child.name: child for child in root.iterdir() if child.is_dir()}


def remove_orphan_workspaces(music_root: Path, active_job_ids: set[str]) -> list[str]:
    """Discard every workspace whose job is no longer active.

    A workspace belongs to a job that is still queued or running; anything else
    is the residue of a completed, failed, cancelled, or vanished job and is
    leaked disk. Removal never raises — a workspace that will not delete is
    reported and left, because a stuck directory must not stall recovery.
    """
    removed: list[str] = []
    for job_id, workspace in existing_workspaces(music_root).items():
        if job_id in active_job_ids:
            continue
        remove_workspace(workspace)
        removed.append(job_id)
    if removed:
        logger.info("removed orphan workspaces", extra={"count": len(removed)})
    return removed
