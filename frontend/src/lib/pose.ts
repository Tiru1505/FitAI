import { FilesetResolver, PoseLandmarker } from "@mediapipe/tasks-vision";

const WASM_PATH = `${import.meta.env.BASE_URL}mediapipe/wasm`;
const MODEL_URL =
  (import.meta.env.VITE_POSE_MODEL_URL as string | undefined) ||
  "https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_lite/float16/latest/pose_landmarker_lite.task";

/** 33 landmarks as [x, y, z, visibility], the payload format expected by the FitAI API. */
export type LandmarkArray = number[][];

/** Runs MediaPipe Pose Landmarker locally in the browser. Video frames never leave the device. */
export class PoseTracker {
  private constructor(private landmarker: PoseLandmarker) {}

  static async create(): Promise<PoseTracker> {
    const fileset = await FilesetResolver.forVisionTasks(WASM_PATH);
    const options = (delegate: "GPU" | "CPU") => ({
      baseOptions: { modelAssetPath: MODEL_URL, delegate },
      runningMode: "VIDEO" as const,
      numPoses: 1,
      minPoseDetectionConfidence: 0.5,
      minPosePresenceConfidence: 0.5,
      minTrackingConfidence: 0.5,
    });
    try {
      return new PoseTracker(await PoseLandmarker.createFromOptions(fileset, options("GPU")));
    } catch {
      return new PoseTracker(await PoseLandmarker.createFromOptions(fileset, options("CPU")));
    }
  }

  detect(video: HTMLVideoElement, timestampMs: number): LandmarkArray | null {
    const result = this.landmarker.detectForVideo(video, timestampMs);
    const pose = result.landmarks[0];
    if (!pose || pose.length < 33) return null;
    return pose.slice(0, 33).map((p) => [
      clamp(p.x, -2, 3),
      clamp(p.y, -2, 3),
      clamp(p.z ?? 0, -10, 10),
      clamp(p.visibility ?? 0, 0, 1),
    ]);
  }

  close() {
    this.landmarker.close();
  }
}

const clamp = (v: number, lo: number, hi: number) => (Number.isFinite(v) ? Math.min(hi, Math.max(lo, v)) : 0);

const CONNECTIONS: [number, number][] = [
  [11, 12], [11, 13], [13, 15], [12, 14], [14, 16], [11, 23], [12, 24], [23, 24],
  [23, 25], [25, 27], [24, 26], [26, 28], [27, 31], [28, 32], [27, 29], [28, 30],
];

/** Local visualisation only: draws the detected skeleton over the (mirrored) video. */
export function drawSkeleton(ctx: CanvasRenderingContext2D, landmarks: LandmarkArray | null, color: string, minVisibility = 0.5) {
  const { width, height } = ctx.canvas;
  ctx.clearRect(0, 0, width, height);
  if (!landmarks) return;
  ctx.lineWidth = 4;
  ctx.strokeStyle = color;
  for (const [a, b] of CONNECTIONS) {
    const pa = landmarks[a], pb = landmarks[b];
    if (pa[3] < minVisibility || pb[3] < minVisibility) continue;
    ctx.beginPath();
    ctx.moveTo(pa[0] * width, pa[1] * height);
    ctx.lineTo(pb[0] * width, pb[1] * height);
    ctx.stroke();
  }
  ctx.fillStyle = "#ffffff";
  for (let i = 11; i < 33; i++) {
    const p = landmarks[i];
    if (p[3] < minVisibility) continue;
    ctx.beginPath();
    ctx.arc(p[0] * width, p[1] * height, 4, 0, Math.PI * 2);
    ctx.fill();
  }
}

/**
 * Capture presets. A webcam's field of view is fixed in hardware, but many laptop cameras crop a
 * 4:3 image out of a 16:9 sensor, so asking for a 16:9 resolution often returns a visibly wider
 * picture — which is what matters when the whole body has to fit in frame.
 */
export const CAMERA_PRESETS = [
  { id: "hd", label: "Wide 16:9 — 1280×720 (recommended)", width: 1280, height: 720 },
  { id: "fullhd", label: "Widest 16:9 — 1920×1080", width: 1920, height: 1080 },
  { id: "sd", label: "Standard 4:3 — 640×480", width: 640, height: 480 },
] as const;

export type CameraPresetId = (typeof CAMERA_PRESETS)[number]["id"];

export interface CameraOptions {
  deviceId?: string;
  preset?: CameraPresetId;
}

