"""Fixture adapters for the gate environment.

These implement the same capability protocols as the production adapters and
are held to the same shared contract suite. They exist so a gate run exercises
the real durable job machinery — the transitions, the events, the publication —
without contacting Deezer or YouTube.

They are resolvable only when `CHILLIFY_ENV=gate` and the gate-safety checks in
`config` have already passed. Nothing here is imported on a production path.
"""

from __future__ import annotations

import json
import logging
import shutil
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from chillify.domain.errors import (
    AcquisitionCancelledError,
    AcquisitionFailedError,
    ProviderResponseError,
)
from chillify.domain.normalization import normalize_key
from chillify.domain.protocols import (
    AudioArtifact,
    CancelledCallback,
    ProgressCallback,
    TrackCandidate,
)
from chillify.infrastructure.providers.deezer_wire import candidates_from_search
from chillify.infrastructure.providers.radio_javan_wire import (
    candidates_from_browse as radio_javan_candidates_from_browse,
)
from chillify.infrastructure.providers.radio_javan_wire import (
    candidates_from_search as radio_javan_candidates_from_search,
)
from chillify.infrastructure.providers.radio_javan_wire import (
    media_url_from_detail,
)

logger = logging.getLogger(__name__)

# Layout beneath CHILLIFY_FIXTURE_ROOT.
SEARCH_FIXTURE = "providers/deezer_search.json"
AUDIO_FIXTURE = "media/gate-tone.mp3"
RADIO_JAVAN_SEARCH_FIXTURE = "providers/radiojavan_search.json"
RADIO_JAVAN_BROWSE_FIXTURES: Final = {
    "featured": "providers/radiojavan_featured.json",
    "trending": "providers/radiojavan_trending.json",
}
RADIO_JAVAN_DETAIL_FIXTURE = "providers/radiojavan_detail.json"

# The fixture acquisition reports these percentages in order, so a gate
# walkthrough sees a real determinate bar advance rather than a frozen one.
_PROGRESS_STEPS: Final = (0.0, 25.0, 50.0, 75.0, 100.0)

# Long enough for a person to watch the phases change, short enough that a gate
# run of several jobs stays quick.
_STEP_SECONDS: Final = 0.2


@dataclass(frozen=True, slots=True)
class FixtureDiscoveryProvider:
    """Deezer search served from a sanitized recorded payload."""

    fixture_root: Path
    name: str = "deezer"

    def search(
        self,
        query: str,
        limit: int,
        proxy: str | None,  # noqa: ARG002 - protocol parameter; a fixture makes no request
    ) -> tuple[TrackCandidate, ...]:
        """Match the recorded payload against the query, exactly as Deezer would.

        The proxy is accepted and ignored: a fixture makes no outbound request,
        and pretending to honour a proxy it never used would be a lie the gate
        then trusts.
        """
        payload = _read_json(self.fixture_root / SEARCH_FIXTURE)
        candidates = candidates_from_search(payload)
        needle = normalize_key(query, fallback="")
        if not needle:
            return ()
        matches = [
            candidate
            for candidate in candidates
            if needle in normalize_key(f"{candidate.artist} {candidate.title}", fallback="")
        ]
        return tuple(matches[:limit])


@dataclass(frozen=True, slots=True)
class FixtureAcquisitionProvider:
    """Acquisition that copies one recorded MP3 into the task workspace."""

    fixture_root: Path
    name: str = "fixture"

    def acquire(
        self,
        candidate: TrackCandidate,
        workspace: str,
        proxy: str | None,  # noqa: ARG002 - protocol parameter; a fixture makes no request
        progress: ProgressCallback,
        cancelled: CancelledCallback,
    ) -> AudioArtifact:
        """Produce one valid MP3, reporting progress and honouring cancellation."""
        source = self.fixture_root / AUDIO_FIXTURE
        if not source.is_file():
            raise AcquisitionFailedError(
                "The gate audio fixture is missing, so nothing could be acquired.",
                context={"provider": self.name},
            )

        target = Path(workspace) / "acquired.mp3"
        for percent in _PROGRESS_STEPS:
            if cancelled():
                target.unlink(missing_ok=True)
                raise AcquisitionCancelledError("That download was cancelled.")
            progress(percent)
            time.sleep(_STEP_SECONDS)

        shutil.copyfile(source, target)
        size = target.stat().st_size
        if size == 0:
            raise AcquisitionFailedError(
                "The acquired file was empty.", context={"provider": self.name}
            )
        logger.info(
            "fixture acquisition complete",
            extra={"provider": self.name, "source_provider": candidate.provider},
        )
        return AudioArtifact(
            location=str(target), duration_ms=candidate.duration_ms, byte_size=size
        )


@dataclass(frozen=True, slots=True)
class FixtureRadioJavanDiscoveryProvider:
    """Radio Javan search served from a sanitized recorded payload."""

    fixture_root: Path
    name: str = "radiojavan"

    def search(
        self,
        query: str,
        limit: int,
        proxy: str | None,  # noqa: ARG002
    ) -> tuple[TrackCandidate, ...]:
        payload = _read_json(self.fixture_root / RADIO_JAVAN_SEARCH_FIXTURE, self.name)
        candidates = radio_javan_candidates_from_search(payload)
        needle = normalize_key(query, fallback="")
        if not needle:
            return ()
        return tuple(
            candidate
            for candidate in candidates
            if needle in normalize_key(f"{candidate.artist} {candidate.title}", fallback="")
        )[:limit]

    def browse(
        self,
        section: str,
        proxy: str | None,  # noqa: ARG002
    ) -> tuple[TrackCandidate, ...]:
        fixture = RADIO_JAVAN_BROWSE_FIXTURES.get(section)
        if fixture is None:
            raise ProviderResponseError(
                "The Radio Javan browse section is unavailable.", context={"provider": self.name}
            )
        payload = _read_json(self.fixture_root / fixture, self.name)
        return radio_javan_candidates_from_browse(payload)


@dataclass(frozen=True, slots=True)
class FixtureRadioJavanAcquisitionProvider:
    """Radio Javan detail resolution backed by a recorded native MP3."""

    fixture_root: Path
    name: str = "radiojavan"

    def acquire(
        self,
        candidate: TrackCandidate,
        workspace: str,
        proxy: str | None,  # noqa: ARG002
        progress: ProgressCallback,
        cancelled: CancelledCallback,
    ) -> AudioArtifact:
        payload = _read_json(self.fixture_root / RADIO_JAVAN_DETAIL_FIXTURE, self.name)
        source_id = candidate.source_id or candidate.acquisition_locator
        media_url_from_detail(payload, source_id)
        if cancelled():
            raise AcquisitionCancelledError("That download was cancelled.")
        source = self.fixture_root / AUDIO_FIXTURE
        if not source.is_file():
            raise AcquisitionFailedError(
                "The Radio Javan audio fixture is missing.", context={"provider": self.name}
            )
        target = Path(workspace) / "radio-javan.mp3"
        progress(0.0)
        shutil.copyfile(source, target)
        progress(100.0)
        size = target.stat().st_size
        if size == 0:
            raise AcquisitionFailedError(
                "The acquired file was empty.", context={"provider": self.name}
            )
        return AudioArtifact(
            location=str(target), duration_ms=candidate.duration_ms, byte_size=size
        )


def _read_json(path: Path, provider: str = "deezer") -> object:
    if not path.is_file():
        raise ProviderResponseError(
            "The gate search fixture is missing.", context={"provider": provider}
        )
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ProviderResponseError(
            "The gate search fixture could not be read.", context={"provider": provider}
        ) from exc
