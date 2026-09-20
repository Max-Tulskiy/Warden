import type { StationStatus } from "../lib/stationStatus";

const LABELS: Record<StationStatus, string> = {
  online: "в сети",
  offline: "не в сети",
  disabled: "отключена",
};

const COLOR_VARS: Record<StationStatus, { color: string; bg: string }> = {
  online: { color: "var(--success)", bg: "var(--success-bg)" },
  offline: { color: "var(--neutral)", bg: "var(--neutral-bg)" },
  disabled: { color: "var(--warning)", bg: "var(--warning-bg)" },
};

export function StatusPill({ status }: { status: StationStatus }) {
  const { color, bg } = COLOR_VARS[status];
  return (
    <span className="pill" style={{ background: bg, color }}>
      <span className="pill-dot" style={{ background: color }} />
      {LABELS[status]}
    </span>
  );
}
