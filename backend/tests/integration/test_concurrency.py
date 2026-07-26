"""Real concurrent access: filelock serialization and race-safe uniqueness.

Every other suite proves these invariants sequentially — one request commits,
then a second observes it. A sequential test cannot tell "the code checks
correctly" apart from "the code happened to run only one request at a time in
this test". This suite drives the same invariants with genuinely concurrent
threads: ARCHITECTURE section 4 names the database's own unique constraint as
the *final* race-safe guard precisely because a pre-check alone cannot close
the window two real concurrent writers open, and section 8 names the advisory
filelock as what serializes two real concurrent mutators of the same track.
"""

from __future__ import annotations

import threading
from pathlib import Path

import pytest

from chillify.application.downloads import DownloadService
from chillify.composition import Composition
from chillify.domain.errors import DuplicateRecordError, MutationLockedError
from chillify.domain.jobs import SourceType
from chillify.domain.protocols import TrackCandidate
from chillify.infrastructure.media.mutations import media_locks

pytestmark = pytest.mark.integration


def _candidate(source_id: str) -> TrackCandidate:
    return TrackCandidate(
        provider="deezer",
        source_id=source_id,
        source_url=f"https://www.deezer.com/track/{source_id}",
        title="Same Track, Twice",
        artist="Concurrency Test",
        album=None,
        release_year=None,
        disc_number=None,
        track_number=None,
        duration_ms=None,
        isrc=None,
        artwork_url=None,
        acquisition_locator=f"ytsearch1:concurrency test {source_id}",
        raw_fingerprint=None,
    )


class TestFileLockSerializesConcurrentMutators:
    def test_a_second_concurrent_mutator_is_refused_while_the_first_holds_the_lock(
        self, tmp_path: Path
    ) -> None:
        """Two real threads race for the same track's advisory lock.

        The first to arrive holds `library.lock` and the track lock for the
        whole critical section; the second's bounded wait must time out and
        report `423 mutation_locked` rather than ever entering alongside it.
        """
        music_root = tmp_path / "music"
        music_root.mkdir()
        entered = threading.Event()
        release = threading.Event()
        outcomes: list[str] = []
        lock = threading.Lock()

        def hold_first() -> None:
            with media_locks(music_root, track_id="racing-track", timeout=5.0):
                entered.set()
                release.wait(timeout=5.0)
            with lock:
                outcomes.append("first-released")

        def attempt_second() -> None:
            assert entered.wait(timeout=5.0), "the first mutator never signalled entry"
            try:
                with media_locks(music_root, track_id="racing-track", timeout=0.2), lock:
                    outcomes.append("second-acquired")
            except MutationLockedError:
                with lock:
                    outcomes.append("second-refused")

        first = threading.Thread(target=hold_first)
        second = threading.Thread(target=attempt_second)
        first.start()
        second.start()
        second.join(timeout=5.0)
        release.set()
        first.join(timeout=5.0)

        assert not first.is_alive(), "the first mutator's thread never finished"
        assert not second.is_alive(), "the second mutator's thread never finished"
        # The second attempt was refused strictly before the first released —
        # never let in alongside it, and never left waiting past its own bound.
        assert outcomes == ["second-refused", "first-released"]


class TestDuplicateDownloadRaceIsResolvedByTheDatabase:
    def test_two_concurrent_identical_requests_yield_exactly_one_active_job(
        self,
        gate_composition: Composition,
        dispatched_jobs: list[str],
    ) -> None:
        """Two threads submit the identical candidate at the same instant.

        `DownloadService.request_download` deliberately has no duplicate
        pre-check — ARCHITECTURE names the partial unique index as the
        race-safe answer instead. This drives two real threads, each with its
        own session against the same on-disk SQLite file, through that exact
        path at once.
        """
        candidate = _candidate("concurrency-race-1")
        barrier = threading.Barrier(2)
        results: list[object] = []
        results_lock = threading.Lock()

        def attempt() -> None:
            service = DownloadService(
                session_factory=gate_composition.session_factory,
                registry=gate_composition.registry,
                music_root=gate_composition.settings.music_root,
                dispatch=lambda job_id: _record_dispatch(job_id, dispatched_jobs),
                queue_reachable=lambda: True,
                worker_identity="test-worker",
            )
            barrier.wait(timeout=5.0)
            try:
                job = service.request_download(candidate, SourceType.DEEZER_RESULT)
                outcome: object = ("ok", str(job.id))
            except DuplicateRecordError:
                outcome = ("duplicate", None)
            with results_lock:
                results.append(outcome)

        threads = [threading.Thread(target=attempt) for _ in range(2)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=10.0)

        assert all(not thread.is_alive() for thread in threads)
        succeeded = [outcome for outcome in results if outcome[0] == "ok"]  # type: ignore[index]
        duplicates = [outcome for outcome in results if outcome[0] == "duplicate"]  # type: ignore[index]
        assert len(succeeded) == 1, f"expected exactly one winner, got {results}"
        assert len(duplicates) == 1, f"expected exactly one duplicate refusal, got {results}"
        # The database, not a race in who happened to dispatch first, decided
        # the winner: exactly one job was ever handed to the queue.
        assert dispatched_jobs == [succeeded[0][1]]  # type: ignore[index]


def _record_dispatch(job_id: object, sink: list[str]) -> str:
    sink.append(str(job_id))
    return f"task-{job_id}"
