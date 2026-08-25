import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, test } from "vitest";

import type { CompactHistoricalIndex } from "../explore/viewportQuery";
import {
  buildSourceHierarchyIndex,
  hierarchyBreadcrumb,
} from "./sourceHierarchy";

describe("source-relative historical hierarchy", () => {
  test("uses the frozen explicit parent chain for Hui Zhou and Weihui Lu", () => {
    const index = JSON.parse(
      readFileSync(resolve(__dirname, "../../../data/processed/explore/tgaz_compact.json"), "utf8"),
    ) as CompactHistoricalIndex;
    const hierarchy = buildSourceHierarchyIndex(index);

    expect(hierarchy.classifications.get("hvd_82279")).toMatchObject({
      tier: "local_governance",
      method: "explicit_polity_chain",
      parentChainIds: ["hvd_84023", "hvd_112022", "hvd_113643"],
    });
    expect(hierarchy.classifications.get("hvd_84023")).toMatchObject({
      tier: "regional_governance",
      method: "explicit_polity_chain",
      parentChainIds: ["hvd_112022", "hvd_113643"],
    });
    expect(hierarchyBreadcrumb(hierarchy, "hvd_82279", 1276)).toEqual([
      expect.objectContaining({ name: "卫辉路", activeAtSelectedYear: false }),
      expect.objectContaining({ name: "河南江北行省", activeAtSelectedYear: false }),
      expect.objectContaining({ name: "元", activeAtSelectedYear: true }),
    ]);
  });
});
