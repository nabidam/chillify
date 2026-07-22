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
export type LinkInspection = components["schemas"]["LinkInspectionModel"];
export type DownloadSourceType = components["schemas"]["DownloadRequestModel"]["source_type"];
export type DownloadJob = components["schemas"]["JobModel"];

/**
 * Inspect one submitted link.
 *
 * A read, never a write: it recognizes and describes the link but queues
 * nothing. An unsupported, malformed, or bulk link fails here, which is why the
 * dialog can report exactly what went wrong before any download exists.
 */
export function useInspectLink() {
  return useMutation({
    // A link inspection is a fresh explicit action every time; a failed attempt
    // should surface its own error rather than be retried behind the person.
    retry: false,
    mutationFn: async (url: string): Promise<LinkInspection> =>
      unwrap(await api.POST("/api/v1/links/inspect", { body: { url } })),
  });
}

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
