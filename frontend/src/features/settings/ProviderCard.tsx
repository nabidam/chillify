import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { ApiRequestError, api, unwrap } from "@/api/client";
import type { components } from "@/api/generated";
import { queryKeys } from "@/api/queryKeys";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Field, FieldDescription, FieldLabel } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";

type ProviderState = components["schemas"]["ProviderStateModel"];
type ProviderDiagnosis = components["schemas"]["ProviderDiagnosisModel"];

const DISPLAY_NAMES: Record<string, string> = {
  deezer: "Deezer",
  spotdl: "SpotDL",
  yt_dlp: "YouTube (yt-dlp)",
  lastfm: "Last.fm",
};

/**
 * One provider's settings row (S12).
 *
 * Enabling and credentials are edited in place; a failure is isolated to this
 * card and never marks the whole screen unhealthy. A missing Last.fm key marks
 * enrichment optional, not broken — so its "unconfigured" state is informational
 * rather than an error.
 */
export function ProviderCard({ provider }: { provider: ProviderState }) {
  const queryClient = useQueryClient();
  const [credential, setCredential] = useState("");
  const [diagnosis, setDiagnosis] = useState<ProviderDiagnosis | null>(null);

  function refresh() {
    void queryClient.invalidateQueries({ queryKey: queryKeys.settings });
    void queryClient.invalidateQueries({ queryKey: queryKeys.systemStatus });
  }

  const save = useMutation({
    retry: false,
    mutationFn: async (body: {
      enabled?: boolean;
      credential?: string;
      clear_secret?: boolean;
    }): Promise<ProviderState> =>
      unwrap(
        await api.PATCH("/api/v1/settings/providers/{provider}", {
          params: { path: { provider: provider.name } },
          body: {
            enabled: body.enabled,
            credential: body.credential,
            clear_secret: body.clear_secret ?? false,
            revision: provider.revision,
          },
        }),
      ),
    onSuccess: () => {
      setCredential("");
      setDiagnosis(null);
      refresh();
    },
  });

  const test = useMutation({
    retry: false,
    mutationFn: async (): Promise<ProviderDiagnosis> =>
      unwrap(
        await api.POST("/api/v1/settings/providers/{provider}/test", {
          params: { path: { provider: provider.name } },
        }),
      ),
    onSuccess: (result) => setDiagnosis(result),
  });

  const busy = save.isPending || test.isPending;

  return (
    <Card>
      <CardHeader className="flex-row items-center justify-between gap-3 space-y-0">
        <div className="flex items-center gap-2">
          <CardTitle>{DISPLAY_NAMES[provider.name] ?? provider.name}</CardTitle>
          <ConfiguredBadge provider={provider} />
        </div>
        <Switch
          checked={provider.enabled}
          disabled={busy}
          aria-label={`Enable ${DISPLAY_NAMES[provider.name] ?? provider.name}`}
          onCheckedChange={(enabled) => save.mutate({ enabled })}
        />
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        {provider.requires_credential ? (
          <Field>
            <FieldLabel htmlFor={`${provider.name}-key`}>API key</FieldLabel>
            <div className="flex gap-2">
              <Input
                id={`${provider.name}-key`}
                type="password"
                autoComplete="off"
                value={credential}
                disabled={busy}
                placeholder={provider.has_credential ? "A key is saved" : "Not configured"}
                onChange={(event) => setCredential(event.target.value)}
              />
              <Button
                type="button"
                variant="secondary"
                disabled={busy || credential.trim().length === 0}
                onClick={() => save.mutate({ credential: credential.trim() })}
              >
                Save key
              </Button>
              {provider.has_credential ? (
                <Button
                  type="button"
                  variant="ghost"
                  disabled={busy}
                  onClick={() => save.mutate({ clear_secret: true })}
                >
                  Remove
                </Button>
              ) : null}
            </div>
            <FieldDescription>
              The key is stored encrypted and never shown again. Last.fm only fills missing
              metadata; leaving it unset keeps enrichment optional.
            </FieldDescription>
          </Field>
        ) : null}

        <div className="flex items-center gap-3">
          <Button type="button" variant="outline" disabled={busy} onClick={() => test.mutate()}>
            {test.isPending ? "Testing…" : "Test"}
          </Button>
          {diagnosis ? (
            <span
              className={
                diagnosis.ok ? "text-sm text-muted-foreground" : "text-sm text-destructive"
              }
            >
              {diagnosis.message}
            </span>
          ) : null}
        </div>

        {save.isError ? (
          <Alert variant="destructive">
            <AlertTitle>That change could not be saved</AlertTitle>
            <AlertDescription>
              {save.error instanceof ApiRequestError ? save.error.message : "Please try again."}
            </AlertDescription>
          </Alert>
        ) : null}
      </CardContent>
    </Card>
  );
}

function ConfiguredBadge({ provider }: { provider: ProviderState }) {
  if (!provider.enabled) {
    return <Badge variant="outline">Off</Badge>;
  }
  if (provider.requires_credential && !provider.has_credential) {
    return <Badge variant="outline">Optional</Badge>;
  }
  return <Badge variant="secondary">Enabled</Badge>;
}
