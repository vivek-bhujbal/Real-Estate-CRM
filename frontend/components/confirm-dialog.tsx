"use client";

import { createContext, useCallback, useContext, useEffect, useRef, useState } from "react";

type ConfirmOptions = {
  title: string;
  message: string;
  confirmLabel?: string;
  tone?: "default" | "danger";
};

type PendingConfirmation = ConfirmOptions & {
  resolve: (confirmed: boolean) => void;
};

const ConfirmDialogContext = createContext<((options: ConfirmOptions) => Promise<boolean>) | null>(null);

export function ConfirmDialogProvider({ children }: { children: React.ReactNode }) {
  const [pending, setPending] = useState<PendingConfirmation | null>(null);
  const pendingRef = useRef<PendingConfirmation | null>(null);
  const cancelRef = useRef<HTMLButtonElement>(null);

  const confirm = useCallback((options: ConfirmOptions) => new Promise<boolean>((resolve) => {
    pendingRef.current?.resolve(false);
    const request = { ...options, resolve };
    pendingRef.current = request;
    setPending(request);
  }), []);

  const settle = useCallback((confirmed: boolean) => {
    const current = pendingRef.current;
    if (!current) return;
    pendingRef.current = null;
    setPending(null);
    current.resolve(confirmed);
  }, []);

  useEffect(() => {
    if (!pending) return;
    cancelRef.current?.focus();
    function onKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") {
        event.preventDefault();
        settle(false);
      }
    }
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, [pending, settle]);

  return (
    <ConfirmDialogContext.Provider value={confirm}>
      {children}
      {pending && (
        <div className="modal-backdrop confirm-backdrop" role="presentation" onMouseDown={(event) => {
          if (event.target === event.currentTarget) settle(false);
        }}>
          <section
            className="modal-card confirm-dialog"
            role="alertdialog"
            aria-modal="true"
            aria-labelledby="confirm-dialog-title"
            aria-describedby="confirm-dialog-description"
          >
            <div className={`confirm-dialog-icon ${pending.tone === "danger" ? "danger" : ""}`} aria-hidden="true">
              {pending.tone === "danger" ? "!" : "?"}
            </div>
            <div>
              <h2 id="confirm-dialog-title">{pending.title}</h2>
              <p id="confirm-dialog-description">{pending.message}</p>
            </div>
            <div className="modal-actions">
              <button ref={cancelRef} type="button" className="button button-secondary" onClick={() => settle(false)}>Cancel</button>
              <button
                type="button"
                className={`button ${pending.tone === "danger" ? "button-danger-solid" : "button-primary"}`}
                onClick={() => settle(true)}
              >
                {pending.confirmLabel ?? "Confirm"}
              </button>
            </div>
          </section>
        </div>
      )}
    </ConfirmDialogContext.Provider>
  );
}

export function useConfirmDialog() {
  const context = useContext(ConfirmDialogContext);
  if (!context) throw new Error("useConfirmDialog must be used within ConfirmDialogProvider");
  return context;
}
