/**
 * The constitution's four-hour ceiling (principle 3). It is only the fallback:
 * the limit in force comes from the server and may be lower, and the server
 * enforces the real one whatever the panel checks.
 */
export const MAX_WINDOW_HOURS = 4;

/** «1 часа», «2 часов»: the number is in the genitive after «превышать». */
export function hoursLimitLabel(hours: number): string {
  return hours === 1 ? "1 часа" : `${hours} часов`;
}

/** Mirrors, but does not replace, the server's own check (plan.md §6). */
export function validateWindow(
  start: string,
  end: string,
  maxHours: number = MAX_WINDOW_HOURS,
): string | null {
  if (!start || !end) {
    return "Укажите начало и конец промежутка";
  }
  const startDate = new Date(start);
  const endDate = new Date(end);
  if (endDate <= startDate) {
    return "Конец промежутка должен быть позже начала";
  }
  const hours = (endDate.getTime() - startDate.getTime()) / (1000 * 60 * 60);
  if (hours > maxHours) {
    return `Промежуток не должен превышать ${hoursLimitLabel(maxHours)}`;
  }
  return null;
}
