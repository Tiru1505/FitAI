import { useState } from "react";

import { errorMessage } from "../api/client";
import { useDietPlan } from "../api/hooks";
import { label, type DayPlan, type PlannedItem, type PlannedMeal } from "../api/types";
import { AppleIcon, SparkIcon } from "./icons";
import { Alert, Button, Card, Spinner } from "./ui";

/** Plain-language explanation of why each food is in the meal. */
const ROLE_COPY: Record<string, { text: string; tone: string }> = {
  protein: { text: "protein", tone: "bg-plum-500/15 text-plum-200 ring-plum-400/25" },
  carb: { text: "energy", tone: "bg-ember-500/15 text-ember-200 ring-ember-400/25" },
  vegetable: { text: "vegetable", tone: "bg-emerald-500/15 text-emerald-200 ring-emerald-400/25" },
  // Called "fruit or veg" because the food table has no food-group column: the slot is picked on
  // sugar and fibre, so a carrot can fill it as fairly as a berry.
  fruit: { text: "fruit or veg", tone: "bg-rose-500/12 text-rose-200 ring-rose-400/25" },
  fat: { text: "healthy fat", tone: "bg-amber-500/15 text-amber-200 ring-amber-400/25" },
};

const servingText = (servings: number, size: string) =>
  servings === 1 ? size : `${servings} × ${size}`;

function RoleBadge({ role }: { role: string }) {
  const copy = ROLE_COPY[role] ?? { text: role, tone: "bg-white/5 text-beige-300 ring-white/10" };
  return <span className={`rounded-full px-2 py-0.5 text-[10px] font-medium uppercase tracking-wide ring-1 ${copy.tone}`}>{copy.text}</span>;
}

/** One number against its target, as a bar. Over-target is shown, not clipped away. */
function TargetBar({ name, actual, target, unit = "g" }: { name: string; actual: number; target: number; unit?: string }) {
  const ratio = target > 0 ? actual / target : 0;
  const over = ratio > 1.05;
  return (
    <div>
      <div className="flex items-baseline justify-between text-xs">
        <span className="text-beige-300">{name}</span>
        <span className="tabular-nums text-beige-400">
          <span className="font-medium text-beige-100">{Math.round(actual)}</span> / {Math.round(target)} {unit}
        </span>
      </div>
      <div className="mt-1 h-1.5 overflow-hidden rounded-full bg-white/8">
        <div
          className={`h-full rounded-full transition-[width] duration-700 ${over ? "bg-ember-400/80" : "bg-plum-400/80"}`}
          style={{ width: `${Math.min(100, ratio * 100)}%` }}
        />
      </div>
    </div>
  );
}

function ItemRow({ item }: { item: PlannedItem }) {
  const [open, setOpen] = useState(false);
  return (
    <li className="rounded-xl px-2 py-2 transition hover:bg-white/4">
      <div className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1">
        <span className="flex items-baseline gap-2">
          <span className="font-medium text-beige-100">{item.name}</span>
          <RoleBadge role={item.role} />
        </span>
        <span className="tabular-nums text-xs text-beige-400">
          {Math.round(item.calories)} kcal · {item.protein_g} g protein
        </span>
      </div>
      <div className="mt-0.5 flex flex-wrap items-center gap-x-3 text-xs text-beige-400">
        <span>{servingText(item.servings, item.serving_size)}</span>
        {item.alternatives.length > 0 && (
          <button type="button" className="text-plum-300 underline decoration-dotted hover:text-plum-200" onClick={() => setOpen((v) => !v)}>
            {open ? "hide swaps" : `${item.alternatives.length} swaps`}
          </button>
        )}
      </div>
      {open && (
        <ul className="mt-2 space-y-1 border-l border-plum-400/30 pl-3 text-xs text-beige-300">
          {item.alternatives.map((alt) => (
            <li key={alt.food_id} className="flex flex-wrap justify-between gap-x-3">
              <span>{alt.name}</span>
              <span className="tabular-nums text-beige-500">{servingText(alt.servings, alt.serving_size)} · {alt.calories} kcal</span>
            </li>
          ))}
        </ul>
      )}
    </li>
  );
}

function MealBlock({ meal }: { meal: PlannedMeal }) {
  return (
    <div className="animate-fade-up rounded-2xl border border-beige-100/12 bg-white/4 p-4">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h4 className="font-semibold text-beige-100">{meal.label}</h4>
        <span className="tabular-nums text-xs text-beige-400">
          {Math.round(meal.calories)} kcal <span className="text-beige-500">(aiming for {meal.target_calories})</span>
        </span>
      </div>
      <ul className="mt-2 divide-y divide-white/6">
        {meal.items.map((item) => <ItemRow key={item.food_id} item={item} />)}
      </ul>
      <p className="mt-2 tabular-nums text-[11px] text-beige-500">
        {meal.protein_g} g protein · {meal.carbs_g} g carbs · {meal.fat_g} g fat · {meal.fiber_g} g fibre
      </p>
    </div>
  );
}

