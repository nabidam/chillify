---
status: gate-passed
---

# Chillify Core Product Requirements

## Product outcome

Chillify turns Deezer discoveries or pasted Spotify/YouTube track links into a clean, deduplicated, metadata-rich MP3 library that plays reliably over a trusted LAN.

## Kernel

1. Acquire one track through Deezer → yt-dlp, Spotify link → SpotDL, or YouTube link → yt-dlp.
2. Run downloads through a durable serial queue with clear progress, cancellation, retry, and restart recovery.
3. Store organized MP3s and artwork on mounted disk while keeping files, ID3 tags, and database metadata synchronized.
4. Search and browse the local library, then play artist, album, year, or playlist queues without interruption during navigation.
5. Configure one global proxy and provider credentials/status while local playback remains usable during internet or Redis failure.

### Kernel journey

Select a named profile → search locally → deliberately search Deezer online → choose an unavailable result → watch it queue, download, convert, tag, and finish → find the deduplicated track locally → correct its metadata/artwork → add it to a personal playlist → play it and navigate elsewhere without interruption → restart Chillify and find the track, metadata, and playlist still intact.

## Users and assumptions

- Chillify is operated by a trusted household on one Arch Linux host.
- One LAN browser is active at a time; the managed library contains at most 500 tracks.
- There is no authentication or authorization. Every visitor can download, edit, delete, and change settings.
- Name-only profiles separate playlists. The shared library, download queue, and settings are global.
- Playback and queue state belong to the current browser session and are discarded on refresh or profile switch.

## User stories

- **US1 — Discover:** As a listener, I want local results first and an explicit online search so I understand what is immediately playable.
- **US2 — Acquire:** As a listener, I want to download one Deezer result, Spotify track link, or YouTube video without keeping the browser open.
- **US3 — Understand progress:** As a listener, I want truthful global job states so I know whether a track is queued, downloading, processing, complete, or needs action.
- **US4 — Organize:** As a librarian, I want metadata, artwork, ID3 tags, database records, and disk paths to agree after every change.
- **US5 — Listen:** As a listener, I want to play tracks by artist, album, year, or playlist while navigating elsewhere.
- **US6 — Personalize:** As a named profile, I want personal playlists over the shared library.
- **US7 — Recover:** As an operator, I want local playback to survive provider/Redis outages and interrupted work to recover clearly.
- **US8 — Diagnose:** As an operator, I want proxy/provider/tool health in one settings view with actionable failures.

## v1 functional requirements

### FR-1 Profiles and shell

1. On first use, S1 shall require creation of a trimmed, unique, name-only profile.
2. S1 shall allow free profile switching without credentials. Switching shall stop playback and clear the session queue.
3. S2–S12 shall share persistent navigation, global job status, and a bottom player that is not remounted during content navigation.
4. S2 shall be the post-selection landing screen; v1 shall have no Home/recommendations screen.

### FR-2 Local library and search

1. S2 shall browse managed tracks as Tracks, Artists, Albums, and Years; manually added folders are excluded.
2. S3 shall search only local track title, artist, and album by default and shall make no provider request until Search Deezer is activated.
3. Deezer results shall be visually and semantically separate, identify their internet source, expose Download rather than Play, and link duplicates to the local record.
4. Missing files shall remain listed as unavailable and shall never cause silent metadata deletion.

### FR-3 Single-track acquisition

1. S3 shall download a selected Deezer track through the configured audio acquisition path.
2. S4 shall accept one Spotify track URL or one YouTube video URL. Album, playlist, channel, and other entity links shall be rejected.
3. A Spotify track shall enter the job queue after successful inspection and duplicate checking.
4. A YouTube video shall always pass through S5. Title and artist shall be reviewable and required before queueing; album, year, disc/track numbers, and artwork shall be optional and editable.
5. Internet results shall not become playable until a completed local track exists.

### FR-4 Durable serial jobs

1. The global queue shall run at most one job at a time and continue independently of any browser.
2. S11 and the shell shall expose queued, downloading, converting, tagging, completed, failed, cancelled, retrying, and restarted states.
3. Percentage progress shall appear only when reported by the active operation; otherwise the current phase shall appear without a fabricated percentage.
4. Users shall be able to cancel queued/running jobs and retry failed/cancelled jobs.
5. Host or service interruption shall return unfinished work to queued and restart it from the beginning.
6. Cancelled and failed jobs shall remove temporary media. Completed/failed history shall remain inspectable.

