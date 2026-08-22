export default function Loading() {
  return (
    <main className="system-state" aria-live="polite" aria-busy="true">
      <span className="spinner" aria-hidden="true" />
      <p>Loading your workspace…</p>
    </main>
  );
}
