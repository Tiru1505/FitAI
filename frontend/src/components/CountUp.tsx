import { useEffect, useRef, useState } from "react";

/** Animates a number from 0 to `value` once, and respects prefers-reduced-motion. */
export function CountUp({ value, duration = 900, format }: {
  value: number; duration?: number; format?: (n: number) => string;
}) {  // prettier-ignore
  const [shown, setShown] = useState(value);
  const frame = useRef<number | null>(null);

  useEffect(() => {
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches || value === 0) {
      setShown(value);
      return;
    }
    const start = performance.now();
    const tick = (now: number) => {
      const t = Math.min(1, (now - start) / duration);
      const eased = 1 - Math.pow(1 - t, 3);
      setShown(value * eased);
      if (t < 1) frame.current = requestAnimationFrame(tick);
    };
    frame.current = requestAnimationFrame(tick);
    return () => {
      if (frame.current) cancelAnimationFrame(frame.current);
    };
  }, [value, duration]);

  return <>{format ? format(shown) : Math.round(shown).toLocaleString()}</>;
}
