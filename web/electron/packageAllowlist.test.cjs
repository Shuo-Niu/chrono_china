const test = require("node:test");
const assert = require("node:assert/strict");
const { validateAsarEntries } = require("./packageAllowlist.cjs");

const minimal = [
  "/package.json",
  "/electron/main.cjs",
  "/electron/runtime.cjs",
  "/dist/index.html",
  "/dist/assets/app.js",
  "/dist/assets/app.css",
  "/dist/explore/tgaz_compact.json",
  "/dist/coverage/historical_layer_coverage.json",
];

test("asar allowlist accepts only the minimum desktop runtime", () => {
  assert.deepEqual(validateAsarEntries(minimal), { status: "PASS", fileCount: 8 });
});

test("asar allowlist rejects dependencies, docs, fixtures, and extra data", () => {
  for (const forbidden of [
    "/node_modules/react/index.js",
    "/docs/design.md",
    "/dist/anchors/index.json",
    "/electron/runtime.test.cjs",
    "/data/raw/chgis.csv",
  ]) {
    assert.throws(() => validateAsarEntries([...minimal, forbidden]), /not allowlisted/);
  }
});
