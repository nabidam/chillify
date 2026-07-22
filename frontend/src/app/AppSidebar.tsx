import { Download, Library, ListMusic, Plus, Search, Settings, UserRound } from "lucide-react";
import { useState } from "react";
import { NavLink, useLocation } from "react-router";
import { useActiveProfile } from "@/app/activeProfile";
import { routes } from "@/app/routes";
import { Button } from "@/components/ui/button";
import {
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarGroup,
  SidebarGroupContent,
  SidebarGroupLabel,
  SidebarHeader,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
} from "@/components/ui/sidebar";
import { AddLinkDialog } from "@/features/acquisition/AddLinkDialog";
import { usePlaylists } from "@/features/playlists/playlistQueries";
import { cn } from "@/lib/cn";

const navigation = [
  { to: routes.library, label: "Library", icon: Library },
  { to: routes.search, label: "Search", icon: Search },
  { to: routes.playlists, label: "Playlists", icon: ListMusic },
  { to: routes.downloads, label: "Downloads", icon: Download },
  { to: routes.settings, label: "Settings", icon: Settings },
] as const;

/**
 * The shell's primary navigation.
 *
 * Below the desktop breakpoint the Shadcn Sidebar becomes a Sheet; that is a
 * functional fallback, not a mobile experience. The active item carries the
 * selected surface plus an accent marker, which is the only place accent
 * appears outside active media and real progress.
 */
export function AppSidebar() {
  const location = useLocation();
  const { activeProfileId } = useActiveProfile();
  const playlists = usePlaylists(activeProfileId).data ?? [];
  const [addOpen, setAddOpen] = useState(false);

  return (
    <Sidebar collapsible="offcanvas">
      <SidebarHeader className="gap-3 p-4">
        <div className="flex items-center gap-2">
          <img src="/chillify-mark.svg" alt="" aria-hidden="true" className="size-6" />
          <span className="type-section text-foreground">Chillify</span>
        </div>
        <Button
          variant="ghost"
          className="justify-start gap-2 text-foreground-muted hover:text-foreground"
        >
          <UserRound className="size-4" aria-hidden="true" />
          Choose profile
        </Button>
      </SidebarHeader>

      <SidebarContent>
        <SidebarGroup>
          <SidebarGroupContent>
            <SidebarMenu>
              {navigation.map((item) => {
                const isCurrent = location.pathname.startsWith(item.to);
                return (
                  <SidebarMenuItem key={item.to}>
                    <SidebarMenuButton asChild isActive={isCurrent}>
                      <NavLink
                        to={item.to}
                        aria-current={isCurrent ? "page" : undefined}
                        className={cn(
                          "relative gap-3",
                          isCurrent && "text-foreground",
                          isCurrent &&
                            "before:absolute before:left-0 before:h-4 before:w-0.5 before:rounded-pill before:bg-primary",
                        )}
                      >
                        <item.icon className="size-4" aria-hidden="true" />
                        <span>{item.label}</span>
                      </NavLink>
                    </SidebarMenuButton>
                  </SidebarMenuItem>
                );
              })}
            </SidebarMenu>
          </SidebarGroupContent>
        </SidebarGroup>

        <SidebarGroup>
          <SidebarGroupLabel>Your playlists</SidebarGroupLabel>
          <SidebarGroupContent>
            {activeProfileId === null ? (
              <p className="px-2 type-meta text-foreground-subtle">
                Playlist shortcuts appear once a profile is selected.
              </p>
            ) : playlists.length === 0 ? (
              <p className="px-2 type-meta text-foreground-subtle">
                No playlists on this profile yet.
              </p>
            ) : (
              <SidebarMenu>
                {playlists.map((playlist) => {
                  const to = `${routes.playlists}/${playlist.id}`;
                  const isCurrent = location.pathname === to;
                  return (
                    <SidebarMenuItem key={playlist.id}>
                      <SidebarMenuButton asChild isActive={isCurrent}>
                        <NavLink to={to} aria-current={isCurrent ? "page" : undefined}>
                          <ListMusic className="size-4" aria-hidden="true" />
                          <span className="truncate">{playlist.name}</span>
                        </NavLink>
                      </SidebarMenuButton>
                    </SidebarMenuItem>
                  );
                })}
              </SidebarMenu>
            )}
          </SidebarGroupContent>
        </SidebarGroup>
      </SidebarContent>

      <SidebarFooter className="p-4">
        <Button className="w-full justify-center gap-2" onClick={() => setAddOpen(true)}>
          <Plus className="size-4" aria-hidden="true" />
          Add music
        </Button>
      </SidebarFooter>

      <AddLinkDialog open={addOpen} onOpenChange={setAddOpen} />
    </Sidebar>
  );
}
