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
  /**
   * The Deezer query carries a submission token rather than the live input:
   * local search reacts to typing, online search happens only when the person
   * presses the button, and the token is what separates the two.
   */
  deezerSearch: (submission: string) => ["search", "deezer", submission] as const,
  downloads: (state?: string) => ["downloads", "list", state ?? "all"] as const,
  download: (jobId: string) => ["downloads", "detail", jobId] as const,
} as const;

/** Everything invalidated when a download changes the library. */
export const LIBRARY_QUERY_PREFIX = ["library"] as const;
export const DOWNLOADS_QUERY_PREFIX = ["downloads"] as const;
