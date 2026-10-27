import { useCallback, useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";

import { errorMessage, tokenStore } from "../api/client";
import { useCompleteSession, useMe, usePlan, useStartSession, useToday, type CompletePayload } from "../api/hooks";
import {
  label, type ExerciseLiveTotals, type ExerciseSlug, type LiveAnalysis, type PlannedExercise,
  type SessionCompleteResponse, type WorkoutSession,
} from "../api/types";
import { CameraIcon, DumbbellIcon, ExerciseMark, TargetIcon } from "../components/icons";
import { SafetyNotice } from "../components/SafetyNotice";
import { Alert, Button, Card, Field, Input, PageHeader, Select, Spinner, Stat, pct } from "../components/ui";
import { LiveInferenceClient } from "../lib/liveSocket";
import {
  CAMERA_PRESETS, PoseTracker, applyZoom, cameraErrorMessage, checkFraming, drawSkeleton, listCameras,
  startCamera, stopCamera, streamResolution, zoomCapability,
  type CameraPresetId, type FramingCheck, type ZoomCapability,
} from "../lib/pose";

const FRAME_INTERVAL_MS = 66; // ~15 fps sent for analysis

const STATUS_STYLE: Record<LiveAnalysis["form_status"], { text: string; className: string; color: string }> = {
  not_started: { text: "Waiting for start position", className: "bg-white/5 text-beige-200", color: "#94a3b8" },
  good: { text: "Good form", className: "bg-emerald-500/20 text-emerald-200", color: "#22c55e" },
  minor_error: { text: "Minor form issue", className: "bg-ember-500/20 text-ember-300", color: "#f59e0b" },
  major_error: { text: "Form issue", className: "bg-red-100 text-red-800", color: "#ef4444" },
  uncertain: { text: "Uncertain: body not clearly visible", className: "bg-white/10 text-beige-200", color: "#64748b" },
};

type Stage = "intro" | "active" | "finish" | "done";

export default function LiveSessionPage() {
  const me = useMe();
  const today = useToday();
  const startSession = useStartSession();
  const [stage, setStage] = useState<Stage>("intro");
  const [session, setSession] = useState<WorkoutSession | null>(null);
  const [exercises, setExercises] = useState<PlannedExercise[]>([]);
  const [totals, setTotals] = useState<Record<string, ExerciseLiveTotals>>({});
  const [result, setResult] = useState<SessionCompleteResponse | null>(null);
  const [endedEarly, setEndedEarly] = useState(false);

  if (me.isLoading || today.isLoading) return <Spinner />;
  if (!me.data?.profile?.safety_acknowledged_at) return <SafetyNotice />;
  if (today.isError) return <Alert tone="error">{errorMessage(today.error)}</Alert>;
  if (!today.data) {
    return (
      <Card title="No plan yet">
        <Link to="/profile"><Button>Create your plan</Button></Link>
      </Card>
    );
  }

  const begin = async (dayIndex: number, list: PlannedExercise[]) => {
    let s: WorkoutSession;
    try {
      s = await startSession.mutateAsync({ plan_id: today.data!.plan_id, day_index: dayIndex });
    } catch {
      return; // shown via startSession.error
    }
    setSession(s);
    setExercises(list);
    setTotals({});
    setStage("active");
  };

  if (stage === "intro") return <IntroStage today={today.data} onStart={begin} busy={startSession.isPending} error={startSession.error} />;
  if (stage === "active" && session) {
    return (
      <ActiveStage
        session={session}
        exercises={exercises}
        totals={totals}
        onTotals={(t) => setTotals((prev) => ({ ...prev, [t.exercise]: t }))}
        onFinish={(early) => {
          setEndedEarly(early);
          setStage("finish");
        }}
      />
    );
  }
  if (stage === "finish" && session) {
    return (
      <FinishStage
        session={session}
        exercises={exercises}
        totals={totals}
        endedEarly={endedEarly}
        onDone={(r) => {
          setResult(r);
          setStage("done");
        }}
      />
    );
  }
  if (stage === "done" && result) return <DoneStage result={result} />;
  return null;
}

/* ------------------------------------------------------------------------------------------ */

function IntroStage({ today, onStart, busy, error }: {
  today: NonNullable<ReturnType<typeof useToday>["data"]>;
  onStart: (dayIndex: number, list: PlannedExercise[]) => void;
  busy: boolean;
  error: unknown;
}) {  // prettier-ignore
  const [chosenDay, setChosenDay] = useState<number>(today.day?.day_index ?? 0);
  const dayList = today.day?.day_index === chosenDay ? today.day.exercises : null;

  return (
    <div className="space-y-6">
      <PageHeader title="Live session" subtitle="Pose landmarks are extracted in your browser; only landmark numbers are sent for analysis." />
      {!today.is_training_day && (
        <Alert tone="info">Today is a rest day in your plan. You can still do an extra session for one of your plan days: it will be recorded and can adapt that day's exercises.</Alert>
      )}
      <Card title={today.day ? `Today: ${today.day.weekday_name}` : "Choose a workout day"}>
        {!today.day && <DayPicker planId={today.plan_id} value={chosenDay} onChange={setChosenDay} />}
        {dayList && (
          <ul className="mb-4 divide-y divide-white/8 text-sm">
            {dayList.map((pe) => (
              <li key={pe.id} className="flex justify-between py-2">
                <span>{pe.exercise.name}</span>
                <span className="tabular-nums text-beige-400">{pe.sets} × {pe.repetitions}</span>
              </li>
            ))}
          </ul>
        )}
        {error != null && <div className="mb-3"><Alert tone="error">{errorMessage(error)}</Alert></div>}
        <DayStarter planId={today.plan_id} dayIndex={chosenDay} preset={dayList} onStart={onStart} busy={busy} />
      </Card>
    </div>
  );
}

function DayPicker({ planId, value, onChange }: { planId: number; value: number; onChange: (d: number) => void }) {
  const plan = usePlan(planId);
  if (!plan.data) return <Spinner />;
  return (
    <div className="mb-4 max-w-xs">
      <Field label="Workout day">
        <Select value={value} onChange={(e) => onChange(Number(e.target.value))}>
          {plan.data.days.map((d) => <option key={d.day_index} value={d.day_index}>Day {d.day_index + 1} ({d.weekday_name})</option>)}
        </Select>
      </Field>
    </div>
  );
}

function DayStarter({ planId, dayIndex, preset, onStart, busy }: {
  planId: number; dayIndex: number; preset: PlannedExercise[] | null;
  onStart: (dayIndex: number, list: PlannedExercise[]) => void; busy: boolean;
}) {  // prettier-ignore
  const plan = usePlan(preset ? null : planId);
  const list = preset ?? plan.data?.days[dayIndex]?.exercises ?? null;
  if (!list) return <Spinner />;
  return (
    <>
      {!preset && (
        <ul className="mb-4 divide-y divide-white/8 text-sm">
          {list.map((pe) => (
            <li key={pe.id} className="flex justify-between py-2"><span>{pe.exercise.name}</span><span className="tabular-nums text-beige-400">{pe.sets} × {pe.repetitions}</span></li>
          ))}
        </ul>
      )}
      <Button disabled={busy} onClick={() => onStart(dayIndex, list)}>{busy ? "Starting…" : "Start session"}</Button>
    </>
  );
}

/* ------------------------------------------------------------------------------------------ */

function ActiveStage({ session, exercises, totals, onTotals, onFinish }: {
  session: WorkoutSession; exercises: PlannedExercise[]; totals: Record<string, ExerciseLiveTotals>;
  onTotals: (t: ExerciseLiveTotals) => void; onFinish: (endedEarly: boolean) => void;
}) {  // prettier-ignore
  const videoRef = useRef<HTMLVideoElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const trackerRef = useRef<PoseTracker | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const clientRef = useRef<LiveInferenceClient | null>(null);
  const rafRef = useRef<number | null>(null);
  const lastSentRef = useRef(0);
  const setActiveRef = useRef(false);
  const colorRef = useRef(STATUS_STYLE.not_started.color);

  const [selected, setSelected] = useState<ExerciseSlug>(exercises[0]?.exercise.slug ?? "squat");
  const [cameraState, setCameraState] = useState<"off" | "starting" | "on">("off");
  const [setActive, setSetActive] = useState(false);
  const [analysis, setAnalysis] = useState<LiveAnalysis | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [modelNote, setModelNote] = useState<string | null>(null);
  const [restLeft, setRestLeft] = useState(0);
  const [dropped, setDropped] = useState({ captured: 0, dropped: 0 });
  const [cameras, setCameras] = useState<MediaDeviceInfo[]>([]);
  const [deviceId, setDeviceId] = useState<string>(() => localStorage.getItem("fitai.camera.device") ?? "");
  const [preset, setPreset] = useState<CameraPresetId>(() => (localStorage.getItem("fitai.camera.preset") as CameraPresetId) ?? "hd");
  const [zoom, setZoom] = useState<ZoomCapability | null>(null);
  const [resolution, setResolution] = useState<{ width: number; height: number } | null>(null);
  const [framing, setFraming] = useState<FramingCheck | null>(null);
  const [repPulse, setRepPulse] = useState(0);
  const lastRepRef = useRef(0);

  const planned = exercises.find((e) => e.exercise.slug === selected);

  const stopLoop = () => {
    if (rafRef.current != null) cancelAnimationFrame(rafRef.current);
    rafRef.current = null;
  };

  const stopEverything = useCallback(() => {
    stopLoop();
    setActiveRef.current = false;
    setSetActive(false);
    clientRef.current?.close();
    clientRef.current = null;
    stopCamera(streamRef.current, videoRef.current);
    streamRef.current = null;
    const ctx = canvasRef.current?.getContext("2d");
    if (ctx) drawSkeleton(ctx, null, "#000");
    setCameraState("off");
  }, []);

  useEffect(() => () => {
    stopEverything();
    trackerRef.current?.close();
    trackerRef.current = null;
  }, [stopEverything]);

  useEffect(() => {
    if (restLeft <= 0) return;
    const t = setTimeout(() => setRestLeft((r) => r - 1), 1000);
    return () => clearTimeout(t);
  }, [restLeft]);

  const loop = () => {
    const video = videoRef.current, canvas = canvasRef.current, tracker = trackerRef.current;
    if (video && canvas && tracker && video.readyState >= 2) {
      const now = performance.now();
      if (now - lastSentRef.current >= FRAME_INTERVAL_MS) {
        lastSentRef.current = now;
        if (canvas.width !== video.videoWidth) {
          canvas.width = video.videoWidth;
          canvas.height = video.videoHeight;
        }
        const landmarks = tracker.detect(video, now);
        const ctx = canvas.getContext("2d");
        if (ctx) drawSkeleton(ctx, landmarks, colorRef.current);
        setFraming(checkFraming(landmarks));
        const client = clientRef.current;
        if (setActiveRef.current && client) {
          client.sendFrame(landmarks, video.videoWidth, video.videoHeight, Math.round(now));
          setDropped({ captured: client.stats.frames_captured, dropped: client.stats.frames_dropped });
        }
      }
    }
    rafRef.current = requestAnimationFrame(loop);
  };

  const startCam = async () => {
    setError(null);
    setCameraState("starting");
    try {
      if (!trackerRef.current) trackerRef.current = await PoseTracker.create();
      streamRef.current = await startCamera(videoRef.current!, { deviceId: deviceId || undefined, preset });
      setResolution(streamResolution(streamRef.current));
      setZoom(zoomCapability(streamRef.current));
      setCameras(await listCameras());
      const token = tokenStore.get();
      if (!token) throw new Error("You are signed out.");
      const client = new LiveInferenceClient(token, {
        onAnalysis: (a) => {
          colorRef.current = STATUS_STYLE[a.form_status].color;
          if (a.repetition_count > lastRepRef.current) setRepPulse((n) => n + 1);
          lastRepRef.current = a.repetition_count;
          setAnalysis(a);
        },
        onError: (m) => setError(m),
        onClose: () => {
          if (setActiveRef.current) setError("Connection to the analysis server was lost. The current set was not saved.");
          setActiveRef.current = false;
          setSetActive(false);
        },
      });
      await client.connect();
      clientRef.current = client;
      setCameraState("on");
      stopLoop();
      rafRef.current = requestAnimationFrame(loop);
    } catch (err) {
      stopEverything();
      setError(err instanceof DOMException || (err instanceof Error && err.message.includes("Camera")) ? cameraErrorMessage(err) : errorMessage(err));
    }
  };

  /** Swap camera or resolution without dropping the analysis socket. */
  const restartCamera = async (next: { deviceId?: string; preset?: CameraPresetId }) => {
    if (next.deviceId !== undefined) {
      setDeviceId(next.deviceId);
      localStorage.setItem("fitai.camera.device", next.deviceId);
    }
    if (next.preset !== undefined) {
      setPreset(next.preset);
      localStorage.setItem("fitai.camera.preset", next.preset);
    }
    if (cameraState !== "on") return;
    try {
      stopCamera(streamRef.current, videoRef.current);
      streamRef.current = await startCamera(videoRef.current!, {
        deviceId: (next.deviceId ?? deviceId) || undefined,
        preset: next.preset ?? preset,
      });
      setResolution(streamResolution(streamRef.current));
      setZoom(zoomCapability(streamRef.current));
    } catch (err) {
      setError(cameraErrorMessage(err));
      stopEverything();
    }
  };

  const changeZoom = async (value: number) => {
    setZoom((z) => (z ? { ...z, value } : z));
    try {
      await applyZoom(streamRef.current, value);
    } catch {
      /* camera rejected the zoom value */
    }
  };

  const beginSet = async () => {
    const client = clientRef.current;
    if (!client) return;
    setError(null);
    try {
      const ready = await client.configure(selected, session.id);
      const clf = ready.model_status.exercise_classifier;
      setModelNote(clf.available ? null : "Recognition model not loaded: analysing the exercise you selected with joint-angle rules.");
      setAnalysis(null);
      setRestLeft(0);
      lastRepRef.current = 0;
      setActiveRef.current = true;
      setSetActive(true);
    } catch (err) {
      setError(errorMessage(err));
    }
  };

  const endSet = async (save: boolean) => {
    const client = clientRef.current;
    setActiveRef.current = false;
    setSetActive(false);
    if (!client) return;
    try {
      const summary = await client.endSet(save);
      if (summary.session_exercise_totals) onTotals(summary.session_exercise_totals);
      if (save && planned) setRestLeft(planned.rest_seconds);
    } catch (err) {
      setError(errorMessage(err));
    }
  };

  const stopSession = async () => {
    if (setActiveRef.current) await endSet(true);
    stopEverything();
    onFinish(true);
  };

  const finish = async () => {
    if (setActiveRef.current) await endSet(true);
    stopEverything();
    onFinish(false);
  };

  const status = analysis ? STATUS_STYLE[analysis.form_status] : null;
  const target = planned ? planned.repetitions : null;

  // Which joints an exercise needs: legs for squats and lunges, upper body for the rest.
  const needsLegs = selected === "squat" || selected === "lunge";
  const framingOk = !!framing && framing.shoulders && framing.hips && (!needsLegs || (framing.knees && framing.ankles));
  const framingHint = !framing
    ? "No person detected yet. Step into view of the camera."
    : framingOk
      ? framing.insideFrame
        ? "Good framing."
        : "You are close to the edge of the picture. Move to the centre or step back a little."
      : !framing.shoulders || !framing.hips
        ? "Move back so your shoulders and hips are both visible."
        : "Your legs are out of frame. Step back, tilt the camera down, or raise it higher. A wider capture size can also help.";

  return (
    <div className="space-y-4">
      <PageHeader
        title="Live session"
        subtitle={`Session #${session.id}`}
        action={<Button variant="danger" onClick={stopSession}>Stop session</Button>}
      />
      {error && <Alert tone="error">{error}</Alert>}
      {modelNote && setActive && <Alert tone="info">{modelNote}</Alert>}

      <div className="grid gap-4 lg:grid-cols-3">
        <div className="space-y-3 lg:col-span-2">
          <div className="relative aspect-[4/3] overflow-hidden rounded-2xl bg-brand-900 shadow-lg shadow-brand-900/20">
            {setActive && (
              <span aria-hidden className="absolute left-3 top-3 z-10 flex items-center gap-2 rounded-full bg-black/55 px-2.5 py-1 text-xs font-medium text-white backdrop-blur-sm">
                <span className="animate-halo h-2 w-2 rounded-full bg-rose-400" />
                Recording set
              </span>
            )}
            {setActive && analysis && !analysis.calibrated && (
              <span className="absolute left-3 top-11 z-10 flex items-center gap-2 rounded-full bg-plum-500/80 px-2.5 py-1 text-xs font-medium text-white backdrop-blur-sm">
                <span className="h-2 w-2 animate-pulse rounded-full bg-white/90" />
                Learning your range — do a full first rep
              </span>
            )}
            <video ref={videoRef} className="absolute inset-0 h-full w-full -scale-x-100 object-cover" playsInline muted />
            <canvas ref={canvasRef} className="absolute inset-0 h-full w-full -scale-x-100 object-cover" />
            {cameraState !== "on" && (
              <div className="absolute inset-0 flex flex-col items-center justify-center gap-3 p-6 text-center text-beige-200">
                {cameraState === "starting" ? <Spinner label="Starting camera and pose model…" /> : (
                  <>
                    <p className="text-sm">Place the camera so your whole body is visible (side view works best for squats and push-ups).</p>
                    <Button onClick={startCam}>Enable camera</Button>
                    <p className="text-xs text-beige-500">The browser will ask for camera permission. Video stays on this device.</p>
                  </>
                )}
              </div>
            )}
            {setActive && analysis && (
              <div className="pointer-events-none absolute inset-x-0 top-0 flex items-start justify-between p-3">
                <div className="rounded-2xl bg-black/60 px-4 py-2 text-white backdrop-blur-sm">
                  <p className="text-xs uppercase tracking-wide text-beige-400">Reps</p>
                  <p key={repPulse} className="animate-pop text-4xl font-bold tabular-nums">
                    {analysis.repetition_count}
                    {target ? <span className="text-lg text-beige-400"> / {target}</span> : null}
                  </p>
                  {target ? (
                    <span className="mt-1 block h-1 w-24 overflow-hidden rounded-full bg-white/25">
                      <span
                        className="block h-full rounded-full bg-gradient-to-r from-brand-300 to-brand-500 transition-[width] duration-500 ease-out"
                        style={{ width: `${Math.min(100, (analysis.repetition_count / target) * 100)}%` }}
                      />
                    </span>
                  ) : null}
                </div>
                {status && (
                  <span className={`rounded-full px-3 py-1 text-sm font-medium shadow-sm transition-colors duration-300 ${status.className}`}>
                    {status.text}
                  </span>
                )}
              </div>
            )}
            {setActive && analysis && (
              <div className="absolute inset-x-0 bottom-0 bg-gradient-to-t from-black/75 to-black/40 px-4 py-3 text-center text-lg font-medium text-white backdrop-blur-sm" aria-live="polite">
                <span key={analysis.feedback} className="animate-fade-up inline-block">{analysis.feedback}</span>
              </div>
            )}
            {cameraState === "on" && !setActive && framing && !framingOk && (
              <div className="absolute inset-x-0 bottom-0 bg-amber-500/90 px-4 py-2 text-center text-sm font-medium text-amber-950">
                {framingHint}
              </div>
            )}
          </div>

          <div className="flex flex-wrap items-center gap-2">
            {cameraState === "on" && !setActive && <Button onClick={beginSet}>Start set</Button>}
            {setActive && <Button onClick={() => endSet(true)}>End set</Button>}
            {setActive && <Button variant="secondary" onClick={() => endSet(false)}>Discard set</Button>}
            {cameraState === "on" && <Button variant="secondary" onClick={stopEverything}>Turn camera off</Button>}
            {restLeft > 0 && <span className="rounded-lg bg-plum-500/12 px-3 py-2 text-sm text-sky-800">Rest: {restLeft}s</span>}
          </div>
        </div>

        <div className="space-y-4">
          {cameraState === "on" && (
            <Card title="Camera" icon={<CameraIcon />}>
              <div className="space-y-3">
                {cameras.length > 1 && (
                  <Field label="Camera">
                    <Select value={deviceId} onChange={(e) => restartCamera({ deviceId: e.target.value })}>
                      <option value="">Default camera</option>
                      {cameras.map((c, i) => (
                        <option key={c.deviceId} value={c.deviceId}>{c.label || `Camera ${i + 1}`}</option>
                      ))}
                    </Select>
                  </Field>
                )}
                <Field
                  label="Capture size"
                  hint={resolution ? `Now capturing ${resolution.width}x${resolution.height}. A 16:9 size is usually wider than 4:3.` : undefined}
                >
                  <Select value={preset} onChange={(e) => restartCamera({ preset: e.target.value as CameraPresetId })}>
                    {CAMERA_PRESETS.map((c) => <option key={c.id} value={c.id}>{c.label}</option>)}
                  </Select>
                </Field>
                {zoom && zoom.max > zoom.min && (
                  <Field label={`Zoom (${zoom.value.toFixed(1)}x) — lower fits more of you in frame`}>
                    <input
                      type="range" className="w-full" min={zoom.min} max={zoom.max} step={zoom.step}
                      value={zoom.value} onChange={(e) => changeZoom(Number(e.target.value))}
                    />
                  </Field>
                )}
                <div>
                  <p className="mb-1 text-sm font-medium text-beige-200">In frame</p>
                  <div className="flex flex-wrap gap-2">
                    {([["Shoulders", framing?.shoulders], ["Hips", framing?.hips], ["Knees", framing?.knees], ["Ankles", framing?.ankles]] as const).map(
                      ([label, ok]) => (
                        <span key={label} className={`rounded-full px-2 py-0.5 text-xs ${ok ? "bg-emerald-500/20 text-emerald-200" : "bg-white/10 text-beige-300"}`}>
                          {ok ? "✓" : "✗"} {label}
                        </span>
                      ),
                    )}
                  </div>
                  <p className="mt-2 text-xs text-beige-400">{framingHint}</p>
                </div>
              </div>
            </Card>
          )}
          <Card title="Exercise" icon={<DumbbellIcon />}>
            <Field label="Current exercise">
              <Select value={selected} disabled={setActive} onChange={(e) => setSelected(e.target.value as ExerciseSlug)}>
                {exercises.map((pe) => <option key={pe.id} value={pe.exercise.slug}>{pe.exercise.name}</option>)}
              </Select>
            </Field>
            {planned && (
              <p className="mt-2 text-sm text-beige-300">
                Target: {planned.sets} sets × {planned.repetitions} reps, {planned.rest_seconds}s rest.
                {planned.practice_mode && <span className="block text-ember-300">Practice mode: move slowly and focus on technique.</span>}
              </p>
            )}
            {planned && <ul className="mt-2 list-disc pl-5 text-xs text-beige-400">{planned.exercise.form_cues.map((c) => <li key={c}>{c}</li>)}</ul>}
          </Card>

          {setActive && analysis && (
            <Card title="Live analysis" icon={<TargetIcon />}>
              <dl className="grid grid-cols-2 gap-x-3 gap-y-2 text-sm">
                <dt className="text-beige-400">Recognised as</dt>
                <dd>
                  {analysis.recognition_source === "model"
                    ? analysis.exercise === "uncertain" ? "Not sure" : analysis.exercise === "collecting_frames" ? "Collecting frames…" : label(analysis.exercise)
                    : `${label(analysis.expected_exercise)} (selected)`}
                </dd>
                <dt className="text-beige-400">Confidence</dt><dd>{analysis.confidence == null ? "n/a" : pct(analysis.confidence)}</dd>
                <dt className="text-beige-400">Phase</dt><dd>{label(analysis.phase)}</dd>
                <dt className="text-beige-400">Joint angle</dt><dd className="tabular-nums">{analysis.angle == null ? "—" : `${analysis.angle}°`}</dd>
                <dt className="text-beige-400">Partial reps</dt><dd className="tabular-nums">{analysis.partial_repetitions}</dd>
                <dt className="text-beige-400">Form score</dt><dd>{pct(analysis.form_score)}</dd>
                <dt className="text-beige-400">Calibration</dt>
                <dd>{analysis.calibrated ? "Matched to your range" : "Learning…"}</dd>
                <dt className="text-beige-400">Server time</dt><dd className="tabular-nums">{analysis.processing_ms.toFixed(1)} ms</dd>
                <dt className="text-beige-400">Dropped frames</dt><dd className="tabular-nums">{dropped.captured ? pct(dropped.dropped / dropped.captured) : "—"}</dd>
              </dl>
            </Card>
          )}

          <Card title="Recorded this session" icon={<ExerciseMark slug={selected} />}>
            <ul className="space-y-2 text-sm">
              {exercises.map((pe) => {
                const t = totals[pe.exercise.slug];
                return (
                  <li key={pe.id} className="flex justify-between">
                    <span>{pe.exercise.name}</span>
                    <span className="tabular-nums text-beige-400">
                      {t ? `${t.repetitions} / ${pe.sets * pe.repetitions} reps · ${t.sets_recorded} sets · form ${pct(t.form_score)}` : "—"}
                    </span>
                  </li>
                );
              })}
            </ul>
            <Button className="mt-4 w-full" variant="secondary" onClick={finish}>Finish workout</Button>
          </Card>
        </div>
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------------------------------ */

function FinishStage({ session, exercises, totals, endedEarly, onDone }: {
  session: WorkoutSession; exercises: PlannedExercise[]; totals: Record<string, ExerciseLiveTotals>;
  endedEarly: boolean; onDone: (r: SessionCompleteResponse) => void;
}) {  // prettier-ignore
  const complete = useCompleteSession();
  const [difficulty, setDifficulty] = useState<number | null>(null);
  const [perExercise, setPerExercise] = useState<Record<string, { rating: string; manual: string }>>({});
  const [formError, setFormError] = useState<string | null>(null);

  const submit = async () => {
    if (difficulty == null) {
      setFormError("Please rate how hard the session felt.");
      return;
    }
    const items: CompletePayload["exercises"] = [];
    for (const pe of exercises) {
      const slug = pe.exercise.slug;
      const entry = perExercise[slug] ?? { rating: "", manual: "" };
      const manual = entry.manual.trim() === "" ? undefined : Number(entry.manual);
      if (manual !== undefined && (!Number.isInteger(manual) || manual < 0 || manual > 1000)) {
        setFormError(`Manual repetitions for ${pe.exercise.name} must be a whole number between 0 and 1000.`);
        return;
      }
      items.push({ exercise_slug: slug, difficulty_rating: entry.rating ? Number(entry.rating) : undefined, manual_repetitions: totals[slug] ? undefined : manual });
    }
    setFormError(null);
    try {
      onDone(await complete.mutateAsync({ sessionId: session.id, body: { perceived_difficulty: difficulty, ended_early: endedEarly, exercises: items } }));
    } catch (err) {
      setFormError(errorMessage(err));
    }
  };

  const setEntry = (slug: string, key: "rating" | "manual", value: string) =>
    setPerExercise((p) => ({ ...p, [slug]: { ...(p[slug] ?? { rating: "", manual: "" }), [key]: value } }));

  return (
    <div className="mx-auto max-w-3xl space-y-4">
      <PageHeader title="Finish session" subtitle={endedEarly ? "Session stopped early. That's okay; results so far are still recorded." : "Great work. A couple of quick questions."} />
      <Card title="How hard did it feel overall?">
        <div className="flex flex-wrap gap-2">
          {["Very easy", "Easy", "Just right", "Hard", "Very hard"].map((text, i) => (
            <Button key={text} variant={difficulty === i + 1 ? "primary" : "secondary"} onClick={() => setDifficulty(i + 1)} aria-pressed={difficulty === i + 1}>
              {i + 1} · {text}
            </Button>
          ))}
        </div>
      </Card>
      <Card title="Exercises">
        <div className="space-y-4">
          {exercises.map((pe) => {
            const t = totals[pe.exercise.slug];
            return (
              <div key={pe.id} className="grid items-end gap-3 border-b border-beige-100/10 pb-4 sm:grid-cols-3">
                <div>
                  <p className="font-medium">{pe.exercise.name}</p>
                  <p className="text-xs text-beige-400">
                    {t ? `Camera: ${t.repetitions} reps, form ${pct(t.form_score)}` : "No camera data recorded"}
                  </p>
                </div>
                <Field label="Difficulty (optional)">
                  <Select value={perExercise[pe.exercise.slug]?.rating ?? ""} onChange={(e) => setEntry(pe.exercise.slug, "rating", e.target.value)}>
                    <option value="">—</option>
                    {[1, 2, 3, 4, 5].map((n) => <option key={n} value={n}>{n}</option>)}
                  </Select>
                </Field>
                {!t && (
                  <Field label="Reps done (manual)" hint="Leave empty if skipped">
                    <Input type="number" min={0} value={perExercise[pe.exercise.slug]?.manual ?? ""} onChange={(e) => setEntry(pe.exercise.slug, "manual", e.target.value)} />
                  </Field>
                )}
              </div>
            );
          })}
        </div>
      </Card>
      {formError && <Alert tone="error">{formError}</Alert>}
      <Button onClick={submit} disabled={complete.isPending}>{complete.isPending ? "Saving…" : "Save session"}</Button>
    </div>
  );
}

function DoneStage({ result }: { result: SessionCompleteResponse }) {
  const s = result.session;
  const breakdown = s.score_breakdown as { weights_used?: Record<string, number>; consistency_score?: number; difficulty_adjustment?: number };
  return (
    <div className="space-y-6">
      <PageHeader title="Session saved" subtitle={`Session #${s.id}`} action={<Link to="/progress"><Button variant="secondary">View progress</Button></Link>} />
      <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
        <Stat label="Session score" value={pct(s.session_score)} />
        <Stat label="Completion" value={pct(s.completion_rate)} />
        <Stat label="Form score" value={pct(s.form_score)} hint={s.form_score == null ? "No live camera data" : undefined} />
        <Stat label="Consistency" value={pct(breakdown.consistency_score ?? null)} />
      </div>
      {breakdown.weights_used && (
        <p className="text-xs text-beige-400">
          Score weights used: {Object.entries(breakdown.weights_used).map(([k, v]) => `${label(k)} ${pct(v)}`).join(" · ")}
        </p>
      )}
      <div className="grid gap-6 lg:grid-cols-2">
        <Card title="Results">
          <ul className="space-y-3 text-sm">
            {s.results.map((r) => (
              <li key={r.id}>
                <div className="flex justify-between">
                  <span className="font-medium">{r.exercise_name}</span>
                  <span className="tabular-nums text-beige-400">
                    {r.repetitions}{r.planned_sets ? ` / ${r.planned_sets * r.planned_repetitions}` : ""} reps · {label(r.source)}
                  </span>
                </div>
                {r.feedback.length > 0 && (
                  <ul className="mt-1 list-disc pl-5 text-beige-300">
                    {r.feedback.map((f) => <li key={f.error_type}>{f.message} <span className="text-beige-500">(×{f.occurrences})</span></li>)}
                  </ul>
                )}
              </li>
            ))}
          </ul>
        </Card>
        <Card title={result.adaptation_applied ? "Your plan was updated" : "Plan review"}>
          <ul className="space-y-2 text-sm text-beige-200">
            {result.decisions.map((d, i) => (
              <li key={i}>
                <span className="mr-2 rounded bg-white/5 px-2 py-0.5 text-xs text-beige-300">{label(d.action)}</span>
                {d.reason}
              </li>
            ))}
            {result.decisions.length === 0 && <li>No adaptation was evaluated for this session.</li>}
          </ul>
          {result.guidance.length > 0 && (
            <div className="mt-4"><Alert tone="info" title="Guidance">{result.guidance.map((g) => <p key={g}>{g}</p>)}</Alert></div>
          )}
        </Card>
      </div>
    </div>
  );
}
