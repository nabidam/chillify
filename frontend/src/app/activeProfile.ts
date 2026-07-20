import { createContext, use } from "react";

/**
 * The active-profile session.
 *
 * Mounted once by `AppProviders`. A profile is a browser-session choice, not a
 * credential: it selects whose playlists are shown and nothing else.
 */
export interface ActiveProfileSession {
  activeProfileId: string | null;
  selectProfile: (profileId: string) => void;
  clearProfile: () => void;
}

export const ActiveProfileContext = createContext<ActiveProfileSession | null>(null);

export function useActiveProfile(): ActiveProfileSession {
  const session = use(ActiveProfileContext);
  if (session === null) {
    throw new Error("useActiveProfile must be used inside AppProviders.");
  }
  return session;
}

/** Survives a reload so a refresh does not send the household back through S1. */
export const ACTIVE_PROFILE_STORAGE_KEY = "chillify.active-profile";
