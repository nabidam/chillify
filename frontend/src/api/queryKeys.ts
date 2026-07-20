/**
 * Query keys for server state.
 *
 * Library, jobs, and settings are global. Only playlists are scoped to the
 * active profile, so only they carry a profile ID.
 */
import type { LibrarySort } from "@/api/client";

export interface LibraryTracksQuery {
  q?: string;
  sort?: LibrarySort;
}

export const queryKeys = {
  systemStatus: ["system", "status"] as const,
  profiles: ["profiles"] as const,
  libraryTracks: (query: LibraryTracksQuery = {}) =>
    ["library", "tracks", query.q ?? "", query.sort ?? "recent"] as const,
  track: (trackId: string) => ["library", "track", trackId] as const,
} as const;
