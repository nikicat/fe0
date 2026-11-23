// The page's browser tests (playground/README.md, "Tests").
import { defineConfig } from "@playwright/test";
import { FORK, FORK_COMMAND } from "./e2e/fork";

const PREVIEW = new URL("http://127.0.0.1:4173/");

export default defineConfig({
  testDir: "e2e",
  // One fork serves every test, and a deploy changes its state, so the tests run one at a time.
  workers: 1,
  forbidOnly: !!process.env.CI,
  timeout: 120_000,
  expect: { timeout: 60_000 },
  use: {
    baseURL: PREVIEW.href,
    // The dev container's Chromium is Debian's (.devcontainer/Containerfile).
    launchOptions: { executablePath: process.env.CHROMIUM ?? "/usr/bin/chromium" },
  },
  webServer: [
    {
      command: "npm run preview --"
        + ` --host ${PREVIEW.hostname} --port ${PREVIEW.port} --strictPort`,
      url: PREVIEW.href,
      reuseExistingServer: !process.env.CI,
    },
    // A fork that is already running would carry another run's state, so a taken port fails.
    { command: FORK_COMMAND, port: Number(FORK.port), reuseExistingServer: false,
      timeout: 60_000 },
  ],
});
