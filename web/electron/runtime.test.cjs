const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");

const {
  resolvePackagedAsset,
  contentTypeFor,
  isAllowedNavigation,
  parseSingleByteRange,
  sanitizeLogMessage,
} = require("./runtime.cjs");

const root = path.resolve("C:/ChronoChina/resources/app/dist");

test("packaged asset resolver stays inside the exact dist root", () => {
  assert.equal(
    resolvePackagedAsset(root, "chronochina://app/explore/tgaz_compact.json"),
    path.join(root, "explore", "tgaz_compact.json"),
  );
  assert.equal(resolvePackagedAsset(root, "chronochina://app/"), path.join(root, "index.html"));
  assert.throws(
    () => resolvePackagedAsset(root, "chronochina://app/%2e%2e/package.json"),
    /outside packaged root/,
  );
  assert.throws(
    () => resolvePackagedAsset(root, "https://example.com/index.html"),
    /unsupported packaged URL/,
  );
});

test("runtime MIME and navigation policies are explicit", () => {
  assert.equal(contentTypeFor("index.html"), "text/html; charset=utf-8");
  assert.equal(contentTypeFor("assets/app.js"), "text/javascript; charset=utf-8");
  assert.equal(contentTypeFor("assets/maplibre-gl-worker.mjs"), "text/javascript; charset=utf-8");
  assert.equal(contentTypeFor("explore/data.json"), "application/json; charset=utf-8");
  assert.equal(contentTypeFor("reference/china_z9.pmtiles"), "application/octet-stream");
  assert.equal(contentTypeFor("unknown.bin"), "application/octet-stream");
  assert.equal(isAllowedNavigation("chronochina://app/index.html"), true);
  assert.equal(isAllowedNavigation("https://tiles.openfreemap.org/planet"), false);
});


test("single byte ranges are bounded and reject malformed requests", () => {
  assert.deepEqual(parseSingleByteRange("bytes=0-16383", 20_000), { start: 0, end: 16_383 });
  assert.deepEqual(parseSingleByteRange("bytes=19000-", 20_000), { start: 19_000, end: 19_999 });
  assert.deepEqual(parseSingleByteRange("bytes=19000-25000", 20_000), { start: 19_000, end: 19_999 });
  assert.equal(parseSingleByteRange("bytes=20000-", 20_000), null);
  assert.equal(parseSingleByteRange("bytes=5-4", 20_000), null);
  assert.equal(parseSingleByteRange("bytes=0-1,4-5", 20_000), null);
});
test("support logs redact local user paths", () => {
  assert.doesNotMatch(
    sanitizeLogMessage("failed at C:\\Users\\example\\ChronoChina\\data.json"),
    /C:\\Users\\example/,
  );
});

test("Windows candidate is portable-only and opens a visible map window", () => {
  const packageJson = JSON.parse(fs.readFileSync(path.resolve(__dirname, "../package.json"), "utf8"));
  assert.deepEqual(packageJson.build.win.target, [{ target: "portable", arch: ["x64"] }]);
  assert.equal(packageJson.build.nsis, undefined);
  const main = fs.readFileSync(path.resolve(__dirname, "main.cjs"), "utf8");
  assert.match(main, /show:\s*true/);
  assert.doesNotMatch(main, /ready-to-show/);
});
