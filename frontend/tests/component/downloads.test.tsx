import { QueryClient } from "@tanstack/react-query";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { HttpResponse, http } from "msw";
import { describe, expect, it } from "vitest";
import { AppProviders } from "@/app/AppProviders";
import { ACTIVE_PROFILE_STORAGE_KEY } from "@/app/activeProfile";
import { routes } from "@/app/routes";
import { jobFixture, profileFixture, systemStatusFixture } from "../msw/handlers";
import { server } from "../msw/server";

function renderDownloads() {
  window.localStorage.setItem(ACTIVE_PROFILE_STORAGE_KEY, profileFixture().id);
  window.history.replaceState(null, "", routes.downloads);
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false, staleTime: 0 } },
  });
  return render(<AppProviders queryClient={queryClient} />);
}

function serveJobs(...jobs: ReturnType<typeof jobFixture>[]) {
  server.use(
    http.get("/api/v1/downloads", () => HttpResponse.json({ items: jobs, next_cursor: null })),
  );
}

describe("S11 downloads", () => {
  it("says downloads continue without this page when there are none", async () => {
    renderDownloads();

    expect(await screen.findByText("No downloads yet")).toBeTruthy();
    expect(screen.getByRole("link", { name: "Go to Search" })).toBeTruthy();
  });

  it("shows a determinate bar only when a real percentage was reported", async () => {
    serveJobs(
      jobFixture({
        id: "job-with-progress",
        state: "running",
        display_state: "running",
        phase: "downloading",
        progress_percent: 42,
      }),
    );
    renderDownloads();

    const bar = await screen.findByRole("progressbar", { name: "Downloading progress" });
    expect(bar.getAttribute("aria-valuenow")).toBe("42");
  });

  it("shows the phase and no invented progress when none was reported", async () => {
    serveJobs(
      jobFixture({
        id: "job-without-progress",
        state: "running",
        display_state: "running",
        phase: "converting",
        progress_percent: null,
      }),
    );
    renderDownloads();

    const content = await screen.findByLabelText("Content");
    expect(await within(content).findByText("Converting to MP3")).toBeTruthy();
    expect(within(content).queryByRole("progressbar")).toBeNull();
    expect(within(content).getByText(/reports no percentage/)).toBeTruthy();
  });

  it("labels a restarted job distinctly from a first attempt", async () => {
    serveJobs(jobFixture({ id: "restarted", display_state: "restarted", restart_count: 1 }));
    renderDownloads();

    expect(await screen.findByText("Restarted")).toBeTruthy();
  });

  it("keeps a failure summary plain and its detail disclosed", async () => {
    serveJobs(
      jobFixture({
        id: "failed",
        state: "failed",
        display_state: "failed",
        phase: "failed",
        error_code: "acquisition_failed",
        error_message: "The audio for that track could not be retrieved.",
        finished_at: "2026-07-20T12:05:00.000Z",
      }),
    );
    renderDownloads();

    const trigger = await screen.findByRole("button", { name: /Failed/ });
    expect(screen.queryByText("The audio for that track could not be retrieved.")).toBeNull();

    await userEvent.click(trigger);

    expect(
      await screen.findByText("The audio for that track could not be retrieved."),
    ).toBeTruthy();
  });

  it("explains degraded mode when the queue is unreachable", async () => {
    server.use(
      http.get("/api/v1/system/status", () =>
        HttpResponse.json(
          systemStatusFixture({
            degraded: true,
            redis: { name: "redis", health: "unavailable", detail: "unreachable" },
          }),
        ),
      ),
    );
    renderDownloads();

    expect(await screen.findByText("The download queue is unreachable")).toBeTruthy();
    expect(screen.getByText(/Your library still plays/)).toBeTruthy();
  });

  it("labels stale states while the stream is reconnecting", async () => {
    renderDownloads();

    // jsdom provides no EventSource, so the bridge is in its polling fallback:
    // exactly the state a person must be told about rather than shown as live.
    expect(await screen.findByText(/Reconnecting/)).toBeTruthy();
  });
});

describe("global job indicator", () => {
  it("appears only while work is queued or running", async () => {
    serveJobs(
      jobFixture({
        id: "active",
        state: "running",
        display_state: "running",
        phase: "tagging",
      }),
    );
    renderDownloads();

    expect(await screen.findByRole("button", { name: /downloads in progress/ })).toBeTruthy();
  });

  it("stays silent when nothing is happening", async () => {
    serveJobs(
      jobFixture({
        id: "done",
        state: "completed",
        display_state: "completed",
        phase: "completed",
      }),
    );
    renderDownloads();

    expect(await screen.findByText("Finished")).toBeTruthy();
    expect(screen.queryByRole("button", { name: /downloads in progress/ })).toBeNull();
  });
});
