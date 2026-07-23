import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router";
import { describe, expect, it, vi } from "vitest";
import { AppSidebar } from "@/app/AppSidebar";
import { ActiveProfileContext, type ActiveProfileSession } from "@/app/activeProfile";
import { SidebarProvider } from "@/components/ui/sidebar";

/**
 * The sidebar's "Choose profile" control must actually switch profiles.
 *
 * Switching is the one thing that clears the browser-session queue before the
 * shell is left (`clearProfile` in AppProviders), so the guarantee that a
 * session does not leak into the next profile depends on this button being
 * wired to that action. A dead button would silently drop the guarantee, which
 * this test forbids by asserting the wiring directly.
 */

const PROFILE_ID = "019f8e33-8ebc-70b6-bb53-2e3833215606";

function renderSidebar(session: ActiveProfileSession) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false, staleTime: 0 } },
  });
  return render(
    <MemoryRouter initialEntries={["/library"]}>
      <QueryClientProvider client={queryClient}>
        <ActiveProfileContext value={session}>
          <SidebarProvider>
            <AppSidebar />
          </SidebarProvider>
        </ActiveProfileContext>
      </QueryClientProvider>
    </MemoryRouter>,
  );
}

describe("Choose profile — switching the profile", () => {
  it("invokes clearProfile when clicked", async () => {
    const clearProfile = vi.fn();
    renderSidebar({
      activeProfileId: PROFILE_ID,
      selectProfile: vi.fn(),
      clearProfile,
    });

    await userEvent.click(screen.getByRole("button", { name: "Choose profile" }));

    expect(clearProfile).toHaveBeenCalledTimes(1);
  });
});
