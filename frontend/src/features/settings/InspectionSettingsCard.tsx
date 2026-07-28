import { useMutation, useQueryClient } from "@tanstack/react-query";
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
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";

type InspectionSettings = components["schemas"]["InspectionSettingsModel"];
type SpotifyApiState = components["schemas"]["SpotifyApiStateModel"];
type InspectionMode = InspectionSettings["mode"];
type TimeoutField = "timeout_spotify_s" | "timeout_spotdl_s" | "timeout_ytdlp_s";

const TIMEOUTS: ReadonlyArray<{
  key: TimeoutField;
  label: string;
  description: string;
  minimum: number;
  maximum: number;
}> = [
  {
    key: "timeout_spotify_s",
    label: "Spotify API timeout",
    description: "Fast lookup before the SpotDL fallback.",
    minimum: 1,
    maximum: 30,
  },
  {
    key: "timeout_spotdl_s",
    label: "SpotDL timeout",
    description: "Thorough lookup and the fallback path.",
    minimum: 30,
    maximum: 600,
  },
  {
    key: "timeout_ytdlp_s",
    label: "YouTube timeout",
    description: "YouTube metadata inspection.",
    minimum: 10,
    maximum: 300,
  },
];

interface InspectionSettingsCardProps {
  inspection: InspectionSettings;
  spotifyApi: SpotifyApiState;
}

