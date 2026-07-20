import { cleanup } from "@testing-library/react";
import { afterAll, afterEach, beforeAll, vi } from "vitest";
import { server } from "./msw/server";

// jsdom implements neither of these, and the Shadcn Sidebar reads both.
beforeAll(() => {
  vi.stubGlobal(
    "matchMedia",
    vi.fn().mockImplementation((query: string) => ({
      matches: false,
      media: query,
      onchange: null,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      addListener: vi.fn(),
      removeListener: vi.fn(),
      dispatchEvent: vi.fn(),
    })),
  );
  globalThis.ResizeObserver = class {
    observe() {}
    unobserve() {}
    disconnect() {}
  };
  // jsdom has no media pipeline at all. The controller's contract is which
  // calls it makes and in what order, so the calls are recorded rather than
  // performed; real playback is a gate concern, not a jsdom one.
  Object.defineProperties(window.HTMLMediaElement.prototype, {
    load: { configurable: true, value: vi.fn() },
    play: { configurable: true, value: vi.fn().mockResolvedValue(undefined) },
    pause: { configurable: true, value: vi.fn() },
  });

  server.listen({ onUnhandledRequest: "error" });
});

afterEach(() => {
  cleanup();
  server.resetHandlers();
  // The active-profile session and the jsdom URL both outlive a render.
  // Leaking either would let one test decide which screen the next one opens.
  window.localStorage.clear();
  window.history.replaceState(null, "", "/");
});

afterAll(() => {
  server.close();
});
