/**
 * The playlists feature's public module.
 *
 * Everything outside this folder — the sidebar, the library row actions —
 * reaches playlists through here rather than importing a screen's internals.
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, type Playlist, type PlaylistDetail, unwrap } from "@/api/client";
import { PLAYLISTS_QUERY_PREFIX, queryKeys } from "@/api/queryKeys";

/** Every playlist of one profile, most recently changed first. */
export function usePlaylists(profileId: string | null) {
  return useQuery({
    queryKey: queryKeys.playlists(profileId ?? ""),
    // A profile is required to have playlists at all, so the query simply does
    // not run until one is chosen rather than asking for an empty owner.
    enabled: profileId !== null,
    queryFn: async (): Promise<Playlist[]> => {
      const page = unwrap(
        await api.GET("/api/v1/profiles/{profile_id}/playlists", {
          params: { path: { profile_id: profileId as string } },
        }),
      );
      return page.items;
    },
  });
}

/** One playlist and its tracks in saved order. */
export function usePlaylist(playlistId: string | undefined) {
  return useQuery({
    queryKey: queryKeys.playlist(playlistId ?? ""),
    enabled: playlistId !== undefined,
    queryFn: async (): Promise<PlaylistDetail> =>
      unwrap(
        await api.GET("/api/v1/playlists/{playlist_id}", {
          params: { path: { playlist_id: playlistId as string } },
        }),
      ),
  });
}

export function useCreatePlaylist(profileId: string | null) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (name: string): Promise<Playlist> =>
      unwrap(
        await api.POST("/api/v1/profiles/{profile_id}/playlists", {
          params: { path: { profile_id: profileId as string } },
          body: { name },
        }),
      ),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: PLAYLISTS_QUERY_PREFIX });
    },
  });
}

export function useRenamePlaylist() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (input: {
      playlistId: string;
      name: string;
      revision: number;
    }): Promise<Playlist> =>
      unwrap(
        await api.PATCH("/api/v1/playlists/{playlist_id}", {
          params: { path: { playlist_id: input.playlistId } },
          body: { name: input.name, revision: input.revision },
        }),
      ),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: PLAYLISTS_QUERY_PREFIX });
    },
  });
}

export function useAddTrackToPlaylist() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (input: {
      playlistId: string;
      trackId: string;
      revision: number;
    }): Promise<PlaylistDetail> =>
      unwrap(
        await api.POST("/api/v1/playlists/{playlist_id}/tracks", {
          params: { path: { playlist_id: input.playlistId } },
          body: { track_id: input.trackId, revision: input.revision },
        }),
      ),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: PLAYLISTS_QUERY_PREFIX });
    },
  });
}

/** Rewrite the whole saved order under the playlist's current revision. */
export function useReorderPlaylist() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (input: {
      playlistId: string;
      trackIds: string[];
      revision: number;
    }): Promise<PlaylistDetail> =>
      unwrap(
        await api.PUT("/api/v1/playlists/{playlist_id}/order", {
          params: { path: { playlist_id: input.playlistId } },
          body: { track_ids: input.trackIds, revision: input.revision },
        }),
      ),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: PLAYLISTS_QUERY_PREFIX });
    },
  });
}

/**
 * Drop one track from a playlist without deleting the shared track.
 *
 * The revision travels as `If-Match`, matching the destructive track routes:
 * a removal made against a stale view is refused rather than silently applied.
 */
export function useRemoveTrackFromPlaylist() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (input: {
      playlistId: string;
      trackId: string;
      revision: number;
    }): Promise<PlaylistDetail> =>
      unwrap(
        await api.DELETE("/api/v1/playlists/{playlist_id}/tracks/{track_id}", {
          params: {
            path: { playlist_id: input.playlistId, track_id: input.trackId },
            header: { "If-Match": String(input.revision) },
          },
        }),
      ),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: PLAYLISTS_QUERY_PREFIX });
    },
  });
}
