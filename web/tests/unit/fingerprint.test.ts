import { describe, expect, it } from "vitest";

import { formatFingerprint } from "../../src/lib/fingerprint";

const HEX = "b171395da10849824071f08074ebc29945c7dd3e3187480647ea0a60cc130833";
const SHOWN =
  "B1:71:39:5D:A1:08:49:82:40:71:F0:80:74:EB:C2:99:45:C7:DD:3E:31:87:48:06:47:EA:0A:60:CC:13:08:33";

describe("formatFingerprint", () => {
  it("shows 64 hex characters as upper-case pairs joined by colons", () => {
    expect(formatFingerprint(HEX)).toBe(SHOWN);
  });

  it("gives the same answer for the form people compare it in", () => {
    expect(formatFingerprint(SHOWN)).toBe(SHOWN);
    expect(formatFingerprint(SHOWN.toLowerCase())).toBe(SHOWN);
    expect(formatFingerprint(HEX.toUpperCase())).toBe(SHOWN);
    expect(formatFingerprint(SHOWN.replaceAll(":", " "))).toBe(SHOWN);
  });

  it("returns anything that is not a SHA-256 unchanged", () => {
    expect(formatFingerprint("")).toBe("");
    expect(formatFingerprint("abc")).toBe("abc");
    expect(formatFingerprint(`${HEX}00`)).toBe(`${HEX}00`);
    expect(formatFingerprint("z".repeat(64))).toBe("z".repeat(64));
  });
});
