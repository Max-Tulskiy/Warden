/**
 * A SHA-256 fingerprint the way people compare it: upper case, in pairs joined
 * by colons, like the agent's window shows it. Case, colons and spaces in the
 * input do not matter; anything that is not exactly 64 hex characters is
 * returned as it came.
 */
export function formatFingerprint(value: string): string {
  const hex = value.replace(/[\s:]/g, "");
  if (!/^[0-9a-fA-F]{64}$/.test(hex)) {
    return value;
  }
  return hex.toUpperCase().match(/.{2}/g)!.join(":");
}
