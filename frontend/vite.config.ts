import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    watch: {
      ignored: [
        "**/dist-essencial/**",
        "**/test-results-essencial/**",
        "**/playwright-report-essencial/**",
        "**/test-results-integrated/**",
        "**/playwright-report-integrated/**",
      ],
    },
  },
});
