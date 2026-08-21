import { ProtectedRoute } from "@/components/protected-route";

export default function PartnersLayout({ children }: { children: React.ReactNode }) {
  return <ProtectedRoute permission="partners.view">{children}</ProtectedRoute>;
}
