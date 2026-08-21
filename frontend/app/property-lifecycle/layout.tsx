import { ProtectedRoute } from "@/components/protected-route";

export default function PropertyLifecycleLayout({ children }: { children: React.ReactNode }) {
  return <ProtectedRoute permission="possession.view">{children}</ProtectedRoute>;
}
