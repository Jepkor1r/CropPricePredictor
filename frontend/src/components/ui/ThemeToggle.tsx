"use client";

import { useCallback, useSyncExternalStore } from "react";

type Theme = "light" | "dark";

/** The theme lives on <html data-theme>, stamped before paint by the inline
 *  script in layout.tsx. Subscribing to that attribute keeps this component a
 *  reader of external state rather than a second source of truth. */
function subscribe(onChange: () => void) {
  const observer = new MutationObserver(onChange);
  observer.observe(document.documentElement, {
    attributes: true,
    attributeFilter: ["data-theme"],
  });
  return () => observer.disconnect();
}

const getSnapshot = (): Theme =>
  document.documentElement.getAttribute("data-theme") === "dark" ? "dark" : "light";

// The server can't know the visitor's theme; React re-reads after hydration.
const getServerSnapshot = (): Theme => "light";

export function ThemeToggle({ className }: { className?: string }) {
  const theme = useSyncExternalStore(subscribe, getSnapshot, getServerSnapshot);

  const toggle = useCallback(() => {
    const next: Theme = getSnapshot() === "dark" ? "light" : "dark";
    document.documentElement.setAttribute("data-theme", next);
    try {
      localStorage.setItem("pricecast-theme", next);
    } catch {
      /* private mode — the attribute still applies for this session */
    }
  }, []);

  return (
    <button
      type="button"
      onClick={toggle}
      aria-label={theme === "dark" ? "Switch to light theme" : "Switch to dark theme"}
      className={`hairline grid size-9 place-items-center rounded-full bg-[var(--surface-raised)] text-[var(--text-secondary)] transition-colors hover:text-[var(--text-primary)] ${className ?? ""}`}
    >
      {theme === "dark" ? (
        <svg viewBox="0 0 20 20" className="size-4" aria-hidden fill="currentColor">
          <path d="M10 3.5a1 1 0 0 1 1 1V5a1 1 0 1 1-2 0v-.5a1 1 0 0 1 1-1Zm0 10a3.5 3.5 0 1 0 0-7 3.5 3.5 0 0 0 0 7Zm0 1.5a1 1 0 0 1 1 1v.5a1 1 0 1 1-2 0V16a1 1 0 0 1 1-1Zm6-5a1 1 0 0 1-1 1h-.5a1 1 0 1 1 0-2h.5a1 1 0 0 1 1 1Zm-10.5 1a1 1 0 1 0 0-2H5a1 1 0 1 0 0 2h.5Zm8.68-5.18a1 1 0 0 1 0 1.41l-.36.36a1 1 0 1 1-1.41-1.42l.35-.35a1 1 0 0 1 1.42 0ZM7.09 12.91a1 1 0 0 1 0 1.42l-.35.35a1 1 0 0 1-1.42-1.41l.36-.36a1 1 0 0 1 1.41 0Zm7.09 1.77a1 1 0 0 1-1.42 0l-.35-.35a1 1 0 0 1 1.41-1.42l.36.36a1 1 0 0 1 0 1.41ZM7.09 7.09a1 1 0 0 1-1.41 0l-.36-.36A1 1 0 0 1 6.74 5.32l.35.35a1 1 0 0 1 0 1.42Z" />
        </svg>
      ) : (
        <svg viewBox="0 0 20 20" className="size-4" aria-hidden fill="currentColor">
          <path d="M16.3 12.3A6.8 6.8 0 0 1 7.7 3.7a.8.8 0 0 0-1-1 8.3 8.3 0 1 0 10.6 10.6.8.8 0 0 0-1-1Z" />
        </svg>
      )}
    </button>
  );
}
