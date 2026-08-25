const fs = require("node:fs");
const path = require("node:path");
const {
  app,
  BrowserWindow,
  dialog,
  protocol,
  session,
} = require("electron");

const {
  contentTypeFor,
  isAllowedNavigation,
  parseSingleByteRange,
  resolvePackagedAsset,
  sanitizeLogMessage,
} = require("./runtime.cjs");

const APP_ORIGIN = "chronochina://app";
const CSP = [
  "default-src 'self'",
  "script-src 'self'",
  "style-src 'self' 'unsafe-inline'",
  "img-src 'self' data: blob:",
  "font-src 'self' data:",
  "connect-src 'self'",
  "worker-src 'self' blob:",
  "object-src 'none'",
  "base-uri 'none'",
  "frame-ancestors 'none'",
].join("; ");

protocol.registerSchemesAsPrivileged([
  {
    scheme: "chronochina",
    privileges: {
      standard: true,
      secure: true,
      supportFetchAPI: true,
      corsEnabled: true,
      codeCache: true,
    },
  },
]);

let logFile = null;

function writeLog(event, detail = "") {
  try {
    if (!logFile) return;
    const line = `${new Date().toISOString()} ${event} ${sanitizeLogMessage(detail)}\n`;
    fs.appendFileSync(logFile, line, { encoding: "utf8" });
  } catch {
    // Logging must never become another startup failure.
  }
}

function assetRoot() {
  return path.join(app.getAppPath(), "dist");
}

async function rangedAssetResponse(filePath, request) {
  const size = (await fs.promises.stat(filePath)).size;
  const rangeHeader = request.headers.get("range");
  const headers = {
    "Accept-Ranges": "bytes",
    "Content-Type": contentTypeFor(filePath),
  };
  if (!rangeHeader) {
    return new Response(await fs.promises.readFile(filePath), {
      status: 200,
      headers: { ...headers, "Content-Length": String(size) },
    });
  }
  const range = parseSingleByteRange(rangeHeader, size);
  if (!range) {
    return new Response(null, {
      status: 416,
      headers: { ...headers, "Content-Range": `bytes */${size}` },
    });
  }
  const length = range.end - range.start + 1;
  const body = Buffer.allocUnsafe(length);
  const handle = await fs.promises.open(filePath, "r");
  try {
    await handle.read(body, 0, length, range.start);
  } finally {
    await handle.close();
  }
  return new Response(body, {
    status: 206,
    headers: {
      ...headers,
      "Content-Length": String(length),
      "Content-Range": `bytes ${range.start}-${range.end}/${size}`,
    },
  });
}

async function createWindow() {
  const window = new BrowserWindow({
    width: 1440,
    height: 900,
    minWidth: 900,
    minHeight: 700,
    show: true,
    backgroundColor: "#eee9df",
    autoHideMenuBar: true,
    webPreferences: {
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
      webSecurity: true,
    },
  });
  window.webContents.setWindowOpenHandler(() => ({ action: "deny" }));
  window.webContents.on("will-navigate", (event, url) => {
    if (!isAllowedNavigation(url)) event.preventDefault();
  });
  window.webContents.on("render-process-gone", (_event, details) => {
    writeLog("renderer_process_gone", details.reason);
  });
  const parameters = new URLSearchParams();
  if (process.env.CHRONOCHINA_PACKAGED_SMOKE === "1") parameters.set("qa", "1");
  const query = parameters.size > 0 ? `?${parameters}` : "";
  void window.loadURL(`${APP_ORIGIN}/index.html${query}`).catch((error) => {
    writeLog("window_load_failed", error);
    dialog.showErrorBox(
      "ChronoChina 启动失败",
      "应用资源无法加载。请关闭应用并将日志文件发送给测试组织者。",
    );
    app.exit(1);
  });
  return window;
}

app.whenReady().then(async () => {
  app.setAppLogsPath();
  logFile = path.join(app.getPath("logs"), "main.log");
  writeLog("application_start", app.getVersion());

  protocol.handle("chronochina", async (request) => {
    try {
      const filePath = resolvePackagedAsset(assetRoot(), request.url);
      const response = await rangedAssetResponse(filePath, request);
      if (path.extname(filePath).toLowerCase() === ".html") {
        const headers = new Headers(response.headers);
        headers.set("Content-Security-Policy", CSP);
        return new Response(response.body, { status: response.status, headers });
      }
      return response;
    } catch (error) {
      writeLog("asset_request_failed", error);
      return new Response("Not found", { status: 404 });
    }
  });

  session.defaultSession.setPermissionRequestHandler((_webContents, _permission, callback) => {
    callback(false);
  });
  session.defaultSession.setPermissionCheckHandler(() => false);

  await createWindow();
  app.on("activate", () => {
    if (BrowserWindow.getAllWindows().length === 0) void createWindow();
  });
}).catch((error) => {
  writeLog("application_ready_failed", error);
  dialog.showErrorBox(
    "ChronoChina 启动失败",
    "应用初始化失败。请将日志文件发送给测试组织者。",
  );
  app.exit(1);
});

process.on("uncaughtException", (error) => {
  writeLog("uncaught_exception", error);
});
process.on("unhandledRejection", (error) => {
  writeLog("unhandled_rejection", error);
});

app.on("window-all-closed", () => {
  if (process.platform !== "darwin") app.quit();
});
