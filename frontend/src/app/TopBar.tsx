import { ChevronLeft, ChevronRight } from "lucide-react";
import { useLocation, useNavigate } from "react-router";
import { useSystemStatus } from "@/app/useSystemStatus";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { SidebarTrigger } from "@/components/ui/sidebar";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { GlobalJobIndicator } from "@/features/downloads/GlobalJobIndicator";

const titles: Record<string, string> = {
  "/library": "Your Library",
  "/search": "Search",
  "/playlists": "Playlists",
  "/downloads": "Downloads",
  "/settings": "Settings",
};

/**
 * Sticky top bar: history controls, the current view title, and a summary of
 * provider and queue state. The summary never claims health it has not
 * observed — an in-flight or failed status request reads as unknown.
 */
export function TopBar() {
  const navigate = useNavigate();
  const location = useLocation();
  const { data, isPending, isError } = useSystemStatus();

  const title = titles[location.pathname] ?? "Chillify";

  return (
    <header className="sticky top-0 z-10 flex h-topbar items-center gap-3 border-b bg-canvas px-5">
      <SidebarTrigger className="text-foreground-muted hover:text-foreground" />

      <nav aria-label="History" className="flex items-center gap-1">
        <Tooltip>
          <TooltipTrigger asChild>
            <Button
              variant="ghost"
              size="icon"
              aria-label="Go back"
              onClick={() => navigate(-1)}
            >
              <ChevronLeft className="size-4" aria-hidden="true" />
            </Button>
          </TooltipTrigger>
          <TooltipContent>Go back</TooltipContent>
        </Tooltip>
        <Tooltip>
          <TooltipTrigger asChild>
            <Button
              variant="ghost"
              size="icon"
              aria-label="Go forward"
              onClick={() => navigate(1)}
            >
              <ChevronRight className="size-4" aria-hidden="true" />
            </Button>
          </TooltipTrigger>
          <TooltipContent>Go forward</TooltipContent>
        </Tooltip>
      </nav>

      {/*
        Chrome, not structure: the screen inside the content viewport owns the
        page heading, so this stays a plain label and the page keeps exactly
        one h1.
      */}
      <p className="type-label truncate text-foreground">{title}</p>

      <div className="ml-auto flex items-center gap-2">
        <GlobalJobIndicator />
        <StatusSummary
          isPending={isPending}
          isError={isError}
          degraded={data?.degraded ?? false}
          redisHealth={data?.redis.health}
        />
      </div>
    </header>
  );
}

function StatusSummary({
  isPending,
  isError,
  degraded,
  redisHealth,
}: {
  isPending: boolean;
  isError: boolean;
  degraded: boolean;
  redisHealth?: "ok" | "degraded" | "unavailable";
}) {
  if (isPending) {
    return (
      <Badge variant="outline" className="text-foreground-subtle">
        Checking status
      </Badge>
    );
  }

  if (isError) {
    return (
      <Badge variant="outline" className="border-warning text-warning">
        Status unknown
      </Badge>
    );
  }

  if (!degraded) {
    return (
      <Badge variant="outline" className="text-foreground-muted">
        All systems normal
      </Badge>
    );
  }

  const reason =
    redisHealth !== "ok"
      ? "Downloads are paused while the queue is unreachable. Your library still plays."
      : "A required tool is unavailable, so new downloads may fail. Your library still plays.";

  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <Badge variant="outline" className="border-warning text-warning">
          Downloads degraded
        </Badge>
      </TooltipTrigger>
      <TooltipContent>{reason}</TooltipContent>
    </Tooltip>
  );
}
