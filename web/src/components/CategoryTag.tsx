import type { EventRecord } from "../api/types";
import { CATEGORY_LABELS } from "../lib/categories";
import { MediaIcon, PrintIcon, ProcessIcon, WebIcon } from "./icons";

const COLOR_VARS: Record<EventRecord["category"], { color: string; bg: string }> = {
  removable_media: { color: "var(--cat-media)", bg: "var(--cat-media-bg)" },
  printing: { color: "var(--cat-print)", bg: "var(--cat-print-bg)" },
  processes: { color: "var(--cat-proc)", bg: "var(--cat-proc-bg)" },
  web: { color: "var(--cat-web)", bg: "var(--cat-web-bg)" },
};

const ICONS: Record<EventRecord["category"], typeof MediaIcon> = {
  removable_media: MediaIcon,
  printing: PrintIcon,
  processes: ProcessIcon,
  web: WebIcon,
};

export function CategoryTag({ category }: { category: EventRecord["category"] }) {
  const { color, bg } = COLOR_VARS[category];
  const Icon = ICONS[category];
  return (
    <span className="cat-tag" style={{ background: bg, color }}>
      <Icon />
      {CATEGORY_LABELS[category]}
    </span>
  );
}
