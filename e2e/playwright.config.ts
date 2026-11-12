import { defineConfig, devices } from "@playwright/test";

/**
 * Journeys through the real production image: built pages, API and database together.
 * Point E2E_BASE_URL at a running container (CI starts one; see .github/workflows/ci.yml).
 */
export default defineConfig({
  testDir: "./tests",
  timeout: 60_000,
  fullyParallel: false,
  forbidOnly: Boolean(process.env.CI),
  retries: 0,
  reporter: process.env.CI ? [["list"], ["html", { open: "never" }]] : "list",
  use: {
    baseURL: process.env.E2E_BASE_URL ?? "http://localhost:8090",
    timezoneId: "America/Toronto",
    locale: "en-US",
    trace: "retain-on-failure",
  },
  projects: [
    { name: "desktop", use: { ...devices["Desktop Chrome"] } },
    { name: "phone", use: { ...devices["Pixel 7"] } },
  ],
});