export async function startCamera(video: HTMLVideoElement, options: CameraOptions = {}): Promise<MediaStream> {
  if (!navigator.mediaDevices?.getUserMedia) {
    throw new Error("Camera access is not supported in this browser (a secure context such as localhost is required).");
  }
  const preset = CAMERA_PRESETS.find((p) => p.id === options.preset) ?? CAMERA_PRESETS[0];
  const constraints: MediaTrackConstraints = {
    width: { ideal: preset.width },
    height: { ideal: preset.height },
    aspectRatio: { ideal: preset.width / preset.height },
  };
  if (options.deviceId) constraints.deviceId = { exact: options.deviceId };
  else constraints.facingMode = "user";

  let stream: MediaStream;
  try {
    stream = await navigator.mediaDevices.getUserMedia({ video: constraints, audio: false });
  } catch (error) {
    // A camera that cannot deliver the requested size fails with OverconstrainedError: retry loosely.
    if (!(error instanceof DOMException) || error.name !== "OverconstrainedError") throw error;
    stream = await navigator.mediaDevices.getUserMedia({
      video: options.deviceId ? { deviceId: { exact: options.deviceId } } : { facingMode: "user" },
      audio: false,
    });
  }
  video.srcObject = stream;
  await video.play();
  return stream;
}

/** Cameras only appear with labels once permission has been granted, so call this after startCamera. */
export async function listCameras(): Promise<MediaDeviceInfo[]> {
  if (!navigator.mediaDevices?.enumerateDevices) return [];
  try {
    return (await navigator.mediaDevices.enumerateDevices()).filter((d) => d.kind === "videoinput");
  } catch {
    return [];
  }
}

export interface ZoomCapability {
  min: number;
  max: number;
  step: number;
  value: number;
}

/** Some cameras expose optical/digital zoom; zooming out fits more of the body in frame. */
export function zoomCapability(stream: MediaStream | null): ZoomCapability | null {
  const track = stream?.getVideoTracks()[0];
  if (!track?.getCapabilities) return null;
  const caps = track.getCapabilities() as MediaTrackCapabilities & { zoom?: { min: number; max: number; step?: number } };
  const settings = track.getSettings() as MediaTrackSettings & { zoom?: number };
  if (!caps.zoom) return null;
  return { min: caps.zoom.min, max: caps.zoom.max, step: caps.zoom.step ?? 0.1, value: settings.zoom ?? caps.zoom.min };
}

export async function applyZoom(stream: MediaStream | null, value: number): Promise<void> {
  const track = stream?.getVideoTracks()[0];
  if (!track) return;
  await track.applyConstraints({ advanced: [{ zoom: value } as MediaTrackConstraintSet] });
}

export function streamResolution(stream: MediaStream | null): { width: number; height: number } | null {
  const settings = stream?.getVideoTracks()[0]?.getSettings();
  return settings?.width && settings?.height ? { width: settings.width, height: settings.height } : null;
}

/** Which body regions are usable for analysis, judged locally to help the user frame the shot. */
export interface FramingCheck {
  shoulders: boolean;
  hips: boolean;
  knees: boolean;
  ankles: boolean;
  insideFrame: boolean;
}

const REGIONS: Record<keyof Omit<FramingCheck, "insideFrame">, [number, number]> = {
  shoulders: [11, 12],
  hips: [23, 24],
  knees: [25, 26],
  ankles: [27, 28],
};

export function checkFraming(landmarks: LandmarkArray | null, minVisibility = 0.5): FramingCheck | null {
  if (!landmarks) return null;
  const visible = (pair: [number, number]) => pair.some((i) => landmarks[i][3] >= minVisibility);
  const used = Object.values(REGIONS).flat().filter((i) => landmarks[i][3] >= minVisibility);
  return {
    shoulders: visible(REGIONS.shoulders),
    hips: visible(REGIONS.hips),
    knees: visible(REGIONS.knees),
    ankles: visible(REGIONS.ankles),
    // Landmarks outside 0..1 are MediaPipe extrapolating past the edge of the picture.
    insideFrame: used.length > 0 && used.every((i) => landmarks[i][0] > 0.02 && landmarks[i][0] < 0.98 && landmarks[i][1] > 0.02 && landmarks[i][1] < 0.98),
  };
}

export function stopCamera(stream: MediaStream | null, video?: HTMLVideoElement | null) {
  stream?.getTracks().forEach((t) => t.stop());
  if (video) video.srcObject = null;
}

export function cameraErrorMessage(error: unknown): string {
  if (error instanceof DOMException) {
    if (error.name === "NotAllowedError") return "Camera permission was denied. Allow camera access in your browser to use live analysis.";
    if (error.name === "NotFoundError") return "No camera was found on this device.";
    if (error.name === "NotReadableError") return "The camera is in use by another application.";
  }
  return error instanceof Error ? error.message : "Could not start the camera.";
}
