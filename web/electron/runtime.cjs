const path = require("node:path");

const MIME_TYPES = new Map([
  [".css", "text/css; charset=utf-8"],
  [".html", "text/html; charset=utf-8"],
  [".js", "text/javascript; charset=utf-8"],
  [".mjs", "text/javascript; charset=utf-8"],
  [".json", "application/json; charset=utf-8"],
  [".map", "application/json; charset=utf-8"],
  [".pbf", "application/x-protobuf"],
  [".pmtiles", "application/octet-stream"],
  [".svg", "image/svg+xml"],
  [".woff", "font/woff"],
  [".woff2", "font/woff2"],
]);

function resolvePackagedAsset(root, requestUrl) {
  const parsed = new URL(requestUrl);
  if (parsed.protocol !== "chronochina:" || parsed.host !== "app") {
    throw new Error("unsupported packaged URL");
  }
  if (/%2e/i.test(requestUrl)) throw new Error("asset path is outside packaged root");
  const relative = decodeURIComponent(parsed.pathname).replace(/^\/+/, "") || "index.html";
  const resolvedRoot = path.resolve(root);
  const resolved = path.resolve(resolvedRoot, relative);
  if (resolved !== resolvedRoot && !resolved.startsWith(`${resolvedRoot}${path.sep}`)) {
    throw new Error("asset path is outside packaged root");
  }
  return resolved;
}

function contentTypeFor(filePath) {
  return MIME_TYPES.get(path.extname(filePath).toLowerCase()) ?? "application/octet-stream";
}

function parseSingleByteRange(value, size) {
  if (!Number.isSafeInteger(size) || size < 0 || typeof value !== "string") return null;
  const match = /^bytes=(\d+)-(\d*)$/.exec(value.trim());
  if (!match) return null;
  const start = Number(match[1]);
  const requestedEnd = match[2] ? Number(match[2]) : size - 1;
  if (!Number.isSafeInteger(start) || !Number.isSafeInteger(requestedEnd)) return null;
  if (start < 0 || start >= size || requestedEnd < start) return null;
  return { start, end: Math.min(requestedEnd, size - 1) };
}
function isAllowedNavigation(url) {
  try {
    const parsed = new URL(url);
    return parsed.protocol === "chronochina:" && parsed.host === "app";
  } catch {
    return false;
  }
}

function sanitizeLogMessage(value) {
  let message = String(value ?? "unknown error");
  for (const candidate of [process.env.USERPROFILE, process.env.HOME]) {
    if (candidate) message = message.split(candidate).join("<user-directory>");
  }
  return message.replace(/[A-Za-z]:\\(?:[^\s:"<>|?*]+\\)*[^\s:"<>|?*]*/g, "<local-path>");
}

module.exports = {
  contentTypeFor,
  isAllowedNavigation,
  parseSingleByteRange,
  resolvePackagedAsset,
  sanitizeLogMessage,
};
