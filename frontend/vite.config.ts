import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// https://vite.dev/config/
export default defineConfig(({ mode }) => ({
  plugins: [react()],
  server: {
    port: 5173,
    watch: {
      ignored: [
        "**/dist-essencial/**",
        "**/test-results-essencial/**",
        "**/playwright-report-essencial/**",
      ],
    },
  },
  // A demonstração só entra no artefato específico de revisão.
  // O build normal continua publicando exclusivamente a aplicação atual.
  ...(mode === "essencial"
    ? { build: { rollupOptions: { input: "essencial.html" } } }
    : {}),
}));
