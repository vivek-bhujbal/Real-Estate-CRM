"use client";

import { FormEvent, useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";

import { AuthFrame } from "@/components/auth-frame";
import { useAuth } from "@/components/auth-provider";
import { ApiError } from "@/lib/api";

export default function LoginPage() {
  const router = useRouter();
  const { login, session, loading } = useAuth();
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  useEffect(() => {
    if (!loading && session) router.replace("/dashboard");
  }, [loading, router, session]);

  useEffect(() => {
    const parameters = new URLSearchParams(window.location.search);
    let nextNotice: string | null = null;
    if (parameters.get("password-reset") === "success") {
      nextNotice = "Your password was reset. Sign in with your new password.";
    } else if (parameters.get("password-changed") === "success") {
      nextNotice = "Your password was changed. Sign in again on this device.";
    }
    if (parameters.size) window.history.replaceState({}, "", "/login");
    const timer = window.setTimeout(() => setNotice(nextNotice), 0);
    return () => window.clearTimeout(timer);
  }, []);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    setSubmitting(true);
    setError(null);
    try {
      await login({
        organization_slug: String(data.get("organization_slug")),
        email: String(data.get("email")),
        password: String(data.get("password"))
      });
      router.replace("/dashboard");
    } catch (reason) {
      setError(reason instanceof ApiError ? reason.message : "Unable to sign in right now");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <AuthFrame
      eyebrow="Welcome back"
      title="Sign in to your workspace"
      description="Use your organization identifier and work account."
      alternate={{ prompt: "Setting up a new company?", label: "Create a workspace", href: "/onboarding" }}
    >
      <form className="form-stack" onSubmit={submit}>
        {notice && <div className="alert alert-success" role="status">{notice}</div>}
        {error && <div className="alert alert-error" role="alert">{error}</div>}
        <label className="field">
          <span>Organization ID</span>
          <input name="organization_slug" autoComplete="organization" placeholder="e.g. northstar-realty" required minLength={3} />
          <small>The unique name chosen when your workspace was created.</small>
        </label>
        <label className="field">
          <span>Work email</span>
          <input name="email" type="email" autoComplete="email" placeholder="you@company.com" required />
        </label>
        <label className="field">
          <span>Password</span>
          <input name="password" type="password" autoComplete="current-password" required />
        </label>
        <div className="form-meta"><Link href="/forgot-password">Forgot your password?</Link></div>
        <button className="button button-primary" type="submit" disabled={submitting || loading}>
          {submitting ? "Signing in…" : "Sign in"}
        </button>
      </form>
    </AuthFrame>
  );
}
