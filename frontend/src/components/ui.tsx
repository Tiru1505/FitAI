import type { ButtonHTMLAttributes, InputHTMLAttributes, ReactNode, SelectHTMLAttributes } from "react";

const cx = (...c: (string | false | null | undefined)[]) => c.filter(Boolean).join(" ");

export function Card({
  title, action, children, className, icon, subtitle,
}: { title?: ReactNode; action?: ReactNode; children: ReactNode; className?: string; icon?: ReactNode; subtitle?: ReactNode }) {  // prettier-ignore
  return (
    <section className={cx("glass glass-hover rounded-3xl p-5", className)}>
      {(title || action) && (
        <div className="mb-4 flex items-start justify-between gap-3">
          {title && (
            <div className="flex items-center gap-3">
              {icon && (
                <span className="grid h-10 w-10 place-items-center rounded-2xl bg-plum-500/15 text-plum-300 ring-1 ring-plum-400/20 [&>svg]:h-5 [&>svg]:w-5">
                  {icon}
                </span>
              )}
              <div>
                <h2 className="text-base font-semibold text-beige-100">{title}</h2>
                {subtitle && <p className="text-xs text-beige-400">{subtitle}</p>}
              </div>
            </div>
          )}
          {action}
        </div>
      )}
      {children}
    </section>
  );
}

type Variant = "primary" | "secondary" | "danger" | "ghost";
const VARIANTS: Record<Variant, string> = {
  primary:
    "bg-gradient-to-br from-plum-400 to-plum-600 text-white shadow-lg shadow-plum-600/30 hover:from-plum-300 hover:to-plum-500 active:scale-[0.98] disabled:opacity-50 disabled:shadow-none",
  secondary:
    "border border-beige-100/15 bg-white/5 text-beige-200 hover:border-plum-400/40 hover:bg-plum-500/10 hover:text-beige-100 active:scale-[0.98] disabled:opacity-45",
  danger:
    "bg-gradient-to-br from-rose-500 to-red-700 text-white shadow-lg shadow-red-900/40 hover:from-rose-400 hover:to-red-600 active:scale-[0.98] disabled:opacity-50",
  ghost: "text-beige-300 hover:bg-white/5 hover:text-beige-100 active:scale-[0.98]",
};

export function Button({ variant = "primary", className, ...props }: ButtonHTMLAttributes<HTMLButtonElement> & { variant?: Variant }) {
  return (
    <button
      {...props}
      className={cx(
        "inline-flex items-center justify-center gap-2 rounded-xl px-4 py-2 text-sm font-medium",
        "transition-all duration-200 disabled:cursor-not-allowed disabled:active:scale-100",
        VARIANTS[variant],
        className,
      )}
    />
  );
}

export function Field({ label, error, hint, children }: { label: string; error?: string; hint?: string; children: ReactNode }) {
  return (
    <label className="block">
      <span className="mb-1 block text-sm font-medium text-beige-200">{label}</span>
      {children}
      {hint && !error && <span className="mt-1 block text-xs text-beige-400">{hint}</span>}
      {error && <span className="mt-1 block text-xs font-medium text-rose-300">{error}</span>}
    </label>
  );
}

const inputClass =
  "w-full rounded-xl border border-beige-100/12 bg-espresso-900/60 px-3 py-2 text-sm text-beige-100 shadow-inner transition-colors duration-200 placeholder:text-beige-500 hover:border-beige-100/20 focus:border-plum-400/60 focus:outline-none [color-scheme:dark]";

export const Input = (props: InputHTMLAttributes<HTMLInputElement>) => <input {...props} className={cx(inputClass, props.className)} />;

export const Select = (props: SelectHTMLAttributes<HTMLSelectElement>) => <select {...props} className={cx(inputClass, props.className)} />;

export function Alert({ tone = "info", title, children }: { tone?: "info" | "warning" | "error" | "success"; title?: string; children: ReactNode }) {
  const tones = {
    info: "border-plum-400/25 bg-plum-500/10 text-plum-200",
    warning: "border-ember-400/30 bg-ember-500/12 text-ember-300",
    error: "border-rose-400/30 bg-rose-500/12 text-rose-200",
    success: "border-emerald-400/25 bg-emerald-500/12 text-emerald-200",
  };
  return (
    <div role={tone === "error" ? "alert" : "status"} className={cx("animate-fade-up rounded-2xl border px-4 py-3 text-sm", tones[tone])}>
      {title && <p className="mb-1 font-semibold">{title}</p>}
      <div className="text-beige-200">{children}</div>
    </div>
  );
}

