import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir:"./tests/refino", fullyParallel:false, workers:1, timeout:45000,
  expect:{timeout:8000}, reporter:[["list"]], outputDir:"test-results-refino",
  use:{baseURL:"http://127.0.0.1:5184",browserName:"chromium",channel:"msedge",headless:true,
    viewport:{width:400,height:860},trace:"retain-on-failure"},
});
