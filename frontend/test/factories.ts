import type { CurrentUser, Session } from "@/lib/api";

let sequence = 0;

export function userFactory(overrides: Partial<CurrentUser> = {}): CurrentUser {
  sequence += 1;
  return {
    id: `test-user-${sequence}`,
    email: `user-${sequence}@test.invalid`,
    full_name: `Test User ${sequence}`,
    organization_id: "test-organization",
    branch_id: null,
    department_id: null,
    is_active: true,
    created_at: "2026-01-01T00:00:00Z",
    organization: {
      id: "test-organization",
      name: "Isolated Test Organization",
      slug: "isolated-test-organization",
    },
    permissions: [],
    ...overrides,
  };
}

export function sessionFactory(user: Partial<CurrentUser> = {}): Session {
  return {
    access_token: "test-access-token",
    token_type: "bearer",
    expires_in: 900,
    user: userFactory(user),
  };
}
