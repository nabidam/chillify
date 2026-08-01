"""The shared SpotDL link-inspection contract.

Every adapter that inspects a Spotify link is held to the same behaviour here,
whether it reads a recorded metadata document or invokes the isolated SpotDL
CLI. The suite is parameterized over adapter factories so the production adapter
Task 16 binds joins these same cases.

Collection rejection and metadata normalization are part of the contract: an
album, playlist, or artist link must be refused before invocation, and a single
track must normalize cleanly with its ISRC and numbering intact.
"""

from __future__ import annotations

import os
import shutil
from collections.abc import Callable, Sequence
from pathlib import Path

import pytest

from chillify.domain.errors import (
    AcquisitionCancelledError,
    AcquisitionFailedError,
    ProviderResponseError,
    UnsupportedEntityError,
)
from chillify.domain.protocols import LinkInspector, TrackCandidate
from chillify.infrastructure.providers.spotdl import (
    FixtureSpotdlInspector,
    SpotdlAcquisitionProvider,
    SpotdlInspector,
    SubprocessResult,
    candidate_from_metadata,
)

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
GATE_TONE = FIXTURES / "media" / "gate-tone.mp3"

TRACK_ID = "2cGxRwrMyEAp8dEbuZaVv6"
TRACK_URL = f"https://open.spotify.com/track/{TRACK_ID}"
INTL_TRACK_URL = f"https://open.spotify.com/intl-de/track/{TRACK_ID}"
ALBUM_URL = "https://open.spotify.com/album/1DFixLWuPkv3KT3TnV35m3"
PLAYLIST_URL = "https://open.spotify.com/playlist/37i9dQZF1DXcBWIGoYBM5M"
ARTIST_URL = "https://open.spotify.com/artist/4tZwfgrHOc3mvqYlEYSvVi"


def _recorded_inspect_factory(root: Path) -> SpotdlInspector:
    """A production inspector whose SpotDL runner writes the recorded metadata.

    The runner performs the same side effect the real `spotdl save` would — one
    metadata document at the requested `--save-file` — so the production adapter
    is held to the identical inspection contract without invoking SpotDL.
    """
    payload = (root / "providers" / "spotdl_metadata.json").read_text(encoding="utf-8")

    def runner(
        argv: Sequence[str],
        *,
        timeout: float,
        cancelled: object = None,
        env: dict[str, str] | None = None,
    ) -> SubprocessResult:
        save_file = Path(argv[argv.index("--save-file") + 1])
        save_file.write_text(payload, encoding="utf-8")
        return SubprocessResult(returncode=0, stdout="", stderr="")

    return SpotdlInspector(runner=runner)


INSPECTOR_FACTORIES: list[tuple[str, Callable[[Path], LinkInspector]]] = [
    ("fixture", lambda root: FixtureSpotdlInspector(fixture_root=root)),
    ("production", _recorded_inspect_factory),
]


@pytest.fixture
def fixture_root(disposable_root: Path) -> Path:
    root = disposable_root / "fixtures"
    shutil.copytree(FIXTURES, root)
    return root


@pytest.mark.contract
@pytest.mark.parametrize(("name", "factory"), INSPECTOR_FACTORIES)
class TestSpotdlInspectorContract:
    def test_a_track_url_is_supported(
        self, name: str, factory: Callable[[Path], LinkInspector], fixture_root: Path
    ) -> None:
        inspector = factory(fixture_root)

        assert inspector.supports(TRACK_URL)
        assert inspector.supports(INTL_TRACK_URL)

    def test_a_foreign_host_is_not_supported(
        self, name: str, factory: Callable[[Path], LinkInspector], fixture_root: Path
    ) -> None:
        assert not factory(fixture_root).supports("https://www.youtube.com/watch?v=u7K72X4eo_s")

    def test_a_supported_track_inspects_to_a_normalized_candidate(
        self, name: str, factory: Callable[[Path], LinkInspector], fixture_root: Path
    ) -> None:
        candidate = factory(fixture_root).inspect(TRACK_URL, None)

        assert candidate.provider == "spotify"
        assert candidate.title
        assert candidate.artist
        assert candidate.source_id == TRACK_ID
        assert candidate.source_url == TRACK_URL
        assert candidate.acquisition_locator == TRACK_URL
        assert candidate.isrc == "USQX91300108"
        assert candidate.duration_ms is not None and candidate.duration_ms > 0
        assert not candidate.is_playable

    @pytest.mark.parametrize("url", [ALBUM_URL, PLAYLIST_URL, ARTIST_URL])
    def test_a_collection_link_is_rejected_before_invocation(
        self,
        name: str,
        factory: Callable[[Path], LinkInspector],
        fixture_root: Path,
        url: str,
    ) -> None:
        with pytest.raises(UnsupportedEntityError):
            factory(fixture_root).inspect(url, None)


