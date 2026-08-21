import { ProtectedRoute } from "@/components/protected-route";

export default function BookingsLayout({ children }: { children: React.ReactNode }) {
  return <ProtectedRoute permission="bookings.view">{children}</ProtectedRoute>;
}
