import { QueryClient } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { HttpResponse, http } from "msw";
import { describe, expect, it } from "vitest";
import { AppProviders } from "@/app/AppProviders";
import { ACTIVE_PROFILE_STORAGE_KEY } from "@/app/activeProfile";
import {
  artworkStageFixture,
  profileFixture,
  trackDetailFixture,
  trackSummaryFixture,
} from "../msw/handlers";
import { server } from "../msw/server";

function renderLibrary() {
  window.localStorage.setItem(ACTIVE_PROFILE_STORAGE_KEY, profileFixture().id);
  window.history.replaceState(null, "", "/library");
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false, staleTime: 0 } },
  });
  return render(<AppProviders queryClient={queryClient} />);
}

/** Open S13 for the seeded library row. */
async function openEditor(user: ReturnType<typeof userEvent.setup>) {
  await user.click(await screen.findByRole("button", { name: /actions for hoppipolla/i }));
  await user.click(await screen.findByRole("menuitem", { name: /edit details/i }));
  return screen.findByRole("dialog");
}

/** The first recorded request, asserted to exist so strict indexing stays honest. */
function first<Item>(items: Item[]): Item {
  const item = items[0];
  if (item === undefined) {
    throw new Error("expected at least one recorded request");
  }
  return item;
}

function serveDetail(detail = trackDetailFixture()) {
  server.use(http.get("/api/v1/tracks/:trackId", () => HttpResponse.json(detail)));
}

describe("S13 track editor", () => {
  it("loads the complete record into its fields", async () => {
    serveDetail();
    const user = userEvent.setup();
    renderLibrary();

    await openEditor(user);

    expect((await screen.findByLabelText("Title")).getAttribute("value")).toBe("Hoppipolla");
    expect(screen.getByLabelText("Artist").getAttribute("value")).toBe("Sigur Rós");
    expect(screen.getByLabelText("Album").getAttribute("value")).toBe("Takk...");
    expect(screen.getByLabelText("Year").getAttribute("value")).toBe("2005");
  });

  it("discloses the source identity", async () => {
    serveDetail();
    const user = userEvent.setup();
    renderLibrary();

    await openEditor(user);

    expect(await screen.findByText(/deezer · 3135556/)).toBeTruthy();
  });

  it("sends the complete record with the track's revision as If-Match", async () => {
    serveDetail();
    const requests: Array<{ ifMatch: string | null; body: unknown }> = [];
    server.use(
      http.patch("/api/v1/tracks/:trackId", async ({ request }) => {
        requests.push({ ifMatch: request.headers.get("If-Match"), body: await request.json() });
        return HttpResponse.json(trackDetailFixture());
      }),
    );
    const user = userEvent.setup();
    renderLibrary();
    await openEditor(user);

    const album = await screen.findByLabelText("Album");
    await user.clear(album);
    await user.type(album, "Takk");
    await user.click(screen.getByRole("button", { name: "Save" }));

    await waitFor(() => expect(requests.length).toBe(1));
    expect(first(requests).ifMatch).toBe("1");
    expect(first(requests).body).toEqual({
      title: "Hoppipolla",
      artist: "Sigur Rós",
      album: "Takk",
      release_year: 2005,
      disc_number: 1,
      track_number: 4,
      artwork_stage_id: null,
    });
  });

  it("sends a cleared album as absence rather than an empty string", async () => {
    serveDetail();
    const bodies: Array<{ album: string | null }> = [];
    server.use(
      http.patch("/api/v1/tracks/:trackId", async ({ request }) => {
        bodies.push((await request.json()) as { album: string | null });
        return HttpResponse.json(trackDetailFixture());
      }),
    );
    const user = userEvent.setup();
    renderLibrary();
    await openEditor(user);

    await user.clear(await screen.findByLabelText("Album"));
    await user.click(screen.getByRole("button", { name: "Save" }));

    await waitFor(() => expect(bodies.length).toBe(1));
    expect(first(bodies).album).toBeNull();
  });

  it("marks a blank title and refuses to save", async () => {
    serveDetail();
    const user = userEvent.setup();
    renderLibrary();
    await openEditor(user);

    await user.clear(await screen.findByLabelText("Title"));

    expect(await screen.findByText("A title cannot be empty.")).toBeTruthy();
    expect(screen.getByRole("button", { name: "Save" }).hasAttribute("disabled")).toBe(true);
  });

  it("states the previous version is authoritative and preserves edits on a failed save", async () => {
    serveDetail();
    server.use(
      http.patch("/api/v1/tracks/:trackId", () =>
        HttpResponse.json(
          {
            error: {
              code: "record_changed",
              message: "Somebody else saved this track first.",
              field: null,
              retryable: false,
              request_id: "test",
              detail: {},
            },
          },
          { status: 409 },
        ),
      ),
    );
    const user = userEvent.setup();
    renderLibrary();
    await openEditor(user);

    const title = await screen.findByLabelText("Title");
    await user.clear(title);
    await user.type(title, "Hoppípolla");
    await user.click(screen.getByRole("button", { name: "Save" }));

    expect(await screen.findByText("This track was not saved")).toBeTruthy();
    expect(screen.getByText(/previous version is still what plays/i)).toBeTruthy();
    expect((title as HTMLInputElement).value).toBe("Hoppípolla");
  });

  it("disables tag mutation for a track whose file is missing", async () => {
    server.use(
      http.get("/api/v1/library/tracks", () =>
        HttpResponse.json({
          items: [trackSummaryFixture({ is_playable: false, availability: "missing" })],
          next_cursor: null,
        }),
      ),
    );
    serveDetail(
      trackDetailFixture({
        track: trackSummaryFixture({ is_playable: false, availability: "missing" }),
      }),
    );
    const user = userEvent.setup();
    renderLibrary();
    await openEditor(user);

    expect(await screen.findByText("This track's file is missing")).toBeTruthy();
    expect(screen.getByLabelText("Title").hasAttribute("disabled")).toBe(true);
    expect(screen.getByRole("button", { name: "Save" }).hasAttribute("disabled")).toBe(true);
  });

  it("reports a failed load without offering a save", async () => {
    server.use(
      http.get("/api/v1/tracks/:trackId", () => HttpResponse.json({}, { status: 503 })),
    );
    const user = userEvent.setup();
    renderLibrary();
    await openEditor(user);

    expect(await screen.findByText("This track could not be loaded")).toBeTruthy();
    expect(screen.getByRole("button", { name: "Save" }).hasAttribute("disabled")).toBe(true);
  });
});

