import { Outlet } from "react-router";
import { AppSidebar } from "@/app/AppSidebar";
import { TopBar } from "@/app/TopBar";
import { SidebarInset, SidebarProvider } from "@/components/ui/sidebar";

/**
 * The four stable regions of screens S2-S12: sidebar, top bar, content
 * viewport, and the bottom player.
 *
 * Only the content viewport scrolls, and only it changes during navigation.
 * The player region is mounted here — above the route outlet — so a route
 * change can never remount the audio element.
 */
export function PersistentShell() {
  return (
    <SidebarProvider>
      <AppSidebar />
      <SidebarInset className="flex h-screen min-w-0 flex-col bg-surface">
        <TopBar />

        <main
          id="content"
          className="min-h-0 flex-1 overflow-y-auto px-5 py-5"
          aria-label="Content"
        >
          <div className="mx-auto w-full max-w-content-max">
            <Outlet />
          </div>
        </main>

        <PlayerRegion />
      </SidebarInset>
    </SidebarProvider>
  );
}

/**
 * The persistent player's region.
 *
 * The transport, artwork, and audio element arrive with the playback slice;
 * the region is reserved and mounted now so layout and continuity are real
 * from the first chunk rather than retrofitted later.
 */
function PlayerRegion() {
  return (
    <section
      aria-label="Player"
      className="flex h-player shrink-0 items-center border-t bg-canvas px-5"
    >
      <p className="type-meta text-foreground-subtle">
        Nothing is playing. Choose a track from your library to start.
      </p>
    </section>
  );
}
