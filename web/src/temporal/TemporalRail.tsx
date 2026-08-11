import type { CSSProperties } from "react";

import type { TemporalSnapshot } from "../types";
import {
  ERA_SHORTCUTS,
  shortcutTargetYear,
  snapDisplayPositionToSupportedYear,
} from "./temporal";


interface TemporalRailProps {
  snapshots: TemporalSnapshot[];
  currentYear: number;
  developerMode: boolean;
  onSelectYear: (year: number) => void;
}

export function TemporalRail({
  snapshots,
  currentYear,
  developerMode,
  onSelectYear,
}: TemporalRailProps) {
  const activeSnapshot = snapshots.find((snapshot) => snapshot.snapshot_year === currentYear);
  if (!activeSnapshot) return null;
  const rangeValue = Math.round(activeSnapshot.timeline.display_normalized_position * 1000);

  return (
    <section className="temporal-navigation" aria-label="时间导航">
      <div className="temporal-rail" data-testid="temporal-rail">
        <div className="temporal-rail__track">
          <input
            type="range"
            min="0"
            max="1000"
            step="1"
            value={rangeValue}
            aria-label="时间轨道"
            aria-valuetext={activeSnapshot.display_year}
            onChange={(event) => {
              const displayPosition = Number(event.target.value) / 1000;
              onSelectYear(snapDisplayPositionToSupportedYear(snapshots, displayPosition));
            }}
          />
          <div className="temporal-rail__line" aria-hidden="true" />
          {snapshots.map((snapshot, index) => (
            <button
              key={snapshot.snapshot_id}
              type="button"
              className={`temporal-node temporal-node--lane-${index % 2}`}
              style={
                {
                  "--timeline-position":
                    `${snapshot.timeline.display_normalized_position * 100}%`,
                } as CSSProperties
              }
              aria-label={snapshot.display_year}
              aria-current={snapshot.snapshot_year === currentYear ? "date" : undefined}
              data-snapshot-id={snapshot.snapshot_id}
              data-snapshot-year={snapshot.snapshot_year}
              data-linear-position={snapshot.timeline.linear_normalized_position}
              data-display-position={snapshot.timeline.display_normalized_position}
              onClick={() => onSelectYear(snapshot.snapshot_year)}
            >
              <span className="temporal-node__dot" aria-hidden="true" />
              <span className="temporal-node__label" aria-hidden="true">
                {snapshot.display_year}
              </span>
            </button>
          ))}
        </div>
      </div>
      <p className="temporal-rail__notice">
        {developerMode
          ? "节点大体按年代距离排列，过近节点留出最小可读间距；拖动会吸附，不生成逐年地图。"
          : "地图仅显示已收录的代表时期，拖动时间轴会自动定位到最近时期；不提供任意年份的逐年地图。"}
      </p>
      {developerMode && (
        <div className="era-shortcuts" role="group" aria-label="时期捷径">
          {ERA_SHORTCUTS.map((shortcut) => {
            const target = shortcutTargetYear(snapshots, shortcut, currentYear);
            return (
              <button
                key={shortcut}
                type="button"
                disabled={target === null}
                aria-label={target === null ? `${shortcut}：暂无代表状态` : `${shortcut}：跳到代表状态`}
                onClick={() => target !== null && onSelectYear(target)}
              >
                {shortcut}
              </button>
            );
          })}
        </div>
      )}
    </section>
  );
}
