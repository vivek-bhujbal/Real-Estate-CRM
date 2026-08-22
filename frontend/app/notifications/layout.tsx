import { ProtectedRoute } from "@/components/protected-route";

export default function NotificationsLayout({ children }: { children: React.ReactNode }) {
  return <ProtectedRoute permission="notifications.view">{children}</ProtectedRoute>;
}
