import { Navigate, Route, Routes } from "react-router";
import { PendingScreen } from "@/app/PendingScreen";
import { PersistentShell } from "@/app/PersistentShell";
import { routes } from "@/app/routes";

/**
 * Route table for the persistent shell.
 *
 * Screens S2-S12 all render inside `PersistentShell`, so navigating between
 * them replaces only the content viewport. The screens themselves arrive in
 * later chunks; each route is registered now so the shell's navigation,
 * history, and player continuity are real rather than simulated.
 */
export function AppRoutes() {
  return (
    <Routes>
      <Route element={<PersistentShell />}>
        <Route index element={<Navigate to={routes.library} replace />} />
        <Route path={routes.library} element={<PendingScreen title="Your Library" />} />
        <Route path={routes.search} element={<PendingScreen title="Search" />} />
        <Route path={routes.playlists} element={<PendingScreen title="Playlists" />} />
        <Route path={routes.downloads} element={<PendingScreen title="Downloads" />} />
        <Route path={routes.settings} element={<PendingScreen title="Settings" />} />
        <Route path="*" element={<PendingScreen title="Not found" />} />
      </Route>
    </Routes>
  );
}
