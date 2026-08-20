"use client";

import { FormEvent, useState } from "react";
import { useRouter } from "next/navigation";

import { AppShell } from "@/components/app-shell";
import { useAuth } from "@/components/auth-provider";
import { ApiError } from "@/lib/api";

export default function AccountSecurityPage() {
  const router = useRouter();
  const { changePassword } = useAuth();
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

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
      await changePassword({
        current_password: String(data.get("current_password")),
        new_password: newPassword
      });
      router.replace("/login?password-changed=success");
    } catch (reason) {
      setError(reason instanceof ApiError ? reason.message : "Unable to change the password");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <AppShell>
      <main className="dashboard-content narrow-content">
        <div className="page-heading">
          <div>
            <p className="overline">Account security</p>
            <h1>Change your password</h1>
            <p>Changing your password signs this account out on every device.</p>
          </div>
        </div>
        <section className="panel security-panel">
          <form className="form-stack" onSubmit={submit}>
            {error && <div className="alert alert-error" role="alert">{error}</div>}
            <label className="field">
              <span>Current password</span>
              <input name="current_password" type="password" autoComplete="current-password" required />
            </label>
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
              {submitting ? "Changing password…" : "Change password"}
            </button>
          </form>
        </section>
      </main>
    </AppShell>
  );
}
