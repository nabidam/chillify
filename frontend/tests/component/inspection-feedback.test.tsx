import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { HttpResponse, http } from "msw";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { AddLinkDialog } from "@/features/acquisition/AddLinkDialog";
import { remoteResultFixture } from "../msw/handlers";
import { server } from "../msw/server";

class FakeEventSource {
  static instances: FakeEventSource[] = [];
  readonly url: string;
  readonly listeners = new Map<string, (event: Event) => void>();
  readonly close = vi.fn();

  constructor(url: string) {
    this.url = url;
    FakeEventSource.instances.push(this);
  }

  addEventListener(name: string, listener: (event: Event) => void) {
    this.listeners.set(name, listener);
  }

  emit(name: string, data: unknown) {
    this.listeners.get(name)?.(new MessageEvent(name, { data: JSON.stringify(data) }));
  }
}

function renderDialog() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <AddLinkDialog open onOpenChange={vi.fn()} />
    </QueryClientProvider>,
  );
}

function serveAccepted(phase = "inspecting_youtube") {
  server.use(
    http.post("/api/v1/links/inspect", () =>
      HttpResponse.json(
        {
          inspection_id: "inspection-1",
          phase,
          started_at: "2026-07-29T10:00:00.000Z",
        },
        { status: 202 },
      ),
    ),
  );
}

async function activeStream() {
  return waitFor(() => {
    const stream = FakeEventSource.instances[0];
    if (!stream) {
      throw new Error("inspection stream was not opened");
    }
    return stream;
  });
}

describe("S4 inspection feedback", () => {
  beforeEach(() => {
    FakeEventSource.instances = [];
    vi.stubGlobal("EventSource", FakeEventSource);
    serveAccepted();
  });

  afterEach(() => {
    vi.stubGlobal("EventSource", undefined);
  });

  it("shows named phases and a rising elapsed value without percentage progress", async () => {
    renderDialog();
    await userEvent.type(screen.getByLabelText("Link"), "https://youtu.be/example");
    await userEvent.click(screen.getByRole("button", { name: "Continue" }));

    expect(await screen.findByText("Inspecting YouTube details")).toBeTruthy();
    const stream = await activeStream();
    act(() => {
      stream.emit("inspection.changed", {
        phase: "inspecting_youtube",
        elapsed_ms: 1200,
        provider: "yt_dlp",
        terminal: false,
      });
    });

    expect(await screen.findByText("Inspecting YouTube details")).toBeTruthy();
    expect(screen.getByText("1.2 seconds elapsed")).toBeTruthy();
    expect((screen.getByRole("button", { name: "Cancel" }) as HTMLButtonElement).disabled).toBe(
      false,
    );
    expect(document.body.textContent).not.toContain("%");
  });

  it("uses Spotify oEmbed matching without opening the legacy inspection stream", async () => {
    renderDialog();
    const input = screen.getByLabelText("Link");
    await userEvent.type(input, "https://open.spotify.com/track/2cGxRwrMyEAp8dEbuZaVv6");
    await userEvent.click(screen.getByRole("button", { name: "Continue" }));

    expect(await screen.findByText("Spotify reference")).toBeTruthy();
    expect(await screen.findByText("Harder Better Faster Stronger")).toBeTruthy();
    expect(FakeEventSource.instances).toHaveLength(0);
  });

  it("renders expiry as its own terminal state", async () => {
    renderDialog();
    const input = screen.getByLabelText("Link");
    await userEvent.type(input, "https://youtu.be/expired");
    await userEvent.click(screen.getByRole("button", { name: "Continue" }));
    const stream = await activeStream();
    act(() => {
      stream.emit("inspection.changed", {
        phase: "expired",
        elapsed_ms: 300000,
        provider: "yt_dlp",
        terminal: true,
        error: { code: "inspection_expired", message: "This inspection expired. Try again." },
      });
    });

    expect(await screen.findByText("Inspection expired")).toBeTruthy();
    expect(screen.queryByText("Inspection failed")).toBeNull();
    expect((input as HTMLInputElement).disabled).toBe(false);
  });

  it("queues the catalog match selected for a Spotify reference", async () => {
    const queued = vi.fn(() => HttpResponse.json({ id: "job-1" }, { status: 201 }));
    server.use(
      http.post("/api/v1/links/spotify/matches", () =>
        HttpResponse.json({
          reference: {
            spotify_id: "2cGxRwrMyEAp8dEbuZaVv6",
            canonical_url: "https://open.spotify.com/track/2cGxRwrMyEAp8dEbuZaVv6",
            title: "Instant Crush",
            thumbnail_url: "https://i.scdn.co/image/reference",
          },
          items: [remoteResultFixture()],
        }),
      ),
      http.post("/api/v1/downloads", queued),
    );
    renderDialog();
    await userEvent.type(
      screen.getByLabelText("Link"),
      "https://open.spotify.com/track/2cGxRwrMyEAp8dEbuZaVv6",
    );
    await userEvent.click(screen.getByRole("button", { name: "Continue" }));
    await userEvent.click(
      await screen.findByRole("button", {
        name: "Download Harder Better Faster Stronger",
      }),
    );
    await waitFor(() => expect(queued).toHaveBeenCalledTimes(1));
  });
});
