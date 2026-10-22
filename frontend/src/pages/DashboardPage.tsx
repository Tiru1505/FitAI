import { useMemo } from "react";
import { Link } from "react-router-dom";

import { errorMessage } from "../api/client";
import { useMe, useModelStatus, useProgressSummary, useToday } from "../api/hooks";
import { label } from "../api/types";
import { CalendarIcon, ChartIcon, CheckIcon, ExerciseMark, FlameIcon, SparkIcon, TargetIcon } from "../components/icons";
import { Alert, Button, Card, Gauge, MiniBars, SkeletonBlock, Sparkline, Spinner, Stat, pct } from "../components/ui";

const PLUM = "#c9a9ff";
const EMBER = "#e0a267";

export default function DashboardPage() {
  const me = useMe();
  const today = useToday();
  const summary = useProgressSummary();
  const models = useModelStatus();
  const name = me.data?.profile?.display_name;

  const series = summary.data?.session_series ?? [];
  const scores = series.map((s) => (s.session_score ?? 0) * 100);
  const repSeries = series.map((s) => s.repetitions);
  const formScores = series.map((s) => (s.form_score ?? 0) * 100);
  const completion = series.map((s) => (s.completion_rate ?? 0) * 100);

  /** Repetitions per day over the last week, for the weekly bar strip. */
  const weekBars = useMemo(() => {
    const days = Array.from({ length: 7 }, (_, i) => {
      const d = new Date();
      d.setDate(d.getDate() - (6 - i));
      return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
    });
    return days.map((day) => series.filter((s) => s.date === day).reduce((sum, s) => sum + s.repetitions, 0));
  }, [series]);

  const overall = summary.data?.average_session_score ?? summary.data?.consistency_score ?? 0;

  return (
    <div className="space-y-5">
      {/* Hero banner — the warm panel the rest of the layout hangs from */}
      <section className="glass relative overflow-hidden rounded-[1.75rem] px-6 py-7 animate-fade-up">
        <div aria-hidden className="pointer-events-none absolute inset-0 -z-10">
          <div className="animate-drift absolute -left-16 -top-24 h-72 w-72 rounded-full bg-plum-500/25 blur-3xl" />
          <div className="animate-drift absolute -bottom-28 right-0 h-80 w-80 rounded-full bg-ember-500/20 blur-3xl" style={{ animationDelay: "-8s" }} />
        </div>
        <div className="flex flex-wrap items-end justify-between gap-5">
          <div>
            <p className="text-xs uppercase tracking-[0.18em] text-plum-300">
              {new Date().toLocaleDateString(undefined, { weekday: "long", day: "numeric", month: "long" })}
            </p>
            <h1 className="mt-1.5 text-3xl font-semibold tracking-tight text-beige-100">
              {name ? `Hey ${name}, ready to move?` : "Ready to move?"}
            </h1>
            <p className="mt-1.5 max-w-xl text-sm text-beige-300">
              {today.data?.is_training_day
                ? "Today is a training day. Your plan is below — start when you are warmed up."
                : today.data
                  ? `Rest day. Your next session is ${today.data.next_training_date ?? "coming up"}.`
                  : "Set up a plan to get started."}
            </p>
          </div>
          <div className="flex gap-2">
            <Link to="/session"><Button>Start workout</Button></Link>
            <Link to="/plan"><Button variant="secondary">View plan</Button></Link>
          </div>
        </div>
      </section>

      {me.data?.profile?.health_flags.length ? (
        <Alert tone="warning">You reported health considerations. Please check with a qualified professional before training.</Alert>
      ) : null}

      {summary.isLoading && (
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
          {[0, 1, 2, 3].map((i) => <SkeletonBlock key={i} className="h-40" />)}
        </div>
      )}
      {summary.isError && <Alert tone="error">{errorMessage(summary.error)}</Alert>}

      {summary.data && (
        <div className="stagger grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
          <Stat
            label="Sessions" value={summary.data.sessions_completed} icon={<CheckIcon />}
            hint={summary.data.last_session_at ? `Last: ${new Date(summary.data.last_session_at).toLocaleDateString()}` : "No sessions yet"}
            chart={<MiniBars values={weekBars} color={EMBER} />}
          />
          <Stat
            label="Total reps" value={summary.data.total_repetitions.toLocaleString()} icon={<ChartIcon />}
            hint="Across all completed sessions" tone="ember"
            chart={<Sparkline values={repSeries.length > 1 ? repSeries : [0, 0]} stroke={EMBER} />}
          />
          <Stat
            label="Avg. completion" value={pct(summary.data.average_completion_rate)} icon={<TargetIcon />}
            hint="Planned work actually finished"
            chart={<Sparkline values={completion.length > 1 ? completion : [0, 0]} stroke={PLUM} />}
          />
          <Stat
            label="Avg. form score" value={pct(summary.data.average_form_score)} icon={<SparkIcon />}
            hint="Live camera sessions only"
            chart={<Sparkline values={formScores.length > 1 ? formScores : [0, 0]} stroke={PLUM} />}
          />
        </div>
      )}

      <div className="grid gap-5 lg:grid-cols-3">
        <Card
          title="Today's workout" icon={<CalendarIcon />} className="lg:col-span-2"
          subtitle={today.data?.day ? `${today.data.day.weekday_name} · day ${today.data.day.day_index + 1}` : undefined}
          action={<Link to="/plan" className="text-sm font-medium text-plum-300 transition-colors hover:text-plum-200">Full plan →</Link>}
        >
          {today.isLoading && <Spinner />}
          {today.isError && <Alert tone="error">{errorMessage(today.error)}</Alert>}
          {today.data === null && (
            <div className="space-y-3">
              <p className="text-sm text-beige-300">You don't have a workout plan yet.</p>
              <Link to="/profile"><Button>Generate a plan</Button></Link>
            </div>
          )}
          {today.data && !today.data.is_training_day && (
            <p className="text-sm text-beige-300">
              Rest day. Next training day: <strong className="text-beige-100">{today.data.next_training_date ?? "—"}</strong>.
            </p>
          )}
          {today.data?.day && (
            <div className="space-y-4">
              {today.data.completed_today && <Alert tone="success">You've completed a session today. Nice work!</Alert>}
              <ul className="stagger space-y-2">
                {today.data.day.exercises.map((pe) => (
                  <li
                    key={pe.id}
                    className="group flex items-center justify-between gap-3 rounded-2xl border border-beige-100/8 bg-white/5 px-3 py-2.5 text-sm transition-all duration-200 hover:border-plum-400/30 hover:bg-plum-500/10"
                  >
                    <span className="flex items-center gap-3 font-medium text-beige-100">
                      <span className="grid h-10 w-10 place-items-center rounded-xl bg-plum-500/15 text-plum-300 ring-1 ring-plum-400/20 transition-transform duration-300 group-hover:scale-105 [&>svg]:h-5 [&>svg]:w-5">
                        <ExerciseMark slug={pe.exercise.slug} />
                      </span>
                      {pe.exercise.name}
                      {pe.practice_mode && <span className="rounded-full bg-ember-500/20 px-2 py-0.5 text-xs text-ember-300">Practice mode</span>}
                    </span>
                    <span className="shrink-0 tabular-nums text-beige-400">{pe.sets} × {pe.repetitions} · rest {pe.rest_seconds}s</span>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </Card>

        <Card title="Overall state" icon={<FlameIcon />} subtitle="Consistency and session quality">
          <Gauge value={overall} caption={summary.data ? `${pct(summary.data.consistency_score)} of planned sessions kept` : undefined} />
          <div className="mt-3 grid grid-cols-2 gap-3 text-center">
            <div className="rounded-2xl bg-white/5 p-3">
              <p className="text-xs text-beige-400">Consistency</p>
              <p className="mt-0.5 text-lg font-semibold tabular-nums text-beige-100">{pct(summary.data?.consistency_score)}</p>
            </div>
            <div className="rounded-2xl bg-white/5 p-3">
              <p className="text-xs text-beige-400">Missed (7d)</p>
              <p className="mt-0.5 text-lg font-semibold tabular-nums text-beige-100">{summary.data?.missed_sessions_last_7_days ?? "—"}</p>
            </div>
          </div>
          <p className="mt-3 text-center text-xs text-beige-400">
            {summary.data?.sessions_completed ? "Balanced energy & recovery state" : "Complete a session to build this picture"}
          </p>
        </Card>

        <Card title="Session scores" icon={<ChartIcon />} subtitle="Every completed session, most recent last" className="lg:col-span-2">
          {scores.length > 1 ? (
            <>
              <Sparkline values={scores} stroke={PLUM} height={128} />
              <div className="mt-3 flex items-center justify-between text-xs text-beige-400">
                <span>{series[0]?.date}</span>
                <span>Latest <strong className="text-beige-100">{pct(series.at(-1)?.session_score ?? null)}</strong></span>
                <span>{series.at(-1)?.date}</span>
              </div>
            </>
          ) : (
            <p className="py-10 text-center text-sm text-beige-400">
              Two sessions are needed before a trend appears. <Link to="/session" className="text-plum-300 underline">Start one</Link>.
            </p>
          )}
        </Card>

        <Card title="Latest feedback" icon={<SparkIcon />}>
          {summary.data?.latest_feedback.length ? (
            <ul className="stagger space-y-2 text-sm text-beige-200">
              {summary.data.latest_feedback.slice(0, 5).map((f) => (
                <li key={f} className="rounded-xl border border-beige-100/8 bg-white/5 px-3 py-2">{f}</li>
              ))}
            </ul>
          ) : (
            <p className="text-sm text-beige-400">Complete a session to see form feedback here.</p>
          )}
        </Card>
      </div>

      {models.data && !models.data.exercise_classifier.available && (
        <Alert tone="info" title="Exercise recognition model not loaded">
          Repetitions and form checks use transparent joint-angle rules for the exercise you select. Train and export the
          BiLSTM model (see the ML README) to enable automatic exercise recognition. Status: {label(models.data.exercise_classifier.status)}.
        </Alert>
      )}
    </div>
  );
}
