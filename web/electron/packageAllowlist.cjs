const REQUIRED = new Set([
  "/package.json",
  "/electron/main.cjs",
  "/electron/runtime.cjs",
  "/dist/index.html",
  "/dist/explore/tgaz_compact.json",
  "/dist/coverage/historical_layer_coverage.json",
]);

const COMPILED_ASSET = /^\/dist\/assets\/[A-Za-z0-9_-]+\.(?:css|js)$/;
const DIRECTORIES = new Set([
  "/dist",
  "/dist/assets",
  "/dist/coverage",
  "/dist/explore",
  "/electron",
]);

function validateAsarEntries(entries) {
  const normalized = entries.map((entry) => entry.replaceAll("\\", "/"));
  const files = normalized.filter((entry) => !DIRECTORIES.has(entry));
  for (const entry of files) {
    if (!REQUIRED.has(entry) && !COMPILED_ASSET.test(entry)) {
      throw new Error(`asar file is not allowlisted: ${entry}`);
    }
  }
  for (const required of REQUIRED) {
    if (!files.includes(required)) throw new Error(`required asar file is missing: ${required}`);
  }
  if (!files.some((entry) => entry.endsWith(".js")) || !files.some((entry) => entry.endsWith(".css"))) {
    throw new Error("compiled JavaScript and CSS assets are required");
  }
  return { status: "PASS", fileCount: files.length };
}

module.exports = { validateAsarEntries };
