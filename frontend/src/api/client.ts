import createClient from "openapi-fetch";
import type { components, paths } from "@/api/generated";

/**
 * The one API client.
 *
 * Requests are same-origin under `/api/v1`: nginx serves the browser bundle and
 * proxies the API from the same host, so there is no environment-specific base
 * URL to configure and no CORS to negotiate.
 */
export const api = createClient<paths>({
  baseUrl: apiBaseUrl(),
  // Resolved per call rather than captured once at module load, so the client
  // always uses the current global `fetch`.
  fetch: (request) => globalThis.fetch(request),
});

/**
 * The page's own origin.
 *
 * It is resolved to an absolute URL rather than left as `/` because the
 * underlying `Request` constructor rejects a relative base outside a browser —
 * which is exactly where the component tests run.
 */
function apiBaseUrl(): string {
  return typeof window === "undefined" ? "http://localhost" : window.location.origin;
}

export type TrackSummary = components["schemas"]["TrackSummaryModel"];
export type TrackDetail = components["schemas"]["TrackDetailModel"];
export type Profile = components["schemas"]["ProfileModel"];
export type Playlist = components["schemas"]["PlaylistModel"];
export type PlaylistDetail = components["schemas"]["PlaylistDetailModel"];
export type ArtworkStage = components["schemas"]["ArtworkStageModel"];
export type DeleteImpact = components["schemas"]["DeleteImpactModel"];
export type LibrarySort = components["schemas"]["LibrarySort"];
export type ApiError = components["schemas"]["ErrorBody"];

/** The documented error envelope, as it arrives on a non-2xx response. */
export interface ApiErrorEnvelope {
  error: ApiError;
}

/**
 * A failed request, carrying the server's stable code and safe message.
 *
 * The envelope is the only thing the UI is allowed to render: it is already
 * redacted, already safe, and already written for a person.
 */
export class ApiRequestError extends Error {
  readonly code: string;
  readonly field: string | null;
  readonly retryable: boolean;
  readonly status: number;

  constructor(status: number, body: ApiError) {
    super(body.message);
    this.name = "ApiRequestError";
    this.status = status;
    this.code = body.code;
    this.field = body.field ?? null;
    this.retryable = body.retryable;
  }
}

function isErrorEnvelope(value: unknown): value is ApiErrorEnvelope {
  return (
    typeof value === "object" &&
    value !== null &&
    "error" in value &&
    typeof (value as ApiErrorEnvelope).error?.code === "string"
  );
}

/**
 * Unwrap one openapi-fetch result into data, or throw the documented error.
 *
 * A response that is neither is still a failure the person must see, so it
 * becomes a generic envelope rather than an undefined the caller renders as an
 * empty screen.
 */
export function unwrap<Data>(result: {
  data?: Data;
  error?: unknown;
  response: Response;
}): Data {
  if (result.error !== undefined) {
    if (isErrorEnvelope(result.error)) {
      throw new ApiRequestError(result.response.status, result.error.error);
    }
    throw new ApiRequestError(result.response.status, {
      code: "request_failed",
      message: "The request failed. Please try again.",
      field: null,
      retryable: true,
      request_id: "unknown",
      detail: {},
    });
  }
  return result.data as Data;
}

/** The stream URL for one track. The `<audio>` element loads this directly. */
export function trackStreamUrl(trackId: string): string {
  return `/api/v1/tracks/${encodeURIComponent(trackId)}/stream`;
}

/**
 * The cover URL for one track.
 *
 * `revision` is carried as a query parameter so a corrected cover replaces the
 * one the browser already cached: the managed filename is derived from the
 * track ID and therefore never changes on its own.
 */
export function trackArtworkUrl(trackId: string, revision: number): string {
  return `/media/artwork/tracks/${encodeURIComponent(trackId)}?v=${revision}`;
}

/** The preview URL for a staged cover, before any save has consumed it. */
export function artworkStageUrl(stageId: string): string {
  return `/media/artwork/stages/${encodeURIComponent(stageId)}`;
}
