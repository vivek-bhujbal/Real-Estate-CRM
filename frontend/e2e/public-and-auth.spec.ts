import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";

async function makeUnauthenticated(page: Page) {
  await page.route("**/api/v1/auth/refresh", async (route) => {
    await route.fulfill({
      status: 401,
      contentType: "application/json",
      body: JSON.stringify({ error: { code: "AUTHENTICATION_REQUIRED", message: "Sign in required" } })
    });
  });
}

async function makeAuthenticated(page: Page) {
  const now = new Date().toISOString();
  const session = {
    access_token: "isolated-browser-test-token",
    token_type: "bearer",
    expires_in: 900,
    user: {
      id: "browser-test-user",
      email: "admin@example.test",
      full_name: "Browser Test Admin",
      organization_id: "browser-test-organization",
      branch_id: null,
      department_id: null,
      is_active: true,
      created_at: now,
      organization: {
        id: "browser-test-organization",
        name: "Isolated Test Workspace",
        slug: "isolated-test-workspace"
      },
      permissions: ["dashboard.view", "notifications.view", "notifications.update"]
    }
  };
  await page.route("**/api/v1/**", async (route) => {
    const path = new URL(route.request().url()).pathname;
    let body: unknown;
    if (path.endsWith("/auth/refresh")) body = session;
    else if (path.endsWith("/dashboard/catalog")) {
      body = {
        items: [{ kind: "EXECUTIVE", label: "Executive", description: "Executive overview" }],
        default_dashboard: "EXECUTIVE"
      };
    } else if (path.endsWith("/dashboard/EXECUTIVE")) {
      body = {
        kind: "EXECUTIVE",
        title: "Executive dashboard",
        description: "Calculated from the isolated test database.",
        currency: "INR",
        as_of: now,
        metrics: [],
        charts: []
      };
    } else if (path.endsWith("/notifications/unread-count")) body = { unread: 0 };
    else if (path.endsWith("/notifications")) {
      body = { items: [], page: 1, page_size: 6, total: 0, pages: 0 };
    } else {
      await route.fulfill({ status: 404, contentType: "application/json", body: "{}" });
      return;
    }
    await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(body) });
  });
}

async function expectAccessible(page: Page) {
  const results = await new AxeBuilder({ page }).analyze();
  expect(results.violations, JSON.stringify(results.violations, null, 2)).toEqual([]);
}

test("login is keyboard-operable and has no detectable accessibility violations", async ({ page }) => {
  await makeUnauthenticated(page);
  const navigation = await page.goto("/login");
  await expect(page.getByRole("heading", { name: "Sign in to your workspace" })).toBeVisible();
  const policy = navigation?.headers()["content-security-policy"] ?? "";
  const scriptPolicy = policy.split(";").find((directive) => directive.trim().startsWith("script-src"));
  expect(scriptPolicy).toContain("'strict-dynamic'");
  expect(scriptPolicy).toContain("'nonce-");
  expect(scriptPolicy).not.toContain("'unsafe-inline'");
  const scriptNonces = await page.locator("script").evaluateAll((scripts) =>
    scripts.map((script) => (script as HTMLScriptElement).nonce)
  );
  expect(scriptNonces.length).toBeGreaterThan(0);
  expect(scriptNonces.every(Boolean)).toBe(true);

  const organizationId = page.getByLabel("Organization ID");
  for (
    let index = 0;
    index < 3 && !(await organizationId.evaluate((node) => node === document.activeElement));
    index += 1
  ) {
    await page.keyboard.press("Tab");
  }
  await expect(organizationId).toBeFocused();
  await page.keyboard.type("northstar-realty");
  await page.keyboard.press("Tab");
  await page.keyboard.type("user@example.com");
  await page.keyboard.press("Tab");
  await page.keyboard.type("not-a-real-password");

  await expectAccessible(page);
});

test("onboarding has explicit labels, responsive controls and no accessibility violations", async ({ page }) => {
  await makeUnauthenticated(page);
  await page.goto("/onboarding");
  await expect(page.getByRole("heading", { name: "Set up your organization" })).toBeVisible();
  await page.getByLabel("Organization name").fill("Northstar Realty");
  await expect(page.getByLabel("Organization ID")).toHaveValue("northstar-realty");
  await expect(page.getByRole("button", { name: "Create workspace" })).toBeVisible();
  await expectAccessible(page);
});

test("unauthenticated users are redirected away from protected pages", async ({ page }) => {
  await makeUnauthenticated(page);
  await page.goto("/dashboard");
  await expect(page).toHaveURL(/\/login$/);
  await expect(page.getByRole("heading", { name: "Sign in to your workspace" })).toBeVisible();
});

test("unknown routes use the branded, accessible recovery page", async ({ page }) => {
  await makeUnauthenticated(page);
  await page.goto("/route-that-does-not-exist");
  await expect(page.getByRole("heading", { name: "That address does not exist" })).toBeVisible();
  await expect(page.getByRole("link", { name: "Go to sign in" })).toBeVisible();
  await expectAccessible(page);
});

test("authenticated empty dashboard and navigation are accessible", async ({ page }) => {
  await makeAuthenticated(page);
  await page.goto("/dashboard");
  await expect(page.getByRole("heading", { name: "Executive dashboard" })).toBeVisible();
  await expect(page.getByRole("navigation", { name: "Primary navigation" })).toBeVisible();
  await expect(page.getByText("Live database calculations")).toBeVisible();
  await expectAccessible(page);
});
