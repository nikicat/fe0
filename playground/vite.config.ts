import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

// GitHub Pages serves the page under the repository's path, so every URL is relative.
export default defineConfig({
  base: "./",
  // The page is one chunk of about 1 MB: React, wagmi with viem, and CodeMirror.
  build: { chunkSizeWarningLimit: 1200 },
  plugins: [react()],
  test: { include: ["src/**/*.test.ts"] },
});
