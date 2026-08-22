import { ProtectedRoute } from "@/components/protected-route";

export default function DashboardLayout({ children }: { children: React.ReactNode }) {
  return <ProtectedRoute permission="dashboard.view">{children}</ProtectedRoute>;
}
