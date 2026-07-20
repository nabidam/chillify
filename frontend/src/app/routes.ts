/**
 * Shell route paths.
 *
 * Kept apart from the route table so navigation components can reference a
 * path without importing the router that renders them.
 */
export const routes = {
  library: "/library",
  search: "/search",
  playlists: "/playlists",
  downloads: "/downloads",
  settings: "/settings",
} as const;
