import { expect, test } from "@playwright/test";
import { compose } from "./gate-stack";

/**
 * Demo Gate 1 — the walking skeleton, walked by a browser.
 *
 * This encodes the journey a human walked at the gate, against the same
 * production composition (nginx + api + worker + a disposable Redis) that
 * `scripts/gate/prepare.sh gate-1 gate` and `deploy/compose.gate.yaml` bring
 * up. It is one ordered story on one page — select a household, search locally
 * and then on Deezer, download a non-playable remote result, watch it stay
 * durable across a reload, play and correct a track, build a playlist, and —
 * the unglamorous step — recreate the production containers and confirm every
 * durable record survives while the browser's own session state is gone.
 *
 * It is a single test because the steps share one browser session: the active
 * profile lives in that session's storage, so splitting the journey into
 * separate tests would drop the household selection and bounce every later
 * step back to the profile gate. The launch and seed are the preflight a human
 * runs before this suite; the suite owns only the container *recreation* in the
 * final step, because that is the behaviour under test. Provisioning and
 * disposing the stack are `global-setup`/`global-teardown`.
 */

// A fixture Deezer result that is NOT one of the two seeded Daft Punk tracks,
// so it comes back genuinely non-playable and downloadable rather than
// "already in your library".
const REMOTE_QUERY = "Teardrop";
// A unique playlist name per run keeps the journey idempotent against a gate
// environment that an earlier walkthrough may already have written to.
const PLAYLIST_NAME = `Gate Run ${Date.now()}`;
const CORRECTED_ALBUM = `Discovery ${Date.now()}`;

test("Gate 1 — the walking skeleton, end to end", async ({ page }) => {
  await test.step("select a household and open the shared library", async () => {
    await page.goto("/");
    await expect(page).toHaveURL(/\/profiles$/);
    await page.getByRole("button", { name: "Household" }).click();
    await expect(page).toHaveURL(/\/library$/);
    await expect(
      page.getByRole("row", { name: /Harder Better Faster Stronger.*Daft Punk/ }),
    ).toBeVisible();
  });

  await test.step("search locally with no provider activity, then explicitly on Deezer", async () => {
    await page.goto("/search");
    await page.getByLabel("Track or artist").fill("Digital");
    await expect(page.getByRole("cell", { name: "Digital Love", exact: true })).toBeVisible();

    await page.getByLabel("Track or artist").fill(REMOTE_QUERY);
    await page.getByRole("button", { name: "Search Deezer" }).click();
  });

  await test.step("download a non-playable remote result", async () => {
    const firstResult = page.getByRole("button", { name: /^Download / }).first();
    await expect(firstResult).toBeVisible();
    await firstResult.click();

    await page.goto("/downloads");
    await expect(page.getByText(/completed/i).first()).toBeVisible({ timeout: 90_000 });
  });

  await test.step("a reload shows the download's durable, truthful completion", async () => {
    await page.reload();
    await expect(page.getByText(/completed/i).first()).toBeVisible();
  });

  // Row actions are scoped to the seeded track's row (matched by title and
  // artist together) so they stay unambiguous even as the library grows.
  const seededRow = page.getByRole("row", { name: /Harder Better Faster Stronger.*Daft Punk/ });

  await test.step("play a track from the library", async () => {
    await page.goto("/library");
    await seededRow.getByRole("button", { name: "Play Harder Better Faster Stronger" }).click();
    const player = page.getByRole("region", { name: "Player" });
    await expect(player.getByText("Harder Better Faster Stronger")).toBeVisible();
    await expect(player.getByRole("button", { name: "Pause" })).toBeVisible();
  });

  await test.step("correct the track's metadata in one save", async () => {
    await seededRow
      .getByRole("button", { name: "Actions for Harder Better Faster Stronger" })
      .click();
    await page.getByRole("menuitem", { name: "Edit details" }).click();
    const editor = page.getByRole("dialog");
    await editor.getByLabel("Album").fill(CORRECTED_ALBUM);
    await editor.getByRole("button", { name: "Save" }).click();
    await expect(editor).toBeHidden();
    await expect(page.getByRole("cell", { name: CORRECTED_ALBUM, exact: true })).toBeVisible();
  });

  // From here the journey navigates by clicking the shell's own links, not by
  // reloading the page: a full reload would reset the in-memory player and
  // defeat the very thing this step proves. `page.goto` returns only in the
  // final step, which deliberately starts a fresh session.
  const navTo = (label: string) => page.getByRole("link", { name: label, exact: true });

  await test.step("create a playlist for the active profile", async () => {
    await navTo("Playlists").click();
    await expect(page).toHaveURL(/\/playlists$/);
    // Header and empty-state both offer this on a profile with no playlists yet.
    await page
      .getByRole("button", { name: /Create Playlist/ })
      .first()
      .click();
    const dialog = page.getByRole("dialog");
    await dialog.getByLabel("Name").fill(PLAYLIST_NAME);
    await dialog.getByRole("button", { name: "Create" }).click();
    await expect(page.getByText(PLAYLIST_NAME).first()).toBeVisible();
  });

  await test.step("add the track and navigate without resetting playback", async () => {
    await navTo("Library").click();
    await expect(page).toHaveURL(/\/library$/);
    await seededRow
      .getByRole("button", { name: "Actions for Harder Better Faster Stronger" })
      .click();
    await page.getByRole("menuitem", { name: PLAYLIST_NAME }).click();

    // Client-side navigation across the shell must not reset playback. Playing
    // from the library queues the whole library, so the brief fixture tone may
    // have ended and auto-advanced; what must survive the navigation is that
    // something is still loaded in the player, not the empty state.
    await navTo("Playlists").click();
    await expect(page).toHaveURL(/\/playlists$/);
    const player = page.getByRole("region", { name: "Player" });
    await expect(player.getByText(/Nothing is playing/)).toBeHidden();
  });

  await test.step("recreate the production containers and verify durable records", async () => {
    // The unglamorous step. Recreate every service against the same disposable
    // mounts. This takes the web and api containers down and back up, so wait
    // for the stack to answer again — over plain HTTP, which does not need the
    // SPA loaded — before navigating.
    compose("up", "-d", "--force-recreate");
    await expect(async () => {
      const response = await page.request.get("/api/v1/system/health");
      expect(response.ok()).toBeTruthy();
    }).toPass({ timeout: 90_000 });

    // Start this browser's session empty: durable records must come from the
    // server, not from the queue or playback state the earlier steps built up.
    await page.context().clearCookies();
    await page.goto("/");
    await page.evaluate(() => window.localStorage.clear());
    await page.goto("/");
    await expect(page).toHaveURL(/\/profiles$/);
    await page.getByRole("button", { name: "Household" }).click();
    await expect(page).toHaveURL(/\/library$/);

    // The corrected track survived with only its new version.
    await expect(page.getByRole("cell", { name: CORRECTED_ALBUM, exact: true })).toBeVisible();

    // The playlist built before the restart is still there.
    await page.goto("/playlists");
    await expect(page.getByText(PLAYLIST_NAME).first()).toBeVisible();

    // The downloaded job is still terminal, read from durable state.
    await page.goto("/downloads");
    await expect(page.getByText(/completed/i).first()).toBeVisible();

    // Nothing is playing in this fresh session: durable records survived, the
    // session's playback did not.
    const player = page.getByRole("region", { name: "Player" });
    await expect(player.getByText(/Nothing is playing/)).toBeVisible();
  });
});
