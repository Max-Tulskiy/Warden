export type RangePreset = "hour" | "day" | "week";

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
