"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";

import {
  apiRequest,
  refreshSession,
  Session,
  setApiSession,
  subscribeToApiSession
} from "@/lib/api";

type LoginValues = { organization_slug: string; email: string; password: string };
type RegistrationValues = {
  organization_name: string;
  organization_slug: string;
  admin_full_name: string;
  admin_email: string;
  password: string;
};
type PasswordChangeValues = { current_password: string; new_password: string };
type AuthStatus = "loading" | "authenticated" | "unauthenticated";
type AuthContextValue = {
  session: Session | null;
  status: AuthStatus;
  loading: boolean;
  login(values: LoginValues): Promise<void>;
  register(values: RegistrationValues): Promise<void>;
  changePassword(values: PasswordChangeValues): Promise<void>;
  logout(): Promise<void>;
};

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [session, setSession] = useState<Session | null>(null);
  const [status, setStatus] = useState<AuthStatus>("loading");

  useEffect(() => {
    const unsubscribe = subscribeToApiSession((next) => {
      setSession(next);
      setStatus(next ? "authenticated" : "unauthenticated");
    });
    void refreshSession().catch(() => {
      // The transport already clears the in-memory session on refresh failure.
    });
    return unsubscribe;
  }, []);

  useEffect(() => {
    if (!session) return;
    const refreshInMilliseconds = Math.max((session.expires_in - 60) * 1000, 5_000);
    const timer = window.setTimeout(() => {
      void refreshSession().catch(() => {
        // Session listeners transition the application to unauthenticated.
      });
    }, refreshInMilliseconds);
    return () => window.clearTimeout(timer);
  }, [session]);

  const login = useCallback(async (values: LoginValues) => {
    const next = await apiRequest<Session>(
      "/auth/login",
      { method: "POST", body: JSON.stringify(values) },
      { authenticated: false, retryAuthentication: false }
    );
    setApiSession(next);
  }, []);

  const register = useCallback(async (values: RegistrationValues) => {
    const next = await apiRequest<Session>(
      "/auth/register-organization",
      { method: "POST", body: JSON.stringify(values) },
      { authenticated: false, retryAuthentication: false }
    );
    setApiSession(next);
  }, []);

  const changePassword = useCallback(async (values: PasswordChangeValues) => {
    await apiRequest<void>("/auth/change-password", {
      method: "POST",
      body: JSON.stringify(values)
    });
    setApiSession(null);
  }, []);

  const logout = useCallback(async () => {
    try {
      await apiRequest<void>("/auth/logout", { method: "POST" });
    } finally {
      setApiSession(null);
    }
  }, []);

  const value = useMemo(
    () => ({
      session,
      status,
      loading: status === "loading",
      login,
      register,
      changePassword,
      logout
    }),
    [session, status, login, register, changePassword, logout]
  );
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const value = useContext(AuthContext);
  if (!value) throw new Error("useAuth must be used inside AuthProvider");
  return value;
}
