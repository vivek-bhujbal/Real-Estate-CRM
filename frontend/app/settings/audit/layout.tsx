import { ProtectedRoute } from "@/components/protected-route";

export default function AuditLayout({ children }: { children: React.ReactNode }) {
  return <ProtectedRoute permission="audit.view">{children}</ProtectedRoute>;
}
