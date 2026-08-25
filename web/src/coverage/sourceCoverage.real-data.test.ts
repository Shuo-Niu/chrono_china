import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { expect, test } from "vitest";

import { parseCoverageMetadata } from "./sourceCoverage";


const INDEX_SHA = "7c9ccaedfd58445595e5ab68fd1fb9e106e33c37b8bb98002a7e8e6bad5b5baf";

test("parses the committed metadata against the real compact index", () => {
  const compact = JSON.parse(
    readFileSync(resolve("../data/processed/explore/tgaz_compact.json"), "utf8"),
  );
  const coverage = JSON.parse(
    readFileSync(resolve("../data/metadata/historical_layer_coverage.json"), "utf8"),
  );
  expect(parseCoverageMetadata(coverage, compact, INDEX_SHA).canonicalIndex).toMatchObject({
    recordCount: 71_393,
    observedEnvelope: { minYear: -763, maxYear: 1912 },
  });
});
