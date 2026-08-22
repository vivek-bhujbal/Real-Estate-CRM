import type { Metadata } from "next";
import { connection } from "next/server";

import { AuthProvider } from "@/components/auth-provider";
import { ConfirmDialogProvider } from "@/components/confirm-dialog";

import "./globals.css";

export const metadata: Metadata = {
  title: { default: "EstateOps", template: "%s · EstateOps" },
  description: "Real estate CRM and revenue operations platform",
  robots: { index: false, follow: false }
};

export default async function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  // Nonce-based CSP requires request-time rendering so Next can attach the proxy nonce.
  await connection();
  return (
    <html lang="en">
      <body>
        <AuthProvider><ConfirmDialogProvider>{children}</ConfirmDialogProvider></AuthProvider>
      </body>
    </html>
  );
}

