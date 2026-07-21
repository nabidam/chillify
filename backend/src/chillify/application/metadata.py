"""Track correction: one save that changes tags, art, path, and record together.

This is the use case ARCHITECTURE section 8's metadata-edit contract describes.
Its whole purpose is that a person pressing Save once cannot end up with an MP3
whose tags say one thing and a library that says another — not if the process
is killed halfway, not if the disk fills, not if somebody else saved first.

The ordering is fixed and every step is journaled:

1. Validate the complete intended record and the optional artwork stage.
2. Open a `media_mutations` row describing what is about to change.
3. Stage a fully retagged copy outside the library.
4. Hard-link the live files into recovery, then atomically place the staged ones.
5. Commit the record, consume the stage, and mark the journal `db_committed`.
6. Drop the superseded paths and close the journal.

A failure before step 5 leaves the old record authoritative and removes only
staged files. A failure at step 5 restores the recovery links, so the old files
are back at their old paths before the error reaches the browser. No old path
is ever removed until the new record can already play.
"""

from __future__ import annotations

import logging
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy.orm import Session, sessionmaker

from chillify.domain.errors import (
    ArtworkStageUnavailableError,
    DuplicateRecordError,
    RecordChangedError,
    RecordNotFoundError,
    TrackFileMissingError,
)
from chillify.domain.models import (
    ArtworkStage,
    ArtworkStageId,
    Availability,
    Track,
    TrackDetail,
    TrackEdit,
    TrackId,
    normalize_metadata,
)
from chillify.domain.normalization import (
    validate_optional_text,
    validate_ordinal,
    validate_release_year,
    validate_required_text,
)
from chillify.infrastructure.db.repositories import (
    ArtworkStageRepository,
    MediaMutationRepository,
    TrackRepository,
)
from chillify.infrastructure.media import mutations
from chillify.infrastructure.media.artwork import artwork_relpath
from chillify.infrastructure.media.storage import organized_relpath, resolve_managed_path
from chillify.infrastructure.media.tags import write_track_tags

logger = logging.getLogger(__name__)

STAGED_AUDIO_NAME = "audio.mp3"
STAGED_ARTWORK_NAME = "cover.jpg"


@dataclass(frozen=True, slots=True)
class _IntendedRecord:
    """The validated record one save intends to make true."""

    title: str
    artist: str
    album: str | None
    release_year: int | None
    disc_number: int | None
    track_number: int | None


