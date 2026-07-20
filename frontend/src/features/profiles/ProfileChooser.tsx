import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useId, useRef, useState } from "react";
import { ApiRequestError, api, type Profile, unwrap } from "@/api/client";
import { queryKeys } from "@/api/queryKeys";
import { useActiveProfile } from "@/app/activeProfile";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Field, FieldError, FieldGroup, FieldLabel } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";

/**
 * S1 — Profile chooser.
 *
 * Choosing an existing profile is the primary action; on a first visit there is
 * nothing to choose, so the creation field takes the eye and the focus. There
 * is deliberately no avatar, PIN, rename, or delete control: profiles separate
 * playlists, and nothing else.
 */
export function ProfileChooser() {
  const queryClient = useQueryClient();
  const { selectProfile } = useActiveProfile();
  const nameFieldId = useId();
  const nameField = useRef<HTMLInputElement>(null);
  const [name, setName] = useState("");

  const profiles = useQuery({
    queryKey: queryKeys.profiles,
    queryFn: async () => unwrap(await api.GET("/api/v1/profiles", {})).items,
  });

  const createProfile = useMutation({
    mutationFn: async (submitted: string) =>
      unwrap(await api.POST("/api/v1/profiles", { body: { name: submitted } })),
    onSuccess: async (profile) => {
      await queryClient.invalidateQueries({ queryKey: queryKeys.profiles });
      selectProfile(profile.id);
    },
  });

  const isEmpty = profiles.isSuccess && profiles.data.length === 0;

  useEffect(() => {
    if (isEmpty) {
      nameField.current?.focus();
    }
  }, [isEmpty]);

  const fieldError =
    createProfile.error instanceof ApiRequestError && createProfile.error.field === "name"
      ? createProfile.error.message
      : null;
  const generalError =
    createProfile.error instanceof ApiRequestError && createProfile.error.field === null
      ? createProfile.error.message
      : null;

  return (
    <main className="flex min-h-screen items-center justify-center bg-canvas px-5 py-8">
      <Card className="w-full max-w-[28rem]">
        <CardHeader>
          <CardTitle className="type-title">Chillify</CardTitle>
          <CardDescription className="type-body text-foreground-muted">
            Everyone in the house shares the same tracks and settings. A profile keeps your
            playlists separate — it is not a login, and anyone here can pick any of them.
          </CardDescription>
        </CardHeader>

        <CardContent className="flex flex-col gap-5">
          {profiles.isPending ? <ProfilePlaceholders /> : null}

          {profiles.isError ? (
            <Alert variant="destructive">
              <AlertTitle>Profiles could not be loaded</AlertTitle>
              <AlertDescription>
                <span className="type-meta">
                  {profiles.error instanceof ApiRequestError
                    ? profiles.error.message
                    : "The server did not respond."}
                </span>
                <Button
                  variant="outline"
                  size="sm"
                  className="mt-2 w-fit"
                  onClick={() => void profiles.refetch()}
                >
                  Retry
                </Button>
              </AlertDescription>
            </Alert>
          ) : null}

          {profiles.isSuccess && profiles.data.length > 0 ? (
            <ProfileList
              profiles={profiles.data}
              disabled={createProfile.isPending}
              onSelect={selectProfile}
            />
          ) : null}

          {isEmpty ? (
            <p className="type-meta text-foreground-muted">
              No profiles yet. Create the first one to open the library.
            </p>
          ) : null}

          <form
            noValidate
            onSubmit={(event) => {
              event.preventDefault();
              if (name.trim().length > 0 && !createProfile.isPending) {
                createProfile.mutate(name);
              }
            }}
          >
            <FieldGroup>
              <Field data-invalid={fieldError ? true : undefined}>
                <FieldLabel htmlFor={nameFieldId}>New profile name</FieldLabel>
                <Input
                  id={nameFieldId}
                  ref={nameField}
                  value={name}
                  maxLength={40}
                  autoComplete="off"
                  aria-invalid={fieldError ? true : undefined}
                  onChange={(event) => setName(event.target.value)}
                />
                {fieldError ? <FieldError>{fieldError}</FieldError> : null}
              </Field>

              {generalError ? (
                <Alert variant="destructive">
                  <AlertTitle>That profile could not be saved</AlertTitle>
                  <AlertDescription>
                    <span className="type-meta">{generalError}</span>
                  </AlertDescription>
                </Alert>
              ) : null}

              <Button
                type="submit"
                disabled={name.trim().length === 0 || createProfile.isPending}
              >
                {createProfile.isPending ? "Creating…" : "Create profile"}
              </Button>
            </FieldGroup>
          </form>
        </CardContent>
      </Card>
    </main>
  );
}

function ProfileList({
  profiles,
  disabled,
  onSelect,
}: {
  profiles: Profile[];
  disabled: boolean;
  onSelect: (profileId: string) => void;
}) {
  return (
    <ul className="flex flex-col gap-2">
      {profiles.map((profile) => (
        <li key={profile.id}>
          <Button
            variant="secondary"
            className="w-full justify-start"
            disabled={disabled}
            onClick={() => onSelect(profile.id)}
          >
            {profile.name}
          </Button>
        </li>
      ))}
    </ul>
  );
}

/** Fixed placeholders that reserve the profile positions while they load. */
function ProfilePlaceholders() {
  return (
    <div className="flex flex-col gap-2" aria-hidden="true">
      <Skeleton className="h-control w-full" />
      <Skeleton className="h-control w-full" />
    </div>
  );
}