### FR-5 Metadata, artwork, storage, and duplicates

1. Output shall be MP3 produced from the best available source audio; quality selection is absent.
2. Provider metadata shall remain authoritative. Last.fm shall only fill missing values and shall never block completion.
3. S13 shall edit title, artist, album, year, disc/track numbers, and cover. Artwork replacement shall accept upload, remote URL, or Last.fm lookup.
4. A successful edit shall leave database values, embedded ID3, stored artwork, and `Music/Artist/Album/NN - Track Title.mp3` synchronized. Missing values shall use deterministic sanitized fallbacks.
5. Duplicate checks shall run in order: exact source identity, ISRC, normalized artist/title. Any match shall block creation and identify the existing track.
6. S15 shall disclose playlist/queue impact before deletion. Confirmed deletion shall remove disk media first, then metadata and all playlist/active-queue references; partial failure shall be repaired or rolled back before another mutation.

### FR-6 Playback and playlists

1. The player shall provide play/pause, seek, volume, previous/next, current-track identity, and S14 queue access. Shuffle and repeat shall not appear.
2. Starting a context shall replace the session queue: album by disc/track; artist by album year then disc/track; year by artist/album/disc/track; playlist by manual position.
3. Playing a row shall begin there and append remaining playable rows in the current view order.
4. Navigation among S2–S12 shall not pause, restart, or replace active playback.
5. S9/S16 shall create and rename profile-specific playlists. Every local track row shall support Add to Playlist.
6. S10 shall play, reorder, and remove playlist entries. Removing an entry shall not delete shared media.
7. S14 shall reorder, remove, or clear upcoming session items; the queue shall not persist after refresh/profile switch.

### FR-7 Settings and degraded operation

1. S12 shall place the optional global proxy first. Supported URLs shall include HTTP, HTTPS, and SOCKS5 with optional credentials.
2. Once saved, the proxy shall cover Deezer, Last.fm, SpotDL, yt-dlp, and artwork retrieval. A failed proxied request shall never retry directly.
3. S12 shall save/test the proxy; enable/test providers; accept a Last.fm API key; and show mounted path, free space, Redis, FFmpeg, SpotDL, and yt-dlp health.
4. Persisted secret values shall be masked on later reads and absent from user-visible technical errors.
5. Provider or internet failure shall not block local search, library browsing, playlists, metadata reads, or playback.
6. Redis failure shall disable new/retry acquisition, preserve local use, show degraded status, and requeue unfinished jobs when connectivity returns.

## Acceptance criteria

1. **Profiles:** Starting with no data shows S1. Creating “Household” opens S2. A second browser can select it without credentials and access all settings/actions.
2. **Local-first search:** With network requests recorded, entering a query displays matching local tracks and sends no provider request until Search Deezer is clicked.
3. **Remote distinction:** After online search, Deezer results appear in a separate labeled region with Download and no Play action; local results remain playable.
4. **Deezer acquisition:** Downloading one Deezer result creates one queued job. Closing the browser does not stop it; reopening shows its current/final state and a playable local track after completion.
5. **Link scope:** A Spotify track URL and YouTube video URL are accepted. Spotify album/playlist and YouTube playlist/channel URLs show a specific unsupported-entity error and create no job.
6. **YouTube review:** A valid YouTube URL opens S5; Queue Download remains unavailable while title or artist is blank and uses the submitted corrections after completion.
7. **Serial execution:** Queueing three tracks never produces more than one downloading/converting/tagging job at once; the remaining jobs stay queued in order.
8. **Cancellation/retry:** Cancelling an active job stops further phases, removes its temporary file, and advances the queue. Retry creates a new queued attempt linked to the failed/cancelled job.
9. **Restart recovery:** Restarting the services during a download causes the job to reappear as queued and restart from the beginning without creating a duplicate completed track.
10. **Duplicate rejection:** Re-submitting the same source, an equal ISRC, or normalized equal artist/title creates no file and links to the existing track.
11. **Metadata synchronization:** Changing artist, album, track number, and cover in S13 changes the displayed record, embedded MP3 tags/art, and mounted path. Restarting preserves the new values and no old file remains.
12. **Edit failure:** Forcing a file-move or tag-write failure leaves the previous playable record/path authoritative and exposes a retryable error.
13. **Deletion:** Confirming S15 removes the MP3/artwork, local record, every playlist entry, and any session occurrence. Restarting does not restore it.
14. **Context order:** Playing a seeded album, artist, year, and playlist produces exactly the orders specified by FR-6.2; S14 shows the same order.
15. **Persistent player:** While a local track plays, navigating through S2, S3, S9, S11, and S12 does not emit a pause or reset playback position.
16. **Session boundary:** Refreshing or switching profile stops playback and clears S14; saved playlists remain.
17. **Playlist ownership:** A playlist created under Profile A is absent under Profile B, while both profiles can play the same shared track.
18. **Proxy fail-closed:** With an intentionally invalid saved proxy, every outbound provider/artwork action fails with a proxy error and traffic inspection shows no direct attempt.
19. **Optional Last.fm:** With no API key or a forced Last.fm failure, a download with complete provider metadata still completes and displays a warning rather than failing.
20. **Redis degradation:** With Redis stopped, an already-local track remains searchable/playable and acquisition controls are disabled. Restoring Redis requeues unfinished work without restarting the web application.
21. **Mounted persistence:** Recreating application containers without deleting host data preserves tracks, profiles, playlists, metadata, settings, and job history.
22. **Empty/error states:** With no tracks, playlists, or jobs, S2, S9, and S11 each explain the state and expose the next valid action. Provider/library failures leave unrelated local playback usable.
23. **Settings health:** S12 shows saved/masked proxy and Last.fm configuration, enabled provider states, mounted path/free space, Redis availability, and FFmpeg/SpotDL/yt-dlp availability; disabling a provider prevents its online action without affecting local playback.

