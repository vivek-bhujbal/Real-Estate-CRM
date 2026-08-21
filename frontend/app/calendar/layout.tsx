import { ProtectedRoute } from "@/components/protected-route";

export default function CalendarLayout({ children }: { children: React.ReactNode }) {
  return <ProtectedRoute permission="visits.view">{children}</ProtectedRoute>;
}
