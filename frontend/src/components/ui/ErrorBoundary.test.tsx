import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { ErrorBoundary } from "./ErrorBoundary";

function Broken(): never {
  throw new Error("boom");
}

describe("ErrorBoundary", () => {
  it("shows a recoverable message instead of a blank page, and clears on navigation", () => {
    vi.spyOn(console, "error").mockImplementation(() => {});
    const { rerender } = render(
      <ErrorBoundary resetKey="/schedule">
        <Broken />
      </ErrorBoundary>,
    );
    expect(screen.getByRole("alert")).toHaveTextContent("Something went wrong on this page");

    rerender(
      <ErrorBoundary resetKey="/tasks">
        <p>Tasks page</p>
      </ErrorBoundary>,
    );
    expect(screen.getByText("Tasks page")).toBeInTheDocument();
  });
});