@pytest.mark.contract
class TestSpotdlWireNormalization:
    """The SpotDL metadata contract, shared by every adapter that parses it."""

    def _candidate(self, payload: object):
        return candidate_from_metadata(payload, track_id=TRACK_ID, canonical_url=TRACK_URL)

    def test_the_first_named_artist_is_used(self) -> None:
        candidate = self._candidate(
            [{"name": "Instant Crush", "artists": ["Daft Punk", "Julian Casablancas"]}]
        )

        assert candidate.artist == "Daft Punk"

    def test_more_than_one_song_is_refused(self) -> None:
        with pytest.raises(ProviderResponseError):
            self._candidate([{"name": "A", "artist": "X"}, {"name": "B", "artist": "Y"}])

    def test_an_empty_result_is_refused(self) -> None:
        with pytest.raises(ProviderResponseError):
            self._candidate([])

    def test_a_non_object_is_refused(self) -> None:
        with pytest.raises(ProviderResponseError):
            self._candidate("not a song")

    def test_an_insecure_cover_is_dropped(self) -> None:
        candidate = self._candidate(
            [{"name": "A", "artist": "X", "cover_url": "http://cdn.invalid/c.jpg"}]
        )

        assert candidate.artwork_url is None

    def test_a_malformed_isrc_is_dropped_rather_than_failing(self) -> None:
        candidate = self._candidate([{"name": "A", "artist": "X", "isrc": "nope"}])

        assert candidate.isrc is None

    def test_a_duration_is_normalized_to_milliseconds(self) -> None:
        candidate = self._candidate([{"name": "A", "artist": "X", "duration": 337.56}])

        assert candidate.duration_ms == 337_560


def _track_candidate() -> TrackCandidate:
    return TrackCandidate(
        provider="spotify",
        source_id=TRACK_ID,
        source_url=TRACK_URL,
        title="Instant Crush",
        artist="Daft Punk",
        album="Random Access Memories",
        release_year=2013,
        disc_number=1,
        track_number=5,
        duration_ms=337_560,
        isrc="USQX91300108",
        artwork_url=None,
        acquisition_locator=TRACK_URL,
        raw_fingerprint=None,
    )


def _download_runner(
    *,
    returncode: int = 0,
    produce_mp3: bool = True,
    captured: list[list[str]] | None = None,
    captured_env: list[dict[str, str] | None] | None = None,
) -> Callable[..., SubprocessResult]:
    """A SpotDL download runner double that leaves one MP3 in the output dir."""

    def runner(
        argv: Sequence[str],
        *,
        timeout: float,
        cancelled: object = None,
        env: dict[str, str] | None = None,
    ) -> SubprocessResult:
        if captured is not None:
            captured.append(list(argv))
        if captured_env is not None:
            captured_env.append(env)
        if produce_mp3 and returncode == 0:
            out_template = argv[argv.index("--output") + 1]
            out_dir = Path(out_template).parent
            shutil.copyfile(GATE_TONE, out_dir / "acquired.mp3")
        return SubprocessResult(returncode=returncode, stdout="", stderr="")

    return runner


@pytest.mark.contract
class TestSpotdlAcquisitionContract:
    def test_a_track_yields_one_valid_mp3(self, tmp_path: Path) -> None:
        adapter = SpotdlAcquisitionProvider(runner=_download_runner())
        artifact = adapter.acquire(
            _track_candidate(), str(tmp_path), None, lambda _phase, _p: None, lambda: False
        )

        acquired = Path(artifact.location)
        assert acquired.is_file()
        assert acquired.parent == tmp_path
        assert artifact.byte_size > 0
        assert artifact.duration_ms is not None and artifact.duration_ms > 0

    def test_a_cancellation_before_work_leaves_the_workspace_empty(self, tmp_path: Path) -> None:
        adapter = SpotdlAcquisitionProvider(runner=_download_runner())
        with pytest.raises(AcquisitionCancelledError):
            adapter.acquire(
                _track_candidate(), str(tmp_path), None, lambda _phase, _p: None, lambda: True
            )

        assert list(tmp_path.iterdir()) == []

    def test_a_nonzero_exit_fails_and_cleans_up(self, tmp_path: Path) -> None:
        adapter = SpotdlAcquisitionProvider(runner=_download_runner(returncode=1))
        with pytest.raises(AcquisitionFailedError):
            adapter.acquire(
                _track_candidate(), str(tmp_path), None, lambda _phase, _p: None, lambda: False
            )

        assert list(tmp_path.iterdir()) == []

    def test_exit_zero_without_an_mp3_still_fails(self, tmp_path: Path) -> None:
        adapter = SpotdlAcquisitionProvider(runner=_download_runner(produce_mp3=False))
        with pytest.raises(AcquisitionFailedError):
            adapter.acquire(
                _track_candidate(), str(tmp_path), None, lambda _phase, _p: None, lambda: False
            )


