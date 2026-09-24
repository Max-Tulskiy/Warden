import { describe, expect, it } from "vitest";

import { presetRange, resolveRange, validateReportRange } from "../../src/lib/reportRange";

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

describe("resolveRange", () => {
  it("resolves a preset from the given instant and ignores the custom fields", () => {
    expect(resolveRange("hour", "", "", NOW)).toEqual({
      range: { start: "2026-09-01T11:00:00.000Z", end: "2026-09-01T12:00:00.000Z" },
    });
  });

  it("converts a valid custom range to ISO instants", () => {
    const result = resolveRange("custom", "2026-09-01T12:00", "2026-09-01T13:00", NOW);

    expect(result).toEqual({
      range: {
        start: new Date("2026-09-01T12:00").toISOString(),
        end: new Date("2026-09-01T13:00").toISOString(),
      },
    });
  });

  it("returns the validation message instead of a range for a bad custom range", () => {
    expect(resolveRange("custom", "2026-09-01T13:00", "2026-09-01T12:00", NOW)).toEqual({
      error: "Конец периода должен быть позже начала",
    });
    expect(resolveRange("custom", "", "", NOW)).toEqual({
      error: "Укажите начало и конец периода",
    });
  });
});
