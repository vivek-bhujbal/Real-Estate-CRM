import { ProtectedRoute } from "@/components/protected-route";

export default function CustomersLayout({ children }: { children: React.ReactNode }) {
  return <ProtectedRoute permission="customers.view">{children}</ProtectedRoute>;
}
