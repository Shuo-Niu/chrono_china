/// <reference types="vitest/config" />

import { createReadStream, mkdirSync, copyFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

const __dirname = dirname(fileURLToPath(import.meta.url));

export default defineConfig({
  plugins: [
    react(),
    {
      name: "chronochina-runtime-data-allowlist",
      configureServer(server) {
        const routes = new Map([
          ["/explore/tgaz_compact.json", resolve(__dirname, "../data/processed/explore/tgaz_compact.json")],
          ["/coverage/historical_layer_coverage.json", resolve(__dirname, "../data/processed/coverage/historical_layer_coverage.json")],
        ]);
        server.middlewares.use((request, response, next) => {
          const source = routes.get(request.url ?? "");
          if (!source) return next();
          response.setHeader("Content-Type", "application/json; charset=utf-8");
          createReadStream(source).on("error", next).pipe(response);
        });
      },
      closeBundle() {
        const files = [
          ["../data/processed/explore/tgaz_compact.json", "dist/explore/tgaz_compact.json"],
          ["../data/processed/coverage/historical_layer_coverage.json", "dist/coverage/historical_layer_coverage.json"],
        ];
        for (const [source, destination] of files) {
          const output = resolve(__dirname, destination);
          mkdirSync(dirname(output), { recursive: true });
          copyFileSync(resolve(__dirname, source), output);
        }
      },
    },
  ],
  optimizeDeps: { exclude: ["maplibre-gl"] },
  publicDir: false,
  test: {
    environment: "jsdom",
    setupFiles: "./tests/setup.ts",
    include: ["src/**/*.test.{ts,tsx}"],
  },
});
