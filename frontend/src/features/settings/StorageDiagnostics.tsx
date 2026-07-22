import { HardDriveIcon, TerminalIcon } from "lucide-react";
import { type ComponentStatus, useSystemStatus } from "@/app/useSystemStatus";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";

/**
 * S12 storage and tool diagnostics.
 *
 * The health checks resolve independently of the settings form above them, so a
 * slow probe never blocks editing the proxy. Each row names its own failure —
 * an unreadable mount, low disk, an unreachable queue, or a missing binary — so
 * the operator sees exactly what to fix, never a single opaque "unhealthy".
 */
export function StorageDiagnostics() {
  const status = useSystemStatus();

  return (
    <Card>
      <CardHeader>
        <CardTitle>Storage and tools</CardTitle>
        <CardDescription>
          Mounted paths, free space, and the binaries acquisition needs. These are read-only
          deployment concerns, configured in the environment before Chillify starts.
        </CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-6">
        {status.isPending ? (
          <DiagnosticsPlaceholder />
        ) : status.isError ? (
          <Alert variant="destructive">
            <AlertTitle>Diagnostics are unavailable</AlertTitle>
            <AlertDescription>
              The system status could not be read. Reload to try again.
            </AlertDescription>
          </Alert>
        ) : (
          <>
            <DiagnosticGroup
              icon={<HardDriveIcon aria-hidden />}
              heading="Storage"
              items={[...status.data.storage, status.data.redis]}
            />
            <DiagnosticGroup
              icon={<TerminalIcon aria-hidden />}
              heading="Required tools"
              items={status.data.tools}
            />
          </>
        )}
      </CardContent>
    </Card>
  );
}

function DiagnosticGroup({
  icon,
  heading,
  items,
}: {
  icon: React.ReactNode;
  heading: string;
  items: ComponentStatus[];
}) {
  return (
    <section className="flex flex-col gap-2">
      <h3 className="flex items-center gap-2 text-sm font-medium text-muted-foreground [&_svg]:size-4">
        {icon}
        {heading}
      </h3>
      <ul className="flex flex-col divide-y divide-border rounded-md border border-border">
        {items.map((item) => (
          <li key={item.name} className="flex items-center justify-between gap-3 px-3 py-2">
            <div className="flex flex-col">
              <span className="text-sm font-medium">{item.name}</span>
              {item.detail ? (
                <span className="text-xs text-muted-foreground">{item.detail}</span>
              ) : null}
            </div>
            <HealthBadge health={item.health} />
          </li>
        ))}
      </ul>
    </section>
  );
}

export function HealthBadge({ health }: { health: ComponentStatus["health"] }) {
  if (health === "ok") {
    return <Badge variant="secondary">Ready</Badge>;
  }
  if (health === "degraded") {
    return <Badge variant="outline">Degraded</Badge>;
  }
  return <Badge variant="destructive">Unavailable</Badge>;
}

function DiagnosticsPlaceholder() {
  return (
    <div className="flex flex-col gap-2" aria-hidden>
      <Skeleton className="h-4 w-24" />
      <Skeleton className="h-10 w-full" />
      <Skeleton className="h-10 w-full" />
    </div>
  );
}
