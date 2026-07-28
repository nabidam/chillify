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

**Next active cycle:** 003 — Discovery and bulk acquisition.

## 003 — Discovery and bulk acquisition

Expand collection building with favorites, grouped Spotify-style search, Spotify album/playlist and YouTube playlist imports, and configurable download format/quality.

## 004 — Existing library integration

Import, scan, and reconcile existing music folders while preserving user files, detecting duplicates, and surfacing metadata conflicts safely.

## 005 — Playback and client expansion

Add mobile-browser UX, shuffle/repeat, crossfade and gapless guarantees, restored queues, and packaging/support beyond Arch Linux.
