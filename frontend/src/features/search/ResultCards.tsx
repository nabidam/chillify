import { DownloadIcon, ExternalLinkIcon, LibraryIcon } from "lucide-react";
import { Link } from "react-router";
import { routes } from "@/app/routes";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import type { RemoteResult } from "@/features/search/remoteSearch";
import { formatMilliseconds } from "@/lib/format";

/**
 * Internet results, kept visibly apart from local ones.
 *
 * A remote result never offers Play: there is no file to play yet. Download is
 * the only primary action, and a result the library already holds offers the
 * local track instead of a second copy.
 */
export function ResultCards({
  results,
  onDownload,
  pendingSourceUrl,
  isDownloadDisabled,
  disabledReason,
}: {
  results: RemoteResult[];
  onDownload: (result: RemoteResult) => void;
  pendingSourceUrl: string | null;
  isDownloadDisabled: boolean;
  disabledReason: string | null;
}) {
  return (
    <ul className="flex flex-col gap-2">
      {results.map((result) => {
        const { candidate } = result;
        const isPending = pendingSourceUrl === candidate.source_url;
        return (
          <li key={candidate.source_url}>
            <Card className="bg-surface-raised">
              <CardContent className="flex items-center gap-4 py-3">
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2">
                    <span className="type-label truncate text-foreground">
                      {candidate.title}
                    </span>
                    <Badge variant="outline" className="border-info text-info">
                      {candidate.provider}
                    </Badge>
                  </div>
                  <p className="type-meta truncate text-foreground-muted">
                    {candidate.artist}
                    {candidate.album ? ` — ${candidate.album}` : ""}
                  </p>
                </div>

                <span className="type-meta shrink-0 text-foreground-subtle tabular-nums">
                  {formatMilliseconds(candidate.duration_ms)}
                </span>

                {result.existing_track_id === null ? (
                  <Button
                    size="sm"
                    className="shrink-0"
                    disabled={isDownloadDisabled || isPending}
                    aria-label={`Download ${candidate.title}`}
                    title={isDownloadDisabled ? (disabledReason ?? undefined) : undefined}
                    onClick={() => onDownload(result)}
                  >
                    <DownloadIcon className="size-4" aria-hidden="true" />
                    {isPending ? "Queueing…" : "Download"}
                  </Button>
                ) : (
                  <Button variant="outline" size="sm" className="shrink-0" asChild>
                    <Link to={routes.library}>
                      <LibraryIcon className="size-4" aria-hidden="true" />
                      Already in your library
                    </Link>
                  </Button>
                )}

                <Button variant="ghost" size="icon" className="shrink-0" asChild>
                  <a
                    href={candidate.source_url}
                    target="_blank"
                    rel="noreferrer noopener"
                    aria-label={`Open ${candidate.title} on ${candidate.provider}`}
                  >
                    <ExternalLinkIcon className="size-4" aria-hidden="true" />
                  </a>
                </Button>
              </CardContent>
            </Card>
          </li>
        );
      })}
    </ul>
  );
}

/** Card-shaped placeholders while remote catalogs are being contacted. */
export function ResultCardsPlaceholder({ rows = 3 }: { rows?: number }) {
  return (
    <div className="flex flex-col gap-2" aria-hidden="true">
      {Array.from({ length: rows }, (_, index) => (
        // biome-ignore lint/suspicious/noArrayIndexKey: fixed-length placeholder geometry.
        <Skeleton key={index} className="h-row w-full" />
      ))}
    </div>
  );
}
