import type { Preset } from "../lib/reportRange";

const PRESETS: { value: Preset; label: string }[] = [
  { value: "hour", label: "Последний час" },
  { value: "day", label: "Последние 24 часа" },
  { value: "week", label: "Последние 7 дней" },
  { value: "custom", label: "Свой период" },
];

interface RangeFilterProps {
  preset: Preset;
  customStart: string;
  customEnd: string;
  onPresetChange: (preset: Preset) => void;
  onCustomStartChange: (value: string) => void;
  onCustomEndChange: (value: string) => void;
}

/** The period control shared by the report and audit screens. */
export function RangeFilter({
  preset,
  customStart,
  customEnd,
  onPresetChange,
  onCustomStartChange,
  onCustomEndChange,
}: RangeFilterProps) {
  return (
    <>
      <div className="segmented" role="group" aria-label="Период">
        {PRESETS.map((item) => (
          <button
            key={item.value}
            type="button"
            className={preset === item.value ? "segmented-item active" : "segmented-item"}
            aria-pressed={preset === item.value}
            onClick={() => onPresetChange(item.value)}
          >
            {item.label}
          </button>
        ))}
      </div>

      {preset === "custom" && (
        <div className="filter-row">
          <label style={{ flex: 1 }}>
            Начало
            <input
              type="datetime-local"
              value={customStart}
              onChange={(e) => onCustomStartChange(e.target.value)}
            />
          </label>
          <label style={{ flex: 1 }}>
            Конец
            <input
              type="datetime-local"
              value={customEnd}
              onChange={(e) => onCustomEndChange(e.target.value)}
            />
          </label>
        </div>
      )}
    </>
  );
}
