import { expect, test } from "@playwright/test";
import {
  chooseHousehold,
  p95,
  readAudioEvents,
  recordAudioEvents,
  timeAction,
} from "./fixtures";

/**
 * Task 18 — named NFR evidence (Chromium).
 *
 * Each test times a repeated user action against the seeded "listening" gate
 * stack and reports its own named line (`NFR-n: ...`), which
 * `scripts/verify/nfr.sh` collects as the evidence artifact. This is the
 * mechanism ARCHITECTURE section 14's numeric-gate table names, run here at a
 * scale that proves it measures correctly; Task 20's release gate reruns the
 * same specs against the full seeded (kernel-500) release stack for the v1
 * exit bar's own numbers.
 *
 * Firefox's share of this evidence (NFR-3's "per browser" clause and NFR-9)
 * lives in firefox-smoke.spec.ts; this file is Chromium-only by convention
 * (the default project excludes only firefox-smoke.spec.ts).
 */

const SAMPLE_SIZE = 20;
const PLAYBACK_SAMPLE_SIZE = 10;

test("NFR-1 — 20 local searches render within budget", async ({ page }) => {
  await chooseHousehold(page);
  await page.goto("/search");
  const input = page.getByLabel("Track or artist");

  // Two distinct seeded queries, alternated, so each search is a genuine
  // re-render rather than a no-op on an unchanged value.
  const queries = ["Daft Punk", "Bonobo"];
  const samples: number[] = [];
  for (let i = 0; i < SAMPLE_SIZE; i += 1) {
    const query = queries[i % queries.length] as string;
    await input.fill("");
    const elapsed = await timeAction(async () => {
      await input.fill(query);
      await expect(page.getByRole("cell", { name: query, exact: false }).first()).toBeVisible();
    });
    samples.push(elapsed);
  }

  const value = p95(samples);
  // biome-ignore lint/suspicious/noConsole: named NFR evidence for scripts/verify/nfr.sh to collect.
  console.log(`NFR-1: rendered p95=${value}ms (limit 300ms) over ${samples.length} searches`);
  expect(value).toBeLessThanOrEqual(300);
});

test("NFR-2 — 20 cached route transitions render within budget", async ({ page }) => {
  await chooseHousehold(page);

  const destinations: { link: string; heading: string }[] = [
    { link: "Library", heading: "Your Library" },
    { link: "Search", heading: "Search" },
    { link: "Playlists", heading: "Playlists" },
    { link: "Downloads", heading: "Downloads" },
    { link: "Settings", heading: "Settings" },
  ];

  const samples: number[] = [];
  for (let i = 0; i < SAMPLE_SIZE; i += 1) {
    const destination = destinations[i % destinations.length] as (typeof destinations)[number];
    const elapsed = await timeAction(async () => {
      await page.getByRole("link", { name: destination.link, exact: true }).click();
      await expect(page.getByRole("heading", { name: destination.heading })).toBeVisible();
    });
    samples.push(elapsed);
  }

  const value = p95(samples);
  // biome-ignore lint/suspicious/noConsole: named NFR evidence for scripts/verify/nfr.sh to collect.
  console.log(
    `NFR-2: transition p95=${value}ms (limit 500ms) over ${samples.length} transitions`,
  );
  expect(value).toBeLessThanOrEqual(500);
});

test("NFR-3 (Chromium) — 10 representative MP3 starts within budget", async ({ page }) => {
  await chooseHousehold(page);
  await page.goto("/library");

  // Alternating between two distinct tracks, rather than pausing and
  // restarting the same one, guarantees each start is a genuine new-source
  // load (`useAudioController` only reassigns `audio.src` when the track ID
  // itself changes) instead of depending on the transport button's current
  // label, which a short fixture tone can already have moved past a paused
  // state's assumption of what "the last click did" left it in.
  const tracks = [
    { name: "Harder Better Faster Stronger", artist: "Daft Punk" },
    { name: "Digital Love", artist: "Daft Punk" },
  ];
  const player = page.getByRole("region", { name: "Player" });

  const samples: number[] = [];
  for (let i = 0; i < PLAYBACK_SAMPLE_SIZE; i += 1) {
    const track = tracks[i % tracks.length] as (typeof tracks)[number];
    const row = page.getByRole("row", { name: new RegExp(`${track.name}.*${track.artist}`) });
    const elapsed = await timeAction(async () => {
      await row.getByRole("button", { name: `Play ${track.name}` }).click();
      await expect(player.getByText(track.name)).toBeVisible();
      await expect(player.getByRole("button", { name: "Pause" })).toBeVisible();
    });
    samples.push(elapsed);
  }

  const value = p95(samples);
  // biome-ignore lint/suspicious/noConsole: named NFR evidence for scripts/verify/nfr.sh to collect.
  console.log(
    `NFR-3 (Chromium): playback-start p95=${value}ms (limit 1000ms) over ${samples.length} starts`,
  );
  expect(value).toBeLessThanOrEqual(1000);
});

test("NFR-5 — 20 route transitions while playing never interrupt playback", async ({
  page,
}) => {
  await chooseHousehold(page);
  await page.goto("/library");

  const row = page.getByRole("row", { name: /Harder Better Faster Stronger.*Daft Punk/ });
  await row.getByRole("button", { name: "Play Harder Better Faster Stronger" }).click();
  const player = page.getByRole("region", { name: "Player" });
  await expect(player.getByRole("button", { name: "Pause" })).toBeVisible();

  await recordAudioEvents(page);

  const destinations = ["Search", "Playlists", "Downloads", "Settings", "Library"];
  for (let i = 0; i < SAMPLE_SIZE; i += 1) {
    await page
      .getByRole("link", { name: destinations[i % destinations.length], exact: true })
      .click();
    await expect(page.getByRole("main", { name: "Content" })).toBeVisible();
  }

  // Playback must still be running, on the same track, after every transition.
  await expect(player.getByRole("button", { name: "Pause" })).toBeVisible();
  await expect(player.getByText("Harder Better Faster Stronger")).toBeVisible();

  const events = await readAudioEvents(page);
  const disruptions = events.filter((event) => event.type !== "seeked");
  // biome-ignore lint/suspicious/noConsole: named NFR evidence for scripts/verify/nfr.sh to collect.
  console.log(
    `NFR-5: ${SAMPLE_SIZE} route transitions while playing, ${disruptions.length} disruptive audio events`,
  );
  expect(disruptions, JSON.stringify(disruptions)).toEqual([]);

  // No event carried a source other than the one track that started playing.
  const sources = new Set(events.map((event) => event.src));
  expect(sources.size).toBeLessThanOrEqual(1);
});
