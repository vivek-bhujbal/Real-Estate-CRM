"use client";

import { useEffect } from "react";

export default function ErrorBoundary({
  error,
  reset
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    // The digest is safe to correlate with server logs; do not render stack details.
    console.error("Unexpected page error", { digest: error.digest });
  }, [error]);

  return (
    <main className="system-state" aria-labelledby="page-error-title">
      <div className="system-state-mark" aria-hidden="true">!</div>
      <p className="overline">Something went wrong</p>
      <h1 id="page-error-title">This page could not be loaded</h1>
      <p>Your work may still be saved. Try loading the page again.</p>
      <div className="system-state-actions">
        <button className="button button-primary" type="button" onClick={reset}>
          Try again
        </button>
        <a className="button button-secondary" href="/dashboard">Return to dashboard</a>
      </div>
      {error.digest ? <small>Reference: {error.digest}</small> : null}
    </main>
  );
}
