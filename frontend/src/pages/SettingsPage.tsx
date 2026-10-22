import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";

import { errorMessage } from "../api/client";
import { useDeleteData, useMe, useModelStatus, useNotices } from "../api/hooks";
import { label } from "../api/types";
import { useAuth } from "../auth/AuthContext";
import { CameraIcon, ChartIcon, ShieldIcon, SparkIcon } from "../components/icons";
import { Alert, Button, Card, Field, Input, PageHeader } from "../components/ui";

export default function SettingsPage() {
  const me = useMe();
  const notices = useNotices();
  const models = useModelStatus();
  const del = useDeleteData();
  const { logout } = useAuth();
  const qc = useQueryClient();
  const navigate = useNavigate();
  const [confirmText, setConfirmText] = useState("");
  const [mode, setMode] = useState<"keep" | "all" | null>(null);
  const [done, setDone] = useState<string | null>(null);

  const runDelete = async () => {
    if (!mode) return;
    try {
      const r = await del.mutateAsync(mode === "keep");
      if (r.account_deleted) {
        logout();
        navigate("/login");
        return;
      }
      const total = Object.values(r.deleted).reduce((a, b) => a + b, 0);
      setDone(`Deleted ${total} stored records. Your login was kept.`);
      setMode(null);
      setConfirmText("");
      qc.invalidateQueries();
      navigate("/profile");
    } catch {
      /* error shown below */
    }
  };

  return (
    <div className="space-y-6">
      <PageHeader title="Settings & privacy" />
      {done && <Alert tone="success">{done}</Alert>}

      <div className="grid gap-6 lg:grid-cols-2">
        <Card title="Account" icon={<SparkIcon />}>
          <p className="text-sm text-beige-300">Signed in as <strong>{me.data?.email}</strong></p>
          <div className="mt-4 flex flex-wrap gap-2">
            <Link to="/profile"><Button variant="secondary">Edit profile & preferences</Button></Link>
            <Button variant="ghost" onClick={logout}>Sign out</Button>
          </div>
        </Card>

        <Card title="Safety guidance" icon={<ShieldIcon />}>
          <p className="text-sm text-beige-200">{notices.data?.safety}</p>
          {me.data?.profile?.safety_acknowledged_at && (
            <p className="mt-2 text-xs text-beige-400">Acknowledged on {new Date(me.data.profile.safety_acknowledged_at).toLocaleString()}</p>
          )}
        </Card>

        <Card title="Privacy notice" icon={<CameraIcon />}>
          <p className="text-sm text-beige-200">{notices.data?.privacy}</p>
          <ul className="mt-3 list-disc space-y-1 pl-5 text-sm text-beige-300">
            <li>The camera runs only on the Live session page and stops when you press Stop session or turn the camera off.</li>
            <li>Stored: profile, plans, session results, form feedback messages, optional weight logs.</li>
            <li>Not stored: video, images, or raw landmark streams.</li>
            <li>Your sign-in token is kept in this browser's local storage until you sign out.</li>
          </ul>
        </Card>

        <Card title="AI models" icon={<ChartIcon />}>
          {models.data ? (
            <div className="space-y-2 text-sm">
              <p>
                <strong>Exercise recognition (BiLSTM):</strong>{" "}
                {models.data.exercise_classifier.available ? `loaded (${models.data.exercise_classifier.model_type})` : label(models.data.exercise_classifier.status)}
              </p>
              <p>
                <strong>Form classifiers:</strong>{" "}
                {Object.entries(models.data.form_classifiers).filter(([, m]) => m.available).map(([k]) => label(k)).join(", ") || "none loaded; rule-based form checks are used"}
              </p>
              <p className="text-beige-400">Repetition counting always uses explainable joint-angle rules.</p>
            </div>
          ) : <p className="text-sm text-beige-400">Loading…</p>}
          <Link to="/data-collection" className="mt-3 inline-block text-sm text-plum-300 underline">Dataset collection tool (researchers)</Link>
        </Card>
      </div>

      <Card title="Delete my data" className="border-rose-400/30">
        <p className="text-sm text-beige-300">Deletion is permanent and cannot be undone.</p>
        <div className="mt-3 flex flex-wrap gap-2">
          <Button variant={mode === "keep" ? "danger" : "secondary"} onClick={() => setMode("keep")}>Delete profile, plans and sessions</Button>
          <Button variant={mode === "all" ? "danger" : "secondary"} onClick={() => setMode("all")}>Delete everything including my account</Button>
        </div>
        {mode && (
          <div className="mt-4 max-w-md space-y-3">
            <Field label='Type "DELETE" to confirm'>
              <Input value={confirmText} onChange={(e) => setConfirmText(e.target.value)} />
            </Field>
            {del.isError && <Alert tone="error">{errorMessage(del.error)}</Alert>}
            <div className="flex gap-2">
              <Button variant="danger" disabled={confirmText !== "DELETE" || del.isPending} onClick={runDelete}>
                {del.isPending ? "Deleting…" : "Permanently delete"}
              </Button>
              <Button variant="ghost" onClick={() => { setMode(null); setConfirmText(""); }}>Cancel</Button>
            </div>
          </div>
        )}
      </Card>
    </div>
  );
}
