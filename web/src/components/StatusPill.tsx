export type StationStatus = "online" | "offline";

const LABELS: Record<StationStatus, string> = {
  online: "в сети",
  offline: "не в сети",
};

const COLOR_VARS: Record<StationStatus, { color: string; bg: string }> = {
  online: { color: "var(--success)", bg: "var(--success-bg)" },
  offline: { color: "var(--neutral)", bg: "var(--neutral-bg)" },
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
