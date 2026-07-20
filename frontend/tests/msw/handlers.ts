import { HttpResponse, http } from "msw";
import type { Profile, TrackSummary } from "@/api/client";
import type { SystemStatus } from "@/app/useSystemStatus";
import type { DownloadJob } from "@/features/downloads/downloadJobs";
import type { RemoteResult, TrackCandidate } from "@/features/search/remoteSearch";

export function systemStatusFixture(overrides: Partial<SystemStatus> = {}): SystemStatus {
  return {
    ready: true,
    degraded: false,
    environment: "production",
    checked_at: "2026-07-20T12:00:00.000Z",
    database: { name: "database", health: "ok", detail: "migrated to 0001_core" },
    storage: [
      { name: "data_root", health: "ok", detail: "40960 MiB free" },
      { name: "music_root", health: "ok", detail: "40960 MiB free" },
    ],
    redis: { name: "redis", health: "ok", detail: "queue transport reachable" },
    tools: [
      { name: "ffmpeg", health: "ok", detail: null },
      { name: "ffprobe", health: "ok", detail: null },
      { name: "yt_dlp", health: "ok", detail: null },
      { name: "spotdl", health: "ok", detail: null },
      { name: "deno", health: "ok", detail: null },
    ],
    providers: [
      { name: "deezer", enabled: true, configured: true },
      { name: "spotdl", enabled: true, configured: true },
      { name: "yt_dlp", enabled: true, configured: true },
      { name: "lastfm", enabled: false, configured: false },
    ],
    ...overrides,
  };
}

export function profileFixture(overrides: Partial<Profile> = {}): Profile {
  return {
    id: "019f8000-0000-7000-8000-000000000001",
    name: "Household",
    created_at: "2026-07-20T12:00:00.000Z",
    updated_at: "2026-07-20T12:00:00.000Z",
    ...overrides,
  };
}

export function trackSummaryFixture(overrides: Partial<TrackSummary> = {}): TrackSummary {
  return {
    id: "019f8000-0000-7000-8000-0000000000a1",
    title: "Hoppipolla",
    artist: "Sigur Rós",
    album: "Takk...",
    release_year: 2005,
    disc_number: 1,
    track_number: 4,
    duration_ms: 268000,
    artist_key: "c2lndXIgcm9z",
    album_key: "c2lndXIgcm9zAHRha2s",
    availability: "available",
    is_playable: true,
    revision: 1,
    created_at: "2026-07-20T12:00:00.000Z",
    updated_at: "2026-07-20T12:00:00.000Z",
    ...overrides,
  };
}

export function remoteResultFixture(
  overrides: Partial<RemoteResult> = {},
  candidateOverrides: Partial<TrackCandidate> = {},
): RemoteResult {
  return {
    candidate: {
      provider: "deezer",
      source_id: "3135556",
      source_url: "https://www.deezer.com/track/3135556",
      title: "Harder Better Faster Stronger",
      artist: "Daft Punk",
      album: "Discovery",
      release_year: null,
      disc_number: null,
      track_number: null,
      duration_ms: 224000,
      isrc: "GBDUW0000059",
      artwork_url: null,
      acquisition_locator: "ytsearch1:Daft Punk Harder Better Faster Stronger",
      raw_fingerprint: null,
      ...candidateOverrides,
    },
    is_playable: false,
    existing_track_id: null,
    ...overrides,
  };
}

export function jobFixture(overrides: Partial<DownloadJob> = {}): DownloadJob {
  return {
    id: "019f8000-0000-7000-8000-0000000000b1",
    provider: "yt_dlp",
    source_type: "deezer_result",
    state: "queued",
    display_state: "queued",
    phase: "accepted",
    progress_percent: null,
    restart_count: 0,
    parent_job_id: null,
    error_code: null,
    error_message: null,
    result_track_id: null,
    version: 1,
    created_at: "2026-07-20T12:00:00.000Z",
    started_at: null,
    finished_at: null,
    updated_at: "2026-07-20T12:00:00.000Z",
    ...overrides,
  };
}

export const handlers = [
  http.get("/api/v1/system/status", () => HttpResponse.json(systemStatusFixture())),
  http.get("/api/v1/profiles", () =>
    HttpResponse.json({ items: [profileFixture()], next_cursor: null }),
  ),
  http.get("/api/v1/library/tracks", () =>
    HttpResponse.json({ items: [trackSummaryFixture()], next_cursor: null }),
  ),
  http.get("/api/v1/search/deezer", () =>
    HttpResponse.json({ items: [remoteResultFixture()], next_cursor: null }),
  ),
  http.get("/api/v1/downloads", () => HttpResponse.json({ items: [], next_cursor: null })),
  http.post("/api/v1/downloads", () => HttpResponse.json(jobFixture(), { status: 201 })),
];
