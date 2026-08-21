import { ProtectedRoute } from "@/components/protected-route";

export default function DocumentsLayout({ children }: { children: React.ReactNode }) {
  return <ProtectedRoute permission="documents.view">{children}</ProtectedRoute>;
}
