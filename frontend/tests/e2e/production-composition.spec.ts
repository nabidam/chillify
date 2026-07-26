import { spawnSync } from "node:child_process";
import { setTimeout as sleep } from "node:timers/promises";
import { expect, test } from "@playwright/test";
import { compose, GATE, gateScript, REPO_ROOT } from "./gate-stack";

/**
 * Task 19 (gate 4) — the unchanged production composition, proven live.
 *
 * Every other gate spec in this suite runs against `deploy/compose.gate.yaml`'s
 * fixture overlay, brought up once by `global-setup.ts` before any spec file
 * runs. This spec proves the other half of the composition root: the real,
 * unchanged production Compose entry point — no gate overlay, no fixture
 * adapters — resolves real provider/tool/Redis/SQLite/media implementations,
 * reports each one, and reaches ready or degraded state on a disposable root.
 *
 * `compose.yaml` names one fixed Compose project (`name: chillify`), so only
 * one stack can run on this host at a time regardless of which `.env` brought
 * it up — a second `docker compose up` under a different env file does not
 * coexist with the first, it adopts and mutates the same containers. That
 * makes this spec's ordering claim ("real classes resolve *before*
 * deterministic fixtures are used") a real constraint, not just prose: this
 * spec explicitly tears down whatever `global-setup.ts` already brought up,
 * proves the production composition on its own disposable environment while
 * nothing else is running, and then restores the shared fixture stack exactly
 * as `global-setup.ts` provisions it — so a spec file ordered after this one
 * (alphabetically, none in this suite are) still finds the environment it was
 * promised. `scripts/production_canary.sh` is driven directly, the same
 * script a household operator or Task 20's release-gate preflight runs,
 * rather than reimplementing its checks in TypeScript.
 *
 * Building and starting the real images is slow even from cache, so this
 * spec runs its own three canary invocations (success path, forced network
 * failure, and the `--no-live-success` bypass); `test.slow()` gives each the
 * same generous budget the NFR suite gives its own multi-step journeys.
 */

const NAME = "gate-4-production-canary";
const ENV_FILE = `.gate/${NAME}/.env`;
const PORT = "8799";
// A reserved, non-routable TEST-NET-2 address (RFC 5737): guaranteed to fail a
// connection attempt without depending on any real host being up or down, so
// the network-failure assertion is deterministic rather than a bet on the
// live internet's state at test time.
const UNREACHABLE_URL = "http://198.51.100.1:65500/";

// Scoped to this one call, not the whole process: `test.afterAll` below
// restores the *shared* `GATE` environment via the same `prepare.sh`, which
// must keep reading its own default port (8788) rather than inheriting ours.
function prepareProductionCanaryEnv(): void {
  const result = spawnSync("./scripts/gate/prepare.sh", [NAME, "production"], {
    cwd: REPO_ROOT,
    encoding: "utf-8",
    env: { ...process.env, CHILLIFY_BIND_PORT: PORT },
  });
  if (result.status !== 0) {
    throw new Error(`prepare.sh ${NAME} production failed: ${result.stderr ?? ""}`);
  }
}

// The canary reports its live-reachability result on stderr and everything
// else on stdout; `execFileSync`'s return value on a *successful* exit is
// stdout only, so a bare call would silently drop the "live reachability
// ..." line whenever the process happens to exit 0. `stdio: "pipe"` plus
// reading `.stdout`/`.stderr` off the result — via `spawnSync`, which returns
// them even on success — keeps both, merged in the order the script itself
// interleaves them onto its own terminal.
function canary(args: string[], env?: Record<string, string>): string {
  const result = spawnSync("./scripts/production_canary.sh", args, {
    cwd: REPO_ROOT,
    encoding: "utf-8",
    timeout: 240_000,
    env: { ...process.env, ...env },
  });
  const combined = `${result.stdout ?? ""}${result.stderr ?? ""}`;
  if (result.status !== 0) {
    throw new CanaryFailure(combined, result.status);
  }
  return combined;
}

class CanaryFailure extends Error {
  output: string;
  status: number | null;

  constructor(output: string, status: number | null) {
    super(`scripts/production_canary.sh exited ${status}`);
    this.output = output;
    this.status = status;
  }
}

