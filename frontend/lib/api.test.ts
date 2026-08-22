import { afterEach, describe, expect, it, vi } from "vitest";

import { apiRequest, permissionGranted, setApiSession } from "@/lib/api";
import { sessionFactory } from "@/test/factories";

afterEach(() => {
  setApiSession(null);
  vi.unstubAllGlobals();
});

describe("permissionGranted", () => {
  it("accepts an exact permission or the module manage permission", () => {
    expect(permissionGranted(["leads.create"], "leads.create")).toBe(true);
    expect(permissionGranted(["leads.manage"], "leads.delete")).toBe(true);
    expect(permissionGranted(["customers.manage"], "leads.view")).toBe(false);
    expect(permissionGranted(["leads.manage"], "malformed")).toBe(false);
  });
});

describe("authenticated API transport", () => {
  it("sends the access token and retries once after a successful refresh", async () => {
    const initial = sessionFactory();
    const refreshed = { ...initial, access_token: "rotated-test-token" };
    setApiSession(initial);
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(new Response(JSON.stringify({ error: { code: "TOKEN_EXPIRED" } }), {
        status: 401,
        headers: { "Content-Type": "application/json" },
      }))
      .mockResolvedValueOnce(new Response(JSON.stringify(refreshed), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ id: "lead-1" }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }));
    vi.stubGlobal("fetch", fetchMock);

    await expect(apiRequest<{ id: string }>("/leads/lead-1")).resolves.toEqual({ id: "lead-1" });

    expect(fetchMock).toHaveBeenCalledTimes(3);
    const firstHeaders = new Headers(fetchMock.mock.calls[0][1].headers);
    const refreshHeaders = new Headers(fetchMock.mock.calls[1][1].headers);
    const retryHeaders = new Headers(fetchMock.mock.calls[2][1].headers);
    expect(firstHeaders.get("Authorization")).toBe("Bearer test-access-token");
    expect(refreshHeaders.get("Authorization")).toBeNull();
    expect(retryHeaders.get("Authorization")).toBe("Bearer rotated-test-token");
  });
});
