"use client";

import { useEffect } from "react";

const focusableSelector = [
  "a[href]",
  "button:not([disabled])",
  "input:not([disabled])",
  "select:not([disabled])",
  "textarea:not([disabled])",
  "[tabindex]:not([tabindex='-1'])"
].join(",");

export function ModalAccessibility() {
  useEffect(() => {
    let activeDialog: HTMLElement | null = null;
    let previousFocus: HTMLElement | null = null;

    function enhancePageSemantics() {
      document.querySelectorAll<HTMLElement>(".alert-error:not([role])").forEach((item) => item.setAttribute("role", "alert"));
      document.querySelectorAll<HTMLElement>(".alert-success:not([role])").forEach((item) => item.setAttribute("role", "status"));
      document.querySelectorAll<HTMLElement>(".center-inline:has(.spinner), .customer-empty:has(.spinner)").forEach((item) => {
        item.setAttribute("role", "status");
        item.setAttribute("aria-live", "polite");
      });
      document.querySelectorAll<HTMLElement>("[role='table']").forEach((table) => {
        table.querySelectorAll<HTMLElement>(":scope > [role='row']").forEach((row) => {
          row.querySelectorAll<HTMLElement>(":scope > span").forEach((cell) => {
            cell.setAttribute("role", row.classList.contains("data-head") ? "columnheader" : "cell");
          });
        });
      });
      const tableSelector = ".data-table, .approval-table, .audit-table, .booking-table, .collection-table, .detail-line-table, .document-table, .hold-table, .inventory-table, .lifecycle-table, .partner-table, .post-sales-table, .quote-table, .rental-table, .service-table, .unit-admin-table, .visit-table";
      document.querySelectorAll<HTMLElement>(".data-card").forEach((card) => {
        const table = card.querySelector<HTMLElement>(tableSelector);
        if (!table) return;
        card.tabIndex = 0;
        card.setAttribute("role", "region");
        card.setAttribute("aria-label", table.getAttribute("aria-label") ?? "Scrollable data table");
      });
      document.querySelectorAll<HTMLElement>(".configuration-tabs, .detail-tabs, .post-sales-tabs, .customer-tabs").forEach((tabs) => {
        const buttons = Array.from(tabs.querySelectorAll<HTMLButtonElement>(":scope > button"));
        if (!buttons.length) return;
        tabs.setAttribute("role", "tablist");
        if (!tabs.hasAttribute("aria-label")) tabs.setAttribute("aria-label", "Page sections");
        buttons.forEach((button) => {
          const selected = button.classList.contains("active");
          button.setAttribute("role", "tab");
          button.setAttribute("aria-selected", String(selected));
          button.tabIndex = selected ? 0 : -1;
        });
        if (tabs.dataset.keyboardTabs === "true") return;
        tabs.dataset.keyboardTabs = "true";
        tabs.addEventListener("keydown", (event) => {
          if (!(event instanceof KeyboardEvent) || !["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) return;
          const currentButtons = Array.from(tabs.querySelectorAll<HTMLButtonElement>(":scope > button"));
          const current = currentButtons.indexOf(document.activeElement as HTMLButtonElement);
          if (current < 0) return;
          event.preventDefault();
          const target = event.key === "Home" ? 0 : event.key === "End" ? currentButtons.length - 1 : event.key === "ArrowRight" ? (current + 1) % currentButtons.length : (current - 1 + currentButtons.length) % currentButtons.length;
          currentButtons[target]?.focus();
          currentButtons[target]?.click();
        });
      });
    }

    function activate() {
      const dialogs = document.querySelectorAll<HTMLElement>(".modal-backdrop .modal-card");
      const dialog = dialogs.item(dialogs.length - 1);
      if (!dialog || dialog === activeDialog) return;
      previousFocus = document.activeElement instanceof HTMLElement ? document.activeElement : null;
      activeDialog = dialog;
      if (!dialog.hasAttribute("role")) dialog.setAttribute("role", "dialog");
      if (!dialog.hasAttribute("aria-modal")) dialog.setAttribute("aria-modal", "true");
      dialog.setAttribute("tabindex", "-1");
      const heading = dialog.querySelector<HTMLElement>("h2");
      if (heading && !dialog.hasAttribute("aria-labelledby")) {
        if (!heading.id) heading.id = `dialog-title-${crypto.randomUUID()}`;
        dialog.setAttribute("aria-labelledby", heading.id);
      } else if (!dialog.hasAttribute("aria-labelledby") && !dialog.hasAttribute("aria-label")) {
        dialog.setAttribute("aria-label", "Dialog");
      }
      window.requestAnimationFrame(() => {
        (dialog.querySelector<HTMLElement>(focusableSelector) ?? dialog).focus();
      });
    }

    function onKeyDown(event: KeyboardEvent) {
      if (!activeDialog || !document.contains(activeDialog)) return;
      if (event.key === "Escape") {
        const close = activeDialog.querySelector<HTMLButtonElement>(".modal-heading .icon-button");
        if (close) {
          event.preventDefault();
          close.click();
        }
        return;
      }
      if (event.key !== "Tab") return;
      const focusable = Array.from(activeDialog.querySelectorAll<HTMLElement>(focusableSelector));
      if (!focusable.length) {
        event.preventDefault();
        activeDialog.focus();
        return;
      }
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    }

    const observer = new MutationObserver(() => {
      if (activeDialog && !document.contains(activeDialog)) {
        activeDialog = null;
        previousFocus?.focus();
        previousFocus = null;
      }
      enhancePageSemantics();
      activate();
    });
    observer.observe(document.body, { childList: true, subtree: true, attributes: true, attributeFilter: ["class"] });
    document.addEventListener("keydown", onKeyDown);
    enhancePageSemantics();
    activate();
    return () => {
      observer.disconnect();
      document.removeEventListener("keydown", onKeyDown);
    };
  }, []);

  return null;
}
