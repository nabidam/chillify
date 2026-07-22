import { setTimeout as sleep } from "node:timers/promises";
import { compose, GATE, gateScript } from "./gate-stack";

const BASE_URL = process.env.GATE_BASE_URL ?? "http://localhost:8788";

/**
 * Bring up a fresh, seeded gate stack before the journey runs.
 *
 * Every prior run is removed first, so the environment is provisioned from
 * nothing: prepare writes the disposable tree and its `.env`, Compose builds
 * and starts the production images plus the fixture overlay, and seed writes
 * the household and its two tracks once the api answers. A run therefore never
 * inherits a track a previous run downloaded.
 */
async function globalSetup(): Promise<void> {
  gateScript("cleanup.sh", GATE);
  gateScript("prepare.sh", GATE, "gate");
  compose("up", "--build", "-d");
  await waitForReady();
  gateScript("seed.sh", GATE);
}

async function waitForReady(): Promise<void> {
  const deadline = Date.now() + 120_000;
  let lastError = "never reached";
  while (Date.now() < deadline) {
    try {
      const response = await fetch(`${BASE_URL}/api/v1/system/health`);
      if (response.ok) {
        const body = (await response.json()) as { status?: string };
        if (body.status === "ready") {
          return;
        }
        lastError = `status ${body.status}`;
      } else {
        lastError = `HTTP ${response.status}`;
      }
    } catch (error) {
      lastError = error instanceof Error ? error.message : String(error);
    }
    await sleep(2_000);
  }
  throw new Error(`gate stack did not become ready within 120s (last: ${lastError})`);
}

export default globalSetup;
