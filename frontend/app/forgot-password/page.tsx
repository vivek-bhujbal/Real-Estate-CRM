"use client";

import { FormEvent, useState } from "react";

import { AuthFrame } from "@/components/auth-frame";
import { apiRequest, ApiError, MessageResponse } from "@/lib/api";

export default function ForgotPasswordPage() {
  const [submitting, setSubmitting] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    setSubmitting(true);
    setError(null);
    try {
      const response = await apiRequest<MessageResponse>(
        "/auth/forgot-password",
        {
          method: "POST",
          body: JSON.stringify({
            organization_slug: String(data.get("organization_slug")),
            email: String(data.get("email"))
          })
        },
        { authenticated: false, retryAuthentication: false }
      );
      setMessage(response.message);
      event.currentTarget.reset();
    } catch (reason) {
      setError(reason instanceof ApiError ? reason.message : "Unable to request a reset right now");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <AuthFrame
      eyebrow="Account recovery"
      title="Reset your password"
      description="Enter your workspace and work email. We will send a one-time reset link if the account exists."
      alternate={{ prompt: "Remembered your password?", label: "Return to sign in", href: "/login" }}
    >
      <form className="form-stack" onSubmit={submit}>
        {message && <div className="alert alert-success" role="status">{message}</div>}
        {error && <div className="alert alert-error" role="alert">{error}</div>}
        <label className="field">
          <span>Organization ID</span>
          <input name="organization_slug" autoComplete="organization" required minLength={3} />
        </label>
        <label className="field">
          <span>Work email</span>
          <input name="email" type="email" autoComplete="email" required />
        </label>
        <button className="button button-primary" type="submit" disabled={submitting}>
          {submitting ? "Sending instructions…" : "Send reset instructions"}
        </button>
      </form>
    </AuthFrame>
  );
}
