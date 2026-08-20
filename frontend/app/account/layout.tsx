import { ProtectedRoute } from "@/components/protected-route";

export default function AccountLayout({ children }: { children: React.ReactNode }) {
  return <ProtectedRoute>{children}</ProtectedRoute>;
}
