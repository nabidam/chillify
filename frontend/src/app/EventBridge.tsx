import { useQueryClient } from "@tanstack/react-query";
import { createContext, type ReactNode, use, useEffect, useState } from "react";
import { DOWNLOADS_QUERY_PREFIX, LIBRARY_QUERY_PREFIX, queryKeys } from "@/api/queryKeys";

/** The one stream. Mounted once, above every route. */
export const EVENTS_PATH = "/api/v1/events";

/** How often the fallback polls when the stream cannot be established. */
export const FALLBACK_POLL_MS = 5_000;

export type BridgeState = "connecting" | "live" | "reconnecting";

const EventBridgeContext = createContext<BridgeState>("connecting");

/**
 * Server-sent events, translated into cache invalidations.
 *
 * Nothing here is treated as the durable copy of anything: an event says "this
 * changed", and TanStack Query refetches the resource that owns it. That is
 * why a missed or duplicated event costs a refetch rather than correctness.
 *
 * There is exactly one connection, held here. Screens read its state through
 * the context rather than opening their own, because two streams would mean
 * two cursors and a household opening two tabs on the Downloads page would
 * quietly double the server's work.
 */
export function EventBridge({ children }: { children: ReactNode }) {
  const state = useEventStream();
  return <EventBridgeContext value={state}>{children}</EventBridgeContext>;
}

/**
 * The stream's current state, for screens that must label stale data.
 *
 * Reading it never opens a connection.
 */
export function useEventBridgeState(): BridgeState {
  return use(EventBridgeContext);
}

function useEventStream(): BridgeState {
  const queryClient = useQueryClient();
  const [state, setState] = useState<BridgeState>("connecting");

  useEffect(() => {
    if (typeof EventSource === "undefined") {
      // No stream available at all: poll instead of pretending to be live.
      setState("reconnecting");
      const timer = window.setInterval(() => {
        void queryClient.invalidateQueries({ queryKey: DOWNLOADS_QUERY_PREFIX });
        void queryClient.invalidateQueries({ queryKey: queryKeys.systemStatus });
      }, FALLBACK_POLL_MS);
      return () => window.clearInterval(timer);
    }

    const source = new EventSource(EVENTS_PATH);

    // The browser reconnects on its own and replays from its Last-Event-ID
    // cursor; the bridge only reports which of those two states it is in.
    source.onopen = () => setState("live");
    source.onerror = () => setState("reconnecting");

    source.addEventListener("job.changed", () => {
      void queryClient.invalidateQueries({ queryKey: DOWNLOADS_QUERY_PREFIX });
    });
    source.addEventListener("library.changed", () => {
      void queryClient.invalidateQueries({ queryKey: LIBRARY_QUERY_PREFIX });
    });
    source.addEventListener("system.changed", () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.systemStatus });
    });

    return () => source.close();
  }, [queryClient]);

  return state;
}
