import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: "./tests/saldos",
  workers: 1,
  fullyParallel: false,
  timeout: 45000,
  expect: {timeout: 10000},
  reporter: "list",
  outputDir: "../.local/e2e-saldos-results",
  use: {
    baseURL: "http://127.0.0.1:5184",
    browserName: "chromium",
    channel: "msedge",
    headless: true,
    viewport: {width:400,height:860},
    trace: "retain-on-failure",
  },
});
