import { ProtectedRoute } from "@/components/protected-route";

export default function ProjectsLayout({ children }: { children: React.ReactNode }) {
  return <ProtectedRoute permission="projects.view">{children}</ProtectedRoute>;
}
