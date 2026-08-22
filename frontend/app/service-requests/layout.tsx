import { ProtectedRoute } from "@/components/protected-route";

export default function ServiceRequestsLayout({ children }: { children: React.ReactNode }) {
  return <ProtectedRoute permission="service_requests.view">{children}</ProtectedRoute>;
}