describe("S13 artwork", () => {
  it("stages an uploaded cover and applies it only on save", async () => {
    serveDetail();
    let staged = false;
    const bodies: Array<{ artwork_stage_id: string | null }> = [];
    server.use(
      http.post("/api/v1/artwork/stages/upload", () => {
        staged = true;
        return HttpResponse.json(artworkStageFixture(), { status: 201 });
      }),
      http.patch("/api/v1/tracks/:trackId", async ({ request }) => {
        bodies.push((await request.json()) as { artwork_stage_id: string | null });
        return HttpResponse.json(trackDetailFixture({ has_artwork: true }));
      }),
    );
    const user = userEvent.setup();
    renderLibrary();
    await openEditor(user);

    await user.upload(
      await screen.findByLabelText("Upload a cover image"),
      new File([new Uint8Array([1, 2, 3])], "cover.png", { type: "image/png" }),
    );

    await waitFor(() => expect(staged).toBe(true));
    // Staging alone must not have changed the track.
    expect(bodies).toEqual([]);
    expect(await screen.findByText(/applied when you save/i)).toBeTruthy();

    await user.click(screen.getByRole("button", { name: "Save" }));
    await waitFor(() => expect(bodies.length).toBe(1));
    expect(first(bodies).artwork_stage_id).toBe(artworkStageFixture().id);
  });

  it("warns but still allows saving when an artwork fetch fails", async () => {
    serveDetail();
    server.use(
      http.post("/api/v1/artwork/stages/url", () =>
        HttpResponse.json(
          {
            error: {
              code: "artwork_unreadable",
              message: "That file is not an image Chillify can use.",
              field: null,
              retryable: false,
              request_id: "test",
              detail: {},
            },
          },
          { status: 400 },
        ),
      ),
    );
    const user = userEvent.setup();
    renderLibrary();
    await openEditor(user);

    await user.type(await screen.findByLabelText("Cover image link"), "https://example.test/a");
    await user.click(screen.getByRole("button", { name: /fetch/i }));

    expect(await screen.findByText(/not an image Chillify can use/)).toBeTruthy();
    expect(screen.getByRole("button", { name: "Save" }).hasAttribute("disabled")).toBe(false);
  });
});
