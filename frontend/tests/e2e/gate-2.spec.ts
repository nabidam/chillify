import { expect, test } from "@playwright/test";
import { compose } from "./gate-stack";

/**
 * Demo Gate 2 — acquisition and recovery, walked by a browser.
 *
 * This encodes the journey a human walked at Gate 2 against the same production
 * composition (nginx + api + worker + a disposable Redis) that the gate overlay
 * brings up. It is one ordered story on one page — add music by link (rejecting
 * a bulk link and reviewing a YouTube video), queue and cancel and retry a
 * download and reach an existing track by resubmitting a duplicate, force a
 * proxy failure and confirm secrets are masked while a provider toggles and
 * local playback survives, delete a shared track, and — the unglamorous step —
 * take Redis away, confirm the library still plays while the queue reports
 * itself unreachable, then restore Redis and watch the degradation clear.
 *
 * It is a single test because the steps share one browser session: the active
 * profile lives in that session's storage, so splitting the journey would drop
 * the household selection and bounce every later step back to the profile gate.
 *
 * Two infrastructure levers the browser cannot pull are driven with Compose,
 * exactly as Gate 1 drove the container recreation: the worker is stopped to
 * hold a job in the queue so cancellation and retry are deterministic rather
 * than racing a fixture download that finishes in about a second, and Redis is
 * stopped and started for the offline step. The fault-injection guarantees that
 * are not reproducible through a browser — a worker killed mid-download, an edit
 * that fails after its files are written, restart-safe anonymous history — are
 * asserted by the backend integration suites (test_queue_recovery,
 * test_media_edit_recovery, test_media_delete_recovery) and are not re-driven
 * here; this suite owns the user-visible journey.
 */

// Fixture links the gate's link inspectors recognize. The Spotify track resolves
// to "Instant Crush" (not one of the two seeded tracks, so it is genuinely
// downloadable), the YouTube video to "Teardrop", and the playlist is a bulk
// entity the inspector must refuse before any job exists.
const SPOTIFY_TRACK = "https://open.spotify.com/track/1234567890abcdefghijkl";
const YOUTUBE_VIDEO = "https://youtu.be/u7K72X4eo_s";
const BULK_PLAYLIST = "https://open.spotify.com/playlist/37i9dQZF1DXcBWIGoYBM5M";

// A proxy that resolves but refuses every connection, carrying a credential that
// must never be echoed back — the masking guarantee, made observable.
const DEAD_PROXY_SECRET = "supersecretproxypassword";
const DEAD_PROXY = `socks5://operator:${DEAD_PROXY_SECRET}@127.0.0.1:9`;

