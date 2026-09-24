export type RangePreset = "hour" | "day" | "week";

/** What the range control offers: a rolling preset, or a range typed by hand. */
export type Preset = RangePreset | "custom";

const PRESET_MILLISECONDS: Record<RangePreset, number> = {
  hour: 60 * 60 * 1000,
  day: 24 * 60 * 60 * 1000,
  week: 7 * 24 * 60 * 60 * 1000,
};

/** A rolling range ending at `now`, so no calendar-day or timezone choice is involved. */
export function presetRange(
  preset: RangePreset,
  now: Date,
): { start: string; end: string } {
  return {
    start: new Date(now.getTime() - PRESET_MILLISECONDS[preset]).toISOString(),
    end: now.toISOString(),
  };
}

/**
 * Mirrors, but does not replace, the server's own check. Unlike an agent
 * request window there is no length cap: a report only reads stored events.
 */
export function validateReportRange(start: string, end: string): string | null {
  if (!start || !end) {
    return "Укажите начало и конец периода";
  }
  if (new Date(end) <= new Date(start)) {
    return "Конец периода должен быть позже начала";
  }
  return null;
}

/**
 * The range a screen should query for the current form state: a preset is
 * computed from `now`, a custom range is validated and converted to ISO
 * instants. Returns the validation message instead when the custom range is
 * unusable, so the caller has one branch to handle.
 */
export function resolveRange(
  preset: Preset,
  customStart: string,
  customEnd: string,
  now: Date,
): { range: { start: string; end: string } } | { error: string } {
  if (preset !== "custom") {
    return { range: presetRange(preset, now) };
  }
  const problem = validateReportRange(customStart, customEnd);
  if (problem) {
    return { error: problem };
  }
  return {
    range: {
      start: new Date(customStart).toISOString(),
      end: new Date(customEnd).toISOString(),
    },
  };
}
