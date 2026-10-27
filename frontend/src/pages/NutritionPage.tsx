import { useState } from "react";

import { errorMessage } from "../api/client";
import { useFoods, useMealGuidance, type FoodFilters } from "../api/hooks";
import { ALLERGENS, DIETS, MEAL_CATEGORIES, label, type FoodItem } from "../api/types";
import DietPlanCard from "../components/DietPlanCard";
import { AppleIcon, SparkIcon } from "../components/icons";
import { Alert, Button, Card, ChipToggle, Field, Input, PageHeader, Select, Spinner } from "../components/ui";

function FoodTable({ items }: { items: FoodItem[] }) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-left text-sm">
        <thead className="text-xs uppercase text-beige-400">
          <tr>
            <th className="py-2 pr-3">Food</th><th className="pr-3">Serving</th><th className="pr-3 text-right">kcal</th>
            <th className="pr-3 text-right">Protein</th><th className="pr-3 text-right">Carbs</th><th className="pr-3 text-right">Fat</th>
            <th className="pr-3 text-right">Fibre</th><th>Tags</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-white/8">
          {items.map((f) => (
            <tr key={f.id}>
              <td className="py-2 pr-3 font-medium text-beige-100">{f.name}</td>
              <td className="pr-3 text-beige-400">{f.serving_size}</td>
              <td className="pr-3 text-right tabular-nums">{Math.round(f.calories)}</td>
              <td className="pr-3 text-right tabular-nums">{f.protein_g} g</td>
              <td className="pr-3 text-right tabular-nums">{f.carbs_g} g</td>
              <td className="pr-3 text-right tabular-nums">{f.fat_g} g</td>
              <td className="pr-3 text-right tabular-nums">{f.fiber_g} g</td>
              <td className="text-xs text-beige-400">{[...f.tags.map(label), ...f.allergens.map((a) => `contains ${label(a).toLowerCase()}`)].join(" · ")}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export default function NutritionPage() {
  const guidance = useMealGuidance();
  const [filters, setFilters] = useState<FoodFilters>({ exclude_allergens: [] });
  const foods = useFoods(filters);
  const g = guidance.data;

  const setNum = (key: "max_calories" | "min_protein_g", v: string) =>
    setFilters((f) => ({ ...f, [key]: v === "" || Number(v) < 0 ? undefined : Number(v) }));

  return (
    <div className="space-y-6">
      <PageHeader title="Nutrition guidance" subtitle="General, educational guidance only. Not a medical or clinical diet plan." />

      <Card
        title="Your general guidance"
        icon={<SparkIcon />}
        action={<Button onClick={() => guidance.mutate()} disabled={guidance.isPending}>{g ? "Refresh" : "Get guidance"}</Button>}
      >
        {guidance.isPending && <Spinner />}
        {guidance.isError && <Alert tone="error">{errorMessage(guidance.error)}</Alert>}
        {!g && !guidance.isPending && <p className="text-sm text-beige-400">Generate guidance based on your profile goal, dietary preferences and allergies.</p>}
        {g && (
          <div className="space-y-4 text-sm">
            {g.professional_referral && (
              <Alert tone="warning" title="Please consult a professional">
                Based on the health considerations in your profile, speak with a doctor or registered dietitian for personalised nutrition advice.
              </Alert>
            )}
            <div className="grid gap-4 md:grid-cols-2">
              <div>
                <p className="font-medium text-beige-200">Approximate daily energy range</p>
                <p className="mt-1 text-2xl font-semibold tabular-nums">
                  {g.calorie_min != null ? `${g.calorie_min.toLocaleString()}–${g.calorie_max?.toLocaleString()} kcal` : "Not shown"}
                </p>
                <p className="mt-1 text-beige-400">{g.calorie_explanation}</p>
              </div>
              <div>
                <p className="font-medium text-beige-200">Protein</p>
                <p className="mt-1 text-beige-300">{g.protein_guidance}</p>
                <p className="mt-3 font-medium text-beige-200">Meal tips for {label(g.goal).toLowerCase()}</p>
                <ul className="mt-1 list-disc pl-5 text-beige-300">{g.meal_tips.map((t) => <li key={t}>{t}</li>)}</ul>
              </div>
            </div>
            <p className="text-xs text-beige-400">
              Filters applied: {g.applied_filters.diet ? label(g.applied_filters.diet) : "no diet filter"}
              {g.applied_filters.exclude_allergens.length > 0 && `; excluding ${g.applied_filters.exclude_allergens.map(label).join(", ")}`}
            </p>
            <div className="grid gap-4 md:grid-cols-2">
              {Object.entries(g.suggested_foods).map(([category, items]) => (
                <div key={category} className="rounded-lg border border-beige-100/12 p-3">
                  <p className="mb-2 font-medium text-beige-200">{label(category)} ideas</p>
                  {items.length ? (
                    <ul className="space-y-1 text-beige-300">
                      {items.map((f) => <li key={f.id} className="flex justify-between gap-2"><span>{f.name}</span><span className="tabular-nums text-beige-500">{Math.round(f.calories)} kcal · {f.protein_g} g protein</span></li>)}
                    </ul>
                  ) : <p className="text-beige-500">No matching foods in the table.</p>}
                </div>
              ))}
            </div>
            <Alert tone="info">{g.disclaimer}</Alert>
          </div>
        )}
      </Card>

      <DietPlanCard />

      <Card title="Food explorer" icon={<AppleIcon />}>
        <div className="mb-4 grid gap-4 md:grid-cols-4">
          <Field label="Diet">
            <Select value={filters.diet ?? ""} onChange={(e) => setFilters((f) => ({ ...f, diet: e.target.value || undefined }))}>
              <option value="">Any</option>
              {DIETS.map((d) => <option key={d} value={d}>{label(d)}</option>)}
            </Select>
          </Field>
          <Field label="Meal category">
            <Select value={filters.meal_category ?? ""} onChange={(e) => setFilters((f) => ({ ...f, meal_category: e.target.value || undefined }))}>
              <option value="">Any</option>
              {MEAL_CATEGORIES.map((d) => <option key={d} value={d}>{label(d)}</option>)}
            </Select>
          </Field>
          <Field label="Max calories per serving">
            <Input type="number" min={0} onChange={(e) => setNum("max_calories", e.target.value)} />
          </Field>
          <Field label="Min protein (g)">
            <Input type="number" min={0} onChange={(e) => setNum("min_protein_g", e.target.value)} />
          </Field>
          <div className="md:col-span-4">
            <Field label="Exclude allergens">
              <ChipToggle options={ALLERGENS} selected={(filters.exclude_allergens ?? []) as (typeof ALLERGENS)[number][]} onChange={(v) => setFilters((f) => ({ ...f, exclude_allergens: v }))} render={label} />
            </Field>
          </div>
          <div className="md:col-span-2">
            <Field label="Search">
              <Input maxLength={60} placeholder="e.g. lentils" onChange={(e) => setFilters((f) => ({ ...f, q: e.target.value || undefined }))} />
            </Field>
          </div>
        </div>
        {foods.isError && <Alert tone="error">{errorMessage(foods.error)}</Alert>}
        {foods.isLoading && <Spinner />}
        {foods.data && (
          <>
            <p className="mb-2 text-xs text-beige-400">{foods.data.total} foods</p>
            <FoodTable items={foods.data.items} />
            <p className="mt-3 text-xs text-beige-400">{foods.data.disclaimer}</p>
          </>
        )}
      </Card>
    </div>
  );
}
