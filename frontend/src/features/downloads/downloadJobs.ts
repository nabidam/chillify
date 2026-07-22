/**
 * The downloads feature's public module.
 *
 * Job state is global and server-owned. Nothing here keeps a second copy of a
 * job: the queries are the copy, and the event bridge invalidates them.
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, unwrap } from "@/api/client";
import type { components } from "@/api/generated";
import { DOWNLOADS_QUERY_PREFIX, queryKeys } from "@/api/queryKeys";

export type DownloadJob = components["schemas"]["JobModel"];
export type JobEvent = components["schemas"]["JobEventModel"];
export type DisplayState = DownloadJob["display_state"];

/** States that mean work is still ahead, in the order S11 groups them. */
const ACTIVE_STATES: ReadonlySet<string> = new Set(["queued", "running"]);

export function isActive(job: DownloadJob): boolean {
  return ACTIVE_STATES.has(job.state);
}

export function useDownloads() {
  return useQuery({
    queryKey: queryKeys.downloads(),
    queryFn: async () => unwrap(await api.GET("/api/v1/downloads", {})),
  });
}

export function useDownloadDetail(jobId: string | null) {
  return useQuery({
    queryKey: queryKeys.download(jobId ?? ""),
    enabled: jobId !== null,
    queryFn: async () =>
      unwrap(
        await api.GET("/api/v1/downloads/{job_id}", {
          params: { path: { job_id: jobId ?? "" } },
        }),
      ),
  });
}

/**
 * Cancel one queued or running download.
 *
 * The job's `version` is sent so a cancel built on a stale view is refused
 * rather than applied to a job that has since moved on. The server owns the
 * outcome, so success simply invalidates the list the SSE bridge also refreshes.
 */
export function useCancelDownload() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (input: { jobId: string; version: number }): Promise<DownloadJob> =>
      unwrap(
        await api.POST("/api/v1/downloads/{job_id}/cancel", {
          params: { path: { job_id: input.jobId } },
          body: { version: input.version },
        }),
      ),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: DOWNLOADS_QUERY_PREFIX });
    },
  });
}

/**
 * Queue a fresh attempt linked to a finished failed or cancelled download.
 *
 * The idempotency key is minted per press so a double-click cannot queue two
 * attempts: the second request replays the first job rather than creating a
 * sibling.
 */
export function useRetryDownload() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (input: { jobId: string }): Promise<DownloadJob> =>
      unwrap(
        await api.POST("/api/v1/downloads/{job_id}/retry", {
          params: {
            path: { job_id: input.jobId },
            header: { "Idempotency-Key": crypto.randomUUID() },
          },
        }),
      ),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: DOWNLOADS_QUERY_PREFIX });
    },
  });
}

/** Human-readable phase labels. Chillify never shows a raw enum to a person. */
export const PHASE_LABELS: Record<string, string> = {
  accepted: "Accepted",
  inspecting: "Inspecting the link",
  queued: "Waiting in the queue",
  restarted: "Restarting",
  downloading: "Downloading",
  converting: "Converting to MP3",
  enriching: "Filling in metadata",
  tagging: "Writing tags",
  organizing: "Filing into your library",
  completed: "Completed",
  failed: "Failed",
  cancelled: "Cancelled",
};

export const DISPLAY_STATE_LABELS: Record<DisplayState, string> = {
  queued: "Queued",
  retrying: "Retrying",
  restarted: "Restarted",
  running: "Running",
  completed: "Completed",
  failed: "Failed",
  cancelled: "Cancelled",
};

export function phaseLabel(job: DownloadJob): string {
  return PHASE_LABELS[job.phase] ?? job.phase;
}

/**
 * The jobs still ahead of the person, in execution order.
 *
 * The API already returns newest first, which is right for history and wrong
 * for a queue: the next thing to run is the oldest active job.
 */
export function queueOrder(jobs: DownloadJob[]): DownloadJob[] {
  return jobs.filter(isActive).reverse();
}

export function historyOrder(jobs: DownloadJob[]): DownloadJob[] {
  return jobs.filter((job) => !isActive(job));
}
