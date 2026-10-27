/**
 * Short motivational lines shown on the dashboard.
 *
 * Deliberately brief and either common gym aphorisms or attributed to the person who made the
 * remark famous, so nothing here leans on a long copyrighted passage.
 */
export interface Quote {
  text: string;
  author?: string;
}

export const QUOTES: Quote[] = [
  { text: "The only bad workout is the one that didn't happen." },
  { text: "It's not the daily increase but the daily decrease. Hack away at the unessential.", author: "Bruce Lee" },
  { text: "Discipline is choosing between what you want now and what you want most." },
  { text: "Small steps, taken daily, outrun big plans you never start." },
  { text: "Strength does not come from winning. Your struggles develop your strengths.", author: "Arnold Schwarzenegger" },
  { text: "Show up on the days you don't feel like it. Those are the ones that count." },
  { text: "Take care of your body. It's the only place you have to live.", author: "Jim Rohn" },
  { text: "Form first, weight second. Your joints keep the receipts." },
  { text: "You don't have to be extreme, just consistent." },
  { text: "The body achieves what the mind believes." },
  { text: "Rest is part of the training, not a reward for it." },
  { text: "A one-hour workout is four percent of your day." },
];

/** Picks a quote that changes with the day, so the greeting feels fresh without being random. */
export function quoteOfTheDay(offset = 0): Quote {
  const day = Math.floor(Date.now() / 86_400_000);
  return QUOTES[(day + offset) % QUOTES.length];
}
