import { Navigate, Outlet, Route, Routes } from "react-router";
import { useActiveProfile } from "@/app/activeProfile";
import { PendingScreen } from "@/app/PendingScreen";
import { PersistentShell } from "@/app/PersistentShell";
import { RouteErrorBoundary } from "@/app/RouteErrorBoundary";
import { routes } from "@/app/routes";
import { DownloadsPage } from "@/features/downloads/DownloadsPage";
import { ContextPage } from "@/features/library/ContextPage";
import { LibraryPage } from "@/features/library/LibraryPage";
import { PlaylistPage } from "@/features/playlists/PlaylistPage";
import { PlaylistsPage } from "@/features/playlists/PlaylistsPage";
import { ProfileChooser } from "@/features/profiles/ProfileChooser";
import { RadioJavanPage } from "@/features/radioJavan/RadioJavanPage";
import { SearchPage } from "@/features/search/SearchPage";
import { SettingsPage } from "@/features/settings/SettingsPage";

/**
 * Route table for the persistent shell.
 *
 * Screens S2-S12 all render inside `PersistentShell`, so navigating between
 * them replaces only the content viewport. The remaining screens arrive in
 * later chunks; each route is registered now so the shell's navigation,
 * history, and player continuity are real rather than simulated.
 */
export function AppRoutes() {
  return (
    // An outer boundary so even the pre-shell screens (the profile chooser)
    // degrade to a recoverable message instead of a blank page; the shell's own
    // boundary catches content errors first and keeps the shell alive.
    <RouteErrorBoundary>
      <Routes>
        <Route path={routes.profiles} element={<ProfileGate />} />
        <Route element={<RequireProfile />}>
          <Route element={<PersistentShell />}>
            <Route index element={<Navigate to={routes.library} replace />} />
            <Route path={routes.library} element={<LibraryPage />} />
            <Route
              path="/library/artists/:contextKey"
              element={<ContextPage kind="artist" />}
            />
            <Route path="/library/albums/:contextKey" element={<ContextPage kind="album" />} />
            <Route path="/library/years/:contextKey" element={<ContextPage kind="year" />} />
            <Route path={routes.search} element={<SearchPage />} />
            <Route path={routes.radioJavan} element={<RadioJavanPage />} />
            <Route path={`${routes.radioJavan}/search`} element={<RadioJavanPage />} />
            <Route path={routes.playlists} element={<PlaylistsPage />} />
            <Route path={`${routes.playlists}/:playlistId`} element={<PlaylistPage />} />
            <Route path={routes.downloads} element={<DownloadsPage />} />
            <Route path={routes.settings} element={<SettingsPage />} />
            <Route path="*" element={<PendingScreen title="Not found" />} />
          </Route>
        </Route>
      </Routes>
    </RouteErrorBoundary>
  );
}

/**
 * The shell is unreachable until a profile is chosen.
 *
 * A profile is not a credential — it decides whose playlists the shell shows,
 * so the shell has nothing coherent to render without one.
 */
/**
 * S1, or the library once a profile has been chosen.
 *
 * Choosing a profile is what opens the shell, so the chooser hands the person
 * straight through rather than leaving them on a screen they already answered.
 */
function ProfileGate() {
  const { activeProfileId } = useActiveProfile();
  return activeProfileId === null ? (
    <ProfileChooser />
  ) : (
    <Navigate to={routes.library} replace />
  );
}

function RequireProfile() {
  const { activeProfileId } = useActiveProfile();
  return activeProfileId === null ? <Navigate to={routes.profiles} replace /> : <Outlet />;
}
