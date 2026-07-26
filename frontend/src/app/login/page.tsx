import Link from "next/link";

import { Logo } from "@/components/landing/Nav";
import { ThemeToggle } from "@/components/ui/ThemeToggle";

export const metadata = { title: "Sign in — PriceCast" };

/** Deliberately unauthenticated: this is a demo, and the button just routes
 *  through to the dashboard. Nothing here reads or stores a credential. */
export default function LoginPage() {
  return (
    <main className="relative isolate flex min-h-dvh flex-col items-center justify-center overflow-hidden px-6">
      <div aria-hidden className="pointer-events-none absolute inset-0 -z-10">
        <div className="absolute top-[-16rem] left-1/2 size-[46rem] -translate-x-1/2 rounded-full bg-brand-300/25 blur-[110px] dark:bg-brand-700/25" />
      </div>

      <div className="absolute top-6 right-6">
        <ThemeToggle />
      </div>

      <div className="w-full max-w-[400px]">
        <div className="flex justify-center">
          <Link href="/" aria-label="PriceCast home">
            <Logo />
          </Link>
        </div>

        <div className="hairline mt-8 rounded-[28px] bg-[var(--surface-raised)] p-8 shadow-[var(--shadow-lift)]">
          <h1 className="text-title text-center text-[24px]">Welcome back</h1>
          <p className="mt-2 text-center text-[14px] leading-relaxed text-[var(--text-secondary)]">
            Sign in to view forecasts, accuracy and coverage for every market.
          </p>

          <div className="mt-7 space-y-3">
            <label className="block">
              <span className="text-[12.5px] font-medium text-[var(--text-secondary)]">Email</span>
              <input
                type="email"
                defaultValue="demo@pricecast.co.ke"
                readOnly
                className="hairline mt-1.5 w-full rounded-xl bg-[var(--surface-page)] px-3.5 py-2.5 text-[14.5px] text-[var(--text-primary)]"
              />
            </label>
            <label className="block">
              <span className="text-[12.5px] font-medium text-[var(--text-secondary)]">Password</span>
              <input
                type="password"
                defaultValue="demo-account"
                readOnly
                className="hairline mt-1.5 w-full rounded-xl bg-[var(--surface-page)] px-3.5 py-2.5 text-[14.5px] text-[var(--text-primary)]"
              />
            </label>
          </div>

          <Link
            href="/dashboard"
            className="mt-6 flex w-full items-center justify-center rounded-full bg-brand-600 px-6 py-3 text-[15px] font-semibold text-white transition-all hover:bg-brand-700 active:scale-[0.985]"
          >
            Sign in
          </Link>

          <p className="mt-4 text-center text-[12px] leading-relaxed text-[var(--text-muted)]">
            Demo build — no account is created and nothing is sent anywhere. The button
            opens the dashboard directly.
          </p>
        </div>

        <p className="mt-6 text-center text-[13px]">
          <Link href="/" className="text-[var(--text-secondary)] hover:text-[var(--text-primary)]">
            ← Back to the overview
          </Link>
        </p>
      </div>
    </main>
  );
}
