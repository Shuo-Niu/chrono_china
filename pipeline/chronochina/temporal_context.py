from __future__ import annotations

import html
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from chronochina.config import PROCESSED_DIR, PROJECT_ROOT, QA_DIR
from chronochina.io import read_json, utc_now, write_json


OUTPUT_DIR = PROCESSED_DIR / "temporal_context"
QA_PATH = QA_DIR / "phase1_3_temporal_context_qa.json"
SOURCE_REPORT_PATH = QA_DIR / "phase1_3_temporal_context_sources.md"
TIMELINE_QA_DIR = PROJECT_ROOT / "artifacts" / "phase1_3" / "timeline_qa"
MINIMUM_DISPLAY_GAP = 0.10


SOURCES: dict[str, dict[str, str]] = {
    "met_china_1000_bce_1": {
        "title": "China, 1000 B.C.–1 A.D. — Heilbrunn Timeline of Art History",
        "publisher": "The Metropolitan Museum of Art",
        "url": "https://www.metmuseum.org/toah/ht/04/eac.html",
        "accessed_at": "2026-08-09",
        "supports": "西汉 206 B.C.–9 A.D.，用于公元前 201 年的宽泛时期标签。",
    },
    "met_china_1_500": {
        "title": "China, 1–500 A.D. — Heilbrunn Timeline of Art History",
        "publisher": "The Metropolitan Museum of Art",
        "url": "https://www.metmuseum.org/toah/ht/05/eac.html",
        "accessed_at": "2026-08-09",
        "supports": (
            "王莽时期 9–25、东汉 25–220、三国 220–265；用于 14、23、190、220 年。"
        ),
    },
    "met_china_500_1000": {
        "title": "China, 500–1000 A.D. — Heilbrunn Timeline of Art History",
        "publisher": "The Metropolitan Museum of Art",
        "url": "https://www.metmuseum.org/toah/ht/06/eac.html",
        "accessed_at": "2026-08-09",
        "supports": (
            "南北朝 386–581、隋 581–618、唐 618–907，并说明长安为隋唐都城；"
            "用于 553、556、557、596、627、742 年。"
        ),
    },
    "dpm_ming_qing_lineages": {
        "title": "宫廷世系",
        "publisher": "故宫博物院",
        "url": "https://www.dpm.org.cn/court/lineages.html",
        "accessed_at": "2026-08-09",
        "supports": "明 1368–1644、清 1644–1911；用于 1368 与 1911 年。",
    },
}


@dataclass(frozen=True)
class ReviewedContext:
    broad_era_label: str
    shortcut_label: str
    source_ids: tuple[str, ...]
    context_confidence: str = "high"
    regional_context_label: str | None = None
    notes: str = "宽泛时期仅用于用户理解，不构成该锚点的政权归属断言。"


# Explicit 5-anchor × 4-snapshot editorial review. This is intentionally not a
# year-to-dynasty function and must not be used to infer historical entity links.
REVIEWED_CONTEXTS: dict[tuple[str, int], ReviewedContext] = {
    ("beijing", 14): ReviewedContext(
        "秦汉时期（王莽时期）", "汉", ("met_china_1_500",), "high"
    ),
    ("beijing", 220): ReviewedContext(
        "三国时期", "三国", ("met_china_1_500",)
    ),
    ("beijing", 1368): ReviewedContext(
        "明代", "明", ("dpm_ming_qing_lineages",)
    ),
    ("beijing", 1911): ReviewedContext(
        "清末", "清", ("dpm_ming_qing_lineages",)
    ),
    ("xian", 23): ReviewedContext(
        "秦汉时期（王莽时期末）", "汉", ("met_china_1_500",), "high"
    ),
    ("xian", 557): ReviewedContext(
        "南北朝时期", "南北朝", ("met_china_500_1000",)
    ),
    ("xian", 627): ReviewedContext(
        "唐代",
        "唐",
        ("met_china_500_1000",),
        "high",
        "长安为唐代都城",
        "区域说明只采用来源明确陈述；不从附近点名称或距离推导。",
    ),
    ("xian", 1911): ReviewedContext(
        "清末", "清", ("dpm_ming_qing_lineages",)
    ),
    ("chengdu", 14): ReviewedContext(
        "秦汉时期（王莽时期）", "汉", ("met_china_1_500",), "high"
    ),
    ("chengdu", 553): ReviewedContext(
        "南北朝时期", "南北朝", ("met_china_500_1000",)
    ),
    ("chengdu", 742): ReviewedContext(
        "唐代", "唐", ("met_china_500_1000",)
    ),
    ("chengdu", 1911): ReviewedContext(
        "清末", "清", ("dpm_ming_qing_lineages",)
    ),
    ("qingdao", -201): ReviewedContext(
        "汉代（西汉）", "汉", ("met_china_1000_bce_1",)
    ),
    ("qingdao", 14): ReviewedContext(
        "秦汉时期（王莽时期）", "汉", ("met_china_1_500",), "high"
    ),
    ("qingdao", 190): ReviewedContext(
        "东汉末年", "汉", ("met_china_1_500",)
    ),
    ("qingdao", 1911): ReviewedContext(
        "清末", "清", ("dpm_ming_qing_lineages",)
    ),
    ("qufu", 14): ReviewedContext(
        "秦汉时期（王莽时期）", "汉", ("met_china_1_500",), "high"
    ),
    ("qufu", 556): ReviewedContext(
        "南北朝时期", "南北朝", ("met_china_500_1000",)
    ),
    ("qufu", 596): ReviewedContext(
        "隋代", "隋", ("met_china_500_1000",)
    ),
    ("qufu", 1911): ReviewedContext(
        "清末", "清", ("dpm_ming_qing_lineages",)
    ),
}


