import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { jsonResponse, stubApi } from "../../test/fakeServer";
import { renderApp } from "../../test/renderApp";

function prefersDark(dark: boolean) {
  vi.stubGlobal("matchMedia", (query: string) => ({
    matches: query.includes("dark") ? dark : !dark,
    addEventListener: () => {},
    removeEventListener: () => {},
  }));
}

describe("appearance", () => {
  afterEach(() => {
    delete document.documentElement.dataset.theme;
  });

  it("switches theme from the sidebar and remembers it", async () => {
    prefersDark(true);
    stubApi({ "GET /dashboard": () => jsonResponse(500, {}) });
    renderApp("/dashboard");
    const user = userEvent.setup();
    const [toggle] = await screen.findAllByRole("button", { name: "Switch to light theme" });
    await user.click(toggle!);
    expect(document.documentElement.dataset.theme).toBe("light");
    expect(localStorage.getItem("coursepilot.theme")).toBe("light");
    expect(screen.getAllByRole("button", { name: "Switch to dark theme" }).length).toBeGreaterThan(0);
  });

  it("offers match device, light and dark in Settings", async () => {
    prefersDark(false);
    stubApi({});
    renderApp("/settings");
    const user = userEvent.setup();
    const system = await screen.findByRole("radio", { name: "Match device" });
    expect(system).toHaveAttribute("aria-checked", "true");
    expect(document.documentElement.dataset.theme).toBeUndefined();

    await user.click(screen.getByRole("radio", { name: "Dark" }));
    expect(localStorage.getItem("coursepilot.theme")).toBe("dark");
    expect(document.documentElement.dataset.theme).toBeUndefined();

    await user.click(screen.getByRole("radio", { name: "Match device" }));
    expect(localStorage.getItem("coursepilot.theme")).toBeNull();
    expect(document.documentElement.dataset.theme).toBe("light");
  });
});
