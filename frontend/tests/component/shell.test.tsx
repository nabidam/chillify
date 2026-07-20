import { QueryClient } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { HttpResponse, http } from "msw";
import { describe, expect, it } from "vitest";
import { AppProviders } from "@/app/AppProviders";
import { systemStatusFixture } from "../msw/handlers";
import { server } from "../msw/server";

function renderShell() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false, staleTime: 0 } },
  });
  return { ...render(<AppProviders queryClient={queryClient} />), queryClient };
}

describe("persistent shell", () => {
  it("renders the four stable regions", async () => {
    renderShell();

    expect(await screen.findByRole("heading", { name: "Your Library" })).toBeTruthy();
    expect(screen.getByRole("navigation", { name: "History" })).toBeTruthy();
    expect(screen.getByRole("main", { name: "Content" })).toBeTruthy();
    expect(screen.getByLabelText("Player")).toBeTruthy();
  });

  it("routes the index to the library view", async () => {
    renderShell();

    await waitFor(() => {
      expect(window.location.pathname).toBe("/library");
    });
  });

  it("changes only the content viewport when navigating", async () => {
    const user = userEvent.setup();
    renderShell();
    const player = await screen.findByLabelText("Player");

    await user.click(screen.getByRole("link", { name: "Downloads" }));

    expect(await screen.findByRole("heading", { name: "Downloads" })).toBeTruthy();
    // Same element instance: the shell and its player were never remounted.
    expect(screen.getByLabelText("Player")).toBe(player);
  });

  it("marks the active navigation item as the current page", async () => {
    const user = userEvent.setup();
    renderShell();

    await user.click(await screen.findByRole("link", { name: "Settings" }));

    await waitFor(() => {
      expect(screen.getByRole("link", { name: "Settings" }).getAttribute("aria-current")).toBe(
        "page",
      );
    });
    expect(
      screen.getByRole("link", { name: "Library" }).getAttribute("aria-current"),
    ).toBeNull();
  });
});

describe("shell status summary", () => {
  it("reports normal operation when nothing is degraded", async () => {
    renderShell();

    expect(await screen.findByText("All systems normal")).toBeTruthy();
  });

  it("names the degraded queue without claiming the library is unusable", async () => {
    server.use(
      http.get("/api/v1/system/status", () =>
        HttpResponse.json(
          systemStatusFixture({
            degraded: true,
            redis: { name: "redis", health: "unavailable", detail: null },
          }),
        ),
      ),
    );
    renderShell();

    expect(await screen.findByText("Downloads degraded")).toBeTruthy();
  });

  it("says the status is unknown rather than healthy when the request fails", async () => {
    server.use(http.get("/api/v1/system/status", () => HttpResponse.json({}, { status: 503 })));
    renderShell();

    expect(await screen.findByText("Status unknown")).toBeTruthy();
    expect(screen.queryByText("All systems normal")).toBeNull();
  });

  it("does not claim health while the status request is still in flight", () => {
    renderShell();

    expect(screen.getByText("Checking status")).toBeTruthy();
    expect(screen.queryByText("All systems normal")).toBeNull();
  });
});