def format_year_zh(year: int) -> str:
    if year == 0:
        raise ValueError("historical year zero is invalid; use -1 then 1")
    return f"公元前 {abs(year)} 年" if year < 0 else f"公元 {year} 年"


def timeline_positions(years: list[int]) -> list[dict[str, Any]]:
    if not years or years != sorted(years) or len(set(years)) != len(years):
        raise ValueError("supported snapshot years must be unique and chronological")
    if 0 in years:
        raise ValueError("supported snapshots cannot contain year zero")
    if len(years) == 1:
        return [
            {
                "year": years[0],
                "linear_normalized_position": 0.0,
                "display_normalized_position": 0.0,
                "position_adjusted": False,
            }
        ]

    earliest, latest = years[0], years[-1]
    span = latest - earliest
    linear = [(year - earliest) / span for year in years]
    display = linear.copy()
    for index in range(1, len(display)):
        display[index] = max(display[index], display[index - 1] + MINIMUM_DISPLAY_GAP)
    display[-1] = 1.0
    for index in range(len(display) - 2, -1, -1):
        display[index] = min(display[index], display[index + 1] - MINIMUM_DISPLAY_GAP)
    display[0] = 0.0
    return [
        {
            "year": year,
            "linear_normalized_position": round(linear[index], 6),
            "display_normalized_position": round(display[index], 6),
            "position_adjusted": abs(linear[index] - display[index]) > 0.000001,
        }
        for index, year in enumerate(years)
    ]


def deterministic_shortcut_target(
    snapshots: list[dict[str, Any]], shortcut_label: str, current_year: int
) -> int | None:
    candidates = [
        snapshot["snapshot_year"]
        for snapshot in snapshots
        if snapshot["shortcut_label"] == shortcut_label
    ]
    if not candidates:
        return None
    return min(candidates, key=lambda candidate: (abs(candidate - current_year), candidate))


def _manifest_paths() -> list[Path]:
    return sorted((PROCESSED_DIR / "anchors").glob("*/manifest.json"))


def _source_snapshot_keys() -> dict[str, list[str]]:
    result = {source_id: [] for source_id in SOURCES}
    for (anchor_id, year), context in sorted(REVIEWED_CONTEXTS.items()):
        for source_id in context.source_ids:
            result[source_id].append(f"{anchor_id}:{year}")
    return result


def _write_source_report(source_snapshot_keys: dict[str, list[str]]) -> None:
    lines = [
        "# Phase 1.3 Temporal Context Sources",
        "",
        "Access date: 2026-08-09",
        "",
        "这些来源只支持 broad-era display metadata；除明确列出的长安说明外，不用于推断锚点政权归属、历史实体 identity 或 lineage。",
        "",
    ]
    for source_id, source in SOURCES.items():
        lines.extend(
            [
                f"## {source_id}",
                "",
                f"- Title: {source['title']}",
                f"- Publisher: {source['publisher']}",
                f"- URL: {source['url']}",
                f"- Accessed: {source['accessed_at']}",
                f"- Evidence scope: {source['supports']}",
                f"- Supported snapshots: {', '.join(source_snapshot_keys[source_id])}",
                "",
            ]
        )
    lines.extend(
        [
            "## Regional-context gaps",
            "",
            "19/20 snapshots intentionally omit regional political context because this phase did not obtain sufficiently specific anchor-year evidence. They remain broad-era-only and safe for display; absence is not interpreted as absence of historical change.",
            "",
            "No unresolved source conflict was found for the displayed broad-era labels. Labels around 14/23 explicitly say 王莽时期 rather than silently treating those years as a continuous Han dynasty claim.",
            "",
        ]
    )
    SOURCE_REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")


