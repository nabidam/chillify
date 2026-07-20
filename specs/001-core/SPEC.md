---
status: gate-passed
profile: full
profile-reason: "M1 spans multiple independent subsystems and exceeds the lite feature-task boundary."
---

# Chillify Core

## Core promise

Chillify turns Deezer discoveries or pasted Spotify/YouTube track links into a clean, deduplicated, metadata-rich MP3 library that plays reliably over a trusted LAN.

## Kernel

1. Acquire one track through Deezer → yt-dlp, Spotify link → SpotDL, or YouTube link → yt-dlp.
2. Run downloads through a durable serial queue with clear progress, cancellation, retry, and restart recovery.
3. Store organized MP3s and artwork on mounted disk while keeping files, ID3 tags, and database metadata synchronized.
4. Search and browse the local library, then play artist, album, year, or playlist queues without interruption during navigation.
5. Configure one global proxy and provider credentials/status while local playback remains usable during internet or Redis failure.

### Kernel journey

Select a named profile → search locally → deliberately search Deezer online → choose an unavailable result → watch it queue, download, convert, tag, and finish → find the deduplicated track locally → correct its metadata/artwork → add it to a personal playlist → play it and navigate elsewhere without interruption → restart Chillify and find the track, metadata, and playlist still intact.

## v1

**User-stated**

- Support Chromium and Firefox desktops over trusted-LAN HTTP with no auth. Anyone may create/switch name-only profiles and use every action; users create/edit personal playlists and queues are session-local.
- Search local tracks by default. A separate Deezer button clearly labels internet results as unplayable until downloaded.
- Accept only individual Spotify-track and YouTube-video links. Review YouTube title, artist, album, year, track/disc number, and cover before queueing.
- Run one durable job at a time. Surface queued, downloading, converting, tagging, completed, failed, cancelled, retrying, and restarted states globally; interrupted work restarts from the beginning.
- Create MP3 from the best source audio. Provider metadata wins; optional Last.fm only fills gaps. Edit metadata and replace art by upload, URL, or Last.fm.
- Store `Music/Artist/Album/NN - Track Title.mp3` with sanitized fallbacks. Edits synchronize database, ID3, artwork, and path.
- Reject duplicates by source identity, ISRC, then normalized artist/title. Confirmed deletion removes disk media first, then metadata and playlist/queue entries.
- Include play/pause, seek, volume, previous/next, and editable queue. Order album by disc/track; artist by album year then disc/track; year by artist/album/disc/track; playlist manually. Exclude shuffle/repeat.
- Put global proxy first in Settings. Once set, all outbound traffic fails closed through it. Include Last.fm key, provider enable/health, and read-only path, disk, and tool diagnostics.

**Kernel-derived**

- Keep playback usable without internet, providers, Last.fm, or Redis. Disable acquisition clearly; requeue unfinished database jobs when Redis returns.
- Persist data outside containers. Compose bind-mounts tracks and uses configurable host `REDIS_URL`; it creates no Redis service.
- Local files remain playable and seekable while moving through the SPA; refresh may stop playback and clear the session queue.

**Process-derived, approved**

- Provider fixtures plus job-recovery, duplicate, metadata, and deletion-safety tests.
- One Chromium journey, Firefox playback smoke, and Docker persistence/degraded-mode canary.

## Ranked backlog

1. Favorites; Spotify-style grouped search.
2. Spotify/YouTube bulk imports.
3. Configurable quality/format.
4. Existing-folder import/rescan.
5. Mobile UX.
6. Shuffle, repeat, crossfade, gapless, restored queues.
7. Non-Arch support.

## Edge cases

Missing years group under “Unknown Year”; missing files become unavailable without metadata loss. Partial moves/deletions roll back or self-repair; cancelled/failed jobs clean temporary files. Last.fm misses warn only. Provider/proxy errors retain actionable details. Exact identity overrides fuzzy duplicate signals.

## Non-functional requirements and constraints

Target one active user and 500 tracks: search ≤300 ms, LAN navigation ≤500 ms, playback start ≤1 s, job UI lag ≤2 s. Providers/downloads have no SLA. Navigation preserves audio. Meet WCAG 2.2 AA, including keyboard, focus, contrast, and reduced motion.

## Suggested stack

React, TypeScript, Vite, TanStack Query, Zustand, Tailwind tokens, and accessible headless primitives. FastAPI, Pydantic, SQLAlchemy/Alembic, SQLite WAL, Celery/host Redis, SSE, FFmpeg, SpotDL, yt-dlp, Mutagen, Docker Compose, and normal disk.

## Design direction

Personality: focused, familiar, premium. References: Spotify Web Player (primary), Plexamp, and YouTube Music. Use a dense desktop shell, original Chillify branding/assets, restrained motion, and WCAG 2.2 AA—not copied Spotify assets.

## Out of scope

Home/recommendations, backlog items above, direct Deezer audio, auth/permissions, TLS, object storage, and non-Arch packaging.
