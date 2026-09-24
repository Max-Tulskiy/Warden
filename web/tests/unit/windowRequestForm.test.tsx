import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { WindowRequestForm } from "../../src/components/WindowRequestForm";
import { validateWindow } from "../../src/lib/windowValidation";

describe("validateWindow", () => {
  it("accepts exactly the 4-hour cap", () => {
    expect(validateWindow("2026-01-01T09:00", "2026-01-01T13:00")).toBeNull();
  });

  it("rejects a window over 4 hours", () => {
    expect(validateWindow("2026-01-01T09:00", "2026-01-01T13:01")).toMatch(/4 часов/);
  });

  it("rejects an end that is not after the start", () => {
    expect(validateWindow("2026-01-01T09:00", "2026-01-01T09:00")).toMatch(/позже/);
  });

  it("rejects missing values", () => {
    expect(validateWindow("", "2026-01-01T09:00")).toMatch(/Укажите/);
  });

  describe("against a limit the server gave", () => {
    it("accepts a window of exactly that limit", () => {
      expect(validateWindow("2026-01-01T09:00", "2026-01-01T11:00", 2)).toBeNull();
    });

    it("rejects a window a minute over it, naming the limit", () => {
      expect(validateWindow("2026-01-01T09:00", "2026-01-01T11:01", 2)).toBe(
        "Промежуток не должен превышать 2 часов",
      );
    });

    it("says «1 часа» for a limit of one hour", () => {
      expect(validateWindow("2026-01-01T09:00", "2026-01-01T10:01", 1)).toBe(
        "Промежуток не должен превышать 1 часа",
      );
    });

    it("still accepts up to four hours when no limit is given", () => {
      expect(validateWindow("2026-01-01T09:00", "2026-01-01T13:00")).toBeNull();
    });
  });
});

describe("WindowRequestForm", () => {
  it("shows a client-side error and does not call onSubmit for an invalid window", async () => {
    const onSubmit = vi.fn();
    render(<WindowRequestForm onSubmit={onSubmit} />);

    await userEvent.type(screen.getByLabelText("Начало"), "2026-01-01T09:00");
    await userEvent.type(screen.getByLabelText("Конец"), "2026-01-01T09:00");
    await userEvent.click(screen.getByRole("button", { name: /Запросить/ }));

    expect(await screen.findByText(/позже/)).toBeInTheDocument();
    expect(onSubmit).not.toHaveBeenCalled();
  });

  it("calls onSubmit with ISO timestamps for a valid window", async () => {
    const onSubmit = vi.fn().mockResolvedValue(undefined);
    render(<WindowRequestForm onSubmit={onSubmit} />);

    await userEvent.type(screen.getByLabelText("Начало"), "2026-01-01T09:00");
    await userEvent.type(screen.getByLabelText("Конец"), "2026-01-01T10:00");
    await userEvent.click(screen.getByRole("button", { name: /Запросить/ }));

    expect(onSubmit).toHaveBeenCalledTimes(1);
    const [start, end] = onSubmit.mock.calls[0] as [string, string];
    expect(new Date(end).getTime() - new Date(start).getTime()).toBe(60 * 60 * 1000);
  });

  describe("with a limit from the server", () => {
    it("says the limit in force", () => {
      render(<WindowRequestForm onSubmit={vi.fn()} maxHours={2} />);

      expect(
        screen.getByText("Промежуток не должен превышать 2 часов"),
      ).toBeInTheDocument();
    });

    it("says four hours when it is given no limit", () => {
      render(<WindowRequestForm onSubmit={vi.fn()} />);

      expect(
        screen.getByText("Промежуток не должен превышать 4 часов"),
      ).toBeInTheDocument();
    });

    it("refuses a longer window before sending anything", async () => {
      const onSubmit = vi.fn();
      render(<WindowRequestForm onSubmit={onSubmit} maxHours={2} />);

      await userEvent.type(screen.getByLabelText("Начало"), "2026-01-01T09:00");
      await userEvent.type(screen.getByLabelText("Конец"), "2026-01-01T12:00");
      await userEvent.click(screen.getByRole("button", { name: /Запросить/ }));

      expect(
        await screen.findByText("Промежуток не должен превышать 2 часов", {
          selector: ".error",
        }),
      ).toBeInTheDocument();
      expect(onSubmit).not.toHaveBeenCalled();
    });

    it("sends a window at the limit", async () => {
      const onSubmit = vi.fn().mockResolvedValue(undefined);
      render(<WindowRequestForm onSubmit={onSubmit} maxHours={2} />);

      await userEvent.type(screen.getByLabelText("Начало"), "2026-01-01T09:00");
      await userEvent.type(screen.getByLabelText("Конец"), "2026-01-01T11:00");
      await userEvent.click(screen.getByRole("button", { name: /Запросить/ }));

      expect(onSubmit).toHaveBeenCalledTimes(1);
    });
  });
});
