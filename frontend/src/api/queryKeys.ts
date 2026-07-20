/**
 * Query keys for server state.
 *
 * Library, jobs, and settings are global. Only playlists are scoped to the
 * active profile, so only they carry a profile ID.
 */
export const queryKeys = {
  systemStatus: ["system", "status"] as const,
} as const;
