import { defineConfig, devices } from "@playwright/test";

/**
 * End-to-end configuration for the demo-gate journeys.
 *
 * These specs run against the real production composition, not the dev server:
 * a gate proves the app a household would actually run, so the browser talks to
 * the nginx+api+worker stack `scripts/gate/prepare.sh` and the gate overlay
 * bring up. `GATE_BASE_URL` points at that stack (the gate's bound port), and
 * the journey recreates the containers itself for the durability step, so no
 * `webServer` block launches or owns the app here.
 */
const baseURL = process.env.GATE_BASE_URL ?? "http://localhost:8788";

export default defineConfig({
  testDir: "./tests/e2e",
  // The suite provisions its own fresh, seeded gate stack and tears it down, so
  // a run is reproducible from nothing rather than depending on a stack left
  // running by hand. Set GATE_KEEP=1 to leave the stack up for inspection.
  globalSetup: "./tests/e2e/global-setup.ts",
  globalTeardown: "./tests/e2e/global-teardown.ts",
  // The journey is one ordered story with shared durable state; its steps must
  // run in sequence, and a flake should not silently pass on retry.
  fullyParallel: false,
  forbidOnly: !!process.env.CI,
  retries: 0,
  workers: 1,
  reporter: [["list"]],
  timeout: 120_000,
  expect: { timeout: 15_000 },
  use: {
    baseURL,
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
});
