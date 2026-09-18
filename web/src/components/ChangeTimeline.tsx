import { useState } from "react";

import type { InventoryChange } from "../api/types";
import { ChevronRightIcon } from "./icons";

type DiffSection = { hardware: Record<string, unknown>; software: Record<string, unknown> };

function countEntries(section: DiffSection): number {
  return Object.keys(section.hardware).length + Object.keys(section.software).length;
}

function summaryParts(change: InventoryChange): { label: string; color: string }[] {
  const parts: { label: string; color: string }[] = [];
  const added = countEntries(change.added);
  const modified = countEntries(change.modified);
  const removed = countEntries(change.removed);
  if (added > 0) parts.push({ label: `+${added} добавлено`, color: "var(--success)" });
  if (modified > 0) parts.push({ label: `~${modified} изменено`, color: "var(--warning)" });
  if (removed > 0) parts.push({ label: `−${removed} удалено`, color: "var(--danger)" });
  return parts;
}

function diffLines(
  section: Record<string, unknown>,
  namespace: "hardware" | "software",
  kind: "added" | "removed",
): { text: string; className: string }[] {
  return Object.keys(section).map((key) => ({
    text: `${namespace}.${key} ${kind === "added" ? "добавлено" : "удалено"}`,
    className: kind === "added" ? "diff-added" : "diff-removed",
  }));
}

function modifiedLines(
  section: Record<string, unknown>,
  namespace: "hardware" | "software",
): { text: string; className: string }[] {
  return Object.entries(section).map(([key, value]) => {
    const { old: oldValue, new: newValue } = value as { old: unknown; new: unknown };
    return {
      text: `${namespace}.${key}: ${String(oldValue)} → ${String(newValue)}`,
      className: "diff-modified",
    };
  });
}

function allDiffLines(change: InventoryChange): { text: string; className: string }[] {
  return [
    ...diffLines(change.added.hardware, "hardware", "added"),
    ...diffLines(change.added.software, "software", "added"),
    ...modifiedLines(change.modified.hardware, "hardware"),
    ...modifiedLines(change.modified.software, "software"),
    ...diffLines(change.removed.hardware, "hardware", "removed"),
    ...diffLines(change.removed.software, "software", "removed"),
  ];
}

export function ChangeTimeline({ changes }: { changes: InventoryChange[] }) {
  const [expanded, setExpanded] = useState<Set<string>>(new Set());

  if (changes.length === 0) {
    return <p className="muted">Изменений конфигурации не зафиксировано.</p>;
  }

  const toggle = (id: string) => {
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(id)) {
        next.delete(id);
      } else {
        next.add(id);
      }
      return next;
    });
  };

  return (
    <ul className="change-timeline">
      {changes.map((change) => {
        const isOpen = expanded.has(change.id);
        const lines = allDiffLines(change);
        return (
          <li key={change.id} className="change-entry">
            <button
              type="button"
              className="change-entry-header"
              onClick={() => toggle(change.id)}
              aria-expanded={isOpen}
            >
              <span className="change-entry-time">
                <ChevronRightIcon
                  color="var(--text-tertiary)"
                  size={12}
                  {...{
                    style: { transform: isOpen ? "rotate(90deg)" : "none" },
                  }}
                />
                {new Date(change.detected_at).toLocaleString("ru-RU")}
              </span>
              <span className="change-entry-summary">
                {summaryParts(change).map((part, index) => (
                  <span
                    key={index}
                    style={{ color: part.color, marginLeft: index > 0 ? 8 : 0 }}
                  >
                    {part.label}
                  </span>
                ))}
              </span>
            </button>
            {isOpen && lines.length > 0 && (
              <div className="change-diff">
                {lines.map((line, index) => (
                  <span key={index} className={`diff-row ${line.className}`}>
                    {line.text}
                  </span>
                ))}
              </div>
            )}
          </li>
        );
      })}
    </ul>
  );
}
