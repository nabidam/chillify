/**
 * Shell route paths.
 *
 * Kept apart from the route table so navigation components can reference a
 * path without importing the router that renders them.
 */
export const routes = {
  profiles: "/profiles",
  library: "/library",
  search: "/search",
  radioJavan: "/radio-javan",
  playlists: "/playlists",
  downloads: "/downloads",
  settings: "/settings",
} as const;

/**
 * Links to one browse context (S6/S7/S8).
 *
 * A context is addressed by its derived key, so the key is percent-encoded into
 * the path here rather than at every call site.
 */
export const contextRoutes = {
  artist: (artistKey: string) => `/library/artists/${encodeURIComponent(artistKey)}`,
  album: (albumKey: string) => `/library/albums/${encodeURIComponent(albumKey)}`,
  year: (yearKey: string) => `/library/years/${encodeURIComponent(yearKey)}`,
} as const;
