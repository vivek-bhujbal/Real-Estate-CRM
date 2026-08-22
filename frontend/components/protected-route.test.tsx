import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ProtectedRoute } from "@/components/protected-route";
import { sessionFactory } from "@/test/factories";

const mocks = vi.hoisted(() => ({
  replace: vi.fn(),
  auth: { status: "loading", session: null } as Record<string, unknown>,
}));

vi.mock("next/navigation", () => ({ useRouter: () => ({ replace: mocks.replace }) }));
vi.mock("next/link", () => ({ default: ({ href, children, ...props }: React.AnchorHTMLAttributes<HTMLAnchorElement> & { href: string }) => <a href={href} {...props}>{children}</a> }));
vi.mock("@/components/auth-provider", () => ({ useAuth: () => mocks.auth }));

describe("ProtectedRoute", () => {
  beforeEach(() => {
    mocks.auth = { status: "loading", session: null };
  });

  it("redirects an unauthenticated user and never renders protected content", () => {
    mocks.auth = { status: "unauthenticated", session: null };
    render(<ProtectedRoute><div>Private content</div></ProtectedRoute>);
    expect(screen.queryByText("Private content")).not.toBeInTheDocument();
    expect(mocks.replace).toHaveBeenCalledWith("/login");
  });

  it("renders a stable access-denied state when the backend permission is absent", () => {
    mocks.auth = { status: "authenticated", session: sessionFactory({ permissions: ["leads.view"] }) };
    render(<ProtectedRoute permission="bookings.view"><div>Booking content</div></ProtectedRoute>);
    expect(screen.getByRole("heading", { name: "This workspace is not available" })).toBeInTheDocument();
    expect(screen.queryByText("Booking content")).not.toBeInTheDocument();
  });

  it("accepts module manage permission and renders children", () => {
    mocks.auth = { status: "authenticated", session: sessionFactory({ permissions: ["bookings.manage"] }) };
    render(<ProtectedRoute permission="bookings.view"><div>Booking content</div></ProtectedRoute>);
    expect(screen.getByText("Booking content")).toBeInTheDocument();
  });
});
