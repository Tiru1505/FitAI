import type { SVGProps } from "react";

import type { ExerciseSlug } from "../api/types";

/** Inline SVG icons: no icon-font dependency, and they inherit currentColor. */
type IconProps = SVGProps<SVGSVGElement>;

const base = (props: IconProps) => ({
  viewBox: "0 0 24 24",
  fill: "none",
  stroke: "currentColor",
  strokeWidth: 1.8,
  strokeLinecap: "round" as const,
  strokeLinejoin: "round" as const,
  ...props,
});

export const DumbbellIcon = (p: IconProps) => (
  <svg {...base(p)}><path d="M6.5 6.5v11M3.5 9v5M17.5 6.5v11M20.5 9v5M6.5 12h11" /></svg>
);
export const FlameIcon = (p: IconProps) => (
  <svg {...base(p)}><path d="M12 3s4.5 4 4.5 8a4.5 4.5 0 0 1-9 0c0-1.3.5-2.4 1.2-3.3.3 1.4 1 2 1.8 2.3C10 8.2 12 6 12 3Z" /><path d="M7.5 14a4.5 4.5 0 0 0 9 0" /></svg>
);
export const ChartIcon = (p: IconProps) => (
  <svg {...base(p)}><path d="M4 19h16M7 16V9M12 16V5M17 16v-4" /></svg>
);
export const AppleIcon = (p: IconProps) => (
  <svg {...base(p)}><path d="M12 8c-1-1.4-2.4-2-3.8-1.7C6.3 6.7 5 8.6 5 11.3c0 3.4 2.3 7.2 4.2 7.2.9 0 1.4-.5 2.8-.5s1.9.5 2.8.5c1.9 0 4.2-3.8 4.2-7.2 0-2.7-1.3-4.6-3.2-5-1.4-.3-2.8.3-3.8 1.7Z" /><path d="M12 8c.2-1.6 1.3-2.9 2.9-3.2" /></svg>
);
export const CameraIcon = (p: IconProps) => (
  <svg {...base(p)}><path d="M4 8.5h3l1.2-2h7.6L17 8.5h3v10H4v-10Z" /><circle cx="12" cy="13" r="3.2" /></svg>
);
export const TargetIcon = (p: IconProps) => (
  <svg {...base(p)}><circle cx="12" cy="12" r="8" /><circle cx="12" cy="12" r="4" /><circle cx="12" cy="12" r="0.8" fill="currentColor" /></svg>
);
export const CheckIcon = (p: IconProps) => (
  <svg {...base(p)}><path d="m5 12.5 4.5 4.5L19 7.5" /></svg>
);
export const SparkIcon = (p: IconProps) => (
  <svg {...base(p)}><path d="M12 4v4M12 16v4M4 12h4M16 12h4M6.8 6.8l2.6 2.6M14.6 14.6l2.6 2.6M17.2 6.8l-2.6 2.6M9.4 14.6l-2.6 2.6" /></svg>
);
export const ShieldIcon = (p: IconProps) => (
  <svg {...base(p)}><path d="M12 3.5 5.5 6v6c0 4 2.8 7 6.5 8.5 3.7-1.5 6.5-4.5 6.5-8.5V6L12 3.5Z" /><path d="m9.3 12.2 1.9 1.9 3.6-3.8" /></svg>
);
export const CalendarIcon = (p: IconProps) => (
  <svg {...base(p)}><rect x="4" y="5.5" width="16" height="14" rx="2.5" /><path d="M4 10h16M9 3.5v4M15 3.5v4" /></svg>
);

/** A stylised body in the matching exercise position — used as the per-exercise mark. */
export function ExerciseMark({ slug, ...props }: IconProps & { slug: ExerciseSlug }) {
  const poses: Record<ExerciseSlug, string> = {
    squat: "M12 5.4a1.4 1.4 0 1 0 0-2.8 1.4 1.4 0 0 0 0 2.8ZM12 6.6v4.2M12 10.8 9 14v4M12 10.8 15 14v4M12 7.8 9.2 9.6M12 7.8l2.8 1.8",
    lunge: "M12 5.4a1.4 1.4 0 1 0 0-2.8 1.4 1.4 0 0 0 0 2.8ZM12 6.6v4.6M12 11.2 8 14.4V18M12 11.2l3.4 2.6.6 4.2M12 8l-2.6 1.4M12 8l2.6 1.4",
    push_up: "M5.6 14.6a1.3 1.3 0 1 0 0-2.6 1.3 1.3 0 0 0 0 2.6ZM7 13.4h7.6l3.4 1.4M7.6 13.6 6.6 17M14.6 13.6l-.6 3.4M18 14.8 19.6 17",
    biceps_curl: "M12 5.4a1.4 1.4 0 1 0 0-2.8 1.4 1.4 0 0 0 0 2.8ZM12 6.6v5.6M12 12.2v6M9.4 8.6 8 11.4l2.6 1.2M14.6 8.6 16 11.4l-2.6 1.2",
    shoulder_press: "M12 7.4a1.4 1.4 0 1 0 0-2.8 1.4 1.4 0 0 0 0 2.8ZM12 8.6v5.4M12 14v4.4M9.4 10.4 8.4 6.2M14.6 10.4l1-4.2M7 6.2h2.8M14.2 6.2H17",
  };
  return <svg {...base(props)}><path d={poses[slug]} /></svg>;
}

/** FitAI logo mark: a figure built from pose landmarks, matching what the app actually tracks. */
export function LogoMark({ className = "h-8 w-8", animated = false }: { className?: string; animated?: boolean }) {
  const dots: [number, number][] = [[16, 6], [10, 13], [22, 13], [16, 14], [11, 23], [21, 23]];
  return (
    <svg viewBox="0 0 32 32" className={className} role="img" aria-label="FitAI">
      <defs>
        <linearGradient id="logo-grad" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0%" stopColor="#c9a9ff" />
          <stop offset="100%" stopColor="#6d3fd4" />
        </linearGradient>
      </defs>
      <rect width="32" height="32" rx="9" fill="url(#logo-grad)" />
      <g stroke="white" strokeWidth="1.6" strokeLinecap="round" fill="none" opacity="0.95">
        <path d="M16 8.5v5.5M10 13h12M16 14l-5 9M16 14l5 9" className={animated ? "animate-trace" : undefined} pathLength={1} />
      </g>
      {dots.map(([cx, cy], i) => (
        <circle key={i} cx={cx} cy={cy} r="1.7" fill="white" opacity={0.95} />
      ))}
    </svg>
  );
}
