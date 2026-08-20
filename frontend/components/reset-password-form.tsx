"use client";

import { FormEvent, useEffect, useState } from "react";
import { useRouter } from "next/navigation";

import { AuthFrame } from "@/components/auth-frame";
import { apiRequest, ApiError, MessageResponse } from "@/lib/api";

export function ResetPasswordForm() {
  const router = useRouter();
  const [token, setToken] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const fragment = new URLSearchParams(window.location.hash.slice(1));
    const resetToken = fragment.get("token") ?? "";
    window.history.replaceState({}, "", "/reset-password");
    const timer = window.setTimeout(() => setToken(resetToken), 0);
    return () => window.clearTimeout(timer);
  }, []);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    const newPassword = String(data.get("new_password"));
    if (newPassword !== String(data.get("confirm_password"))) {
      setError("The new passwords do not match");
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      await apiRequest<MessageResponse>(
        "/auth/reset-password",
        { method: "POST", body: JSON.stringify({ token, new_password: newPassword }) },
        { authenticated: false, retryAuthentication: false }
      );
      router.replace("/login?password-reset=success");
    } catch (reason) {
      setError(reason instanceof ApiError ? reason.message : "Unable to reset the password");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <AuthFrame
      eyebrow="Secure reset"
      title="Choose a new password"
      description="This one-time link will be consumed when your password is changed. All existing sessions will be signed out."
      alternate={{ prompt: "No longer need to reset?", label: "Return to sign in", href: "/login" }}
    >
      {token === null ? (
        <div className="center-inline" aria-busy="true"><span className="spinner" />Checking reset link…</div>
      ) : !token ? (
        <div className="alert alert-error" role="alert">This password reset link is invalid or incomplete.</div>
      ) : (
        <form className="form-stack" onSubmit={submit}>
          {error && <div className="alert alert-error" role="alert">{error}</div>}
          <label className="field">
            <span>New password</span>
            <input name="new_password" type="password" autoComplete="new-password" required minLength={12} />
            <small>At least 12 characters with upper, lower, number, and symbol.</small>
          </label>
          <label className="field">
            <span>Confirm new password</span>
            <input name="confirm_password" type="password" autoComplete="new-password" required minLength={12} />
          </label>
          <button className="button button-primary" type="submit" disabled={submitting}>
            {submitting ? "Resetting password…" : "Reset password"}
          </button>
        </form>
      )}
    </AuthFrame>
  );
}