@dataclass(frozen=True, slots=True)
class MetadataService:
    """Reading one complete track and applying one recoverable correction."""

    session_factory: sessionmaker[Session]
    music_root: Path

    @contextmanager
    def _transaction(self) -> Iterator[Session]:
        session = self.session_factory()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def get_track_detail(self, track_id: TrackId) -> TrackDetail:
        with self._transaction() as session:
            detail = TrackRepository(session).get_detail(track_id)
        if detail is None:
            raise RecordNotFoundError("That track is not in this library.")
        return detail

    def open_artwork(self, track_id: TrackId) -> Path | None:
        """The managed cover file for one track, or None when it has none."""
        detail = self.get_track_detail(track_id)
        if detail.track.artwork_relpath is None:
            return None
        path = resolve_managed_path(self.music_root, detail.track.artwork_relpath)
        return path if path.is_file() else None

    def open_artwork_stage(self, stage_id: ArtworkStageId) -> Path:
        """The staged cover file, so S13 can preview it before saving.

        A stage that has expired or been consumed is already gone as far as the
        browser is concerned, so it reports the same unavailability the save
        would.
        """
        now = datetime.now(UTC)
        with self._transaction() as session:
            stage = ArtworkStageRepository(session).require_consumable(stage_id, now=now)
        path = resolve_managed_path(self.music_root, stage.file_relpath)
        if not path.is_file():
            raise ArtworkStageUnavailableError(
                "That cover image is no longer available. Choose it again."
            )
        return path

    def update_track(
        self, track_id: TrackId, edit: TrackEdit, *, expected_revision: int
    ) -> TrackDetail:
        """Apply one complete correction atomically, or change nothing."""
        now = datetime.now(UTC)
        intended = _validate(edit, now=now)

        # Both locks are held across the whole mutation: the duplicate recheck,
        # the path calculation, and the commit all have to see one filesystem.
        with mutations.media_locks(self.music_root, track_id=str(track_id)):
            plan = self._prepare(track_id, edit, intended, expected_revision=expected_revision)
            return self._perform(plan, now=now)

    # -- step 1 and 2: validate against live state, open the journal ----------

    def _prepare(
        self,
        track_id: TrackId,
        edit: TrackEdit,
        intended: _IntendedRecord,
        *,
        expected_revision: int,
    ) -> _EditPlan:
        now = datetime.now(UTC)
        with self._transaction() as session:
            tracks = TrackRepository(session)
            detail = tracks.get_detail(track_id)
            if detail is None:
                raise RecordNotFoundError("That track is not in this library.")
            current = detail.track
            # The revision is checked before anything is journaled or staged:
            # a save that has already lost to another one must not leave a
            # recovery record and a staging directory behind it.
            if current.revision != expected_revision:
                raise RecordChangedError(
                    "Somebody else saved this track first. Reload it and try again.",
                    context={"current_revision": current.revision},
                )
            if current.availability is Availability.MISSING:
                raise TrackFileMissingError(
                    "This track's file is missing, so its tags cannot be rewritten.",
                    context={"availability": str(current.availability)},
                )

            normalized = normalize_metadata(
                artist=intended.artist, title=intended.title, album=intended.album
            )
            conflict = tracks.find_conflict(
                track_id=track_id,
                normalized_artist=normalized.normalized_artist,
                normalized_title=normalized.normalized_title,
            )
            if conflict is not None:
                raise DuplicateRecordError(
                    "Another track in this library already has that artist and title.",
                    context={"existing_track_id": str(conflict.id)},
                )

            stage: ArtworkStage | None = None
            if edit.artwork_stage_id is not None:
                stage = ArtworkStageRepository(session).require_consumable(
                    edit.artwork_stage_id, now=now
                )

            intended_audio = mutations.unused_relpath(
                self.music_root,
                organized_relpath(
                    artist=intended.artist,
                    album=intended.album,
                    title=intended.title,
                    track_number=intended.track_number,
                ),
                keeping=current.file_relpath,
            )
            # The cover's managed name is derived from the track ID, so it is
            # stable across a rename: only a new image changes that file.
            intended_artwork = (
                artwork_relpath(str(track_id)) if stage is not None else current.artwork_relpath
            )

            mutation_id = MediaMutationRepository(session).open_edit(
                track_id=track_id,
                old_record=_record_snapshot(current),
                new_record={
                    "title": intended.title,
                    "artist": intended.artist,
                    "album": intended.album,
                    "release_year": intended.release_year,
                    "disc_number": intended.disc_number,
                    "track_number": intended.track_number,
                    "file_relpath": intended_audio,
                    "artwork_relpath": intended_artwork,
                },
                now=now,
            )

        return _EditPlan(
            track_id=track_id,
            current=current,
            intended=intended,
            intended_audio_relpath=intended_audio,
            intended_artwork_relpath=intended_artwork,
            stage=stage,
            mutation_id=mutation_id,
            expected_revision=expected_revision,
        )

    # -- steps 3 to 6: stage, place, commit, clean up ------------------------

    def _perform(self, plan: _EditPlan, *, now: datetime) -> TrackDetail:
        """Stage, place, commit, and clean up — or leave the old record intact.

        Everything before the commit is wrapped so that a failure while staging
        or preserving recovery discards its own workspace and journal row. Only
        the old files exist at that point, so there is nothing to roll back —
        but leaving the journal open would make startup recovery inspect a
        change that never began.
        """
        # Everything up to placement only creates files outside the library, so
        # a failure here discards its own workspace and journal row: the old
        # record was never touched, and an open journal would make startup
        # recovery inspect a change that never began.
        try:
            staged_audio = mutations.stage_copy(
                self.music_root,
                mutation_id=plan.mutation_id,
                source_relpath=plan.current.file_relpath,
                name=STAGED_AUDIO_NAME,
            )
            staged_artwork = self._stage_artwork(plan)
            embedded = staged_artwork or self._existing_artwork_path(plan)

            write_track_tags(
                staged_audio,
                title=plan.intended.title,
                artist=plan.intended.artist,
                album=plan.intended.album,
                release_year=plan.intended.release_year,
                disc_number=plan.intended.disc_number,
                track_number=plan.intended.track_number,
                artwork=embedded,
            )
            mutations.fsync_file(staged_audio)
            content_sha256, size_bytes = mutations.file_digest(staged_audio)
            self._advance(plan.mutation_id, "files_staged", now=now)

            live_paths = [plan.current.file_relpath]
            if plan.current.artwork_relpath is not None:
                live_paths.append(plan.current.artwork_relpath)
            recovery = mutations.preserve_recovery(
                self.music_root, mutation_id=plan.mutation_id, relpaths=live_paths
            )
            self._advance(plan.mutation_id, "files_staged", now=now, recovery=recovery)

            with self._transaction() as session:
                TrackRepository(session).begin_mutation(
                    plan.track_id, expected_revision=plan.expected_revision
                )
        except Exception:
            mutations.discard_mutation_workspace(self.music_root, plan.mutation_id)
            self._close_journal(plan.mutation_id)
            raise

        placed: list[str] = []
        try:
            mutations.place(
                self.music_root,
                mutations.StagedFile(
                    staged_path=staged_audio, intended_relpath=plan.intended_audio_relpath
                ),
            )
            placed.append(plan.intended_audio_relpath)
            if staged_artwork is not None and plan.intended_artwork_relpath is not None:
                mutations.place(
                    self.music_root,
                    mutations.StagedFile(
                        staged_path=staged_artwork,
                        intended_relpath=plan.intended_artwork_relpath,
                    ),
                )
                placed.append(plan.intended_artwork_relpath)

            with self._transaction() as session:
                track = TrackRepository(session).apply_edit(
                    plan.track_id,
                    expected_revision=plan.expected_revision,
                    title=plan.intended.title,
                    artist=plan.intended.artist,
                    album=plan.intended.album,
                    release_year=plan.intended.release_year,
                    disc_number=plan.intended.disc_number,
                    track_number=plan.intended.track_number,
                    file_relpath=plan.intended_audio_relpath,
                    artwork_relpath=plan.intended_artwork_relpath,
                    file_size_bytes=size_bytes,
                    content_sha256=content_sha256,
                    now=now,
                )
                if plan.stage is not None:
                    ArtworkStageRepository(session).consume(plan.stage.id, now=now)
                MediaMutationRepository(session).advance(
                    plan.mutation_id, state="db_committed", now=now
                )
        except Exception:
            self._roll_back(plan, recovery=recovery, placed=placed, now=now)
            raise

        self._finalize(plan, recovery=recovery, now=now)
        logger.info(
            "track corrected",
            extra={"track_id": str(track.id), "revision": track.revision},
        )
        return self.get_track_detail(plan.track_id)

    def _stage_artwork(self, plan: _EditPlan) -> Path | None:
        """Copy the chosen stage into this mutation's own staging directory.

        The stage file itself is left alone until the commit consumes its row,
        so a failed save leaves the person's chosen image still available to
        try again with.
        """
        if plan.stage is None:
            return None
        source = resolve_managed_path(self.music_root, plan.stage.file_relpath)
        try:
            payload = source.read_bytes()
        except OSError as exc:
            raise TrackFileMissingError("That cover image is no longer readable.") from exc
        staged = mutations.stage_bytes(
            self.music_root,
            mutation_id=plan.mutation_id,
            name=STAGED_ARTWORK_NAME,
            payload=payload,
        )
        mutations.fsync_file(staged)
        return staged

    def _existing_artwork_path(self, plan: _EditPlan) -> Path | None:
        """The track's current cover, when the save is not replacing it."""
        if plan.current.artwork_relpath is None:
            return None
        path = resolve_managed_path(self.music_root, plan.current.artwork_relpath)
        return path if path.is_file() else None

    def _roll_back(
        self,
        plan: _EditPlan,
        *,
        recovery: dict[str, str],
        placed: list[str],
        now: datetime,
    ) -> None:
        """Put the previous files back and return the track to `available`.

        Newly placed paths are removed first, then the recovery links are
        relinked, so a rename that landed somewhere new does not leave a second
        copy of the track behind. The old record was never changed, so once the
        files are back the library is exactly as the person left it.
        """
        superseded = [path for path in placed if path not in recovery]
        mutations.discard_paths(self.music_root, superseded)
        mutations.restore_recovery(self.music_root, recovery)
        try:
            with self._transaction() as session:
                TrackRepository(session).end_mutation(plan.track_id)
                MediaMutationRepository(session).advance(
                    plan.mutation_id,
                    state="rolled_back",
                    now=now,
                    error_detail="database commit failed after placement",
                )
        except Exception:
            # The journal row is the recovery record; failing to update it is
            # logged once here and left for startup recovery to finish.
            logger.exception(
                "edit rollback could not update its journal",
                extra={"track_id": str(plan.track_id)},
            )
            return
        mutations.discard_mutation_workspace(self.music_root, plan.mutation_id)
        logger.warning(
            "track edit rolled back; the previous version remains authoritative",
            extra={"track_id": str(plan.track_id)},
        )

    def _finalize(self, plan: _EditPlan, *, recovery: dict[str, str], now: datetime) -> None:
        """Drop the superseded paths and close the journal."""
        obsolete = [
            relative
            for relative in recovery
            if relative not in (plan.intended_audio_relpath, plan.intended_artwork_relpath)
        ]
        mutations.discard_paths(self.music_root, obsolete)
        mutations.discard_mutation_workspace(self.music_root, plan.mutation_id)
        with self._transaction() as session:
            journal = MediaMutationRepository(session)
            journal.advance(plan.mutation_id, state="finalized", now=now)
            journal.close(plan.mutation_id)
        mutations.prune_empty_parents(self.music_root, obsolete)

    def _close_journal(self, mutation_id: str) -> None:
        """Remove a journal row for a change that never reached the filesystem.

        Never raises: it runs while another failure is already on its way to the
        browser, and replacing that failure with this one would hide the cause.
        """
        try:
            with self._transaction() as session:
                MediaMutationRepository(session).close(mutation_id)
        except Exception:
            logger.exception("edit journal row could not be closed")

    def _advance(
        self,
        mutation_id: str,
        state: str,
        *,
        now: datetime,
        recovery: dict[str, str] | None = None,
    ) -> None:
        with self._transaction() as session:
            MediaMutationRepository(session).advance(
                mutation_id, state=state, now=now, recovery=recovery
            )


