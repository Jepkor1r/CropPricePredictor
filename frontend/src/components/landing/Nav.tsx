import Link from "next/link";

import { ThemeToggle } from "@/components/ui/ThemeToggle";

export function Logo({ compact = false }: { compact?: boolean }) {
  return (
    <span className="flex items-center gap-2.5">
      <span
        aria-hidden
        className="grid size-8 place-items-center rounded-[10px] bg-brand-600 shadow-[var(--shadow-tile)]"
      >
        <svg viewBox="0 0 24 24" className="size-[18px]" fill="none" aria-hidden>
          <path
            d="M4 17.5c5.2 0 8-2.6 9.4-5.4M20 5.5c-6.6-1.2-11 1.3-12.4 4.2-1 2 .1 4 2.3 4.2 3 .3 5.9-2.2 6.4-5.1"
            stroke="#ffffff"
            strokeWidth="1.9"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
        </svg>
      </span>
      {!compact && (
        <span className="text-[16.5px] font-semibold tracking-[-0.02em]">PriceCast</span>
      )}
    </span>
  );
}

const LINKS = [
  { href: "#how", label: "How it works" },
  { href: "#accuracy", label: "Accuracy" },
  { href: "#delivery", label: "Delivery" },
  { href: "#data", label: "Data" },
];

export function Nav() {
  return (
    <header className="sticky top-0 z-50">
      <div className="glass hairline-b">
        <nav className="mx-auto flex h-16 max-w-6xl items-center justify-between gap-6 px-6">
          <Link href="/" className="shrink-0">
            <Logo />
          </Link>

          <ul className="hidden items-center gap-1 md:flex">
            {LINKS.map((l) => (
              <li key={l.href}>
                <a
                  href={l.href}
                  className="rounded-full px-3.5 py-2 text-[13.5px] font-medium text-[var(--text-secondary)] transition-colors hover:bg-[var(--surface-page)] hover:text-[var(--text-primary)]"
                >
                  {l.label}
                </a>
              </li>
            ))}
          </ul>

          <div className="flex items-center gap-2">
            <ThemeToggle />
            <Link
              href="/login"
              className="rounded-full bg-brand-600 px-4 py-2 text-[13.5px] font-semibold text-white transition-transform hover:bg-brand-700 active:scale-[0.97]"
            >
              Open dashboard
            </Link>
          </div>
        </nav>
      </div>
    </header>
  );
}
