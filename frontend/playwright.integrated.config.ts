import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: "./tests/integrated",
  fullyParallel: false,
  workers: 1,
  timeout: 45000,
  expect: { timeout: 8000 },
  retries: 0,
  reporter: [["list"],["html",{outputFolder:"playwright-report-integrated",open:"never"}]],
  outputDir: "test-results-integrated",
  use: {
    baseURL: process.env.SENTAVOS_E2E_WEB ?? "http://127.0.0.1:5182",
    browserName: "chromium",
    channel: "msedge",
    headless: true,
    viewport: {width:400,height:860},
    trace: "retain-on-failure",
  },
});