## Validation rules

| Input | Rule | Failure behavior |
|---|---|---|
| Profile name | Trimmed Unicode, 1–40 characters, unique by case-folded value | Inline error; preserve input |
| Playlist name | Trimmed Unicode, 1–100 characters, unique within profile by case-folded value | Inline error; preserve input/order |
| Search query | Trimmed, 1–200 characters before online submission | Disable online action; local empty query shows guidance |
| Track title/artist | Trimmed, 1–200 characters each | Block review/edit submission |
| Album | Optional; trimmed, at most 200 characters | Inline error |
| Year | Optional integer from 1000 through current year + 1 | Inline error; missing value groups as Unknown Year |
| Disc/track number | Optional integer 1–999 | Inline error |
| Spotify URL | HTTPS Spotify track entity resolving to one track | Reject unsupported/malformed entity; no job |
| YouTube URL | HTTPS URL resolving to one video; playlist context may be ignored but must not expand | Reject non-video/bulk entity; no job |
| Proxy URL | HTTP, HTTPS, or SOCKS5 URL with host; optional port and credentials | Reject before save; retain previous setting |
| Artwork upload | JPEG, PNG, or WebP; valid image content; at most 10 MiB | Reject without changing existing art |
| Artwork URL | HTTP/HTTPS; response must be an image and at most 10 MiB | Fail through configured proxy; retain existing art |
| Provider credential | Trim surrounding whitespace; never return stored secret value | Show configured/not-configured only |

Filesystem components shall remove control characters, reserved separators, leading/trailing dots/spaces, and traversal segments. Empty sanitized artist/album/title values shall use deterministic “Unknown Artist,” “Unknown Album,” or “Unknown Title” fallbacks. Colliding paths shall not overwrite another track.

## Error and edge behavior

- **Offline/provider timeout:** keep local content and player usable; identify the affected provider/action and expose retry or Settings.
- **Proxy failure:** distinguish malformed configuration, authentication, connection, and timeout where known; never bypass.
- **Last.fm miss/failure:** retain provider metadata and existing artwork; show a warning only.
- **Extractor/converter/tagger failure:** stop the job at its real phase, retain technical detail behind disclosure, clean temporary files, and allow retry.
- **Redis disconnect:** retain last known job state as stale, disable queue mutations, and reconnect without resetting UI history.
- **Event-stream disconnect:** continue polling/reconnect behavior without changing server-owned state or inventing progress.
- **Disk full/unwritable:** do not mark the job complete; keep prior files/metadata intact and expose required free-space/path action.
- **Missing managed file:** mark unavailable, skip during playback, preserve metadata, and allow permanent metadata cleanup through S15.
- **Concurrent edit/delete:** only one mutation may succeed; the other action must reload the current record and explain that it changed.
- **Track deleted while playing:** stop or advance to the next playable queue item and remove every remaining occurrence.
- **Unknown year:** show a normal “Unknown Year” context that links to S13 correction.
- **Empty library:** lead to S4 or S3; never imply filesystem import exists.
- **No online results:** preserve query/local results and state that Deezer returned none.
- **No reported progress:** show phase and elapsed time, never a fake percentage.