const dayName = (iso: string) =>
  new Date(`${iso}T12:00:00`).toLocaleDateString(undefined, { weekday: "short", day: "numeric", month: "short" });

export default function DietPlanCard() {
  const plan = useDietPlan();
  const [activeDay, setActiveDay] = useState(0);
  const data = plan.data;
  const day: DayPlan | undefined = data?.days[Math.min(activeDay, data.days.length - 1)];

  const request = (days: number) => {
    setActiveDay(0);
    plan.mutate({ days });
  };

  return (
    <Card
      title="Your diet plan"
      icon={<AppleIcon />}
      subtitle="Meals and portions sized to your body and goal, from the same USDA food table."
      action={
        <div className="flex gap-2">
          <Button onClick={() => request(1)} disabled={plan.isPending}>Today</Button>
          <Button variant="secondary" onClick={() => request(7)} disabled={plan.isPending}>This week</Button>
        </div>
      }
    >
      {plan.isPending && <Spinner label="Building your plan" />}
      {plan.isError && <Alert tone="error">{errorMessage(plan.error)}</Alert>}
      {!data && !plan.isPending && (
        <p className="text-sm text-beige-400">
          Build a day or a week of meals from your profile. Your weight, height, age, training days and goal set the
          calorie and protein targets; your dietary preferences and allergies decide which foods can appear.
        </p>
      )}

      {data && !data.available && (
        <div className="space-y-3">
          <Alert tone="warning" title="No plan is shown">{data.reason}</Alert>
          <p className="text-xs text-beige-400">{data.body.note}</p>
        </div>
      )}

      {data?.available && data.targets && day && (
        <div className="space-y-5 text-sm">
          <div className="grid gap-4 md:grid-cols-[1fr_1.4fr]">
            <div className="rounded-2xl border border-beige-100/12 bg-white/4 p-4">
              <p className="text-xs uppercase tracking-wide text-beige-400">Body mass index</p>
              {data.body.bmi != null ? (
                <>
                  <p className="mt-1 text-3xl font-semibold tabular-nums text-beige-100">{data.body.bmi}</p>
                  <p className="text-xs text-plum-300">{data.body.category}</p>
                </>
              ) : (
                <p className="mt-1 text-beige-300">Not shown</p>
              )}
              <p className="mt-2 text-[11px] leading-relaxed text-beige-500">{data.body.note}</p>
            </div>
            <div className="rounded-2xl border border-beige-100/12 bg-white/4 p-4">
              <div className="flex items-baseline justify-between">
                <p className="text-xs uppercase tracking-wide text-beige-400">Daily targets</p>
                <p className="tabular-nums text-xs text-beige-400">{data.targets.calories.toLocaleString()} kcal</p>
              </div>
              <div className="mt-3 space-y-2.5">
                <TargetBar name="Calories" actual={day.calories} target={data.targets.calories} unit="kcal" />
                <TargetBar name="Protein" actual={day.protein_g} target={data.targets.protein_g} />
                <TargetBar name="Carbohydrate" actual={day.carbs_g} target={data.targets.carbs_g} />
                <TargetBar name="Fat" actual={day.fat_g} target={data.targets.fat_g} />
              </div>
              <p className="mt-3 text-[11px] leading-relaxed text-beige-500">{data.targets.explanation}</p>
            </div>
          </div>

          {data.days.length > 1 && (
            <div className="flex flex-wrap gap-2" role="tablist" aria-label="Day of the plan">
              {data.days.map((d, i) => (
                <button
                  key={d.date}
                  role="tab"
                  aria-selected={i === activeDay}
                  onClick={() => setActiveDay(i)}
                  className={`rounded-full px-3 py-1 text-xs ring-1 transition ${
                    i === activeDay
                      ? "bg-plum-500/25 text-plum-100 ring-plum-400/40"
                      : "bg-white/5 text-beige-300 ring-white/10 hover:bg-white/10"
                  }`}
                >
                  {dayName(d.date)}
                </button>
              ))}
            </div>
          )}

          <div className="stagger grid gap-4 md:grid-cols-2">
            {day.meals.map((meal) => <MealBlock key={meal.key} meal={meal} />)}
          </div>

          <div className="rounded-2xl border border-beige-100/12 bg-white/4 p-4">
            <p className="flex items-center gap-2 font-medium text-beige-200"><SparkIcon /> Making it work</p>
            <ul className="mt-2 list-disc space-y-1 pl-5 text-beige-300">{data.tips.map((t) => <li key={t}>{t}</li>)}</ul>
            <p className="mt-3 text-xs text-beige-400">
              Filters applied: {data.applied_filters.diet ? label(data.applied_filters.diet) : "no diet filter"}
              {data.applied_filters.exclude_allergens.length > 0 &&
                `; excluding ${data.applied_filters.exclude_allergens.map(label).join(", ")}`}
            </p>
          </div>

          <Alert tone="info">
            Portions are rounded to half servings, so a day's total lands near your target rather than exactly on it —
            both numbers are shown above. {data.disclaimer}
          </Alert>
        </div>
      )}
    </Card>
  );
}
