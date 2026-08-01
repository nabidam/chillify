# Chillify Roadmap

Each milestone is a separate release-gated specification cycle. Re-check this roadmap when a milestone closes; later scope remains intentionally coarse until its own cycle begins.

## 001 — Core acquisition and playback

Deliver the smallest complete downloader-first LAN player: single-track acquisition, durable jobs, synchronized disk metadata, local playback, personal playlists, provider settings, and Spotify-quality desktop structure.

## 002 — CANCELLED — Fast, legible Spotify link inspection

Child cycle spawned from 001's blocked Gate 4. Add a fast Spotify inspection path with automatic spotdl fallback, operator-configurable inspection mode and per-provider timeouts, and honest phase/elapsed/cancel feedback in Add Music.

**Status:** Cancelled 2026-07-29. Spotify's development-mode Web API requires
Premium for the app owner, which is not an acceptable project dependency. The
cycle's implementation and evidence remain archived under
`specs/002-spotify-inspection/`; unfinished work is deferred and any replacement
must begin with a new feasibility/specification pass.

**Next cycle:** 003 — Free discovery and Spotify references.

## 003 — COMPLETE — Free discovery and Spotify references

Deliver keyless MusicBrainz, Apple, and Deezer catalog search plus credential-free
Spotify track references through oEmbed and explicit match selection. Bulk
Spotify album/playlist import remains deferred because oEmbed cannot enumerate
collection tracks. See `specs/003-free-discovery/PLAN.md`.

**Status:** Completed and operator-tested 2026-07-29. Migration
`0004_catalog_track_sources` preserves Apple and MusicBrainz provenance.

**Next active cycle:** 004 — Radio Javan discovery and direct acquisition.

## 004 — Radio Javan discovery and direct acquisition

Add a dedicated anonymous Radio Javan search/explore experience for Featured and
Trending tracks, backed by exact direct Radio Javan acquisition rather than
cross-catalog results or yt-dlp matching. See `specs/004-radio-javan/PLAN.md`.

**Status:** Planned 2026-08-01; implementation has not started.

## 005 — Existing library integration

Import, scan, and reconcile existing music folders while preserving user files, detecting duplicates, and surfacing metadata conflicts safely.

## 006 — Playback and client expansion

Add mobile-browser UX, shuffle/repeat, crossfade and gapless guarantees, restored queues, and packaging/support beyond Arch Linux.
