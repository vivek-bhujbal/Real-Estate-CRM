"use client";

export default function GlobalError({ reset }: { error: Error; reset: () => void }) {
  return (
    <html lang="en">
      <body>
        <main className="system-state" aria-labelledby="global-error-title">
          <div className="system-state-mark" aria-hidden="true">!</div>
          <p className="overline">Application error</p>
          <h1 id="global-error-title">EstateOps needs to reload</h1>
          <p>An unexpected error interrupted the application.</p>
          <button className="button button-primary" type="button" onClick={reset}>
            Reload application
          </button>
        </main>
      </body>
    </html>
  );
}
