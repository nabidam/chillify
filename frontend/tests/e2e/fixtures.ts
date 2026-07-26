import type { Page } from "@playwright/test";

/**
 * Shared helpers for the NFR/cross-browser suite (Task 18).
 *
 * `gate-stack.ts` owns the disposable Compose stack these specs run against;
 * this module owns the browser-side measurement helpers that are common to
 * more than one of `nfr.spec.ts`, `firefox-smoke.spec.ts`, and
 * `degraded.spec.ts` — selecting the seeded household, timing a repeated
 * user action for a percentile, and watching the one `<audio>` element for the
 * events a continuous playback session must never produce.
 */

/** Select the seeded "Household" profile and land on the library. */
export async function chooseHousehold(page: Page): Promise<void> {
  await page.goto("/");
  await page.getByRole("button", { name: "Household" }).click();
  await page.waitForURL(/\/library$/);
}

/** The p95 of a sample, nearest-rank: the method named throughout ARCHITECTURE. */
export function p95(samplesMs: number[]): number {
  if (samplesMs.length === 0) {
    throw new Error("p95 of an empty sample is undefined");
  }
  const sorted = [...samplesMs].sort((a, b) => a - b);
  const rank = Math.min(Math.ceil(0.95 * sorted.length) - 1, sorted.length - 1);
  const value = sorted[rank];
  if (value === undefined) {
    throw new Error("p95 rank computation is out of bounds");
  }
  return value;
}

/** Time one async action in milliseconds. */
export async function timeAction(action: () => Promise<void>): Promise<number> {
  const started = Date.now();
  await action();
  return Date.now() - started;
}

/**
 * A record of every event the one `<audio>` element fired, tagged with the
 * `src` it carried at the time. NFR-5 requires that a route transition during
 * playback never pauses, ends, resets the source, or moves time backward;
 * this is the instrument that makes each of those observable from the test.
 */
export interface AudioEvent {
  type: string;
  src: string;
  currentTime: number;
}

declare global {
  interface Window {
    __chillifyAudioEvents__?: AudioEvent[];
  }
}

const WATCHED_EVENTS = ["play", "pause", "ended", "emptied", "loadstart", "seeked"] as const;

/** Attach the recorder to the page's `<audio>` element. Call before the action under test. */
export async function recordAudioEvents(page: Page): Promise<void> {
  await page.evaluate((eventNames) => {
    const audio = document.querySelector("audio");
    if (audio === null) {
      throw new Error("no <audio> element is mounted");
    }
    window.__chillifyAudioEvents__ = [];
    for (const type of eventNames) {
      audio.addEventListener(type, () => {
        window.__chillifyAudioEvents__?.push({
          type,
          src: audio.currentSrc,
          currentTime: audio.currentTime,
        });
      });
    }
  }, WATCHED_EVENTS);
}

/** Read back everything the recorder captured since `recordAudioEvents`. */
export async function readAudioEvents(page: Page): Promise<AudioEvent[]> {
  return page.evaluate(() => window.__chillifyAudioEvents__ ?? []);
}
