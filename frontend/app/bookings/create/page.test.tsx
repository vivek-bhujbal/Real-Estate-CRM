import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import CreateBookingPage from "@/app/bookings/create/page";
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

const options = {
  quotations: [{
    id: "quote-1",
    quotation_number: "Q-001",
    version: 3,
    customer_id: "customer-1",
    customer_name: "Test Buyer",
    unit_id: "unit-1",
    unit_number: "A-101",
    agreed_price: "12500000.00",
    discount_amount: "100000.00",
    booking_amount: "500000.00",
    currency: "INR",
    hold_id: "approved-hold-1",
  }],
  salespeople: [{ id: "salesperson-1", label: "Sales User" }],
  brokers: [],
  approvers: [],
};

describe("booking creation workflow", () => {
  beforeEach(() => {
    mocks.auth = { session: sessionFactory({ id: "salesperson-1", permissions: ["bookings.create"] }) };
    mocks.apiRequest.mockImplementation((path: string, init?: RequestInit) => {
      if (path === "/bookings/options") return Promise.resolve(options);
      if (path === "/bookings" && init?.method === "POST") return Promise.resolve({ id: "booking-1" });
      throw new Error(`Unexpected test request: ${path}`);
    });
  });

  it("keeps quotation, hold, and price server-derived when creating a booking", async () => {
    const user = userEvent.setup();
    render(<CreateBookingPage />);

    await user.selectOptions(await screen.findByLabelText("Eligible accepted quotation"), "quote-1");
    await user.type(screen.getByLabelText("Booking number"), "bk-001");
    await user.click(screen.getByRole("button", { name: "Create booking" }));

    await waitFor(() => expect(mocks.push).toHaveBeenCalledWith("/bookings/booking-1"));
    const createCall = mocks.apiRequest.mock.calls.find(([path, init]) => path === "/bookings" && init?.method === "POST");
    const payload = JSON.parse(String(createCall?.[1]?.body));
    expect(payload).toMatchObject({
      quotation_id: "quote-1",
      unit_hold_id: "approved-hold-1",
      booking_number: "BK-001",
      salesperson_user_id: "salesperson-1",
      financing: { status: "NOT_REQUIRED" },
      payment_plan: {
        name: "Standard payment plan",
        installments: [{ name: "Agreed property value", amount: "12500000.00" }],
      },
    });
    expect(payload).not.toHaveProperty("agreed_price");
    expect(payload).not.toHaveProperty("unit_id");
  });

  it("shows the real prerequisite empty state when the API returns no eligible records", async () => {
    mocks.apiRequest.mockResolvedValueOnce({ ...options, quotations: [] });
    render(<CreateBookingPage />);
    expect(await screen.findByRole("heading", { name: "No eligible quotation" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Create booking" })).not.toBeInTheDocument();
  });
});