def _save_runner(
    *,
    captured: list[list[str]] | None = None,
    captured_env: list[dict[str, str] | None] | None = None,
) -> Callable[..., SubprocessResult]:
    """A SpotDL `save` runner double that writes the recorded metadata document."""

    def runner(
        argv: Sequence[str],
        *,
        timeout: float,
        cancelled: object = None,
        env: dict[str, str] | None = None,
    ) -> SubprocessResult:
        if captured is not None:
            captured.append(list(argv))
        if captured_env is not None:
            captured_env.append(env)
        Path(argv[argv.index("--save-file") + 1]).write_text(
            (FIXTURES / "providers" / "spotdl_metadata.json").read_text(encoding="utf-8"),
            encoding="utf-8",
        )
        return SubprocessResult(returncode=0, stdout="", stderr="")

    return runner


@pytest.mark.contract
class TestSpotdlCliContract:
    """The exact SpotDL argument vector, pinned in one place as the plan requires."""

    def test_the_download_invocation_names_the_track_output_and_mp3_format(
        self, tmp_path: Path
    ) -> None:
        captured: list[list[str]] = []
        adapter = SpotdlAcquisitionProvider(
            executable="/opt/spotdl/bin/spotdl", runner=_download_runner(captured=captured)
        )
        adapter.acquire(
            _track_candidate(),
            str(tmp_path),
            "socks5://p.invalid:1080",
            lambda _phase, _p: None,
            lambda: False,
        )

        argv = captured[0]
        assert argv[:3] == ["/opt/spotdl/bin/spotdl", "download", TRACK_URL]
        assert "--format" in argv and argv[argv.index("--format") + 1] == "mp3"
        assert argv[argv.index("--output") + 1].startswith(str(tmp_path))

    def test_the_save_invocation_names_the_url_and_a_save_file(self, tmp_path: Path) -> None:
        captured: list[list[str]] = []
        SpotdlInspector(
            executable="/opt/spotdl/bin/spotdl", runner=_save_runner(captured=captured)
        ).inspect(TRACK_URL, None)

        argv = captured[0]
        assert argv[:3] == ["/opt/spotdl/bin/spotdl", "save", TRACK_URL]
        assert "--save-file" in argv


