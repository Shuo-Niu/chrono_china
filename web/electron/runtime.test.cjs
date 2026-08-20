const test = require("node:test");
const assert = require("node:assert/strict");
const path = require("node:path");

const {
  resolvePackagedAsset,
  contentTypeFor,
  isAllowedNavigation,
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
  assert.equal(contentTypeFor("explore/data.json"), "application/json; charset=utf-8");
  assert.equal(contentTypeFor("unknown.bin"), "application/octet-stream");
  assert.equal(isAllowedNavigation("chronochina://app/index.html"), true);
  assert.equal(isAllowedNavigation("https://tiles.openfreemap.org/planet"), false);
});

test("support logs redact local user paths", () => {
  assert.doesNotMatch(
    sanitizeLogMessage("failed at C:\\Users\\example\\ChronoChina\\data.json"),
    /C:\\Users\\example/,
  );
});
