import Link from "next/link";

export default function NotFound() {
  return (
    <main className="system-state" aria-labelledby="not-found-title">
      <div className="system-state-mark" aria-hidden="true">404</div>
      <p className="overline">Page not found</p>
      <h1 id="not-found-title">That address does not exist</h1>
      <p>The page may have moved, or you may not have access to it.</p>
      <div className="system-state-actions">
        <Link className="button button-primary" href="/dashboard">Go to dashboard</Link>
        <Link className="button button-secondary" href="/login">Go to sign in</Link>
      </div>
    </main>
  );
}
