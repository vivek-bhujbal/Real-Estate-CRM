import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import LoginPage from "@/app/login/page";

const mocks = vi.hoisted(() => ({
  replace: vi.fn(),
  login: vi.fn(),
  auth: { session: null, loading: false } as Record<string, unknown>,
}));

vi.mock("next/navigation", () => ({ useRouter: () => ({ replace: mocks.replace }) }));
vi.mock("next/link", () => ({ default: ({ href, children, ...props }: React.AnchorHTMLAttributes<HTMLAnchorElement> & { href: string }) => <a href={href} {...props}>{children}</a> }));
vi.mock("@/components/auth-frame", () => ({ AuthFrame: ({ children }: { children: React.ReactNode }) => <main>{children}</main> }));
vi.mock("@/components/auth-provider", () => ({ useAuth: () => ({ ...mocks.auth, login: mocks.login }) }));

describe("login form", () => {
  beforeEach(() => {
    mocks.auth = { session: null, loading: false };
    window.history.replaceState({}, "", "/login");
  });

  it("uses native validation and does not submit incomplete credentials", async () => {
    const user = userEvent.setup();
    render(<LoginPage />);
    await user.click(screen.getByRole("button", { name: "Sign in" }));
    expect(mocks.login).not.toHaveBeenCalled();
    expect(screen.getByRole("textbox", { name: /^Organization ID/ })).toBeInvalid();
  });

  it("submits the organization-scoped credentials and navigates after login", async () => {
    const user = userEvent.setup();
    mocks.login.mockResolvedValue(undefined);
    render(<LoginPage />);

    await user.type(screen.getByRole("textbox", { name: /^Organization ID/ }), "northstar-realty");
    await user.type(screen.getByRole("textbox", { name: "Work email" }), "owner@example.com");
    await user.type(screen.getByLabelText("Password"), "Secure-password-42!");
    await user.click(screen.getByRole("button", { name: "Sign in" }));

    expect(mocks.login).toHaveBeenCalledWith({
      organization_slug: "northstar-realty",
      email: "owner@example.com",
      password: "Secure-password-42!",
    });
    expect(mocks.replace).toHaveBeenCalledWith("/dashboard");
  });
});