export function InspectionSettingsCard({
  inspection,
  spotifyApi,
}: InspectionSettingsCardProps) {
  const queryClient = useQueryClient();
  const [clientId, setClientId] = useState("");
  const [clientSecret, setClientSecret] = useState("");
  const [spotifyConfigured, setSpotifyConfigured] = useState(spotifyApi.configured);
  const [spotifyRevision, setSpotifyRevision] = useState(spotifyApi.revision);
  const [mode, setMode] = useState<InspectionMode>(inspection.mode);
  const [timeouts, setTimeouts] = useState<Record<TimeoutField, string>>(
    () =>
      Object.fromEntries(TIMEOUTS.map(({ key }) => [key, String(inspection[key])])) as Record<
        TimeoutField,
        string
      >,
  );
  const [timeoutErrors, setTimeoutErrors] = useState<Partial<Record<TimeoutField, string>>>({});

  function refreshSettings() {
    void queryClient.invalidateQueries({ queryKey: queryKeys.settings });
  }

  const saveCredentials = useMutation({
    retry: false,
    mutationFn: async (): Promise<SpotifyApiState> =>
      unwrap(
        await api.PATCH("/api/v1/settings/providers/spotify_api", {
          body: {
            client_id: clientId.trim() || undefined,
            client_secret: clientSecret,
            clear_secret: false,
            revision: spotifyRevision,
          },
        }),
      ),
    onSuccess: (saved) => {
      setClientId("");
      setClientSecret("");
      setSpotifyConfigured(saved.configured);
      setSpotifyRevision(saved.revision);
      refreshSettings();
      toast.success("Spotify credentials saved");
    },
  });

  const clearCredentials = useMutation({
    retry: false,
    mutationFn: async (): Promise<SpotifyApiState> =>
      unwrap(
        await api.PATCH("/api/v1/settings/providers/spotify_api", {
          body: {
            clear_secret: true,
            revision: spotifyRevision,
          },
        }),
      ),
    onSuccess: (saved) => {
      setClientId("");
      setClientSecret("");
      setSpotifyConfigured(saved.configured);
      setSpotifyRevision(saved.revision);
      refreshSettings();
      toast.success("Spotify credentials cleared");
    },
  });

  const saveInspection = useMutation({
    retry: false,
    mutationFn: async (values: {
      timeout_spotify_s: number;
      timeout_spotdl_s: number;
      timeout_ytdlp_s: number;
    }): Promise<InspectionSettings> =>
      unwrap(
        await api.PATCH("/api/v1/settings/inspection", {
          body: { ...values, mode, revision: inspection.revision },
        }),
      ),
    onSuccess: () => {
      refreshSettings();
      toast.success("Link inspection settings saved");
    },
  });

  const credentialsBusy = saveCredentials.isPending || clearCredentials.isPending;
  const inspectionBusy = saveInspection.isPending;
  const credentialError =
    saveCredentials.error instanceof ApiRequestError ? saveCredentials.error : null;
  const clearError =
    clearCredentials.error instanceof ApiRequestError ? clearCredentials.error : null;
  const inspectionError =
    saveInspection.error instanceof ApiRequestError ? saveInspection.error : null;

  function updateTimeout(key: TimeoutField, value: string) {
    setTimeouts((current) => ({ ...current, [key]: value }));
    setTimeoutErrors((current) => ({ ...current, [key]: undefined }));
    saveInspection.reset();
  }

  function submitInspection(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const nextErrors: Partial<Record<TimeoutField, string>> = {};
    const values = {} as Record<TimeoutField, number>;

    for (const timeout of TIMEOUTS) {
      const value = Number(timeouts[timeout.key]);
      if (!Number.isInteger(value) || value < timeout.minimum || value > timeout.maximum) {
        nextErrors[timeout.key] =
          `Enter a whole number from ${timeout.minimum} to ${timeout.maximum} seconds.`;
      } else {
        values[timeout.key] = value;
      }
    }

    setTimeoutErrors(nextErrors);
    if (Object.keys(nextErrors).length > 0) {
      saveInspection.reset();
      return;
    }
    saveInspection.mutate(values);
  }

  function serverTimeoutError(key: TimeoutField): string | null {
    if (inspectionError?.field !== key) {
      return null;
    }
    return inspectionError.message;
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>Link inspection</CardTitle>
        <CardDescription>
          Choose what Chillify tries first for Spotify links. Fast falls back to SpotDL when the
          direct lookup is unavailable.
        </CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-6">
        <section aria-labelledby="spotify-credentials-heading" className="flex flex-col gap-4">
          <div>
            <h3 id="spotify-credentials-heading" className="font-medium">
              Spotify credentials
            </h3>
            {spotifyConfigured ? (
              <p className="text-sm text-muted-foreground">
                Configured. The secret is write-only and will never be shown here.
              </p>
            ) : (
              <p className="text-sm text-muted-foreground">
                Not configured. Spotify links use SpotDL instead, which is slower. Get
                credentials from the{" "}
                <a
                  className="underline underline-offset-4 hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                  href="https://developer.spotify.com/dashboard"
                  target="_blank"
                  rel="noreferrer"
                >
                  Spotify developer dashboard
                </a>
                .
              </p>
            )}
          </div>

          <form
            className="flex flex-col gap-4"
            onSubmit={(event) => {
              event.preventDefault();
              saveCredentials.mutate();
            }}
            noValidate
          >
            <div className="grid gap-4 sm:grid-cols-2">
              <Field data-invalid={credentialError?.field === "client_id" ? true : undefined}>
                <FieldLabel htmlFor="spotify-client-id">Client ID</FieldLabel>
                <Input
                  id="spotify-client-id"
                  autoComplete="off"
                  value={clientId}
                  disabled={credentialsBusy}
                  aria-invalid={credentialError?.field === "client_id" ? true : undefined}
                  onChange={(event) => {
                    setClientId(event.target.value);
                    saveCredentials.reset();
                  }}
                />
                {credentialError?.field === "client_id" ? (
                  <FieldError>{credentialError.message}</FieldError>
                ) : null}
              </Field>
              <Field
                data-invalid={credentialError?.field === "client_secret" ? true : undefined}
              >
                <FieldLabel htmlFor="spotify-client-secret">Client secret</FieldLabel>
                <Input
                  id="spotify-client-secret"
                  type="password"
                  autoComplete="new-password"
                  value={clientSecret}
                  disabled={credentialsBusy}
                  aria-invalid={credentialError?.field === "client_secret" ? true : undefined}
                  onChange={(event) => {
                    setClientSecret(event.target.value);
                    saveCredentials.reset();
                  }}
                />
                {credentialError?.field === "client_secret" ? (
                  <FieldError>{credentialError.message}</FieldError>
                ) : null}
              </Field>
            </div>
            <FieldDescription>
              Leave a field blank to keep its saved value. Saving clears these inputs; it never
              echoes a stored secret.
            </FieldDescription>
            <div className="flex flex-wrap items-center gap-2">
              <Button
                type="submit"
                disabled={
                  credentialsBusy || (clientId.trim() === "" && clientSecret.trim() === "")
                }
              >
                {saveCredentials.isPending ? "Saving…" : "Save credentials"}
              </Button>
              {spotifyConfigured ? (
                <Button
                  type="button"
                  variant="ghost"
                  disabled={credentialsBusy}
                  onClick={() => clearCredentials.mutate()}
                >
                  {clearCredentials.isPending ? "Clearing…" : "Clear credentials"}
                </Button>
              ) : null}
            </div>
            {clearError ? (
              <Alert variant="destructive">
                <AlertTitle>Spotify credentials could not be cleared</AlertTitle>
                <AlertDescription>{clearError.message}</AlertDescription>
              </Alert>
            ) : null}
            {credentialError &&
            credentialError.field !== "client_id" &&
            credentialError.field !== "client_secret" ? (
              <Alert variant="destructive">
                <AlertTitle>Spotify credentials could not be saved</AlertTitle>
                <AlertDescription>{credentialError.message}</AlertDescription>
              </Alert>
            ) : null}
          </form>
        </section>

        <form className="flex flex-col gap-4" onSubmit={submitInspection} noValidate>
          <div>
            <h3 className="font-medium">First inspection path</h3>
            <p className="text-sm text-muted-foreground">
              Fast asks Spotify directly and usually returns in about a second. Thorough asks
              SpotDL, which can take minutes on a slow connection.
            </p>
          </div>
          <Field>
            <FieldLabel htmlFor="inspection-mode">Mode</FieldLabel>
            <Select value={mode} onValueChange={(value) => setMode(value as InspectionMode)}>
              <SelectTrigger id="inspection-mode" className="w-full sm:w-56">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="fast">Fast — Spotify first</SelectItem>
                <SelectItem value="thorough">Thorough — SpotDL first</SelectItem>
              </SelectContent>
            </Select>
            <FieldDescription>
              Fast always falls back to SpotDL if credentials are missing or the direct lookup
              fails.
            </FieldDescription>
          </Field>

          <div className="grid gap-4 sm:grid-cols-3">
            {TIMEOUTS.map((timeout) => {
              const error = timeoutErrors[timeout.key] ?? serverTimeoutError(timeout.key);
              return (
                <Field key={timeout.key} data-invalid={error ? true : undefined}>
                  <FieldLabel htmlFor={timeout.key}>{timeout.label}</FieldLabel>
                  <Input
                    id={timeout.key}
                    type="number"
                    min={timeout.minimum}
                    max={timeout.maximum}
                    step="1"
                    inputMode="numeric"
                    value={timeouts[timeout.key]}
                    disabled={inspectionBusy}
                    aria-invalid={error ? true : undefined}
                    onChange={(event) => updateTimeout(timeout.key, event.target.value)}
                  />
                  <FieldDescription>
                    {timeout.description} {timeout.minimum}–{timeout.maximum} seconds.
                  </FieldDescription>
                  {error ? <FieldError>{error}</FieldError> : null}
                </Field>
              );
            })}
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <Button type="submit" disabled={inspectionBusy}>
              {inspectionBusy ? "Saving…" : "Save inspection settings"}
            </Button>
          </div>
          {inspectionError &&
          inspectionError.field !== "timeout_spotify_s" &&
          inspectionError.field !== "timeout_spotdl_s" &&
          inspectionError.field !== "timeout_ytdlp_s" ? (
            <Alert variant="destructive">
              <AlertTitle>Inspection settings could not be saved</AlertTitle>
              <AlertDescription>{inspectionError.message}</AlertDescription>
            </Alert>
          ) : null}
        </form>
      </CardContent>
    </Card>
  );
}
