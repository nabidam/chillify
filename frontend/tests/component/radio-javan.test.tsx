import { QueryClient } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { HttpResponse, http } from "msw";
import { describe, expect, it, vi } from "vitest";
import { AppProviders } from "@/app/AppProviders";
import { ACTIVE_PROFILE_STORAGE_KEY } from "@/app/activeProfile";
import { routes } from "@/app/routes";
import { profileFixture } from "../msw/handlers";
import { server } from "../msw/server";

function renderRadioJavan() {
  window.localStorage.setItem(ACTIVE_PROFILE_STORAGE_KEY, profileFixture().id);
  window.history.replaceState(null, "", routes.radioJavan);
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