@pytest.mark.contract
class TestSpotdlProxyEnvironmentContract:
    """The proxy must reach SpotDL's child process environment, never argv.

    A proxy on argv is visible in `ps` output to any user on the host — a
    credential leak if the saved proxy carries one — and it does not cover the
    `requests`/urllib3 traffic SpotDL uses internally, which is what actually
    needs to go through the proxy. ARCHITECTURE's SpotDL contract calls for
    "the saved proxy exported only to the child"; these cases pin that down.
    """

    PROXY = "socks5://user:hunter2@p.invalid:1080"

    def test_the_proxy_never_appears_on_the_save_argv(self, tmp_path: Path) -> None:
        captured: list[list[str]] = []
        SpotdlInspector(
            executable="/opt/spotdl/bin/spotdl", runner=_save_runner(captured=captured)
        ).inspect(TRACK_URL, self.PROXY)

        argv = captured[0]
        assert "--proxy" not in argv
        assert not any(self.PROXY in arg or "hunter2" in arg for arg in argv)

    def test_the_proxy_never_appears_on_the_download_argv(self, tmp_path: Path) -> None:
        captured: list[list[str]] = []
        adapter = SpotdlAcquisitionProvider(
            executable="/opt/spotdl/bin/spotdl", runner=_download_runner(captured=captured)
        )
        adapter.acquire(
            _track_candidate(), str(tmp_path), self.PROXY, lambda _phase, _p: None, lambda: False
        )

        argv = captured[0]
        assert "--proxy" not in argv
        assert not any(self.PROXY in arg or "hunter2" in arg for arg in argv)

    def test_the_proxy_reaches_the_save_child_environment(self, tmp_path: Path) -> None:
        captured_env: list[dict[str, str] | None] = []
        SpotdlInspector(
            executable="/opt/spotdl/bin/spotdl", runner=_save_runner(captured_env=captured_env)
        ).inspect(TRACK_URL, self.PROXY)

        env = captured_env[0]
        assert env is not None
        # socks5:// is converted to socks5h:// so DNS resolves through the
        # proxy rather than locally — see `_proxy_for_child_env`.
        expected = "socks5h://user:hunter2@p.invalid:1080"
        assert env["HTTP_PROXY"] == expected
        assert env["HTTPS_PROXY"] == expected
        assert env["http_proxy"] == expected
        assert env["https_proxy"] == expected

    def test_the_proxy_reaches_the_download_child_environment(self, tmp_path: Path) -> None:
        captured_env: list[dict[str, str] | None] = []
        adapter = SpotdlAcquisitionProvider(
            executable="/opt/spotdl/bin/spotdl",
            runner=_download_runner(captured_env=captured_env),
        )
        adapter.acquire(
            _track_candidate(), str(tmp_path), self.PROXY, lambda _phase, _p: None, lambda: False
        )

        env = captured_env[0]
        assert env is not None
        expected = "socks5h://user:hunter2@p.invalid:1080"
        assert env["HTTP_PROXY"] == expected
        assert env["HTTPS_PROXY"] == expected

    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("socks5://p.invalid:1080", "socks5h://p.invalid:1080"),
            ("socks5h://p.invalid:1080", "socks5h://p.invalid:1080"),
            ("http://p.invalid:8080", "http://p.invalid:8080"),
            ("https://p.invalid:8443", "https://p.invalid:8443"),
        ],
    )
    def test_the_scheme_conversion_is_exactly_socks5_to_socks5h(
        self, tmp_path: Path, raw: str, expected: str
    ) -> None:
        captured_env: list[dict[str, str] | None] = []
        SpotdlInspector(
            executable="/opt/spotdl/bin/spotdl", runner=_save_runner(captured_env=captured_env)
        ).inspect(TRACK_URL, raw)

        env = captured_env[0]
        assert env is not None
        assert env["HTTP_PROXY"] == expected
        assert env["HTTPS_PROXY"] == expected

    def test_no_proxy_configured_means_no_proxy_argv_flag_and_no_env(self, tmp_path: Path) -> None:
        captured: list[list[str]] = []
        captured_env: list[dict[str, str] | None] = []
        SpotdlInspector(
            executable="/opt/spotdl/bin/spotdl",
            runner=_save_runner(captured=captured, captured_env=captured_env),
        ).inspect(TRACK_URL, None)

        assert "--proxy" not in captured[0]
        # None tells the runner to inherit this process's environment
        # unchanged (`subprocess.Popen(env=None)`); no proxy env is injected.
        assert captured_env[0] is None

    def test_the_child_still_inherits_variables_it_needs(self, tmp_path: Path) -> None:
        captured_env: list[dict[str, str] | None] = []
        SpotdlInspector(
            executable="/opt/spotdl/bin/spotdl", runner=_save_runner(captured_env=captured_env)
        ).inspect(TRACK_URL, self.PROXY)

        env = captured_env[0]
        assert env is not None
        assert env["PATH"] == os.environ["PATH"]

    def test_a_credentialed_proxy_never_appears_in_a_raised_error_message(
        self, tmp_path: Path
    ) -> None:
        def failing_runner(
            argv: Sequence[str],
            *,
            timeout: float,
            cancelled: object = None,
            env: dict[str, str] | None = None,
        ) -> SubprocessResult:
            return SubprocessResult(returncode=1, stdout="", stderr="boom")

        with pytest.raises(ProviderResponseError) as excinfo:
            SpotdlInspector(executable="/opt/spotdl/bin/spotdl", runner=failing_runner).inspect(
                TRACK_URL, self.PROXY
            )

        assert self.PROXY not in str(excinfo.value)
        assert "hunter2" not in str(excinfo.value)
        assert "hunter2" not in repr(excinfo.value.context)
