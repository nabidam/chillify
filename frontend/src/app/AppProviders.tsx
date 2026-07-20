import { QueryClient, QueryClientProvider, useQueryClient } from "@tanstack/react-query";
import { type ReactNode, useCallback, useMemo, useState } from "react";
import { BrowserRouter } from "react-router";
import {
  ACTIVE_PROFILE_STORAGE_KEY,
  ActiveProfileContext,
  type ActiveProfileSession,
} from "@/app/activeProfile";
import { AppRoutes } from "@/app/Router";
import { Toaster } from "@/components/ui/sonner";
import { TooltipProvider } from "@/components/ui/tooltip";
import { usePlayerStore } from "@/features/player/playerStore";

/**
 * Mounted once, above every route. The query client, router, active-profile
 * session, tooltip context, and toaster live here so a route transition never
 * remounts them.
 */
function createQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: {
        // Server state is invalidated by SSE, not by polling. Refetching on
        // window focus would fight that and hide staleness the UI must show.
        refetchOnWindowFocus: false,
        retry: 1,
        staleTime: 30_000,
      },
    },
  });
}

const defaultQueryClient = createQueryClient();

export function AppProviders({
  queryClient = defaultQueryClient,
}: {
  queryClient?: QueryClient;
}) {
  return (
    <QueryClientProvider client={queryClient}>
      <ActiveProfileProvider>
        <TooltipProvider delayDuration={200}>
          <BrowserRouter>
            <AppRoutes />
          </BrowserRouter>
          <Toaster />
        </TooltipProvider>
      </ActiveProfileProvider>
    </QueryClientProvider>
  );
}

function readStoredProfile(): string | null {
  try {
    return window.localStorage.getItem(ACTIVE_PROFILE_STORAGE_KEY);
  } catch {
    // Storage can be unavailable in a locked-down browser. The session then
    // lasts one page view, which is a degradation, not a failure.
    return null;
  }
}

function ActiveProfileProvider({ children }: { children: ReactNode }) {
  const queryClient = useQueryClient();
  const [activeProfileId, setActiveProfileId] = useState<string | null>(readStoredProfile);

  const selectProfile = useCallback((profileId: string) => {
    try {
      window.localStorage.setItem(ACTIVE_PROFILE_STORAGE_KEY, profileId);
    } catch {
      // See readStoredProfile: the choice still applies to this page view.
    }
    setActiveProfileId(profileId);
  }, []);

  const clearProfile = useCallback(() => {
    // Switching profiles stops playback and clears the session queue before
    // any profile-scoped query is invalidated.
    usePlayerStore.getState().clearSession();
    try {
      window.localStorage.removeItem(ACTIVE_PROFILE_STORAGE_KEY);
    } catch {
      // See readStoredProfile.
    }
    setActiveProfileId(null);
    void queryClient.invalidateQueries({ queryKey: ["playlists"] });
  }, [queryClient]);

  const session = useMemo<ActiveProfileSession>(
    () => ({ activeProfileId, selectProfile, clearProfile }),
    [activeProfileId, selectProfile, clearProfile],
  );

  return <ActiveProfileContext value={session}>{children}</ActiveProfileContext>;
}

export { createQueryClient };
