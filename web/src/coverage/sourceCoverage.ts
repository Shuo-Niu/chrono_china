import type { HistoricalFeature } from "../types";
import {
  displayFamilyFromRawType,
  type DisplayFamily,
} from "../display/hierarchy";
import type { CompactHistoricalIndex } from "../explore/viewportQuery";

export type TemporalModel = "TIME_SERIES" | "TIME_SLICE";
export type SourceSupport = "SUPPORTED" | "UNSUPPORTED" | "LIMITED" | "UNKNOWN";
export type ViewportResult = "HAS_RECORDS" | "NO_RECORDS";

export interface SourceCoverageComponent {
  id: string;
  rawTypes: readonly string[];
  temporalModel: TemporalModel;
  support: SourceSupport;
  snapshotYears: readonly number[];
  supportedPeriods: readonly (readonly [number, number])[];
  observedPeriods: readonly (readonly [number, number])[];
}

interface SourceCoverageFamily {
  defaultSupport: SourceSupport;
  components: readonly SourceCoverageComponent[];
  userModeCopy: Readonly<Record<string, string>>;
}

export interface CoverageMetadata {
  schemaVersion: "1.0";
  canonicalIndex: {
    path: string;
    bytes: number;
    recordCount: number;
    sha256: string;
    observedEnvelope: { minYear: number; maxYear: number };
  };
  families: Readonly<Record<DisplayFamily, SourceCoverageFamily>>;
}

export interface SourceCoverageAssessment {
  family: DisplayFamily;
  year: number;
  support: SourceSupport;
  temporalModels: readonly TemporalModel[];
  activeComponents: readonly SourceCoverageComponent[];
  userModeCopy: Readonly<Record<string, string>>;
  diagnostic: string | null;
}

export interface CoverageMessage {
  kind: "snapshot" | "unsupported" | "limited" | "unknown" | "viewport_empty";
  text: string;
  explanation: string;
}

const FAMILIES: readonly DisplayFamily[] = [
  "high_admin", "regional_admin", "county", "settlement", "other", "polity",
];
const TEMPORAL_MODELS: readonly TemporalModel[] = ["TIME_SERIES", "TIME_SLICE"];
const SUPPORT_VALUES: readonly SourceSupport[] = [
  "SUPPORTED", "UNSUPPORTED", "LIMITED", "UNKNOWN",
];

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function asInteger(value: unknown, field: string): number {
  if (!Number.isInteger(value)) throw new Error(`invalid coverage metadata schema: ${field}`);
  return value as number;
}

function asString(value: unknown, field: string): string {
  if (typeof value !== "string") throw new Error(`invalid coverage metadata schema: ${field}`);
  return value;
}

function asSupport(value: unknown, field: string): SourceSupport {
  if (!SUPPORT_VALUES.includes(value as SourceSupport)) {
    throw new Error(`invalid coverage metadata schema: ${field}`);
  }
  return value as SourceSupport;
}

function asPeriods(value: unknown, field: string): readonly (readonly [number, number])[] {
  if (value === undefined) return [];
  if (!Array.isArray(value)) throw new Error(`invalid coverage metadata schema: ${field}`);
  return value.map((period, index) => {
    if (!Array.isArray(period) || period.length !== 2) {
      throw new Error(`invalid coverage metadata schema: ${field}[${index}]`);
    }
    return [
      asInteger(period[0], `${field}[${index}][0]`),
      asInteger(period[1], `${field}[${index}][1]`),
    ] as const;
  });
}

function parseComponent(value: unknown, field: string): SourceCoverageComponent {
  if (!isRecord(value) || !Array.isArray(value.raw_types)) {
    throw new Error(`invalid coverage metadata schema: ${field}`);
  }
  const temporalModel = value.temporal_model;
  if (!TEMPORAL_MODELS.includes(temporalModel as TemporalModel)) {
    throw new Error(`invalid coverage metadata schema: ${field}.temporal_model`);
  }
  if (value.snapshot_years !== undefined && !Array.isArray(value.snapshot_years)) {
    throw new Error(`invalid coverage metadata schema: ${field}.snapshot_years`);
  }
  const snapshotYears = value.snapshot_years === undefined
    ? []
    : value.snapshot_years.map((year, index) =>
      asInteger(year, `${field}.snapshot_years[${index}]`));
  return {
    id: asString(value.id, `${field}.id`),
    rawTypes: value.raw_types.map((rawType, index) =>
      asString(rawType, `${field}.raw_types[${index}]`)),
    temporalModel: temporalModel as TemporalModel,
    support: asSupport(value.support, `${field}.support`),
    snapshotYears,
    supportedPeriods: asPeriods(value.supported_periods, `${field}.supported_periods`),
    observedPeriods: asPeriods(value.observed_periods, `${field}.observed_periods`),
  };
}

function compactEnvelope(index: CompactHistoricalIndex): { minYear: number; maxYear: number } {
  if (index.records.length === 0) {
    throw new Error("coverage metadata identity cannot be checked against an empty index");
  }
  return index.records.reduce(
    (range, record) => ({
      minYear: Math.min(range.minYear, record[3]),
      maxYear: Math.max(range.maxYear, record[4]),
    }),
    { minYear: Infinity, maxYear: -Infinity },
  );
}

