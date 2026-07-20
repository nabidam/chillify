import { QueryClient } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { HttpResponse, http } from "msw";
import { describe, expect, it } from "vitest";
import type { Profile } from "@/api/client";
import { AppProviders } from "@/app/AppProviders";
import { profileFixture } from "../msw/handlers";
import { server } from "../msw/server";

function renderApp() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false, staleTime: 0 } },
  });
  return render(<AppProviders queryClient={queryClient} />);
}

describe("S1 profile chooser", () => {
  it("is where the app starts when no profile has been chosen", async () => {
    renderApp();

    expect(await screen.findByLabelText("New profile name")).toBeTruthy();
    await waitFor(() => {
      expect(window.location.pathname).toBe("/profiles");
    });
  });

  it("offers each existing profile as a choice and opens the library on one", async () => {
    const user = userEvent.setup();
    renderApp();

    await user.click(await screen.findByRole("button", { name: "Household" }));

    expect(await screen.findByRole("heading", { name: "Your Library" })).toBeTruthy();
  });

  it("explains the shared-library model without offering a login", async () => {
    renderApp();

    expect(await screen.findByText(/keeps your playlists separate/i)).toBeTruthy();
    expect(screen.queryByLabelText(/password/i)).toBeNull();
  });

  it("focuses the creation field when there is nothing to choose", async () => {
    server.use(
      http.get("/api/v1/profiles", () => HttpResponse.json({ items: [], next_cursor: null })),
    );
    renderApp();

    const field = await screen.findByLabelText("New profile name");
    await waitFor(() => {
      expect(document.activeElement).toBe(field);
    });
  });

  it("creates a profile and selects it", async () => {
    const user = userEvent.setup();
    let created: Profile | null = null;
    server.use(
      http.get("/api/v1/profiles", () =>
        HttpResponse.json({ items: created === null ? [] : [created], next_cursor: null }),
      ),
      http.post("/api/v1/profiles", async ({ request }) => {
        const body = (await request.json()) as { name: string };
        created = profileFixture({ name: body.name });
        return HttpResponse.json(created, { status: 201 });
      }),
    );
    renderApp();

    await user.type(await screen.findByLabelText("New profile name"), "Kitchen");
    await user.click(screen.getByRole("button", { name: "Create profile" }));

    expect(await screen.findByRole("heading", { name: "Your Library" })).toBeTruthy();
  });

  it("keeps the entered name and identifies a duplicate on the field", async () => {
    const user = userEvent.setup();
    server.use(
      http.post("/api/v1/profiles", () =>
        HttpResponse.json(
          {
            error: {
              code: "duplicate_record",
              message: "A profile with that name already exists in this household.",
              field: "name",
              retryable: false,
              request_id: "test",
              detail: {},
            },
          },
          { status: 409 },
        ),
      ),
    );
    renderApp();

    const field = await screen.findByLabelText("New profile name");
    await user.type(field, "Household");
    await user.click(screen.getByRole("button", { name: "Create profile" }));

    expect(await screen.findByText(/already exists in this household/)).toBeTruthy();
    expect((field as HTMLInputElement).value).toBe("Household");
    expect(window.location.pathname).toBe("/profiles");
  });

  it("reports a failed listing with a retry rather than an empty house", async () => {
    server.use(http.get("/api/v1/profiles", () => HttpResponse.json({}, { status: 503 })));
    renderApp();

    expect(await screen.findByText("Profiles could not be loaded")).toBeTruthy();
    expect(screen.getByRole("button", { name: "Retry" })).toBeTruthy();
  });

  it("disables creation until a name is entered", async () => {
    renderApp();

    await screen.findByLabelText("New profile name");

    expect(
      screen.getByRole("button", { name: "Create profile" }).hasAttribute("disabled"),
    ).toBe(true);
  });
});
