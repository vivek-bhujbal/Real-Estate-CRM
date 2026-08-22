import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import CreateLeadPage from "@/app/leads/create/page";
import { sessionFactory } from "@/test/factories";

const mocks = vi.hoisted(() => ({
  push: vi.fn(),
  apiRequest: vi.fn(),
  auth: { session: null } as Record<string, unknown>,
}));

vi.mock("next/navigation", () => ({ useRouter: () => ({ push: mocks.push }) }));
vi.mock("next/link", () => ({ default: ({ href, children, ...props }: React.AnchorHTMLAttributes<HTMLAnchorElement> & { href: string }) => <a href={href} {...props}>{children}</a> }));
vi.mock("@/components/app-shell", () => ({ AppShell: ({ children }: { children: React.ReactNode }) => <>{children}</> }));
vi.mock("@/components/lead-navigation", () => ({ LeadNavigation: () => <nav aria-label="Lead navigation" /> }));
vi.mock("@/components/auth-provider", () => ({ useAuth: () => mocks.auth }));
vi.mock("@/lib/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api")>();
  return { ...actual, apiRequest: mocks.apiRequest };
});

describe("lead creation workflow", () => {
  beforeEach(() => {
    mocks.auth = { session: sessionFactory({ permissions: ["leads.create"] }) };
    mocks.apiRequest.mockImplementation((path: string, init?: RequestInit) => {
      if (path === "/leads/sources") return Promise.resolve([]);
      if (path === "/leads/duplicate-check") return Promise.resolve([]);
      if (path === "/leads" && init?.method === "POST") return Promise.resolve({ id: "created-lead" });
      throw new Error(`Unexpected test request: ${path}`);
    });
  });

  it("does not render assignment controls without assignment permission", async () => {
    render(<CreateLeadPage />);
    await waitFor(() => expect(mocks.apiRequest).toHaveBeenCalledWith("/leads/sources"));
    expect(screen.queryByLabelText("Owner")).not.toBeInTheDocument();
  });

  it("submits normalized optional values and routes to the persisted lead", async () => {
    const user = userEvent.setup();
    render(<CreateLeadPage />);
    await screen.findByRole("heading", { name: "Create lead" });

    await user.type(screen.getByLabelText("Full name"), "Riya Sharma");
    await user.type(screen.getByLabelText("Email"), "riya@example.com");
    await user.type(screen.getByLabelText("Minimum budget"), "8000000");
    await user.type(screen.getByLabelText("Maximum budget"), "12000000");
    await user.click(screen.getByRole("button", { name: "Create lead" }));

    await waitFor(() => expect(mocks.push).toHaveBeenCalledWith("/leads/created-lead"));
    const createCall = mocks.apiRequest.mock.calls.find(([path, init]) => path === "/leads" && init?.method === "POST");
    expect(createCall).toBeDefined();
    expect(JSON.parse(String(createCall?.[1]?.body))).toMatchObject({
      full_name: "Riya Sharma",
      email: "riya@example.com",
      phone: null,
      owner_user_id: null,
      budget_min: "8000000",
      budget_max: "12000000",
      duplicate_override: false,
    });
  });
});
