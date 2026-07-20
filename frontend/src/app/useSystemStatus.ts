import { useQuery } from "@tanstack/react-query";
import { queryKeys } from "@/api/queryKeys";

/** The `GET /system/status` envelope documented in ARCHITECTURE section 5. */
export interface ComponentStatus {
  name: string;
  health: "ok" | "degraded" | "unavailable";
  detail: string | null;
}

export interface ProviderStatus {
  name: string;
  enabled: boolean;
  configured: boolean;
}

export interface SystemStatus {
  ready: boolean;
  degraded: boolean;
  environment: "production" | "gate";
  checked_at: string;
  database: ComponentStatus;
  storage: ComponentStatus[];
  redis: ComponentStatus;
  tools: ComponentStatus[];
  providers: ProviderStatus[];
}

export const SYSTEM_STATUS_PATH = "/api/v1/system/status";

async function fetchSystemStatus(signal: AbortSignal): Promise<SystemStatus> {
  const response = await fetch(SYSTEM_STATUS_PATH, {
    signal,
    headers: { Accept: "application/json" },
  });
  if (!response.ok) {
    throw new Error(`System status request failed with ${response.status}`);
  }
  return (await response.json()) as SystemStatus;
}

/**
 * Shell-wide system status.
 *
 * Degradation is surfaced, never inferred: while the request is in flight or
 * failing, the shell says the status is unknown rather than claiming health.
 */
export function useSystemStatus() {
  return useQuery({
    queryKey: queryKeys.systemStatus,
    queryFn: ({ signal }) => fetchSystemStatus(signal),
  });
}
