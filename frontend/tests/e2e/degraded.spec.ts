import { expect, test } from "@playwright/test";
import { chooseHousehold } from "./fixtures";
import { compose } from "./gate-stack";

/**
 * Task 18 — NFR-10: local reads survive with Redis (the acquisition queue's
 * only dependency) gone.
 *
 * `gate-2.spec.ts` already drives a Redis-offline step, but as one leg of a
 * much longer acquisition-and-recovery journey. This suite isolates the
 * guarantee ARCHITECTURE names for NFR-10 on its own — local browse, search,
 * playback, and playlist reads all stay usable — and walks every one of them,
 * not just the single read that journey's step happened to need.
 */

test("NFR-10 — local browse, search, playback, and playlists survive Redis loss", async ({
  page,
}) => {
  test.slow();

  const playlistName = `NFR-10 ${Date.now()}`;

  await test.step("build a playlist and start playback before the fault", async () => {
    await chooseHousehold(page);
    await page.goto("/playlists");
    await page
      .getByRole("button", { name: /Create Playlist/ })
      .first()
      .click();
    const dialog = page.getByRole("dialog");
    await dialog.getByLabel("Name").fill(playlistName);
    await dialog.getByRole("button", { name: "Create" }).click();
    // The name appearing in the list is the observable success signal (the
    // same one gate-1.spec.ts's identical creation step asserts): the dialog
    // closes as a side effect of the same mutation, so asserting on the list
    // update rather than the dialog's own visibility avoids a race between
    // the mutation's success callback and axe/animation timing.
    await expect(page.getByText(playlistName).first()).toBeVisible();

    await page.goto("/library");
    const row = page.getByRole("row", { name: /Digital Love.*Daft Punk/ });
    await row.getByRole("button", { name: "Play Digital Love" }).click();
    const player = page.getByRole("region", { name: "Player" });
    await expect(player.getByRole("button", { name: "Pause" })).toBeVisible();
  });

  await test.step("take Redis away", async () => {
    compose("stop", "redis");
  });

  await test.step("the library is still browsable", async () => {
    await page.reload();
    await expect(
      page.getByRole("row", { name: /Harder Better Faster Stronger.*Daft Punk/ }),
    ).toBeVisible();
  });

  await test.step("local search still answers with no provider request", async () => {
    await page.goto("/search");
    await page.getByLabel("Track or artist").fill("Bonobo");
    await expect(page.getByRole("cell", { name: "Kiara", exact: true })).toBeVisible();
  });

  await test.step("a track still plays locally", async () => {
    await page.goto("/library");
    const row = page.getByRole("row", { name: /Harder Better Faster Stronger.*Daft Punk/ });
    await row.getByRole("button", { name: "Play Harder Better Faster Stronger" }).click();
    const player = page.getByRole("region", { name: "Player" });
    await expect(player.getByRole("button", { name: "Pause" })).toBeVisible();
  });

  await test.step("playlists still read", async () => {
    await page.goto("/playlists");
    await expect(page.getByRole("heading", { name: "Playlists" })).toBeVisible();
    await expect(page.getByText(playlistName).first()).toBeVisible();
  });

  await test.step("the queue reports itself unreachable rather than hanging", async () => {
    await page.goto("/downloads");
    await expect(async () => {
      await page.reload();
      await expect(page.getByText("The download queue is unreachable")).toBeVisible();
    }).toPass({ timeout: 45_000 });
  });

  await test.step("restoring Redis clears the degradation", async () => {
    compose("start", "redis");
    await expect(async () => {
      await page.goto("/downloads");
      await expect(page.getByText("The download queue is unreachable")).toBeHidden();
    }).toPass({ timeout: 45_000 });
  });
});
