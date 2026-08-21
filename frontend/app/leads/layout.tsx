import { ProtectedRoute } from "@/components/protected-route";

export default function LeadsLayout({ children }: { children: React.ReactNode }) {
  return <ProtectedRoute>{children}</ProtectedRoute>;
}
