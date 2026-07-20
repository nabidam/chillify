/**
 * The downloads feature's public module.
 *
 * Job state is global and server-owned. Nothing here keeps a second copy of a
 * job: the queries are the copy, and the event bridge invalidates them.
 */
import { useQuery } from "@tanstack/react-query";
import { api, unwrap } from "@/api/client";
import type { components } from "@/api/generated";
import { queryKeys } from "@/api/queryKeys";

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
