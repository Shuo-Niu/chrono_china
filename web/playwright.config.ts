import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
  testDir: "./tests/e2e",
  // The old files assert the removed Focus/snapshot product path. They remain
  // archived in-tree, while Phase 1.3.1d is the authoritative browser contract.
  testIgnore: [
    "phase1.spec.ts",
    "phase1_1.spec.ts",
    "phase1_2.spec.ts",
    "phase1_2_2.spec.ts",
    "phase1_2_2_capture.spec.ts",
    "phase1_3.spec.ts",
    "phase1_3_1.spec.ts",
    "phase1_3_1a.spec.ts",
    "phase1_3_1b.spec.ts",
    "phase1_3_1c_track_a.spec.ts",
    "phase1_3_1c_track_b.spec.ts",
    "phase1_3_1d.spec.ts",
  ],
  fullyParallel: false,
  retries: 0,
  reporter: [
    ["list"],
    ["json", { outputFile: "../artifacts/playwright-results.json" }],
  ],
  use: {
    baseURL: "http://127.0.0.1:4173",
    trace: "retain-on-failure",
  },
  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"] },
    },
  ],
  webServer: {
    command: "npm run dev -- --host 127.0.0.1 --port 4173",
    url: "http://127.0.0.1:4173",
    reuseExistingServer: false,
    timeout: 120_000,
  },
});
