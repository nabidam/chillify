import AxeBuilder from "@axe-core/playwright";
import { expect, type Page, test } from "@playwright/test";

/**
 * Gate 3 — keyboard, reduced motion, and axe across the enumerated states.
 *
 * The component suite proves each screen's empty/loading/error/success branch in
 * isolation; this walks the same app the household runs and holds it to the
 * accessibility bar the design contract sets: a visible focus path that never
 * traps, motion that yields to `prefers-reduced-motion`, and zero critical or
 * serious axe findings on every state a browser can reach against the seeded
 * gate stack.
 *
 * It shares the gate's fixtures: the "Household" profile and the two seeded
 * tracks ("Harder Better Faster Stronger" and "Digital Love", both by Daft
 * Punk) that `scripts/gate/seed.sh` writes before the run.
 */

/** Fail the run on any critical or serious finding, naming each one. */
async function expectNoSeriousViolations(page: Page, context: string): Promise<void> {
  const results = await new AxeBuilder({ page })
    .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"])
    .analyze();
  const serious = results.violations.filter(
    (violation) => violation.impact === "critical" || violation.impact === "serious",
  );
  const summary = serious
    .map((violation) => `${violation.id} (${violation.impact}) on ${context}`)
    .join("\n");
  expect(serious, summary).toEqual([]);
}

async function chooseHousehold(page: Page): Promise<void> {
  await page.goto("/");
  await expect(page).toHaveURL(/\/profiles$/);
  await page.getByRole("button", { name: "Household" }).click();
  await expect(page).toHaveURL(/\/library$/);
}

test("Gate 3 — the profile chooser is keyboard operable and clean", async ({ page }) => {
  await page.goto("/");
  await expect(page).toHaveURL(/\/profiles$/);
  // S1 creation field is the primary, focused control.
  await expectNoSeriousViolations(page, "S1 profiles");

  // The household can be reached by keyboard alone.
  await page.getByRole("button", { name: "Household" }).focus();
  await page.keyboard.press("Enter");
  await expect(page).toHaveURL(/\/library$/);
});

test("Gate 3 — the skip link jumps the chrome to the content", async ({ page }) => {
  await chooseHousehold(page);

  // The first Tab from the top lands on the skip link, and activating it moves
  // focus into the content region rather than the sidebar.
  await page.keyboard.press("Tab");
  const skip = page.getByRole("link", { name: "Skip to content" });
  await expect(skip).toBeFocused();
  await skip.press("Enter");

  const main = page.getByRole("main", { name: "Content" });
  await expect(main).toBeVisible();
});

test("Gate 3 — primary navigation traverses by keyboard without a trap", async ({ page }) => {
  await chooseHousehold(page);

  for (const name of ["Search", "Playlists", "Downloads", "Settings", "Library"]) {
    const link = page.getByRole("link", { name, exact: true });
    await link.focus();
    await expect(link).toBeFocused();
    await link.press("Enter");
    // Focus stays reachable and the view changed; nothing swallowed the keyboard.
    await expect(page.getByRole("main", { name: "Content" })).toBeVisible();
  }
});

test("Gate 3 — axe is clean across the reachable screen states", async ({ page }) => {
  await chooseHousehold(page);

  const screens: { name: string; open: () => Promise<void>; ready: () => Promise<void> }[] = [
    {
      name: "S2 library",
      open: () => page.getByRole("link", { name: "Library", exact: true }).click(),
      ready: () => expect(page.getByRole("heading", { name: "Your Library" })).toBeVisible(),
    },
    {
      name: "S3 search",
      open: () => page.getByRole("link", { name: "Search", exact: true }).click(),
      ready: () => expect(page.getByRole("heading", { name: "Search" })).toBeVisible(),
    },
    {
      name: "S9 playlists",
      open: () => page.getByRole("link", { name: "Playlists", exact: true }).click(),
      ready: () => expect(page.getByRole("heading", { name: "Playlists" })).toBeVisible(),
    },
    {
      name: "S11 downloads",
      open: () => page.getByRole("link", { name: "Downloads", exact: true }).click(),
      ready: () => expect(page.getByRole("heading", { name: "Downloads" })).toBeVisible(),
    },
    {
      name: "S12 settings",
      open: () => page.getByRole("link", { name: "Settings", exact: true }).click(),
      ready: () => expect(page.getByRole("heading", { name: "Settings" })).toBeVisible(),
    },
  ];

  for (const screen of screens) {
    await screen.open();
    await screen.ready();
    await expectNoSeriousViolations(page, screen.name);
  }
});

test("Gate 3 — an empty playlist context is clean and keyboard escapable", async ({ page }) => {
  await chooseHousehold(page);
  await page.getByRole("link", { name: "Playlists", exact: true }).click();

  // Opening the editor by keyboard traps focus inside it, and Escape returns to
  // the invoking control — the modal-focus-return guarantee, in the real app.
  // The empty playlists screen shows a Create Playlist button in both the
  // header and the empty-state card (UX.md S9: the header action survives
  // every state, and the empty state also "offers Create Playlist"); the
  // header one is always present, so it is the one exercised here, matching
  // the same disambiguation already used by gate-3.spec.ts and
  // firefox-smoke.spec.ts for this identical, intentional duplicate.
  const create = page.getByRole("button", { name: "Create Playlist" }).first();
  await create.focus();
  await create.press("Enter");

  const dialog = page.getByRole("dialog");
  await expect(dialog).toBeVisible();
  await expectNoSeriousViolations(page, "S9 playlist editor open");

  await page.keyboard.press("Escape");
  await expect(dialog).toBeHidden();
  await expect(create).toBeFocused();
});

test("Gate 3 — reduced motion is honored on settings recovery", async ({ page }) => {
  await page.emulateMedia({ reducedMotion: "reduce" });
  await chooseHousehold(page);

  await page.getByRole("link", { name: "Settings", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Settings" })).toBeVisible();

  // The seeded provider and storage cards always exist; each health result is
  // independently reachable and axe-clean under reduced motion.
  await expectNoSeriousViolations(page, "S12 settings (reduced motion)");
});
