/// <reference types="vitest/config" />

import {
  copyFileSync,
  cpSync,
  createReadStream,
  existsSync,
  mkdirSync,
  statSync,
} from "node:fs";
import { dirname, extname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

const __dirname = dirname(fileURLToPath(import.meta.url));
const publicBuild = process.env.CHRONOCHINA_PUBLIC_BUILD === "1";
const referenceArchive = resolve(__dirname, "../data/processed/reference/china_z9.pmtiles");
const referenceAssets = resolve(__dirname, "../data/processed/reference/assets");
const mapLibreRuntimeAssets = new Map([
  ["/assets/maplibre-gl-worker.mjs", resolve(__dirname, "node_modules/maplibre-gl/dist/maplibre-gl-worker.mjs")],
  ["/assets/maplibre-gl-shared.mjs", resolve(__dirname, "node_modules/maplibre-gl/dist/maplibre-gl-shared.mjs")],
]);

function serveRangeFile(
  request: { headers: Record<string, string | string[] | undefined> },
  response: {
    statusCode: number;
    setHeader(name: string, value: string | number): void;
    end(value?: string): void;
  },
  source: string,
  contentType: string,
): void {
  if (!existsSync(source)) {
    response.statusCode = 404;
    response.end("Not found");
    return;
  }
  const size = statSync(source).size;
  const range = Array.isArray(request.headers.range)
    ? request.headers.range[0]
    : request.headers.range;
  response.setHeader("Accept-Ranges", "bytes");
  response.setHeader("Content-Type", contentType);
  if (range) {
    const match = /^bytes=(\d+)-(\d*)$/.exec(range);
    if (!match) {
      response.statusCode = 416;
      response.setHeader("Content-Range", `bytes */${size}`);
      response.end();
      return;
    }
    const start = Number(match[1]);
    const end = match[2] ? Math.min(Number(match[2]), size - 1) : size - 1;
    if (start >= size || end < start) {
      response.statusCode = 416;
      response.setHeader("Content-Range", `bytes */${size}`);
      response.end();
      return;
    }
    response.statusCode = 206;
    response.setHeader("Content-Range", `bytes ${start}-${end}/${size}`);
    response.setHeader("Content-Length", end - start + 1);
    createReadStream(source, { start, end }).pipe(response as never);
    return;
  }
  response.statusCode = 200;
  response.setHeader("Content-Length", size);
  createReadStream(source).pipe(response as never);
}

function referenceContentType(path: string): string {
  const extension = extname(path).toLowerCase();
  if (extension === ".pbf" || extension === ".pmtiles") return "application/octet-stream";
  if (extension === ".png") return "image/png";
  if (extension === ".json") return "application/json; charset=utf-8";
  return "application/octet-stream";
}

export default defineConfig({
  plugins: [
    react(),
    {
      name: "chronochina-runtime-data-allowlist",
      configureServer(server) {
        const routes = new Map([
          ["/explore/tgaz_compact.json", resolve(__dirname, "../data/processed/explore/tgaz_compact.json")],
          ["/coverage/historical_layer_coverage.json", resolve(__dirname, "../data/processed/coverage/historical_layer_coverage.json")],
          ["/knowledge/qing_late_institution_notes_v0.1.json", resolve(__dirname, "../data/processed/knowledge/qing_late_institution_notes_v0.1.json")],
        ]);
        server.middlewares.use((request, response, next) => {
          const pathname = request.url?.split("?", 1)[0] ?? "";
          if (pathname === "/reference/china_z9.pmtiles") {
            serveRangeFile(request, response, referenceArchive, "application/octet-stream");
            return;
          }
          if (pathname.startsWith("/reference/assets/")) {
            const relative = decodeURIComponent(pathname.slice("/reference/assets/".length));
            const source = resolve(referenceAssets, relative);
            if (source !== referenceAssets && source.startsWith(`${referenceAssets}\\`)) {
              serveRangeFile(request, response, source, referenceContentType(source));
              return;
            }
          }
          const mapLibreAsset = mapLibreRuntimeAssets.get(pathname);
          if (mapLibreAsset) {
            response.setHeader("Content-Type", "text/javascript; charset=utf-8");
            createReadStream(mapLibreAsset).on("error", next).pipe(response);
            return;
          }
          const source = routes.get(pathname);
          if (!source) return next();
          response.setHeader("Content-Type", "application/json; charset=utf-8");
          createReadStream(source).on("error", next).pipe(response);
        });
      },
      closeBundle() {
        const files = [
          ["../data/processed/explore/tgaz_compact.json", "dist/explore/tgaz_compact.json"],
          ["../data/processed/coverage/historical_layer_coverage.json", "dist/coverage/historical_layer_coverage.json"],
          ["../data/processed/knowledge/qing_late_institution_notes_v0.1.json", "dist/knowledge/qing_late_institution_notes_v0.1.json"],
        ];
        if (!publicBuild) {
          for (const [source, destination] of files) {
            const output = resolve(__dirname, destination);
            mkdirSync(dirname(output), { recursive: true });
            copyFileSync(resolve(__dirname, source), output);
          }
        }
        for (const [requestPath, source] of mapLibreRuntimeAssets) {
          const output = resolve(__dirname, "dist/" + requestPath.replace(/^\/+/, ""));
          mkdirSync(dirname(output), { recursive: true });
          copyFileSync(source, output);
        }
        if (!publicBuild && existsSync(referenceArchive) && existsSync(referenceAssets)) {
          const archiveOutput = resolve(__dirname, "dist/reference/china_z9.pmtiles");
          mkdirSync(dirname(archiveOutput), { recursive: true });
          copyFileSync(referenceArchive, archiveOutput);
          cpSync(referenceAssets, resolve(__dirname, "dist/reference/assets"), { recursive: true });
        } else if (!publicBuild) {
          console.warn("Offline reference assets are absent; run scripts/download_offline_basemap.ps1 before packaging.");
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
