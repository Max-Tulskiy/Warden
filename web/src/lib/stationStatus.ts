import type { Agent } from "../api/types";

export type StationStatus = "online" | "offline" | "disabled";

const ONLINE_THRESHOLD_MINUTES = 5;

function isOnline(lastSeenAt: string | null): boolean {
  if (!lastSeenAt) return false;
  const elapsedMinutes = (Date.now() - new Date(lastSeenAt).getTime()) / 60_000;
  return elapsedMinutes < ONLINE_THRESHOLD_MINUTES;
}

/** A disabled station is shown as disabled however recently it was last seen. */
export function stationStatus(agent: Agent): StationStatus {
  if (agent.status === "disabled") return "disabled";
  return isOnline(agent.last_seen_at) ? "online" : "offline";
}