## Non-functional requirements

| ID | Requirement | Budget | Measurement |
|---|---|---|---|
| NFR-1 | Local search latency | 95th percentile ≤300 ms with 500 tracks | Seed 500 tracks; run 20 distinct searches in current Chromium on the LAN; record input-to-render duration and calculate p95 |
| NFR-2 | Client navigation latency | 95th percentile ≤500 ms for S2–S12 cached/local-data transitions | Record 20 route transitions with browser performance timing on the target Arch host/LAN and calculate p95 |
| NFR-3 | Local playback start | 95th percentile ≤1,000 ms from Play activation to audible/`playing` state | Start 10 representative mounted MP3s in each supported browser over LAN; capture click-to-media-event duration |
| NFR-4 | Job feedback freshness | State visible ≤2,000 ms after its server timestamp | Capture 20 job transitions; compare emitted transition timestamp with the first rendered matching state |
| NFR-5 | Navigation continuity | Zero pause, ended, source-reset, or backward-time events across 20 navigation transitions | Play a five-minute MP3, navigate S2–S12 twenty times, and record media events/current-time monotonicity |
| NFR-6 | Restart durability | 100% of seeded profiles, playlists, tracks, metadata, settings, and job history survive container recreation | Seed named records, recreate containers without deleting host data, and compare every visible record/file before and after |
| NFR-7 | Mutation consistency | Zero database/file/tag/art mismatches after successful operations or injected failures | Execute one successful edit/deletion and one injected failure at each mutation stage; audit visible metadata, MP3 tags, artwork, and mounted paths after recovery |
| NFR-8 | Accessibility | WCAG 2.2 AA; zero critical/serious automated violations; every action keyboard reachable | Audit every S-screen state with a WCAG 2.2 AA checker, then manually verify keyboard order, focus return, names, contrast, and reduced-motion behavior |
| NFR-9 | Browser support | Kernel journey succeeds in current stable Chromium and Firefox desktop | Run F1 in Chromium; repeat playback, navigation, seek, queue, modal focus, and download-status smoke in Firefox |
| NFR-10 | Degraded local availability | 100% of local browse/search/play/playlist-read actions remain usable during internet and Redis outage | Disconnect outbound network and Redis, then execute local portions of S2, S3, S6–S10, and player controls |
| NFR-11 | Secret redaction | Zero stored proxy/Last.fm secret values in API responses, UI errors, or application logs | Save unique sentinel secrets, exercise all settings/provider failures, export responses and logs, and search for the sentinels |
| NFR-12 | Storage placement | 100% of completed MP3/artwork and durable app data remain outside container writable layers | Complete downloads, inspect configured host paths, recreate containers, and verify identical files and records |

External provider response time and total download duration have no v1 latency budget because Chillify does not control them; the UI must expose elapsed phase/status instead.

## Constraints

- Deployment is Docker Compose on Arch Linux and serves trusted-LAN HTTP.
- Redis is supplied by the host through `REDIS_URL`; Compose shall not create it.
- Music uses a host-mounted normal filesystem; object storage is prohibited in v1.
- Only Chillify-managed downloads appear in the library.
- The desktop experience targets current stable Chromium and Firefox; mobile is not release-blocking.
- Provider and artwork network access must honor the saved global proxy.
- Spotify-quality UX means comparable hierarchy, feedback, and interaction coherence with original Chillify branding—not copied trademarks/assets.

## Out of scope

Home/recommendations, favorites, grouped multi-entity search, Spotify albums/playlists, YouTube playlists/channels, direct Deezer audio, configurable format/quality, existing-folder import/rescan, mobile UX, shuffle, repeat, crossfade, gapless guarantees, restored playback queues, authentication/permissions, TLS, object storage, and non-Arch packaging.

## Ranked future improvements

1. Favorites and grouped Spotify-style search.
2. Spotify/YouTube bulk acquisition.
3. Configurable download quality and format.
4. Existing-folder import and reconciliation.
5. Mobile browser experience.
6. Shuffle, repeat, crossfade, gapless guarantees, and restored queues.
7. Support beyond Arch Linux.
