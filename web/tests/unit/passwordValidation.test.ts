import { describe, expect, it } from "vitest";

import { validateNewPassword } from "../../src/lib/passwordValidation";

const MIN = 12;

describe("validateNewPassword", () => {
  it("accepts a long enough, repeated, different password", () => {
    expect(
      validateNewPassword(
        "current-secret",
        "a-brand-new-passphrase",
        "a-brand-new-passphrase",
        MIN,
      ),
    ).toBeNull();
  });

  it("asks for the current password", () => {
    expect(
      validateNewPassword("", "a-brand-new-passphrase", "a-brand-new-passphrase", MIN),
    ).toBe("Введите текущий пароль");
  });

  it("rejects a password shorter than the policy minimum", () => {
    expect(validateNewPassword("current-secret", "short", "short", MIN)).toBe(
      "Новый пароль должен быть не короче 12 символов",
    );
  });

  it("accepts exactly the minimum length", () => {
    const twelve = "x".repeat(MIN);

    expect(validateNewPassword("current-secret", twelve, twelve, MIN)).toBeNull();
  });

  it("rejects a repeat that does not match", () => {
    expect(
      validateNewPassword(
        "current-secret",
        "a-brand-new-passphrase",
        "a-brand-new-passphrasE",
        MIN,
      ),
    ).toBe("Пароли не совпадают");
  });

  it("rejects a new password equal to the current one", () => {
    expect(
      validateNewPassword(
        "the-same-passphrase",
        "the-same-passphrase",
        "the-same-passphrase",
        MIN,
      ),
    ).toBe("Новый пароль должен отличаться от текущего");
  });
});