function canaryFails(args: string[], env?: Record<string, string>): string {
  try {
    canary(args, env);
  } catch (error) {
    if (error instanceof CanaryFailure) {
      expect(error.status).not.toBe(0);
      return error.output;
    }
    throw error;
  }
  throw new Error("expected scripts/production_canary.sh to fail, but it exited 0");
}

async function waitForReady(baseUrl: string): Promise<void> {
  const deadline = Date.now() + 120_000;
  let lastError = "never reached";
  while (Date.now() < deadline) {
    try {
      const response = await fetch(`${baseUrl}/api/v1/system/health`);
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
  throw new Error(`stack at ${baseUrl} did not become ready within 120s (last: ${lastError})`);
}

test.describe
  .serial("production composition canary (gate 4)", () => {
    test.beforeAll(() => {
      // Only one Compose project can run at a time; hand it over cleanly before
      // this describe block starts using it for something else.
      compose("down", "--remove-orphans");
    });

    test.afterAll(async () => {
      // Give the shared fixture stack back exactly as global-setup provisioned
      // it, for any spec that runs after this one in the same session. A full
      // build+up+seed cycle routinely exceeds the default 120s hook timeout.
      test.setTimeout(300_000);
      gateScript("cleanup.sh", GATE);
      gateScript("prepare.sh", GATE, "gate");
      compose("up", "--build", "-d");
      await waitForReady(process.env.GATE_BASE_URL ?? "http://localhost:8788");
      gateScript("seed.sh", GATE, process.env.GATE_SCENARIO ?? "default");
    });

    test.beforeEach(() => {
      gateScript("cleanup.sh", NAME);
      prepareProductionCanaryEnv();
    });

    test.afterEach(() => {
      gateScript("cleanup.sh", NAME);
    });

    test("resolves real provider/tool/Redis/SQLite/media adapters and reaches ready or degraded", async () => {
      test.slow();

      const output = canary(["--env-file", ENV_FILE, "--no-live-success"]);

      expect(output).toContain(
        "production_canary: bringing up the unchanged production composition",
      );
      // ready or degraded — either is a legitimate outcome; a crash or an
      // unavailable database is not, and either would make this assertion fail.
      expect(output).toMatch(/production_canary: ready=true degraded=(true|false)/);
      // Every real adapter/tool this environment allows is named in the report.
      for (const provider of ["deezer", "spotdl", "yt_dlp", "lastfm"]) {
        expect(output).toContain(`production_canary: provider: {"name": "${provider}"`);
      }
      for (const tool of ["ffmpeg", "ffprobe", "yt_dlp", "spotdl", "deno"]) {
        expect(output).toContain(`production_canary: tool: {"name": "${tool}"`);
      }
      expect(output).toContain("production_canary: PASS");
    });

    test("a network failure is a clear canary failure with no fallback, unless --no-live-success is passed", async () => {
      test.slow();

      const failure = canaryFails(["--env-file", ENV_FILE], {
        CHILLIFY_CANARY_LIVE_URL: UNREACHABLE_URL,
      });
      expect(failure).toContain("production_canary: live reachability failed");
      expect(failure).toContain(
        "production_canary: FAILED — live reachability is required and was not satisfied",
      );

      // The teardown trap inside the script already tore its own containers
      // down on that failure; bring the environment back up fresh rather than
      // assuming what state it was left in before proving the bypass.
      gateScript("cleanup.sh", NAME);
      prepareProductionCanaryEnv();

      const bypassed = canary(["--env-file", ENV_FILE, "--no-live-success"], {
        CHILLIFY_CANARY_LIVE_URL: UNREACHABLE_URL,
      });
      expect(bypassed).toContain("production_canary: live reachability failed");
      expect(bypassed).toContain(
        "live reachability not required (--no-live-success); continuing",
      );
      expect(bypassed).toContain("production_canary: PASS");
    });

    test("refuses an env file outside the disposable .gate/ tree, before any container starts", async () => {
      // Fast, no-Docker refusal — the containment check runs before `docker
      // compose up`. The household-*root* refusal (a gate-shaped env file
      // naming real household storage) is covered in depth at the contract
      // layer (backend/tests/integration/test_production_composition.py); this
      // is the one live confirmation, from this suite's own shell, that a
      // non-disposable env file is refused the same way.
      const output = canaryFails(["--env-file", "/etc/hostname"]);
      expect(output).toContain("refusing a non-disposable env file");
    });
  });
