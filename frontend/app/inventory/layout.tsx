import { ProtectedRoute } from "@/components/protected-route";

export default function InventoryLayout({ children }: { children: React.ReactNode }) {
  return <ProtectedRoute permission="inventory.view">{children}</ProtectedRoute>;
}
