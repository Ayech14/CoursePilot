import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";
import { afterEach, vi } from "vitest";

import { setAccessToken } from "../lib/api";

afterEach(() => {
  cleanup();
  setAccessToken(null);
  vi.unstubAllGlobals();
});
