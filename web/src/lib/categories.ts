import type { EventRecord } from "../api/types";

export type EventCategory = EventRecord["category"];

export const CATEGORY_LABELS: Record<EventCategory, string> = {
  removable_media: "Носители",
  printing: "Печать",
  processes: "Процессы",
  web: "Сайты",
};

export const CATEGORIES = Object.keys(CATEGORY_LABELS) as EventCategory[];
