import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { HttpResponse, http } from "msw";
import { MemoryRouter } from "react-router";
import { afterEach, describe, expect, it, vi } from "vitest";
import { AppProviders } from "@/app/AppProviders";
import { ACTIVE_PROFILE_STORAGE_KEY } from "@/app/activeProfile";
import { RouteErrorBoundary } from "@/app/RouteErrorBoundary";
import { routes } from "@/app/routes";
import { DataState, ErrorState } from "@/features/shared/DataState";
import { DegradedBanner } from "@/features/shared/DegradedBanner";
import { playlistFixture, profileFixture, systemStatusFixture } from "../msw/handlers";
import { server } from "../msw/server";

function withQueryClient(node: React.ReactNode) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false, staleTime: 0 } },
  });
  return <QueryClientProvider client={queryClient}>{node}</QueryClientProvider>;
}

function renderDataState(overrides: Partial<React.ComponentProps<typeof DataState>> = {}) {
  return render(
    <DataState
      status="success"
      loading={<div data-testid="skeleton" />}
      empty={<p>Nothing here yet</p>}
      error={{ title: "It broke", description: "The server did not respond." }}
      {...overrides}
    >
      <p>Loaded content</p>
    </DataState>,
  );
}

describe("DataState — enumerated view states", () => {
  it("announces loading as busy and hides the skeleton geometry", () => {
    renderDataState({ status: "pending" });

    const region = screen.getByRole("status");
    expect(region.getAttribute("aria-live")).toBe("polite");
    expect(screen.getByText("Loading")).toBeTruthy();
    // The placeholder shapes are chrome, not content.
    expect(screen.getByTestId("skeleton").closest("[aria-hidden='true']")).toBeTruthy();
    expect(screen.queryByText("Loaded content")).toBeNull();
  });

  it("shows a recoverable error with a working retry", async () => {
    const onRetry = vi.fn();
    renderDataState({ status: "error", error: { title: "It broke", onRetry } });
    const user = userEvent.setup();

    expect(screen.getByRole("alert")).toBeTruthy();
    expect(screen.getByText("It broke")).toBeTruthy();
    await user.click(screen.getByRole("button", { name: "Try again" }));

    expect(onRetry).toHaveBeenCalledOnce();
  });

  it("renders the empty branch only when success is empty", () => {
    renderDataState({ status: "success", isEmpty: true });

    expect(screen.getByText("Nothing here yet")).toBeTruthy();
    expect(screen.queryByText("Loaded content")).toBeNull();
  });

  it("renders content on a non-empty success", () => {
    renderDataState({ status: "success", isEmpty: false });

    expect(screen.getByText("Loaded content")).toBeTruthy();
    expect(screen.queryByText("Nothing here yet")).toBeNull();
  });
});

describe("ErrorState", () => {
  it("omits the retry control when no handler is given", () => {
    render(<ErrorState title="Read-only failure" />);

    expect(screen.getByText("Read-only failure")).toBeTruthy();
    expect(screen.queryByRole("button")).toBeNull();
  });
});

describe("DegradedBanner — surfaced, never inferred", () => {
  it("stays silent while status is unconfirmed", async () => {
    server.use(
      http.get("/api/v1/system/status", () => HttpResponse.json(null, { status: 503 })),
    );
    render(withQueryClient(<DegradedBanner />));

    // Give the failing query a tick; the banner must never claim a problem it
    // has not observed.
    await waitFor(() => {
      expect(screen.queryByRole("alert")).toBeNull();
    });
  });

  it("names the queue outage when the queue is unreachable", async () => {
    server.use(
      http.get("/api/v1/system/status", () =>
        HttpResponse.json(
          systemStatusFixture({
            degraded: true,
            redis: { name: "redis", health: "unavailable", detail: "queue unreachable" },
          }),
        ),
      ),
    );
    render(withQueryClient(<DegradedBanner />));

    expect(
      await screen.findByText("Downloads are paused while the queue is unreachable"),
    ).toBeTruthy();
    expect(screen.getByText(/still plays/)).toBeTruthy();
  });

  it("names a tool outage when the queue is healthy but a tool is gone", async () => {
    server.use(
      http.get("/api/v1/system/status", () =>
        HttpResponse.json(systemStatusFixture({ degraded: true })),
      ),
    );
    render(withQueryClient(<DegradedBanner />));

    expect(await screen.findByText("New downloads may fail right now")).toBeTruthy();
  });
});

describe("RouteErrorBoundary — contains a view crash", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  function Boom(): React.ReactNode {
    throw new Error("render exploded");
  }

  it("shows a recoverable message instead of a blank page and recovers on retry", async () => {
    // A thrown render is expected here; keep the boundary's own logging quiet.
    vi.spyOn(console, "error").mockImplementation(() => {});
    let shouldThrow = true;
    function Maybe() {
      return shouldThrow ? <Boom /> : <p>Recovered content</p>;
    }
    const user = userEvent.setup();

    render(
      <MemoryRouter>
        <RouteErrorBoundary>
          <Maybe />
        </RouteErrorBoundary>
      </MemoryRouter>,
    );

    expect(screen.getByText("This view ran into a problem")).toBeTruthy();
    shouldThrow = false;
    await user.click(screen.getByRole("button", { name: "Reload this view" }));

    expect(await screen.findByText("Recovered content")).toBeTruthy();
  });
});

describe("Modal focus return", () => {
  afterEach(() => {
    window.localStorage.clear();
    window.history.replaceState(null, "", "/");
  });

  it("returns focus to the invoking control after the dialog closes", async () => {
    window.localStorage.setItem(ACTIVE_PROFILE_STORAGE_KEY, profileFixture().id);
    window.history.replaceState(null, "", routes.playlists);
    // A populated list leaves the header's Create control as the only one, so
    // the empty-state duplicate never competes for the query.
    server.use(
      http.get("/api/v1/profiles/:profileId/playlists", () =>
        HttpResponse.json({ items: [playlistFixture()], next_cursor: null }),
      ),
    );
    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false, staleTime: 0 } },
    });
    const user = userEvent.setup();
    render(<AppProviders queryClient={queryClient} />);

    const create = await screen.findByRole("button", { name: "Create Playlist" });
    await user.click(create);

    const dialog = await screen.findByRole("dialog");
    expect(dialog).toBeTruthy();

    await user.keyboard("{Escape}");

    await waitFor(() => {
      expect(screen.queryByRole("dialog")).toBeNull();
    });
    await waitFor(() => {
      expect(document.activeElement).toBe(create);
    });
  });
});