def _write_timeline_svg(anchor: dict[str, Any]) -> Path:
    width, height = 1000, 250
    left, right = 90, 930
    display_y, linear_y = 90, 190
    snapshots = anchor["snapshots"]
    parts = [
        '<svg xmlns="http://www.w3.org/2000/svg" width="1000" height="250" viewBox="0 0 1000 250" role="img">',
        f"<title>{html.escape(anchor['display_name'])} Temporal Rail QA</title>",
        "<desc>Display rail compared with strict linear year positions. Orange nodes were moved only for minimum visual spacing.</desc>",
        '<rect width="1000" height="250" fill="#f5f1e8"/>',
        f'<text x="36" y="34" font-family="sans-serif" font-size="18" font-weight="700" fill="#18333f">{html.escape(anchor["display_name"])} · Temporal Rail QA</text>',
        '<text x="36" y="60" font-family="sans-serif" font-size="12" fill="#596b70">上：UI display position（最小间距 10%） · 下：严格线性时间参考</text>',
        f'<line x1="{left}" y1="{display_y}" x2="{right}" y2="{display_y}" stroke="#50676e" stroke-width="2"/>',
        f'<line x1="{left}" y1="{linear_y}" x2="{right}" y2="{linear_y}" stroke="#aeb8b7" stroke-width="1"/>',
    ]
    for snapshot in snapshots:
        timeline = snapshot["timeline"]
        display_x = left + (right - left) * timeline["display_normalized_position"]
        linear_x = left + (right - left) * timeline["linear_normalized_position"]
        color = "#a34a2e" if timeline["position_adjusted"] else "#18333f"
        parts.extend(
            [
                f'<line x1="{display_x:.2f}" y1="72" x2="{display_x:.2f}" y2="108" stroke="{color}" stroke-width="1"/>',
                f'<circle cx="{display_x:.2f}" cy="{display_y}" r="6" fill="{color}" stroke="#fff7eb" stroke-width="2"/>',
                f'<text x="{display_x:.2f}" y="70" text-anchor="middle" font-family="sans-serif" font-size="12" font-weight="700" fill="#18333f">{html.escape(snapshot["display_year"])}</text>',
                f'<text x="{display_x:.2f}" y="124" text-anchor="middle" font-family="sans-serif" font-size="11" fill="#53666c">{html.escape(snapshot["broad_era_label"])}</text>',
                f'<text x="{display_x:.2f}" y="140" text-anchor="middle" font-family="monospace" font-size="10" fill="#778488">display {timeline["display_normalized_position"]:.3f}</text>',
                f'<line x1="{linear_x:.2f}" y1="181" x2="{linear_x:.2f}" y2="199" stroke="#6f7e81" stroke-width="1"/>',
                f'<text x="{linear_x:.2f}" y="216" text-anchor="middle" font-family="monospace" font-size="10" fill="#657579">{snapshot["snapshot_year"]} · {timeline["linear_normalized_position"]:.3f}</text>',
            ]
        )
    parts.append("</svg>\n")
    destination = TIMELINE_QA_DIR / f"{anchor['anchor_id']}.svg"
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text("\n".join(parts), encoding="utf-8")
    return destination


