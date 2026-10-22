import { useEffect, useRef, useState } from "react";

import { EXERCISES, label } from "../api/types";
import { Alert, Button, Card, Field, Input, PageHeader, Select, Spinner } from "../components/ui";
import { PoseTracker, cameraErrorMessage, drawSkeleton, startCamera, stopCamera, type LandmarkArray } from "../lib/pose";

/**
 * Consent-based landmark recording for the custom dataset (Dataset B).
 * Everything stays in this browser: landmarks are kept in memory and downloaded as CSV.
 * No video is recorded and nothing is uploaded to the server.
 */

interface Recording {
  sample_id: string;
  participant_id: string;
  exercise_label: string;
  form_label: string;
  error_label: string;
  true_repetitions: string;
  width: number;
  height: number;
  frames: LandmarkArray[];
}

const FPS = 30;

function toCsv(recordings: Recording[]): string {
  const header = ["sample_id", "participant_id", "exercise_label", "form_label", "error_label", "frame_index", "visibility_score", "image_width", "image_height"];
  for (let i = 0; i < 33; i++) header.push(`landmark_${i}_x`, `landmark_${i}_y`, `landmark_${i}_visibility`);
  const lines = [header.join(",")];
  const esc = (s: string) => (/[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s);
  for (const r of recordings) {
    r.frames.forEach((f, idx) => {
      const vis = f.reduce((a, p) => a + p[3], 0) / f.length;
      const row: (string | number)[] = [esc(r.sample_id), esc(r.participant_id), r.exercise_label, esc(r.form_label), esc(r.error_label), idx, vis.toFixed(4), r.width, r.height];
      for (const p of f) row.push(p[0].toFixed(5), p[1].toFixed(5), p[3].toFixed(4));
      lines.push(row.join(","));
    });
  }
  return lines.join("\n");
}

function download(name: string, text: string) {
  const url = URL.createObjectURL(new Blob([text], { type: "text/csv" }));
  const a = document.createElement("a");
  a.href = url;
  a.download = name;
  a.click();
  URL.revokeObjectURL(url);
}

export default function DataCollectionPage() {
  const videoRef = useRef<HTMLVideoElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const trackerRef = useRef<PoseTracker | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const rafRef = useRef<number | null>(null);
  const recordingRef = useRef<Recording | null>(null);
  const lastRef = useRef(0);

  const [consent, setConsent] = useState(false);
  const [meta, setMeta] = useState({ participant_id: "P01", exercise_label: "squat", form_label: "correct", error_label: "", true_repetitions: "" });
  const [camera, setCamera] = useState<"off" | "starting" | "on">("off");
  const [recording, setRecording] = useState(false);
  const [frameCount, setFrameCount] = useState(0);
  const [recordings, setRecordings] = useState<Recording[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => () => {
    if (rafRef.current) cancelAnimationFrame(rafRef.current);
    stopCamera(streamRef.current);
    trackerRef.current?.close();
  }, []);

  const loop = () => {
    const video = videoRef.current, canvas = canvasRef.current, tracker = trackerRef.current;
    const now = performance.now();
    if (video && canvas && tracker && video.readyState >= 2 && now - lastRef.current >= 1000 / FPS) {
      lastRef.current = now;
      canvas.width = video.videoWidth;
      canvas.height = video.videoHeight;
      const lm = tracker.detect(video, now);
      const ctx = canvas.getContext("2d");
      if (ctx) drawSkeleton(ctx, lm, recordingRef.current ? "#ef4444" : "#22c55e");
      if (recordingRef.current && lm) {
        recordingRef.current.frames.push(lm);
        setFrameCount(recordingRef.current.frames.length);
      }
    }
    rafRef.current = requestAnimationFrame(loop);
  };

  const enableCamera = async () => {
    setError(null);
    setCamera("starting");
    try {
      trackerRef.current ??= await PoseTracker.create();
      streamRef.current = await startCamera(videoRef.current!);
      setCamera("on");
      rafRef.current = requestAnimationFrame(loop);
    } catch (e) {
      setError(cameraErrorMessage(e));
      setCamera("off");
    }
  };

  const toggleRecording = () => {
    if (recording) {
      const r = recordingRef.current;
      recordingRef.current = null;
      setRecording(false);
      if (r && r.frames.length) setRecordings((rs) => [...rs, r]);
      return;
    }
    if (!meta.participant_id.trim()) {
      setError("Enter a pseudonymous participant ID (no names).");
      return;
    }
    const video = videoRef.current!;
    const n = recordings.filter((r) => r.participant_id === meta.participant_id).length + 1;
    recordingRef.current = {
      ...meta,
      sample_id: `${meta.participant_id}_${meta.exercise_label}_${meta.form_label}_${String(n).padStart(3, "0")}`,
      width: video.videoWidth,
      height: video.videoHeight,
      frames: [],
    };
    setFrameCount(0);
    setRecording(true);
  };

  return (
    <div className="space-y-6">
      <PageHeader title="Dataset collection" subtitle="Record pose landmarks (not video) from consenting volunteers for model training." />
      <Alert tone="warning" title="Consent and ethics">
        Only record volunteers who have given informed consent under your institution's process. Use pseudonymous IDs
        (e.g. P01), never names. Landmarks stay in this browser until you download the CSV.
      </Alert>
      <label className="flex items-center gap-2 text-sm">
        <input type="checkbox" checked={consent} onChange={(e) => setConsent(e.target.checked)} />
        The participant has given informed consent for this recording.
      </label>
      {error && <Alert tone="error">{error}</Alert>}

      <div className="grid gap-6 lg:grid-cols-3">
        <div className="lg:col-span-2">
          <div className="relative aspect-[4/3] overflow-hidden rounded-xl bg-espresso-950">
            <video ref={videoRef} className="absolute inset-0 h-full w-full -scale-x-100 object-cover" playsInline muted />
            <canvas ref={canvasRef} className="absolute inset-0 h-full w-full -scale-x-100 object-cover" />
            {camera !== "on" && (
              <div className="absolute inset-0 flex items-center justify-center">
                {camera === "starting" ? <Spinner label="Starting…" /> : <Button disabled={!consent} onClick={enableCamera}>Enable camera</Button>}
              </div>
            )}
            {recording && <span className="absolute left-3 top-3 rounded-full bg-red-600 px-3 py-1 text-sm text-white">● REC {frameCount} frames</span>}
          </div>
        </div>
        <Card title="Sample labels">
          <div className="space-y-3">
            <Field label="Participant ID"><Input value={meta.participant_id} disabled={recording} onChange={(e) => setMeta({ ...meta, participant_id: e.target.value.replace(/[^\w-]/g, "") })} /></Field>
            <Field label="Exercise">
              <Select value={meta.exercise_label} disabled={recording} onChange={(e) => setMeta({ ...meta, exercise_label: e.target.value })}>
                {EXERCISES.map((x) => <option key={x} value={x}>{label(x)}</option>)}
              </Select>
            </Field>
            <Field label="Form label">
              <Select value={meta.form_label} disabled={recording} onChange={(e) => setMeta({ ...meta, form_label: e.target.value, error_label: e.target.value === "correct" ? "" : meta.error_label })}>
                <option value="correct">Correct</option>
                <option value="incorrect">Incorrect</option>
              </Select>
            </Field>
            {meta.form_label === "incorrect" && (
              <Field label="Error type" hint="e.g. knees_caving, hip_sag, elbow_drift">
                <Input value={meta.error_label} disabled={recording} onChange={(e) => setMeta({ ...meta, error_label: e.target.value.toLowerCase().replace(/[^a-z_]/g, "") })} />
              </Field>
            )}
            <Field label="True repetitions (manual count)" hint="Used to evaluate the rep counter">
              <Input type="number" min={0} value={meta.true_repetitions} onChange={(e) => setMeta({ ...meta, true_repetitions: e.target.value })} />
            </Field>
            <Button className="w-full" variant={recording ? "danger" : "primary"} disabled={camera !== "on" || !consent} onClick={toggleRecording}>
              {recording ? "Stop recording" : "Start recording"}
            </Button>
          </div>
        </Card>
      </div>

      <Card
        title={`Recorded samples (${recordings.length})`}
        action={recordings.length > 0 && (
          <div className="flex gap-2">
            <Button variant="secondary" onClick={() => download(`fitai_landmarks_${Date.now()}.csv`, toCsv(recordings))}>Download landmarks CSV</Button>
            <Button variant="secondary" onClick={() => download(`fitai_rep_counts_${Date.now()}.csv`, "sample_id,true_repetitions\n" + recordings.filter((r) => r.true_repetitions !== "").map((r) => `${r.sample_id},${r.true_repetitions}`).join("\n"))}>
              Download rep counts CSV
            </Button>
          </div>
        )}
      >
        {recordings.length === 0 ? <p className="text-sm text-beige-400">No samples yet.</p> : (
          <ul className="divide-y divide-white/8 text-sm">
            {recordings.map((r, i) => (
              <li key={r.sample_id + i} className="flex items-center justify-between py-2">
                <span>{r.sample_id} · {r.frames.length} frames{r.error_label && ` · ${r.error_label}`}</span>
                <Button variant="ghost" onClick={() => setRecordings((rs) => rs.filter((_, j) => j !== i))}>Remove</Button>
              </li>
            ))}
          </ul>
        )}
      </Card>
    </div>
  );
}
