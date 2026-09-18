export const MAX_WINDOW_HOURS = 4;

/** Mirrors, but does not replace, the server's own ≤4h check (plan.md §6). */
export function validateWindow(start: string, end: string): string | null {
  if (!start || !end) {
    return "Укажите начало и конец промежутка";
  }
  const startDate = new Date(start);
  const endDate = new Date(end);
  if (endDate <= startDate) {
    return "Конец промежутка должен быть позже начала";
  }
  const hours = (endDate.getTime() - startDate.getTime()) / (1000 * 60 * 60);
  if (hours > MAX_WINDOW_HOURS) {
    return `Промежуток не должен превышать ${MAX_WINDOW_HOURS} часов`;
  }
  return null;
}
