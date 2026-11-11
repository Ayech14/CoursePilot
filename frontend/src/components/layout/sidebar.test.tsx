import { fireEvent, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { jsonResponse, stubApi } from "../../test/fakeServer";
import { renderApp } from "../../test/renderApp";

async function openApp() {
  stubApi({ "GET /dashboard": () => jsonResponse(500, {}) });
  renderApp("/dashboard");
  return screen.findByRole("button", { name: "Collapse sidebar" });
}

describe("collapsible sidebar", () => {
  it("folds down to icons that still navigate, and remembers it", async () => {
    const user = userEvent.setup();
    await user.click(await openApp());

    const expand = screen.getByRole("button", { name: "Expand sidebar" });
    expect(expand).toHaveAttribute("aria-expanded", "false");
    expect(localStorage.getItem("coursepilot.sidebar")).toBe("collapsed");

    // Labels are hidden from sight but still name each link, and hovering shows them.
    const nav = within(screen.getAllByRole("navigation", { name: "Main" })[0]!);
    const tasks = nav.getByRole("link", { name: "Tasks" });
    expect(tasks).toHaveAttribute("title", "Tasks");
    expect(within(tasks).getByText("Tasks")).toHaveClass("sr-only");

    await user.click(expand);
    expect(screen.getByRole("button", { name: "Collapse sidebar" })).toHaveAttribute("aria-expanded", "true");
    expect(localStorage.getItem("coursepilot.sidebar")).toBeNull();
  });

  it("opens folded when it was left folded", async () => {
    localStorage.setItem("coursepilot.sidebar", "collapsed");
    stubApi({ "GET /dashboard": () => jsonResponse(500, {}) });
    renderApp("/dashboard");
    expect(await screen.findByRole("button", { name: "Expand sidebar" })).toBeInTheDocument();
  });

  it("toggles with Ctrl or Cmd and backslash", async () => {
    await openApp();
    fireEvent.keyDown(document, { key: "\\", ctrlKey: true });
    expect(screen.getByRole("button", { name: "Expand sidebar" })).toBeInTheDocument();
    fireEvent.keyDown(document, { key: "\\", metaKey: true });
    expect(screen.getByRole("button", { name: "Collapse sidebar" })).toBeInTheDocument();
    fireEvent.keyDown(document, { key: "\\" });
    expect(screen.getByRole("button", { name: "Collapse sidebar" })).toBeInTheDocument();
  });
});
