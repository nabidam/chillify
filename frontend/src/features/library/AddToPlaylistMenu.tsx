import { ListPlus } from "lucide-react";
import { useActiveProfile } from "@/app/activeProfile";
import { DropdownMenuItem, DropdownMenuLabel } from "@/components/ui/dropdown-menu";
import { useAddTrackToPlaylist, usePlaylists } from "@/features/playlists/playlistQueries";

/**
 * The "Add to playlist" section shared by every track row action.
 *
 * A household has a handful of playlists, so this is a flat section rather than
 * a submenu: one keystroke reaches any of them instead of two. It is meant to
 * sit inside an open `DropdownMenuContent`, after the row's own actions, so it
 * emits menu items directly rather than its own menu.
 */
export function AddToPlaylistMenu({ trackId }: { trackId: string }) {
  const { activeProfileId } = useActiveProfile();
  const playlists = usePlaylists(activeProfileId);
  const addToPlaylist = useAddTrackToPlaylist();
  const available = playlists.data ?? [];

  return (
    <>
      <DropdownMenuLabel className="flex items-center gap-2">
        <ListPlus className="size-4" aria-hidden="true" />
        Add to playlist
      </DropdownMenuLabel>
      {available.length === 0 ? (
        <DropdownMenuItem disabled>
          {playlists.isPending ? "Loading playlists…" : "No playlists on this profile yet"}
        </DropdownMenuItem>
      ) : (
        available.map((playlist) => (
          <DropdownMenuItem
            key={playlist.id}
            disabled={addToPlaylist.isPending}
            onSelect={() => {
              addToPlaylist.mutate({
                playlistId: playlist.id,
                trackId,
                revision: playlist.revision,
              });
            }}
          >
            {playlist.name}
          </DropdownMenuItem>
        ))
      )}
    </>
  );
}
