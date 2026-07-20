import { HttpResponse, http } from "msw";
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

export const handlers = [
  http.get("/api/v1/system/status", () => HttpResponse.json(systemStatusFixture())),
];
