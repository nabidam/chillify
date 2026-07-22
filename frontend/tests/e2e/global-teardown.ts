import { GATE, gateScript } from "./gate-stack";

/**
 * Remove the disposable gate stack the journey ran against.
 *
 * cleanup.sh stops the containers and deletes only its own tree beneath
 * `.gate/`, so nothing the suite created outlives it. Kept best-effort: a
 * teardown failure must not mask a real test result.
 */
async function globalTeardown(): Promise<void> {
  if (process.env.GATE_KEEP === "1") {
    return;
  }
  try {
    gateScript("cleanup.sh", GATE);
  } catch (error) {
    const reason = error instanceof Error ? error.message : String(error);
    process.stderr.write(`gate teardown failed: ${reason}\n`);
  }
}

export default globalTeardown;
