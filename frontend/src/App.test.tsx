import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";

import { App } from "./App";
import { AuthProvider } from "./features/auth/AuthContext";
import { ADA, callsTo, errorResponse, jsonResponse, session, stubFetch } from "./test/fakeServer";

const REFRESH = "/api/v1/auth/refresh";

function renderApp(path: string) {
  return render(
    <QueryClientProvider client={new QueryClient()}>
      <MemoryRouter initialEntries={[path]}>
        <AuthProvider>
          <App />
        </AuthProvider>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

const noSession = () => errorResponse(401, "invalid_refresh_token", "Expired");

describe("routing", () => {
  it("sends anonymous visitors to the login page", async () => {
    stubFetch(noSession);
    renderApp("/dashboard");
    expect(await screen.findByRole("heading", { name: "Sign in" })).toBeInTheDocument();
  });

  it("restores a session from the refresh cookie", async () => {
    stubFetch(() => jsonResponse(200, session()));
    renderApp("/dashboard");
    expect(await screen.findByRole("heading", { name: /Ada$/ })).toBeInTheDocument();
  });

  it("does not show invented figures on the dashboard", async () => {
    stubFetch(() => jsonResponse(200, session()));
    renderApp("/dashboard");
    expect(await screen.findByText("Nothing to show yet")).toBeInTheDocument();
  });

  it("redirects signed-in users away from the login page", async () => {
    stubFetch(() => jsonResponse(200, session()));
    renderApp("/login");
    expect(await screen.findByRole("heading", { name: /Ada$/ })).toBeInTheDocument();
  });

  it("labels unbuilt pages as not built", async () => {
    stubFetch(() => jsonResponse(200, session()));
    renderApp("/analytics");
    expect(await screen.findByText("Not built yet")).toBeInTheDocument();
    expect(screen.getByText("Planned for Milestone 5")).toBeInTheDocument();
  });

  it("shows a not found page for unknown paths", async () => {
    stubFetch(noSession);
    renderApp("/does-not-exist");
    expect(await screen.findByText("Page not found")).toBeInTheDocument();
  });
});

describe("sign in", () => {
  it("signs in and returns to the originally requested page", async () => {
    stubFetch((url) => (url === REFRESH ? noSession() : jsonResponse(200, session())));
    renderApp("/settings");
    const user = userEvent.setup();

    await user.type(await screen.findByLabelText("Email"), "ada@example.com");
    await user.type(screen.getByLabelText("Password"), "a-long-enough-password");
    await user.click(screen.getByRole("button", { name: "Sign in" }));

    expect(await screen.findByRole("heading", { name: "Settings" })).toBeInTheDocument();
  });

  it("shows the server's message for wrong credentials", async () => {
    stubFetch((url) =>
      url === REFRESH ? noSession() : errorResponse(401, "invalid_credentials", "Incorrect email or password."),
    );
    renderApp("/login");
    const user = userEvent.setup();

    await user.type(await screen.findByLabelText("Email"), "ada@example.com");
    await user.type(screen.getByLabelText("Password"), "wrong-password");
    await user.click(screen.getByRole("button", { name: "Sign in" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("Incorrect email or password.");
    expect(screen.getByRole("button", { name: "Sign in" })).toBeEnabled();
  });
});

describe("registration", () => {
  it("shows validation errors beside the matching field", async () => {
    stubFetch((url) =>
      url === REFRESH
        ? noSession()
        : errorResponse(422, "validation_error", "Invalid", [
            { field: "password", message: "Password is too short" },
          ]),
    );
    renderApp("/register");
    const user = userEvent.setup();

    await user.click(await screen.findByRole("button", { name: "Create account" }));

    const password = screen.getByLabelText("Password");
    await waitFor(() => expect(password).toBeInvalid());
    expect(password).toHaveAccessibleDescription("Password is too short");
  });

  it("submits the detected time zone", async () => {
    const fetchMock = stubFetch((url) =>
      url === REFRESH ? noSession() : jsonResponse(201, session()),
    );
    renderApp("/register");
    const user = userEvent.setup();

    await user.type(await screen.findByLabelText("Name"), "Ada");
    await user.type(screen.getByLabelText("Email"), "ada@example.com");
    await user.type(screen.getByLabelText("Password"), "a-long-enough-password");
    await user.click(screen.getByRole("button", { name: "Create account" }));

    await screen.findByRole("heading", { name: /Ada$/ });
    const [, init] = callsTo(fetchMock, "/api/v1/auth/register")[0]!;
    expect(JSON.parse(init.body as string).timezone).toBe(
      Intl.DateTimeFormat().resolvedOptions().timeZone,
    );
  });
});

describe("signed-in actions", () => {
  it("signs out and returns to the login page", async () => {
    stubFetch((url) =>
      url === "/api/v1/auth/logout" ? new Response(null, { status: 204 }) : jsonResponse(200, session()),
    );
    renderApp("/dashboard");
    const user = userEvent.setup();

    await user.click(await screen.findByRole("button", { name: "Sign out" }));

    expect(await screen.findByRole("heading", { name: "Sign in" })).toBeInTheDocument();
  });

  it("saves profile changes", async () => {
    const fetchMock = stubFetch((url) =>
      url === REFRESH ? jsonResponse(200, session()) : jsonResponse(200, { ...ADA, display_name: "Ada L." }),
    );
    renderApp("/settings");
    const user = userEvent.setup();

    const name = await screen.findByLabelText("Name");
    await user.clear(name);
    await user.type(name, "Ada L.");
    await user.click(screen.getByRole("button", { name: "Save changes" }));

    expect(await screen.findByText("Saved")).toBeInTheDocument();
    const [, init] = callsTo(fetchMock, "/api/v1/users/me")[0]!;
    expect(init.method).toBe("PATCH");
    expect(JSON.parse(init.body as string).display_name).toBe("Ada L.");
  });
});
