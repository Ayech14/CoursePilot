import { expect, test, type Page } from "@playwright/test";

/** Every run makes its own student, so runs never depend on each other. */
function newStudent() {
  const id = `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
  return { name: "Journey Student", email: `journey-${id}@example.com`, password: `journey-pass-${id}` };
}

async function register(page: Page, student = newStudent()) {
  await page.goto("/register");
  await page.getByLabel("Name").fill(student.name);
  await page.getByLabel("Email").fill(student.email);
  await page.getByLabel("Password").fill(student.password);
  await page.getByLabel("Time zone").selectOption("America/Toronto");
  await page.getByRole("button", { name: "Create account" }).click();
  await expect(page).toHaveURL(/\/dashboard$/);
  return student;
}

/** On a phone the navigation sits behind the menu button. */
async function go(page: Page, name: string) {
  const menu = page.getByRole("button", { name: "Open menu" });
  if (await menu.isVisible()) await menu.click();
  await page.getByRole("navigation", { name: "Main" }).getByRole("link", { name }).click();
}

/** A deadline five days from now, as the date-time field expects it. */
function inFiveDays(): string {
  const date = new Date(Date.now() + 5 * 24 * 60 * 60 * 1000);
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T23:59`;
}

test("a new student plans their week, times a session and finds their task", async ({ page }) => {
  await register(page);
  await expect(page.getByText("Nothing to show yet")).toBeVisible();

  await go(page, "Courses");
  await page.getByRole("button", { name: "New course" }).click();
  const course = page.getByRole("dialog", { name: "New course" });
  await course.getByLabel("Name").fill("Linear Algebra");
  await course.getByRole("button", { name: "Create course" }).click();
  await expect(page.getByText("Linear Algebra").first()).toBeVisible();

  await go(page, "Tasks");
  await page.getByRole("button", { name: "New task" }).first().click();
  const task = page.getByRole("dialog", { name: "New task" });
  await task.getByLabel("Title").fill("Problem set 1");
  await task.getByLabel("Course").selectOption({ label: "Linear Algebra" });
  await task.getByLabel("Deadline (optional)").fill(inFiveDays());
  await task.getByLabel("Estimated effort (hours)").fill("3");
  await task.getByRole("button", { name: "Create task" }).click();
  await expect(page.getByText("Problem set 1")).toBeVisible();

  await go(page, "Your week");
  for (const day of ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]) {
    await page.getByRole("button", { name: `Add ${day} time` }).click();
  }
  await page.getByRole("button", { name: "Save weekly hours" }).click();
  await expect(page.getByText("Saved")).toBeVisible();

  await go(page, "Schedule");
  await page.getByRole("button", { name: "Generate schedule" }).click();
  const proposal = page.getByRole("region", { name: "Proposed schedule" });
  await expect(proposal).toBeVisible();
  await proposal.getByRole("button", { name: "Apply changes" }).click();
  await expect(proposal).toBeHidden();
  await page.getByRole("button", { name: "List" }).click();
  await expect(page.getByText("Problem set 1").first()).toBeVisible();

  // Start a timer on the task without waiting for its planned session, then undo it.
  await page.getByRole("button", { name: "Start timer" }).click();
  const timer = page.getByRole("dialog", { name: "Start a timer" });
  await expect(timer.getByRole("combobox")).toHaveValue(/.+/);
  await timer.getByRole("button", { name: "Start timer" }).click();
  const bar = page.getByRole("region", { name: "Study timer" });
  await expect(bar).toContainText("Problem set 1");
  await bar.getByRole("button", { name: "Discard" }).click();
  await page.getByRole("button", { name: "Discard timer" }).click();
  await expect(bar).toBeHidden();

  // Search finds the task from anywhere.
  await go(page, "Dashboard");
  await page.getByRole("button", { name: "Search" }).first().click();
  await page.getByRole("combobox", { name: "Search pages, tasks and courses" }).fill("problem");
  await expect(page.getByRole("option", { name: /Problem set 1/ })).toHaveAttribute("aria-selected", "true");
  await page.keyboard.press("Enter");
  await expect(page.getByRole("dialog", { name: "Edit task" })).toBeVisible();
  await expect(page.getByLabel("Title")).toHaveValue("Problem set 1");
  await page.keyboard.press("Escape");

  // A reload keeps the student signed in, through the same-origin refresh cookie.
  await page.reload();
  await expect(page.getByRole("heading", { level: 1 })).toContainText("Journey Student");
});

test("signing out and back in, and a wrong password is refused", async ({ page }) => {
  const student = await register(page);
  const menu = page.getByRole("button", { name: "Open menu" });
  if (await menu.isVisible()) await menu.click();
  await page.getByRole("button", { name: "Sign out" }).click();
  await expect(page).toHaveURL(/\/login$/);

  await page.getByLabel("Email").fill(student.email);
  await page.getByLabel("Password").fill("not-the-password");
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page.getByText("Incorrect email or password.")).toBeVisible();

  await page.getByLabel("Password").fill(student.password);
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page).toHaveURL(/\/dashboard$/);
});

test("pages are served with the strict policy and nothing is blocked", async ({ page }) => {
  const blocked: string[] = [];
  page.on("console", (message) => {
    if (message.type() === "error" && message.text().includes("Content Security Policy")) blocked.push(message.text());
  });
  const response = await page.goto("/login");
  expect(response?.headers()["content-security-policy"]).toContain("default-src 'self'");
  await register(page);
  await go(page, "Schedule");
  await expect(page.locator(".fc")).toBeVisible();
  await go(page, "Analytics");
  await expect(page.getByRole("heading", { name: "Analytics" })).toBeVisible();
  expect(blocked).toEqual([]);
});
