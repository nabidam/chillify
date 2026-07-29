/**
 * The acquisition feature's public module.
 *
 * Adding music by link is two deliberate steps that never collapse into one:
 * inspection recognizes a URL and reports what it is, and only a separate queue
 * call commits a download. A YouTube link is reviewed (S5) before it is queued;
 * a Spotify link is queued straight from its inspected candidate.
 */
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { api, unwrap } from "@/api/client";
import type { components } from "@/api/generated";
import { DOWNLOADS_QUERY_PREFIX } from "@/api/queryKeys";

export type TrackCandidate = components["schemas"]["TrackCandidateModel"];
export type LinkInspection = {
  source_type: DownloadSourceType;
  provider: "deezer" | "spotdl" | "yt_dlp";
  review_required: boolean;
  candidate: TrackCandidate;
  is_playable: false;
  existing_track_id?: string | null;
};
export type DownloadSourceType = components["schemas"]["DownloadRequestModel"]["source_type"];
export type DownloadJob = components["schemas"]["JobModel"];
export type SpotifyLinkMatches = components["schemas"]["SpotifyLinkMatchesModel"];

/** Queue one reviewed acquisition. The durable job is the response, not a promise. */
export function useQueueReviewedDownload() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (request: {
      source_type: DownloadSourceType;
      candidate: TrackCandidate;
    }): Promise<DownloadJob> =>
      unwrap(
        await api.POST("/api/v1/downloads", {
          body: { source_type: request.source_type, candidate: request.candidate },
        }),
      ),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: DOWNLOADS_QUERY_PREFIX });
    },
  });
}

/** Resolve a Spotify reference and search independent catalogs for choices. */
export function useSpotifyLinkMatches() {
  return useMutation({
    mutationFn: async (url: string): Promise<SpotifyLinkMatches> =>
      unwrap(
        await api.POST("/api/v1/links/spotify/matches", {
          body: { url },
        }),
      ),
  });
}
