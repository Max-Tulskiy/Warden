/**
 * Mirrors, but does not replace, the server's own password checks. The
 * minimum length comes from the server's policy, not a constant here.
 */
export function validateNewPassword(
  current: string,
  next: string,
  repeat: string,
  minLength: number,
): string | null {
  if (!current) {
    return "Введите текущий пароль";
  }
  if (next.length < minLength) {
    return `Новый пароль должен быть не короче ${minLength} символов`;
  }
  if (next !== repeat) {
    return "Пароли не совпадают";
  }
  if (next === current) {
    return "Новый пароль должен отличаться от текущего";
  }
  return null;
}
