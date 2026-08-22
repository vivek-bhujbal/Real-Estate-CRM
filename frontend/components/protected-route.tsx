"use client";

import Link from "next/link";
import { useEffect } from "react";
import { useRouter } from "next/navigation";

import { useAuth } from "@/components/auth-provider";
import { permissionGranted } from "@/lib/api";

export function ProtectedRoute({ children, permission }: { children: React.ReactNode; permission?: string }) {
  const router = useRouter();
  const { status, session } = useAuth();

  useEffect(() => {
    if (status === "unauthenticated") router.replace("/login");
  }, [router, status]);

  if (status !== "authenticated") {
    return (
      <main className="center-page state-page" aria-busy="true" aria-live="polite">
        <span className="spinner" />
        <span>Checking your session…</span>
      </main>
    );
  }

  if (permission && !permissionGranted(session?.user.permissions ?? [], permission)) {
    return <main className="center-page state-page"><div className="state-card"><span className="state-card-icon" aria-hidden="true">!</span><p className="overline">Access restricted</p><h1>This workspace is not available</h1><p>Your role does not include the permission required for this page.</p><Link className="button button-secondary" href="/dashboard">Return to overview</Link></div></main>;
  }

  return children;
}
