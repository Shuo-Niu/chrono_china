import { useMemo, type CSSProperties } from "react";
import { formatHistoricalYear } from "./temporal";
import {
  ordinalToYear,
  timelinePosition,
  timelineTicks,
  yearToOrdinal,
  type TimelineRange,
} from "./timelineScale";

interface ContinuousTimelineProps extends TimelineRange {
  year: number;
  onChange: (year: number) => void;
}

export function ContinuousTimeline({ minYear, maxYear, year, onChange }: ContinuousTimelineProps) {
  const range = useMemo(() => ({ minYear, maxYear }), [maxYear, minYear]);
  const ticks = useMemo(() => timelineTicks(range), [range]);
  const position = timelinePosition(year, range);
  const currentEdge = position <= 0.08 ? "left" : position >= 0.92 ? "right" : "middle";
  return (
    <section
      className="continuous-timeline"
      aria-label="连续历史时间轴"
      data-progress-fill="none"
      data-testid="continuous-timeline"
    >
      <div className="continuous-timeline__rail">
        <output
          className="continuous-timeline__current"
          data-edge={currentEdge}
          data-testid="timeline-current-year"
          style={{ "--timeline-position": `${position * 100}%` } as CSSProperties}
        >
          {formatHistoricalYear(year)}
        </output>
        <input
          aria-label="历史年份"
          aria-valuetext={formatHistoricalYear(year)}
          data-testid="timeline-range"
          type="range"
          min={yearToOrdinal(minYear)}
          max={yearToOrdinal(maxYear)}
          step="1"
          value={yearToOrdinal(year)}
          onChange={(event) => onChange(ordinalToYear(Number(event.target.value)))}
        />
        <div className="continuous-timeline__ticks" aria-hidden="true">
          {ticks.map((tick, index) => (
            <span
              key={tick}
              data-edge={index === 0 ? "left" : index === ticks.length - 1 ? "right" : "middle"}
              style={{ left: `${timelinePosition(tick, range) * 100}%` }}
            >
              <i />
              <b>{formatHistoricalYear(tick).replace(" 年", "")}</b>
            </span>
          ))}
        </div>
      </div>
    </section>
  );
}
