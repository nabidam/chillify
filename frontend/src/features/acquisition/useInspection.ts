import { useCallback, useEffect, useRef, useState } from "react";
import { type ApiRequestError, api, unwrap } from "@/api/client";
import type { components } from "@/api/generated";
import type { LinkInspection } from "@/features/acquisition/acquisitionQueries";

export type InspectionPhase = components["schemas"]["InspectionAcceptedModel"]["phase"];
export type InspectionStatus = "idle" | "starting" | "running" | "done" | "failed" | "expired";

export interface InspectionError {
  code: string;
  message: string;
}

export interface InspectionEvent {
  phase: InspectionPhase;
  elapsed_ms: number;
  provider: string | null;
  terminal: boolean;
  result?: LinkInspection;
  error?: InspectionError;
}

interface InspectionState {
  status: InspectionStatus;
  phase: InspectionPhase | null;
  provider: string | null;
  elapsedMs: number;
  result: LinkInspection | null;
  error: InspectionError | null;
}

const INITIAL_STATE: InspectionState = {
  status: "idle",
  phase: null,
  provider: null,
  elapsedMs: 0,
  result: null,
  error: null,
};

const TERMINAL_PHASES = new Set<InspectionPhase>(["cancelled", "expired", "failed", "done"]);

function isInspectionEvent(value: unknown): value is InspectionEvent {
  if (typeof value !== "object" || value === null) {
    return false;
  }
  const event = value as Partial<InspectionEvent>;
  return (
    typeof event.phase === "string" &&
    typeof event.elapsed_ms === "number" &&
    typeof event.terminal === "boolean"
  );
}

function errorFromUnknown(error: unknown): InspectionError {
  if (error instanceof Error) {
    return { code: "inspection_failed", message: error.message };
  }
  return {
    code: "inspection_failed",
    message: "The link could not be inspected.",
  };
}

/** Owns one tracked inspection, including its SSE connection and elapsed clock. */
export function useInspection() {
  const [state, setState] = useState<InspectionState>(INITIAL_STATE);
  const eventSourceRef = useRef<EventSource | null>(null);
  const inspectionIdRef = useRef<string | null>(null);
  const operationRef = useRef(0);
  const elapsedOriginRef = useRef<number | null>(null);

  const closeStream = useCallback(() => {
    eventSourceRef.current?.close();
    eventSourceRef.current = null;
  }, []);

  const reset = useCallback(() => {
    operationRef.current += 1;
    closeStream();
    inspectionIdRef.current = null;
    elapsedOriginRef.current = null;
    setState(INITIAL_STATE);
  }, [closeStream]);

  const start = useCallback(
    async (url: string) => {
      const operation = operationRef.current + 1;
      operationRef.current = operation;
      closeStream();
      inspectionIdRef.current = null;
      elapsedOriginRef.current = null;
      setState({ ...INITIAL_STATE, status: "starting" });

      try {
        const accepted = unwrap(
          await api.POST("/api/v1/links/inspect", {
            body: { url },
          }),
        );
        if (operationRef.current !== operation) {
          return;
        }

        inspectionIdRef.current = accepted.inspection_id;
        elapsedOriginRef.current = performance.now();
        setState((current) => ({
          ...current,
          status: "running",
          phase: accepted.phase,
        }));

        const eventSource = new EventSource(
          `/api/v1/links/inspect/${encodeURIComponent(accepted.inspection_id)}/events`,
        );
        eventSourceRef.current = eventSource;

        const handleEvent = (message: Event) => {
          if (operationRef.current !== operation) {
            return;
          }
          let parsed: unknown;
          try {
            parsed = JSON.parse((message as MessageEvent<string>).data) as unknown;
          } catch {
            return;
          }
          if (!isInspectionEvent(parsed)) {
            return;
          }

          const event = parsed;
          const nextElapsed = Math.max(0, Math.round(event.elapsed_ms));
          setState((current) => ({
            ...current,
            status:
              event.phase === "expired"
                ? "expired"
                : event.phase === "failed"
                  ? "failed"
                  : event.phase === "done"
                    ? "done"
                    : event.terminal
                      ? "idle"
                      : "running",
            phase: event.phase,
            provider: event.provider,
            elapsedMs: Math.max(current.elapsedMs, nextElapsed),
            result: event.result ?? current.result,
            error: event.error ?? current.error,
          }));

          if (event.terminal || TERMINAL_PHASES.has(event.phase)) {
            closeStream();
            inspectionIdRef.current = null;
            elapsedOriginRef.current = null;
          }
        };

        eventSource.addEventListener("inspection.changed", handleEvent);
      } catch (error) {
        if (operationRef.current !== operation) {
          return;
        }
        const failure = errorFromUnknown(error);
        setState({
          ...INITIAL_STATE,
          status: "failed",
          phase: "failed",
          error: failure,
        });
        inspectionIdRef.current = null;
        elapsedOriginRef.current = null;
      }
    },
    [closeStream],
  );

  const cancel = useCallback(async () => {
    const inspectionId = inspectionIdRef.current;
    if (inspectionId === null) {
      reset();
      return;
    }

    operationRef.current += 1;
    closeStream();
    inspectionIdRef.current = null;
    elapsedOriginRef.current = null;

    try {
      await unwrap(
        await api.DELETE("/api/v1/links/inspect/{inspection_id}", {
          params: { path: { inspection_id: inspectionId } },
        }),
      );
      setState(INITIAL_STATE);
    } catch (error) {
      const failure = errorFromUnknown(error);
      const isExpired =
        error instanceof Error &&
        "status" in error &&
        (error as ApiRequestError).status === 404;
      setState({
        ...INITIAL_STATE,
        status: isExpired ? "expired" : "failed",
        phase: isExpired ? "expired" : "failed",
        error: isExpired
          ? {
              code: "inspection_expired",
              message: "This inspection expired. Paste the link again to retry.",
            }
          : failure,
      });
    }
  }, [closeStream, reset]);

  useEffect(() => {
    if (state.status !== "running" || elapsedOriginRef.current === null) {
      return;
    }
    const timer = window.setInterval(() => {
      const origin = elapsedOriginRef.current;
      if (origin === null) {
        return;
      }
      setState((current) =>
        current.status === "running"
          ? {
              ...current,
              elapsedMs: Math.max(current.elapsedMs, Math.round(performance.now() - origin)),
            }
          : current,
      );
    }, 100);
    return () => window.clearInterval(timer);
  }, [state.status]);

  useEffect(() => reset, [reset]);

  return {
    ...state,
    isActive: state.status === "starting" || state.status === "running",
    start,
    cancel,
    reset,
  };
}

export function formatElapsed(elapsedMs: number): string {
  const seconds = elapsedMs / 1000;
  return `${seconds.toFixed(seconds >= 10 ? 0 : 1)} seconds elapsed`;
}
