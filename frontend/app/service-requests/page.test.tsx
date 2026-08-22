import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import ServiceRequestsPage from "@/app/service-requests/page";
import { sessionFactory } from "@/test/factories";

const mocks = vi.hoisted(() => ({
  push: vi.fn(),
  apiRequest: vi.fn(),
  auth: { session: null } as Record<string, unknown>,
}));

vi.mock("next/navigation", () => ({ useRouter: () => ({ push: mocks.push }) }));
vi.mock("next/link", () => ({ default: ({ href, children, ...props }: React.AnchorHTMLAttributes<HTMLAnchorElement> & { href: string }) => <a href={href} {...props}>{children}</a> }));
vi.mock("@/components/app-shell", () => ({ AppShell: ({ children }: { children: React.ReactNode }) => <>{children}</> }));
vi.mock("@/components/auth-provider", () => ({ useAuth: () => mocks.auth }));
vi.mock("@/lib/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api")>();
  return { ...actual, apiRequest: mocks.apiRequest };
});

const category = {
  id: "category-1", code: "GENERAL", name: "General request", description: null,
  is_active: true, policy_count: 0, ticket_count: 0,
  created_at: "2026-01-01T00:00:00Z", updated_at: "2026-01-01T00:00:00Z",
};

describe("service request critical workflow", () => {
  beforeEach(() => {
    mocks.auth = { session: sessionFactory({ permissions: ["service_requests.view", "service_requests.create"] }) };
    mocks.apiRequest.mockImplementation((path: string, init?: RequestInit) => {
      if (path.startsWith("/service-requests?") && !init) return Promise.resolve({ items: [], page: 1, page_size: 20, total: 0, pages: 0 });
      if (path === "/service-requests/stats") return Promise.resolve({ total_open: 0, unassigned: 0, in_progress: 0, waiting_for_customer: 0, resolved: 0, sla_breached: 0, escalated: 0, average_feedback: null });
      if (path === "/service-requests/options") return Promise.resolve({ categories: [category], agents: [], customers: [], tenants: [], projects: [], units: [] });
      if (path === "/service-requests" && init?.method === "POST") return Promise.resolve({ ticket: { id: "ticket-1" } });
      throw new Error(`Unexpected test request: ${path}`);
    });
  });

  it("creates a ticket through the API and routes to its persisted detail page", async () => {
    const user = userEvent.setup();
    render(<ServiceRequestsPage />);
    await screen.findByText("No tickets found");

    await user.click(screen.getByRole("button", { name: "New ticket" }));
    await user.selectOptions(screen.getByLabelText("Category"), "category-1");
    await user.type(screen.getByLabelText("Subject"), "Possession document query");
    await user.type(screen.getByLabelText("Description"), "Customer needs a verified handover copy.");
    await user.click(screen.getByRole("button", { name: "Create ticket" }));

    await waitFor(() => expect(mocks.push).toHaveBeenCalledWith("/service-requests/ticket-1"));
    const createCall = mocks.apiRequest.mock.calls.find(([path, init]) => path === "/service-requests" && init?.method === "POST");
    expect(JSON.parse(String(createCall?.[1]?.body))).toMatchObject({
      category_id: "category-1",
      priority: "MEDIUM",
      subject: "Possession document query",
      assigned_user_id: null,
    });
  });

  it("does not render ticket creation when permission is absent", async () => {
    mocks.auth = { session: sessionFactory({ permissions: ["service_requests.view"] }) };
    render(<ServiceRequestsPage />);
    await screen.findByText("No tickets found");
    expect(screen.queryByRole("button", { name: "New ticket" })).not.toBeInTheDocument();
  });
});