export function parseCoverageMetadata(
  value: unknown,
  index: CompactHistoricalIndex,
): CoverageMetadata {
  if (!isRecord(value) || value.schema_version !== "1.0" ||
      !isRecord(value.canonical_index) || !isRecord(value.families)) {
    throw new Error("invalid coverage metadata schema");
  }
  const canonical = value.canonical_index;
  if (!isRecord(canonical.observed_envelope)) {
    throw new Error("invalid coverage metadata schema: canonical_index.observed_envelope");
  }
  const observedEnvelope = {
    minYear: asInteger(canonical.observed_envelope.min_year, "canonical_index.min_year"),
    maxYear: asInteger(canonical.observed_envelope.max_year, "canonical_index.max_year"),
  };
  const actualEnvelope = compactEnvelope(index);
  const recordCount = asInteger(canonical.record_count, "canonical_index.record_count");
  const sha256 = asString(canonical.sha256, "canonical_index.sha256");
  const compactSha = index.source.compact_sha256;
  if (
    recordCount !== index.records.length ||
    observedEnvelope.minYear !== actualEnvelope.minYear ||
    observedEnvelope.maxYear !== actualEnvelope.maxYear ||
    !/^[0-9a-f]{64}$/i.test(sha256) ||
    (compactSha !== undefined && compactSha !== sha256)
  ) {
    throw new Error("coverage metadata identity does not match compact index");
  }

  const families = {} as Record<DisplayFamily, SourceCoverageFamily>;
  for (const family of FAMILIES) {
    const rawFamily = value.families[family];
    if (!isRecord(rawFamily) || !Array.isArray(rawFamily.components) ||
        (family !== "polity" && !isRecord(rawFamily.user_mode_copy))) {
      throw new Error(`invalid coverage metadata schema: families.${family}`);
    }
    const userModeCopy: Record<string, string> = {};
    for (const [key, copy] of Object.entries(rawFamily.user_mode_copy ?? {})) {
      userModeCopy[key] = asString(copy, `families.${family}.user_mode_copy.${key}`);
    }
    families[family] = {
      defaultSupport: asSupport(rawFamily.default_support, `families.${family}.default_support`),
      components: rawFamily.components.map((component, index) =>
        parseComponent(component, `families.${family}.components[${index}]`)),
      userModeCopy,
    };
  }

  return {
    schemaVersion: "1.0",
    canonicalIndex: {
      path: asString(canonical.path, "canonical_index.path"),
      bytes: asInteger(canonical.bytes, "canonical_index.bytes"),
      recordCount,
      sha256,
      observedEnvelope,
    },
    families,
  };
}

function includesYear(periods: readonly (readonly [number, number])[], year: number): boolean {
  return periods.some(([start, end]) => start <= year && year <= end);
}

function componentActive(component: SourceCoverageComponent, year: number): boolean {
  if (component.temporalModel === "TIME_SLICE") {
    return component.snapshotYears.includes(year);
  }
  const periods = component.supportedPeriods.length > 0
    ? component.supportedPeriods
    : component.observedPeriods;
  return includesYear(periods, year);
}

export function assessSourceCoverage(
  metadata: CoverageMetadata | null,
  family: DisplayFamily,
  year: number,
): SourceCoverageAssessment {
  if (metadata === null) {
    return {
      family,
      year,
      support: "UNKNOWN",
      temporalModels: [],
      activeComponents: [],
      userModeCopy: {},
      diagnostic: "coverage metadata unavailable or invalid",
    };
  }
  const sourceFamily = metadata.families[family];
  const activeComponents = sourceFamily.components.filter((component) =>
    componentActive(component, year));
  const temporalModels = TEMPORAL_MODELS.filter((model) =>
    activeComponents.some((component) => component.temporalModel === model));
  let support = sourceFamily.defaultSupport;
  if (support !== "LIMITED" && activeComponents.length > 0) {
    support = activeComponents.some((component) => component.support === "LIMITED")
      ? "LIMITED"
      : activeComponents.some((component) => component.support === "UNKNOWN")
        ? "UNKNOWN"
        : "SUPPORTED";
  }
  return {
    family,
    year,
    support,
    temporalModels,
    activeComponents,
    userModeCopy: sourceFamily.userModeCopy,
    diagnostic: null,
  };
}

export function resolveViewportResult(
  features: readonly HistoricalFeature[],
  family: DisplayFamily,
): ViewportResult {
  return features.some((feature) =>
    displayFamilyFromRawType(feature.properties.feature_type) === family)
    ? "HAS_RECORDS"
    : "NO_RECORDS";
}

function message(
  kind: CoverageMessage["kind"],
  text: string | undefined,
): CoverageMessage | null {
  return text ? {
    kind,
    text,
    explanation: `${text}；此状态描述当前来源或视口结果，不代表历史上不存在该类地点。`,
  } : null;
}

export function userCoverageMessages(
  assessment: SourceCoverageAssessment,
  viewport: ViewportResult,
  enabled: boolean,
): readonly CoverageMessage[] {
  if (!enabled || assessment.family === "polity" || assessment.diagnostic !== null) return [];
  const messages: CoverageMessage[] = [];
  const snapshot = assessment.activeComponents.find((component) =>
    component.temporalModel === "TIME_SLICE");
  if (snapshot) {
    const copy = assessment.userModeCopy.snapshot_template?.replace("{year}", String(assessment.year));
    const item = message("snapshot", copy);
    if (item) messages.push(item);
  } else {
    const key = assessment.support === "UNSUPPORTED"
      ? "unsupported"
      : assessment.support === "LIMITED"
        ? "limited"
        : assessment.support === "UNKNOWN"
          ? "unknown"
          : null;
    const item = key === null ? null : message(key, assessment.userModeCopy[key]);
    if (item) messages.push(item);
  }
  if (
    viewport === "NO_RECORDS" &&
    assessment.support !== "UNSUPPORTED" &&
    (assessment.activeComponents.length > 0 ||
      assessment.support === "SUPPORTED" || assessment.support === "LIMITED")
  ) {
    messages.push({
      kind: "viewport_empty",
      text: "当前范围无记录",
      explanation: "当前来源状态与所选年份允许查询，但当前视口没有符合条件的记录；这不代表历史上不存在。",
    });
  }
  return messages;
}
