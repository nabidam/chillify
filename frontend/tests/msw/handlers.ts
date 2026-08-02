import { HttpResponse, http } from "msw";
import type { ArtworkStage, Playlist, Profile, TrackDetail, TrackSummary } from "@/api/client";
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
    ],
    providers: [
      { name: "deezer", enabled: true, configured: true },
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

export function playlistFixture(overrides: Partial<Playlist> = {}): Playlist {
  return {
    id: "019f8000-0000-7000-8000-0000000000c1",
    profile_id: profileFixture().id,
    name: "Sunday Morning",
    track_count: 0,
    revision: 1,
    created_at: "2026-07-20T12:00:00.000Z",
    updated_at: "2026-07-20T12:00:00.000Z",
    ...overrides,
  };
}

export function trackDetailFixture(overrides: Partial<TrackDetail> = {}): TrackDetail {
  return {
    track: trackSummaryFixture(),
    has_artwork: false,
    sources: [
      {
        provider: "deezer",
        source_id: "3135556",
        source_url: "https://www.deezer.com/track/3135556",
      },
    ],
    ...overrides,
  };
}

export function artworkStageFixture(overrides: Partial<ArtworkStage> = {}): ArtworkStage {
  return {
    id: "019f8000-0000-7000-8000-0000000000d1",
    mime_type: "image/jpeg",
    size_bytes: 24_576,
    origin: "upload",
    created_at: "2026-07-20T12:00:00.000Z",
    expires_at: "2026-07-20T13:00:00.000Z",
    ...overrides,
  };
}

export const handlers = [
  http.get("/api/v1/system/status", () => HttpResponse.json(systemStatusFixture())),
  http.get("/api/v1/profiles/:profileId/playlists", () =>
    HttpResponse.json({ items: [], next_cursor: null }),
  ),
  http.get("/api/v1/profiles", () =>
    HttpResponse.json({ items: [profileFixture()], next_cursor: null }),
  ),
  http.get("/api/v1/library/tracks", () =>
    HttpResponse.json({ items: [trackSummaryFixture()], next_cursor: null }),
  ),
  http.get("/api/v1/search/deezer", () =>
    HttpResponse.json({ items: [remoteResultFixture()], next_cursor: null }),
  ),
  http.get("/api/v1/search/catalog", () =>
    HttpResponse.json({ items: [remoteResultFixture()], next_cursor: null }),
  ),
  http.get("/api/v1/radio-javan/search", ({ request }) => {
    const query = new URL(request.url).searchParams.get("q") ?? "";
    return HttpResponse.json({
      items: [
        remoteResultFixture(
          {},
          {
            provider: "radiojavan",
            source_id: "900001",
            source_url: "https://play.radiojavan.com/song/900001",
            title: "Radio Javan Search Fixture",
            artist: "Radio Javan Ensemble",
            acquisition_locator: "900001",
          },
        ),
      ],
      next_cursor: null,
      query,
    });
  }),
  http.get("/api/v1/radio-javan/tracks", ({ request }) => {
    const section = new URL(request.url).searchParams.get("section") ?? "featured";
    const id = section === "featured" ? "900002" : "900004";
    return HttpResponse.json({
      items: [
        remoteResultFixture(
          {},
          {
            provider: "radiojavan",
            source_id: id,
            source_url: `https://play.radiojavan.com/song/${id}`,
            title: section === "featured" ? "Featured Fixture" : "Trending Fixture",
            artist: "Radio Javan Ensemble",
            acquisition_locator: id,
          },
        ),
      ],
      next_cursor: null,
    });
  }),
  http.post("/api/v1/links/spotify/matches", () =>
    HttpResponse.json({
      reference: {
        spotify_id: "2cGxRwrMyEAp8dEbuZaVv6",
        canonical_url: "https://open.spotify.com/track/2cGxRwrMyEAp8dEbuZaVv6",
        title: "Instant Crush",
        thumbnail_url: "https://i.scdn.co/image/reference",
      },
      items: [remoteResultFixture()],
    }),
  ),
  http.get("/api/v1/downloads", () => HttpResponse.json({ items: [], next_cursor: null })),
  http.post("/api/v1/downloads", () => HttpResponse.json(jobFixture(), { status: 201 })),
];
