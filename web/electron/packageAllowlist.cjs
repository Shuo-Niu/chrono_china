const REQUIRED = new Set([
  "/package.json",
  "/electron/main.cjs",
  "/electron/runtime.cjs",
  "/dist/index.html",
  "/dist/explore/tgaz_compact.json",
  "/dist/coverage/historical_layer_coverage.json",
  "/dist/reference/china_z9.pmtiles",
  "/dist/knowledge/qing_late_institution_notes_v0.1.json",
  "/dist/reference/assets/fonts/OFL.txt",
]);

const COMPILED_ASSET = /^\/dist\/assets\/[A-Za-z0-9_-]+\.(?:css|js|mjs)$/;
const REFERENCE_ASSET = new RegExp(
  "^/dist/reference/assets/(?:" +
    "fonts/(?:Noto Sans Regular|Noto Sans Medium)/[0-9]+-[0-9]+\\.pbf|" +
    "sprites/v4/light(?:@2x)?\\.(?:json|png)" +
  ")$",
);
const DIRECTORIES = new Set([
  "/dist",
  "/dist/assets",
  "/dist/coverage",
  "/dist/explore",
  "/electron",
  "/dist/knowledge",
]);
const REFERENCE_DIRECTORY = /^\/dist\/reference(?:\/assets(?:\/fonts(?:\/(?:Noto Sans Regular|Noto Sans Medium))?|\/sprites(?:\/v4)?)?)?$/;

function validateAsarEntries(entries) {
  const normalized = entries.map((entry) => entry.replaceAll("\\", "/"));
  const files = normalized.filter((entry) =>
    !DIRECTORIES.has(entry) && !REFERENCE_DIRECTORY.test(entry),
  );
  for (const entry of files) {
    if (!REQUIRED.has(entry) && !COMPILED_ASSET.test(entry) && !REFERENCE_ASSET.test(entry)) {
      throw new Error(`asar file is not allowlisted: ${entry}`);
    }
  }
  for (const required of REQUIRED) {
    if (!files.includes(required)) throw new Error(`required asar file is missing: ${required}`);
  }
  if (!files.some((entry) => entry.endsWith(".js")) || !files.some((entry) => entry.endsWith(".css"))) {
    throw new Error("compiled JavaScript and CSS assets are required");
  }
  if (!files.some((entry) => REFERENCE_ASSET.test(entry) && entry.endsWith(".pbf"))) {
    throw new Error("offline reference glyph assets are required");
  }
  return { status: "PASS", fileCount: files.length };
}

module.exports = { validateAsarEntries };
