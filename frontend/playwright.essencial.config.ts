import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: "./tests/essencial",
  fullyParallel: false,
  timeout: 30000,
  expect: { timeout: 5000 },
  retries: 0,
  workers: 1,
  reporter: [
    ["list"],
    ["html", { outputFolder: "playwright-report-essencial", open: "never" }],
  ],
  outputDir: "test-results-essencial",
  use: {
    baseURL: "http://127.0.0.1:5178",
    browserName: "chromium",
    channel: "msedge",
    headless: true,
    viewport: { width: 400, height: 860 },
    trace: "retain-on-failure",
  },
  webServer: {
    command:
      "node node_modules/vite/bin/vite.js --host 127.0.0.1 --port 5178 --strictPort",
    url: "http://127.0.0.1:5178/essencial.html",
    reuseExistingServer: !process.env.CI,
    timeout: 30000,
  },
});
