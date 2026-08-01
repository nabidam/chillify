/**
 * The search feature's public module.
 *
 * Local and online search are separate queries on purpose. The local one
 * reacts to typing; the online one is disabled until an explicit submission
 * token appears, so no keystroke can reach a provider.
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, unwrap } from "@/api/client";
import type { components } from "@/api/generated";
import { DOWNLOADS_QUERY_PREFIX, queryKeys } from "@/api/queryKeys";

export type TrackCandidate = components["schemas"]["TrackCandidateModel"];
export type RemoteResult = components["schemas"]["RemoteResultModel"];
export type DownloadJob = components["schemas"]["JobModel"];
export type DownloadSourceType = components["schemas"]["DownloadRequestModel"]["source_type"];

export const CATALOG_RESULT_LIMIT = 15;

/**
 * Online discovery, held behind an explicit submission.
 *
 * `submission` is empty until the person presses the button. The query is
 * disabled until then, which is the local-first rule expressed as state rather
 * than as a comment.
 */
export function useCatalogSearch(submission: string) {
  return useQuery({
    queryKey: queryKeys.catalogSearch(submission),
    enabled: submission.length > 0,
    // A remote result is a snapshot of someone else's catalogue; refetching it
    // behind the person's back would silently change what they are looking at.
    staleTime: Number.POSITIVE_INFINITY,
    retry: false,
    queryFn: async () =>
      unwrap(
        await api.GET("/api/v1/search/catalog", {
          params: {
            query: { q: submission, provider: "all", limit: CATALOG_RESULT_LIMIT },
          },
        }),
      ),
  });
}

/** Queue one acquisition. The durable job is the response, not a promise of one. */
export function useQueueDownload(sourceType: DownloadSourceType = "deezer_result") {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (candidate: TrackCandidate): Promise<DownloadJob> =>
      unwrap(
        await api.POST("/api/v1/downloads", {
          // The durable v1 wire value predates multi-catalog search. The
          // candidate's provider remains the authoritative source identity;
          // yt-dlp acquires every catalog result through the same path.
          body: { source_type: sourceType, candidate },
        }),
      ),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: DOWNLOADS_QUERY_PREFIX });
    },
  });
}
