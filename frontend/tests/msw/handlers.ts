import { HttpResponse, http } from "msw";
import type { Profile, TrackSummary } from "@/api/client";
import type { SystemStatus } from "@/app/useSystemStatus";

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

export const handlers = [
  http.get("/api/v1/system/status", () => HttpResponse.json(systemStatusFixture())),
  http.get("/api/v1/profiles", () =>
    HttpResponse.json({ items: [profileFixture()], next_cursor: null }),
  ),
  http.get("/api/v1/library/tracks", () =>
    HttpResponse.json({ items: [trackSummaryFixture()], next_cursor: null }),
  ),
];
