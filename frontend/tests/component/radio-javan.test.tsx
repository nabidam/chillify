import { QueryClient } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { HttpResponse, http } from "msw";
import { describe, expect, it, vi } from "vitest";
import { AppProviders } from "@/app/AppProviders";
import { ACTIVE_PROFILE_STORAGE_KEY } from "@/app/activeProfile";
import { routes } from "@/app/routes";
import {
  jobFixture,
  profileFixture,
  remoteResultFixture,
  trackSummaryFixture,
} from "../msw/handlers";
import { server } from "../msw/server";

function renderRadioJavan(path: string = routes.radioJavan) {
  window.localStorage.setItem(ACTIVE_PROFILE_STORAGE_KEY, profileFixture().id);
  window.history.replaceState(null, "", path);
  return render(
    <AppProviders
      queryClient={
        new QueryClient({ defaultOptions: { queries: { retry: false, staleTime: 0 } } })
      }
    />,
  );
}

describe("Radio Javan Explore", () => {
  it("switches between dedicated Featured and Trending first-page results", async () => {
    const catalog = vi.fn(() => HttpResponse.json({ items: [], next_cursor: null }));
    server.use(http.get("/api/v1/search/catalog", catalog));
    renderRadioJavan();

    expect(await screen.findByText("Featured Fixture")).toBeTruthy();
    await userEvent.click(screen.getByRole("tab", { name: "Trending" }));

    expect(await screen.findByText("Trending Fixture")).toBeTruthy();
    expect(catalog).not.toHaveBeenCalled();
  });

  it("keeps the section controls available for keyboard retry after a scoped failure", async () => {
    let attempts = 0;
    server.use(
      http.get("/api/v1/radio-javan/tracks", () => {
        attempts += 1;
        return attempts === 1
          ? HttpResponse.json(
              {
                error: {
                  code: "dependency_unavailable",
                  message: "Radio Javan is temporarily unavailable.",
                  field: null,
                  retryable: true,
                  request_id: "test",
                  detail: {},
                },
              },
              { status: 503 },
            )
          : HttpResponse.json({ items: [], next_cursor: null });
      }),
    );
    renderRadioJavan();

    expect(await screen.findByText("Radio Javan is temporarily unavailable.")).toBeTruthy();
    await userEvent.click(screen.getByRole("button", { name: "Retry" }));
    expect(await screen.findByText("No featured tracks found")).toBeTruthy();
    screen.getByRole("tab", { name: "Featured" }).focus();
    await userEvent.keyboard("{ArrowRight}");
    expect(screen.getByRole("tab", { name: "Trending" }).getAttribute("data-state")).toBe(
      "active",
    );

    expect(await screen.findByText("No trending tracks found")).toBeTruthy();
  });
});

describe("Radio Javan search", () => {
  it("loads the submitted deep link without touching the general catalog search", async () => {
    const catalog = vi.fn(() => HttpResponse.json({ items: [], next_cursor: null }));
    const dedicated = vi.fn(({ request }: { request: Request }) => {
      expect(new URL(request.url).searchParams.get("q")).toBe("fixture artist");
      return HttpResponse.json({
        items: [
          remoteResultFixture(
            {},
            {
              provider: "radiojavan",
              source_id: "900010",
              source_url: "https://play.radiojavan.com/song/900010",
              title: "Deep Link Fixture",
              artist: "Fixture Artist",
              acquisition_locator: "900010",
            },
          ),
        ],
        next_cursor: null,
      });
    });
    server.use(
      http.get("/api/v1/search/catalog", catalog),
      http.get("/api/v1/radio-javan/search", dedicated),
    );
    renderRadioJavan(`${routes.radioJavan}/search?q=fixture%20artist`);

    expect((await screen.findByLabelText("Search Radio Javan")).getAttribute("value")).toBe(
      "fixture artist",
    );
    expect(await screen.findByText("Deep Link Fixture")).toBeTruthy();
    expect(screen.getByText("1 track for “fixture artist”")).toBeTruthy();
    expect(dedicated).toHaveBeenCalledTimes(1);
    expect(catalog).not.toHaveBeenCalled();
  });

  it("keeps the deep link and retry action during provider failures", async () => {
    let attempts = 0;
    server.use(
      http.get("/api/v1/radio-javan/search", () => {
        attempts += 1;
        return attempts === 1
          ? HttpResponse.json(
              {
                error: {
                  code: "dependency_unavailable",
                  message: "Radio Javan is temporarily unavailable.",
                  field: null,
                  retryable: true,
                  request_id: "test",
                  detail: {},
                },
              },
              { status: 503 },
            )
          : HttpResponse.json({ items: [], next_cursor: null });
      }),
    );
    renderRadioJavan(`${routes.radioJavan}/search?q=missing`);

    expect(await screen.findByText("Radio Javan is temporarily unavailable.")).toBeTruthy();
    expect(screen.getByLabelText("Search Radio Javan").getAttribute("value")).toBe("missing");
    await userEvent.click(screen.getByRole("button", { name: "Retry" }));

    expect(
      await screen.findByText("0 tracks for “missing”. Try a different title or artist."),
    ).toBeTruthy();
  });

  it("links a local duplicate to the library instead of offering another download", async () => {
    server.use(
      http.get("/api/v1/radio-javan/search", () =>
        HttpResponse.json({
          items: [remoteResultFixture({ existing_track_id: trackSummaryFixture().id })],
          next_cursor: null,
        }),
      ),
    );
    renderRadioJavan(`${routes.radioJavan}/search?q=owned`);

    const localLink = await screen.findByRole("link", { name: /Already in your library/ });
    expect(localLink.getAttribute("href")).toBe(routes.library);
    expect(screen.queryByRole("button", { name: /^Download/ })).toBeNull();
  });

  it("disables only the result being queued", async () => {
    let completeDownload: ((response: Response) => void) | undefined;
    server.use(
      http.get("/api/v1/radio-javan/search", () =>
        HttpResponse.json({
          items: [
            remoteResultFixture(
              {},
              {
                provider: "radiojavan",
                source_id: "900011",
                source_url: "https://play.radiojavan.com/song/900011",
                title: "First Result",
                acquisition_locator: "900011",
              },
            ),
            remoteResultFixture(
              {},
              {
                provider: "radiojavan",
                source_id: "900012",
                source_url: "https://play.radiojavan.com/song/900012",
                title: "Second Result",
                acquisition_locator: "900012",
              },
            ),
          ],
          next_cursor: null,
        }),
      ),
      http.post(
        "/api/v1/downloads",
        () =>
          new Promise<Response>((resolve) => {
            completeDownload = resolve;
          }),
      ),
    );
    renderRadioJavan(`${routes.radioJavan}/search?q=two`);

    await userEvent.click(await screen.findByRole("button", { name: "Download First Result" }));

    expect(await screen.findByText("Queueing…")).toBeTruthy();
    expect(
      screen.getByRole("button", { name: "Download Second Result" }).hasAttribute("disabled"),
    ).toBe(false);
    if (completeDownload === undefined)
      throw new Error("The download request was not started.");
    completeDownload(HttpResponse.json(jobFixture(), { status: 201 }));
    expect(await screen.findByText("Queued for download")).toBeTruthy();
  });
});
