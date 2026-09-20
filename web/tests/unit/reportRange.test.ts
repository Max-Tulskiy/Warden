import { describe, expect, it } from "vitest";

import { presetRange, validateReportRange } from "../../src/lib/reportRange";

const NOW = new Date("2026-09-01T12:00:00.000Z");

describe("presetRange", () => {
  it("covers the last hour up to now", () => {
    expect(presetRange("hour", NOW)).toEqual({
      start: "2026-09-01T11:00:00.000Z",
      end: "2026-09-01T12:00:00.000Z",
    });
  });

  it("covers the last 24 hours up to now", () => {
    expect(presetRange("day", NOW)).toEqual({
      start: "2026-08-31T12:00:00.000Z",
      end: "2026-09-01T12:00:00.000Z",
    });
  });

  it("covers the last 7 days up to now", () => {
    expect(presetRange("week", NOW)).toEqual({
      start: "2026-08-25T12:00:00.000Z",
      end: "2026-09-01T12:00:00.000Z",
    });
  });
});

describe("validateReportRange", () => {
  it("asks for both ends when either is missing", () => {
    expect(validateReportRange("", "2026-09-01T13:00")).toBe(
      "Укажите начало и конец периода",
    );
    expect(validateReportRange("2026-09-01T12:00", "")).toBe(
      "Укажите начало и конец периода",
    );
  });

  it("rejects an end that is not after the start", () => {
    const message = "Конец периода должен быть позже начала";

    expect(validateReportRange("2026-09-01T12:00", "2026-09-01T12:00")).toBe(message);
    expect(validateReportRange("2026-09-01T12:00", "2026-09-01T11:00")).toBe(message);
  });

  it("accepts a range longer than four hours", () => {
    expect(validateReportRange("2026-09-01T12:00", "2026-09-08T12:00")).toBeNull();
  });
});
