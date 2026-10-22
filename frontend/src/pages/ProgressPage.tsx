import { useMemo, useState, type FormEvent } from "react";
import {
  Area, AreaChart, Bar, BarChart, CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from "recharts";

import { errorMessage } from "../api/client";
import { useProgressHistory, useProgressSummary, useSaveProgressRecord } from "../api/hooks";
import { label } from "../api/types";
import { CalendarIcon, ChartIcon, CheckIcon, FlameIcon, SparkIcon, TargetIcon } from "../components/icons";
import { Alert, Button, Card, Field, Input, PageHeader, Spinner, Stat, pct } from "../components/ui";

// Chart palette: plum + ember accents on the dark surface
const COLORS = ["#c9a9ff", "#e0a267", "#8b5cf6", "#f2c48b", "#f08aa8"];
const AXIS = { fill: "#a28b74", fontSize: 11 };
const toPct = (v: number | null) => (v == null ? null : Math.round(v * 100));

function Empty({ text }: { text: string }) {
  return <p className="py-10 text-center text-sm text-beige-400">{text}</p>;
}

export default function ProgressPage() {
  const summary = useProgressSummary();
  const history = useProgressHistory();
  const [exercise, setExercise] = useState<string | null>(null);

  const sessionData = useMemo(
    () =>
      (summary.data?.session_series ?? []).map((s, i) => ({
        name: `#${i + 1} ${s.date.slice(5)}`,
        completion: toPct(s.completion_rate),
        form: toPct(s.form_score),
        score: toPct(s.session_score),
        reps: s.repetitions,
      })),
    [summary.data],
  );

  if (summary.isLoading) return <Spinner />;
  if (summary.isError) return <Alert tone="error">{errorMessage(summary.error)}</Alert>;
  const s = summary.data!;
  const exerciseKeys = Object.keys(s.exercise_series);
  const activeExercise = exercise ?? exerciseKeys[0] ?? null;
  const exerciseData = activeExercise
    ? s.exercise_series[activeExercise].map((p, i) => ({ name: `#${i + 1} ${p.date.slice(5)}`, reps: p.repetitions, form: toPct(p.form_score) }))
    : [];
  const errorData = Object.entries(s.error_frequency).map(([k, v]) => ({ name: label(k), count: v })).sort((a, b) => b.count - a.count);

  return (
    <div className="space-y-6">
      <PageHeader title="Progress" subtitle="All values are computed by the FitAI server from your stored sessions." />
      <div className="stagger grid grid-cols-2 gap-4 md:grid-cols-5">
        <Stat label="Sessions" value={s.sessions_completed} icon={<CheckIcon />} />
        <Stat label="Total reps" value={s.total_repetitions} icon={<ChartIcon />} />
        <Stat label="Avg. completion" value={pct(s.average_completion_rate)} icon={<TargetIcon />} />
        <Stat label="Avg. form" value={pct(s.average_form_score)} icon={<SparkIcon />} />
        <Stat label="Consistency" value={pct(s.consistency_score)} hint={`last ${s.consistency_window_days} days`} icon={<FlameIcon />} />
      </div>

      <div className="grid gap-6 lg:grid-cols-2">
        <Card title="Session scores (%)" icon={<ChartIcon />}>
          {sessionData.length ? (
            <ResponsiveContainer width="100%" height={260}>
              <AreaChart data={sessionData} margin={{ left: -18, right: 8, top: 6 }}>
                <defs>
                  {[["gradScore", COLORS[0]], ["gradForm", COLORS[1]]].map(([id, c]) => (
                    <linearGradient key={id} id={id} x1="0" y1="0" x2="0" y2="1">
                      <stop offset="0%" stopColor={c} stopOpacity={0.45} />
                      <stop offset="100%" stopColor={c} stopOpacity={0} />
                    </linearGradient>
                  ))}
                </defs>
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis dataKey="name" tick={AXIS} tickLine={false} />
                <YAxis domain={[0, 100]} tick={AXIS} tickLine={false} />
                <Tooltip cursor={{ stroke: "rgba(201,169,255,0.35)" }} />
                <Legend wrapperStyle={{ fontSize: 12, color: "#c9b49c" }} />
                <Area type="monotone" dataKey="score" name="Session score" stroke={COLORS[0]} strokeWidth={2.5} fill="url(#gradScore)" connectNulls />
                <Area type="monotone" dataKey="form" name="Form" stroke={COLORS[1]} strokeWidth={2} fill="url(#gradForm)" connectNulls />
                <Line type="monotone" dataKey="completion" name="Completion" stroke={COLORS[2]} strokeWidth={2} dot={false} connectNulls />
              </AreaChart>
            </ResponsiveContainer>
          ) : <Empty text="No completed sessions yet." />}
        </Card>

        <Card
          title="Repetitions by exercise"
          action={exerciseKeys.length > 0 && (
            <select className="rounded border border-slate-300 px-2 py-1 text-sm" value={activeExercise ?? ""} onChange={(e) => setExercise(e.target.value)}>
              {exerciseKeys.map((k) => <option key={k} value={k}>{label(k)}</option>)}
            </select>
          )}
        >
          {exerciseData.length ? (
            <ResponsiveContainer width="100%" height={260}>
              <LineChart data={exerciseData} margin={{ left: -18, right: 8, top: 6 }}>
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis dataKey="name" tick={AXIS} tickLine={false} />
                <YAxis yAxisId="reps" tick={AXIS} tickLine={false} />
                <YAxis yAxisId="form" orientation="right" domain={[0, 100]} tick={AXIS} tickLine={false} />
                <Tooltip cursor={{ stroke: "rgba(201,169,255,0.35)" }} />
                <Legend wrapperStyle={{ fontSize: 12, color: "#c9b49c" }} />
                <Line yAxisId="reps" type="monotone" dataKey="reps" name="Reps" stroke={COLORS[0]} strokeWidth={2.5} dot={{ r: 3, fill: COLORS[0] }} />
                <Line yAxisId="form" type="monotone" dataKey="form" name="Form %" stroke={COLORS[1]} strokeWidth={2} connectNulls dot={false} />
              </LineChart>
            </ResponsiveContainer>
          ) : <Empty text="No exercise results yet." />}
        </Card>

        <Card title="Most frequent form issues" icon={<SparkIcon />}>
          {errorData.length ? (
            <ResponsiveContainer width="100%" height={240}>
              <BarChart data={errorData} layout="vertical" margin={{ left: 40 }}>
                <CartesianGrid strokeDasharray="3 3" horizontal={false} />
                <XAxis type="number" allowDecimals={false} tick={AXIS} tickLine={false} />
                <YAxis type="category" dataKey="name" width={120} tick={AXIS} tickLine={false} />
                <Tooltip cursor={{ fill: "rgba(201,169,255,0.08)" }} />
                <Bar dataKey="count" name="Reps affected" fill={COLORS[1]} radius={[0, 6, 6, 0]} barSize={14} />
              </BarChart>
            </ResponsiveContainer>
          ) : <Empty text="No form issues recorded." />}
        </Card>

        <WeightCard series={s.weight_series} />
      </div>

      <Card title="Adaptation history" icon={<SparkIcon />}>
        {history.isLoading && <Spinner />}
        {history.data?.adaptations.length ? (
          <ul className="divide-y divide-white/8 text-sm">
            {history.data.adaptations.map((a) => (
              <li key={a.id} className="py-3">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <span className="font-medium text-beige-100">
                    {new Date(a.created_at).toLocaleString()} · session #{a.session_id ?? "—"}
                  </span>
                  <span className="text-xs text-beige-400">
                    {a.new_plan_id ? `Plan #${a.old_plan_id} → #${a.new_plan_id}` : "No plan change"}
                  </span>
                </div>
                <ul className="mt-1 space-y-1 text-beige-300">
                  {(a.details.decisions ?? []).map((d, i) => (
                    <li key={i}><span className="mr-2 rounded bg-white/5 px-2 py-0.5 text-xs">{label(d.action)}</span>{d.reason}</li>
                  ))}
                </ul>
              </li>
            ))}
          </ul>
        ) : !history.isLoading && <Empty text="Your plan adapts after each completed session. Changes will appear here." />}
      </Card>

      <Card title="Session history" icon={<CalendarIcon />}>
        {history.data?.sessions.length ? (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead className="text-xs uppercase text-beige-400">
                <tr><th className="py-2 pr-4">Date</th><th className="pr-4">Duration</th><th className="pr-4">Completion</th><th className="pr-4">Form</th><th className="pr-4">Score</th><th>Exercises</th></tr>
              </thead>
              <tbody className="divide-y divide-white/8">
                {history.data.sessions.map((ss) => (
                  <tr key={ss.id}>
                    <td className="py-2 pr-4">{ss.completed_at ? new Date(ss.completed_at).toLocaleDateString() : "—"}{ss.ended_early && <span className="ml-1 text-xs text-ember-300">(stopped early)</span>}</td>
                    <td className="pr-4 tabular-nums">{ss.duration_seconds != null ? `${Math.round(ss.duration_seconds / 60)} min` : "—"}</td>
                    <td className="pr-4">{pct(ss.completion_rate)}</td>
                    <td className="pr-4">{pct(ss.form_score)}</td>
                    <td className="pr-4">{pct(ss.session_score)}</td>
                    <td className="text-beige-300">{ss.results.map((r) => `${r.exercise_name} ${r.repetitions}`).join(", ")}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : <Empty text="No sessions yet." />}
      </Card>
    </div>
  );
}

function WeightCard({ series }: { series: { date: string; weight_kg: number }[] }) {
  const save = useSaveProgressRecord();
  const [weight, setWeight] = useState("");
  const [error, setError] = useState<string | null>(null);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    const value = Number(weight);
    if (!weight || !Number.isFinite(value) || value < 30 || value > 300) {
      setError("Enter a weight between 30 and 300 kg.");
      return;
    }
    setError(null);
    try {
      const d = new Date();
      const date = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
      await save.mutateAsync({ date, weight_kg: value, notes: "" });
      setWeight("");
    } catch (err) {
      setError(errorMessage(err));
    }
  };

  return (
    <Card title="Body weight (optional)" icon={<ChartIcon />}>
      {series.length ? (
        <ResponsiveContainer width="100%" height={180}>
          <LineChart data={series} margin={{ left: -18, right: 8, top: 6 }}>
            <CartesianGrid strokeDasharray="3 3" />
            <XAxis dataKey="date" tick={AXIS} tickLine={false} />
            <YAxis domain={["dataMin - 2", "dataMax + 2"]} tick={AXIS} tickLine={false} />
            <Tooltip cursor={{ stroke: "rgba(201,169,255,0.35)" }} />
            <Line type="monotone" dataKey="weight_kg" name="kg" stroke={COLORS[2]} strokeWidth={2.5} dot={{ r: 3, fill: COLORS[2] }} />
          </LineChart>
        </ResponsiveContainer>
      ) : <p className="mb-3 text-sm text-beige-400">Log your weight if it is useful to you. It is never required.</p>}
      <form onSubmit={submit} className="mt-3 flex items-end gap-2" noValidate>
        <Field label="Today's weight (kg)" error={error ?? undefined}>
          <Input type="number" step="0.1" value={weight} onChange={(e) => setWeight(e.target.value)} />
        </Field>
        <Button type="submit" variant="secondary" disabled={save.isPending}>Save</Button>
      </form>
    </Card>
  );
}
