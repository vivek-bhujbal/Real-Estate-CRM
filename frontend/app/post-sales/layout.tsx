import { ProtectedRoute } from "@/components/protected-route";

export default function PostSalesLayout({ children }: { children: React.ReactNode }) {
  return <ProtectedRoute permission="bookings.view">{children}</ProtectedRoute>;
}
