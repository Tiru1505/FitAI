import { liveSocketUrl } from "../api/client";
import type { ExerciseSlug, LiveAnalysis, LiveSetSummary, ModelStatus } from "../api/types";
import type { LandmarkArray } from "./pose";

interface Handlers {
  onAnalysis: (a: LiveAnalysis) => void;
  onError: (message: string) => void;
  onClose: () => void;
}

/**
 * WebSocket client for /api/inference/live.
 * Applies simple back-pressure: a new frame is only sent once the previous one was answered,
 * otherwise it is dropped and counted (reported to the server as client_stats).
 */
export class LiveInferenceClient {
  private ws: WebSocket | null = null;
  private pendingSince: number | null = null;
  private waiters: { type: string; resolve: (data: unknown) => void; reject: (e: Error) => void }[] = [];
  stats = { frames_captured: 0, frames_sent: 0, frames_dropped: 0 };

  constructor(private token: string, private handlers: Handlers) {}

  connect(): Promise<void> {
    return new Promise((resolve, reject) => {
      const ws = new WebSocket(liveSocketUrl(this.token));
      this.ws = ws;
      ws.onopen = () => resolve();
      ws.onerror = () => reject(new Error("Could not connect to the live analysis service."));
      ws.onclose = (ev) => {
        this.waiters.forEach((w) => w.reject(new Error("Connection closed")));
        this.waiters = [];
        if (ev.code === 1008) this.handlers.onError("Live analysis rejected the connection: please sign in again.");
        this.handlers.onClose();
      };
      ws.onmessage = (ev) => this.handleMessage(ev.data);
    });
  }

  private handleMessage(raw: string) {
    let data: { type?: string; detail?: string };
    try {
      data = JSON.parse(raw);
    } catch {
      return;
    }
    if (data.type === "analysis") {
      this.pendingSince = null;
      this.handlers.onAnalysis(data as LiveAnalysis);
      return;
    }
    if (data.type === "error") {
      this.pendingSince = null;
      const waiter = this.waiters.shift();
      if (waiter) waiter.reject(new Error(data.detail ?? "error"));
      else this.handlers.onError(data.detail ?? "Live analysis error");
      return;
    }
    const idx = this.waiters.findIndex((w) => w.type === data.type);
    if (idx >= 0) this.waiters.splice(idx, 1)[0].resolve(data);
  }

  private request<T>(message: object, responseType: string): Promise<T> {
    if (!this.ws || this.ws.readyState !== WebSocket.OPEN) return Promise.reject(new Error("Not connected"));
    return new Promise<T>((resolve, reject) => {
      this.waiters.push({ type: responseType, resolve: resolve as (d: unknown) => void, reject });
      this.ws!.send(JSON.stringify(message));
    });
  }

  configure(exercise: ExerciseSlug, sessionId: number | null) {
    this.stats = { frames_captured: 0, frames_sent: 0, frames_dropped: 0 };
    return this.request<{ model_status: ModelStatus }>(
      { type: "config", expected_exercise: exercise, session_id: sessionId },
      "ready",
    );
  }

  /** Returns true if the frame was sent, false if it was dropped because the server is still busy. */
  sendFrame(landmarks: LandmarkArray | null, width: number, height: number, timestampMs: number): boolean {
    this.stats.frames_captured++;
    const now = performance.now();
    if (!this.ws || this.ws.readyState !== WebSocket.OPEN || (this.pendingSince !== null && now - this.pendingSince < 1000)) {
      this.stats.frames_dropped++;
      return false;
    }
    this.pendingSince = now;
    this.stats.frames_sent++;
    this.ws.send(JSON.stringify({ type: "frame", landmarks, image_width: width, image_height: height, timestamp_ms: timestampMs }));
    return true;
  }

  /** Ends the current set; with save=true the server adds it to the session's stored results. */
  endSet(save: boolean) {
    const stats = { ...this.stats };
    this.stats = { frames_captured: 0, frames_sent: 0, frames_dropped: 0 };
    return this.request<LiveSetSummary>({ type: "end", save, client_stats: stats }, "summary");
  }

  close() {
    if (this.ws) {
      this.ws.onclose = null;
      this.ws.close();
    }
    this.ws = null;
  }
}
