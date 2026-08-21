import { ProtectedRoute } from "@/components/protected-route";

export default function CollectionsLayout({ children }: { children: React.ReactNode }) {
  return <ProtectedRoute permission="collections.view">{children}</ProtectedRoute>;
}