export function Spinner({ label = "Loading" }: { label?: string }) {
  return (
    <div className="flex items-center gap-2.5 text-sm text-beige-400" role="status">
      <span className="h-4 w-4 animate-spin rounded-full border-2 border-beige-100/15 border-t-plum-400" />
      {label}
    </div>
  );
}

export const SkeletonBlock = ({ className = "h-24" }: { className?: string }) => (
  <div className={cx("skeleton rounded-2xl", className)} />
);

/** Tiny inline area chart for metric tiles — pure SVG, no chart library needed. */
export function Sparkline({ values, className = "", stroke = "#c9a9ff", height = 36 }: {
  values: number[]; className?: string; stroke?: string; height?: number;
}) {  // prettier-ignore
  if (values.length < 2) return <div className={cx("h-9", className)} />;
  const max = Math.max(...values);
  const min = Math.min(...values);
  const span = max - min || 1;
  const points = values.map((v, i) => [(i / (values.length - 1)) * 100, 100 - ((v - min) / span) * 86 - 7]);
  const line = points.map(([x, y], i) => `${i ? "L" : "M"}${x.toFixed(2)},${y.toFixed(2)}`).join(" ");
  const id = `spark-${stroke.replace("#", "")}`;
  return (
    <svg viewBox="0 0 100 100" preserveAspectRatio="none" className={cx("w-full", className)} style={{ height }} aria-hidden>
      <defs>
        <linearGradient id={id} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor={stroke} stopOpacity="0.45" />
          <stop offset="100%" stopColor={stroke} stopOpacity="0" />
        </linearGradient>
      </defs>
      <path d={`${line} L100,100 L0,100 Z`} fill={`url(#${id})`} />
      <path d={line} fill="none" stroke={stroke} strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" vectorEffect="non-scaling-stroke" />
      <circle cx={points.at(-1)![0]} cy={points.at(-1)![1]} r="2.5" fill={stroke} vectorEffect="non-scaling-stroke" />
    </svg>
  );
}

/** Vertical bars for small weekly series, as in the reference dashboard. */
export function MiniBars({ values, color = "#e0a267", height = 40 }: { values: number[]; color?: string; height?: number }) {
  const max = Math.max(...values, 1);
  return (
    <div className="flex items-end gap-1.5" style={{ height }} aria-hidden>
      {values.map((v, i) => (
        <span
          key={i}
          className="flex-1 rounded-sm transition-all duration-500"
          style={{
            height: `${Math.max(8, (v / max) * 100)}%`,
            background: v > 0 ? color : "rgba(246,236,224,0.12)",
            opacity: v > 0 ? 0.55 + (v / max) * 0.45 : 1,
          }}
        />
      ))}
    </div>
  );
}

export function Stat({ label, value, hint, icon, tone = "plum", chart }: {
  label: string; value: ReactNode; hint?: string; icon?: ReactNode; tone?: "plum" | "ember" | "beige"; chart?: ReactNode;
}) {  // prettier-ignore
  const accents = {
    plum: "text-plum-300 bg-plum-500/15 ring-plum-400/20",
    ember: "text-ember-300 bg-ember-500/15 ring-ember-400/20",
    beige: "text-beige-300 bg-white/5 ring-white/10",
  };
  return (
    <div className="glass glass-hover rounded-3xl p-4">
      <div className="flex items-start justify-between gap-2">
        <p className="text-[11px] font-medium uppercase tracking-[0.08em] text-beige-400">{label}</p>
        {icon && <span className={cx("grid h-8 w-8 place-items-center rounded-xl ring-1 [&>svg]:h-4 [&>svg]:w-4", accents[tone])}>{icon}</span>}
      </div>
      <p className="mt-2 text-3xl font-semibold tabular-nums tracking-tight text-beige-100">{value}</p>
      {hint && <p className="mt-1 text-xs text-beige-400">{hint}</p>}
      {chart && <div className="mt-3">{chart}</div>}
    </div>
  );
}

