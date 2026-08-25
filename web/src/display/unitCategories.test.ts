import { describe, expect, test } from "vitest";

import {
  HISTORICAL_UNIT_CATEGORY_REGISTRY,
  historicalUnitCategoryFromRawType,
  unitCategoryConfig,
} from "./unitCategories";

describe("historical unit categories", () => {
  test("maps only audited raw types and never infers a category from the name", () => {
    expect(historicalUnitCategoryFromRawType("省")).toBe("province");
    expect(historicalUnitCategoryFromRawType("路")).toBe("dao_lu");
    expect(historicalUnitCategoryFromRawType("府")).toBe("prefecture");
    expect(historicalUnitCategoryFromRawType("郡")).toBe("commandery");
    expect(historicalUnitCategoryFromRawType("侨县")).toBe("county");
    expect(historicalUnitCategoryFromRawType("军镇")).toBe("military_special");
    expect(historicalUnitCategoryFromRawType("村镇")).toBe("unclassified");
    expect(historicalUnitCategoryFromRawType("亭")).toBe("unclassified");
    expect(historicalUnitCategoryFromRawType("建陵侨县")).toBe("unclassified");
  });

  test("uses the shared dark outline and light halo for clipped marker shapes", () => {
    for (const category of ["commandery", "military_special"] as const) {
      const config = unitCategoryConfig(category);
      expect(config.stroke).toBe("#18333f");
      expect(config.halo).toBe("#fffaf0");
    }
  });

  test("publishes the six approved User Mode categories with complete raw type labels", () => {
    const visible = HISTORICAL_UNIT_CATEGORY_REGISTRY.filter((item) => item.userVisible);
    expect(visible.map((item) => item.labelZh)).toEqual([
      "省与行省", "道与路", "府州厅", "郡与侯国", "县", "军政特殊",
    ]);
    expect(visible.map((item) => item.descriptionZh)).toEqual([
      "省、行省、省级、王畿",
      "道、路",
      "府、州、直隶州、厅",
      "郡、侨郡、侯国",
      "县、侨县",
      "军、监、军镇、防镇",
    ]);
  });
});
