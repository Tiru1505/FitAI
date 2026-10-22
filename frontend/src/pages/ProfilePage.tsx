import { useState, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";

import { errorMessage } from "../api/client";
import { useActivePlan, useGeneratePlan, useMe, useSaveProfile } from "../api/hooks";
import {
  ALLERGENS, DIETS, EQUIPMENT, EXERCISES, EXPERIENCE, GOALS, HEALTH_FLAGS, WEEKDAYS, label, type ProfileInput,
} from "../api/types";
import { Alert, Button, Card, ChipToggle, Field, Input, PageHeader, Select } from "../components/ui";
import { fieldErrors, profileSchema, type FieldErrors } from "../lib/validation";

const DEFAULTS: ProfileInput = {
  display_name: null, age: null, sex: "unspecified", height_cm: null, weight_kg: null,
  goal: "general_fitness", experience: "beginner", equipment: [], days_per_week: 3, preferred_days: [],
  session_minutes: 30, exclusions: [], dietary_preferences: [], allergies: [], health_flags: [],
};

const HEALTH_LABELS: Record<string, string> = {
  injury: "Current or recent injury",
  chronic_condition: "Chronic health condition",
  pregnancy: "Pregnancy",
  eating_disorder_history: "History of eating disorders",
  special_diet: "Medically prescribed diet",
};

const numberOrNull = (v: string) => (v.trim() === "" ? null : Number(v));

export default function ProfilePage() {
  const me = useMe();
  const plan = useActivePlan();
  const save = useSaveProfile();
  const generate = useGeneratePlan();
  const navigate = useNavigate();
  const existing = me.data?.profile;
  const [form, setForm] = useState<ProfileInput>(() => {
    if (!existing) return DEFAULTS;
    const { safety_acknowledged_at: _a, updated_at: _u, ...rest } = existing;
    return rest;
  });
  const [errors, setErrors] = useState<FieldErrors>({});
  const [serverError, setServerError] = useState<string | null>(null);

  const update = <K extends keyof ProfileInput>(key: K, value: ProfileInput[K]) => setForm((f) => ({ ...f, [key]: value }));

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setServerError(null);
    const parsed = profileSchema.safeParse(form);
    if (!parsed.success) {
      setErrors(fieldErrors(parsed.error));
      return;
    }
    setErrors({});
    try {
      await save.mutateAsync(parsed.data as ProfileInput);
      await generate.mutateAsync();
      navigate("/plan");
    } catch (err) {
      setServerError(errorMessage(err));
    }
  };

  const busy = save.isPending || generate.isPending;

  return (
    <div>
      <PageHeader
        title={existing ? "Edit profile" : "Set up your profile"}
        subtitle="Your answers drive an explainable, rule-based workout plan. Saving regenerates your plan."
      />
      <form onSubmit={submit} className="grid gap-6 lg:grid-cols-2" noValidate>
        <Card title="About you">
          <div className="grid gap-4 sm:grid-cols-2">
            <Field label="Display name" error={errors.display_name}>
              <Input value={form.display_name ?? ""} onChange={(e) => update("display_name", e.target.value || null)} />
            </Field>
            <Field label="Age" error={errors.age} hint="Optional; used for calorie estimates">
              <Input type="number" inputMode="numeric" value={form.age ?? ""} onChange={(e) => update("age", numberOrNull(e.target.value))} />
            </Field>
            <Field label="Sex" hint="Optional; used only in the calorie equation">
              <Select value={form.sex} onChange={(e) => update("sex", e.target.value as ProfileInput["sex"])}>
                <option value="unspecified">Prefer not to say</option>
                <option value="female">Female</option>
                <option value="male">Male</option>
              </Select>
            </Field>
            <Field label="Height (cm)" error={errors.height_cm}>
              <Input type="number" value={form.height_cm ?? ""} onChange={(e) => update("height_cm", numberOrNull(e.target.value))} />
            </Field>
            <Field label="Weight (kg)" error={errors.weight_kg}>
              <Input type="number" value={form.weight_kg ?? ""} onChange={(e) => update("weight_kg", numberOrNull(e.target.value))} />
            </Field>
          </div>
        </Card>

        <Card title="Goal and experience">
          <div className="grid gap-4 sm:grid-cols-2">
            <Field label="Primary goal">
              <Select value={form.goal} onChange={(e) => update("goal", e.target.value as ProfileInput["goal"])}>
                {GOALS.map((g) => <option key={g} value={g}>{label(g)}</option>)}
              </Select>
            </Field>
            <Field label="Experience">
              <Select value={form.experience} onChange={(e) => update("experience", e.target.value as ProfileInput["experience"])}>
                {EXPERIENCE.map((x) => <option key={x} value={x}>{label(x)}</option>)}
              </Select>
            </Field>
            <Field label="Training days per week" error={errors.days_per_week}>
              <Select value={form.days_per_week} onChange={(e) => update("days_per_week", Number(e.target.value))}>
                {[1, 2, 3, 4, 5, 6].map((d) => <option key={d} value={d}>{d}</option>)}
              </Select>
            </Field>
            <Field label="Session length (minutes)" error={errors.session_minutes}>
              <Input type="number" min={10} max={120} value={form.session_minutes} onChange={(e) => update("session_minutes", Number(e.target.value))} />
            </Field>
          </div>
          <div className="mt-4 space-y-4">
            <Field label="Preferred days (optional)">
              <ChipToggle options={[0, 1, 2, 3, 4, 5, 6]} selected={form.preferred_days} onChange={(v) => update("preferred_days", v.sort())} render={(d) => WEEKDAYS[d].slice(0, 3)} />
            </Field>
          </div>
        </Card>

        <Card title="Equipment and exclusions">
          <div className="space-y-4">
            <Field label="Available equipment" hint="Biceps curl and shoulder press need dumbbells or a band">
              <ChipToggle options={EQUIPMENT} selected={form.equipment} onChange={(v) => update("equipment", v)} render={label} />
            </Field>
            <Field label="Exercises to exclude" error={errors.exclusions}>
              <ChipToggle options={EXERCISES} selected={form.exclusions} onChange={(v) => update("exclusions", v)} render={label} />
            </Field>
          </div>
        </Card>

        <Card title="Nutrition preferences">
          <div className="space-y-4">
            <Field label="Dietary preferences">
              <ChipToggle options={DIETS} selected={form.dietary_preferences} onChange={(v) => update("dietary_preferences", v)} render={label} />
            </Field>
            <Field label="Allergies to avoid">
              <ChipToggle options={ALLERGENS} selected={form.allergies} onChange={(v) => update("allergies", v)} render={label} />
            </Field>
          </div>
        </Card>

        <Card title="Health considerations" className="lg:col-span-2">
          <p className="mb-3 text-sm text-beige-300">
            Select any that apply. FitAI will keep plans at beginner intensity, avoid calorie targets where appropriate,
            and recommend consulting a qualified professional. This is not a medical screening.
          </p>
          <ChipToggle options={HEALTH_FLAGS} selected={form.health_flags} onChange={(v) => update("health_flags", v)} render={(f) => HEALTH_LABELS[f]} />
          {form.health_flags.length > 0 && (
            <div className="mt-4">
              <Alert tone="warning" title="Please consult a professional">
                With these circumstances, speak to a doctor, physiotherapist, or registered dietitian before starting a new
                exercise or nutrition routine.
              </Alert>
            </div>
          )}
        </Card>

        <div className="flex flex-wrap items-center gap-3 lg:col-span-2">
          {serverError && <div className="w-full"><Alert tone="error">{serverError}</Alert></div>}
          {Object.keys(errors).length > 0 && <div className="w-full"><Alert tone="error">Please fix the highlighted fields.</Alert></div>}
          <Button type="submit" disabled={busy}>{busy ? "Saving…" : plan.data ? "Save and regenerate plan" : "Save and generate plan"}</Button>
          {existing && <Button type="button" variant="secondary" onClick={() => navigate(-1)}>Cancel</Button>}
        </div>
      </form>
    </div>
  );
}
