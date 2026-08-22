import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { SettingsNavigation } from "@/components/settings-navigation";
import { sessionFactory } from "@/test/factories";

const mocks = vi.hoisted(() => ({
  pathname: "/settings/users",
  auth: { session: null } as Record<string, unknown>,
}));

vi.mock("next/navigation", () => ({ usePathname: () => mocks.pathname }));
vi.mock("next/link", () => ({ default: ({ href, children, ...props }: React.AnchorHTMLAttributes<HTMLAnchorElement> & { href: string }) => <a href={href} {...props}>{children}</a> }));
vi.mock("@/components/auth-provider", () => ({ useAuth: () => mocks.auth }));

describe("SettingsNavigation", () => {
  it("renders only permitted destinations and marks the current page", () => {
    mocks.auth = { session: sessionFactory({ permissions: ["users.view", "audit.manage"] }) };
    render(<SettingsNavigation />);

    expect(screen.getByRole("link", { name: "Users" })).toHaveClass("active");
    expect(screen.getByRole("link", { name: "Audit trail" })).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Roles" })).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Organization" })).not.toBeInTheDocument();
  });
});