def build() -> dict[str, Any]:
    manifests = [read_json(path) for path in _manifest_paths()]
    if len(manifests) != 5:
        raise ValueError(f"expected five anchor manifests, found {len(manifests)}")

    generated_at = utc_now()
    anchor_outputs: list[dict[str, Any]] = []
    all_snapshots: list[dict[str, Any]] = []
    for manifest in manifests:
        years = manifest["available_periods"]
        positions = {item["year"]: item for item in timeline_positions(years)}
        period_by_year = {period["year"]: period for period in manifest["periods"]}
        snapshots: list[dict[str, Any]] = []
        for index, year in enumerate(years):
            key = (manifest["anchor_id"], year)
            if key not in REVIEWED_CONTEXTS:
                raise KeyError(f"missing reviewed temporal context: {key}")
            reviewed = REVIEWED_CONTEXTS[key]
            missing_sources = set(reviewed.source_ids) - SOURCES.keys()
            if missing_sources:
                raise KeyError(f"unknown context sources for {key}: {missing_sources}")
            period = period_by_year[year]
            snapshot = {
                "snapshot_id": f"{manifest['anchor_id']}:{year}",
                "anchor_id": manifest["anchor_id"],
                "snapshot_year": year,
                "display_year": format_year_zh(year),
                "broad_era_label": reviewed.broad_era_label,
                "shortcut_label": reviewed.shortcut_label,
                "regional_context_label": reviewed.regional_context_label,
                "context_confidence": reviewed.context_confidence,
                "source_status": "supported",
                "source_ids": list(reviewed.source_ids),
                "notes": reviewed.notes,
                "whether_context_is_manual_reviewed": True,
                "whether_context_is_safe_for_user_display": True,
                "unresolved_conflicts": [],
                "sequence_index": index,
                "sequence_count": len(years),
                "previous_snapshot_year": years[index - 1] if index > 0 else None,
                "changes_from_previous": {
                    "added_records": period["added_since_previous"],
                    "removed_records": period["removed_since_previous"],
                    "mechanical_only": True,
                },
                "timeline": {
                    **positions[year],
                    "scale_scope": "per_anchor",
                    "display_algorithm": "linear_with_minimum_gap_0_10",
                },
            }
            snapshots.append(snapshot)
            all_snapshots.append(snapshot)

        anchor_output = {
            "schema_version": "1.0",
            "generated_at": generated_at,
            "anchor_id": manifest["anchor_id"],
            "display_name": manifest["display_name"],
            "supported_snapshot_count": len(snapshots),
            "earliest_supported_year": years[0],
            "latest_supported_year": years[-1],
            "timeline_scale_scope": "per_anchor",
            "timeline_display_algorithm": "linear_with_minimum_gap_0_10",
            "semantic_notice": (
                "Temporal context is display metadata only; the map changes only among "
                "the listed supported snapshots and does not interpolate years or infer lineage."
            ),
            "snapshots": snapshots,
        }
        write_json(OUTPUT_DIR / f"{manifest['anchor_id']}.json", anchor_output)
        _write_timeline_svg(anchor_output)
        anchor_outputs.append(anchor_output)

    source_snapshot_keys = _source_snapshot_keys()
    index = {
        "schema_version": "1.0",
        "generated_at": generated_at,
        "snapshot_count": len(all_snapshots),
        "anchor_count": len(anchor_outputs),
        "anchors": [
            {
                "anchor_id": anchor["anchor_id"],
                "display_name": anchor["display_name"],
                "manifest_path": f"temporal_context/{anchor['anchor_id']}.json",
            }
            for anchor in anchor_outputs
        ],
        "sources": [{"source_id": source_id, **source} for source_id, source in SOURCES.items()],
        "semantic_notice": (
            "Broad era is a user-facing chronology aid, not a nationwide political lookup. "
            "Regional context is optional and never changes historical points."
        ),
    }
    write_json(OUTPUT_DIR / "index.json", index)
    _write_source_report(source_snapshot_keys)

    expected_keys = {
        (manifest["anchor_id"], year)
        for manifest in manifests
        for year in manifest["available_periods"]
    }
    actual_keys = {(item["anchor_id"], item["snapshot_year"]) for item in all_snapshots}
    qa = {
        "phase": "1.3",
        "generated_at": generated_at,
        "result": "PASS" if expected_keys == actual_keys else "FAIL",
        "coverage": {
            "expected_snapshots": len(expected_keys),
            "manifest_snapshots": len(actual_keys),
            "exact_year_displayable": sum(bool(item["display_year"]) for item in all_snapshots),
            "broad_era_supported": sum(bool(item["broad_era_label"]) for item in all_snapshots),
            "regional_context_supported": sum(
                bool(item["regional_context_label"]) for item in all_snapshots
            ),
            "safe_for_user_display": sum(
                item["whether_context_is_safe_for_user_display"] for item in all_snapshots
            ),
        },
        "year_zero_count": sum(item["snapshot_year"] == 0 for item in all_snapshots),
        "chronological_order_valid": all(
            [item["snapshot_year"] for item in anchor["snapshots"]]
            == sorted(item["snapshot_year"] for item in anchor["snapshots"])
            for anchor in anchor_outputs
        ),
        "no_fake_snapshots": expected_keys == actual_keys,
        "unresolved_conflict_count": sum(
            bool(item["unresolved_conflicts"]) for item in all_snapshots
        ),
        "source_count": len(SOURCES),
        "source_snapshot_keys": source_snapshot_keys,
        "timeline": {
            "scale_scope": "per_anchor",
            "display_algorithm": "linear_with_minimum_gap_0_10",
            "minimum_display_gap": MINIMUM_DISPLAY_GAP,
            "adjusted_snapshot_count": sum(
                item["timeline"]["position_adjusted"] for item in all_snapshots
            ),
        },
        "records": all_snapshots,
    }
    write_json(QA_PATH, qa)
    return qa


def main() -> None:
    result = build()
    print(result["result"])


if __name__ == "__main__":
    main()
