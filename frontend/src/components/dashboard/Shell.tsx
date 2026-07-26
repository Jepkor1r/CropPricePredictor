"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import type { ReactNode } from "react";

import { Logo } from "@/components/landing/Nav";
import { ThemeToggle } from "@/components/ui/ThemeToggle";
import { cx } from "@/lib/format";

const NAV = [
  {
    href: "/dashboard",
    label: "Overview",
    icon: "M3 10.5 10 4l7 6.5M5 9.5V16h10V9.5",
  },
  {
    href: "/dashboard/forecasts",
    label: "Forecasts",
    icon: "M3 14.5 7.5 9l3.5 3.5L17 5.5M17 5.5h-4M17 5.5v4",
  },
  {
    href: "/dashboard/accuracy",
    label: "Accuracy",
    icon: "M4 16V9m6 7V5m6 11v-4",
  },
  {
    href: "/dashboard/coverage",
    label: "Coverage",
    icon: "M4 5h12M4 10h12M4 15h7",
  },
  {
    href: "/dashboard/messages",
    label: "Messages",
    icon: "M3 6.5A2 2 0 0 1 5 4.5h10a2 2 0 0 1 2 2v6a2 2 0 0 1-2 2H8l-4 3v-3a2 2 0 0 1-1-1.7Z",
  },
];

function NavLinks({ horizontal = false }: { horizontal?: boolean }) {
  const pathname = usePathname();
  return (
    <ul className={horizontal ? "flex min-w-max gap-1.5" : "space-y-1"}>
      {NAV.map((item) => {
        const active =
          item.href === "/dashboard" ? pathname === item.href : pathname.startsWith(item.href);
        return (
          <li key={item.href}>
            <Link
              href={item.href}
              aria-current={active ? "page" : undefined}
              className={cx(
                "flex items-center gap-3 rounded-xl px-3 py-2.5 text-[14px] font-medium whitespace-nowrap transition-colors",
                active
                  ? "bg-brand-600 text-white"
                  : "text-[var(--text-secondary)] hover:bg-[var(--surface-page)] hover:text-[var(--text-primary)]",
              )}
            >
              <svg viewBox="0 0 20 20" className="size-[18px] shrink-0" aria-hidden fill="none">
                <path
                  d={item.icon}
                  stroke="currentColor"
                  strokeWidth="1.7"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                />
              </svg>
              {item.label}
            </Link>
          </li>
        );
      })}
    </ul>
  );
}

export function DashboardShell({
  children,
  generatedAt,
}: {
  children: ReactNode;
  generatedAt: string;
}) {
  return (
    <div className="flex min-h-dvh flex-col lg:flex-row">
      {/* Desktop rail */}
      <aside className="hairline-b sticky top-0 z-40 hidden w-[248px] shrink-0 flex-col border-r bg-[var(--surface-raised)] px-4 py-6 lg:flex lg:h-dvh lg:border-b-0">
        <Link href="/" className="px-2">
          <Logo />
        </Link>
        <nav className="mt-8 flex-1">
          <NavLinks />
        </nav>
        <div className="hairline-t px-2 pt-4">
          <p className="text-[11.5px] leading-relaxed text-[var(--text-muted)]">
            Reading the same SQLite tables the pipeline writes.
            <br />
            Snapshot {generatedAt.slice(0, 10)}.
          </p>
        </div>
      </aside>

      {/* Mobile bar */}
      <div className="glass hairline-b sticky top-0 z-40 lg:hidden">
        <div className="flex h-14 items-center justify-between px-4">
          <Link href="/">
            <Logo />
          </Link>
          <ThemeToggle />
        </div>
        <nav className="overflow-x-auto px-3 pb-3">
          <NavLinks horizontal />
        </nav>
      </div>

      <div className="min-w-0 flex-1">
        <div className="glass hairline-b sticky top-0 z-30 hidden lg:block">
          <div className="flex h-16 items-center justify-end gap-3 px-8">
            <span className="hairline rounded-full px-3 py-1 text-[12.5px] text-[var(--text-secondary)]">
              Demo account
            </span>
            <ThemeToggle />
          </div>
        </div>
        <main className="px-5 py-7 sm:px-8 lg:py-9">{children}</main>
      </div>
    </div>
  );
}

export function PageHeading({
  title,
  description,
}: {
  title: string;
  description: string;
}) {
  return (
    <div className="mb-7 max-w-3xl">
      <h1 className="text-title text-[clamp(1.6rem,3vw,2.1rem)]">{title}</h1>
      <p className="mt-2.5 text-[14.5px] leading-relaxed text-[var(--text-secondary)]">
        {description}
      </p>
    </div>
  );
}
