import { defineConfig } from "@playwright/test";
export default defineConfig({
  testDir:"./tests/reset", workers:1, fullyParallel:false, timeout:45000,
  reporter:[["list"]], outputDir:"../.local/reset-total-browser-results",
  use:{baseURL:"http://127.0.0.1:5189",browserName:"chromium",channel:"msedge",headless:true,
       viewport:{width:400,height:860},trace:"retain-on-failure"},
});
