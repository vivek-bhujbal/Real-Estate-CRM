import { ProtectedRoute } from "@/components/protected-route";

export default function RentalsLayout({ children }: { children: React.ReactNode }) {
  return <ProtectedRoute permission="properties.view">{children}</ProtectedRoute>;
}
