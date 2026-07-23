import { Outlet } from "react-router";
import { AppSidebar } from "@/app/AppSidebar";
import { EventBridge } from "@/app/EventBridge";
import { RouteErrorBoundary } from "@/app/RouteErrorBoundary";
import { TopBar } from "@/app/TopBar";
import { SidebarInset, SidebarProvider } from "@/components/ui/sidebar";
import { PersistentPlayer } from "@/features/player/PersistentPlayer";
import { DegradedBanner } from "@/features/shared/DegradedBanner";

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
      {/* First focusable stop, so keyboard traversal can jump the sidebar and
          top bar and land on the content the person came for. */}
      <a
        href="#content"
        className="sr-only rounded-md bg-surface-raised px-4 py-2 text-foreground focus:not-sr-only focus:absolute focus:top-2 focus:left-2 focus:z-50 focus-visible:outline-2 focus-visible:outline-focus"
      >
        Skip to content
      </a>
      <SidebarProvider>
        <AppSidebar />
        <SidebarInset className="flex h-screen min-w-0 flex-col bg-surface">
          <TopBar />

          <DegradedBanner />

          <main
            id="content"
            className="min-h-0 flex-1 overflow-y-auto px-5 py-5"
            aria-label="Content"
          >
            <div className="mx-auto w-full max-w-content-max">
              <RouteErrorBoundary>
                <Outlet />
              </RouteErrorBoundary>
            </div>
          </main>

          <PersistentPlayer />
        </SidebarInset>
      </SidebarProvider>
    </EventBridge>
  );
}
