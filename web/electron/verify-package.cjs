const path = require("node:path");
const { listPackage } = require("@electron/asar");
const { validateAsarEntries } = require("./packageAllowlist.cjs");

const asarPath = process.argv[2];
if (!asarPath) throw new Error("usage: node verify-package.cjs <app.asar>");
const result = validateAsarEntries(listPackage(path.resolve(asarPath)));
process.stdout.write(`validated app.asar allowlist (${result.fileCount} files)\n`);
