"use client";

import { FormEvent, useMemo, useState } from "react";
import { useRouter } from "next/navigation";

import { AuthFrame } from "@/components/auth-frame";
import { useAuth } from "@/components/auth-provider";
import { ApiError } from "@/lib/api";

function toSlug(value: string): string {
  return value.toLowerCase().trim().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "").slice(0, 80);
}

export default function OnboardingPage() {
  const router = useRouter();
  const { register } = useAuth();
  const [organizationName, setOrganizationName] = useState("");
  const suggestedSlug = useMemo(() => toSlug(organizationName), [organizationName]);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    setSubmitting(true);
    setError(null);
    try {
      await register({
        organization_name: String(data.get("organization_name")),
        organization_slug: String(data.get("organization_slug")),
        admin_full_name: String(data.get("admin_full_name")),
        admin_email: String(data.get("admin_email")),
        password: String(data.get("password"))
      });
      router.replace("/dashboard");
    } catch (reason) {
      setError(reason instanceof ApiError ? reason.message : "Unable to create the workspace");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <AuthFrame
      eyebrow="New workspace"
      title="Set up your organization"
      description="Create a clean workspace with no sample records. You will be its first administrator."
      alternate={{ prompt: "Already have a workspace?", label: "Sign in", href: "/login" }}
    >
      <form className="form-stack" onSubmit={submit}>
        {error && <div className="alert alert-error" role="alert">{error}</div>}
        <div className="field-row">
          <label className="field">
            <span>Organization name</span>
            <input name="organization_name" autoComplete="organization" value={organizationName} onChange={(event) => setOrganizationName(event.target.value)} required minLength={2} />
          </label>
          <label className="field">
            <span>Organization ID</span>
            <input key={suggestedSlug} name="organization_slug" defaultValue={suggestedSlug} pattern="[a-z0-9]+(?:-[a-z0-9]+)*" required minLength={3} />
          </label>
        </div>
        <label className="field">
          <span>Your full name</span>
          <input name="admin_full_name" autoComplete="name" required minLength={2} />
        </label>
        <label className="field">
          <span>Work email</span>
          <input name="admin_email" type="email" autoComplete="email" required />
        </label>
        <label className="field">
          <span>Password</span>
          <input name="password" type="password" autoComplete="new-password" required minLength={12} aria-describedby="password-help" />
          <small id="password-help">At least 12 characters with upper, lower, number, and symbol.</small>
        </label>
        <button className="button button-primary" type="submit" disabled={submitting}>
          {submitting ? "Creating workspace…" : "Create workspace"}
        </button>
      </form>
    </AuthFrame>
  );
}

