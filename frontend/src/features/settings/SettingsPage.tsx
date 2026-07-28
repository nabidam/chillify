import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ShieldIcon } from "lucide-react";
import { type FormEvent, useState } from "react";
import { toast } from "sonner";
import { ApiRequestError, api, unwrap } from "@/api/client";
import type { components } from "@/api/generated";
import { queryKeys } from "@/api/queryKeys";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Field, FieldDescription, FieldError, FieldLabel } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { InspectionSettingsCard } from "@/features/settings/InspectionSettingsCard";
import { ProviderCard } from "@/features/settings/ProviderCard";
import { StorageDiagnostics } from "@/features/settings/StorageDiagnostics";

type Settings = components["schemas"]["SettingsModel"];
type ProxyDiagnosis = components["schemas"]["ProxyDiagnosisModel"];

/**
 * S12 — Settings.
 *
 * The global proxy comes first, because everything else reaches the internet
 * through it. Saving validates before it stores, testing always goes through
 * the proxy, and no credential is ever echoed back into a field. Provider and
 * storage health resolve independently below, so a slow probe never blocks the
 * proxy form.
 */
export function SettingsPage() {
  const settings = useQuery({
    queryKey: queryKeys.settings,
    queryFn: async (): Promise<Settings> => unwrap(await api.GET("/api/v1/settings")),
  });

  return (
    <div className="mx-auto flex w-full max-w-3xl flex-col gap-6 p-6">
      <header className="flex flex-col gap-1">
        <h1 className="text-2xl font-semibold tracking-tight">Settings</h1>
        <p className="text-sm text-muted-foreground">
          Configure the outbound proxy and providers, and inspect storage and tool health.
        </p>
      </header>

      {settings.isPending ? (
        <SettingsPlaceholder />
      ) : settings.isError ? (
        <Alert variant="destructive">
          <AlertTitle>Settings could not be loaded</AlertTitle>
          <AlertDescription>
            {settings.error instanceof ApiRequestError
              ? settings.error.message
              : "Reload to try again."}
          </AlertDescription>
        </Alert>
      ) : (
        <>
          <ProxyCard proxy={settings.data.proxy} />
          <section className="flex flex-col gap-4">
            <h2 className="text-lg font-medium">Providers</h2>
            {settings.data.providers.map((provider) => (
              <ProviderCard key={provider.name} provider={provider} />
            ))}
          </section>
          <InspectionSettingsCard
            inspection={settings.data.inspection}
            spotifyApi={settings.data.spotify_api}
          />
          <StorageDiagnostics />
        </>
      )}
    </div>
  );
}

function ProxyCard({ proxy }: { proxy: Settings["proxy"] }) {
  const queryClient = useQueryClient();
  const [url, setUrl] = useState("");
  const [diagnosis, setDiagnosis] = useState<ProxyDiagnosis | null>(null);

  function refresh() {
    void queryClient.invalidateQueries({ queryKey: queryKeys.settings });
    void queryClient.invalidateQueries({ queryKey: queryKeys.systemStatus });
  }

  const save = useMutation({
    retry: false,
    mutationFn: async (body: { url?: string; clear?: boolean }): Promise<Settings["proxy"]> =>
      unwrap(
        await api.PATCH("/api/v1/settings/proxy", {
          body: { url: body.url, clear: body.clear ?? false, revision: proxy.revision },
        }),
      ),
    onSuccess: (_saved, variables) => {
      setUrl("");
      setDiagnosis(null);
      refresh();
      toast.success(variables.clear ? "Proxy removed" : "Proxy saved");
    },
  });

  const test = useMutation({
    retry: false,
    mutationFn: async (): Promise<ProxyDiagnosis> =>
      unwrap(
        await api.POST("/api/v1/settings/proxy/test", {
          body: { url: url.trim() === "" ? null : url.trim() },
        }),
      ),
    onSuccess: (result) => setDiagnosis(result),
  });

  const busy = save.isPending || test.isPending;
  const validationField =
    save.error instanceof ApiRequestError && save.error.code === "proxy_configuration_invalid"
      ? save.error.message
      : null;

  function submit(event: FormEvent) {
    event.preventDefault();
    if (url.trim().length > 0) {
      save.mutate({ url: url.trim() });
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2 [&_svg]:size-5">
          <ShieldIcon aria-hidden />
          Outbound proxy
        </CardTitle>
        <CardDescription>
          All internet traffic is routed through this proxy. There is no direct fallback: if the
          proxy fails, acquisition stops rather than reaching out around it.
        </CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        {proxy.configured ? (
          <p className="text-sm">
            Currently using <span className="font-medium">{proxy.masked_url}</span>.
          </p>
        ) : (
          <p className="text-sm text-muted-foreground">No proxy is configured.</p>
        )}

        <form className="flex flex-col gap-3" onSubmit={submit} noValidate>
          <Field data-invalid={validationField ? true : undefined}>
            <FieldLabel htmlFor="proxy-url">Proxy URL</FieldLabel>
            <Input
              id="proxy-url"
              value={url}
              disabled={busy}
              aria-invalid={validationField ? true : undefined}
              placeholder="socks5://user:password@host:1080"
              onChange={(event) => setUrl(event.target.value)}
            />
            {validationField ? (
              <FieldError>{validationField}</FieldError>
            ) : (
              <FieldDescription>
                Supported schemes: http, https, socks5, socks5h. Credentials are stored
                encrypted and never shown again.
              </FieldDescription>
            )}
          </Field>

          <div className="flex flex-wrap items-center gap-2">
            <Button type="submit" disabled={busy || url.trim().length === 0}>
              {save.isPending ? "Saving…" : "Save"}
            </Button>
            <Button
              type="button"
              variant="outline"
              disabled={busy}
              onClick={() => test.mutate()}
            >
              {test.isPending ? "Testing…" : "Test"}
            </Button>
            {proxy.configured ? (
              <Button
                type="button"
                variant="ghost"
                disabled={busy}
                onClick={() => save.mutate({ clear: true })}
              >
                Remove proxy
              </Button>
            ) : null}
          </div>
        </form>

        {diagnosis ? (
          <Alert variant={diagnosis.ok ? "default" : "destructive"}>
            <AlertTitle>{diagnosis.ok ? "Proxy reachable" : "Proxy test failed"}</AlertTitle>
            <AlertDescription>{diagnosis.message}</AlertDescription>
          </Alert>
        ) : null}
      </CardContent>
    </Card>
  );
}

function SettingsPlaceholder() {
  return (
    <div className="flex flex-col gap-6" aria-hidden>
      <Skeleton className="h-48 w-full" />
      <Skeleton className="h-32 w-full" />
      <Skeleton className="h-32 w-full" />
    </div>
  );
}
