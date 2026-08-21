"use client";

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
      <main className="center-page" aria-busy="true">
        <span className="spinner" />
        <span>Checking your session…</span>
      </main>
    );
  }

  if (permission && !permissionGranted(session?.user.permissions ?? [], permission)) {
    return <main className="center-page"><span>You do not have permission to view this page.</span></main>;
  }

  return children;
}