test("Gate 2 — acquisition and recovery, end to end", async ({ page }) => {
  // Several Compose stop/start cycles plus two fixture downloads run longer than
  // a single default timeout allows, though each lever is far quicker than the
  // Gate 1 container recreation.
  test.slow();

  const addMusic = () => page.getByRole("button", { name: "Add music" });

  await test.step("select a household and open the shared library", async () => {
    await page.goto("/");
    await expect(page).toHaveURL(/\/profiles$/);
    await page.getByRole("button", { name: "Household" }).click();
    await expect(page).toHaveURL(/\/library$/);
    await expect(
      page.getByRole("row", { name: /Harder Better Faster Stronger.*Daft Punk/ }),
    ).toBeVisible();
  });

  await test.step("a bulk link is refused before any job exists", async () => {
    await addMusic().click();
    const dialog = page.getByRole("dialog");
    await dialog.getByLabel("Link").fill(BULK_PLAYLIST);
    await dialog.getByRole("button", { name: "Continue" }).click();
    // The inspector rejects the album/playlist/artist entity in place; the
    // dialog stays open showing why, and nothing is queued.
    await expect(dialog.getByText(/album, playlist, or artist/i)).toBeVisible();
    await dialog.getByRole("button", { name: "Cancel" }).click();
    await expect(dialog).toBeHidden();
  });

  await test.step("a YouTube video is reviewed, then queued", async () => {
    await addMusic().click();
    const addDialog = page.getByRole("dialog");
    await addDialog.getByLabel("Link").fill(YOUTUBE_VIDEO);
    await addDialog.getByRole("button", { name: "Continue" }).click();

    // YouTube metadata is unreliable, so inspection transitions to the S5 review
    // dialog rather than queueing straight away.
    const review = page.getByRole("dialog", { name: "Review before downloading" });
    await expect(review).toBeVisible();
    await expect(review.getByLabel("Title")).toHaveValue("Teardrop");
    await review.getByRole("button", { name: "Queue download" }).click();
    await expect(review).toBeHidden();
  });

  await test.step("the reviewed download completes durably", async () => {
    await page.goto("/downloads");
    await expect(page.getByText("Completed").first()).toBeVisible({ timeout: 90_000 });
  });

  await test.step("with the worker stopped, a queued download can be cancelled", async () => {
    // Hold the next job in the queue: with no worker to consume it, a fixture
    // download cannot finish before the browser can act on it.
    compose("stop", "worker");

    await addMusic().click();
    const addDialog = page.getByRole("dialog");
    await addDialog.getByLabel("Link").fill(SPOTIFY_TRACK);
    await addDialog.getByRole("button", { name: "Continue" }).click();
    // A Spotify track carries authoritative metadata, so it is downloadable
    // straight from its inspected candidate.
    await expect(addDialog.getByText("Instant Crush")).toBeVisible();
    await addDialog.getByRole("button", { name: "Download" }).click();
    await expect(addDialog).toBeHidden();

    await page.goto("/downloads");
    const queue = page.getByRole("region", { name: "In the queue" });
    const cancel = queue.getByRole("button", { name: "Cancel" });
    await expect(cancel).toBeVisible();
    await cancel.click();
    // The cancelled job leaves the active queue for the finished history.
    await expect(page.getByText("Cancelled").first()).toBeVisible();
  });

  await test.step("retrying the cancelled job completes once the worker returns", async () => {
    // Reopen the finished job and queue a fresh, linked attempt.
    await page.getByText("Cancelled").first().click();
    await page.getByRole("button", { name: "Try this download again" }).click();
    // A new attempt is waiting; nothing consumes it until the worker is back.
    await expect(page.getByRole("region", { name: "In the queue" })).toBeVisible();

    compose("start", "worker");
    // The retried attempt runs to completion; the queue drains.
    await expect(page.getByRole("region", { name: "In the queue" })).toBeHidden({
      timeout: 90_000,
    });
  });

  await test.step("resubmitting the same link reaches the existing track", async () => {
    await addMusic().click();
    const addDialog = page.getByRole("dialog");
    await addDialog.getByLabel("Link").fill(SPOTIFY_TRACK);
    await addDialog.getByRole("button", { name: "Continue" }).click();
    // The duplicate resolves to the track already acquired, so it offers the
    // library rather than a second download.
    await expect(
      addDialog.getByRole("link", { name: /Already in your library/ }),
    ).toBeVisible();
    await expect(addDialog.getByRole("button", { name: "Download" })).toHaveCount(0);
    await addDialog.getByRole("button", { name: "Cancel" }).click();
    await expect(addDialog).toBeHidden();
  });

  await test.step("a failing proxy is reported without leaking its credential", async () => {
    await page.goto("/settings");
    await page.getByLabel("Proxy URL").fill(DEAD_PROXY);
    await page.getByRole("button", { name: "Test", exact: true }).first().click();
    // The proxy-first policy has no direct fallback, so an unreachable proxy is
    // a clear failure — reported with the credential masked out of the message.
    await expect(page.getByText("Proxy test failed")).toBeVisible({ timeout: 30_000 });
    await expect(page.locator("body")).not.toContainText(DEAD_PROXY_SECRET);
  });

  await test.step("a provider toggles off and back on", async () => {
    const deezer = page.getByRole("switch", { name: "Enable Deezer" });
    await expect(deezer).toBeChecked();
    await deezer.click();
    await expect(deezer).not.toBeChecked();
    await deezer.click();
    await expect(deezer).toBeChecked();
  });

  await test.step("local playback is unaffected by the provider changes", async () => {
    await page.goto("/library");
    const row = page.getByRole("row", { name: /Harder Better Faster Stronger.*Daft Punk/ });
    await row.getByRole("button", { name: "Play Harder Better Faster Stronger" }).click();
    const player = page.getByRole("region", { name: "Player" });
    await expect(player.getByText("Harder Better Faster Stronger")).toBeVisible();
  });

  await test.step("a shared track is deleted for the whole household", async () => {
    await page.goto("/library");
    const row = page.getByRole("row", { name: /Digital Love.*Daft Punk/ });
    await row.getByRole("button", { name: "Actions for Digital Love" }).click();
    await page.getByRole("menuitem", { name: "Edit details" }).click();

    const editor = page.getByRole("dialog", { name: "Track details" });
    await expect(editor).toBeVisible();
    await editor.getByRole("button", { name: "Delete track" }).click();

    const confirm = page.getByRole("alertdialog");
    await expect(confirm).toBeVisible();
    // Delete stays disabled until the impact resolves, then removes the track.
    const deletePermanently = confirm.getByRole("button", { name: "Delete Permanently" });
    await expect(deletePermanently).toBeEnabled({ timeout: 30_000 });
    await deletePermanently.click();

    await expect(page.getByRole("row", { name: /Digital Love.*Daft Punk/ })).toHaveCount(0);
  });

  await test.step("with Redis gone, the queue reports itself unreachable", async () => {
    compose("stop", "redis");
    await page.goto("/downloads");
    await expect(async () => {
      await page.reload();
      await expect(page.getByText("The download queue is unreachable")).toBeVisible();
    }).toPass({ timeout: 45_000 });
  });

  await test.step("the local library still plays while Redis is down", async () => {
    await page.goto("/library");
    const row = page.getByRole("row", { name: /Harder Better Faster Stronger.*Daft Punk/ });
    await row.getByRole("button", { name: "Play Harder Better Faster Stronger" }).click();
    const player = page.getByRole("region", { name: "Player" });
    await expect(player.getByText("Harder Better Faster Stronger")).toBeVisible();
  });

  await test.step("restoring Redis clears the degradation without a web restart", async () => {
    compose("start", "redis");
    await expect(async () => {
      await page.goto("/downloads");
      await expect(page.getByText("The download queue is unreachable")).toBeHidden();
    }).toPass({ timeout: 45_000 });
  });
});
