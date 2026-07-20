import { Outlet } from "react-router";
import { AppSidebar } from "@/app/AppSidebar";
import { EventBridge } from "@/app/EventBridge";
import { TopBar } from "@/app/TopBar";
import { SidebarInset, SidebarProvider } from "@/components/ui/sidebar";
import { PersistentPlayer } from "@/features/player/PersistentPlayer";

/**
 * The four stable regions of screens S2-S12: sidebar, top bar, content
 * viewport, and the bottom player.
 *
 * Only the content viewport scrolls, and only it changes during navigation.
 * The player region is mounted here — above the route outlet — so a route
 * change can never remount the audio element. The event stream is established
 * at the same level, for the same reason.
 */
export function PersistentShell() {
  return (
    <EventBridge>
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

          <PersistentPlayer />
        </SidebarInset>
      </SidebarProvider>
    </EventBridge>
  );
}
