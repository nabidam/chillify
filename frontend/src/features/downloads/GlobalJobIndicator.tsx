import { LoaderIcon } from "lucide-react";
import { useNavigate } from "react-router";
import { routes } from "@/app/routes";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Progress } from "@/components/ui/progress";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { phaseLabel, queueOrder, useDownloads } from "@/features/downloads/downloadJobs";

/**
 * The compact, always-available job indicator.
 *
 * Visible exactly while work is queued or running, and silent otherwise: a
 * permanent badge saying "nothing is happening" is noise. Activating it opens
 * S11.
 */
export function GlobalJobIndicator() {
  const navigate = useNavigate();
  const downloads = useDownloads();

  const active = queueOrder(downloads.data?.items ?? []);
  const current = active[0];
  if (current === undefined) {
    return null;
  }

  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <Button
          variant="ghost"
          size="sm"
          className="gap-2"
          aria-label={`${active.length} downloads in progress. Open Downloads.`}
          onClick={() => void navigate(routes.downloads)}
        >
          <LoaderIcon className="size-4 text-signal" aria-hidden="true" />
          <span className="type-meta text-foreground-muted">{phaseLabel(current)}</span>
          {active.length > 1 ? <Badge variant="outline">{active.length}</Badge> : null}
          {current.progress_percent === null ? null : (
            <Progress
              value={current.progress_percent}
              className="w-cover-sm bg-progress-track"
              // The button already announces the work; the bar is decoration
              // beside it and must not be read a second time.
              aria-hidden="true"
            />
          )}
        </Button>
      </TooltipTrigger>
      <TooltipContent>
        {active.length === 1
          ? "One download is in progress. Open Downloads."
          : `${active.length} downloads are queued. Open Downloads.`}
      </TooltipContent>
    </Tooltip>
  );
}
