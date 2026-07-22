import { execFileSync } from "node:child_process";

/**
 * Shared control of the disposable gate stack the Gate 1 journey runs against.
 *
 * The e2e suite owns its environment end to end: global setup brings up a fresh
 * gate from nothing and seeds it, global teardown removes it, and the journey's
 * durability step recreates the containers in between. Because every run starts
 * from a clean seed, the journey is reproducible — a track it downloads is not
 * already present from a previous run.
 */

export const GATE = process.env.GATE_NAME ?? "gate-1";
export const ENV_FILE = `.gate/${GATE}/.env`;
export const COMPOSE_FILES = ["-f", "compose.yaml", "-f", "deploy/compose.gate.yaml"];
// This file lives at frontend/tests/e2e/; the repository root is three up.
export const REPO_ROOT = new URL("../../../", import.meta.url).pathname;

export function run(command: string, args: string[]): void {
  execFileSync(command, args, { cwd: REPO_ROOT, stdio: "inherit", timeout: 300_000 });
}

export function compose(...args: string[]): void {
  run("docker", ["compose", "--env-file", ENV_FILE, ...COMPOSE_FILES, ...args]);
}

export function gateScript(script: string, ...args: string[]): void {
  run(`./scripts/gate/${script}`, args);
}