@dataclass(frozen=True, slots=True)
class _EditPlan:
    """Everything one save decided before it touched the filesystem."""

    track_id: TrackId
    current: Track
    intended: _IntendedRecord
    intended_audio_relpath: str
    intended_artwork_relpath: str | None
    stage: ArtworkStage | None
    mutation_id: str
    expected_revision: int


def _validate(edit: TrackEdit, *, now: datetime) -> _IntendedRecord:
    """Hold the submitted record to the domain rules before anything is locked."""
    return _IntendedRecord(
        title=validate_required_text(edit.title, field="title", label="A title"),
        artist=validate_required_text(edit.artist, field="artist", label="An artist"),
        album=validate_optional_text(edit.album, field="album", label="An album"),
        release_year=validate_release_year(edit.release_year, now=now),
        disc_number=validate_ordinal(edit.disc_number, field="disc_number", label="A disc number"),
        track_number=validate_ordinal(
            edit.track_number, field="track_number", label="A track number"
        ),
    )


def _record_snapshot(track: Track) -> dict[str, object]:
    """The old record as the journal stores it, for conservative recovery."""
    return {
        "title": track.title,
        "artist": track.artist,
        "album": track.album,
        "release_year": track.release_year,
        "disc_number": track.disc_number,
        "track_number": track.track_number,
        "file_relpath": track.file_relpath,
        "artwork_relpath": track.artwork_relpath,
        "file_size_bytes": track.file_size_bytes,
        "content_sha256": track.content_sha256,
        "revision": track.revision,
    }
