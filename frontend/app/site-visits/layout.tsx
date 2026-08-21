import { ProtectedRoute } from "@/components/protected-route";

export default function SiteVisitsLayout({ children }: { children: React.ReactNode }) {
  return <ProtectedRoute permission="visits.view">{children}</ProtectedRoute>;
}