/** Half-circle gauge, echoing the reference dashboard's speed dial. */
export function Gauge({ value, label, caption, size = 190 }: { value: number; label?: string; caption?: string; size?: number }) {
  const clamped = Math.max(0, Math.min(1, value));
  const ticks = 44;
  return (
    <div className="relative mx-auto" style={{ width: size, height: size / 2 + 54 }} role="img" aria-label={`${Math.round(clamped * 100)}%`}>
      <svg viewBox="0 0 200 118" className="w-full">
        {Array.from({ length: ticks }, (_, i) => {
          const t = i / (ticks - 1);
          const angle = Math.PI * (1 - t);
          const lit = t <= clamped;
          const [cx, cy] = [100, 104];
          const [r1, r2] = [72, lit ? 86 : 82];
          return (
            <line
              key={i}
              x1={cx + Math.cos(angle) * r1} y1={cy - Math.sin(angle) * r1}
              x2={cx + Math.cos(angle) * r2} y2={cy - Math.sin(angle) * r2}
              stroke={lit ? "#c9a9ff" : "rgba(246,236,224,0.16)"}
              strokeWidth={lit ? 3 : 2} strokeLinecap="round"
              style={{ transition: "stroke 600ms ease" }}
            />
          );
        })}
      </svg>
      {/* The number sits inside the arc; the caption clears it so the two never collide. */}
      <p className="absolute inset-x-0 top-[46%] text-center text-3xl font-semibold tabular-nums text-beige-100">
        {label ?? `${Math.round(clamped * 100)}%`}
      </p>
      {caption && <p className="absolute inset-x-0 bottom-0 px-2 text-center text-[11px] leading-snug text-beige-400">{caption}</p>}
    </div>
  );
}

/** Circular dial for compact percentages. */
export function ProgressRing({ value, size = 68, label }: { value: number; size?: number; label?: string }) {
  const r = (size - 8) / 2;
  const circumference = 2 * Math.PI * r;
  const clamped = Math.max(0, Math.min(1, value));
  return (
    <div className="relative inline-grid place-items-center" style={{ width: size, height: size }}>
      <svg width={size} height={size} className="-rotate-90">
        <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke="rgba(246,236,224,0.10)" strokeWidth="6" />
        <circle
          cx={size / 2} cy={size / 2} r={r} fill="none" stroke="url(#ring-grad)" strokeWidth="6" strokeLinecap="round"
          strokeDasharray={circumference} strokeDashoffset={circumference * (1 - clamped)}
          style={{ transition: "stroke-dashoffset 900ms cubic-bezier(0.22, 1, 0.36, 1)" }}
        />
        <defs>
          <linearGradient id="ring-grad" x1="0" y1="0" x2="1" y2="1">
            <stop offset="0%" stopColor="#c9a9ff" />
            <stop offset="100%" stopColor="#e0a267" />
          </linearGradient>
        </defs>
      </svg>
      <span className="absolute text-sm font-semibold tabular-nums text-beige-100">{label ?? `${Math.round(clamped * 100)}%`}</span>
    </div>
  );
}

export function ChipToggle<T extends string | number>({
  options, selected, onChange, render,
}: { options: readonly T[]; selected: T[]; onChange: (v: T[]) => void; render?: (v: T) => string }) {  // prettier-ignore
  return (
    <div className="flex flex-wrap gap-2">
      {options.map((o) => {
        const on = selected.includes(o);
        return (
          <button
            key={String(o)}
            type="button"
            aria-pressed={on}
            onClick={() => onChange(on ? selected.filter((s) => s !== o) : [...selected, o])}
            className={cx(
              "rounded-full border px-3 py-1 text-sm transition-all duration-200 active:scale-95",
              on
                ? "border-plum-400/50 bg-plum-500/25 text-beige-100 shadow-sm shadow-plum-900/40"
                : "border-beige-100/12 bg-white/5 text-beige-300 hover:border-plum-400/35 hover:text-beige-100",
            )}
          >
            {render ? render(o) : String(o)}
          </button>
        );
      })}
    </div>
  );
}

export const pct = (v: number | null | undefined, digits = 0) => (v == null ? "—" : `${(v * 100).toFixed(digits)}%`);

export function PageHeader({ title, subtitle, action }: { title: string; subtitle?: string; action?: ReactNode }) {
  return (
    <div className="mb-6 flex flex-wrap items-end justify-between gap-3 animate-fade-up">
      <div>
        <h1 className="text-[1.7rem] font-semibold tracking-tight text-beige-100">{title}</h1>
        {subtitle && <p className="mt-1 text-sm text-beige-400">{subtitle}</p>}
      </div>
      {action}
    </div>
  );
}
