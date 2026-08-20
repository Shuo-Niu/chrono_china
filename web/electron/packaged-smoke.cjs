const assert = require("node:assert/strict");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const { _electron: electron } = require("playwright");

const projectRoot = path.resolve(__dirname, "..", "..");
const sourceApp = path.join(projectRoot, "artifacts", "phase1_5", "windows", "win-unpacked");
const smokeRoot = path.join(os.tmpdir(), "ChronoChina User Smoke Test");
const copiedApp = path.join(smokeRoot, "Application Files");
const workingDirectory = path.join(smokeRoot, "Working Directory With Spaces");
const executable = path.join(copiedApp, "ChronoChina.exe");

function yearToOrdinal(year) {
  if (year === 0) throw new Error("year zero is unsupported");
  return year < 0 ? year : year - 1;
}

async function setYear(page, year) {
  await page.getByTestId("timeline-range").evaluate((element, ordinal) => {
    const input = element;
    Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value").set.call(
      input,
      String(ordinal),
    );
    input.dispatchEvent(new Event("input", { bubbles: true }));
  }, yearToOrdinal(year));
  await page.getByTestId("map").waitFor({ state: "visible" });
  await page.waitForFunction(
    (value) => document.querySelector('[data-testid="map"]')?.getAttribute("data-query-result-year") === value,
    String(year),
  );
}

async function launchAndVerify(reopen = false) {
  const application = await electron.launch({
    executablePath: executable,
    cwd: workingDirectory,
    env: { ...process.env, CHRONOCHINA_PACKAGED_SMOKE: "1" },
    timeout: 60_000,
  });
  try {
    const page = await application.firstWindow({ timeout: 60_000 });
    const requests = [];
    page.on("request", (request) => requests.push(request.url()));
    const errors = [];
    page.on("pageerror", (error) => errors.push(String(error)));

    await page.getByTestId("map").waitFor({ state: "visible", timeout: 60_000 });
    await page.waitForFunction(() => {
      const map = document.querySelector('[data-testid="map"]');
      return map?.getAttribute("data-explore-index-status") === "ready" &&
        map?.getAttribute("data-coverage-metadata-status") === "ready" &&
        Number(map?.getAttribute("data-historical-point-count")) > 0;
    }, null, { timeout: 60_000 });

    assert.equal(new URL(page.url()).protocol, "chronochina:");
    assert.equal(
      requests.some((url) => /^https?:\/\/(localhost|127\.0\.0\.1)(:|\/)/.test(url)),
      false,
      "packaged application must not request a development server",
    );

    if (!reopen) {
      await setYear(page, 1911);
      const highDensity = Number(await page.getByTestId("map").getAttribute("data-explore-active-record-count"));
      assert.ok(highDensity > 0, "1911 viewport must contain real historical records");

      await setYear(page, 1820);
      await page.getByTestId("coverage-settlement").waitFor({ state: "visible" });
      assert.match(await page.getByTestId("coverage-settlement").innerText(), /1820 村镇快照/);
      await setYear(page, 1819);
      assert.match(await page.getByTestId("coverage-settlement").innerText(), /来源无资料/);

      const county = page.locator('[data-legend-family="county"]');
      await county.click();
      assert.equal(await county.getAttribute("aria-pressed"), "false");
      await county.click();
      assert.equal(await county.getAttribute("aria-pressed"), "true");

      await page.getByRole("button", { name: "仅点" }).click();
      assert.equal(await page.getByTestId("map").getAttribute("data-historical-display-mode"), "point_only");
      await page.getByRole("button", { name: "点 + 标签" }).click();
      assert.equal(await page.getByTestId("map").getAttribute("data-historical-display-mode"), "point_label");

      const pointsBeforeBasemapFailure = Number(
        await page.getByTestId("map").getAttribute("data-historical-point-count"),
      );
      await page.route("https://tiles.openfreemap.org/**", (route) => route.abort("internetdisconnected"));
      await page.getByRole("button", { name: "彩色地理" }).click();
      await page.waitForFunction(() =>
        /r4_color_geography|r2_minimal_modern/.test(
          document.querySelector('[data-testid="map"]')?.getAttribute("data-reference-effective-mode") ?? "",
        ), null, { timeout: 30_000 });
      assert.ok(
        Number(await page.getByTestId("map").getAttribute("data-historical-point-count")) > 0 &&
          pointsBeforeBasemapFailure > 0,
        "remote basemap failure must not remove historical points",
      );

      const marker = page.locator(".history-marker").first();
      await marker.click();
      await page.locator(".detail-card,.colocated-card").waitFor({ state: "visible" });
      assert.deepEqual(errors, []);
    }

    return await application.evaluate(({ app }) => app.getPath("logs"));
  } finally {
    await application.close();
  }
}

async function main() {
  const sourceExecutable = path.join(sourceApp, "ChronoChina.exe");
  if (!fs.existsSync(sourceExecutable)) {
    throw new Error(`missing packaged executable: ${sourceExecutable}`);
  }
  fs.rmSync(smokeRoot, { recursive: true, force: true });
  fs.mkdirSync(workingDirectory, { recursive: true });
  fs.cpSync(sourceApp, copiedApp, { recursive: true });

  const logDirectory = await launchAndVerify(false);
  await launchAndVerify(true);
  const logFile = path.join(logDirectory, "main.log");
  assert.equal(fs.existsSync(logFile), true, "packaged application must create a support log");
  const log = fs.readFileSync(logFile, "utf8");
  assert.match(log, /application_start/);
  assert.doesNotMatch(log, /D:\\VibeCoding|C:\\Users\\shuon/i);

  process.stdout.write(`${JSON.stringify({
    status: "PASS",
    executable,
    copied_path: copiedApp,
    working_directory: workingDirectory,
    close_reopen: "PASS",
    dev_server_dependency: false,
    remote_basemap_failure_keeps_history: true,
    log_file_created: true,
  }, null, 2)}\n`);
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
