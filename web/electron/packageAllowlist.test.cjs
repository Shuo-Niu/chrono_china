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
  "/dist/knowledge/qing_late_institution_notes_v0.1.json",
  "/dist/assets/maplibre-gl-worker.mjs",
  "/dist/explore/tgaz_compact.json",
  "/dist/coverage/historical_layer_coverage.json",
  "/dist/reference/china_z9.pmtiles",
  "/dist/reference/assets/fonts/OFL.txt",
  "/dist/reference/assets/fonts/Noto Sans Regular/0-255.pbf",
  "/dist/reference/assets/fonts/Noto Sans Italic/0-255.pbf",
  "/dist/reference/assets/fonts/Noto Sans Devanagari Regular v1/63488-63743.pbf",
  "/dist/reference/assets/sprites/v4/light.png",
];

test("asar allowlist accepts only the minimum desktop runtime", () => {
  assert.deepEqual(validateAsarEntries(minimal), { status: "PASS", fileCount: 16 });
});

test("asar allowlist rejects packages missing the previously absent glyphs", () => {
  for (const font of ["Noto Sans Italic", "Noto Sans Devanagari Regular v1"]) {
    assert.throws(
      () => validateAsarEntries(minimal.filter((entry) => !entry.includes(font))),
      /required asar file is missing/,
    );
  }
});

test("asar allowlist rejects dependencies, docs, fixtures, and extra data", () => {
  for (const forbidden of [
    "/node_modules/react/index.js",
    "/docs/design.md",
    "/dist/anchors/index.json",
    "/electron/runtime.test.cjs",
    "/data/raw/chgis.csv",
    "/dist/reference/assets/secret.exe",
  ]) {
    assert.throws(() => validateAsarEntries([...minimal, forbidden]), /not allowlisted/);
  }
});
