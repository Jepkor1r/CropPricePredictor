import type { ReactNode } from "react";

import { cx } from "@/lib/format";
import type { Confidence, Tier } from "@/lib/types";

export function Card({
  children,
  className,
  as: Tag = "div",
}: {
  children: ReactNode;
  className?: string;
  as?: "div" | "section" | "article";
}) {
  return (
    <Tag
      className={cx(
        "hairline rounded-[var(--radius-card)] bg-[var(--surface-raised)] shadow-[var(--shadow-tile)]",
        className,
      )}
    >
      {children}
    </Tag>
  );
}

export function CardHeader({
  title,
  subtitle,
  right,
}: {
  title: string;
  subtitle?: string;
  right?: ReactNode;
}) {
  return (
    <div className="flex items-start justify-between gap-4 px-6 pt-5 pb-4">
      <div className="min-w-0">
        <h3 className="text-title text-[15px] text-[var(--text-primary)]">{title}</h3>
        {subtitle ? (
          <p className="mt-1 text-[13px] leading-relaxed text-[var(--text-secondary)]">{subtitle}</p>
        ) : null}
      </div>
      {right ? <div className="shrink-0">{right}</div> : null}
    </div>
  );
}

/** Stat tile: label · value · optional delta. Value uses proportional
 *  figures — tabular-nums is reserved for columns that align vertically. */
export function StatTile({
  label,
  value,
  hint,
  accent = false,
}: {
  label: string;
  value: string;
  hint?: string;
  accent?: boolean;
}) {
  return (
    <div
      className={cx(
        "hairline rounded-[var(--radius-tile)] px-5 py-4",
        accent
          ? "bg-brand-600 text-white [border-color:transparent]"
          : "bg-[var(--surface-raised)]",
      )}
    >
      <div
        className={cx(
          "text-[12px] font-medium tracking-wide uppercase",
          accent ? "text-brand-100" : "text-[var(--text-muted)]",
        )}
      >
        {label}
      </div>
      <div
        className={cx(
          "mt-2 text-[30px] leading-none font-semibold tracking-[-0.03em]",
          accent ? "text-white" : "text-[var(--text-primary)]",
        )}
      >
        {value}
      </div>
      {hint ? (
        <div
          className={cx(
            "mt-2 text-[12.5px] leading-snug",
            accent ? "text-brand-100" : "text-[var(--text-secondary)]",
          )}
        >
          {hint}
        </div>
      ) : null}
    </div>
  );
}

const TIER_DOT: Record<Tier, string> = {
  model: "var(--ordinal-3)",
  seasonal_fallback: "var(--ordinal-1)",
  insufficient_data: "var(--text-muted)",
};

export function TierBadge({ tier, label }: { tier: Tier; label: string }) {
  return (
    <span className="hairline inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-[12px] font-medium text-[var(--text-secondary)]">
      <span
        aria-hidden
        className="size-2 rounded-full"
        style={{ background: TIER_DOT[tier] }}
      />
      {label}
    </span>
  );
}

/** Confidence rides an ordinal green ramp (it is an ordered scale, not a
 *  status), and always carries its text label so hue is never load-bearing. */
const CONFIDENCE_FILL: Record<Confidence, { bars: number; color: string }> = {
  high: { bars: 3, color: "var(--ordinal-3)" },
  medium: { bars: 2, color: "var(--ordinal-2)" },
  low: { bars: 1, color: "var(--ordinal-1)" },
  none: { bars: 0, color: "var(--text-muted)" },
};

export function ConfidenceBadge({
  confidence,
  label,
}: {
  confidence: Confidence;
  label: string;
}) {
  const { bars, color } = CONFIDENCE_FILL[confidence];
  return (
    <span className="inline-flex items-center gap-2 text-[12px] font-medium text-[var(--text-secondary)]">
      <span aria-hidden className="flex items-end gap-[2px]">
        {[0, 1, 2].map((i) => (
          <span
            key={i}
            className="w-[3px] rounded-[1px]"
            style={{
              height: `${6 + i * 3}px`,
              background: i < bars ? color : "var(--gridline)",
            }}
          />
        ))}
      </span>
      {label} confidence
    </span>
  );
}

/** Status is the fixed reserved scale and always ships icon + label, never
 *  color alone. */
export function AnomalyBadge({ note }: { note: string }) {
  return (
    <span
      className="inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-[12px] font-medium"
      style={{
        background: "color-mix(in srgb, var(--status-serious) 16%, transparent)",
        color: "var(--text-primary)",
      }}
    >
      <svg aria-hidden viewBox="0 0 16 16" className="size-3.5 shrink-0">
        <path
          d="M8 1.6 15 14H1L8 1.6Z"
          fill="none"
          stroke="var(--status-serious)"
          strokeWidth="1.6"
          strokeLinejoin="round"
        />
        <path d="M8 6v3.6" stroke="var(--status-serious)" strokeWidth="1.6" strokeLinecap="round" />
        <circle cx="8" cy="11.8" r="0.9" fill="var(--status-serious)" />
      </svg>
      {note}
    </span>
  );
}

export function Pill({ children }: { children: ReactNode }) {
  return (
    <span className="hairline inline-flex items-center gap-2 rounded-full bg-[var(--surface-raised)] px-3 py-1 text-[12.5px] font-medium text-[var(--text-secondary)]">
      {children}
    </span>
  );
}

export function Empty({ title, body }: { title: string; body: string }) {
  return (
    <div className="px-6 py-14 text-center">
      <p className="text-[15px] font-medium text-[var(--text-primary)]">{title}</p>
      <p className="mx-auto mt-1.5 max-w-md text-[13.5px] leading-relaxed text-[var(--text-secondary)]">
        {body}
      </p>
    </div>
  );
}
